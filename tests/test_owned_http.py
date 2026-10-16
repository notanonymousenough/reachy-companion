"""Loopback-only checks of the extracted owned HTTP deadline/body boundary."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from urllib.request import Request

from reachy_companion import owned_http, provisional_stt as partial
from test_provisional_stt import answer, payload, PCM, wait_for


class OwnedHttpTests(unittest.TestCase):
    def server(self, handle):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self): handle(self)
            def log_message(self, *args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler); server.daemon_threads=True
        thread=threading.Thread(target=lambda:server.serve_forever(poll_interval=.02),daemon=True); thread.start()
        self.addCleanup(thread.join,1); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        return server

    def test_valid_response_and_bounded_oversize_keep_auth_and_same_binding(self):
        seen=[]; oversized=[False]
        def handle(handler):
            value=json.loads(handler.rfile.read(int(handler.headers['Content-Length'])))
            seen.append((handler.path,handler.headers.get('Authorization'),value))
            body=json.dumps(answer(value),ensure_ascii=False).encode()
            if oversized[0]: body=b' '*(partial.MAX_RESPONSE+1)
            handler.send_response(200); handler.send_header('Content-Type','application/json')
            handler.send_header('Content-Length',str(len(body))); handler.end_headers(); handler.wfile.write(body)
        server=self.server(handle); url='http://127.0.0.1:'+str(server.server_port)+'/transcribe'
        class Config(dict): token='fixture'
        agent=SimpleNamespace(config=Config(network=dict(voice_url=url.removesuffix('/transcribe'))))
        target=owned_http.prepare(url)
        result=partial.exchange(agent,target,payload(),time.monotonic()+1)
        self.assertEqual(result['binding'],payload()['binding']); self.assertEqual(len(seen),1)
        self.assertEqual(seen[0][:2],('/transcribe','Bearer fixture'))
        oversized[0]=True
        with self.assertRaises(ValueError): partial.exchange(agent,target,payload(),time.monotonic()+1)
        self.assertEqual(len(seen),2)

    def test_header_and_body_trickle_cannot_extend_original_deadline(self):
        for headers in (True,False):
            stop=threading.Event(); done=threading.Event(); posts=[]
            def handle(handler):
                posts.append(True); value=json.loads(handler.rfile.read(int(handler.headers.get('Content-Length',0))))
                try:
                    if headers:
                        handler.wfile.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nX-Slow: ')
                    else:
                        handler.send_response(200); handler.send_header('Content-Type','application/json')
                        handler.send_header('Content-Length','8192'); handler.end_headers()
                        # A complete JSON prefix must not be accepted when the
                        # claimed body only finishes because the watchdog fires.
                        handler.wfile.write(json.dumps(answer(value)).encode())
                    handler.wfile.flush()
                    while not stop.wait(.02): handler.wfile.write(b' '); handler.wfile.flush()
                except OSError: pass
                finally: done.set()
            server=self.server(handle); url='http://127.0.0.1:'+str(server.server_port)+'/transcribe'
            target=owned_http.prepare(url)
            class Config(dict): token='fixture'
            agent=SimpleNamespace(config=Config(network=dict(voice_url=url.removesuffix('/transcribe'))))
            began=time.monotonic()
            try:
                with self.assertRaises((OSError,ValueError,http.client.HTTPException)):
                    partial.exchange(agent,target,payload(),began+.25)
                self.assertLess(time.monotonic()-began,1)
                self.assertEqual(posts,[True])
            finally:
                stop.set(); self.assertTrue(done.wait(1))

    def test_context_cancellation_closes_socket_and_never_sends_again(self):
        done=threading.Event(); count=[]
        def handle(handler):
            count.append(True); handler.rfile.read(int(handler.headers.get('Content-Length',0)))
            handler.send_response(200); handler.send_header('Content-Type','application/json')
            handler.send_header('Content-Length','1000'); handler.end_headers()
            try:
                while True: handler.wfile.write(b'x'); handler.wfile.flush(); time.sleep(.02)
            except OSError: pass
            finally: done.set()
        server=self.server(handle); url='http://127.0.0.1:'+str(server.server_port)+'/transcribe'
        target=owned_http.prepare(url)
        with self.assertRaises(RuntimeError):
            with owned_http.owned_response(Request(url,data=b'{}'),time.monotonic()+1,target):
                raise RuntimeError('fixture cancellation')
        self.assertTrue(done.wait(1)); self.assertEqual(count,[True])

    def test_truncated_framing_keeps_durable_unknown_and_never_reposts(self):
        for framing in ('length','chunked','chunked_trailer_missing_crlf','chunked_complete'):
            posts=[]
            def handle(handler):
                value=json.loads(handler.rfile.read(int(handler.headers['Content-Length'])))
                posts.append(value); body=json.dumps(answer(value)).encode()
                handler.send_response(200); handler.send_header('Content-Type','application/json')
                if framing=='length': handler.send_header('Content-Length',str(len(body)+100))
                else: handler.send_header('Transfer-Encoding','chunked')
                handler.end_headers()
                try:
                    if framing.startswith('chunked'):
                        ending={'chunked':b'', 'chunked_trailer_missing_crlf':b'0\r\n',
                                'chunked_complete':b'0\r\n\r\n'}[framing]
                        handler.wfile.write(('%x\r\n'%len(body)).encode()+body+b'\r\n'+ending)
                    else: handler.wfile.write(body)
                    handler.wfile.flush()
                except OSError: pass
                finally: handler.close_connection=True
            server=self.server(handle); url='http://127.0.0.1:'+str(server.server_port)
            class Config(dict): token='fixture'
            with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
                owner=SimpleNamespace(config=Config(network=dict(voice_url=url)))
                latch=partial.IntentLatch(Path(directory)/'intent')
                pump=SimpleNamespace(binding=('fixture',1,2),generation=1)
                fresh=lambda item:item.received_end<=time.monotonic()<=item.deadline
                client=partial.ProvisionalClient(owner,pump,fresh,latch=latch)
                self.addCleanup(client.close); client.begin(1); client.start()
                began=time.monotonic(); client.offer(1,PCM,began,0)
                wait_for(lambda:client.stopped)
                self.assertLess(time.monotonic()-began,1.5)
                self.assertTrue(owner._provisional_unknown); self.assertTrue(latch.exists())
                self.assertIsNone(client.latest); self.assertEqual(len(posts),1)
                next_owner=SimpleNamespace(config=owner.config)
                next_client=partial.ProvisionalClient(next_owner,
                    SimpleNamespace(binding=('new-boot',3,4),generation=2),fresh,latch=partial.IntentLatch(latch.path))
                self.addCleanup(next_client.close); next_client.begin(1); next_client.start()
                self.assertFalse(next_client.offer(1,PCM,time.monotonic(),0))
                self.assertTrue(next_owner._provisional_unknown); self.assertEqual(len(posts),1)

    def test_chunked_is_unsupported_and_complete_eof_is_accepted(self):
        for framing in ('chunked','eof'):
            def handle(handler):
                value=json.loads(handler.rfile.read(int(handler.headers['Content-Length'])))
                body=json.dumps(answer(value)).encode()
                handler.send_response(200); handler.send_header('Content-Type','application/json')
                if framing=='chunked': handler.send_header('Transfer-Encoding','chunked')
                handler.end_headers()
                try:
                    if framing=='chunked': handler.wfile.write(('%x\r\n'%len(body)).encode()+body+b'\r\n0\r\n\r\n')
                    else: handler.wfile.write(body)
                    handler.wfile.flush()
                except OSError: pass
                finally: handler.close_connection=True
            server=self.server(handle); url='http://127.0.0.1:'+str(server.server_port)
            class Config(dict): token='fixture'
            owner=SimpleNamespace(config=Config(network=dict(voice_url=url)))
            target=owned_http.prepare(url+'/transcribe')
            if framing=='chunked':
                with self.assertRaises(ValueError): partial.exchange(owner,target,payload(),time.monotonic()+1)
            else:
                result=partial.exchange(owner,target,payload(),time.monotonic()+1)
                self.assertEqual(result['status'],'recognized')


if __name__=='__main__': unittest.main()
