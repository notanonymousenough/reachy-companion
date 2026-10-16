"""Launcher authority/cleanup checks; these do not certify hardware acceptance."""
import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from reachy_companion.client import demo, guarded_control
from reachy_companion.microphone import validate_control


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.operator = dict(agent_boot_id='boot', microphone_epoch=4, microphone_owner_id=None,
            microphone_enabled=False, capture_active=False, listening=False, phase='paused',
            motion_policy_owner_id=None, motion_policy=dict(epoch=8, motor_enabled=False, quiet=False, privacy_all=False))
        self.posts = []
        self.completed = 0
        self.fail_after_microphone = False
        self.foreign = False
        def guarded(config,base,path,payload,expected):
            import time
            from reachy_companion.client import request
            began=time.monotonic()
            if request(config,base+'/control/operator') != expected or time.monotonic()-began>.3:
                raise TimeoutError('stale fixture authority')
            return request(config,base+path,payload)
        guard=patch('reachy_companion.client.guarded_control',side_effect=guarded)
        guard.start();self.addCleanup(guard.stop)

    def request(self, config, url, payload=None, timeout=None):
        path = url.removeprefix('http://fixture')
        if payload is not None:
            self.posts.append((path, copy.deepcopy(payload)))
            self.assertEqual(payload['expected_boot_id'], self.operator['agent_boot_id'])
            mic = path.endswith('/microphone')
            state = self.operator if mic else self.operator['motion_policy']
            epoch = 'microphone_epoch' if mic else 'epoch'
            owner = 'microphone_owner_id' if mic else 'motion_policy_owner_id'
            self.assertEqual(payload['expected_epoch'], state[epoch])
            if 'expected_owner_id' in payload:
                self.assertEqual(payload['expected_owner_id'], self.operator[owner])
            state[epoch] += 1
            self.operator[owner] = payload.get('owner_id')
            if mic:
                self.operator.update(microphone_enabled=payload['enabled'], listening=payload['enabled'],
                    capture_active=payload['enabled'], phase='listening' if payload['enabled'] else 'paused')
                if payload['enabled'] and self.fail_after_microphone:
                    raise TimeoutError('private upstream body')
            else:
                state.update({k: payload[k] for k in ('motor_enabled','quiet','privacy_all')})
            return {}
        if path == '/control/operator':
            if self.foreign and self.operator['microphone_enabled']:
                self.operator['microphone_epoch'] += 1
                self.operator['microphone_owner_id'] = 'human'
                self.operator['motion_policy']['epoch'] += 1
                self.operator['motion_policy_owner_id'] = 'human'
            return copy.deepcopy(self.operator)
        if path == '/control/status':
            if self.operator['microphone_enabled']:
                self.completed += 1
            return dict(turns=self.completed, volume_percent=50)
        if path == '/status':
            return dict(stock_motion=dict(selected=True, unknown=False,
                owned_uuid='task' if self.completed and self.operator['microphone_enabled'] else None,
                stop_observed=True), action_running=False,
                ownership=dict(state='free'), robot=dict(control_mode='enabled'))
        self.fail(path)

    def run_demo(self, **kwargs):
        with patch('reachy_companion.client.request', side_effect=self.request), \
                patch('reachy_companion.client.time.sleep'), patch('builtins.print') as output:
            result = demo({'network': {'hub_url': 'http://fixture'}}, **kwargs)
        self.assertNotIn('private upstream body', str(output.call_args_list))
        return result

    def test_real_turn_counter_then_off_releases_both_claims(self):
        self.assertEqual(self.run_demo(), 0)
        self.assertEqual(self.completed, 3)
        self.assertFalse(self.operator['microphone_enabled'])
        self.assertFalse(self.operator['motion_policy']['motor_enabled'])
        self.assertIsNone(self.operator['microphone_owner_id'])
        self.assertIsNone(self.operator['motion_policy_owner_id'])
        self.assertEqual(len(self.posts), 4)
        self.assertNotIn('owner_id', self.posts[-1][1])

    def test_post_applied_but_response_lost_still_releases_own_claim(self):
        self.fail_after_microphone = True
        self.assertEqual(self.run_demo(), 1)
        self.assertEqual(len(self.posts), 4)
        self.assertFalse(self.operator['microphone_enabled'])

    def test_foreign_takeover_never_writes_cleanup(self):
        self.foreign = True
        self.assertEqual(self.run_demo(), 1)
        self.assertEqual(len(self.posts), 2)
        self.assertEqual(self.operator['microphone_owner_id'], 'human')

    def test_ctrl_c_and_deadline_release_without_restoring_on(self):
        with patch('reachy_companion.client.time.sleep',side_effect=KeyboardInterrupt):
            # Keep the inner helper from replacing this sleep patch.
            with patch('reachy_companion.client.request',side_effect=self.request), patch('builtins.print'):
                self.assertEqual(demo({'network':{'hub_url':'http://fixture'}}),130)
        self.assertFalse(self.operator['microphone_enabled'])
        self.setUp()
        clock=[0]
        with patch('reachy_companion.client.time.monotonic',side_effect=lambda:clock[0]), \
                patch('reachy_companion.client.time.sleep',side_effect=lambda _:clock.__setitem__(0,181)), \
                patch('reachy_companion.client.request',side_effect=self.request), patch('builtins.print'):
            self.assertEqual(demo({'network':{'hub_url':'http://fixture'}}),1)
        self.assertFalse(self.operator['microphone_enabled'])

    def test_quiet_or_existing_owner_denies_before_posts(self):
        self.operator['motion_policy']['quiet'] = True
        self.assertEqual(self.run_demo(), 1)
        self.assertEqual(self.posts, [])

    def test_unknown_stock_receipt_is_nonzero_even_after_turns(self):
        original = self.request
        def retained(*args, **kwargs):
            value = original(*args, **kwargs)
            if args[1].endswith('/status') and 'stock_motion' in value and self.completed:
                value['stock_motion'].update(owned_uuid='retained',stop_observed=None)
            return value
        with patch('reachy_companion.client.request',side_effect=retained), \
                patch('reachy_companion.client.time.sleep'), patch('builtins.print') as output:
            self.assertEqual(demo({'network':{'hub_url':'http://fixture'}}),1)
        self.assertIn('"cleanup_unknown": true',output.call_args.args[0])

    def test_expired_operator_prevents_permission_send(self):
        original = self.request
        clock=[0]
        def slow(*args, **kwargs):
            value=original(*args, **kwargs)
            if args[1].endswith('/control/operator'): clock[0] += .301
            return value
        with patch('reachy_companion.client.request',side_effect=slow), \
                patch('reachy_companion.client.time.monotonic',side_effect=lambda:clock[0]), patch('builtins.print'):
            self.assertEqual(demo({'network':{'hub_url':'http://fixture'}}),1)
        self.assertEqual(self.posts,[])

    def test_bounds_before_io(self):
        for kwargs in (dict(turns=True), dict(turns=4), dict(seconds=301), dict(seconds=0)):
            with self.assertRaises(ValueError): self.run_demo(**kwargs)
        self.assertEqual(self.posts, [])

    def test_microphone_whitelist_authority_bounds(self):
        validate_control(dict(enabled=True))
        valid = dict(enabled=True, listen=True, expected_boot_id='boot', expected_epoch=4,
            owner_id='demo', expected_owner_id='previous')
        validate_control(valid)
        for updates in (dict(enabled=1), dict(listen=1), dict(expected_epoch=True),
                dict(expected_epoch=-1), dict(expected_epoch=2**63), dict(expected_boot_id=''),
                dict(expected_boot_id='a'*257), dict(owner_id=None), dict(owner_id='a'*129), dict(extra=True)):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                validate_control(dict(valid, **updates))
        for value in (dict(enabled=True, owner_id='x'), dict(enabled=True, expected_epoch=4)):
            with self.assertRaises(ValueError): validate_control(value)


