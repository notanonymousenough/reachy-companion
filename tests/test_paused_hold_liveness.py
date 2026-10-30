"""R15 exact frozen R8/7a5 bundle + actual R13, fake clock, no I/O.

R15_BUNDLE may point to a relocated review bundle containing candidate/preimages.
Runtime candidates intentionally stay separate from the differently based Agent checkout.
"""
import ast
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, patch

import test_native_goal_clock_stock as r13

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path(os.environ.get('R15_BUNDLE', ROOT/'tests/fixtures/legacy/r15'))
TRACES = []


def player_class(directory):
    raw = (BUNDLE/directory/'expression_player.py').read_bytes()
    module = ModuleType('reachy_companion.r15_expression_fixture')
    module.__package__ = 'reachy_companion'
    exec(compile(raw, str(BUNDLE/directory/'expression_player.py'), 'exec'), module.__dict__)
    return module.ExpressionPlayer


def agent_run(directory):
    tree = ast.parse((BUNDLE/directory/'agent.py').read_bytes())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Agent')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    namespace = {}
    # Execute the entire real method, including its one-second wait and paused branch.
    # No constructor/import stubs can accidentally start audio, HTTP or device threads.
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'exact-R8-Agent.run', 'exec'), namespace)
    return namespace['run']


def make_player(directory='candidate'):
    config = json.loads((ROOT/'config.example.json').read_text())
    config['guarded_motion'].update(enabled=True, transport='stock')
    config['conversation']['expressions']['enabled'] = False
    p = player_class(directory)(config, Mock(side_effect=AssertionError('No expression I/O')),
        threading.Event(), binding=lambda: dict(agent_boot_id='fixture-agent', microphone_epoch=1,
                                               microphone_enabled=False, policy_epoch=2))
    # Enable enqueuing without starting the player worker; run is tested separately.
    p.settings['enabled'] = True
    return p


