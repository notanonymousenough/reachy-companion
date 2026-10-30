"""R13 finite goal/clock source fixtures. No network, models or hardware."""
import copy
import hashlib
from concurrent.futures import Future
import json
import math
from pathlib import Path
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import Mock, patch

import test_native_agent_session as fixtures
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.native_agent import (
    GoalClockNativeAgent, GoalClockBinding, NativeReadExpired, NativeScheduler, motor_identity)
from reachy_companion.autonomous.native_agent_session import validate_lifecycle

ROOT = Path(__file__).resolve().parents[1]
GOAL = dict(id='finite-initial-settle', version=13, text='One initial fixed settle when clock permits.',
            changed_at='2026-10-17T10:00:00Z', reason='Explicit operator finite trial',
            evidence_ids=[], origin='operator')
CHOICE = dict(a='explore', why='Operator goal and clock', motion='settle')


class GoalClockStockTests(unittest.TestCase):
    factory = fixtures.NativeSessionTests.factory
    guarded = fixtures.NativeSessionTests.guarded
    wait = fixtures.NativeSessionTests.wait
    finish = fixtures.NativeSessionTests.finish
    pending = staticmethod(fixtures.NativeSessionTests.pending)
    stock_transport = fixtures.NativeSessionTests.stock_transport

    def setUp(self):
        fixtures.NativeSessionTests.setUp(self)
        self.cfg['context']['enabled'] = False
        self.cfg['native_agent'].update(stock_profile='finite_goal_clock',
                                       operator_goal=copy.deepcopy(GOAL), goal_ttl_s=30)
        self.replace_native()

    def replace_native(self, *, clock=time.monotonic):
        previous = self.native
        self.native = GoalClockNativeAgent(previous.agent, previous.hub, self.companion,
            copy.deepcopy(self.operator), self.hub.boot_id, allow_stock=True,
            goal=self.cfg['native_agent']['operator_goal'], goal_ttl_s=self.cfg['native_agent']['goal_ttl_s'], clock=clock)
        self.scheduler = NativeScheduler(self.cfg, self.gateway, self.native)
        self.addCleanup(self.scheduler.close)
        self.native.latest = self.native.read()
        self.native.motor_unavailable = False
        self.scheduler.state.observe()
        self.native.next_poll = math.inf

    def proposal(self, *, now=None, timeout=2):
        now = self.native.clock() if now is None else now
        state = self.scheduler.state
        binding = state.bind(now, timeout)
        state.apply(CHOICE, binding, now)
        self.assertIsNotNone(state.stock_proposal)
        return state.stock_proposal

    def accept_poll(self):
        self.native.poll_job = self.pending()
        self.native.poll_job.future.set_result(self.native.read())
        self.native.advance()

    def collect_stock(self):
        self.wait(lambda: self.native.stock_job.future.done())
        self.native.advance()

    def test_goal_clock_projection_excludes_all_audio_context_and_external_inputs(self):
        state = self.scheduler.state
        state.current_utterance = 'private text'
        state.previous.append('audio-derived old choice')
        state.context_sensors = [dict(id='private-camera', state='ready', age_ms=0, summary='private image')]
        view = state.snapshot(self.native.clock())
        self.assertEqual(view['goal'], GOAL)
        self.assertEqual([v['id'] for v in view['sensors']], ['native.clock', 'native.audio'])
        for key in ('memory', 'pending', 'ready', 'candidates', 'prev', 'evidence_aliases'):
            self.assertEqual(view[key], [])
        self.assertEqual(view['dialogue'], '')
        self.assertNotIn('private', json.dumps(view))
        for event in (dict(type='utterance', text='audio'), dict(type='sensor', id='audio'), dict(type='workflow')):
            with self.assertRaises(ValueError): state.ingest(event, self.native.clock())
        proposal = self.proposal()
        self.assertEqual(proposal['basis'], 'operator_goal_clock')
        with self.assertRaises(Exception):
            state.apply(dict(CHOICE, basis='audio'), state.bind(self.native.clock(), 1), self.native.clock())

    def test_initial_mic_off_and_pause_are_sensor_unknown_not_new_motor_grant(self):
        self.operator.update(microphone_enabled=False, listening=False, capture_active=False, phase='paused')
        self.replace_native()
        self.accept_poll()
        self.assertTrue(self.native.stock_allowed(self.native.clock()))
        self.assertTrue(self.native.unavailable)
        self.assertFalse(self.native.sensor_continuous)
        self.assertIsNone(self.native.withdrawn)
        proposal = self.proposal()
        with patch('reachy_companion.autonomous.native_agent.guarded_control', side_effect=self.guarded) as send:
            self.assertTrue(self.native.dispatch(proposal)); self.collect_stock()
        self.assertEqual(send.call_count, 1)
        self.assertEqual(len(self.writes), 2)
        self.assertEqual(self.native.stock_receipt['completion'], 'observed')

    def test_gap_invalidates_old_fast_and_proposal_but_new_clock_binding_can_settle(self):
        old = self.proposal()
        old_binding = self.scheduler.state.bind(self.native.clock(), 2)
        self.native.sensor_gap('audio_timeout', self.native.clock())
        self.accept_poll()  # Recovery/replacement never restores PCM continuity.
        self.scheduler.state.apply(CHOICE, old_binding, self.native.clock())
        self.assertEqual(self.scheduler.state.counts['native_decision_discarded'], 1)
        with patch('reachy_companion.autonomous.native_agent.guarded_control', side_effect=self.guarded) as send:
            self.assertFalse(self.native.dispatch(old)); self.assertEqual(send.call_count, 0)
            new = self.proposal()
            self.assertNotEqual(new['request_id'], old['request_id'])
            self.assertTrue(self.native.dispatch(new)); self.collect_stock()
            self.assertFalse(self.native.dispatch(new)); self.assertFalse(self.native.dispatch(old))
        self.assertEqual(send.call_count, 1)
        self.assertFalse(self.native.sensor_continuous)
        self.assertEqual(len(self.writes), 2)

    def test_audio_replacement_counter_regression_and_retirement_invalidate_each_new_decision(self):
        for change in ('replacement', 'counter', 'retired', 'pause', 'turns'):
            with self.subTest(change=change):
                proposal = self.proposal()
                generation = self.native.generation
                if change == 'replacement': self.pcm['source_generation'] += 1
                elif change == 'counter': self.pcm['read_calls'] = -100
                elif change == 'retired': self.pcm['retired'] = True
                elif change == 'pause': self.operator.update(listening=False, capture_active=False, phase='paused')
                else:
                    self.turns = 5; self.accept_poll(); self.turns = 1
                self.accept_poll()
                # Initial fixture watermark must first be observed before a replacement comparison.
                if change == 'replacement' and generation == self.native.generation:
                    self.pcm['source_generation'] += 1; self.accept_poll()
                self.assertGreater(self.native.generation, generation)
                self.assertFalse(self.native.admit_stock(proposal))
                self.assertIsNone(self.native.withdrawn)
                self.pcm.update(read_calls=0, retired=False)
                self.operator.update(listening=True, capture_active=True, phase='processing')
                self.accept_poll()
                self.assertFalse(self.native.sensor_continuous)

    def test_motor_projection_is_typed_and_ignores_only_sensor_observations(self):
        original = motor_identity(self.operator)
        current = copy.deepcopy(self.operator)
        current.update(listening=False, capture_active=False, phase='paused')
        self.assertEqual(motor_identity(current), original)
        current['listening'] = 0
        with self.assertRaises(ValueError): motor_identity(current)

    def test_durable_withdrawals_and_aba_remain_terminal_no_auto_rebinding(self):
        mutations = (
            lambda op: op.update(microphone_enabled=False, microphone_epoch=2),
            lambda op: op.update(microphone_epoch=3),  # OFF -> ON ABA
            lambda op: op['motion_policy'].update(epoch=4),  # policy/owner ABA
            lambda op: op.update(microphone_epoch=3, microphone_owner_id=None),
            lambda op: op.update(microphone_owner_id='foreign'),
            lambda op: op.update(motion_policy_owner_id='foreign'),
            lambda op: op.update(agent_boot_id='restarted'),
            lambda op: op.update(microphone_state_error='persistence'),
            lambda op: op['motion_policy'].update(motor_enabled=False),
            lambda op: op['motion_policy'].update(quiet=True),
            lambda op: op['motion_policy'].update(privacy_all=True),
            lambda op: op['motion_policy'].update(epoch=None),
            lambda op: op['motion_policy'].update(epoch=2**63-1),
            lambda op: op.update(microphone_epoch=2**63-1),
        )
        initial = copy.deepcopy(self.operator)
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.operator = copy.deepcopy(initial); self.replace_native()
                proposal = self.proposal(); mutate(self.operator)
                with self.assertRaises(ValueError): self.native.read_motor_receipt()
                self.assertIsNotNone(self.native.withdrawn)
                self.operator = copy.deepcopy(initial)
                self.native.latest = self.native.read_motor_receipt()
                self.native.motor_unavailable = False
                with patch('reachy_companion.autonomous.native_agent.guarded_control') as send:
                    self.assertFalse(self.native.dispatch(proposal)); send.assert_not_called()

    def test_poll_gap_during_reducer_never_rebinds_old_fast_to_new_generation(self):
        from reachy_companion.autonomous.state import State
        original = State.apply
        binding = self.scheduler.state.bind(self.native.clock(), 2)
        def gap_during_apply(state, choice, bound, now):
            result = original(state, choice, bound, now)
            self.native.sensor_gap('concurrent_poll', now)
            return result
        with patch.object(State, 'apply', gap_during_apply), \
             patch('reachy_companion.autonomous.native_agent.guarded_control') as send:
            self.scheduler.state.apply(CHOICE, binding, self.native.clock())
            self.assertIsNone(self.scheduler.state.stock_proposal)
            send.assert_not_called()
        self.assertEqual(self.scheduler.state.counts['native_decision_discarded'], 1)

    def test_reserved_busy_poll_holds_admission_but_does_not_forge_effect_unknown(self):
        proposal = self.proposal()
        self.native.stock_used = True
        self.native.stock_job = self.pending()
        hardware = self.hub.status(); hardware['action_running'] = True
        original = self.native.hub.get
        def busy(path): return hardware if path == '/status' else original(path)
        with patch.object(self.native.hub, 'get', side_effect=busy):
            with self.assertRaises(NativeReadExpired): self.native.read_motor_receipt(poll=True)
            self.assertIsNone(self.native.withdrawn)
            self.assertFalse(self.native.admit_stock(proposal))
            self.assertFalse(self.native.stock_unknown)
            # The SAME busy hardware may never pass the effect preflight.
            with self.assertRaises(ValueError): self.native.read_motor_receipt()
        self.assertIsNotNone(self.native.withdrawn)
        self.native.stock_job.future.set_result(dict(completion='observed'))
        self.native.advance()
        self.assertEqual(self.native.stock_receipt['completion'], 'observed')
        self.assertTrue(self.native.stock_used)

    def test_sensor_revoke_publishes_before_final_control_timeout_and_before_send(self):
        proposal = self.proposal()
        self.pcm['retired'] = True
        original = self.native.hub.get
        reads = [0]
        def timeout(path):
            if path == '/control/operator':
                reads[0] += 1
                if reads[0] == 2: raise TimeoutError('final control unavailable')
            return original(path)
        with patch.object(self.native.hub, 'get', side_effect=timeout):
            with self.assertRaises(TimeoutError): self.native.read()
        self.assertGreater(self.native.generation, proposal['generation'])
        self.assertFalse(self.native.admit_stock(proposal))
        self.assertIsNone(self.native.withdrawn)
        self.assertFalse(self.native.sensor_continuous)

    def test_finite_session_acceptance_allows_sensor_unknown_and_reports_no_live_claim(self):
        from reachy_companion.autonomous.native_agent_session import run_native_session
        self.operator.update(listening=False, capture_active=False, phase='paused')
        self.replace_native(); self.native.next_poll = 0
        self.gateway.choice = CHOICE
        stop = threading.Event()
        with patch('reachy_companion.autonomous.native_agent.guarded_control', side_effect=self.guarded):
            report = run_native_session(self.scheduler, stop, 1, lambda _: None)
        self.assertTrue(report['accepted'], report)
        self.assertEqual(report['stock_profile'], 'finite_goal_clock')
        self.assertEqual(report['minimum_accepted_decisions'], 1)
        self.assertTrue(report['stock_used']); self.assertTrue(report['stock_dispatch_observed'])
        self.assertFalse(report['live_acceptance']); self.assertFalse(report['continuous_acceptance'])
        self.assertEqual(report['observation']['sensor_state'], 'UNKNOWN')
        self.assertFalse(report['observation']['pcm_continuity'])
        self.assertEqual(len(self.writes), 2)

    def test_original_effect_deadline_is_minimum_never_extended_by_rereads(self):
        clock = [100.]
        self.replace_native(clock=lambda: clock[0])
        self.native.goal_expires = 100.25
        proposal = self.proposal(timeout=.2)
        self.assertEqual(proposal['deadline'], 100.2)
        clock[0] = 100.15; self.accept_poll()
        self.assertTrue(self.native.admit_stock(proposal))
        clock[0] = 100.2
        self.assertFalse(self.native.admit_stock(proposal))
        self.assertEqual(proposal['receipt_begin'], 100.)
        self.assertEqual(self.proposal(timeout=1)['deadline'], 100.25)

    def test_goal_changes_expiry_and_explicit_disable_close_the_arm(self):
        for kind in ('goal_version', 'goal_text', 'goal_replace', 'expired', 'operator_disable', 'stop_event'):
            with self.subTest(kind=kind):
                self.cfg['native_agent']['operator_goal'] = copy.deepcopy(GOAL)
                self.replace_native(); proposal = self.proposal()
                if kind == 'goal_version': self.cfg['native_agent']['operator_goal']['version'] += 1
                elif kind == 'goal_text': self.cfg['native_agent']['operator_goal']['text'] = 'Changed goal'
                elif kind == 'goal_replace': self.cfg['native_agent']['operator_goal'] = dict(GOAL, version=14)
                elif kind == 'expired': self.native.goal_expires = self.native.clock()
                elif kind == 'operator_disable':
                    self.scheduler.ingest(dict(type='operator', muted=True))
                    self.scheduler.ingest(dict(type='operator', muted=False))
                else:
                    event = threading.Event(); self.native.stop_requested = event.is_set; event.set()
                self.assertFalse(self.native.dispatch(proposal))
                if kind != 'expired': self.assertIsNotNone(self.native.withdrawn)

    def test_busy_unknown_foreign_boot_and_malformed_control_all_have_zero_post(self):
        hardware = self.hub.status()
        for update in (
            dict(action_running=True), dict(ownership=dict(state='foreign')),
            dict(stock_motion=dict(hardware['stock_motion'], unknown=True)),
            dict(stock_motion=dict(hardware['stock_motion'], owned_uuid=fixtures.MOVE)),
            dict(stock_motion=dict(hardware['stock_motion'], hub_boot_id='foreign')),
            dict(stock_motion=dict(hardware['stock_motion'], selected=False)),
            dict(stock_motion={k:v for k,v in hardware['stock_motion'].items() if k != 'owned_uuid'}),
            dict(stock_motion=dict(hardware['stock_motion'], owned_uuid=123)),
            dict(robot=dict(control_mode='disabled')),
        ):
            with self.subTest(update=update):
                self.replace_native(); proposal = self.proposal()
                with patch.object(self.native.hub, 'get', return_value=dict(hardware, **update)), \
                     patch('reachy_companion.autonomous.native_agent.guarded_control') as send:
                    self.assertTrue(self.native.dispatch(proposal)); self.collect_stock()
                    send.assert_not_called()
                self.assertIsNotNone(self.native.withdrawn)
                self.assertTrue(self.native.stock_used)
        self.replace_native(); proposal = self.proposal()
        def bad(path): return hardware if path == '/status' else dict(self.operator, expression_version=True)
        with patch.object(self.native.hub, 'get', side_effect=bad), \
             patch('reachy_companion.autonomous.native_agent.guarded_control') as send:
            self.assertTrue(self.native.dispatch(proposal)); self.collect_stock(); send.assert_not_called()
        self.assertIsNotNone(self.native.withdrawn)

    def test_control_timeout_closes_admission_and_known_revoke_is_not_hidden_by_later_timeout(self):
        with patch.object(self.native.hub, 'get', side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError): self.native.read_motor_receipt()
        self.assertFalse(self.native.stock_allowed(self.native.clock()))
        self.assertIsNone(self.native.withdrawn)
        hardware = self.hub.status(); hardware['stock_motion']['unknown'] = True
        with patch.object(self.native.hub, 'get', side_effect=[hardware, TimeoutError()]) as get:
            with self.assertRaises(ValueError): self.native.read_motor_receipt()
            self.assertEqual(get.call_count, 1)
        self.assertIsNotNone(self.native.withdrawn)

    def test_begin_age_not_end_time_and_expired_proposals_have_zero_post(self):
        clock = [100.]; self.replace_native(clock=lambda: clock[0])
        original = self.native.hub.get
        def slow(path):
            result = original(path)
            if path == '/control/operator': clock[0] += .3
            return result
        with patch.object(self.native.hub, 'get', side_effect=slow):
            with self.assertRaises(NativeReadExpired): self.native.read_motor_receipt()
        self.assertIsNone(self.native.withdrawn)
        self.assertFalse(self.native.stock_allowed(clock[0]))
        self.replace_native(clock=lambda: clock[0]); proposal = self.proposal()
        clock[0] += .3
        with patch('reachy_companion.autonomous.native_agent.guarded_control') as send:
            self.assertFalse(self.native.dispatch(proposal)); send.assert_not_called()

    def test_single_actual_poll_and_fast_slots_survive_unknown_without_replacements(self):
        clock = [100.]; self.replace_native(clock=lambda: clock[0])
        self.native.next_poll = 0
        with patch('reachy_companion.autonomous.native_agent.Job', side_effect=self.pending), \
             patch('reachy_companion.autonomous.runtime.Job', side_effect=self.pending):
            self.scheduler.advance()
            poll, fast = self.native.poll_job, self.scheduler.fast_job
            self.assertIsNotNone(poll); self.assertIsNotNone(fast)
            for now in (100.1, 100.31, 101., 105.):
                clock[0] = now; self.scheduler.advance()
                self.assertIs(self.native.poll_job, poll); self.assertIs(self.scheduler.fast_job, fast)
            self.assertEqual(self.native.polls, 1)
            receipt = self.native.read(); poll.future.set_result(receipt)
            self.scheduler.advance()
            fast.future.set_result(dict(output=CHOICE, compute_boot_id=self.gateway.boot_id,
                                        request_id=self.scheduler.binding.request_id))
            self.scheduler.advance()
            self.assertEqual(self.scheduler.state.counts['native_decision_discarded'], 1)
            self.assertFalse(self.native.stock_used)

    def test_socket_barrier_revoke_and_local_stop_have_zero_post_reserved_no_replay(self):
        for kind in ('stop', 'policy', 'expression', 'gap'):
            with self.subTest(kind=kind):
                self.operator['motion_policy']['motor_enabled'] = True
                self.replace_native(); proposal = self.proposal()
                def barrier():
                    if kind == 'stop': self.native.stop_requested = lambda: True
                    elif kind == 'policy': self.operator['motion_policy']['motor_enabled'] = False
                    elif kind == 'expression': self.operator['expression_version'] += 1
                    else: self.native.sensor_gap('barrier', self.native.clock())
                sent = self.stock_transport(barrier)
                self.assertTrue(self.native.dispatch(proposal))
                self.wait(lambda: self.native.stock_job.future.done())
                result = self.native.stock_job.future.result()
                self.assertEqual(result['completion'], 'not_dispatched')
                self.assertEqual(sent, [])
                self.assertTrue(self.native.stock_used); self.assertFalse(self.native.dispatch(proposal))

    def test_changed_sensor_observations_after_preconnect_do_not_become_motor_withdrawal(self):
        proposal = self.proposal()
        def barrier(): self.operator.update(listening=False, capture_active=False, phase='paused')
        sent = self.stock_transport(barrier)
        response = SimpleNamespace(status=200, read=lambda _: json.dumps(dict(ok=True, steps_observed=2,
                                  pose_verified=False, hard_stop_certified=False)).encode())
        with patch('http.client.HTTPConnection.getresponse', return_value=response):
            self.assertTrue(self.native.dispatch(proposal)); self.collect_stock()
        self.assertEqual(sum(raw.startswith(b'POST ') for raw in sent), 1)
        self.assertEqual(self.native.stock_receipt['completion'], 'observed')

    def test_partial_header_body_and_lost_response_are_one_attempt_unknown_no_replay(self):
        for kind in ('partial', 'body', 'lost_response'):
            with self.subTest(kind=kind):
                self.replace_native(); proposal = self.proposal(); sent = self.stock_transport()
                def send(raw):
                    sent.append(bytes(raw))
                    if kind == 'partial':
                        self.native.stop_requested = lambda: True
                        return 1
                    if kind == 'body' and bytes(raw).startswith(b'POST '):
                        self.native.stop_requested = lambda: True
                    return len(raw)
                def connect(connection):
                    connection.sock = SimpleNamespace(settimeout=lambda *_: None, close=lambda: None, send=send)
                with patch('http.client.HTTPConnection.connect', connect), \
                     patch('http.client.HTTPConnection.getresponse', side_effect=TimeoutError('lost response')):
                    self.assertTrue(self.native.dispatch(proposal))
                    self.wait(lambda: self.native.stock_job.future.done())
                    # Clear only the test stop callback so the ordinary collector runs.
                    self.native.stop_requested = lambda: False
                    self.native.advance()
                self.assertTrue(self.native.stock_unknown)
                self.assertEqual(self.native.stock_receipt['completion'], 'UNKNOWN')
                self.assertEqual(sum(raw.startswith(b'POST ') for raw in sent), 1)
                self.assertFalse(self.native.dispatch(proposal))

    def test_existing_hub_guards_recheck_both_targets_and_fixed_profile_is_unchanged(self):
        for revoke_before in (1, 2, None):
            with self.subTest(revoke_before=revoke_before):
                self.operator['motion_policy']['motor_enabled'] = True
                self.replace_native(); proposal = self.proposal(); self.writes.clear()
                original_robot = self.hub.robot
                checks = []
                def robot(path, payload=None):
                    if path == '/api/move/goto':
                        checks.append(motor_identity(self.operator))
                        if len(checks) == revoke_before:
                            self.operator['motion_policy']['motor_enabled'] = False
                    return original_robot(path, payload)
                with patch.object(self.hub, 'robot', side_effect=robot), \
                     patch('reachy_companion.autonomous.native_agent.guarded_control', side_effect=self.guarded) as send:
                    self.assertTrue(self.native.dispatch(proposal)); self.collect_stock()
                expected = 2 if revoke_before is None else revoke_before - 1
                self.assertEqual(len(self.writes), expected)
                self.assertEqual(send.call_count, 1)
                if revoke_before is None:
                    steps = [payload for _, payload in self.writes]
                    self.assertEqual([step['duration'] for step in steps], [.5, .5])
                    self.assertEqual([step['head_pose']['roll'] for step in steps], [math.radians(1), 0])
                else: self.assertTrue(self.native.stock_unknown)

    def test_cli_requires_matching_new_arm_and_rejects_service_before_any_client(self):
        from reachy_companion.autonomous import native_agent_session as session
        argv = ['native', '--config', 'unused', '--companion-config', 'unused', '--token-file', 'unused',
                '--output', str(Path(self.tmp.name)/'fresh-report.json'), '--agent-url', 'http://127.0.0.1:8775',
                '--hub-url', 'http://127.0.0.1:8080', '--agent-boot', self.operator['agent_boot_id'],
                '--microphone-epoch', '1', '--policy-epoch', '2', '--controller', 'fixture',
                '--allow-native-observation']
        for flags, config in (([], self.cfg), (['--allow-stock-settle'], self.cfg),
                (['--allow-goal-clock-stock-settle'], load(ROOT/'config.autonomous.native-agent.example.json')),
                (['--service', '--metadata', str(Path(self.tmp.name)/'meta.json'),
                  '--allow-goal-clock-stock-settle'], self.cfg)):
            with self.subTest(flags=flags), patch('sys.argv', argv+flags), \
                 patch.object(session, 'load', return_value=config), patch.object(session, 'NativeClient') as client:
                with self.assertRaises(ValueError): session.main()
                client.assert_not_called()

    def test_explicit_config_arm_and_service_rejections_preserve_r5_default(self):
        validate_lifecycle(self.cfg, allow_stock=True)
        for options in (dict(service=True, duration=None, allow_stock=True), dict(allow_stock=False),
                        dict(allow_stock=True, allow_camera=True)):
            with self.assertRaises(ValueError): validate_lifecycle(self.cfg, **options)
        self.assertNotIn('stock_profile', load(ROOT/'config.autonomous.native-agent.example.json')['native_agent'])
        path = Path(self.tmp.name)/'goal-clock.json'
        for change in ('valid', 'context', 'ttl', 'evidence', 'no_goal'):
            cfg = copy.deepcopy(self.cfg)
            if change == 'context': cfg['context']['enabled'] = True
            elif change == 'ttl': cfg['native_agent']['goal_ttl_s'] = float('inf')
            elif change == 'evidence': cfg['native_agent']['operator_goal']['evidence_ids'] = ['audio-derived']
            elif change == 'no_goal': cfg['native_agent'].pop('operator_goal')
            path.write_text(json.dumps(cfg))
            if change == 'valid': self.assertEqual(load(path), cfg)
            else:
                with self.assertRaises(ValueError): load(path)




