"""A remote HTTP operation surviving local timeout must not admit an overlap."""
import copy
import io
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch
from reachy_companion import brains


def configuration():
    return json.loads((Path(__file__).resolve().parents[1]/'config.example.json').read_text())


def body(cfg,text='OK',finish='stop'):
    return json.dumps(dict(model=cfg['llm']['model'],choices=[dict(index=0,text=text,finish_reason=finish)])).encode()


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        guard=patch.object(brains,'MODEL_EXECUTION',brains.ModelExecutionOwnership())
        guard.start();self.addCleanup(guard.stop)

    def serve(self,hold_first=True):
        state=dict(calls=[],entered=threading.Event(),release=threading.Event(),lock=threading.Lock())
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                with state['lock']:
                    state['calls'].append(request['model']);first=len(state['calls'])==1
                if first and hold_first:state['entered'].set();state['release'].wait(3)
                content=json.dumps(dict(model=request['model'],choices=[dict(index=0,text='OK',finish_reason='stop')])).encode()
                try:
                    self.send_response(200);self.send_header('Content-Length',str(len(content)))
                    self.end_headers();self.wfile.write(content)
                except OSError:pass
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def cleanup():state['release'].set();server.shutdown();server.server_close();thread.join(1)
        self.addCleanup(cleanup)
        cfg=configuration();cfg['network']['llm_base_url']='http://127.0.0.1:'+str(server.server_port)+'/v1'
        return cfg,state

    def pipeline(self,cfg):
        piper=types.ModuleType('piper');piper.PiperVoice=piper.SynthesisConfig=object
        vosk=types.ModuleType('vosk');vosk.Model=vosk.KaldiRecognizer=vosk.SetLogLevel=object
        with patch.dict(sys.modules,{'piper':piper,'vosk':vosk}):
            from reachy_companion.voice import Pipeline
        p=Pipeline.__new__(Pipeline);p.config=cfg;p.sessions={};p.agent_sessions={}
        p.lock=threading.Lock();p.phase='idle';p.last_turn=None
        p.check_robot=lambda:None;p.classify=lambda _:dict(action='answer');p.synthesize=lambda _:'audio'
        return p

    def test_pinned_old_source_reproduces_real_pipeline_remote_overlap(self):
        import subprocess
        baseline='87d239db96fc95f345a16b5fa9fd5c93d4c2dc3d'
        source=subprocess.check_output(['git','show',baseline+':src/reachy_companion/brains.py'],cwd=Path(__file__).resolve().parents[1])
        old=types.ModuleType('pinned_old_http_brains');old.__package__='reachy_companion'
        exec(compile(source,'pinned_old_brains.py','exec'),old.__dict__)
        cfg,state=self.serve();cfg['timeouts']['llm']=.05;p=self.pipeline(cfg)
        with patch.object(brains,'answer',old.answer):
            with self.assertRaises(TimeoutError):p.turn(dict(text='first fixture',session='fixture'),'/text')
            self.assertTrue(state['entered'].is_set());self.assertFalse(p.lock.locked())
            self.assertFalse(state['release'].is_set())
            self.assertTrue(p.turn(dict(text='second fixture',session='fixture'),'/text')['ok'])
        self.assertEqual(state['calls'],[cfg['llm']['model'],cfg['llm']['model']])

    def test_real_pipeline_timeout_blocks_second_post_while_remote_still_held(self):
        cfg,state=self.serve();cfg['timeouts']['llm']=.05;p=self.pipeline(cfg)
        with self.assertRaises(TimeoutError):p.turn(dict(text='first fixture',session='fixture'),'/text')
        self.assertTrue(state['entered'].is_set());self.assertFalse(p.lock.locked())
        with self.assertRaises(RuntimeError):p.turn(dict(text='second fixture',session='fixture'),'/text')
        self.assertEqual(state['calls'],[cfg['llm']['model']])
        self.assertEqual(p.sessions,{});self.assertIsNone(p.last_turn)
        self.assertEqual(brains.MODEL_EXECUTION.status(brains.model_identity(cfg)),dict(active=False,unknown=True))
        # Server-side release is not a terminal response received by this client.
        state['release'].set()
        with self.assertRaises(RuntimeError):brains.answer(cfg,[],'fixture')
        self.assertEqual(len(state['calls']),1)

    def test_direct_concurrent_call_denied_then_known_terminal_allows_next(self):
        cfg,state=self.serve();cfg['timeouts']['llm']=2;results=[]
        def run():results.append(brains.answer(cfg,[],'first'))
        worker=threading.Thread(target=run);worker.start();self.addCleanup(lambda:worker.join(3))
        self.assertTrue(state['entered'].wait(1))
        self.assertEqual(brains.MODEL_EXECUTION.status(brains.model_identity(cfg)),dict(active=True,unknown=False))
        with self.assertRaises(RuntimeError):brains.answer(cfg,[],'second')
        self.assertEqual(len(state['calls']),1)
        state['release'].set();worker.join(2);self.assertFalse(worker.is_alive());self.assertEqual(results,['OK'])
        self.assertEqual(brains.answer(cfg,[],'fresh'),'OK');self.assertEqual(len(state['calls']),2)

    def test_unknown_backend_does_not_block_other_configured_model(self):
        cfg,state=self.serve();cfg['timeouts']['llm']=.05
        with self.assertRaises(TimeoutError):brains.answer(cfg,[],'first')
        other=copy.deepcopy(cfg);other['llm']['model']='different-configured-model'
        self.assertEqual(brains.answer(other,[],'other'),'OK')
        self.assertEqual(state['calls'],[cfg['llm']['model'],'different-configured-model'])

    def test_known_length_or_invalid_spoken_text_does_not_poison_terminal(self):
        cfg=configuration()
        for text,finish in [('partial','length'),('','stop')]:
            with patch('reachy_companion.brains.build_opener') as op:
                op.return_value.open.return_value=io.BytesIO(body(cfg,text,finish))
                with self.assertRaises(RuntimeError):brains.answer(cfg,[],'bad')
                self.assertEqual(brains.MODEL_EXECUTION.status(brains.model_identity(cfg)),dict(active=False,unknown=False))
                op.return_value.open.return_value=io.BytesIO(body(cfg))
                self.assertEqual(brains.answer(cfg,[],'fresh'),'OK')

    def test_invalid_truncated_mismatched_or_ambiguous_envelope_stays_unknown(self):
        cfg=configuration();valid=json.loads(body(cfg))
        bad=[b'{',json.dumps({**valid,'model':'foreign'}).encode(),json.dumps({'choices':valid['choices']}).encode(),
             json.dumps({**valid,'choices':valid['choices']*2}).encode(),
             json.dumps({**valid,'choices':[dict(index=True,text='x',finish_reason='stop')]}).encode(),
             json.dumps({**valid,'choices':[dict(text='x',finish_reason=None)]}).encode(),
             b'{"model":"x","model":"y"}',b'{"x":NaN}',b'x'*1048577]
        for raw in bad:
            with self.subTest(raw_prefix=raw[:20]),patch.object(brains,'MODEL_EXECUTION',brains.ModelExecutionOwnership()),patch('reachy_companion.brains.build_opener') as op:
                op.return_value.open.return_value=io.BytesIO(raw)
                with self.assertRaises((ValueError,RuntimeError)):brains.answer(cfg,[],'bad')
                with self.assertRaises(RuntimeError):brains.answer(cfg,[],'blocked')
                self.assertEqual(op.return_value.open.call_count,1)
                self.assertTrue(brains.MODEL_EXECUTION.status(brains.model_identity(cfg))['unknown'])

    def test_capacity_never_evicts_unknown_and_pre_submission_failure_releases(self):
        guard=brains.ModelExecutionOwnership(capacity=1)
        with self.assertRaises(ValueError):
            with guard.reserve(('host','a')):raise ValueError('before submit')
        with guard.reserve(('host','a')) as execution:execution.submitted()
        with self.assertRaises(RuntimeError):
            with guard.reserve(('host','b')):self.fail('unknown entry evicted')
        self.assertTrue(guard.status(('host','a'))['unknown'])


if __name__=='__main__':unittest.main()
