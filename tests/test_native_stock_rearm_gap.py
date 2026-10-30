"""Exact R8 composite-read counterexample; offline source evidence, no rearm."""
from concurrent.futures import Future
import copy
import hashlib
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_continuous_capture as continuous
import test_manual_retire_fix as r8
from test_agent_live_latency_patch import load
from reachy_companion.autonomous.native_agent import NativeAgent, identity
from reachy_companion.hub import Hub


class NativeStockRearmGapTests(unittest.TestCase):
    receipts = []
    setUp = continuous.ContinuousCaptureTests.setUp
    reap = continuous.ContinuousCaptureTests.reap
    popen = continuous.ContinuousCaptureTests.popen
    actual = continuous.ContinuousCaptureTests.actual
    pump = continuous.ContinuousCaptureTests.pump

    @classmethod
    def setUpClass(cls):
        continuous.ContinuousCaptureTests.setUpClass()
        cls.helper = continuous.ContinuousCaptureTests.helper
        _, cls.raw = r8.builder.candidate()
        cls.module = load(cls.raw.decode())

    def test_status_before_retire_final_operator_after_resume_recovers_on_exact_r8(self):
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
                armed = [False]
                proxy = Hub.__new__(Hub)
                proxy.agent = lambda route, **kwargs: a.operator_status()

                def agent_get(route):
                    if route == '/operator': return a.operator_status()
                    self.assertEqual(route, '/status')
                    status = a.status()
                    if armed[0]:
                        trace.append(dict(leg='Agent/status-before-retire',
                            operator=a.operator_status(), pcm=copy.deepcopy(status['capture_pcm'])))
                    return status

                def hub_get(route):
                    self.assertEqual(route, '/control/operator')
                    if armed[0]:
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
                native = NativeAgent(client, SimpleNamespace(get=hub_get), {},
                                     initial_operator, 'fixture-hub', allow_stock=True)
                try:
                    native.latest = native.read()
                    gap_start = time.monotonic()
                    native.unavailable_since('transient-read-gap', gap_start)
                    native.next_poll = float('inf')
                    armed[0] = True
                    recovered = native.read()  # Begins AFTER gap; all real R8 read methods.
                    future = Future(); future.set_result(recovered)
                    native.poll_job = SimpleNamespace(future=future)
                    native.advance()
                    self.assertEqual(native.recoveries, 1)
                    self.assertFalse(native.unavailable)
                    self.assertTrue(native.fresh(time.monotonic()))
                    self.assertEqual(native.generation, 1)
                    self.assertGreaterEqual(recovered['received'], gap_start)
                    self.assertEqual(identity(initial_operator), identity(a.operator_status()))
                    self.assertEqual(initial_operator, recovered['operator'])
                    self.assertEqual(recovered['pcm']['source_generation'], 1)
                    self.assertFalse(trace[0]['pcm']['retired'])
                    self.assertTrue(trace[1]['pcm']['retired'])
                    self.assertEqual(trace[0]['operator'], trace[1]['operator'])
                    # Existing R5 physical fence is required and remains intact.
                    self.assertTrue(native.physical_closed_after_gap)
                    self.assertFalse(native.stock_allowed(time.monotonic()))
                    with self.assertRaisesRegex(ValueError, 'actual PCM counters required'):
                        native.read()  # A later complete read sees the retirement.
                    self.assertIsNotNone(native.withdrawn)
                    self.receipts.append(dict(case=path, fixture_not_live=True,
                        agent_sha256=hashlib.sha256(self.raw).hexdigest(), trace=trace,
                        recovered=recovered, recoveries=native.recoveries,
                        gap_start=gap_start, recovered_age_s=time.monotonic()-recovered['received'],
                        generation=native.generation, physical_closed_after_gap=True,
                        stock_posts=0, subsequent_read_terminal=True))
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
