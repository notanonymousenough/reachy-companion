"""Opt-in mono AEC capture owner; receipt timestamps are not hardware timestamps.

The reader performs no HTTP, expression actions or interruption callbacks. There
is one bounded assembler and one latest event; consumers perform control work.
"""
import array
from collections import deque
from dataclasses import dataclass
import math
import os
import selectors
import statistics
import subprocess
import threading
import time


@dataclass(frozen=True)
class Utterance:
    binding: tuple
    source_generation: int
    number: int
    revision: int
    pcm: bytes
    received_end: float
    deadline: float
    final: bool
    # Deliberately no hardware-capture-time claim.
    clock: str = 'monotonic_read_receipt'


class Assembler:
    """Single-reader VAD state. Thresholds and frame sizes match finite capture."""
    def __init__(self, agent):
        self.agent = agent
        self.audio = agent.audio
        self.pre = deque(maxlen=self.audio['pre_roll_chunks'])
        self.noise = []
        self.number = self.revision = self.seen = 0
        self.frames = []
        self.voiced = self.silent = self.barge_voiced = 0
        self.probed = False

    def clear(self):
        self.pre.clear()
        self.frames = []
        self.voiced = self.silent = self.barge_voiced = 0
        self.probed = False

    def feed(self, chunk, during_reply):
        a = self.agent
        self.seen += 1
        samples = array.array('h', chunk)
        rms = math.sqrt(sum(s*s for s in samples) / len(samples))
        if not a.calibrated:
            self.noise.append(rms)
            self.pre.append(chunk)
            if len(self.noise) >= self.audio['calibration_chunks']:
                a.threshold = max(self.audio['rms_floor'], statistics.median(self.noise) * self.audio['noise_multiplier'])
                a.calibrated = True
                self.noise.clear()
            return None
        speech = sum(a.vad.is_speech(chunk[i:i+a.vad_bytes], self.audio['sample_rate'])
                     for i in range(0, len(chunk), a.vad_bytes))
        barge = a.config['conversation']['barge_in']
        threshold = a.threshold * (barge.get('threshold_multiplier', 1) if during_reply else 1)
        loud = rms >= threshold and speech >= self.audio['min_speech_frames']
        eligible = self.seen > barge.get('warmup_chunks', 9)
        self.barge_voiced = self.barge_voiced + 1 if loud and eligible else 0
        if not self.frames:
            self.pre.append(chunk)
            if loud:
                self.number += 1
                self.frames = list(self.pre)
                self.voiced = 1
                self.revision = 0
            return None
        self.frames.append(chunk)
        if loud:
            a.last_voice_at = time.monotonic()
            self.voiced += 1
            self.silent = 0
        else:
            self.silent += 1
        final = (self.silent >= self.audio['silence_chunks'] or
                 len(self.frames) >= self.audio['max_recording_seconds'] * 1000 / self.audio['chunk_ms'])
        probe = during_reply and not self.probed and loud and self.barge_voiced >= barge['min_voiced_chunks']
        result = None
        if (final and self.voiced >= self.audio['min_voiced_chunks']) or probe:
            self.revision += 1
            result = (self.number, self.revision, b''.join(self.frames), final)
            self.probed = True
        if final:
            self.clear()
        return result