class GuardedControlTests(unittest.TestCase):
    def run_send(self, *, slow_before=False, slow_headers=False, partial=False, changed=False):
        clock=[0];self.sent=[];expected=dict(agent_boot_id='boot')
        def connect(connection):
            if slow_before:clock[0]+=10
            def send(data):
                self.sent.append(bytes(data))
                if partial:
                    clock[0]+=.301
                    return 1
                return len(data)
            connection.sock=SimpleNamespace(send=send,settimeout=lambda _:None,close=lambda:None)
        def read(*args,**kwargs):
            return {} if changed else expected
        import http.client
        real_putrequest=http.client.HTTPConnection.putrequest
        def putrequest(*args,**kwargs):
            if slow_headers:clock[0]+=.301
            return real_putrequest(*args,**kwargs)
        with patch('reachy_companion.client.time.monotonic',side_effect=lambda:clock[0]), \
                patch('reachy_companion.client.request',side_effect=read), \
                patch('http.client.HTTPConnection.connect',connect), \
                patch('http.client.HTTPConnection.putrequest',putrequest), \
                patch('http.client.HTTPConnection.getresponse',return_value=SimpleNamespace(status=200,read=lambda _:b'{}')):
            return guarded_control(SimpleNamespace(token='fixture'), 'http://fixture',
                '/control/microphone',dict(enabled=True),expected)

    def test_connect_before_fresh_read_and_headers_body_guarded(self):
        self.assertEqual(self.run_send(slow_before=True),{})
        self.assertEqual(len(self.sent),2)
        with self.assertRaises(TimeoutError):self.run_send(slow_headers=True)
        self.assertEqual(self.sent,[])

    def test_partial_socket_write_rechecks_before_every_next_send(self):
        with self.assertRaises(TimeoutError):self.run_send(partial=True)
        self.assertEqual(len(self.sent),1)

    def test_operator_change_after_connect_denies_all_sends(self):
        with self.assertRaises(ValueError):self.run_send(changed=True)
        self.assertEqual(self.sent,[])


if __name__ == '__main__': unittest.main()
