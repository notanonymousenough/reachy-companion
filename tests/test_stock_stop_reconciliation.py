"""Expired-owned UUID and stop transport failures; no physical stop claims."""
import json
import threading
import copy
import time
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from unittest.mock import Mock,patch

import test_stock_motion_routing as fixture_module


class StockStopReconciliationTests(unittest.TestCase):
    setUp=fixture_module.StockMotionTests.setUp
    factory=fixture_module.StockMotionTests.factory

    def stop_server(self,failure):
        fixture=self;self.reads_after_stop=[];self.stop_attempted=False
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                fixture.assertEqual(self.path,'/api/move/stop')
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.assertEqual(payload,dict(uuid=fixture_module.OWN))
                fixture.stop_attempted=True
                if failure=='404':self.send_error(404,'move no longer exists')
                else:
                    # Close without a response, representing an unknown HTTP
                    # completion. Fresh GET observations are independent.
                    if failure=='timeout':time.sleep(.2)
                    self.connection.close()
            def do_GET(self):
                if fixture.stop_attempted:fixture.reads_after_stop.append(self.path)
                value=fixture.factory(self.path)
                body=json.dumps(value).encode();self.send_response(200)
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join(2)))
        self.config.data['network']['robot_url']='http://127.0.0.1:'+str(server.server_port)
        self.hub.factory=type(self.hub).factory.__get__(self.hub)

    def payload(self):
        return dict(expected_hub_boot_id=self.hub.boot_id,owned_uuid=fixture_module.OWN,
            operator_binding=dict(agent_boot_id=self.operator['agent_boot_id'],microphone_epoch=self.operator['microphone_epoch'],
                policy_epoch=self.operator['motion_policy']['epoch'],microphone_enabled=self.operator['microphone_enabled']))

    def prepare_unknown(self):
        self.hub.stock_owned=fixture_module.OWN;self.hub.stock_unknown=True
        self.operator['motion_policy']['motor_enabled']=False

    def test_expired_uuid_404_observes_empty_but_retains_unknown_until_explicit_reconciliation(self):
        self.stop_server('404');self.hub.stock_owned=fixture_module.OWN
        with self.assertRaises(Exception):self.hub.stock_stop_owned(fixture_module.OWN)
        self.assertTrue(self.hub.stock_unknown)
        self.assertTrue(self.hub.stock_stop_observed)
        self.assertEqual(self.hub.stock_owned,fixture_module.OWN)
        self.assertIn('/api/move/running',self.reads_after_stop)
        self.assertEqual(self.hub.stock_stop_request,dict(endpoint='/api/move/stop',error_class='HTTPError',http_status=404))
        with self.assertRaises(RuntimeError):self.hub.move('/api/move/goto',{})
        self.operator['motion_policy']['motor_enabled']=False
        result=self.hub.stock_reconcile(self.payload())
        self.assertTrue(result['reconciled']);self.assertFalse(result['pose_verified']);self.assertFalse(result['hard_stop_certified'])
        self.assertFalse(self.hub.stock_unknown);self.assertIsNone(self.hub.stock_owned)
        self.assertFalse(self.operator['motion_policy']['motor_enabled'])
        with self.assertRaises(RuntimeError):self.hub.move('/api/move/goto',{})
        self.assertEqual(self.writes,[])

    def test_unknown_stop_transport_observes_empty_without_automatic_recovery(self):
        self.stop_server('transport');self.hub.stock_owned=fixture_module.OWN
        with self.assertRaises(Exception):self.hub.stock_stop_owned(fixture_module.OWN)
        self.assertTrue(self.hub.stock_unknown)
        self.assertTrue(self.hub.stock_stop_observed)
        self.assertIn('/api/move/running',self.reads_after_stop)

    def test_timeout_stop_empty_has_same_sticky_semantics(self):
        self.stop_server('timeout');self.config.data['timeouts']['robot']=.08
        self.hub.stock_owned=fixture_module.OWN
        with self.assertRaises(RuntimeError):self.hub.stock_stop_owned(fixture_module.OWN)
        self.assertTrue(self.hub.stock_unknown);self.assertTrue(self.hub.stock_stop_observed)
        self.assertEqual(self.hub.stock_stop_request['error_class'],'TimeoutError')
        self.assertNotIn('private',json.dumps(self.hub.stock_stop_request))

    def test_reconcile_denies_foreign_own_active_unready_or_unknown_state_without_writes(self):
        for problem in ('foreign','own','unready','held','state'):
            with self.subTest(problem=problem):
                self.prepare_unknown();original=self.factory
                def factory(path,payload=None):
                    if path=='/api/move/running':
                        return [dict(uuid=fixture_module.FOREIGN if problem=='foreign' else fixture_module.OWN)] if problem in ('foreign','own') else []
                    if path=='/api/daemon/status' and problem=='unready':return dict(state='running',backend_status=dict(ready=False))
                    if path=='/api/daemon/robot-app-lock-status' and problem=='held':return dict(state='held')
                    if path=='/api/state/full' and problem=='state':return {}
                    return original(path,payload)
                self.hub.factory.side_effect=factory
                with self.assertRaises(RuntimeError):self.hub.stock_reconcile(self.payload())
                self.assertTrue(self.hub.stock_unknown)
        self.assertEqual(self.writes,[])

    def test_reconcile_requires_exact_uuid_hub_and_complete_typed_operator(self):
        self.prepare_unknown();valid=self.payload()
        for change in (dict(expected_hub_boot_id='new-hub'),dict(owned_uuid=fixture_module.FOREIGN),dict(owned_uuid='bad'),
                       dict(owned_uuid=None),dict(operator_binding=None),dict(operator_binding={}),
                       dict(operator_binding=dict(valid['operator_binding'],microphone_epoch=True))):
            with self.subTest(change=change):
                with self.assertRaises((ValueError,RuntimeError,TypeError)):self.hub.stock_reconcile(dict(valid,**change))
                self.assertTrue(self.hub.stock_unknown)
        self.hub.stock_owned=None
        with self.assertRaises(RuntimeError):self.hub.stock_reconcile(valid)
        self.hub.stock_owned=fixture_module.OWN;self.hub.stock_unknown=False
        with self.assertRaises(RuntimeError):self.hub.stock_reconcile(valid)
        self.assertEqual(self.writes,[])

    def test_stop_with_missing_or_malformed_owned_uuid_never_posts(self):
        self.hub.stock_owned=None
        for task_id in (None,True,'bad',''):
            with self.assertRaises(ValueError):self.hub.stock_stop_owned(task_id)
        self.assertEqual(self.writes,[])

    def test_reconcile_lock_busy_or_enabled_motor_or_stale_operator_retains_latch(self):
        self.prepare_unknown();payload=self.payload()
        self.hub.lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError,'busy'):self.hub.stock_reconcile(payload)
        finally:self.hub.lock.release()
        self.operator['motion_policy']['motor_enabled']=True
        with self.assertRaises(RuntimeError):self.hub.stock_reconcile(payload)
        self.operator['motion_policy']['motor_enabled']=False
        def slow(path):time.sleep(.31);return copy.deepcopy(self.operator)
        self.hub.agent.side_effect=slow
        with self.assertRaises(RuntimeError):self.hub.stock_reconcile(payload)
        self.assertTrue(self.hub.stock_unknown);self.assertEqual(self.writes,[])

    def test_reconcile_rereads_operator_and_denies_epoch_or_boot_change_before_clear(self):
        for field in ('boot','mic','policy','mic_enabled'):
            self.prepare_unknown();payload=self.payload();calls=[]
            def operator(path):
                value=copy.deepcopy(self.operator);calls.append(path)
                if len(calls)==2:
                    if field=='boot':value['agent_boot_id']='new-boot'
                    if field=='mic':value['microphone_epoch']+=1
                    if field=='policy':value['motion_policy']['epoch']+=1
                    if field=='mic_enabled':value['microphone_enabled']=not value['microphone_enabled']
                return value
            self.hub.agent.side_effect=operator
            with self.assertRaises(RuntimeError):self.hub.stock_reconcile(payload)
            self.assertEqual(len(calls),2)
            self.assertTrue(self.hub.stock_unknown)
        self.assertEqual(self.writes,[])

    def test_real_authenticated_endpoint_strict_body_and_sanitized_errors(self):
        from reachy_companion.hub import serve
        self.prepare_unknown();ready=threading.Event();servers=[]
        self.hub.monitor=Mock()
        def create(address,handler):
            server=ThreadingHTTPServer(('127.0.0.1',0),handler)
            servers.append(server);ready.set();return server
        with patch('reachy_companion.hub.ThreadingHTTPServer',side_effect=create):
            thread=threading.Thread(target=serve,args=(self.hub,),daemon=True);thread.start()
            self.assertTrue(ready.wait(1))
        server=servers[0]
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join(2)))
        url='http://127.0.0.1:'+str(server.server_port)+'/actions/stock-reconcile'
        opener=build_opener(ProxyHandler({}))
        def call(body,token=None):
            request=Request(url,data=body,headers={'Authorization':'Bearer '+(self.config.token if token is None else token)})
            try:
                with opener.open(request,timeout=2) as response:return response.status,json.load(response)
            except HTTPError as exc:
                with exc:return exc.code,json.load(exc)
        body=json.dumps(self.payload()).encode()
        self.assertEqual(call(body,'wrong')[0],401)
        for invalid in (b'[]',b'{"owned_uuid":1,"owned_uuid":2}',b'x'*4097):
            self.assertEqual(call(invalid)[0],400)
            self.assertTrue(self.hub.stock_unknown)
        original=self.hub.factory.side_effect
        self.hub.factory.side_effect=RuntimeError('PRIVATE BODY TOKEN MUST NOT LEAK')
        code,result=call(body)
        self.assertEqual(code,409);self.assertEqual(result,dict(error='reconciliation_denied',
            phase='factory_deps',error_class='state_denied'))
        self.assertTrue(self.hub.stock_unknown)
        self.hub.factory.side_effect=original
        code,result=call(b'{"owned_uuid":1,"owned_uuid":2}')
        self.assertEqual(code,400);self.assertEqual(result,dict(error='invalid_reconciliation_request',
            phase='decode',error_class='validation'))
        self.hub.lock.acquire()
        try:code,result=call(body)
        finally:self.hub.lock.release()
        self.assertEqual(code,409);self.assertEqual(result['phase'],'admission')
        self.assertEqual(result['error_class'],'state_denied')
        self.assertTrue(self.hub.stock_unknown)
        code,result=call(body)
        self.assertEqual(code,200);self.assertTrue(result['reconciled'])
        self.assertFalse(result['hard_stop_certified']);self.assertEqual(self.writes,[])

    def test_diagnostics_cover_operator_factory_state_and_window_without_exception_text(self):
        from reachy_companion.hub import reconciliation_error_class
        self.assertEqual(reconciliation_error_class(ModuleNotFoundError('SECRET_MODULE')),'module_missing')
        for target in ('operator_before','factory_deps','state','operator_after','window'):
            self.prepare_unknown();diagnostic={};calls=[]
            original=self.factory
            def factory(path,payload=None):
                if target=='factory_deps' and path=='/api/daemon/status':
                    raise HTTPError('SECRET_URL',500,'SECRET_BODY',None,None)
                if target=='state' and path=='/api/state/full':raise ValueError('SECRET_STATE')
                if target=='window' and path=='/api/state/full':time.sleep(.31)
                return original(path,payload)
            def operator(path):
                calls.append(path)
                if target=='operator_before' or target=='operator_after' and len(calls)==2:
                    raise TimeoutError('SECRET_OPERATOR')
                return copy.deepcopy(self.operator)
            self.hub.factory.side_effect=factory;self.hub.agent.side_effect=operator
            with self.assertRaises(Exception) as caught:self.hub.stock_reconcile(self.payload(),diagnostic=diagnostic)
            self.assertEqual(diagnostic,dict(phase=target))
            self.assertNotIn('SECRET',json.dumps(diagnostic))
            self.assertEqual(reconciliation_error_class(caught.exception),
                'timeout' if target.startswith('operator_') else 'http_error' if target=='factory_deps'
                else 'validation' if target=='state' else 'state_denied')
            self.assertTrue(self.hub.stock_unknown)
        self.assertEqual(self.writes,[])

    def test_isolated_production_hub_without_autonomous_namespace_serves_strict_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            package=Path(directory)/'reachy_companion';package.mkdir()
            (package/'__init__.py').write_text('')
            shutil.copy(Path(__file__).resolve().parents[1]/'src/reachy_companion/hub.py',package/'hub.py')
            script=r'''
import importlib.util,json,sys,threading
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
sys.path.insert(0,sys.argv[1])
from reachy_companion.hub import Hub,serve
assert importlib.util.find_spec('reachy_companion.autonomous') is None
class Config:
    token='t'*32
    data={'guarded_motion':{'transport':'stock','enabled':True},'timeouts':{'http':1},
          'servers':{'hub':{'listen':'127.0.0.1','port':0}}}
    def __getitem__(self,key):return self.data[key]
hub=Hub(Config());hub.stock_unknown=True
hub.stock_owned='00000000-0000-4000-8000-000000000001'
operator=dict(agent_boot_id='fixture',microphone_epoch=0,microphone_enabled=False,
    microphone_state_error=None,motion_policy=dict(epoch=0,motor_enabled=False,quiet=False,privacy_all=False))
hub.agent=lambda path:operator
reads=[]
def factory(path,payload=None):
    assert payload is None
    reads.append(path)
    return {'/api/daemon/status':dict(state='running',backend_status=dict(ready=True)),
        '/api/daemon/robot-app-lock-status':dict(state='free'),'/api/move/running':[],
        '/api/state/full':dict(control_mode='enabled')}[path]
hub.factory=factory;hub.monitor=lambda:None
import reachy_companion.hub as module
ready=threading.Event();servers=[]
def server(address,handler):
    value=ThreadingHTTPServer(address,handler);servers.append(value);ready.set();return value
module.ThreadingHTTPServer=server
thread=threading.Thread(target=serve,args=(hub,),daemon=True);thread.start();assert ready.wait(2)
server=servers[0];url='http://127.0.0.1:'+str(server.server_port)+'/actions/stock-reconcile'
def call(body,token=Config.token):
    request=Request(url,data=body,headers={'Authorization':'Bearer '+token})
    try:
        with urlopen(request,timeout=2) as response:return response.status,json.load(response)
    except HTTPError as exc:
        with exc:return exc.code,json.load(exc)
try:
    body=json.dumps(dict(expected_hub_boot_id=hub.boot_id,owned_uuid=hub.stock_owned,
        operator_binding=dict(agent_boot_id='fixture',microphone_epoch=0,policy_epoch=0,microphone_enabled=False))).encode()
    assert call(body,'wrong')[0]==401
    for bad in (b'{}',b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'x'*4097):
        status,result=call(bad);assert status==400,(status,result);assert hub.stock_unknown
    operator['motion_policy']['motor_enabled']=True
    status,result=call(body);assert status==409
    assert result==dict(error='reconciliation_denied',phase='operator_before',error_class='state_denied')
    assert hub.stock_unknown
    operator['motion_policy']['motor_enabled']=False
    status,result=call(body);assert status==200 and result['reconciled']
    assert result['hard_stop_certified'] is False and hub.stock_unknown is False
    assert reads and 'reachy_companion.autonomous' not in sys.modules
finally:
    server.shutdown();server.server_close();thread.join(2)
'''
            result=subprocess.run([sys.executable,'-I','-c',script,directory],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
