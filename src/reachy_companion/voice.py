#!/usr/bin/env python3
"""LAN-only Russian voice pipeline: Vosk -> LM Studio -> Piper."""
import base64
import hmac
import io
import json
import logging
import re
import subprocess
import threading
import time
import wave
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

from piper import PiperVoice, SynthesisConfig
from vosk import Model, KaldiRecognizer, SetLogLevel

LOG = logging.getLogger('reachy-voice')


def speaker_eq_effects(config):
    """Output-only speaker correction; native WAV and microphone are unchanged."""
    eq = config['tts'].get('playback_eq', {})
    if not eq.get('enabled', False):
        return []
    return ['highpass', str(eq['highpass_hz']),
            'equalizer', str(eq['bass_hz']), str(eq['bass_width_q']) + 'q', str(eq['bass_db']),
            'equalizer', str(eq['presence_hz']), str(eq['presence_width_q']) + 'q', str(eq['presence_db']),
            'treble', str(eq['treble_db']), 'gain', '-n', str(-eq['headroom_db'])]


class Pipeline:
    def __init__(self, config):
        self.config = config
        self.http = build_opener(ProxyHandler({}))
        self.lock = threading.Lock()
        self.sessions = {}
        self.agent_sessions = {}
        self.phase = 'loading'
        self.last_turn = None
        SetLogLevel(-1)
        self.stt = Model(str(config.path(config['models']['stt']['path'])))
        self.tts = PiperVoice.load(config.path(config['models']['tts']['path']))
        self.tts_settings = SynthesisConfig(**config['tts']['synthesis'])
        self.phase = 'idle'
        LOG.info('models_ready')

    def token_ok(self, header):
        return hmac.compare_digest(header.encode(),
                                   ('Bearer ' + self.config.token).encode())

    def request(self, url, payload=None, authenticated=False, timeout=None):
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + self.config.token
        request = Request(url, data=None if payload is None else json.dumps(payload).encode(),
                          headers=headers)
        with self.http.open(request, timeout=timeout or self.config['timeouts']['http']) as response:
            return json.load(response)

    def check_robot(self):
        owner = self.request(self.config['network']['hub_url'] + '/status', authenticated=True)['ownership']
        if owner['state'] != 'free':
            raise RuntimeError('Robot is controlled by another application')

    def transcribe(self, pcm):
        if not pcm or len(pcm) % 2 or len(pcm) > self.config['audio']['max_input_seconds'] * self.config['audio']['sample_rate'] * 2:
            raise ValueError('Expected up to 30 seconds of mono 16 kHz signed 16-bit PCM')
        recognizer = KaldiRecognizer(self.stt, 16000)
        parts = []
        for offset in range(0, len(pcm), 8000):
            if recognizer.AcceptWaveform(pcm[offset:offset+8000]):
                parts.append(json.loads(recognizer.Result()).get('text', ''))
        parts.append(json.loads(recognizer.FinalResult()).get('text', ''))
        return ' '.join(p for p in parts if p).strip()

    def synthesize(self, text):
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.S)
        text = re.sub(r'[*#`]', '', text).strip()
        if not text or len(text) > self.config['limits']['max_speech_chars']:
            raise ValueError('Expected 1–5000 characters for speech')
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            self.tts.synthesize_wav(text, wav, syn_config=self.tts_settings)
        audio = buffer.getvalue()
        pitch = self.config['tts']['pitch_cents']
        if pitch:
            result = subprocess.run(['sox', '-t', 'wav', '-', '-t', 'wav', '-',
                                     'pitch', str(pitch)], input=audio,
                                    capture_output=True, timeout=self.config['timeouts']['pitch'], check=True)
            # Rebuild the WAV header: SoX's non-seekable stdout uses an unknown
            # frame count, while the robot needs an accurate playback duration.
            with wave.open(io.BytesIO(result.stdout), 'rb') as source:
                frames = source.readframes(source.getnframes())
                fixed = io.BytesIO()
                with wave.open(fixed, 'wb') as target:
                    target.setnchannels(source.getnchannels())
                    target.setsampwidth(source.getsampwidth())
                    target.setframerate(source.getframerate())
                    target.writeframes(frames)
            audio = fixed.getvalue()
        return base64.b64encode(audio).decode()

    def answer(self, text, session):
        now = time.monotonic()
        self.sessions = {k: v for k, v in self.sessions.items() if now - v['used'] < self.config['llm']['history_ttl_seconds']}
        if session not in self.sessions and len(self.sessions) >= self.config['llm']['max_sessions']:
            del self.sessions[min(self.sessions, key=lambda k: self.sessions[k]['used'])]
        self.agent_sessions = {k: v for k, v in self.agent_sessions.items() if k in self.sessions}
        entry = self.sessions.get(session, {'used': now, 'messages': []})
        messages = [{'role': 'system', 'content': self.config['llm']['system_prompt']}]
        messages += entry['messages'][-self.config['llm']['history_messages']:]
        messages.append({'role': 'user', 'content': text})
        from .brains import answer
        agent_session = self.agent_sessions.setdefault(session, uuid.uuid4().hex)
        reply = answer(self.config, messages, agent_session)
        pending = entry['messages'] + [{'role': 'user', 'content': text},
                                       {'role': 'assistant', 'content': reply}]
        return reply, {'used': now, 'messages': pending[-self.config['llm']['history_messages']:]}

    def reset(self, session):
        self.sessions.pop(session, None)
        self.agent_sessions.pop(session, None)

    def prepare(self, payload, path):
        session = payload.get('session', self.config['conversation']['session'])
        if not isinstance(session, str) or not 1 <= len(session) <= self.config['limits']['max_session_chars']:
            raise ValueError('Invalid session')
        self.check_robot()
        if path == '/turn':
            self.phase = 'recognizing'
            text = self.transcribe(base64.b64decode(payload['pcm_base64'], validate=True))
        else:
            text = payload['text'].strip()
            if not text or len(text) > self.config['limits']['max_text_chars']:
                raise ValueError('Invalid text length')
        pending = None
        command = None
        normalized = text.lower().strip(' .!?')
        if not text:
            reply = ''
        elif path != '/say' and normalized in self.config['conversation']['reset_phrases']:
            self.reset(session)
            reply = self.config['conversation']['reset_reply']
        elif path != '/say' and normalized in self.config['conversation']['pause_phrases']:
            reply = self.config['conversation']['pause_reply']
            command = 'pause'
        elif path == '/say':
            reply = text
        else:
            self.phase = 'thinking'
            reply, pending = self.answer(text, session)
        return {'transcript': text, 'reply': reply, 'command': command}, session, pending

    def completed(self, result, session, pending, started):
        if pending is not None:
            self.sessions[session] = pending
        result['elapsed_seconds'] = round(time.monotonic() - started, 2)
        self.last_turn = dict(result)
        if self.config['logging']['log_transcripts']:
            LOG.info('turn session=%s transcript=%r reply=%r seconds=%s', session,
                     result['transcript'], result['reply'], result['elapsed_seconds'])
        return result

    def turn(self, payload, path):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('Conversation pipeline is busy')
        started = time.monotonic()
        try:
            result, session, pending = self.prepare(payload, path)
            self.phase = 'speaking'
            audio = self.synthesize(result['reply']) if result['reply'] else ''
            return {'ok': True, **self.completed(result, session, pending, started), 'audio_base64': audio}
        finally:
            self.phase = 'idle'
            self.lock.release()

    def stream(self, payload, path):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('Conversation pipeline is busy')
        started = time.monotonic()
        try:
            result, session, pending = self.prepare(payload, path)
            yield {'type': 'reply', **result}
            self.phase = 'speaking'
            rate = self.config['streaming']['sample_rate']
            maximum = rate * 2 * self.config['streaming']['max_output_seconds']
            total = 0
            text = re.sub(r'[*#`]', '', result['reply']).strip()
            for chunk in self.tts.synthesize(text, syn_config=self.tts_settings):
                # Convert each Piper sentence on the COMPUTE worker, preserving
                # the configured voice. Hub forwards bytes without decoding/resampling.
                command = ['sox', '-t', 'raw', '-e', 'signed-integer', '-b', '16',
                           '-L', '-c', str(chunk.sample_channels), '-r', str(chunk.sample_rate), '-',
                           '-t', 'raw', '-e', 'signed-integer', '-b', '16', '-L',
                           '-c', '1', '-r', str(rate), '-']
                if self.config['tts']['pitch_cents']:
                    command += ['pitch', str(self.config['tts']['pitch_cents'])]
                command += speaker_eq_effects(self.config)
                pcm = subprocess.run(command, input=chunk.audio_int16_bytes, capture_output=True,
                                     timeout=self.config['timeouts']['pitch'], check=True).stdout
                total += len(pcm)
                if total > maximum:
                    raise RuntimeError('Streaming answer exceeds duration limit')
                size = self.config['streaming']['pcm_chunk_bytes']
                for offset in range(0, len(pcm), size):
                    yield {'type': 'audio', 'format': 'S16_LE', 'sample_rate': rate,
                           'channels': 1, 'pcm_base64': base64.b64encode(pcm[offset:offset+size]).decode()}
            yield {'type': 'done', 'ok': True, **self.completed(result, session, pending, started)}
        finally:
            self.phase = 'idle'
            self.lock.release()


