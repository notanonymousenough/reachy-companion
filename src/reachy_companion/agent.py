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
        self.microphone_epoch = 0
        self.microphone_lock = threading.Lock()
        self.playback_process = None
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
        self.vad = webrtcvad.Vad(self.audio['vad_mode'])
        from .expression_player import ExpressionPlayer
        self.expressions = ExpressionPlayer(config, self.request, self.stopping)
        self.chunk_bytes = self.audio['sample_rate'] * 2 * self.audio['chunk_ms'] // 1000
        self.vad_bytes = self.audio['sample_rate'] * 2 * self.audio['vad_frame_ms'] // 1000

    def set_microphone(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be boolean')
        with self.microphone_lock:
            self.microphone_epoch += 1
            self.listening.clear()
            if not enabled:
                self.expressions.set('neutral')
                process = self.playback_process
                if process is not None and process.poll() is None:
                    process.terminate()
            self.microphone.save(enabled)
            if enabled:
                self.listening.set()
        return {'ok': True, 'microphone_enabled': enabled, 'capture_active': self.capture_active}

    def configure_playback(self):
        settings = self.audio.get('playback_mixer', {})
        if not settings.get('enabled', False):
            return
        subprocess.run(['amixer', '-c', str(settings['card']), 'sset',
                        settings['control'], str(settings['volume_percent']) + '%'],
                       capture_output=True, check=True, timeout=self.config['timeouts']['http'])
        LOG.info('playback_mixer card=%s control=%s volume=%s%%', settings['card'],
                 settings['control'], settings['volume_percent'])

    def request(self, base, path, payload=None, timeout=None):
        request = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json',
                                   'Authorization': 'Bearer ' + self.config.token})
        try:
            with self.http.open(request, timeout=timeout or self.config['timeouts']['client']) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError('Hub HTTP %s: %s' % (exc.code, exc.read().decode()[:600])) from exc

    def capture(self):
        epoch = self.microphone_epoch
        self.expressions.set('listening', wait=True)
        if not self.listening.is_set() or epoch != self.microphone_epoch:
            return None
        self.phase = 'listening'
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
                while self.listening.is_set() and not self.stopping.is_set() and epoch == self.microphone_epoch:
                    if not selector.select(timeout=1):
                        if process.poll() is not None:
                            raise RuntimeError(process.stderr.read().decode()[:500])
                        continue
                    chunk = process.stdout.read(self.chunk_bytes)
                    if len(chunk) != self.chunk_bytes:
                        raise RuntimeError('Microphone stream ended: ' + process.stderr.read().decode()[:500])
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
                    loud = rms >= self.threshold and speech_frames >= self.audio['min_speech_frames']
                    if not frames:
                        pre.append(chunk)
                        if loud:
                            frames = list(pre)
                            voiced = 1
                            self.phase = 'recording'
                        continue
                    frames.append(chunk)
                    if loud:
                        voiced += 1
                        silent = 0
                    else:
                        silent += 1
                    if silent >= self.audio['silence_chunks'] or len(frames) >= self.audio['max_recording_seconds'] * 1000 / self.audio['chunk_ms']:
                        if voiced >= self.audio['min_voiced_chunks']:
                            return b''.join(frames) if epoch == self.microphone_epoch and self.listening.is_set() else None
                        frames = []
                        voiced = silent = 0
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
        if not encoded:
            return
        self.phase = 'speaking'
        wav = base64.b64decode(encoded, validate=True)
        with wave.open(io.BytesIO(wav), 'rb') as stream:
            seconds = stream.getnframes() / stream.getframerate()
        with subprocess.Popen(['aplay', '-q', '-D', self.audio['playback_device']],
                              stdin=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            self.playback_process = process
            try:
                if epoch is not None and epoch != self.microphone_epoch:
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

    def voice(self, path, payload, expected_epoch=None):
        epoch = self.microphone_epoch if expected_epoch is None else expected_epoch
        def cancelled():
            return epoch != self.microphone_epoch or self.stopping.is_set()
        if cancelled():
            return {'ok': True, 'cancelled': True}
        if path in ('/text', '/turn'):
            self.expressions.set('processing')
        if not self.config['streaming']['enabled']:
            response = self.request(self.config['network']['voice_url'], path, payload)
            if cancelled():
                return {'ok': True, 'cancelled': True}
            self.expressions.set('speaking', response.get('emotion', 'neutral'))
            try:
                self.play(response.get('audio_base64', ''), epoch)
            finally:
                self.expressions.set('neutral')
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
        try:
            with self.http.open(item, timeout=self.config['timeouts']['client']) as response:
                if response.headers.get_content_type() != 'application/x-ndjson':
                    raise RuntimeError('Expected an audio event stream')
                while True:
                    if cancelled():
                        return {'ok': True, 'cancelled': True}
                    line = response.readline(settings['max_event_bytes'] + 1)
                    if not line:
                        break
                    if len(line) > settings['max_event_bytes'] or not line.endswith(b'\n'):
                        raise ValueError('Invalid stream event size')
                    event = json.loads(line)
                    if event['type'] == 'reply':
                        result = event
                    elif event['type'] == 'audio':
                        if cancelled():
                            return {'ok': True, 'cancelled': True}
                        if event.get('sample_rate') != settings['sample_rate'] or event.get('format') != 'S16_LE' or event.get('channels') != 1:
                            raise ValueError('Unsupported stream audio format')
                        pcm = base64.b64decode(event['pcm_base64'], validate=True)
                        total += len(pcm)
                        if len(pcm) % 2 or total > maximum:
                            raise ValueError('Invalid stream audio length')
                        if process is None:
                            self.phase = 'speaking'
                            self.expressions.set('speaking', (result or {}).get('emotion', 'neutral'))
                            process = subprocess.Popen(['aplay', '-q', '-D', self.audio['playback_device'],
                                '-t', 'raw', '-f', 'S16_LE', '-r', str(settings['sample_rate']), '-c', '1'],
                                stdin=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                            self.playback_process = process
                            if cancelled():
                                return {'ok': True, 'cancelled': True}
                            os.set_blocking(process.stdin.fileno(), False)
                            selector = selectors.DefaultSelector()
                            selector.register(process.stdin, selectors.EVENT_WRITE)
                            deadline = time.monotonic() + settings['max_output_seconds'] + self.config['timeouts']['playback_margin']
                        remaining = memoryview(pcm)
                        while remaining:
                            if cancelled():
                                return {'ok': True, 'cancelled': True}
                            if time.monotonic() > deadline:
                                raise TimeoutError('Streaming playback stopped or timed out')
                            if process.poll() is not None:
                                raise RuntimeError('Streaming playback failed')
                            if selector.select(timeout=0.2):
                                try:
                                    written = os.write(process.stdin.fileno(), remaining)
                                    remaining = remaining[written:]
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
                    return {'ok': True, 'cancelled': True}
                if process.returncode:
                    raise RuntimeError('Streaming playback failed')
                time.sleep(self.audio['echo_tail_seconds'])
            return {key: value for key, value in result.items() if key != 'type'}
        except Exception:
            if cancelled():
                return {'ok': True, 'cancelled': True}
            raise
        finally:
            self.playback_process = None
            self.expressions.set('neutral')
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

    def run(self):
        greeted = False
        while not self.stopping.is_set():
            if not self.listening.wait(timeout=1):
                if not self.audio_lock.locked():
                    self.phase = 'paused'
                    self.expressions.set('neutral')
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
                    pcm = self.capture()
                    if not pcm or not self.listening.is_set() or epoch != self.microphone_epoch:
                        continue
                    self.phase = 'processing'
                    LOG.info('phrase captured seconds=%.2f', len(pcm) / 32000)
                    response = self.voice('/turn',
                                            {'pcm_base64': base64.b64encode(pcm).decode(),
                                             'session': self.config['conversation']['session']}, expected_epoch=epoch)
                    self.last_transcript = response.get('transcript', '')
                    if self.last_transcript:
                        self.turns += 1
                        if self.config['logging']['log_transcripts']:
                            LOG.info('turn transcript=%r reply=%r', self.last_transcript, response.get('reply'))
                    if response.get('command') == 'pause':
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
                                    {'text': payload['text'], 'session': self.config['conversation']['session']})
            return {k: v for k, v in response.items() if k != 'audio_base64'}
        finally:
            self.phase = 'paused'
            self.audio_lock.release()
            if was_listening and self.microphone.enabled:
                self.listening.set()


def main(config, test_speaker=False):
    logging.basicConfig(level=config['logging']['level'], format='%(asctime)s %(levelname)s %(message)s')
    agent = Agent(config)
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
            self.reply(200, {'listening': agent.listening.is_set(), 'phase': agent.phase,
                             'threshold_rms': agent.threshold, 'last_error': agent.last_error,
                             'last_transcript': agent.last_transcript, 'turns': agent.turns,
                             'microphone_enabled': agent.microphone.enabled,
                             'capture_active': agent.capture_active,
                             'microphone_state_error': agent.microphone.error,
                             'expression': agent.expressions.last_expression,
                             'expression_error': agent.expressions.last_error})

        def do_POST(self):
            if not self.auth():
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
