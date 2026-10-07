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
        from .recognition import Recognizer
        self.stt = Recognizer(config)
        self.tts = PiperVoice.load(config.path(config['models']['tts']['path']),
                                   include_alignments=config['conversation']['expressions'].get('speech_sync', {}).get('phoneme_alignments', False))
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
        return self.stt.transcribe(pcm)

    def classify(self, text):
        from .intents import classify, classify_with_model
        decision = classify(text, self.config['conversation']['interaction'],
                        self.config['conversation']['pause_phrases'], self.config['conversation']['reset_phrases'])
        return classify_with_model(self.config, text, decision)

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

    def answer(self, text, session, interrupted=False):
        now = time.monotonic()
        self.sessions = {k: v for k, v in self.sessions.items() if now - v['used'] < self.config['llm']['history_ttl_seconds']}
        if session not in self.sessions and len(self.sessions) >= self.config['llm']['max_sessions']:
            del self.sessions[min(self.sessions, key=lambda k: self.sessions[k]['used'])]
        self.agent_sessions = {k: v for k, v in self.agent_sessions.items() if k in self.sessions}
        entry = self.sessions.get(session, {'used': now, 'messages': []})
        messages = [{'role': 'system', 'content': self.config['llm']['system_prompt']}]
        messages += entry['messages'][-self.config['llm']['history_messages']:]
        if interrupted:
            messages.append({'role': 'system', 'content': 'Предыдущий ответ был прерван и не прозвучал полностью. Отвечай на новую реплику пользователя, не продолжай старый ответ без просьбы.'})
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

    def prepare(self, payload, path, recognized_text=None, answer_result=None):
        session = payload.get('session', self.config['conversation']['session'])
        if not isinstance(session, str) or not 1 <= len(session) <= self.config['limits']['max_session_chars']:
            raise ValueError('Invalid session')
        self.check_robot()
        if path == '/turn':
            self.phase = 'recognizing'
            text = (recognized_text if recognized_text is not None else
                    self.transcribe(base64.b64decode(payload['pcm_base64'], validate=True)))
        else:
            text = payload['text'].strip()
            if not text or len(text) > self.config['limits']['max_text_chars']:
                raise ValueError('Invalid text length')
        pending = None
        command = None
        decision = self.classify(text)
        if not text:
            reply = ''
        elif path != '/say' and decision['action'] == 'stop':
            reply = ''
            command = 'stop'
        elif path != '/say' and decision['action'] == 'reset':
            self.reset(session)
            reply = self.config['conversation']['reset_reply']
        elif path != '/say' and decision['action'] == 'pause':
            reply = self.config['conversation']['pause_reply']
            command = 'pause'
        elif path == '/say':
            reply = text
        else:
            self.phase = 'thinking'
            reply, pending = (answer_result if answer_result is not None else
                              self.answer(text, session, payload.get('previous_reply_interrupted', False)))
        from .expressions import spoken_expression, spoken_segments
        segments = spoken_segments(reply)
        reply, emotion = spoken_expression(reply)
        if pending is not None and not reply:
            raise RuntimeError('Backend returned an expression without spoken text')
        if pending is not None:
            pending['messages'][-1]['content'] = reply
        return {'transcript': text, 'reply': reply, 'command': command, 'emotion': emotion, 'segments': segments, 'decision': decision}, session, pending

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

    def audio_events(self, segments, initial_bytes=0):
        rate = self.config['streaming']['sample_rate']
        maximum = rate * 2 * self.config['streaming']['max_output_seconds']
        total = initial_bytes
        beat_offset = 0
        from .speech_motion import cues
        for segment in segments:
            text = re.sub(r'[*#`]', '', segment['text']).strip()
            if not text:
                continue
            for chunk in self.tts.synthesize(text, syn_config=self.tts_settings,
                                             include_alignments=self.config['conversation']['expressions'].get('speech_sync', {}).get('phoneme_alignments', False)):
                command = ['sox', '-t', 'raw', '-e', 'signed-integer', '-b', '16',
                           '-L', '-c', str(chunk.sample_channels), '-r', str(chunk.sample_rate), '-',
                           '-t', 'raw', '-e', 'signed-integer', '-b', '16', '-L', '-c', '1', '-r', str(rate), '-']
                if self.config['tts']['pitch_cents']:
                    command += ['pitch', str(self.config['tts']['pitch_cents'])]
                command += speaker_eq_effects(self.config)
                pcm = subprocess.run(command, input=chunk.audio_int16_bytes, capture_output=True,
                                     timeout=self.config['timeouts']['pitch'], check=True).stdout
                if total + len(pcm) > maximum:
                    raise RuntimeError('Streaming answer exceeds duration limit')
                motion = cues(self.config['conversation']['expressions'], chunk, segment,
                              total / (rate * 2), rate, len(pcm), beat_offset)
                motion = motion[:max(0, self.config['conversation']['expressions']['speech_sync']['max_cues'] - beat_offset)]
                if motion:
                    yield {'type': 'motion', 'cues': motion}
                    beat_offset += len(motion)
                size = self.config['streaming']['pcm_chunk_bytes']
                for offset in range(0, len(pcm), size):
                    yield {'type': 'audio', 'format': 'S16_LE', 'sample_rate': rate,
                           'channels': 1, 'pcm_base64': base64.b64encode(pcm[offset:offset+size]).decode()}
                total += len(pcm)

    def stream(self, payload, path):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('Conversation pipeline is busy')
        started = time.monotonic()
        future = executor = None
        try:
            recognized = answer_result = None
            intro_bytes = 0
            acknowledgements = self.config['conversation'].get('interaction', {}).get('acknowledgements', {})
            if path != '/say' and acknowledgements.get('enabled', False):
                self.check_robot()
                recognized = (self.transcribe(base64.b64decode(payload['pcm_base64'], validate=True))
                              if path == '/turn' else payload['text'].strip())
                if not isinstance(recognized, str) or len(recognized) > self.config['limits']['max_text_chars']:
                    raise ValueError('Invalid text length')
                decision = self.classify(recognized)
                if decision['action'] == 'answer':
                    import concurrent.futures
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    session = payload.get('session', self.config['conversation']['session'])
                    if not isinstance(session, str) or not 1 <= len(session) <= self.config['limits']['max_session_chars']:
                        raise ValueError('Invalid session')
                    self.phase = 'thinking'
                    future = executor.submit(self.answer, recognized, session, payload.get('previous_reply_interrupted', False))
                    try:
                        answer_result = future.result(timeout=acknowledgements['delay_seconds'])
                    except concurrent.futures.TimeoutError:
                        intro = acknowledgements['phrases'][decision['intent']]
                        yield {'type': 'reply', 'transcript': recognized, 'reply': intro, 'emotion': decision['emotion'],
                               'command': None, 'acknowledgement': True}
                        for event in self.audio_events([{'text': intro, 'emotion': decision['emotion'], 'gesture': 'auto'}]):
                            if event['type'] == 'audio':
                                intro_bytes += len(base64.b64decode(event['pcm_base64']))
                            yield event
                        answer_result = future.result()
            result, session, pending = (self.prepare(payload, path, recognized, answer_result)
                                        if recognized is not None else self.prepare(payload, path))
            yield {'type': 'reply', **result}
            self.phase = 'speaking'
            segments = result.get('segments') or [{'text': result['reply'], 'emotion': result.get('emotion', 'neutral'), 'gesture': 'auto'}]
            yield from self.audio_events(segments, intro_bytes)
            yield {'type': 'done', 'ok': True, **self.completed(result, session, pending, started)}
        finally:
            if executor is not None:
                executor.shutdown(wait=True)
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
            if self.path == '/transcribe':
                try:
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= config['limits']['max_request_bytes']:
                        raise ValueError('Invalid audio request size')
                    payload = json.loads(self.rfile.read(size))
                    text = pipeline.transcribe(base64.b64decode(payload['pcm_base64'], validate=True))
                    self.reply(200, {'ok': True, 'transcript': text, 'decision': pipeline.classify(text)})
                except (ValueError, KeyError, TypeError) as exc:
                    self.reply(400, {'error': str(exc)})
                except Exception:
                    LOG.exception('transcription_failed')
                    self.reply(503, {'error': 'Transcription failed'})
                return
            if self.path == '/expression/plan':
                try:
                    from .expressions import plan
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= config['limits']['max_agent_request_bytes']:
                        raise ValueError('Invalid expression request size')
                    payload = json.loads(self.rfile.read(size))
                    value = plan(config['conversation'].get('expressions', {}),
                                 payload['phase'], payload.get('emotion', 'neutral'))
                    if payload['phase'] == 'speaking' and config['conversation'].get('barge_in', {}).get('enabled', False):
                        value['steps'] = value['steps'][-1:]
                    self.reply(200, value)
                except (ValueError, KeyError, TypeError) as exc:
                    self.reply(400, {'error': str(exc)})
                return
            if self.path in ('/stream/turn', '/stream/text', '/stream/say'):
                self.stream_reply()
                return
            if worker and self.path in ('/pause', '/resume', '/microphone', '/robot/ask', '/robot/say'):
                self.reply(404, {'error': 'Robot control is available through hub only'})
                return
            if self.path not in ('/turn', '/text', '/say', '/reset', '/pause', '/resume', '/microphone', '/robot/ask', '/robot/say'):
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
                elif self.path in ('/pause', '/resume', '/microphone'):
                    value = pipeline.request(pipeline.config['network']['agent_url'] + self.path, payload if self.path == '/microphone' else {}, True)
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