def main(config, worker=False):
    from .logging_utils import configure
    configure(config, 'compute' if worker else 'voice')
    pipeline = Pipeline(config)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(config['timeouts']['client'])

        def reply(self, code, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            if not pipeline.token_ok(self.headers.get('Authorization', '')):
                self.reply(401, {'error': 'Bearer token required'})
                return False
            return True

        def do_GET(self):
            if self.path == '/health':
                self.reply(200, {'ok': True, 'phase': pipeline.phase, 'service': 'compute-worker' if worker else 'local-voice'})
            elif self.path == '/status' and self.authorized():
                try:
                    robot = {'via': 'hub'} if worker else pipeline.request(pipeline.config['network']['agent_url'] + '/status', authenticated=True)
                except Exception as exc:
                    robot = {'error': str(exc)}
                self.reply(200, {'ok': True, 'phase': pipeline.phase,
                                 'last_turn': pipeline.last_turn, 'agent': robot,
                                 'provider': config['brains']['provider'], 'streaming': config['streaming']['enabled']})
            elif self.path != '/status':
                self.reply(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.authorized():
                return
            if self.path in ('/stream/turn', '/stream/text', '/stream/say'):
                self.stream_reply()
                return
            if worker and self.path in ('/pause', '/resume', '/robot/ask', '/robot/say'):
                self.reply(404, {'error': 'Robot control is available through hub only'})
                return
            if self.path not in ('/turn', '/text', '/say', '/reset', '/pause', '/resume', '/robot/ask', '/robot/say'):
                self.reply(404, {'error': 'Not found'})
                return
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= pipeline.config['limits']['max_request_bytes']:
                    self.reply(413, {'error': 'Invalid request size'})
                    return
                payload = json.loads(self.rfile.read(size))
                if self.path in ('/robot/ask', '/robot/say'):
                    value = pipeline.request(pipeline.config['network']['agent_url'] + self.path.removeprefix('/robot'), payload, True, timeout=config['timeouts']['client'])
                elif self.path in ('/pause', '/resume'):
                    value = pipeline.request(pipeline.config['network']['agent_url'] + self.path, {}, True)
                elif self.path == '/reset':
                    if not pipeline.lock.acquire(blocking=False):
                        raise RuntimeError('Conversation pipeline is busy')
                    try:
                        pipeline.reset(payload.get('session', config['conversation']['session']))
                    finally:
                        pipeline.lock.release()
                    value = {'ok': True}
                else:
                    value = pipeline.turn(payload, self.path)
                self.reply(200, value)
            except HTTPError as exc:
                LOG.exception('upstream_http_error code=%s', exc.code)
                self.reply(502, {'ok': False, 'error': 'Upstream HTTP %s' % exc.code})
            except (ValueError, KeyError, TypeError) as exc:
                self.reply(400, {'ok': False, 'error': str(exc)})
            except Exception as exc:
                LOG.exception('request_failed path=%s', self.path)
                self.reply(503, {'ok': False, 'error': str(exc)})

        def stream_reply(self):
            sent = False
            iterator = None
            try:
                if not config['streaming']['enabled']:
                    self.reply(404, {'error': 'Streaming is disabled'})
                    return
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= config['limits']['max_request_bytes']:
                    raise ValueError('Invalid request size')
                payload = json.loads(self.rfile.read(size))
                iterator = pipeline.stream(payload, self.path.removeprefix('/stream'))
                first = next(iterator)
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-ndjson')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                sent = True
                def event(value):
                    self.wfile.write((json.dumps(value, ensure_ascii=False) + '\n').encode())
                    self.wfile.flush()
                event(first)
                for value in iterator:
                    event(value)
            except (BrokenPipeError, ConnectionResetError):
                LOG.info('stream_client_disconnected')
            except Exception:
                LOG.exception('stream_failed')
                if sent:
                    try:
                        event({'type': 'error', 'error': 'Worker stream failed'})
                    except OSError:
                        pass
                else:
                    self.reply(503, {'error': 'Worker stream failed'})
            finally:
                if iterator is not None:
                    iterator.close()

        def log_message(self, fmt, *args):
            LOG.info('http client=%s %s', self.client_address[0], fmt % args)

    address = config['servers']['worker' if worker else 'voice']
    server = ThreadingHTTPServer((address['listen'], address['port']), Handler)
    server.daemon_threads = True
    LOG.info('listening %s:%s', *server.server_address)
    server.serve_forever()
