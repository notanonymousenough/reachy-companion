"""Authenticated, uncached exact Agent operator read through production Hub."""
import copy
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from unittest.mock import Mock,patch

import test_stock_motion_routing as fixture_module


class OperatorProxyTests(unittest.TestCase):
    def setUp(self):
        fixture_module.StockMotionTests.setUp(self)
        self.value=dict(agent_boot_id='current-agent',microphone_epoch=110,microphone_owner_id=None,
            microphone_enabled=False,capture_active=False,phase='paused',listening=False,
            microphone_state_error=None,motion_policy=dict(epoch=15,motor_enabled=False,quiet=False,privacy_all=False),
            motion_policy_owner_id=None,expression_version=8)
        self.upstream=[];self.delay=0;self.status=200;self.raw=None;self.content_type='application/json'
        fixture=self
        class AgentHandler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                fixture.upstream.append((self.path,self.headers.get('Authorization')))
                time.sleep(fixture.delay)
                body=json.dumps(fixture.value).encode() if fixture.raw is None else fixture.raw
                try:
                    self.send_response(fixture.status);self.send_header('Content-Type',fixture.content_type)
                    self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
        self.agent_server=ThreadingHTTPServer(('127.0.0.1',0),AgentHandler)
        self.agent_thread=threading.Thread(target=self.agent_server.serve_forever,daemon=True);self.agent_thread.start()
        self.config.data['network']['agent_url']='http://127.0.0.1:'+str(self.agent_server.server_port)
        self.hub.agent=type(self.hub).agent.__get__(self.hub)
        self.hub.monitor=Mock()
        servers=[];ready=threading.Event()
        def create(address,handler):
            server=ThreadingHTTPServer(('127.0.0.1',0),handler);servers.append(server);ready.set();return server
        from reachy_companion.hub import serve
        with patch('reachy_companion.hub.ThreadingHTTPServer',side_effect=create):
            self.thread=threading.Thread(target=serve,args=(self.hub,),daemon=True);self.thread.start()
            self.assertTrue(ready.wait(1))
        self.server=servers[0];self.addCleanup(self.close)
        self.opener=build_opener(ProxyHandler({}))

    factory=fixture_module.StockMotionTests.factory

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        self.agent_server.shutdown();self.agent_server.server_close();self.agent_thread.join(2)

    def call(self,token=None,path='/control/operator'):
        request=Request('http://127.0.0.1:'+str(self.server.server_port)+path,
            headers={'Authorization':'Bearer '+(self.config.token if token is None else token)})
        try:response=self.opener.open(request,timeout=2)
        except HTTPError as exc:response=exc
        with response:return response.code,json.load(response),response.headers

    def test_bad_auth_never_calls_upstream_and_fixed_route_is_not_arbitrary_proxy(self):
        for token in ('wrong','é',''):
            code,_,headers=self.call(token)
            self.assertEqual(code,401);self.assertEqual(headers['Cache-Control'],'no-store')
        for path in ('/control/operator?path=/status','/control/operator/other'):
            self.assertEqual(self.call(path=path)[0],404)
        self.assertEqual(self.upstream,[]);self.assertEqual(self.writes,[])

    def test_complete_fresh_typed_operator_forwarded_exactly_and_uncached(self):
        for index in range(2):
            self.value['microphone_epoch']+=1
            self.value['microphone_owner_id']='fixture-owner' if index else None
            self.value['motion_policy_owner_id']='fixture-policy' if index else None
            self.value['motion_policy'].update(motor_enabled=bool(index),quiet=bool(index),privacy_all=bool(index))
            code,value,headers=self.call()
            self.assertEqual(code,200);self.assertEqual(value,self.value)
            self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.upstream,[('/operator','Bearer '+self.config.token)]*2)
        self.assertEqual(self.writes,[])

    def test_slow_error_oversized_invalid_json_and_media_type_fail_closed(self):
        for failure in ('slow','http','oversized','json','duplicate','nonfinite','media'):
            self.delay=0;self.status=200;self.raw=None;self.content_type='application/json'
            if failure=='slow':self.delay=.35
            if failure=='http':self.status=500;self.raw=b'SECRET upstream body'
            if failure=='oversized':self.raw=b' '*8193
            if failure=='json':self.raw=b'SECRET malformed JSON'
            if failure=='duplicate':self.raw=b'{"agent_boot_id":"a","agent_boot_id":"SECRET"}'
            if failure=='nonfinite':self.raw=b'{"microphone_epoch":NaN}'
            if failure=='media':self.content_type='text/plain'
            with self.subTest(failure=failure):
                code,value,headers=self.call()
                self.assertEqual(code,503);self.assertEqual(value,dict(error='operator_unavailable'))
                self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.writes,[])

    def test_missing_fields_null_bool_aliases_owner_and_error_states_fail_closed(self):
        original=copy.deepcopy(self.value)
        mutations=[lambda v:v.pop('microphone_owner_id'),lambda v:v.update(microphone_epoch=True),
            lambda v:v.update(expression_version=None),lambda v:v.update(capture_active=0),
            lambda v:v.update(microphone_owner_id=42),lambda v:v.update(motion_policy_owner_id=''),
            lambda v:v.update(microphone_state_error='SECRET private path'),lambda v:v.update(phase=['paused']),
            lambda v:v['motion_policy'].update(epoch=None),lambda v:v['motion_policy'].update(motor_enabled=0),
            lambda v:v['motion_policy'].update(privacy_all=None),lambda v:v.update(secret='SECRET')]
        for mutate in mutations:
            self.value=copy.deepcopy(original);mutate(self.value)
            code,result,_=self.call();self.assertEqual(code,503)
            self.assertEqual(result,dict(error='operator_unavailable'))
        self.assertEqual(self.writes,[])

    def test_elapsed_from_upstream_begin_and_before_response_are_both_checked(self):
        valid=copy.deepcopy(self.value)
        with patch.object(self.hub,'agent',return_value=valid),patch('reachy_companion.hub.time.monotonic',side_effect=[1,1.301]):
            with self.assertRaises(TimeoutError):self.hub.operator_proxy()
        with patch.object(self.hub,'operator_proxy',return_value=(valid,time.monotonic()-.301)):
            code,result,_=self.call();self.assertEqual(code,503)
            self.assertEqual(result,dict(error='operator_unavailable'))
        self.assertEqual(self.upstream,[])


if __name__=='__main__':unittest.main()
