"""Synthetic concurrency/contract checks; these are not live sensory proof."""
import threading
import time
import unittest

from reachy_companion.sensory_loop import SensoryLoop


class Clock:
    def __init__(self):
        self.now = 100.
    def __call__(self):
        return self.now


def choice(view):
    fresh = [x for x in view['observations'] if x['state'] == 'fresh']
    return (dict(action='attend', why='actual observation', evidence=[fresh[-1]['id']])
            if fresh else dict(action='wait', why='no fresh evidence', evidence=[]))


class SensoryLoopChecks(unittest.TestCase):
    def make(self, decision=None, execute=None, **kwargs):
        self.clock = Clock()
        loop = SensoryLoop(decision or (lambda view, cancel: choice(view)),
                           execute or (lambda proposal, permit: permit()), clock=self.clock, **kwargs)
        self.addCleanup(loop.close)
        loop.set_authority({'boot': 'test', 'microphone_epoch': 1, 'policy_epoch': 2}, enabled=True)
        return loop

    def publish(self, loop, summary='changed scene', *, kind='vision.semantic', source='snapshot-vlm', ttl=10):
        return loop.publish(dict(kind=kind, source=source, observed_monotonic=self.clock(),
                                 summary=summary, ttl_s=ttl, source_event_id='actual-event-contract'))

    def pump_until(self, loop, condition):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            loop.advance()
            if condition():
                return
            time.sleep(.001)
        self.fail('callback did not reach expected terminal state')

    def test_compact_freshness_capacity_and_input_validation(self):
        loop = self.make(sensor_cap=2)
        first = self.publish(loop, ttl=1)
        self.clock.now += 1
        view = loop.snapshot()
        self.assertEqual(view['observations'][0]['state'], 'expired')
        self.assertIsNone(loop.publish(dict(kind='vision.semantic', source='snapshot-vlm',
                                            observed_monotonic=100, summary='old')))
        self.publish(loop, source='second')
        self.publish(loop, source='third')
        self.assertEqual(len(loop.snapshot()['observations']), 2)
        self.assertNotIn(first, [x['id'] for x in loop.snapshot()['observations']])
        for timestamp in (float('nan'), float('inf'), True, self.clock.now+1):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                loop.publish(dict(kind='sound', source='capture', observed_monotonic=timestamp, summary='sound'))
        with self.assertRaises(ValueError):
            self.publish(loop, summary='x'*513)

    def test_one_decision_active_latest_pending_replaces_without_blocking_publish(self):
        entered, release = threading.Event(), threading.Event()
        views, effects = [], []
        def decide(view, cancel):
            views.append(view)
            if len(views) == 1:
                entered.set()
                release.wait(2)
            return choice(view)
        loop = self.make(decide, lambda proposal, permit: effects.append(proposal) or permit())
        self.addCleanup(release.set)
        first = self.publish(loop)
        loop.advance()
        self.assertTrue(entered.wait(1))
        for i in range(100):
            self.clock.now += .001
            newest = self.publish(loop, summary='real source update '+str(i))
            loop.advance()
        view = loop.snapshot()
        self.assertEqual(len(views), 1)
        self.assertEqual(len(view['observations']), 1)
        self.assertTrue(view['busy']['decision'])
        self.assertTrue(view['pending']['decision'])
        self.assertGreater(view['counts']['pending_replaced'], 1)
        release.set()
        self.pump_until(loop, lambda: loop.snapshot()['counts']['completed'] == 1)
        self.assertEqual(len(views), 2)
        self.assertEqual(effects[0]['evidence'], [newest])
        self.assertNotEqual(effects[0]['evidence'], [first])
        self.assertEqual(effects[0]['provenance'][0]['source_event_id'], 'actual-event-contract')

    def test_stop_and_off_revoke_outputs_but_keep_decision_busy_until_exit(self):
        for stop_kind in ('stop', 'off', 'invalidate'):
            with self.subTest(stop_kind=stop_kind):
                entered, release = threading.Event(), threading.Event()
                tokens, effects = [], []
                def decide(view, cancel):
                    tokens.append(cancel)
                    entered.set()
                    release.wait(2)
                    return choice(view)
                loop = self.make(decide, lambda p, permit: effects.append(p) or True)
                self.addCleanup(release.set)
                self.publish(loop)
                loop.advance()
                self.assertTrue(entered.wait(1))
                old_revision = loop.snapshot()['authority_revision']
                if stop_kind == 'off':
                    loop.set_authority({'boot': 'test'}, enabled=False)
                else:
                    getattr(loop, stop_kind)()
                self.assertTrue(tokens[0].is_set())
                self.assertTrue(loop.advance()['busy']['decision'])
                self.assertGreater(loop.snapshot()['authority_revision'], old_revision)
                release.set()
                self.pump_until(loop, lambda: not loop.snapshot()['busy']['decision'])
                self.assertEqual(effects, [])

    def test_slow_execution_does_not_block_sensors_or_decisions_and_keeps_one_pending(self):
        entered, release = threading.Event(), threading.Event()
        executions, gates = [], []
        def execute(proposal, permit):
            executions.append(proposal)
            gates.append(permit)
            if len(executions) == 1:
                entered.set()
                release.wait(2)
            return permit()
        loop = self.make(execute=execute)
        self.addCleanup(release.set)
        self.publish(loop)
        self.pump_until(loop, entered.is_set)
        for i in range(4):
            self.clock.now += .1
            latest = self.publish(loop, summary='sensor '+str(i))
            before = loop.snapshot()['counts']['decision_started']
            self.pump_until(loop, lambda: loop.snapshot()['counts']['decision_started'] > before
                            and not loop.snapshot()['busy']['decision'])
        view = loop.snapshot()
        self.assertEqual(len(executions), 1)
        self.assertTrue(view['busy']['execution'])
        self.assertTrue(view['pending']['execution'])
        self.assertTrue(gates[0].cancelled.is_set())
        self.assertFalse(gates[0]())
        release.set()
        self.pump_until(loop, lambda: loop.snapshot()['counts']['completed'] == 1)
        self.assertEqual(len(executions), 2)
        self.assertEqual(executions[-1]['evidence'], [latest])
        self.assertEqual([x['outcome'] for x in loop.snapshot()['previous_actions']], ['withdrawn', 'completed'])

    def test_deadline_cancellation_is_not_terminal_and_expired_result_never_executes(self):
        entered, release = threading.Event(), threading.Event()
        tokens, effects = [], []
        def decide(view, cancel):
            tokens.append(cancel)
            entered.set()
            release.wait(2)
            return choice(view)
        loop = self.make(decide, lambda p, permit: effects.append(p) or True, decision_timeout_s=1)
        self.addCleanup(release.set)
        self.publish(loop, ttl=.5)
        loop.advance()
        self.assertTrue(entered.wait(1))
        self.clock.now += 2
        self.assertTrue(loop.advance()['busy']['decision'])
        self.assertTrue(tokens[0].is_set())
        release.set()
        self.pump_until(loop, lambda: not loop.snapshot()['busy']['decision'])
        self.assertEqual(effects, [])

    def test_execution_expiry_and_close_signal_permit_without_false_completion(self):
        for close in (False, True):
            with self.subTest(close=close):
                entered, release = threading.Event(), threading.Event()
                gates = []
                def execute(proposal, permit):
                    gates.append(permit)
                    entered.set()
                    release.wait(2)
                    return True  # Even a dishonest/late success cannot validate output.
                loop = self.make(execute=execute)
                self.addCleanup(release.set)
                self.publish(loop, ttl=1)
                self.pump_until(loop, entered.is_set)
                if close:
                    loop.close()
                else:
                    self.clock.now += 2
                self.assertFalse(gates[0]())
                self.assertTrue(loop.advance()['busy']['execution'])
                release.set()
                self.pump_until(loop, lambda: not loop.snapshot()['busy']['execution'])
                self.assertEqual(loop.snapshot()['counts']['completed'], 0)

    def test_wait_and_fabricated_provenance_never_execute(self):
        for result in (dict(action='wait', why='idle', evidence=[]),
                       dict(action='attend', why='invented', evidence=['not-in-view']),
                       dict(action='attend', why='no evidence', evidence=[])):
            effects = []
            loop = self.make(lambda view, cancel: result, lambda p, permit: effects.append(p))
            self.publish(loop)
            loop.advance()
            self.pump_until(loop, lambda: not loop.snapshot()['busy']['decision'])
            self.assertEqual(effects, [])

    def test_privacy_and_callback_failures_are_bounded_and_recoverable(self):
        calls = []
        def decide(view, cancel):
            calls.append(view)
            if len(calls) == 1:
                raise RuntimeError('synthetic failure')
            return choice(view)
        loop = self.make(decide)
        self.publish(loop)
        loop.advance()
        self.pump_until(loop, lambda: loop.snapshot()['counts']['decision_failed'] == 1)
        self.clock.now += 1
        self.publish(loop)
        self.pump_until(loop, lambda: loop.snapshot()['counts']['completed'] == 1)
        loop.set_authority({'boot': 'test'}, enabled=True, privacy=True)
        self.assertIsNone(self.publish(loop))
        self.assertEqual(loop.snapshot()['observations'], [])
        self.assertEqual(loop.snapshot()['previous_actions'], [])
        self.assertFalse(loop.advance()['busy']['decision'])

    def test_off_on_and_authority_change_require_new_observations(self):
        effects = []
        loop = self.make(execute=lambda p, permit: effects.append(p) or permit())
        self.publish(loop)
        loop.stop()
        self.assertEqual(loop.snapshot()['observations'], [])
        loop.set_authority({'boot': 'new', 'microphone_epoch': 3}, enabled=True)
        loop.advance()
        self.pump_until(loop, lambda: not loop.snapshot()['busy']['decision'])
        self.assertEqual(effects, [])
        self.clock.now += 1
        newest = self.publish(loop)
        self.pump_until(loop, lambda: loop.snapshot()['counts']['completed'] == 1)
        self.assertEqual(effects[0]['evidence'], [newest])
        self.assertEqual(effects[0]['authority'], {'boot': 'new', 'microphone_epoch': 3})

    def test_executor_failure_releases_lane_only_at_terminal_and_recovers(self):
        calls = []
        def execute(proposal, permit):
            calls.append(proposal)
            if len(calls) == 1:
                raise RuntimeError('synthetic actuator failure')
            return permit()
        loop = self.make(execute=execute)
        self.publish(loop)
        self.pump_until(loop, lambda: loop.snapshot()['counts']['execution_failed'] == 1)
        self.clock.now += 1
        self.publish(loop)
        self.pump_until(loop, lambda: loop.snapshot()['counts']['completed'] == 1)
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
