"""Exact installed-Agent guard: stale bindings cannot change listening."""
import ast
import importlib.util
import io
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_agent_live_latency_patch import load

ROOT = Path(__file__).resolve().parents[1]


class BoundListeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('bound_listening_builder',
            ROOT/'deploy/autonomous/prepare_bound_listening.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)
        _, source = cls.builder.candidate()
        cls.module = load(source.decode())
        cls.source = source.decode()

    def setUp(self):
        self.agent = self.module.Agent.__new__(self.module.Agent)
        a = self.agent
        a.agent_boot_id = 'boot'
        a.microphone_epoch = 11
        a.microphone_owner_id = 'owner'
        a.microphone = SimpleNamespace(enabled=True, error=None)
        a.microphone_lock = threading.Lock()
        a.stopping = threading.Event()
        a.listening = threading.Event()
        a.phase = 'paused'
        a.capture_active = False
        self.policy = dict(epoch=7, motor_enabled=True, quiet=False, privacy_all=False)
        a.motion_policy = SimpleNamespace(lock=threading.RLock(), owner_id='owner',
                                         snapshot=lambda: dict(self.policy))
        self.binding = dict(agent_boot_id='boot', microphone_epoch=11, policy_epoch=7,
                            owner_id='owner', expires_at_monotonic=120.)
        self.clock = patch.object(self.module.time, 'monotonic', return_value=100.)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def call(self, enabled=True, binding=None):
        return self.agent.set_listening(enabled,
            {'operator_binding': self.binding if binding is None else binding})

    def test_bound_resume_and_pause_mutate_under_both_locks_without_epoch_change(self):
        a = self.agent
        events = []
        class CheckedEvent:
            def set(inner):
                events.append(('set', a.microphone_lock.locked(), a.motion_policy.lock._is_owned()))
            def clear(inner):
                events.append(('clear', a.microphone_lock.locked(), a.motion_policy.lock._is_owned()))
        a.listening = CheckedEvent()
        self.assertEqual(self.call(), dict(ok=True, listening=True))
        a.phase = 'speaking'
        self.assertEqual(self.call(False), dict(ok=True, listening=False))
        self.assertEqual(events, [('set', True, True), ('clear', True, True)])
        self.assertEqual((a.microphone_epoch, self.policy['epoch']), (11, 7))

    def test_stale_boot_epochs_owner_and_deadline_never_mutate(self):
        for key, value in (('agent_boot_id', 'new'), ('microphone_epoch', 12),
                           ('policy_epoch', 8), ('owner_id', 'new'),
                           ('expires_at_monotonic', 100.), ('expires_at_monotonic', 161.)):
            with self.subTest(key=key, value=value):
                for enabled in (False, True):
                    self.agent.listening.set()
                    with self.assertRaises(RuntimeError):
                        self.call(enabled, dict(self.binding, **{key: value}))
                    self.assertTrue(self.agent.listening.is_set())

    def test_types_nan_oversized_clock_and_extra_fields_rejected(self):
        for key, value in (('microphone_epoch', True), ('owner_id', False),
                           ('expires_at_monotonic', float('nan')),
                           ('expires_at_monotonic', float('inf')),
                           ('expires_at_monotonic', 10**1000), ('extra', 1)):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    self.call(binding=dict(self.binding, **{key: value}))
                self.assertFalse(self.agent.listening.is_set())
        with self.assertRaises(ValueError):
            self.agent.set_listening(True, {'ignored': 'not allowed'})
        for field in ('owner_id', 'expires_at_monotonic'):
            missing = dict(self.binding)
            missing.pop(field)
            with self.assertRaises(ValueError): self.call(binding=missing)

    def test_muted_privacy_new_policy_owner_and_stopping_reject(self):
        for change in ('muted', 'error', 'privacy', 'quiet', 'motor', 'owner', 'stop', 'capture'):
            with self.subTest(change=change):
                a = self.agent
                a.microphone.enabled = True
                a.microphone.error = None
                a.motion_policy.owner_id = 'owner'
                a.stopping.clear()
                a.capture_active = False
                self.policy.update(epoch=7, motor_enabled=True, quiet=False, privacy_all=False)
                if change == 'muted': a.microphone.enabled = False
                if change == 'error': a.microphone.error = 'unknown'
                if change == 'privacy': self.policy['privacy_all'] = True
                if change == 'quiet': self.policy['quiet'] = True
                if change == 'motor': self.policy['motor_enabled'] = False
                if change == 'owner': a.motion_policy.owner_id = 'new'
                if change == 'stop': a.stopping.set()
                if change == 'capture': a.capture_active = True
                with self.assertRaises(RuntimeError): self.call()
                self.assertFalse(a.listening.is_set())

    def test_expected_manual_none_requires_both_current_owners_none(self):
        a = self.agent
        binding = dict(self.binding, owner_id=None)
        for mic_owner, policy_owner in (('owner', 'owner'), (None, 'owner'), ('owner', None)):
            a.microphone_owner_id = mic_owner
            a.motion_policy.owner_id = policy_owner
            with self.assertRaises(RuntimeError): self.call(binding=binding)
            self.assertFalse(a.listening.is_set())
        a.microphone_owner_id = a.motion_policy.owner_id = None
        self.assertTrue(self.call(binding=binding)['listening'])
        self.assertFalse(self.call(False, binding)['listening'])
        with self.assertRaises(RuntimeError): self.call(binding=self.binding)

    def test_manual_bound_say_passes_explicit_epochs_deadline_and_rejects_new_owner(self):
        a = self.agent
        a.microphone_owner_id = a.motion_policy.owner_id = None
        a.audio_lock = threading.Lock()
        a.config = {'timeouts': {'manual_audio_lock': .1}, 'conversation': {'session': 'test'}}
        a.voice = Mock(return_value={'ok': True})
        def operator():
            return dict(agent_boot_id=a.agent_boot_id, microphone_epoch=a.microphone_epoch,
                motion_policy=dict(self.policy), microphone_owner_id=a.microphone_owner_id,
                motion_policy_owner_id=a.motion_policy.owner_id, microphone_enabled=a.microphone.enabled,
                capture_active=a.capture_active, listening=a.listening.is_set(), phase=a.phase)
        a.operator_status = operator
        payload = dict(text='public fixed cue', operator_binding=dict(self.binding, owner_id=None))
        self.assertTrue(a.manual('/say', payload)['ok'])
        self.assertEqual(a.voice.call_args.kwargs,
            dict(allow_barge_in=False, expected_epoch=11, expected_policy_epoch=7, valid_until=120.))
        a.voice.reset_mock()
        a.microphone_epoch += 1
        with self.assertRaises(RuntimeError): a.manual('/say', payload)
        a.voice.assert_not_called()
        a.microphone_epoch -= 1
        a.microphone_owner_id = 'new-owner'
        with self.assertRaises(RuntimeError): a.manual('/say', payload)
        a.voice.assert_not_called()

    def test_bound_manual_phase_and_new_grant_before_event_clear_are_guarded(self):
        a = self.agent
        a.microphone_owner_id = a.motion_policy.owner_id = None
        a.audio_lock = threading.Lock()
        a.config = {'timeouts': {'manual_audio_lock': .1}, 'conversation': {'session': 'test'}}
        a.voice = Mock(return_value={'ok': True})
        def operator():
            return dict(agent_boot_id=a.agent_boot_id, microphone_epoch=a.microphone_epoch,
                motion_policy=dict(self.policy), microphone_owner_id=a.microphone_owner_id,
                motion_policy_owner_id=a.motion_policy.owner_id, microphone_enabled=a.microphone.enabled,
                capture_active=a.capture_active, listening=a.listening.is_set(), phase=a.phase)
        a.operator_status = operator
        payload = dict(text='public fixed cue', operator_binding=dict(self.binding, owner_id=None))
        a.phase = 'speaking'
        with self.assertRaises(RuntimeError): a.manual('/say', payload)
        a.voice.assert_not_called()
        a.phase = 'paused'
        def changed_after_snapshot():
            previous = operator()
            a.microphone_epoch += 1
            a.microphone_owner_id = 'new'
            a.listening.set()
            return previous
        a.operator_status = changed_after_snapshot
        with self.assertRaises(RuntimeError): a.manual('/say', payload)
        self.assertTrue(a.listening.is_set())
        a.voice.assert_not_called()

    def test_nullable_binding_does_not_change_microphone_owner_grant_validation(self):
        from reachy_companion.microphone import validate_control
        with self.assertRaises(ValueError):
            validate_control(dict(enabled=True, expected_boot_id='boot', expected_epoch=11, owner_id=None))

    def test_deadline_is_rechecked_after_waiting_for_mutation_lock(self):
        reached = threading.Event()
        release = threading.Event()
        class GateLock:
            def __enter__(inner):
                reached.set()
                if not release.wait(1): raise RuntimeError('test lock timed out')
            def __exit__(inner, *args): pass
        self.agent.microphone_lock = GateLock()
        errors = []
        def run():
            try: self.call()
            except RuntimeError as error: errors.append(error)
        worker = threading.Thread(target=run)
        worker.start()
        self.assertTrue(reached.wait(1))
        self.module.time.monotonic.return_value = 121.
        release.set()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertFalse(self.agent.listening.is_set())

    def test_new_microphone_epoch_while_waiting_for_lock_wins(self):
        a = self.agent
        errors = []
        begun = threading.Event()
        def run():
            begun.set()
            try: self.call()
            except RuntimeError as error: errors.append(error)
        with a.microphone_lock:
            worker = threading.Thread(target=run)
            worker.start()
            self.assertTrue(begun.wait(1))
            a.microphone_epoch += 1
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertFalse(a.listening.is_set())

    def test_new_policy_epoch_before_mutation_wins(self):
        a = self.agent
        errors = []
        begun = threading.Event()
        def run():
            begun.set()
            try: self.call(False)
            except RuntimeError as error: errors.append(error)
        a.listening.set()
        with a.motion_policy.lock:
            worker = threading.Thread(target=run)
            worker.start()
            self.assertTrue(begun.wait(1))
            self.policy['epoch'] += 1
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertTrue(a.listening.is_set())

    def test_legacy_manual_payload_retained_and_muted_resume_still_fails(self):
        a = self.agent
        self.assertTrue(a.set_listening(True, {})['listening'])
        self.assertFalse(a.set_listening(False, {})['listening'])
        a.microphone.enabled = False
        with self.assertRaises(RuntimeError): a.set_listening(True, {})
        self.assertFalse(a.set_listening(False, {})['listening'])

    def test_actual_http_handler_consumes_binding_and_rejects_stale_duplicate_json(self):
        tree = ast.parse(self.source)
        handler = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == 'Handler')
        scope = dict(self.module.__dict__, agent=self.agent, config={}, LOG=Mock())
        exec(compile(ast.Module(body=[handler], type_ignores=[]), 'listening-handler.py', 'exec'), scope)
        cls = scope['Handler']
        replies = []
        cls.auth = lambda item: True
        cls.reply = lambda item, status, body: replies.append((status, body))
        h = cls.__new__(cls)
        def post(body):
            h.path = '/resume'
            h.headers = {'Content-Length': str(len(body))}
            h.rfile = io.BytesIO(body)
            h.do_POST()
            return replies[-1][0]
        self.assertEqual(post(json.dumps({'operator_binding': self.binding}).encode()), 200)
        self.agent.listening.clear()
        self.agent.microphone_epoch += 1
        self.assertEqual(post(json.dumps({'operator_binding': self.binding}).encode()), 409)
        self.assertFalse(self.agent.listening.is_set())
        self.assertEqual(post(b'{"operator_binding":{},"operator_binding":{}}'), 409)
        self.assertFalse(self.agent.listening.is_set())
        self.assertEqual(post(b'{}'), 200)