# Executes exact R8 Agent methods and A1 pump with the same deterministic
# subprocess PCM writer as R10. Only HTTP/device dependencies are fixtures.
import test_native_stock_rearm_gap as r10
from reachy_companion.autonomous.config import load as load_config
import test_manual_retire_fix as r8


class ExactR8GoalClockTraceTests(unittest.TestCase):
    setUp = r10.NativeStockRearmGapTests.setUp
    @classmethod
    def setUpClass(cls):
        import subprocess
        from types import ModuleType
        r10.NativeStockRearmGapTests.setUpClass.__func__(cls)
        raw = subprocess.check_output(['git', 'show',
            '2865db30e92fcb069c241c34bae4419ad65ed594:src/reachy_companion/microphone.py'], cwd=ROOT)
        if hashlib.sha256(raw).hexdigest() != 'd35ef6d3e0cc289e8043a0da68480ecd110ef3fff98afb81da0afad25e416129':
            raise ValueError('Exact installed microphone dependency required')
        cls.exact_microphone = ModuleType('r13_exact_microphone')
        exec(compile(raw, 'microphone-exact-R8.py', 'exec'), cls.exact_microphone.__dict__)
    reap = r10.NativeStockRearmGapTests.reap
    popen = r10.NativeStockRearmGapTests.popen
    actual = r10.NativeStockRearmGapTests.actual
    pump = r10.NativeStockRearmGapTests.pump

    def test_exact_r8_real_durable_disable_and_owner_aba_never_restore_arm(self):
        import tempfile
        MicrophoneState = self.exact_microphone.MicrophoneState
        from reachy_companion.motion_policy import MotionPolicy
        with tempfile.TemporaryDirectory() as directory:
            for kind in ('STOP_ON', 'mic_owner_ABA', 'policy_owner_ABA', 'quiet_ABA', 'privacy_ABA', 'motor_OFF_ON'):
                with self.subTest(kind=kind), patch('socket.socket', side_effect=AssertionError('No network')):
                    a = self.actual(); r8.operator_fixture(a)
                    a.microphone = MicrophoneState(Path(directory)/(kind+'-mic.json'))
                    a.microphone_epoch = a.microphone.epoch
                    a.motion_policy = MotionPolicy(Path(directory)/(kind+'-policy.json'))
                    policy = dict(motor_enabled=True, quiet=False, privacy_all=False)
                    a.motion_policy.save(policy)
                    initial = a.operator_status()
                    hardware = dict(stock_motion=dict(hub_boot_id='fixture-hub', selected=True, unknown=False,
                        owned_uuid=None), action_running=False, ownership=dict(state='free'),
                        daemon=dict(state='running', error=None, backend_status=dict(ready=True)),
                        robot=dict(control_mode='enabled'))
                    def hub_get(path): return hardware if path == '/status' else a.operator_status()
                    native = GoalClockNativeAgent(SimpleNamespace(get=lambda _: a.status()),
                        SimpleNamespace(get=hub_get), {}, initial, 'fixture-hub', allow_stock=True,
                        goal=copy.deepcopy(GOAL), goal_ttl_s=30)
                    if kind == 'STOP_ON':
                        a.set_microphone(False); a.set_microphone(True, listen=False)
                    elif kind == 'mic_owner_ABA':
                        a.set_microphone(True, listen=False, expected_boot_id=a.agent_boot_id,
                            expected_epoch=a.microphone_epoch, owner_id='foreign')
                        a.set_microphone(True, listen=False, expected_boot_id=a.agent_boot_id,
                            expected_epoch=a.microphone_epoch, expected_owner_id='foreign')
                    elif kind == 'policy_owner_ABA':
                        a.set_motion_policy(dict(policy, expected_boot_id=a.agent_boot_id,
                            expected_epoch=a.motion_policy.snapshot()['epoch'], owner_id='foreign'))
                        a.set_motion_policy(dict(policy, expected_boot_id=a.agent_boot_id,
                            expected_epoch=a.motion_policy.snapshot()['epoch'], expected_owner_id='foreign'))
                    else:
                        field = {'quiet_ABA': 'quiet', 'privacy_ABA': 'privacy_all',
                                 'motor_OFF_ON': 'motor_enabled'}[kind]
                        a.set_motion_policy(dict(policy, **{field: not policy[field]}))
                        a.set_motion_policy(policy)
                    after = a.operator_status()
                    self.assertIsNone(after['microphone_owner_id']); self.assertIsNone(after['motion_policy_owner_id'])
                    self.assertNotEqual(motor_identity(initial), motor_identity(after))
                    with self.assertRaises(ValueError): native.read_motor_receipt()
                    self.assertIsNotNone(native.withdrawn)
                    self.assertFalse(native.stock_allowed(time.monotonic()))
                    # Actual state bytes survived a fresh read/reconstruction.
                    self.assertEqual(MicrophoneState(a.microphone.path).epoch, a.microphone.epoch)
                    self.assertEqual(MotionPolicy(a.motion_policy.path).snapshot(), a.motion_policy.snapshot())

    def test_exact_r10_trace_only_new_goal_clock_proposal_allowed_audio_stays_unknown(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), r8.builder.AFTER)
        for path in ('/pause-bound', '/say', '/ask'):
            with self.subTest(path=path), patch('socket.socket', side_effect=AssertionError('No network')):
                a = self.actual()
                policy = r8.operator_fixture(a)
                _, pump = self.pump(a)
                a._capture_pump = pump
                a._capture_source_generation = 1
                a.voice = Mock(side_effect=AssertionError('No voice/model'))
                reader_waiting, reader_release = threading.Event(), threading.Event()
                closing, close_release = threading.Event(), threading.Event()
                self.addCleanup(reader_release.set)
                self.addCleanup(close_release.set)

                def snapshot():
                    if threading.current_thread() is pump.thread and a.capture_active:
                        reader_waiting.set()
                        if not reader_release.wait(2): raise RuntimeError('Reader gate expired')
                    with a.motion_policy.lock:
                        return dict(policy)
                a.motion_policy.snapshot.side_effect = snapshot
                original_close = pump.close

                def close():
                    self.assertTrue(pump.retired.is_set())
                    self.assertFalse(a.microphone_lock.locked())
                    self.assertFalse(a.motion_policy.lock._is_owned())
                    closing.set()
                    if not close_release.wait(2): raise RuntimeError('Close gate expired')
                    original_close()
                pump.close = close
                pump.start()
                self.assertTrue(reader_waiting.wait(1))
                initial_operator = a.operator_status()
                errors, trace = [], []
                a.config['timeouts']['manual_audio_lock'] = .001
                a.audio_lock.acquire()  # Manual exits busy after the real reap.

                def mutate():
                    try:
                        if path == '/pause-bound':
                            a.set_listening(False, dict(operator_binding=dict(
                                agent_boot_id=a.agent_boot_id, microphone_epoch=a.microphone_epoch,
                                policy_epoch=policy['epoch'], owner_id=None,
                                expires_at_monotonic=time.monotonic()+10)))
                        else:
                            a.manual(path, dict(text='offline fixture'))
                    except Exception as exc:
                        errors.append(str(exc))
                worker = threading.Thread(target=mutate, name='R10-real-mutator')
                armed = [False]; sensor_read = [False]
                proxy = r10.Hub.__new__(r10.Hub)
                proxy.agent = lambda route, **kwargs: a.operator_status()

                def agent_get(route):
                    if route == '/operator': return a.operator_status()
                    self.assertEqual(route, '/status')
                    status = a.status()
                    if armed[0]:
                        sensor_read[0] = True
                        trace.append(dict(leg='Agent/status-before-retire',
                            operator=a.operator_status(), pcm=copy.deepcopy(status['capture_pcm'])))
                    return status

                def hub_get(route):
                    if route == '/status':
                        return dict(stock_motion=dict(hub_boot_id='fixture-hub', selected=True, unknown=False, owned_uuid=None),
                            action_running=False, ownership=dict(state='free'), robot=dict(control_mode='enabled'),
                            daemon=dict(state='running', error=None, backend_status=dict(ready=True)))
                    self.assertEqual(route, '/control/operator')
                    if armed[0] and sensor_read[0]:
                        armed[0] = False
                        worker.start()
                        self.assertTrue(closing.wait(1), errors)  # Actual clear+retire finished.
                        self.assertFalse(a.listening.is_set())
                        a.set_listening(True, {})  # Existing legacy API; no epoch change.
                        self.assertTrue(a.capture_active)  # Real reader still parked.
                        trace.append(dict(leg='Hub/operator-after-resume',
                            operator=a.operator_status(), pcm=copy.deepcopy(a.status()['capture_pcm'])))
                    return proxy.operator_proxy()[0]

                client = SimpleNamespace(get=agent_get)
                native = GoalClockNativeAgent(client, SimpleNamespace(get=hub_get, url='http://127.0.0.1:8080'), {},
                    initial_operator, 'fixture-hub', allow_stock=True, goal=copy.deepcopy(GOAL), goal_ttl_s=30)
                cfg = load_config(ROOT/'config.autonomous.native-agent.example.json')
                cfg['context']['enabled'] = False
                cfg['native_agent'].update(stock_profile='finite_goal_clock', operator_goal=copy.deepcopy(GOAL), goal_ttl_s=30)
                gateway = SimpleNamespace(boot_id='fixture-compute')
                scheduler = NativeScheduler(cfg, gateway, native)
                state = scheduler.state
                try:
                    native.latest = native.read()
                    native.motor_unavailable = False
                    state.observe()
                    binding = state.bind(time.monotonic(), 2)
                    state.apply(CHOICE, binding, time.monotonic())
                    old_proposal = copy.deepcopy(state.stock_proposal)
                    old_fast = state.bind(time.monotonic(), 2)
                    gap_start = time.monotonic()
                    native.sensor_gap('transient-read-gap', gap_start)
                    native.next_poll = float('inf')
                    armed[0] = True
                    recovered = native.read()  # Begins AFTER gap; all real R8 read methods.
                    future = Future(); future.set_result(recovered)
                    native.poll_job = SimpleNamespace(future=future)
                    native.advance()
                    self.assertEqual(native.recoveries, 0)
                    self.assertTrue(native.unavailable)
                    self.assertFalse(native.sensor_continuous)
                    self.assertTrue(native.fresh(time.monotonic()))
                    self.assertEqual(native.generation, 1)
                    self.assertGreaterEqual(recovered['received'], gap_start)
                    self.assertEqual(motor_identity(initial_operator), motor_identity(a.operator_status()))
                    self.assertEqual(initial_operator, recovered['operator'])
                    self.assertEqual(recovered['pcm']['source_generation'], 1)
                    self.assertFalse(trace[0]['pcm']['retired'])
                    self.assertTrue(trace[1]['pcm']['retired'])
                    self.assertEqual(trace[0]['operator'], trace[1]['operator'])
                    # Same R10 trace is a valid motor projection, NEVER a
                    # continuous audio source. Existing proposals/fast stay dead.
                    self.assertTrue(native.physical_closed_after_gap)
                    with patch('reachy_companion.autonomous.native_agent.guarded_control') as send:
                        self.assertFalse(native.dispatch(old_proposal)); send.assert_not_called()
                        state.stock_proposal = None
                        state.apply(CHOICE, old_fast, time.monotonic())
                        self.assertIsNone(state.stock_proposal)
                        self.assertTrue(native.stock_allowed(time.monotonic()))
                        fresh_binding = state.bind(time.monotonic(), 2)
                        state.apply(CHOICE, fresh_binding, time.monotonic())
                        fresh_proposal = state.stock_proposal
                        self.assertTrue(native.admit_stock(fresh_proposal))
                        self.assertNotEqual(fresh_proposal['request_id'], old_proposal['request_id'])
                        # Complete next read sees actual retired pump; MOTOR
                        # remains valid and PCM never masquerades as fresh.
                        later = native.read()
                        self.assertIsNone(later['pcm'])
                        self.assertIsNone(native.withdrawn)
                        self.assertFalse(native.admit_stock(fresh_proposal))
                        # Observing the retirement is another discontinuity;
                        # only a binding created AFTER it may be admitted.
                        fresh_binding = state.bind(time.monotonic(), 2)
                        state.apply(CHOICE, fresh_binding, time.monotonic())
                        fresh_proposal = state.stock_proposal
                        send.return_value = dict(ok=True, steps_observed=2, pose_verified=False, hard_stop_certified=False)
                        self.assertTrue(native.dispatch(fresh_proposal))
                        native.stock_job.thread.join(1)
                        native.advance()
                        self.assertEqual(send.call_count, 1)
                        self.assertTrue(native.stock_used)
                        self.assertFalse(native.dispatch(fresh_proposal))
                        self.assertFalse(native.dispatch(old_proposal))
                        self.assertEqual(native.stock_receipt['completion'], 'observed')
                    scheduler.close()
                finally:
                    armed[0] = False
                    close_release.set(); reader_release.set()
                    if worker.ident is not None: worker.join(3)
                    a.audio_lock.release()
                    pump.close = original_close
                    pump.close()
                self.assertFalse(worker.is_alive())
                self.assertEqual(errors, [] if path == '/pause-bound' else
                    ['Robot is processing a voice turn; try again when idle'])
                a.voice.assert_not_called(); a.request.assert_not_called()



if __name__ == '__main__': unittest.main()
