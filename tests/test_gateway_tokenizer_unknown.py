"""Actual local Gateway HTTP and producer slots, synthetic SDK/tokenizer only."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
import socket
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.contracts import decode
from reachy_companion.autonomous.gateway import create_server
from reachy_companion.autonomous.state import State


class TokenizerHTTPTests(unittest.TestCase):
    def fixture(self,*,sdk=True,close='normal'):
        entered=threading.Event();release=threading.Event();late_terminal=threading.Event()
        state=SimpleNamespace(mode='valid',tokenize=0,http_tokenize=0,complete=0,closed=0)
        class ModelHandler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=decode(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path=='/tokenize':
                    if body['model']=='fixture-main':
                        state.http_tokenize+=1
                        if state.mode in ('truncated','bad_status'):
                            entered.set()
                            if state.mode=='truncated':
                                self.send_response(200);self.send_header('Transfer-Encoding','chunked');self.end_headers()
                                self.wfile.write(b'10\r\nx') # promised chunk never finishes
                            else:self.wfile.write(b'INVALID STATUS\r\n\r\n')
                            self.wfile.flush();self.connection.shutdown(socket.SHUT_WR)
                            release.wait(2);late_terminal.set();return
                        if state.mode=='timeout':entered.set();release.wait(2);late_terminal.set()
                    value=dict(tokens=[True] if state.mode=='invalid_http' else [1,2])
                else:value=dict(choices=[dict(text='{"a":"wait","why":"fixture"}',finish_reason='stop')])
                raw=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except OSError:pass
        model_server=ThreadingHTTPServer(('127.0.0.1',0),ModelHandler)
        model_thread=threading.Thread(target=model_server.serve_forever,daemon=True);model_thread.start()
        cfg=load(Path(__file__).resolve().parents[1]/'config.autonomous.example.json')
        cfg['gateway'].update(port=0,token_env='TOKENIZER_FIXTURE_TOKEN');cfg['http_timeout_s']=.1
        for role in ('fast','main'):
            model=cfg['models'][role]
            model.update(id='fixture-'+role,base_url='http://127.0.0.1:'+str(model_server.server_port),tokenize_path='/tokenize')
            model['audit'].update(verified=True,device='cpu_pc',runtime_build='fixture',weight_sha256='fixture',
                template_sha256='fixture',tokenizer_sha256='fixture',runtime_context_tokens=model['context_tokens'])
        class Handle:
            def get_info(self):return SimpleNamespace(identifier='fixture-main',context_length=cfg['models']['main']['context_tokens'])
            def tokenize(self,text):
                state.tokenize+=1
                if state.mode=='timeout':
                    entered.set();release.wait(2)
                    raise TimeoutError('fixture SDK tokenizer outcome unknown')
                return [True] if state.mode=='invalid' else [1,2]
            def complete(self,prompt,config):
                state.complete+=1
                return SimpleNamespace(content='Neutral fixture reply',stats=SimpleNamespace(stop_reason='eosFound',predicted_tokens_count=1,time_to_first_token_sec=.001))
        handle=Handle()
        class Client:
            def __init__(self,*args):self.llm=SimpleNamespace(list_loaded=lambda:[handle])
            def __enter__(self):return self
            def __exit__(self,kind,value,tb):
                state.closed+=1
                if close=='raise' and kind is not None:raise OSError('fixture SDK close failure')
                return close=='suppress'
        if sdk:cfg['models']['main'].update(completion_backend='lmstudio_sdk',tokenizer_backend='lmstudio_sdk')
        fake_sdk=SimpleNamespace(Client=Client,set_sync_api_timeout=lambda _:None)
        modules=patch.dict('sys.modules',lmstudio=fake_sdk);environment=patch.dict(os.environ,TOKENIZER_FIXTURE_TOKEN='t'*32)
        modules.start();environment.start();server=create_server(cfg)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def cleanup():
            release.set();server.shutdown();server.server_close();worker.join(1)
            model_server.shutdown();model_server.server_close();model_thread.join(1);modules.stop();environment.stop()
        self.addCleanup(cleanup)
        url='http://127.0.0.1:'+str(server.server_port)
        def request(path,data=None):
            payload=None if data is None else json.dumps(dict(request_id='fixture-request',data=data)).encode()
            req=Request(url+path,data=payload,headers={'Authorization':'Bearer '+'t'*32,'Content-Type':'application/json'})
            try:
                with urlopen(req,timeout=3) as response:return response.status,decode(response.read())
            except HTTPError as exc:return exc.code,decode(exc.read())
        return SimpleNamespace(request=request,server=server,config=cfg,state=state,entered=entered,release=release,late_terminal=late_terminal)

    def test_sdk_tokenizer_unknown_keeps_lane_reserved_through_close_raise_or_suppression(self):
        for close in ('normal','raise','suppress'):
            with self.subTest(close=close):
                fixture=self.fixture(close=close);fixture.state.mode='timeout';out=[]
                worker=threading.Thread(target=lambda:out.append(fixture.request('/main','Neutral fixture input')));worker.start()
                self.assertTrue(fixture.entered.wait(1))
                health=fixture.request('/health')[1]
                self.assertTrue(health['busy']['main']);self.assertFalse(health['busy']['fast'])
                self.assertEqual(fixture.request('/main','Concurrent fixture')[0],409)
                fixture.release.set();worker.join(2);self.assertFalse(worker.is_alive())
                self.assertEqual(out[0][0],503);self.assertEqual(out[0][1]['error'],'execution_unknown_quarantined')
                fixture.late_terminal.set();fixture.state.mode='valid'
                health=fixture.request('/health')[1]
                self.assertEqual(health['compute_boot_id'],fixture.server.gateway.boot_id)
                self.assertEqual(health['quarantined'],['main']);self.assertTrue(health['busy']['main'])
                self.assertEqual(fixture.request('/main','Late terminal cannot reset')[0],409)
                self.assertEqual(fixture.state.tokenize,1);self.assertEqual(fixture.state.complete,0);self.assertEqual(fixture.state.closed,1)
                self.assertEqual(fixture.request('/decision',State().snapshot(0))[0],200)
                self.assertFalse(fixture.request('/health')[1]['busy']['fast'])

    def test_known_invalid_tokens_and_local_budget_reject_422_then_valid_terminal_releases(self):
        fixture=self.fixture();fixture.state.mode='invalid'
        self.assertEqual(fixture.request('/main','Known malformed tokenizer result')[0],422)
        self.assertFalse(fixture.request('/health')[1]['busy']['main']);self.assertEqual(fixture.state.complete,0)
        fixture.state.mode='valid';model=fixture.config['models']['main'];cap=model['input_cap_tokens'];model['input_cap_tokens']=1
        self.assertEqual(fixture.request('/main','Known budget rejection')[0],422)
        self.assertEqual(fixture.request('/health')[1]['quarantined'],[]);self.assertEqual(fixture.state.complete,0)
        model['input_cap_tokens']=cap
        self.assertEqual(fixture.request('/main','Known successful completion')[0],200)
        self.assertFalse(fixture.request('/health')[1]['busy']['main']);self.assertEqual(fixture.state.complete,1)

    def test_http_tokenizer_socket_timeout_retains_lane_after_remote_handler_finally_returns(self):
        fixture=self.fixture(sdk=False);fixture.state.mode='timeout'
        code,body=fixture.request('/main','Neutral HTTP tokenizer fixture')
        self.assertEqual(code,503);self.assertTrue(fixture.entered.is_set())
        self.assertEqual(body['error'],'execution_unknown_quarantined')
        self.assertTrue(fixture.request('/health')[1]['busy']['main'])
        fixture.release.set();self.assertTrue(fixture.late_terminal.wait(1))
        self.assertEqual(fixture.request('/main','No ABA after late producer return')[0],409)
        self.assertEqual(fixture.request('/health')[1]['quarantined'],['main'])
        self.assertEqual(fixture.request('/decision',State().snapshot(0))[0],200)

    def test_http_framing_errors_quarantine_while_tokenizer_handler_is_still_occupied(self):
        for mode in ('truncated','bad_status'):
            with self.subTest(mode=mode):
                fixture=self.fixture(sdk=False);fixture.state.mode=mode
                code,body=fixture.request('/main','Neutral framing fixture')
                self.assertEqual(code,503);self.assertEqual(body['error'],'execution_unknown_quarantined')
                self.assertTrue(fixture.entered.is_set());self.assertFalse(fixture.late_terminal.is_set())
                health=fixture.request('/health')[1]
                self.assertTrue(health['busy']['main']);self.assertEqual(health['quarantined'],['main'])
                self.assertEqual(fixture.request('/main','Must not start second tokenizer')[0],409)
                self.assertEqual(fixture.state.http_tokenize,1)
                fixture.release.set();self.assertTrue(fixture.late_terminal.wait(1))
                self.assertEqual(fixture.request('/main','Late terminal is not reset')[0],409)
                self.assertEqual(fixture.state.http_tokenize,1)

    def test_fully_received_invalid_http_tokens_remain_known_422_then_release(self):
        fixture=self.fixture(sdk=False);fixture.state.mode='invalid_http'
        self.assertEqual(fixture.request('/main','Known complete invalid HTTP result')[0],422)
        health=fixture.request('/health')[1]
        self.assertFalse(health['busy']['main']);self.assertEqual(health['quarantined'],[])
        fixture.state.mode='valid'
        self.assertEqual(fixture.request('/main','Known later valid HTTP completion')[0],200)
        self.assertFalse(fixture.request('/health')[1]['busy']['main'])


if __name__=='__main__':unittest.main()
