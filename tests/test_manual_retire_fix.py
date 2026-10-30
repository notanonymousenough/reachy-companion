"""R8 exact methods + real pipe; scheduling gates only, no network/devices."""
import ast
from concurrent.futures import Future
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_continuous_capture as continuous
import test_bound_listening as bound
from test_agent_live_latency_patch import load

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('r8_builder', ROOT/'deploy/autonomous/prepare_manual_retire.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def operator_fixture(a):
    policy = dict(epoch=3, motor_enabled=True, quiet=False, privacy_all=False)
    a.motion_policy.snapshot.side_effect = lambda: dict(policy)
    a.motion_policy.owned_snapshot.side_effect = lambda: (a.motion_policy.snapshot(), None)
    a.motion_policy.owner_id = None
    a.expressions.version = 1
    a.motion_actor_status = Mock(return_value={})
    a.stream_timing_status = Mock(return_value=None)
    a.vision_route_status = Mock(return_value=None)
    a.last_error = a.last_transcript = a.resume_blocked_reason = None
    a.volume = SimpleNamespace(percent=100)
    return policy


def assert_manual_resume_boundary(case):
    """Same R7 clear/reader barriers; candidate must block then reject retire."""
    from reachy_companion.autonomous.native_agent import NativeAgent, identity
    _, raw = builder.candidate()
    fixed = load(raw.decode())
    for path in ('/say', '/ask'):
        with case.subTest(path=path):
            a = fixed.Agent.__new__(fixed.Agent)
            a.__dict__.update(vars(case.actual()))
            policy = operator_fixture(a)
            _, pump = case.pump(a)
            a._capture_pump = pump
            a._capture_source_generation = 1
            reader_waiting, reader_continue = threading.Event(), threading.Event()
            case.addCleanup(reader_continue.set)
            # Identical R7 phase: reader is in its first actual binding check
            # AFTER capture_active=true, outside the pump condition.
            def snapshot():
                if (threading.current_thread() is pump.thread and a.capture_active
                        and not reader_continue.is_set()):
                    reader_waiting.set()
                    if not reader_continue.wait(2):
                        raise RuntimeError('Reader scheduling gate expired')
                with a.motion_policy.lock:
                    return dict(policy)
            a.motion_policy.snapshot.side_effect = snapshot
            a.voice = Mock(side_effect=AssertionError('No voice/model call'))
            pump.start()
            continuous.wait_for(lambda: a.capture_active)
            case.assertTrue(reader_waiting.wait(1))
            operator = a.operator_status()
            client = SimpleNamespace(get=lambda path: a.status() if path == '/status' else a.operator_status())
            native = NativeAgent(client, client, {}, operator, 'fixture-hub', allow_stock=True)
            native.latest = native.read()
            initial = native.latest
            case.assertTrue(native.stock_allowed(time.monotonic()))
            native.unavailable_since('fixture-observation-gap', time.monotonic())
            native.next_poll = float('inf')

            cleared, release = threading.Event(), threading.Event()
            closing, reap = threading.Event(), threading.Event()
            resume_attempt, read_attempt = threading.Event(), threading.Event()
            resume_done, read_done = threading.Event(), threading.Event()
            class TracedLock:
                def __init__(inner):
                    inner.lock = threading.Lock()
                    inner.owner = None
                def __enter__(inner):
                    if threading.current_thread().name == 'R8-resume': resume_attempt.set()
                    if threading.current_thread().name == 'R8-observer': read_attempt.set()
                    inner.lock.acquire()
                    inner.owner = threading.get_ident()
                    return inner
                def __exit__(inner, *args):
                    inner.owner = None
                    inner.lock.release()
                def locked(inner): return inner.lock.locked()
            a.microphone_lock = TracedLock()
            class PausedClear(threading.Event):
                def clear(inner):
                    super().clear()
                    case.assertTrue(a.microphone_lock.locked())
                    case.assertTrue(a.motion_policy.lock._is_owned())
                    cleared.set()
                    if not release.wait(2): raise RuntimeError('Manual scheduling gate expired')
            a.listening = PausedClear(); a.listening.set()
            original_close = pump.close
            def close():
                case.assertNotEqual(a.microphone_lock.owner, threading.get_ident())
                case.assertFalse(a.motion_policy.lock._is_owned())
                case.assertTrue(pump.retired.is_set())
                closing.set()
                if not reap.wait(2): raise RuntimeError('Reap scheduling gate expired')
                original_close()
            pump.close = close
            errors, read_errors, receipts = [], [], []
            def manual():
                try: a.manual(path, dict(text='offline fixture'))
                except Exception as exc: errors.append(exc)
            def resume():
                try: a.set_listening(True, {})
                except Exception as exc: errors.append(exc)
                finally: resume_done.set()
            def observe():
                try: receipts.append(native.read())
                except Exception as exc: read_errors.append(exc)
                finally: read_done.set()
            worker = threading.Thread(target=manual, name='R8-manual')
            resumer = threading.Thread(target=resume, name='R8-resume')
            observer = threading.Thread(target=observe, name='R8-observer')
            a.config['timeouts']['manual_audio_lock'] = .001
            a.audio_lock.acquire()
            try:
                worker.start()
                case.assertTrue(cleared.wait(1))
                case.assertFalse(a.listening.is_set())
                case.assertFalse(pump.retired.is_set())
                # Unlike R7, neither resume nor a complete typed operator read
                # can pass the same clear boundary: both attempt the held lock.
                resumer.start(); observer.start()
                case.assertTrue(resume_attempt.wait(1)); case.assertTrue(read_attempt.wait(1))
                case.assertFalse(resume_done.is_set()); case.assertFalse(read_done.is_set())
                release.set()
                case.assertTrue(closing.wait(1))
                case.assertTrue(resume_done.wait(1)); case.assertTrue(read_done.wait(1))
                case.assertTrue(a.listening.is_set())
                case.assertTrue(a.capture_active)  # Reader remains parked, as in R7.
                case.assertTrue(pump.retired.is_set())
                case.assertEqual(identity(a.operator_status()), identity(operator))
                case.assertEqual(receipts, [])
                case.assertEqual(len(read_errors), 1)
                case.assertIsInstance(read_errors[0], ValueError)
                case.assertIsNotNone(native.withdrawn)
                case.assertEqual(native.recoveries, 0)
                case.assertFalse(native.fresh(time.monotonic()))
                # Force the strongest R7 observation even if the first racing
                # reader saw listening=false: resume has now completed, phase
                # and capture remain active, but actual status exposes retire.
                retired_status = a.status()
                case.assertTrue(retired_status['listening'])
                case.assertTrue(retired_status['capture_active'])
                case.assertEqual(retired_status['phase'], initial['phase'])
                with case.assertRaisesRegex(ValueError, 'A1 actual PCM counters required'):
                    native.read()
                # Same existing pipe still receives bytes and reader is allowed
                # to continue only AFTER resume. Retire survives that real check.
                case.send(20, .005)
                reader_continue.set()
                pump.thread.join(2)
                case.assertFalse(pump.thread.is_alive())
                case.assertFalse(a.capture_active)
                case.assertFalse(pump.permitted())
                drained = pump.snapshot()
                case.assertEqual(drained['source_generation'], 1)
                case.assertGreater(drained['read_bytes'], initial['pcm']['read_bytes'])
                case.assertEqual(drained['chunks'], 0)
                case.assertEqual(drained['pending_events'], 0)
                # Even an old completed successful receipt cannot recover now.
                future = Future(); future.set_result(initial)
                native.poll_job = SimpleNamespace(future=future)
                native.advance()
                case.assertEqual(native.recoveries, 0)
                case.assertTrue(native.physical_closed_after_gap)
                case.assertFalse(native.stock_allowed(time.monotonic()))
            finally:
                reader_continue.set(); release.set(); reap.set()
                for thread in (worker, resumer, observer):
                    if thread.ident is not None: thread.join(3)
                a.audio_lock.release()
                pump.close = original_close
            case.assertFalse(any(t.is_alive() for t in (worker, resumer, observer)))
            case.assertEqual([str(e) for e in errors], ['Robot is processing a voice turn; try again when idle'])
            case.assertTrue(a.listening.is_set())
            case.assertEqual(a.microphone_epoch, 1)
            a.voice.assert_not_called(); a.request.assert_not_called()
            # The real resume/get path may open a replacement only after reap;
            # it has new source identity, never same-generation recovery.
            original = case.helper.CapturePump
            with patch.object(case.helper, 'CapturePump', side_effect=lambda agent, generation:
                    original(agent, generation, popen=case.popen)):
                replacement = a._capture_get()
            case.addCleanup(replacement.close)
            continuous.wait_for(lambda: a.capture_active)
            case.assertEqual(replacement.generation, 2)
            case.assertIsNotNone(case.children[-2].poll())
            with case.assertRaisesRegex(ValueError, 'source changed'):
                native.read()
            case.assertEqual(native.recoveries, 0)
            case.assertFalse(native.stock_allowed(time.monotonic()))
            replacement.close()
            case.receipts.append(dict(case='R8-legacy-manual-atomic-retire', path=path,
                initial=initial, blocked_at_clear=['resume', 'operator'],
                read_error=str(read_errors[0]), recoveries=native.recoveries,
                active_retired_pcm=retired_status['capture_pcm'], pcm=pump.snapshot(),
                replacement_pcm=replacement.snapshot(), final_listening=a.listening.is_set(),
                final_capture_active=a.capture_active, physical_closed_after_gap=native.physical_closed_after_gap))


class ManualRetireFixTests(unittest.TestCase):
    receipts = []
    setUp = continuous.ContinuousCaptureTests.setUp
    reap = continuous.ContinuousCaptureTests.reap
    popen = continuous.ContinuousCaptureTests.popen
    send = continuous.ContinuousCaptureTests.send
    actual = continuous.ContinuousCaptureTests.actual
    pump = continuous.ContinuousCaptureTests.pump

    @classmethod
    def setUpClass(cls):
        continuous.ContinuousCaptureTests.setUpClass()
        cls.helper = continuous.ContinuousCaptureTests.helper
        cls.before, cls.output = builder.candidate()
        cls.module = load(cls.output.decode())

    def test_exact_builder_changes_only_manual_and_keeps_A1_pump(self):
        def outside(raw):
            tree = ast.parse(raw)
            agent = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Agent')
            agent.body = [n for n in agent.body if getattr(n, 'name', None) != 'manual']
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(outside(self.before), outside(self.output))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'bundle'
            manifest = builder.build(target)
            self.assertEqual(builder.digest((target/'agent.py').read_bytes()), builder.AFTER)
            self.assertEqual(builder.digest((target/'agent-A1-preimage.py').read_bytes()), builder.BEFORE)
            self.assertFalse(manifest['physical_rearm'])
            self.assertEqual(manifest['required_unchanged']['capture_pump.py'], builder.PUMP)
            with self.assertRaises(FileExistsError): builder.build(target)

    def test_manual_normal_error_and_lock_failure_preserve_restoration(self):
        for path in ('/say', '/ask'):
            for listening in (False, True):
                for outcome in ('ok', 'error', 'busy'):
                    with self.subTest(path=path, listening=listening, outcome=outcome):
                        a = self.actual(); operator_fixture(a)
                        if not listening: a.listening.clear()
                        _, pump = self.pump(a)
                        a._capture_pump = pump
                        if listening:
                            pump.start(); continuous.wait_for(lambda: a.capture_active)
                        original_close = pump.close
                        def close():
                            self.assertFalse(a.microphone_lock.locked())
                            self.assertFalse(a.motion_policy.lock._is_owned())
                            self.assertTrue(pump.retired.is_set())
                            original_close()
                        pump.close = close
                        def voice(route, payload, **options):
                            self.assertTrue(pump.retired.is_set())
                            self.assertFalse(a.capture_active)
                            self.assertEqual(route, '/text' if path == '/ask' else '/say')
                            self.assertEqual(payload, dict(text='fixture', session=a.config['conversation']['session']))
                            self.assertEqual(options, dict(allow_barge_in=listening))
                            if outcome == 'error': raise ValueError('manual fixture error')
                            return dict(ok=True, reply='fixture reply', audio_base64='filtered')
                        a.voice = Mock(side_effect=voice)
                        restored = []
                        original_set = a.listening.set
                        def checked_set():
                            self.assertTrue(a.microphone_lock.locked())
                            self.assertTrue(a.motion_policy.lock._is_owned())
                            restored.append(True)
                            original_set()
                        a.listening.set = checked_set
                        a.config['timeouts']['manual_audio_lock'] = .001
                        if outcome == 'busy': a.audio_lock.acquire()
                        try:
                            if outcome == 'busy':
                                with self.assertRaisesRegex(RuntimeError, 'processing a voice turn'):
                                    a.manual(path, dict(text='fixture'))
                                a.voice.assert_not_called()
                            elif outcome == 'error':
                                with self.assertRaisesRegex(ValueError, 'manual fixture error'):
                                    a.manual(path, dict(text='fixture'))
                            else:
                                self.assertEqual(a.manual(path, dict(text='fixture')), dict(ok=True, reply='fixture reply'))
                            self.assertEqual(a.listening.is_set(), listening)
                            self.assertTrue(pump.retired.is_set())
                            self.assertFalse(a.capture_active)
                            self.assertEqual(len(restored), int(listening))
                        finally:
                            if outcome == 'busy': a.audio_lock.release()
                        self.assertFalse(a.audio_lock.locked())

    def test_unknown_reap_during_manual_preserves_owner_and_refuses_second_child(self):
        for path in ('/say', '/ask'):
            with self.subTest(path=path):
                a = self.actual(); operator_fixture(a)
                read_fd, write_fd = os.pipe(); os.close(write_fd)
                process = Mock(stdout=os.fdopen(read_fd, 'rb', buffering=0))
                self.addCleanup(process.stdout.close)
                process.poll.return_value = None
                process.wait.side_effect = subprocess.TimeoutExpired('fixture', .01)
                factory = Mock(return_value=process)
                pump = self.helper.CapturePump(a, 1, popen=factory)
                a._capture_pump = pump
                pump._read()  # Existing unknown-reap fixture; no actual child.
                self.assertEqual(pump.error, 'Capture reap unavailable')
                a.voice = Mock()
                with self.assertRaisesRegex(RuntimeError, 'Capture process still owned'):
                    a.manual(path, dict(text='fixture'))
                self.assertIs(pump.process, process)
                self.assertTrue(a.capture_active)
                self.assertFalse(a.listening.is_set())
                self.assertFalse(a.audio_lock.locked())
                with self.assertRaises(RuntimeError): a._capture_get()
                factory.assert_called_once()
                a.voice.assert_not_called(); a.request.assert_not_called()

    def test_STOP_privacy_quiet_and_shutdown_during_manual_never_restore(self):
        for path in ('/say', '/ask'):
            for outcome in ('ok', 'error', 'busy'):
                for withdrawal in ('STOP', 'privacy', 'quiet', 'shutdown'):
                    with self.subTest(path=path, outcome=outcome, withdrawal=withdrawal):
                        a = self.actual(); policy = operator_fixture(a)
                        _, pump = self.pump(a)
                        a._capture_pump = pump
                        pump.start(); continuous.wait_for(lambda: a.capture_active)
                        entered, release = threading.Event(), threading.Event()
                        # Gate the existing acquire boundary for lock failure;
                        # gate the voice callback for normal/error finally.
                        lock = a.audio_lock
                        class AudioLock:
                            def acquire(inner, **kwargs):
                                if outcome == 'busy':
                                    entered.set()
                                    if not release.wait(2): raise RuntimeError('Acquire gate expired')
                                    return False
                                return lock.acquire(**kwargs)
                            def release(inner): lock.release()
                        a.audio_lock = AudioLock()
                        def voice(*args, **kwargs):
                            entered.set()
                            if not release.wait(2): raise RuntimeError('Voice gate expired')
                            if outcome == 'error': raise ValueError('manual fixture error')
                            return dict(ok=True)
                        a.voice = Mock(side_effect=voice)
                        errors = []
                        def manual():
                            try: a.manual(path, dict(text='fixture'))
                            except Exception as exc: errors.append(exc)
                        worker = threading.Thread(target=manual)
                        worker.start()
                        try:
                            self.assertTrue(entered.wait(2))
                            self.assertTrue(pump.retired.is_set())
                            self.assertFalse(a.capture_active)
                            if withdrawal == 'STOP':
                                a.set_microphone(False)
                            elif withdrawal == 'shutdown':
                                a.stopping.set()
                            else:
                                def save(value):
                                    with a.motion_policy.lock:
                                        policy.update(value); policy['epoch'] += 1
                                        return dict(policy)
                                a.motion_policy.save.side_effect = save
                                a.set_motion_policy({('privacy_all' if withdrawal == 'privacy' else 'quiet'): True})
                            release.set(); worker.join(2)
                            self.assertFalse(worker.is_alive())
                            self.assertFalse(a.listening.is_set())
                            self.assertFalse(a.capture_active)
                            self.assertFalse(pump.permitted())
                            self.assertEqual(len(errors), int(outcome != 'ok'))
                            self.assertEqual(len(self.children), 1)
                            self.assertIsNotNone(self.children[0].poll())
                            self.assertFalse(lock.locked())
                        finally:
                            release.set(); worker.join(3)
                        # Each subcase has an independent process inventory.
                        self.reap(); self.children.clear()


class CandidateBoundListeningTests(bound.BoundListeningTests):
    @classmethod
    def setUpClass(cls):
        _, raw = builder.candidate()
        cls.module = load(raw.decode())
        cls.source = raw.decode()


if __name__ == '__main__':
    unittest.main()