class PausedHoldTests(unittest.TestCase):
    # Reuse fixture plumbing only; do not inherit/repeat the R13 review suite.
    factory = r13.GoalClockStockTests.factory
    guarded = r13.GoalClockStockTests.guarded
    wait = r13.GoalClockStockTests.wait
    finish = r13.GoalClockStockTests.finish
    pending = staticmethod(r13.GoalClockStockTests.pending)
    replace_native = r13.GoalClockStockTests.replace_native
    accept_poll = r13.GoalClockStockTests.accept_poll
    collect_stock = r13.GoalClockStockTests.collect_stock

    def setUp(self):
        r13.GoalClockStockTests.setUp(self)
        self.now = 100.
        self.operator.update(microphone_enabled=False, listening=False, capture_active=False, phase='paused')
        self.replace_native(clock=lambda: self.now)
        self.accept_poll()  # Initial paused sensor UNKNOWN precedes the model binding.
        self.cfg['fast_deadline_s'] = 6

    def poll(self, player):
        self.operator['expression_version'] = player.version
        self.accept_poll()
        self.scheduler.state.observe()

    def trial(self, directory, choice, on_result=None, scheduled=False):
        player = make_player(directory)
        player.hold()  # Actual durable MicOFF transition, before arm/bind.
        self.poll(player)
        state = self.scheduler.state
        if scheduled:
            jobs = patch('reachy_companion.autonomous.runtime.Job', side_effect=self.pending)
            self.jobs = jobs.start(); self.addCleanup(jobs.stop)
            self.scheduler.advance()
            binding = self.scheduler.binding
            fast = self.scheduler.fast_job
            self.assertIsNotNone(fast)
            self.scheduler.next_tick = float('inf')
        else:
            binding = state.bind(self.now, 6)
        epoch = state.authority.operator_epoch
        stopping = threading.Event()
        waits = []
        applied = []
        outer = self
        class Listening:
            def wait(_, timeout):
                waits.append(timeout)
                for _ in range(10):
                    outer.now = round(outer.now + .1, 6)
                    outer.poll(player)
                    if outer.now == 102.4:
                        if scheduled:
                            fast.future.set_result(dict(output=copy.deepcopy(choice),
                                request_id=binding.request_id, compute_boot_id=outer.gateway.boot_id))
                            outer.scheduler.advance()
                        else:
                            state.apply(copy.deepcopy(choice), binding, outer.now)
                        applied.append(outer.now)
                        if on_result: on_result(player, state.stock_proposal)
                    elif scheduled:
                        outer.scheduler.advance()
                        if outer.now < 102.4:
                            outer.assertIs(outer.scheduler.fast_job, fast)
                if len(waits) == 3: stopping.set()
                return False
        agent = SimpleNamespace(stopping=stopping, listening=Listening(),
            audio_lock=threading.Lock(), microphone=SimpleNamespace(enabled=False),
            phase='paused', expressions=player, _capture_enabled=lambda: False)
        agent_run(directory)(agent)
        self.assertEqual(waits, [1, 1, 1])
        self.assertEqual(applied, [102.4])
        self.assertEqual(binding.deadline, 106.)
        self.assertEqual(self.native.generation, binding.decision_generation)
        self.assertFalse(self.native.sensor_continuous)
        if scheduled: self.assertEqual(self.jobs.call_count, 1)
        proposal = state.stock_proposal
        TRACES.append(dict(source=directory, choice=copy.deepcopy(choice), waits=waits,
            bind_at=100., apply_at=applied[0], model_deadline=binding.deadline,
            epoch_before=epoch, epoch_after=state.authority.operator_epoch,
            expression_version=player.version, decision_generation=self.native.generation,
            counts=dict(state.counts), proposal=copy.deepcopy(proposal),
            effect=copy.deepcopy(self.native.stock_receipt), stock_used=self.native.stock_used,
            physical_motion_verified=False))
        return player, binding, epoch

    def test_exact_preimage_reproduces_stale_wait_at_2_4s(self):
        player, binding, epoch = self.trial('preimages', dict(a='wait', why='Offline fixture wait'))
        self.assertEqual(self.scheduler.state.counts['decision_stale'], 1)
        self.assertEqual(self.scheduler.state.counts['decision_accepted'], 0)
        self.assertGreater(self.scheduler.state.authority.operator_epoch, epoch)
        self.assertLess(102.4, binding.deadline)
        self.assertIsNone(self.scheduler.state.stock_proposal)
        self.assertFalse(self.native.stock_used)
        self.assertEqual(self.writes, [])

    def test_candidate_paused_wait_is_accepted_without_effect_or_motion_forcing(self):
        player, _, epoch = self.trial('candidate', dict(a='wait', why='Offline fixture wait'))
        self.assertEqual(self.scheduler.state.counts['decision_accepted'], 1)
        self.assertEqual(self.scheduler.state.counts['decision_stale'], 0)
        self.assertEqual(self.scheduler.state.authority.operator_epoch, epoch)
        self.assertEqual(player.version, 1)
        self.assertIsNone(self.scheduler.state.stock_proposal)
        self.assertEqual(self.writes, [])
        self.assertFalse(self.native.stock_used)

    def test_actual_scheduler_preimage_rejects_same_occupied_fast_at_2_4s(self):
        self.trial('preimages', dict(a='wait', why='Offline scheduler fixture'), scheduled=True)
        self.assertEqual(self.scheduler.state.counts['decision_stale'], 1)
        self.assertEqual(self.scheduler.state.counts['decision_accepted'], 0)

    def test_actual_scheduler_candidate_accepts_same_occupied_fast_at_2_4s(self):
        self.trial('candidate', dict(a='wait', why='Offline scheduler fixture'), scheduled=True)
        self.assertEqual(self.scheduler.state.counts['decision_accepted'], 1)
        self.assertEqual(self.scheduler.state.counts['decision_stale'], 0)
        self.assertIsNone(self.scheduler.state.stock_proposal)
        self.assertEqual(self.writes, [])

    def test_candidate_settle_proposal_preserves_model_and_effect_deadlines(self):
        _, binding, epoch = self.trial('candidate', r13.CHOICE)
        proposal = self.scheduler.state.stock_proposal
        self.assertEqual(self.scheduler.state.authority.operator_epoch, epoch)
        self.assertEqual(proposal['model_deadline'], binding.deadline)
        self.assertEqual(proposal['receipt_begin'], 102.4)
        self.assertEqual(proposal['deadline'], 102.7)
        # Trial has now reached 103.0 with newer receipts: no deadline renewal.
        with patch('reachy_companion.autonomous.native_agent.guarded_control') as send:
            self.assertFalse(self.native.dispatch(proposal))
            send.assert_not_called()
        self.assertEqual(proposal['deadline'], 102.7)

    def test_real_hold_and_expression_changes_still_stale_before_effect(self):
        for action in ('hold', 'set', 'timeline', 'dance', 'active_maintenance'):
            with self.subTest(action=action):
                self.replace_native(clock=lambda: self.now)
                self.accept_poll()
                p = make_player()
                p.hold()
                if action == 'active_maintenance': p.set('processing')
                self.poll(p)
                state = self.scheduler.state
                binding = state.bind(self.now, 6)
                if action == 'hold': p.hold()
                elif action == 'active_maintenance': p.hold(maintenance=True)
                else: self.enqueue(p, action)
                self.now += .1
                self.poll(p)
                state.apply(r13.CHOICE, binding, self.now)
                self.assertEqual(state.counts['decision_stale'], 1)
                self.assertIsNone(state.stock_proposal)
                self.assertEqual(self.writes, [])

    def enqueue(self, p, kind):
        step = dict(head_pose=dict(x=0., y=0., z=0., roll=0., pitch=0., yaw=0.),
                    antennas=[0., 0.], duration=.5, interpolation='minjerk')
        if kind == 'set': p.set('processing')
        elif kind == 'timeline': p.timeline([dict(at=0., steps=[step])], SimpleNamespace(seconds=lambda: 0.))
        else: p.dance(dict(steps=[step], beat_seconds=.5, next_beat_seconds=0.), 0.)

    def test_idle_maintenance_fences_all_inflight_enqueue_without_expression_churn(self):
        for action in ('set', 'timeline', 'dance'):
            with self.subTest(action=action):
                p = make_player()
                original = p.binding
                def interleave():
                    p.hold(maintenance=True)
                    return original()
                p.binding = interleave
                self.enqueue(p, action)
                self.assertIsNone(p.state)
                self.assertEqual(p.version, 0)
                self.assertEqual(p.cues, [])
                p.binding = original
                self.enqueue(p, action)
                self.assertIsNotNone(p.state)
                self.assertEqual(p.version, 1)

    def test_explicit_idle_hold_remains_unconditional_cancellation_barrier(self):
        p = make_player()
        for n in range(1, 4):
            p.hold()
            self.assertEqual(p.version, n)
        p.hold(maintenance=True)
        self.assertEqual(p.version, 3)

    def effect_transport(self, before_send=None):
        sent = []
        def send(raw):
            sent.append(bytes(raw))
            return len(raw)
        def connect(connection):
            connection.sock = SimpleNamespace(settimeout=lambda *_: None, close=lambda: None, send=send)
        def reread(*args, **kwargs):
            if before_send: before_send()
            return copy.deepcopy(self.operator), self.now
        response = SimpleNamespace(status=200, read=lambda _: json.dumps(dict(ok=True,
            steps_observed=2, pose_verified=False, hard_stop_certified=False)).encode())
        for guard in (patch('http.client.HTTPConnection.connect', connect),
                      patch('http.client.HTTPConnection.getresponse', return_value=response),
                      patch('reachy_companion.autonomous.native_agent._demo_read', side_effect=reread),
                      patch('reachy_companion.autonomous.native_agent.time.monotonic', lambda: self.now)):
            guard.start(); self.addCleanup(guard.stop)
        return sent

    def run_effect(self, proposal):
        self.assertIsNotNone(proposal)
        self.assertTrue(self.native.dispatch(proposal))
        self.native.stock_job.thread.join(1)
        self.assertFalse(self.native.stock_job.thread.is_alive())
        self.native.advance()
        self.assertTrue(self.native.stock_used)
        self.assertFalse(self.native.dispatch(proposal))

    def test_fixture_settle_after_2_4s_reaches_one_socket_attempt_with_original_deadline(self):
        sent = self.effect_transport()
        def effect(player, proposal):
            self.assertEqual(self.now, 102.4)
            self.assertLess(self.now, proposal['receipt_begin'] + .3)
            player.hold(maintenance=True)
            self.operator['expression_version'] = player.version
            self.run_effect(proposal)
            self.assertEqual(self.native.stock_receipt['completion'], 'observed')
            self.assertEqual(proposal['deadline'], 102.7)
        self.trial('candidate', r13.CHOICE, effect)
        self.assertEqual(sum(raw.startswith(b'POST ') for raw in sent), 1)
        # This is a socket-response fixture, not model choice or physical motion evidence.
        self.assertEqual(self.writes, [])

    def test_real_hold_after_proposal_is_rejected_in_effect_preflight(self):
        sent = self.effect_transport()
        def effect(player, proposal):
            player.hold()
            self.operator['expression_version'] = player.version
            self.run_effect(proposal)
            self.assertEqual(self.native.stock_receipt['completion'], 'not_dispatched')
        self.trial('candidate', r13.CHOICE, effect)
        self.assertEqual(sent, [])

    def test_expression_change_after_connect_is_rejected_before_any_send(self):
        player_box = []
        def barrier():
            player_box[0].set('processing')
            self.operator['expression_version'] = player_box[0].version
        sent = self.effect_transport(barrier)
        def effect(player, proposal):
            player_box.append(player)
            self.run_effect(proposal)
            self.assertEqual(self.native.stock_receipt['completion'], 'not_dispatched')
        self.trial('candidate', r13.CHOICE, effect)
        self.assertEqual(sent, [])

    def test_hold_cancels_actual_player_plan_before_action(self):
        for maintenance in (False, True):
            with self.subTest(maintenance=maintenance):
                p = make_player()
                entered = threading.Event()
                release = threading.Event()
                actions = []
                def request(base, path, payload, **kwargs):
                    if path == '/expression/plan':
                        entered.set()
                        if not release.wait(1): raise AssertionError('Plan fixture timeout')
                        return dict(steps=[{}])
                    actions.append(path)
                    raise AssertionError('Canceled plan must not act')
                p.request = request
                p.thread.start()
                try:
                    p.set('processing')
                    self.assertTrue(entered.wait(1))
                    p.hold(maintenance=maintenance)
                    version = p.version
                    release.set()
                    with p.condition:
                        self.assertTrue(p.condition.wait_for(lambda: p.completed >= version, timeout=1))
                    self.assertEqual(actions, [])
                finally:
                    p.stopping.set(); release.set(); p.hold(); p.thread.join(1)
                    self.assertFalse(p.thread.is_alive())

    def test_candidate_bundle_pins_and_only_paused_agent_keyword_changed(self):
        manifest = json.loads((BUNDLE/'source-manifest.json').read_text())
        for name, pin in manifest['payload'].items():
            for directory, key in [('preimages', 'before'), ('candidate', 'after')]:
                raw = (BUNDLE/directory/name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), pin[key])
        agent = (BUNDLE/'candidate/agent.py').read_text()
        self.assertEqual(agent.replace('hold(maintenance=True)', 'hold()'),
                         (BUNDLE/'preimages/agent.py').read_text())



if __name__ == '__main__': unittest.main()
