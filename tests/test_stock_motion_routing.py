"""Stock factory route: epochs, one command lane, owned stop and honest receipts."""
import copy
import json
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

from reachy_companion.config import Config, initialize
from reachy_companion.hub import Hub


OWN = '00000000-0000-4000-8000-000000000001'
FOREIGN = '00000000-0000-4000-8000-000000000002'


class StockMotionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        source = Path(__file__).resolve().parents[1]
        shutil.copy(source/'config.example.json', root)
        shutil.copytree(source/'profiles', root/'profiles')
        initialize(root)
        self.config = Config(root/'config.local.json')
        self.config.data['guarded_motion'].update(enabled=True, transport='stock')
        self.config.data['motion']['move_poll_seconds'] = .001
        self.config.data['timeouts']['move'] = .02
        self.hub = Hub(self.config)
        self.operator = dict(agent_boot_id='current', microphone_epoch=1,
            microphone_enabled=False, microphone_state_error=None,
            motion_policy=dict(epoch=2, motor_enabled=True, quiet=False, privacy_all=False))
        self.active = []
        self.writes = []
        self.on_post = lambda: None
        self.on_poll = lambda: self.active.clear()
        self.hub.agent = Mock(side_effect=lambda path: copy.deepcopy(self.operator))
        self.hub.factory = Mock(side_effect=self.factory)

    def factory(self, path, payload=None):
        if payload is not None:
            self.writes.append((path, copy.deepcopy(payload)))
            if path == '/api/move/stop':
                self.active = [v for v in self.active if v['uuid'] != payload['uuid']]
                return {}
            self.active = [dict(uuid=OWN)]
            self.on_post()
            return dict(uuid=OWN)
        if path == '/api/daemon/status':
            return dict(state='running', error=None, backend_status=dict(ready=True))
        if path == '/api/daemon/robot-app-lock-status': return dict(state='free')
        if path == '/api/move/running':
            if self.active: self.on_poll()
            return copy.deepcopy(self.active)
        if path == '/api/state/full': return dict(control_mode='enabled')
        raise AssertionError(path)

    def test_default_and_unknown_transport_validation(self):
        data = json.loads(self.config.filename.read_text())
        data['guarded_motion'].pop('transport', None)
        self.config.filename.write_text(json.dumps(data))
        self.assertEqual(Config(self.config.filename)['guarded_motion']['transport'], 'native')
        for transport in ('fallback', None, True, 0, []):
            data['guarded_motion']['transport'] = transport
            self.config.filename.write_text(json.dumps(data))
            with self.assertRaises(ValueError): Config(self.config.filename)

    def test_stock_explicit_enable_typed_permission_and_native_separation(self):
        changes = [('microphone_epoch', True), ('microphone_state_error', 'unavailable'),
                   ('agent_boot_id', ''), ('microphone_enabled', 0)]
        for key, value in changes:
            with self.subTest(key=key):
                old = self.operator[key];self.operator[key] = value
                with self.assertRaises(RuntimeError): self.hub.move('/api/move/goto', {})
                self.operator[key] = old
        for key, value in [('epoch', True), ('motor_enabled', 1), ('quiet', True), ('privacy_all', True)]:
            old = self.operator['motion_policy'][key];self.operator['motion_policy'][key] = value
            with self.assertRaises(RuntimeError): self.hub.move('/api/move/goto', {})
            self.operator['motion_policy'][key] = old
        self.config.data['guarded_motion']['enabled'] = False
        with self.assertRaises(RuntimeError): self.hub.move('/api/move/goto', {})
        with self.assertRaises(RuntimeError): self.hub.native_motion({})
        self.assertEqual(self.writes, [])
        self.assertFalse(self.hub.lock.locked())

    def test_completion_is_observation_and_untouched_axes_explicit_null(self):
        result = self.hub.move('/api/move/goto', dict(antennas=[.01, 0], duration=.5))
        self.assertEqual(self.writes[0][1], dict(antennas=[.01, 0], duration=.5,
                                              body_yaw=None, head_pose=None))
        self.assertTrue(result['completion_observed'])
        self.assertFalse(result['pose_verified'])
        self.assertFalse(result['hard_stop_certified'])
        self.assertIsNone(self.hub.stock_owned)

    def test_boot_mic_policy_change_stops_only_owned_without_return_or_sleep(self):
        for change in ('boot', 'mic', 'mic_enabled', 'policy', 'deny', 'offline'):
            with self.subTest(change=change):
                self.setUp()
                self.on_poll = lambda: None
                def withdraw():
                    if change == 'boot': self.operator['agent_boot_id'] = 'new'
                    if change == 'mic': self.operator['microphone_epoch'] += 1
                    if change == 'mic_enabled': self.operator['microphone_enabled'] = True
                    if change == 'policy': self.operator['motion_policy']['epoch'] += 1
                    if change == 'deny': self.operator['motion_policy']['motor_enabled'] = False
                    if change == 'offline': self.hub.agent.side_effect = TimeoutError('operator offline')
                self.on_post = withdraw
                step = dict(head_pose=dict(x=0,y=0,z=0,roll=0,pitch=0,yaw=0),
                            antennas=[.01,0],duration=.5,interpolation='minjerk')
                with self.assertRaises((RuntimeError, TimeoutError)):
                    self.hub.expression(dict(steps=[step, step]))
                self.assertEqual([p for p, _ in self.writes], ['/api/move/goto','/api/move/stop'])
                self.assertEqual(self.writes[-1][1], dict(uuid=OWN))
                self.assertTrue(self.hub.stock_stop_observed)
                self.assertFalse(self.hub.lock.locked())

    def test_unknown_post_or_missing_uuid_latches_without_retry_or_blind_stop(self):
        for result in (TimeoutError('lost response'), {}, {'uuid':'bad'}):
            with self.subTest(result=result):
                self.setUp()
                original = self.factory
                def factory(path, payload=None):
                    if payload is not None:
                        self.writes.append((path, payload))
                        if isinstance(result, Exception): raise result
                        return result
                    return original(path, payload)
                self.hub.factory.side_effect = factory
                with self.assertRaises((TimeoutError, KeyError, ValueError)):
                    self.hub.move('/api/move/goto', {})
                with self.assertRaises(RuntimeError): self.hub.move('/api/move/goto', {})
                self.assertTrue(self.hub.stock_unknown)
                self.assertEqual(len(self.writes), 1)

    def test_timeout_stop_and_foreign_uuid_never_stopped(self):
        self.on_poll = lambda: None
        with self.assertRaises(TimeoutError): self.hub.move('/api/move/goto', {})
        self.assertEqual(self.writes[-1], ('/api/move/stop', dict(uuid=OWN)))
        self.assertTrue(self.hub.stock_stop_observed)
        self.active = [dict(uuid=FOREIGN)]
        with self.assertRaises(RuntimeError): self.hub.move('/api/move/goto', {})
        self.assertEqual(len(self.writes), 2)

    def test_foreign_appearing_midflight_stops_own_and_leaves_foreign(self):
        self.on_post = lambda: self.active.append(dict(uuid=FOREIGN))
        self.on_poll = lambda: None
        with self.assertRaises(RuntimeError): self.hub.move('/api/move/goto', {})
        self.assertEqual(self.writes[-1], ('/api/move/stop', dict(uuid=OWN)))
        self.assertEqual(self.active, [dict(uuid=FOREIGN)])

    def test_stop_failure_latches_unknown(self):
        original = self.factory
        self.on_poll=lambda:None
        self.on_post = lambda: self.operator['motion_policy'].update(quiet=True)
        def factory(path, payload=None):
            if path == '/api/move/stop': raise TimeoutError('stop unobserved')
            return original(path,payload)
        self.hub.factory.side_effect = factory
        with self.assertRaises(RuntimeError): self.hub.move('/api/move/goto', {})
        self.assertTrue(self.hub.stock_unknown)
        self.assertFalse(self.hub.stock_stop_observed)
        self.assertEqual(self.hub.stock_owned, OWN)

    def test_wake_failure_does_not_finally_sleep(self):
        original=self.factory
        def factory(path,payload=None):
            if path=='/api/state/full':return dict(control_mode='disabled')
            if path=='/api/motors/set_mode/enabled':
                self.writes.append((path,payload))
                self.operator['motion_policy']['motor_enabled']=False
                return {}
            return original(path,payload)
        self.hub.factory.side_effect=factory
        with self.assertRaises(RuntimeError):self.hub.action('wake')
        self.assertEqual(self.writes,[('/api/motors/set_mode/enabled',{})])
        self.assertFalse(self.hub.lock.locked())

    def test_hello_actual_pose_requires_two_finite_positions(self):
        (self.config.path(self.config['paths']['scenarios_dir'])).mkdir(parents=True,exist_ok=True)
        (self.config.path(self.config['paths']['scenarios_dir'])/'hello.json').write_text(
            json.dumps(dict(steps=[dict(offset=[.01,0],duration=.5),dict(offset=[0,0],duration=.5)])))
        original=self.factory
        actuals=[[0,0],[.01,0],[0,0],[0,0]]
        def factory(path,payload=None):
            if path=='/api/motors/status':return dict(mode='enabled')
            if path=='/api/state/present_antenna_joint_positions':return actuals.pop(0)
            return original(path,payload)
        self.hub.factory.side_effect=factory
        result=self.hub.action('hello')
        self.assertTrue(result['antenna_pose_verified'])
        self.assertFalse(result['pose_verified'])
        self.assertEqual(result['moves_observed'],2)
        self.assertTrue(all(body['body_yaw'] is None and body['head_pose'] is None for _,body in self.writes))
        actuals[:]=[[]]
        with self.assertRaisesRegex(RuntimeError,'positions unknown'):self.hub.action('hello')
        self.assertEqual(len(self.writes),2)

    def test_unready_or_foreign_factory_denies_before_post(self):
        for owner in (None,{'state':'held'}):
            original=self.factory
            def factory(path,payload=None):
                if path=='/api/daemon/robot-app-lock-status':return owner
                return original(path,payload)
            self.hub.factory.side_effect=factory
            with self.assertRaises(RuntimeError):self.hub.move('/api/move/goto',{})
        self.assertEqual(self.writes,[])

    def test_one_lane_denies_concurrent_movement(self):
        entered = threading.Event();release = threading.Event();errors=[]
        self.on_post = lambda: (entered.set(), release.wait(2))
        def move():
            try: self.hub.move('/api/move/goto', {})
            except BaseException as exc: errors.append(exc)
        thread = threading.Thread(target=move)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaisesRegex(RuntimeError, 'busy'): self.hub.move('/api/move/goto', {})
        finally: release.set();thread.join(2)
        self.assertEqual(errors, [])
        self.assertEqual(len(self.writes), 1)

    def test_real_http_agent_auth_and_factory_body(self):
        fixture = self
        auth = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self): self.reply(None)
            def do_POST(self):
                self.reply(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            def reply(self,payload):
                if self.path == '/operator':
                    auth.append(self.headers.get('Authorization'))
                    result = fixture.operator
                else: result = fixture.factory(self.path,payload)
                body=json.dumps(result).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url='http://127.0.0.1:'+str(server.server_port)
            self.config.data['network'].update(robot_url=url,agent_url=url)
            self.hub=Hub(self.config)
            result=self.hub.move('/api/move/goto',dict(antennas=[0,.01],duration=.5))
            self.assertTrue(result['completion_observed'])
            self.assertTrue(auth)
            self.assertTrue(all(value=='Bearer '+self.config.token for value in auth))
            self.assertIsNone(self.writes[0][1]['body_yaw'])
        finally:server.shutdown();server.server_close();thread.join(2)


if __name__ == '__main__': unittest.main()
