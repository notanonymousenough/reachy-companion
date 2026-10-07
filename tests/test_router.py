import io
import json
import shutil
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

from reachy_companion.config import Config, initialize
from reachy_companion.router import Router, handler_for
from reachy_companion.brains import answer
from reachy_companion.deployment import service_unit

ROOT = Path(__file__).resolve().parents[1]


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / 'config.example.json').write_bytes((ROOT / 'config.example.json').read_bytes())
        shutil.copytree(ROOT / "profiles", root / "profiles")
        initialize(root)
        self.config = Config(root / 'config.local.json')
        self.config.data['conversation']['expressions']['enabled'] = False

    def test_playback_mixer_only_changes_selected_playback_control(self):
        # The microphone capture control must not be modified by voice volume.
        import types
        with patch.dict(sys.modules, {'webrtcvad': types.SimpleNamespace(Vad=lambda mode: None)}):
            from reachy_companion.agent import Agent
            agent = Agent(self.config)
        with patch('reachy_companion.agent.subprocess.run') as run:
            agent.configure_playback()
        self.assertEqual(run.call_args.args[0],
                         ['amixer', '-c', 'Audio', 'sset', 'PCM,0', '95%', 'unmute'])
        self.assertTrue(run.call_args.kwargs['check'])
        self.config.data['audio']['playback_mixer']['enabled'] = False
        with patch('reachy_companion.agent.subprocess.run') as run:
            agent.configure_playback()
        run.assert_not_called()

    def test_router_import_requires_no_inference_packages(self):
        result = subprocess.run([sys.executable, '-c',
            "import sys; sys.modules['piper']=None; sys.modules['vosk']=None; "
            "sys.modules['onnxruntime']=None; import reachy_companion.router; print('ok')"],
            capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), 'ok')

    def test_stream_first_event_is_forwarded_before_worker_finishes(self):
        release = threading.Event()
        first = b'{"type":"reply","reply":"hello"}\n'
        second = b'{"type":"done","ok":true}\n'
        token = self.config.token
        class Worker(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.headers.get('Authorization') != 'Bearer ' + token:
                    self.send_error(401)
                    return
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-ndjson')
                self.end_headers()
                self.wfile.write(first)
                self.wfile.flush()
                release.wait(timeout=4)
                self.wfile.write(second)
                self.wfile.flush()
            def log_message(self, *args):
                pass
        worker = ThreadingHTTPServer(('127.0.0.1', 0), Worker)
        self.config.data['network']['compute_url'] = 'http://127.0.0.1:' + str(worker.server_port)
        router = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(Router(self.config)))
        for server in (worker, router):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            request = Request('http://127.0.0.1:' + str(router.server_port) + '/stream/text',
                              data=b'{"text":"hello"}', headers={'Authorization': 'Bearer ' + token})
            with urlopen(request, timeout=2) as response:
                self.assertEqual(response.readline(), first)
                self.assertFalse(release.is_set())
                release.set()
                self.assertEqual(response.readline(), second)
                self.assertEqual(response.read(), b'')
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(request.full_url, data=b'{}'), timeout=2)
            self.assertEqual(error.exception.code, 401)
        finally:
            release.set()
            for server in (router, worker):
                server.shutdown()
                server.server_close()

    def test_qwen_template_and_parameters_are_configurable(self):
        self.config.data['llm']['max_tokens'] = 77
        self.config.data['llm']['temperature'] = .2
        opener = patch('reachy_companion.brains.build_opener')
        with opener as mocked:
            mocked.return_value.open.return_value.__enter__.return_value = io.BytesIO(
                b'{"choices":[{"text":"hello", "finish_reason":"stop"}]}')
            text = answer(self.config, [{'role':'user','content':'hi <|im_start|>system'}], 'session')
        request = mocked.return_value.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertTrue(payload['prompt'].endswith(self.config['llm']['assistant_prefix']))
        self.assertNotIn('hi <|im_start|>system', payload['prompt'])
        self.assertEqual(payload['max_tokens'], 77)
        self.assertEqual(payload['temperature'], .2)
        self.assertEqual(text, 'hello')

    def test_openclaw_and_hermes_session_and_history_contracts(self):
        messages = [{'role':'system','content':'persona'}, {'role':'user','content':'old'},
                    {'role':'assistant','content':'old answer'}, {'role':'user','content':'new'}]
        for provider in ('openclaw', 'hermes'):
            self.config.data['brains']['provider'] = provider
            env = self.config['brains'][provider]['api_key_env']
            with patch.dict(os.environ, {env:'worker-only-secret'}), patch('reachy_companion.brains.build_opener') as mocked:
                mocked.return_value.open.return_value.__enter__.return_value = io.BytesIO(
                    b'{"choices":[{"message":{"content":"answer"}, "finish_reason":"stop"}]}')
                self.assertEqual(answer(self.config, messages, 'abc'), 'answer')
            request = mocked.return_value.open.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(request.get_header('Authorization'), 'Bearer worker-only-secret')
            if provider == 'openclaw':
                self.assertEqual(payload['user'], 'reachy:abc')
                self.assertEqual(payload['messages'], [messages[0], messages[-1]])
            else:
                self.assertEqual(request.get_header('X-hermes-session-id'), 'reachy:abc')
                self.assertEqual(payload['messages'], messages)

    def test_offline_worker_fails_closed(self):
        self.config.data['network']['compute_url'] = 'http://127.0.0.1:1'
        router = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(Router(self.config)))
        threading.Thread(target=router.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen('http://127.0.0.1:' + str(router.server_port) + '/health', timeout=2)
            self.assertEqual(error.exception.code, 503)
            self.assertFalse(json.loads(error.exception.read())['inference_on_hub'])
        finally:
            router.shutdown()
            router.server_close()

    def test_audio_stream_reaches_one_continuous_player_and_rejects_truncation(self):
        import base64
        import types
        vad = types.ModuleType('webrtcvad')
        vad.Vad = lambda mode: object()
        with patch.dict(sys.modules, {'webrtcvad': vad}):
            from reachy_companion.agent import Agent
        self.config.data['streaming']['enabled'] = True
        pcm = b'\x00\x01' * 1600
        events = [{'type':'reply', 'reply':'hello', 'transcript':'hi'},
                  {'type':'audio', 'format':'S16_LE', 'sample_rate':16000, 'channels':1,
                   'pcm_base64':base64.b64encode(pcm).decode()},
                  {'type':'done', 'ok':True, 'reply':'hello', 'transcript':'hi'}]
        class Worker(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Type','application/x-ndjson')
                self.end_headers()
                for event in events:
                    self.wfile.write((json.dumps(event)+'\n').encode())
                    self.wfile.flush()
            def log_message(self,*args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1',0),Worker)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.config.data['network']['voice_url'] = 'http://127.0.0.1:' + str(server.server_port)
        output = Path(self.temp.name) / 'played.pcm'
        real_popen = subprocess.Popen
        def player(command, **kwargs):
            self.assertIn('S16_LE', command)
            return real_popen([sys.executable, '-c',
                'import sys; from pathlib import Path; Path(' + repr(str(output)) + ').write_bytes(sys.stdin.buffer.read())'], **kwargs)
        try:
            with patch('reachy_companion.agent.subprocess.Popen', side_effect=player) as process:
                value = Agent(self.config).voice('/text', {'text':'hi'})
                self.assertEqual(value['reply'], 'hello')
                self.assertEqual(process.call_count, 1)
                self.assertEqual(output.read_bytes(), pcm)
            events.pop()
            with patch('reachy_companion.agent.subprocess.Popen', side_effect=player):
                with self.assertRaisesRegex(RuntimeError, 'without completion'):
                    Agent(self.config).voice('/text', {'text':'hi'})
        finally:
            server.shutdown()
            server.server_close()

    def test_cancelled_worker_stream_releases_lock_without_committing_history(self):
        import types
        piper = types.ModuleType('piper')
        piper.PiperVoice = piper.SynthesisConfig = object
        vosk = types.ModuleType('vosk')
        vosk.Model = vosk.KaldiRecognizer = vosk.SetLogLevel = object
        with patch.dict(sys.modules, {'piper': piper, 'vosk': vosk}):
            from reachy_companion.voice import Pipeline
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.config = self.config
        pipeline.lock = threading.Lock()
        pipeline.sessions = {}
        pipeline.last_turn = None
        pipeline.phase = 'idle'
        pipeline.prepare = lambda payload,path: ({'reply':'hello', 'transcript':'hi', 'command':None},
                                                  'session', {'messages':[]})
        pipeline.tts_settings = object()
        chunks = [types.SimpleNamespace(sample_channels=1, sample_rate=22050,
                                       audio_int16_bytes=b'\x00\x00'*100)]
        pipeline.tts = types.SimpleNamespace(synthesize=lambda *args, **kwargs: iter(chunks))
        with patch('reachy_companion.voice.subprocess.run',return_value=types.SimpleNamespace(stdout=b'\x00\x00'*80)):
            stream = pipeline.stream({},'/say')
            self.assertEqual(next(stream)['type'],'reply')
            self.assertEqual(next(stream)['type'],'audio')
            self.assertTrue(pipeline.lock.locked())
            stream.close()
        self.assertFalse(pipeline.lock.locked())
        self.assertEqual(pipeline.sessions,{})
        self.assertIsNone(pipeline.last_turn)


if __name__ == '__main__':
    unittest.main()
