"""Opt-in existing mono capture owner; receipts do not prove AEC or acoustic age.

The reader performs no HTTP, expression actions or interruption callbacks. There
is one bounded assembler and one latest event; consumers perform control work.
"""
import array
from collections import deque
from dataclasses import dataclass
import math
import os
import selectors
import resource
import sys
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


class PremaskCanary:
    """Finite metadata-only observer. Lock order: pump -> mailbox, never reverse.

    The reader offers one immutable reference; only this worker computes RMS/VAD.
    No production VAD, utterances, controls, HTTP, history or PCM export.
    """
    MAX_BYTES = 3200
    TTL = .300
    LIMIT = 1000000

    def __init__(self, pump, deadline):
        self.pump = pump
        self.binding = pump.binding
        self.source_generation = pump.generation
        self.deadline = deadline
        self.condition = threading.Condition()
        self.active = True
        self.withdraw = threading.Event()
        self.closed_receipt = None
        self.slot = None
        self.inflight = False
        self.serial = 0
        self.reason = 'observing'
        self.reference = None
        self.observation_reference = None
        self.rss_scale = 1 if sys.platform == 'darwin' else 1024
        self.rss_start = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * self.rss_scale
        self.counts = dict(received=0, measured=0, idle=0, output_overlap=0,
                           unknown=0, rms_active=0, vad_active=0,
                           output_overlap_rms_active=0, output_overlap_vad_active=0)
        self.last_receipt = None
        self.last_offer = None
        self.cpu_seconds = 0.
        self.peak_rss_delta = 0
        self.started = pump.clock()
        self.thread = threading.Thread(target=self.run, name='reachy-premask-canary', daemon=True)

    def authority(self):
        p = self.pump
        a = p.agent
        policy, owner = a.motion_policy.owned_snapshot()
        return (p.permitted() and p.error is None
                and p.binding == self.binding and p.generation == self.source_generation and a._capture_pump is p
                and a.microphone_owner_id is None and owner is None
                and a.microphone.error is None and not policy['quiet'] and not policy['privacy_all'])

    def permitted(self):
        return (self.active and not self.withdraw.is_set()
                and self.pump.clock() < self.deadline and self.authority())

    def invalid_reason(self):
        return ('expired' if not self.withdraw.is_set() and self.authority()
                and self.pump.clock() >= self.deadline else 'authority_changed')

    def off(self, reason='off', clear=True):
        with self.condition:
            if self.active and reason in ('off', 'expired') and not self.withdraw.is_set():
                self.closed_receipt = dict(counts=dict(self.counts),
                    source_generation=self.source_generation, closed_monotonic=self.pump.clock(),
                    worker_cpu_seconds=self.cpu_seconds,
                    observed_elapsed_seconds=max(0.,self.pump.clock()-self.started),
                    peak_rss_delta_bytes=self.peak_rss_delta,
                    resource_metric='worker_cpu_and_process_highwater_delta_not_isolated_rss',
                    last_overlap_written_reference=self.observation_reference)
            if reason not in ('off', 'expired'):
                self.closed_receipt = None
            self.withdraw.set()
            self.active = False
            self.serial += 1
            self.slot = None
            self.reference = None
            self.last_receipt = None
            self.observation_reference = None
            if clear:
                self.counts = {key: 0 for key in self.counts}
            self.reason = reason
            self.condition.notify_all()

    def offer(self, chunk, now):
        # Called only after the ordinary permitted check under pump.condition.
        # No permission/status callbacks, VAD, copies or control on this path.
        if not self.condition.acquire(blocking=False):
            # No waiting for the diagnostic worker on the production reader.
            self.withdraw.set()
            self.slot = None
            return
        try:
            if not self.active or self.withdraw.is_set():
                return
            a = self.pump.agent
            if (a.microphone_owner_id is not None or a.motion_policy.owner_id is not None
                    or a.microphone.error is not None or a._capture_pump is not self.pump
                    or self.pump.error is not None or type(chunk) is not bytes or not 0 < len(chunk) <= self.MAX_BYTES
                    or len(chunk) % 2 or self.slot is not None
                    or (self.last_offer is not None and now-self.last_offer > self.TTL)):
                self.off('expiry_or_gap_or_drop')
                return
            if now >= self.deadline:
                self.off('expired')
                return
            self.last_offer = now
            p = self.pump
            self.slot = (chunk, now, self.serial, p.playback_generation,
                         p.output_active, p.clock() < p.suppress_until, self.reference)
            self.counts['received'] = min(self.LIMIT, self.counts['received']+1)
            self.condition.notify()
        finally:
            self.condition.release()

    def written(self, generation, player, attempt, start, count, rate, now):
        with self.condition:
            if not self.active:
                return
            if (type(attempt) is not str or len(attempt) != 32
                    or any(c not in '0123456789abcdef' for c in attempt)
                    or type(player) is not int or player <= 0
                    or type(count) is not int or count <= 0 or type(start) is not int or start < 0
                    or type(rate) is not int or rate != 16000):
                self.off('reference_unknown')
                return
            old = self.reference
            if old is not None and (old['playback_generation'] != generation
                    or old['owned_player_pid'] != player or old['content_attempt_id'] != attempt
                    or old['accepted_end_byte'] != start):
                self.off('reference_gap')
                return
            self.reference = dict(playback_generation=generation, owned_player_pid=player,
                content_attempt_id=attempt, accepted_start_byte=start, accepted_end_byte=start+count,
                accepted_bytes=count, sample_rate=rate, written_receipt_monotonic=now)

    def transition(self):
        with self.condition:
            # Withdraw all queued/inflight results, without re-aging/rebinding.
            self.serial += 1
            self.slot = None
            self.reference = None
            self.last_receipt = None

    def snapshot(self):
        # Caller never holds mailbox while asking for authority.
        if self.active and not self.permitted():
            self.off(self.invalid_reason())
        with self.condition:
            return dict(enabled=self.active, purpose='local_premask_activity_only', reason=self.reason,
                source_generation=self.source_generation, binding=list(self.binding),
                deadline_monotonic=self.deadline, counts=dict(self.counts),
                last_read_receipt_monotonic=self.last_receipt,
                freshness_seconds=(None if self.last_receipt is None else max(0., self.pump.clock()-self.last_receipt)),
                written_reference=(None if self.reference is None else dict(self.reference)),
                last_overlap_written_reference=(None if self.observation_reference is None
                    else dict(self.observation_reference)),
                worker_alive=self.thread.is_alive(), pcm_export_bytes=0, history_entries=0,
                closed_receipt=self.closed_receipt, worker_cpu_seconds=self.cpu_seconds,
                observed_elapsed_seconds=max(0.,self.pump.clock()-self.started),
                peak_rss_delta_bytes=self.peak_rss_delta,
                resource_metric='worker_cpu_and_process_highwater_delta_not_isolated_rss',
                acoustic_alignment_verified=False, speaker_identity='unknown')

    def run(self):
        chunk = item = None
        try:
            # A distinct instance; production a.vad is never touched.
            import webrtcvad
            vad = webrtcvad.Vad(self.pump.agent.audio['vad_mode'])
            cpu_started = time.thread_time()
            while True:
                with self.condition:
                    if not self.active:
                        return
                    if self.withdraw.is_set():
                        self.off('withdrawn')
                        return
                    if self.slot is None:
                        self.condition.wait(timeout=min(.05, max(0., self.deadline-self.pump.clock())))
                    if not self.active:
                        return
                    if self.withdraw.is_set():
                        self.off('withdrawn')
                        return
                    item, self.slot = self.slot, None
                    self.inflight = item is not None
                # No mailbox lock across permission/policy/pump locks.
                if not self.permitted():
                    self.off(self.invalid_reason())
                    return
                if item is None:
                    continue
                chunk, received, serial, generation, output, tail, reference = item
                if not received <= self.pump.clock() <= min(received+self.TTL, self.deadline):
                    self.off('ttl')
                    return
                samples = memoryview(chunk).cast('h')
                rms = math.sqrt(sum(x*x for x in samples)/len(samples))
                a = self.pump.agent
                frame = a.vad_bytes
                speech = sum(vad.is_speech(memoryview(chunk)[i:i+frame], a.audio['sample_rate'])
                             for i in range(0, len(chunk)-frame+1, frame))
                self.cpu_seconds = time.thread_time()-cpu_started
                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * self.rss_scale
                self.peak_rss_delta = max(0,peak-self.rss_start)
                if self.peak_rss_delta > 8*1024*1024:
                    self.off('rss_ceiling')
                    return
                elapsed = self.pump.clock()-self.started
                if elapsed >= 1 and self.cpu_seconds/elapsed > .05:
                    self.off('cpu_ceiling')
                    return
                # Existing policy lock order is pump -> policy. Final authority,
                # generation and serial checks prevent late publication.
                with self.pump.condition:
                    if not self.permitted():
                        self.off('authority_or_deadline')
                        return
                    with self.condition:
                        if (not self.active or self.withdraw.is_set() or serial != self.serial
                                or generation != self.pump.playback_generation):
                            chunk = item = samples = None
                            self.inflight = False
                            continue
                        if self.pump.clock() > received+self.TTL:
                            self.off('ttl')
                            return
                        category = 'unknown' if tail else 'idle'
                        if output:
                            category = ('output_overlap' if reference is not None
                                and reference['playback_generation'] == generation
                                and reference['written_receipt_monotonic'] <= received else 'unknown')
                        for key in ('measured', category):
                            self.counts[key] = min(self.LIMIT, self.counts[key]+1)
                        for key, yes in (('rms_active', rms >= a.threshold), ('vad_active', speech > 0)):
                            self.counts[key] = min(self.LIMIT, self.counts[key]+int(yes))
                        if category == 'output_overlap':
                            self.observation_reference = reference
                            for key, yes in (('output_overlap_rms_active', rms >= a.threshold),
                                             ('output_overlap_vad_active', speech > 0)):
                                self.counts[key] = min(self.LIMIT, self.counts[key]+int(yes))
                        self.last_receipt = received
                chunk = item = samples = None
                with self.condition:
                    self.inflight = False
        except Exception:
            self.off('worker_failure')
        finally:
            chunk = item = None
            with self.condition:
                self.inflight = False
                self.slot = None


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
        self.accepted = None
        self.output_active = False
        self.playback_generation = 0
        self.canary = None
        self.candidate = None
        self.suppress_until = 0.
        self.counters = dict(read_bytes=0, read_frames=0, read_calls=0, chunks=0,
            overflow_events=0, overflow_bytes=0, superseded_events=0,
            suppressed_frames=0, gap_events=0, max_read_gap_seconds=0.,
            last_read_monotonic=None, raw_buffer_peak_bytes=0)

    def snapshot(self):
        """Actual os.read receipts, per source generation; never acoustic time."""
        with self.condition:
            return dict(self.counters, source_generation=self.generation,
                clock='monotonic_read_receipt', retired=self.retired.is_set(),
                output_suppressed=self.output_active or self.clock() < self.suppress_until,
                pending_events=int(self.latest is not None),
                overflow_frames=self.counters['overflow_bytes'] // 2,
                assembler_bytes=sum(map(len, self.assembler.frames)),
                raw_overflow_threshold_bytes=self.agent.chunk_bytes * 4,
                raw_capacity_bytes=self.agent.chunk_bytes * 9 - 1)

    def admitted(self, packet):
        # Queue TTL gates admission, not the duration of an already admitted
        # synchronous STT request. Its existing HTTP timeout still applies.
        with self.condition:
            return packet is not None and packet is self.accepted and self.permitted()

    def output(self, active):
        """Mask own output and a bounded tail. This is not AEC or barge-in."""
        with self.condition:
            if active:
                self.playback_generation += 1
            self.output_active = active
            if self.candidate is not None:
                self.candidate.transition(self.playback_generation, active)
            if self.canary is not None and self.canary.active:
                try: self.canary.transition()
                except Exception:
                    self._canary_off('transition_failure')
                    self.canary = None
            if not active:
                tail = self.agent.audio.get('echo_tail_seconds', .3)
                self.suppress_until = self.clock() + max(.3, min(2., tail))
            self.assembler.clear()
            self.assembler.number += 1
            self.assembler.revision = 0
            self.latest = None
            self.condition.notify_all()

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

    def _canary_off(self, reason):
        try:
            if self.canary is not None: self.canary.off(reason)
        except Exception:
            # A diagnostic failure must never fail/retire ordinary capture.
            try:
                self.canary.withdraw.set()
                self.canary.slot = None
            except Exception: pass

    def retire(self):
        # Nonblocking withdrawal may be called under the microphone lock.
        self.retired.set()
        self._canary_off('retired')
        if self.candidate is not None:self.candidate.cancel()
        with self.condition:
            self.latest = None
            self.accepted = None
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
            if self.canary is not None and self.canary.active and not self.canary.withdraw.is_set():
                try: self.canary.offer(chunk, now)
                except Exception:
                    try: self.canary.off('offer_failure')
                    except Exception: pass
            if self.output_active and self.candidate is not None:
                self.candidate.offer(chunk, now, self.playback_generation)
            if self.output_active or now < self.suppress_until:
                self.counters['suppressed_frames'] += len(chunk) // 2
                self.assembler.clear()
                self.latest = None
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
                self.counters['superseded_events'] += int(self.latest is not None)
                self.latest = None
            if result is not None:
                self.counters['superseded_events'] += int(self.latest is not None)
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
            self.accepted = packet
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
                if reply:
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
                    with self.condition:
                        self.counters['gap_events'] += 1
                        self.counters['max_read_gap_seconds'] = max(
                            self.counters['max_read_gap_seconds'], now-last)
                    raise RuntimeError('Capture receipt continuity lost')
                if not ready:
                    if process.poll() is not None:
                        raise RuntimeError('Capture process exited')
                    continue
                try:
                    data = os.read(process.stdout.fileno(), a.chunk_bytes * 8)
                except BlockingIOError:
                    continue
                if not data:
                    raise RuntimeError('Capture stream ended')
                now = self.clock()
                with self.condition:
                    self.counters['read_bytes'] += len(data)
                    self.counters['read_frames'] = self.counters['read_bytes'] // 2
                    self.counters['read_calls'] += 1
                    self.counters['last_read_monotonic'] = now
                    self.counters['max_read_gap_seconds'] = max(
                        self.counters['max_read_gap_seconds'], now-last)
                last = now
                buffered.extend(data)
                with self.condition:
                    self.counters['raw_buffer_peak_bytes'] = max(
                        self.counters['raw_buffer_peak_bytes'], len(buffered))
                    if len(buffered) > a.chunk_bytes * 4:
                        # Keep the latest complete chunk plus partial tail;
                        # never assemble an utterance across discarded PCM.
                        dropped = (len(buffered) // a.chunk_bytes - 1) * a.chunk_bytes
                        del buffered[:dropped]
                        self._canary_off('source_overflow')
                        if self.candidate is not None:self.candidate.cancel()
                        self.counters['overflow_events'] += 1
                        self.counters['overflow_bytes'] += dropped
                        self.assembler.clear()
                        self.assembler.number += 1
                        self.assembler.revision = 0
                        self.latest = None
                while len(buffered) >= a.chunk_bytes and self.permitted():
                    chunk = bytes(buffered[:a.chunk_bytes])
                    del buffered[:a.chunk_bytes]
                    with self.condition:
                        self.counters['chunks'] += 1
                    self._publish(chunk, now)
        except Exception:
            # Fixed class only: no ALSA private device/error text in status.
            self.error = 'Capture source unavailable'
        finally:
            self.retire()
            selector.close()
            if process is not None:
                try:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=a.config['timeouts']['process_stop'])
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=a.config['timeouts']['process_stop'])
                    process.stdout.close()
                except (OSError, subprocess.TimeoutExpired):
                    # Keep ownership and capture_active truthful after unknown
                    # reap; _capture_get/close must refuse a second child.
                    self.error = 'Capture reap unavailable'
                    return
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