class CapturePump:
    """One owned arecord, one reader, latest-only utterance event, no callbacks.

    A binding includes boot, mic epoch and policy epoch. Changes retire this
    source, never silently refresh its authority or re-age a pending packet.
    """
    def __init__(self, agent, generation, *, clock=time.monotonic, popen=subprocess.Popen):
        self.agent = agent
        self.generation = generation
        self.clock = clock
        self.popen = popen
        self.binding = self.current_binding()
        self.condition = threading.Condition()
        self.retired = threading.Event()
        self.thread = None
        self.process = None
        self.error = None
        self.latest = None
        self.claimed = 0
        self.reply = False
        self.assembler = Assembler(agent)

    def current_binding(self):
        a = self.agent
        policy = a.motion_policy.snapshot()
        if (not a.microphone.enabled or not a.listening.is_set() or a.stopping.is_set()
                or policy['quiet'] or policy['privacy_all']):
            return None
        return (a.agent_boot_id, a.microphone_epoch, policy['epoch'])

    def permitted(self):
        return not self.retired.is_set() and self.binding is not None and self.current_binding() == self.binding

    def fresh(self, packet):
        with self.condition:
            return (isinstance(packet, Utterance) and self.permitted()
                    and packet.binding == self.binding and packet.source_generation == self.generation
                    and packet.number == self.assembler.number
                    and packet.revision == self.assembler.revision
                    and packet.received_end <= self.clock() <= packet.deadline)

    def start(self):
        with self.condition:
            if self.thread is not None:
                return
            if not self.permitted():
                raise RuntimeError('Capture authority unavailable')
            self.thread = threading.Thread(target=self._read, name='reachy-aec-reader', daemon=True)
            self.thread.start()

    def retire(self):
        # Nonblocking withdrawal may be called under the microphone lock.
        self.retired.set()
        with self.condition:
            self.latest = None
            self.assembler.clear()
            self.assembler.noise.clear()
            self.condition.notify_all()

    def close(self):
        # The caller must not hold microphone_lock: a control worker may be
        # completing a STOP that needs it. Only this owned process is stopped.
        self.retire()
        thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self.agent.config['timeouts']['process_stop'] * 2 + 1)
            if thread.is_alive():
                raise RuntimeError('Capture reader did not reap')
        if self.process is not None:
            raise RuntimeError('Capture process still owned')

    def _publish(self, chunk, now):
        with self.condition:
            if not self.permitted():
                return
            # SoundMonitor.feed is bounded queue work; its existing separate
            # worker owns classification HTTP, never this reader.
            if not self.reply:
                self.agent.sounds.feed(chunk)
                if self.agent.sounds.music:
                    self.assembler.clear()
                    self.latest = None
                    return
            previous = self.assembler.number
            result = self.assembler.feed(chunk, self.reply)
            if self.assembler.number != previous:
                self.latest = None
            if result is not None:
                number, revision, pcm, final = result
                self.latest = Utterance(self.binding, self.generation, number, revision, pcm, now, now+2., final)
            self.condition.notify_all()

    def event(self, after=(0, 0), stop=None, idle_deadline=None, final_only=False):
        with self.condition:
            while self.permitted() and not (stop and stop.is_set()):
                packet = self.latest
                if (packet is not None and (packet.number, packet.revision) > after
                        and packet.number > self.claimed and self.fresh(packet)
                        and (packet.final or not final_only)):
                    return packet
                if self.error is not None:
                    raise RuntimeError(self.error)
                if idle_deadline is not None and self.clock() >= idle_deadline:
                    return None
                self.condition.wait(timeout=.05)
            return None

    def claim(self, packet):
        with self.condition:
            if not packet.final or packet.number <= self.claimed or not self.fresh(packet):
                return False
            self.claimed = packet.number
            self.latest = None
            return True

    def reject(self, packet):
        with self.condition:
            if (packet.number == self.assembler.number
                    and packet.revision == self.assembler.revision):
                self.claimed = max(self.claimed, packet.number)
                self.latest = None
                self.assembler.clear()

    def mode(self, reply):
        with self.condition:
            if self.reply != reply:
                self.reply = reply
                self.assembler.seen = 0
                self.assembler.clear()
                self.latest = None

    def _read(self):
        a = self.agent
        selector = selectors.DefaultSelector()
        process = None
        try:
            if not self.permitted():
                return
            command = ['arecord', '-q', '-D', a.audio['capture_device'], '-f', 'S16_LE',
                       '-r', str(a.audio['sample_rate']), '-c', '1', '-t', 'raw']
            process = self.popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            self.process = process
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            a.capture_active = True
            last = self.clock()
            buffered = bytearray()
            gap = max(.25, a.audio['chunk_ms'] / 1000 * 4)
            while self.permitted():
                ready = selector.select(timeout=.05)
                now = self.clock()
                if now-last > gap:
                    raise RuntimeError('Capture receipt continuity lost')
                if not ready:
                    if process.poll() is not None:
                        raise RuntimeError('Capture process exited')
                    continue
                try:
                    data = os.read(process.stdout.fileno(), a.chunk_bytes * 2)
                except BlockingIOError:
                    continue
                if not data:
                    raise RuntimeError('Capture stream ended')
                buffered.extend(data)
                if len(buffered) >= a.chunk_bytes * 2:
                    raise RuntimeError('Capture receipt backlog unknown')
                if len(buffered) >= a.chunk_bytes:
                    chunk = bytes(buffered[:a.chunk_bytes])
                    del buffered[:a.chunk_bytes]
                    last = now
                    self._publish(chunk, now)
        except Exception:
            # Fixed class only: no ALSA private device/error text in status.
            self.error = 'Capture source unavailable'
        finally:
            self.retire()
            selector.close()
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=a.config['timeouts']['process_stop'])
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=a.config['timeouts']['process_stop'])
                process.stdout.close()
            self.process = None
            a.capture_active = False


def barge_monitor(agent, pump):
    """Existing confirmation/echo/STOP logic, on a bounded consumer thread.

    The exact barge-in overlay adds a permit check after blocking STT and before
    any side effect. No callback is ever dispatched by the PCM reader.
    """
    from .barge_in import BargeInMonitor
    previous = getattr(agent, '_capture_control', None)
    if previous is not None and previous.thread.is_alive():
        raise RuntimeError('Previous capture control still active')

    class PumpMonitor(BargeInMonitor):
        def capture_stop_parameters(self):
            return dict(expected_boot_id=pump.binding[0], expected_epoch=self.epoch)

        def source_failed(self):
            if (getattr(self, '_source_woken', False) or pump.error is None
                    or self.stop.is_set() or pump.current_binding() != pump.binding):
                return
            self._source_woken = True
            agent.barge_in_error = 'Capture source unavailable'
            try:
                agent.stop_speaker()
            except OSError:
                # The voice finally scope still owns cleanup. Never retry a
                # wake against a potentially newer playback process.
                pass

        def run(self):
            after = (0, 0)
            accepted = None
            try:
                while not self.stop.is_set():
                    packet = pump.event(after, self.stop)
                    if packet is None:
                        self.source_failed()
                        return
                    after = (packet.number, packet.revision)
                    self.capture_permitted = lambda: pump.fresh(packet) and not self.stop.is_set()
                    if accepted != packet.number:
                        if not self.trigger(packet.pcm):
                            pump.reject(packet)
                            continue
                        accepted = packet.number
                    with pump.condition:
                        if packet.final and not self.stop.is_set() and pump.claim(packet):
                            self.pcm = packet
                            return
            except Exception:
                agent.barge_in_error = 'Capture control unavailable'
                self.source_failed()
            finally:
                # Release the closure's PCM reference after the bounded control
                # operation. Retirement already withdrew all action authority.
                self.capture_permitted = lambda: False

        def finish(self):
            packet = super().finish()
            self.pcm = None
            return packet if packet is not None and pump.fresh(packet) else None

    pump.mode(True)
    monitor = PumpMonitor(agent)
    agent._capture_control = monitor
    return monitor
