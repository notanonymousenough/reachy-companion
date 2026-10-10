#!/usr/bin/env python3
"""Reachy Mini microphone/speaker bridge. Uses the daemon's shared ALSA devices."""
import array
import base64
from collections import deque
import hmac
import io
import json
import logging
import math
import os
import selectors
import signal
import statistics
import subprocess
import threading
import time
import wave
from uuid import uuid4
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
import webrtcvad

LOG = logging.getLogger('reachy-voice-agent')



class Agent:
    def __init__(self, config):
        self.config = config
        self.audio = config['audio']
        self.http = build_opener(ProxyHandler({}))
        self.listening = threading.Event()
        from .microphone import MicrophoneState
        self.microphone = MicrophoneState(config.path(config['paths']['data_dir']) / 'microphone-state.json',
                                          config['conversation']['listen_on_start'])
        self.agent_boot_id = str(uuid4())
        self.microphone_epoch = self.microphone.epoch
        self.microphone_lock = threading.Lock()
        self.playback_process = None
        self.voice_response = None
        self.pending_pcm = None
        self.resume_audio = None
        self.resume_blocked_reason = None
        self.last_voice_at = None
        self.current_reply_text = ''
        self.interruptions = 0
        self.barge_in_error = None
        self.capture_active = False
        if self.microphone.enabled:
            self.listening.set()
        self.stopping = threading.Event()
        self.audio_lock = threading.Lock()
        self.phase = 'starting'
        self.threshold = self.audio['rms_floor']
        self.last_error = None
        self.last_transcript = None
        self.turns = 0
        self.calibrated = False
        self.playback_configured = False
        from .volume import PlaybackVolume
        self.volume = PlaybackVolume(config.path(config['paths']['data_dir']) / 'volume-state.json',
                                     self.audio.get('playback_mixer', {}).get('volume_percent', 95))
        self.volume_lock = threading.Lock()
        self.vad = webrtcvad.Vad(self.audio['vad_mode'])
        from .expression_player import ExpressionPlayer
        self.expressions = ExpressionPlayer(config, self.request, self.stopping)
        self.chunk_bytes = self.audio['sample_rate'] * 2 * self.audio['chunk_ms'] // 1000
        from .sound_monitor import SoundMonitor
        self.sounds = SoundMonitor(self)
        self.vad_bytes = self.audio['sample_rate'] * 2 * self.audio['vad_frame_ms'] // 1000

    def stop_speaker(self, abort_stream=True):
        process = self.playback_process
        if process is not None and process.poll() is None:
            process.terminate()
        # Wake a blocked urllib reader as well as stopping physical playback.
        response = self.voice_response
        if abort_stream and response is not None:
            try:
                import socket
                response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
            except (AttributeError, OSError):
                pass

    def set_microphone(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be boolean')
        with self.microphone_lock:
            self.microphone_epoch += 1
            self.listening.clear()
            if not enabled:
                self.microphone.enabled = False
                self.expressions.hold()
                self.pending_pcm = None
                self.resume_audio = None
                self.stop_speaker()
            try:
                self.microphone.save(enabled)
            except (OSError, ValueError):
                self.expressions.hold()
                self.pending_pcm = None
                self.resume_audio = None
                self.stop_speaker()
                raise
            self.sounds.reset()
            if enabled:
                self.listening.set()
        return {'ok': True, 'microphone_enabled': enabled, 'capture_active': self.capture_active,
                'agent_boot_id': self.agent_boot_id, 'microphone_epoch': self.microphone_epoch}

    def status(self):
        with self.microphone_lock:
            return {'listening': self.listening.is_set(), 'phase': self.phase,
                             'agent_boot_id': self.agent_boot_id, 'microphone_epoch': self.microphone_epoch,
                             'threshold_rms': self.threshold, 'last_error': self.last_error,
                             'last_transcript': self.last_transcript, 'turns': self.turns,
                             'microphone_enabled': self.microphone.enabled,
                             'interruptions': self.interruptions, 'resumable_reply': self.resume_audio is not None, 'barge_in_error': self.barge_in_error,
                             'resume_blocked_reason': self.resume_blocked_reason,
                             'playback_cursor_provenance': 'wall_time_estimate',
                             'motion_actor': self.motion_actor_status(),
                             'volume_percent': self.volume.percent,
                             'volume_control_enabled': self.audio.get('playback_mixer', {}).get('enabled', False),
                             'capture_active': self.capture_active,
                             'sound_mode': 'music' if self.sounds.music else 'conversation', 'sound_error': self.sounds.last_error,
                             'microphone_state_error': self.microphone.error,
                             'expression': self.expressions.last_expression,
                             'expression_error': self.expressions.last_error}

    def motion_actor_status(self):
        # Registration must follow native all-writer + physical stop acceptance.
        # A microphone switch is not a motor permission or this gate's blocker.
        return {'ready': False, 'enabled': self.config['guarded_motion']['enabled'],
                'reason': 'native_writer_fence_and_verified_stop_unaccepted'}

    def set_volume(self, percent):
        from .volume import validate_percent
        validate_percent(percent)
        if not self.audio.get('playback_mixer', {}).get('enabled', False):
            raise ValueError('Playback mixer control is disabled in configuration')
        with self.volume_lock:
            self.configure_playback(percent)
            self.volume.save(percent)
            self.playback_configured = True
        return {'ok': True, 'volume_percent': self.volume.percent}

    def configure_playback(self, percent=None):
        settings = self.audio.get('playback_mixer', {})
        if not settings.get('enabled', False):
            return
        percent = self.volume.percent if percent is None else percent
        subprocess.run(['amixer', '-c', str(settings['card']), 'sset',
                        settings['control'], str(percent) + '%', 'mute' if percent == 0 else 'unmute'],
                       capture_output=True, check=True, timeout=self.config['timeouts']['http'])
        LOG.info('playback_mixer card=%s control=%s volume=%s%%', settings['card'],
                 settings['control'], percent)

    def request(self, base, path, payload=None, timeout=None):
        request = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json',
                                   'Authorization': 'Bearer ' + self.config.token})
        try:
            with self.http.open(request, timeout=timeout or self.config['timeouts']['client']) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError('Hub HTTP %s: %s' % (exc.code, exc.read().decode()[:600])) from exc

    def capture(self, during_reply=False, on_speech=None, stop_event=None, idle_deadline=None, skip_expression=False):
        epoch = self.microphone_epoch
        def active():
            return (self.microphone.enabled if during_reply else self.listening.is_set()) and not self.stopping.is_set() and epoch == self.microphone_epoch and not (stop_event and stop_event.is_set())
        if not during_reply and not skip_expression:
            self.expressions.set('neutral', wait=True)
            self.phase = 'listening'
        if not active():
            return None
        confirmed = False
        barge_voiced = 0
        chunks_seen = 0
        barge = self.config['conversation'].get('barge_in', {})
        command = ['arecord', '-q', '-D', self.audio['capture_device'], '-f', 'S16_LE',
                   '-r', str(self.audio['sample_rate']), '-c', '1', '-t', 'raw']
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            self.capture_active = True
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            pre = deque(maxlen=self.audio['pre_roll_chunks'])
            frames = []
            noise = []
            voiced = 0
            silent = 0
            calibrating = not self.calibrated
            try:
                while active():
                    if idle_deadline is not None and time.monotonic() >= idle_deadline and not frames:
                        return None
                    if not selector.select(timeout=1):
                        if process.poll() is not None:
                            raise RuntimeError(process.stderr.read().decode()[:500])
                        continue
                    chunk = process.stdout.read(self.chunk_bytes)
                    if len(chunk) != self.chunk_bytes:
                        raise RuntimeError('Microphone stream ended: ' + process.stderr.read().decode()[:500])
                    chunks_seen += 1
                    if not during_reply:
                        self.sounds.feed(chunk)
                        if self.sounds.music:
                            frames = []; voiced = silent = 0
                            pre.clear()
                            self.phase = 'music'
                            continue
                    samples = array.array('h', chunk)
                    rms = math.sqrt(sum(s*s for s in samples) / len(samples))
                    if calibrating:
                        noise.append(rms)
                        pre.append(chunk)
                        if len(noise) >= self.audio['calibration_chunks']:
                            floor = self.audio['rms_floor']
                            self.threshold = max(floor, statistics.median(noise) * self.audio['noise_multiplier'])
                            LOG.info('listening threshold_rms=%.1f', self.threshold)
                            calibrating = False
                            self.calibrated = True
                        continue
                    speech_frames = sum(self.vad.is_speech(chunk[i:i+self.vad_bytes], self.audio['sample_rate'])
                                        for i in range(0, len(chunk), self.vad_bytes))
                    threshold = self.threshold * (barge.get('threshold_multiplier', 1) if during_reply else 1)
                    loud = rms >= threshold and speech_frames >= self.audio['min_speech_frames']
                    if during_reply and not confirmed:
                        eligible = chunks_seen > barge.get('warmup_chunks', 9)
                        barge_voiced = barge_voiced + 1 if loud and eligible else 0
                    if not frames:
                        pre.append(chunk)
                        if loud:
                            frames = list(pre)
                            voiced = 1
                            if not during_reply:
                                self.phase = 'recording'
                                self.expressions.set('listening', force=True)
                        continue
                    frames.append(chunk)
                    if loud:
                        self.last_voice_at = time.monotonic()
                        voiced += 1
                        silent = 0
                    else:
                        silent += 1
                    if during_reply and not confirmed and loud and barge_voiced >= barge['min_voiced_chunks']:
                        accepted = on_speech(b''.join(frames)) if on_speech else True
                        confirmed = accepted is not False
                        if not confirmed:
                            barge_voiced = 0
                            frames = []
                            voiced = silent = 0
                            continue
                    if silent >= self.audio['silence_chunks'] or len(frames) >= self.audio['max_recording_seconds'] * 1000 / self.audio['chunk_ms']:
                        if voiced >= self.audio['min_voiced_chunks'] and (not during_reply or confirmed):
                            return b''.join(frames) if active() else None
                        frames = []
                        voiced = silent = 0
                        if not during_reply:
                            self.phase = 'listening'
                return None
            finally:
                selector.close()
                process.terminate()
                try:
                    process.wait(timeout=self.config['timeouts']['process_stop'])
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                self.capture_active = False

    def play(self, encoded, epoch=None):
        if not encoded or not self.microphone.enabled or (epoch is not None and epoch != self.microphone_epoch):
            return
        self.phase = 'speaking'
        wav = base64.b64decode(encoded, validate=True)
        with wave.open(io.BytesIO(wav), 'rb') as stream:
            seconds = stream.getnframes() / stream.getframerate()
        with subprocess.Popen(['aplay', '-q', '-D', self.audio['playback_device']],
                              stdin=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            self.playback_process = process
            try:
                if not self.microphone.enabled or (epoch is not None and epoch != self.microphone_epoch):
                    process.terminate()
                    return
                _, error = process.communicate(wav, timeout=seconds + self.config['timeouts']['playback_margin'])
                if process.returncode and (epoch is None or epoch == self.microphone_epoch):
                    raise RuntimeError('Playback failed: ' + error.decode()[:500])
            finally:
                self.playback_process = None
                if process.poll() is None:
                    process.kill()
                    process.wait()
        time.sleep(self.audio['echo_tail_seconds'])

    def voice(self, path, payload, expected_epoch=None, allow_barge_in=True, replay=None):
        epoch = self.microphone_epoch if expected_epoch is None else expected_epoch
        monitor = None
        self.current_reply_text = replay.get('spoken_text', '') if replay else ''
        def cancelled():
            return not self.microphone.enabled or epoch != self.microphone_epoch or self.stopping.is_set()
        def interrupted():
            return bool(monitor and monitor.interrupted.is_set())
        def cancelled_result():
            return {'ok': True, 'cancelled': True, 'interrupted': bool(monitor and monitor.interrupted.is_set())}
        if cancelled():
            return cancelled_result()
        if replay is not None and replay.get('cursor_verified') is not True:
            self.resume_audio=None
            self.resume_blocked_reason='unverified_pcm_cursor'
            return {**cancelled_result(),'cancelled':True,'resume_blocked_reason':self.resume_blocked_reason}
        self.resume_blocked_reason=None
        if path in ('/text', '/turn'):
            self.expressions.set('processing')
        if not self.config['streaming']['enabled']:
            response = self.request(self.config['network']['voice_url'], path, payload)
            if cancelled():
                return cancelled_result()
            self.expressions.set('speaking', response.get('emotion', 'neutral'))
            try:
                self.play(response.get('audio_base64', ''), epoch)
            finally:
                self.expressions.hold()
                if not cancelled():self.expressions.set('neutral')
            return response
        item = Request(self.config['network']['voice_url'] + '/stream' + path,
                       data=json.dumps(payload).encode(),
                       headers={'Content-Type': 'application/json',
                                'Authorization': 'Bearer ' + self.config.token})
        process = None
        complete = False
        result = None
        total = 0
        settings = self.config['streaming']
        maximum = settings['sample_rate'] * 2 * settings['max_output_seconds']
        deadline = None
        selector = None
        from .speech_clock import SpeechClock
        clock = SpeechClock(settings['sample_rate'], settings['playback_latency_seconds'])
        full_pcm = bytearray()
        all_cues = []
        cursor = None
        from .replay import ReplayResponse
        response_context = self.http.open(item, timeout=self.config['timeouts']['client']) if replay is None else ReplayResponse(replay, settings)
        try:
            with response_context as response:
                self.voice_response = response
                if response.headers.get_content_type() != 'application/x-ndjson':
                    raise RuntimeError('Expected an audio event stream')
                while True:
                    if cancelled():
                        return cancelled_result()
                    line = response.readline(settings['max_event_bytes'] + 1)
                    if not line:
                        break
                    if len(line) > settings['max_event_bytes'] or not line.endswith(b'\n'):
                        raise ValueError('Invalid stream event size')
                    event = json.loads(line)
                    if event['type'] == 'reply':
                        result = event
                        self.current_reply_text += ' ' + event.get('reply', '')
                    elif event['type'] == 'motion':
                        if len(all_cues) + len(event['cues']) > self.config['conversation']['expressions']['speech_sync']['max_cues']:
                            raise ValueError('Too many speech motion cues')
                        all_cues.extend(event['cues'])
                        if not interrupted():
                            self.expressions.timeline(event['cues'], clock)
                    elif event['type'] == 'audio':
                        if cancelled():
                            return cancelled_result()
                        if event.get('sample_rate') != settings['sample_rate'] or event.get('format') != 'S16_LE' or event.get('channels') != 1:
                            raise ValueError('Unsupported stream audio format')
                        pcm = base64.b64decode(event['pcm_base64'], validate=True)
                        total += len(pcm)
                        if len(pcm) % 2 or total > maximum:
                            raise ValueError('Invalid stream audio length')
                        full_pcm.extend(pcm)
                        if interrupted():
                            if cursor is None:
                                cursor = clock.resume_cursor()
                            continue
                        if process is None:
                            if all_cues:
                                self.expressions.wait_timeline(clock)
                            if cancelled(): return cancelled_result()
                            self.phase = 'speaking'
                            if not all_cues:
                                self.expressions.set('speaking', (result or {}).get('emotion', 'neutral'))
                            process = subprocess.Popen(['aplay', '-q', '-D', self.audio['playback_device'],
                                '--buffer-time='+str(settings['playback_buffer_us']), '--period-time='+str(settings['playback_period_us']),
                                '-t', 'raw', '-f', 'S16_LE', '-r', str(settings['sample_rate']), '-c', '1'],
                                stdin=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                            self.playback_process = process
                            if allow_barge_in and self.microphone.enabled and self.config['conversation'].get('barge_in', {}).get('enabled', False):
                                from .barge_in import BargeInMonitor
                                monitor = BargeInMonitor(self)
                                monitor.start()
                            if cancelled():
                                return cancelled_result()
                            os.set_blocking(process.stdin.fileno(), False)
                            selector = selectors.DefaultSelector()
                            selector.register(process.stdin, selectors.EVENT_WRITE)
                            deadline = time.monotonic() + settings['max_output_seconds'] + self.config['timeouts']['playback_margin']
                        remaining = memoryview(pcm)
                        while remaining:
                            if interrupted():
                                if cursor is None:
                                    cursor = clock.resume_cursor()
                                break
                            if cancelled():
                                return cancelled_result()
                            if time.monotonic() > deadline:
                                raise TimeoutError('Streaming playback stopped or timed out')
                            if process.poll() is not None:
                                raise RuntimeError('Streaming playback failed')
                            if selector.select(timeout=0.2):
                                try:
                                    written = os.write(process.stdin.fileno(), remaining)
                                    clock.feed(written)
                                    remaining = remaining[written:]
                                except BrokenPipeError:
                                    if not interrupted():
                                        raise
                                except BlockingIOError:
                                    pass
                    elif event['type'] == 'done':
                        if result is None or not event.get('ok'):
                            raise RuntimeError('Invalid stream completion')
                        result = event
                        complete = True
                        break
                    elif event['type'] == 'error':
                        raise RuntimeError('Compute worker failed during audio stream')
                    else:
                        raise ValueError('Unknown stream event')
                if not complete:
                    raise RuntimeError('Audio stream ended without completion')
            if process is not None:
                process.stdin.close()
                process.wait(timeout=max(1, deadline - time.monotonic()))
                if cancelled():
                    return cancelled_result()
                if process.returncode and not interrupted():
                    raise RuntimeError('Streaming playback failed')
                if not interrupted():
                    time.sleep(self.audio['echo_tail_seconds'])
            if interrupted():
                if cursor is None:
                    cursor = clock.resume_cursor()
                if cursor is None:
                    self.resume_audio=None
                    self.resume_blocked_reason='unverified_pcm_cursor'
                    return {**{key:value for key,value in result.items() if key!='type'},
                            **cancelled_result(),'resume_blocked_reason':self.resume_blocked_reason}
                self.resume_audio = {'pcm': bytes(full_pcm), 'cursor': min(cursor, len(full_pcm)),
                                     'cursor_verified': True,
                                     'result': {key: value for key, value in result.items() if key != 'type'},
                                     'cues': all_cues, 'epoch': epoch, 'spoken_text': self.current_reply_text,
                                     'deadline': (self.last_voice_at or time.monotonic()) + self.config['conversation']['interaction']['resume_after_empty_seconds']}
                return {**self.resume_audio['result'], **cancelled_result()}
            self.resume_audio = None
            return {key: value for key, value in result.items() if key != 'type'}
        except Exception:
            if cancelled() or interrupted():
                self.resume_audio = None
                return cancelled_result()
            raise
        finally:
            self.voice_response = None
            if selector is not None:
                selector.close()
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=self.config['timeouts']['process_stop'])
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if process is not None:
                if not process.stdin.closed:
                    process.stdin.close()
                process.stderr.close()
            self.playback_process = None
            try:
                if epoch != self.microphone_epoch or not self.microphone.enabled:
                    self.resume_audio = None
                if monitor is not None:
                    pcm = monitor.finish()
                    if pcm:
                        self.pending_pcm = (epoch, pcm)
                    if self.resume_audio is not None:
                        self.resume_audio['deadline'] = (self.last_voice_at or time.monotonic()) + self.config['conversation']['interaction']['resume_after_empty_seconds']
            finally:
                self.expressions.hold()
                if self.microphone.enabled and epoch == self.microphone_epoch:
                    self.expressions.set('neutral')

    def run(self):
        greeted = False
        while not self.stopping.is_set():
            if not self.listening.wait(timeout=1):
                if not self.audio_lock.locked():
                    self.phase = 'paused'
                    if self.microphone.enabled:
                        self.expressions.set('neutral')
                    else:
                        self.expressions.hold()
                continue
            try:
                with self.audio_lock:
                    epoch = self.microphone_epoch
                    if not self.listening.is_set():
                        continue
                    health = self.request(self.config['network']['voice_url'], '/health', timeout=self.config['timeouts']['http'])
                    if not health.get('ok'):
                        raise RuntimeError('Voice server is not ready')
                    status = self.request(self.config['network']['hub_url'], '/status', timeout=self.config['timeouts']['http'])
                    if status['ownership']['state'] != 'free':
                        raise RuntimeError('Robot is controlled by another application')
                    if not self.listening.is_set() or epoch != self.microphone_epoch:
                        continue
                    self.last_error = None
                    if not self.playback_configured:
                        self.configure_playback()
                        self.playback_configured = True
                    if not greeted:
                        if self.config['conversation']['wake_on_start']:
                            self.request(self.config['network']['hub_url'], '/actions/wake', {}, timeout=self.config['timeouts']['wake'])
                        if self.config['conversation']['greet_on_start']:
                            self.voice('/say', {'text': self.config['conversation']['greeting']}, expected_epoch=epoch)
                        greeted = True
                    if not self.listening.is_set() or epoch != self.microphone_epoch:
                        continue
                    interrupted_input = False
                    pending, self.pending_pcm = self.pending_pcm, None
                    if pending is not None and pending[0] == epoch:
                        pcm = pending[1]
                        interrupted_input = True
                    else:
                        pcm = self.capture()
                    if not pcm or not self.listening.is_set() or epoch != self.microphone_epoch:
                        continue
                    self.phase = 'processing'
                    LOG.info('phrase captured seconds=%.2f', len(pcm) / 32000)
                    if interrupted_input:
                        recognized = self.request(self.config['network']['voice_url'], '/transcribe',
                                                  {'pcm_base64': base64.b64encode(pcm).decode()})
                        text = recognized['transcript']
                        if not text and self.resume_audio is not None:
                            saved = self.resume_audio
                            if saved.get('cursor_verified') is not True:
                                self.resume_audio=None
                                self.resume_blocked_reason='unverified_pcm_cursor'
                                continue
                            self.phase = 'waiting_to_resume'
                            if time.monotonic() < saved['deadline']:
                                more = self.capture(idle_deadline=saved['deadline'], skip_expression=True)
                                if more:
                                    self.pending_pcm = (epoch, more)
                                    continue
                            if self.sounds.music:
                                self.resume_audio = None
                                continue
                            if self.microphone.enabled and self.listening.is_set() and epoch == self.microphone_epoch:
                                LOG.info('empty_interruption_resume')
                                self.voice('/say', {}, expected_epoch=epoch, replay=saved)
                            continue
                        self.resume_audio = None
                        if not text:
                            continue
                        if recognized['decision']['action'] == 'stop':
                            self.last_transcript = text
                            LOG.info('spoken_stop')
                            self.set_microphone(False)
                            continue
                        response = self.voice('/text', {'text': text, 'session': self.config['conversation']['session'],
                                                       'previous_reply_interrupted': True}, expected_epoch=epoch)
                        response['transcript'] = text
                    else:
                        response = self.voice('/turn', {'pcm_base64': base64.b64encode(pcm).decode(),
                                                       'session': self.config['conversation']['session']}, expected_epoch=epoch)
                    self.last_transcript = response.get('transcript', '')
                    if self.last_transcript:
                        self.turns += 1
                        if self.config['logging']['log_transcripts']:
                            LOG.info('turn transcript=%r reply=%r', self.last_transcript, response.get('reply'))
                    if response.get('command') == 'stop':
                        self.resume_audio = None
                    if response.get('command') in ('pause', 'stop'):
                        self.set_microphone(False)
                    self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                self.phase = 'error'
                LOG.exception('conversation_error')
                self.stopping.wait(self.config['conversation']['retry_seconds'])
        self.phase = 'stopped'

    def manual(self, path, payload):
        was_listening = self.listening.is_set()
        self.listening.clear()
        acquired = self.audio_lock.acquire(timeout=self.config['timeouts']['manual_audio_lock'])
        if not acquired:
            if was_listening and self.microphone.enabled:
                self.listening.set()
            raise RuntimeError('Robot is processing a voice turn; try again when idle')
        try:
            response = self.voice('/text' if path == '/ask' else '/say',
                                    {'text': payload['text'], 'session': self.config['conversation']['session']}, allow_barge_in=was_listening)
            return {k: v for k, v in response.items() if k != 'audio_base64'}
        finally:
            self.phase = 'paused'
            self.audio_lock.release()
            if was_listening and self.microphone.enabled:
                self.listening.set()


def main(config, test_speaker=False):
    logging.basicConfig(level=config['logging']['level'], format='%(asctime)s %(levelname)s %(message)s')
    agent = Agent(config)
    try:
        agent.configure_playback()
        agent.playback_configured = True
    except Exception:
        LOG.exception('initial_playback_configuration_failed')
    if test_speaker:
        response = agent.request(config['network']['voice_url'], '/text',
                                 {'text': 'Поздоровайся и скажи, что разговор через локальную модель работает.',
                                  'session': 'setup-test'})
        agent.play(response['audio_base64'])
        print(json.dumps({k: v for k, v in response.items() if k != 'audio_base64'}, ensure_ascii=False))
        return

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, value):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def auth(self):
            if not hmac.compare_digest(self.headers.get('Authorization', '').encode(),
                                       ('Bearer ' + config.token).encode()):
                self.reply(401, {'error': 'Bearer token required'})
                return False
            return True

        def do_GET(self):
            if not self.auth():
                return
            if self.path != '/status':
                self.reply(404, {'error': 'Not found'})
                return
            self.reply(200, agent.status())

        def do_POST(self):
            if not self.auth():
                return
            if self.path == '/actors/motion/native':
                self.close_connection = True
                self.reply(503, {'accepted': False, 'error': agent.motion_actor_status()['reason']})
                return
            try:
                if self.path == '/pause':
                    agent.listening.clear()
                    value = {'ok': True, 'listening': False}
                elif self.path == '/resume':
                    if not agent.microphone.enabled:
                        raise RuntimeError('Microphone is muted; enable it with the microphone switch')
                    agent.listening.set()
                    value = {'ok': True, 'listening': True}
                elif self.path == '/volume':
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= config['limits']['max_agent_request_bytes']:
                        raise ValueError('Invalid request size')
                    value = agent.set_volume(json.loads(self.rfile.read(size))['volume_percent'])
                elif self.path == '/microphone':
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= config['limits']['max_agent_request_bytes']:
                        raise ValueError('Invalid request size')
                    value = agent.set_microphone(json.loads(self.rfile.read(size))['enabled'])
                elif self.path in ('/ask', '/say'):
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= config['limits']['max_agent_request_bytes']:
                        raise ValueError('Invalid request size')
                    value = agent.manual(self.path, json.loads(self.rfile.read(size)))
                else:
                    self.reply(404, {'error': 'Not found'})
                    return
                self.reply(200, value)
            except Exception as exc:
                LOG.exception('control_failed')
                self.reply(409, {'error': str(exc)})

        def log_message(self, fmt, *args):
            LOG.info('http %s', fmt % args)

    server = ThreadingHTTPServer((config['servers']['agent']['listen'], config['servers']['agent']['port']), Handler)
    server.daemon_threads = True
    threading.Thread(target=agent.run, daemon=True).start()

    def stop(signum, frame):
        agent.listening.clear()
        agent.stopping.set()
        # Exit from the main signal handler; systemd kills any remaining children.
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.serve_forever()
