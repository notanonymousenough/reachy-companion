"""R11 exact full Agent methods, durable microphone and real PCM pipe; offline."""
import ast
from concurrent.futures import Future
import copy
import hashlib
import importlib.util
import json
import io
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_continuous_capture as continuous
import test_manual_retire_fix as r8
import test_bound_listening as bound
from test_agent_live_latency_patch import load
from reachy_companion.autonomous.native_agent import NativeAgent, identity
from reachy_companion.hub import Hub

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('r11_builder', ROOT/'deploy/autonomous/prepare_retirement_authority.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class RetirementAuthorityTests(unittest.TestCase):
    receipts = []
    setUp = continuous.ContinuousCaptureTests.setUp
    reap = continuous.ContinuousCaptureTests.reap
    popen = continuous.ContinuousCaptureTests.popen
    send = continuous.ContinuousCaptureTests.send
    pump = continuous.ContinuousCaptureTests.pump

    @classmethod
    def setUpClass(cls):
        continuous.ContinuousCaptureTests.setUpClass()
        cls.helper = continuous.ContinuousCaptureTests.helper
        cls.before, cls.raw = builder.candidate()
        cls.module = load(cls.raw.decode())
        mic = subprocess.check_output(['git', 'show',
            '2865db30e92fcb069c241c34bae4419ad65ed594:src/reachy_companion/microphone.py'], cwd=ROOT)
        assert hashlib.sha256(mic).hexdigest() == 'd35ef6d3e0cc289e8043a0da68480ecd110ef3fff98afb81da0afad25e416129'
        cls.mic = ModuleType('r11_exact_microphone')
        exec(compile(mic, 'microphone-exact.py', 'exec'), cls.mic.__dict__)

    def actual(self):
        a = continuous.ContinuousCaptureTests.actual(self)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)/'microphone.json'
        path.write_text(json.dumps(dict(enabled=True, epoch=a.microphone_epoch)))
        a.microphone = self.mic.MicrophoneState(path)
        r8.operator_fixture(a)
        return a

    def binding(self, a):
        return dict(operator_binding=dict(agent_boot_id=a.agent_boot_id, microphone_epoch=a.microphone_epoch,
            policy_epoch=a.motion_policy.snapshot()['epoch'], owner_id=a.microphone_owner_id,
            expires_at_monotonic=time.monotonic()+10))

    def test_R10_composite_receipt_rejects_retirement_for_pause_say_ask(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), builder.AFTER)
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
                    with self.assertRaisesRegex(ValueError, 'authority/listening withdrawn') as rejected:
                        native.read()  # BEGIN after gap, status before retire, final Hub operator after resume.
                    self.assertIsNotNone(native.withdrawn)
                    self.assertEqual(native.recoveries, 0)
                    self.assertTrue(native.unavailable)
                    self.assertFalse(native.fresh(time.monotonic()))
                    self.assertNotEqual(identity(initial_operator), identity(a.operator_status()))
                    self.assertEqual(a.microphone_epoch, initial_operator['microphone_epoch']+1)
                    self.assertFalse(trace[0]['pcm']['retired'])
                    self.assertTrue(trace[1]['pcm']['retired'])
                    self.assertEqual(trace[0]['pcm']['source_generation'], trace[1]['pcm']['source_generation'])
                    self.assertNotEqual(trace[0]['operator'], trace[1]['operator'])
                    self.assertTrue(native.physical_closed_after_gap)
                    self.assertFalse(native.stock_allowed(time.monotonic()))
                    # An already completed old result cannot undo terminal revoke.
                    future = Future(); future.set_result(native.latest)
                    native.poll_job = SimpleNamespace(future=future)
                    native.advance()
                    self.assertEqual(native.recoveries, 0)
                    self.receipts.append(dict(case=path, fixture_not_live=True,
                        agent_sha256=hashlib.sha256(self.raw).hexdigest(), trace=trace,
                        rejected=str(rejected.exception), recoveries=native.recoveries,
                        physical_closed_after_gap=True, stock_posts=0))
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


    def test_exact_build_only_three_methods_and_private_receipt_change(self):
        def outside(raw):
            tree = ast.parse(raw)
            agent = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Agent')
            agent.body = [n for n in agent.body if getattr(n, 'name', None) not in
                ('set_microphone', 'set_listening', '_set_listening', 'manual')]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(outside(self.before), outside(self.raw))
        with tempfile.TemporaryDirectory() as root:
            target = Path(root)/'bundle'
            manifest = builder.build(target)
            self.assertEqual(builder.digest((target/'agent.py').read_bytes()), builder.AFTER)
            self.assertEqual(builder.digest((target/'agent-R8-preimage.py').read_bytes()), builder.BEFORE)
            self.assertFalse(manifest['physical_rearm'])
            with self.assertRaises(FileExistsError): builder.build(target)
            patchfile = str(ROOT/'deploy/patches'/builder.PATCH)
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-R', '-i', patchfile],
                cwd=target, check=True, capture_output=True)
            self.assertEqual((target/'agent.py').read_bytes(), self.before)
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', patchfile],
                cwd=target, check=True, capture_output=True)
            self.assertEqual((target/'agent.py').read_bytes(), self.raw)

    def live_pump(self, a):
        _, pump = self.pump(a)
        a._capture_pump = pump
        a._capture_source_generation = 1
        pump.start()
        continuous.wait_for(lambda: a.capture_active)
        return pump

    def durable(self, a):
        return self.mic.MicrophoneState(a.microphone.path)

    def test_first_retirement_persists_under_both_locks_preserves_enabled_and_owner(self):
        for owner in (None, 'owner'):
            with self.subTest(owner=owner):
                a = self.actual()
                a.microphone_owner_id = a.motion_policy.owner_id = owner
                a.motion_policy.owned_snapshot.side_effect = lambda: (a.motion_policy.snapshot(), a.motion_policy.owner_id)
                pump = self.live_pump(a)
                old = self.binding(a)
                saving, synced = [], []
                original_save = a.microphone.save
                def save(enabled):
                    self.assertTrue(a.microphone_lock.locked())
                    self.assertTrue(a.motion_policy.lock._is_owned())
                    self.assertFalse(a.listening.is_set())
                    self.assertTrue(pump.retired.is_set())
                    saving.append(enabled)
                    return original_save(enabled)
                a.microphone.save = save
                original_close = pump.close
                def close():
                    self.assertFalse(a.microphone_lock.locked())
                    self.assertFalse(a.motion_policy.lock._is_owned())
                    original_close()
                pump.close = close
                original_sync = self.mic.os.fsync
                def sync(fd):
                    synced.append(fd)
                    return original_sync(fd)
                with patch.object(self.mic.os, 'fsync', side_effect=sync):
                    self.assertEqual(a.set_listening(False, old), dict(ok=True, listening=False))
                self.assertEqual(len(synced), 2)
                self.assertEqual(saving, [True])
                self.assertEqual((a.microphone_epoch, a.microphone.epoch, self.durable(a).epoch), (2, 2, 2))
                self.assertTrue(a.microphone.enabled)
                self.assertTrue(self.durable(a).enabled)
                self.assertEqual(a.microphone_owner_id, owner)
                self.assertFalse(a.capture_active)
                self.assertIsNotNone(self.children[-1].poll())
                # Refresh CAS after active pause, then bound manual is no-op:
                # no additional epoch/save, and no stale resume bypass.
                a.phase = 'paused'
                with self.assertRaisesRegex(RuntimeError, 'operator or snapshot changed'):
                    a.set_listening(True, old)
                a.voice = Mock(return_value=dict(ok=True))
                fresh = self.binding(a)
                self.assertTrue(a.manual('/say', dict(text='fixture', **fresh))['ok'])
                self.assertFalse(a.listening.is_set())
                self.assertEqual(a.microphone_epoch, 2)
                self.assertEqual(saving, [True])
                self.assertTrue(a.set_listening(True, fresh)['listening'])
                with self.assertRaisesRegex(RuntimeError, 'Speech operator or snapshot changed'):
                    a.manual('/say', dict(text='fixture', **old))
                self.assertEqual(a.voice.call_count, 1)
                original = self.helper.CapturePump
                with patch.object(self.helper, 'CapturePump', side_effect=lambda agent, generation:
                        original(agent, generation, popen=self.popen)):
                    replacement = a._capture_get()
                self.addCleanup(replacement.close)
                continuous.wait_for(lambda: a.capture_active)
                self.assertEqual(replacement.generation, 2)
                self.assertFalse(replacement.retired.is_set())
                replacement.close()
                self.reap(); self.children.clear()

    def test_already_paused_bound_manual_does_not_advance_even_unretired_inactive_source(self):
        a = self.actual()
        a.listening.clear()
        a.phase = 'paused'
        _, pump = self.pump(a)
        a._capture_pump = pump  # Inactive source object, not a live reader.
        a.voice = Mock(return_value=dict(ok=True))
        self.assertFalse(pump.retired.is_set())
        binding = self.binding(a)
        self.assertTrue(a.manual('/say', dict(text='fixture', **binding))['ok'])
        self.assertEqual((a.microphone_epoch, a.microphone.epoch, self.durable(a).epoch), (1, 1, 1))
        self.assertTrue(pump.retired.is_set())
        self.assertFalse(a.listening.is_set())
        self.assertEqual(self.children, [])

    def test_OFF_has_one_transition_pause_does_not_increment_again_and_stale_CAS_cannot_write(self):
        a = self.actual()
        pump = self.live_pump(a)
        a.microphone_owner_id = 'owner'
        a.set_microphone(False, expected_boot_id=a.agent_boot_id, expected_epoch=1,
            owner_id='owner', expected_owner_id='owner')
        self.assertEqual((a.microphone_epoch, a.microphone.epoch), (2, 2))
        a.set_listening(False, {})
        self.assertEqual((a.microphone_epoch, a.microphone.epoch), (2, 2))
        with self.assertRaisesRegex(RuntimeError, 'Microphone authority changed'):
            a.set_microphone(True, expected_boot_id=a.agent_boot_id, expected_epoch=1)
        self.assertFalse(a.listening.is_set())
        self.assertFalse(a.microphone.enabled)
        self.assertTrue(pump.retired.is_set())
        self.assertEqual(a.microphone_owner_id, 'owner')
        self.assertEqual(len(self.children), 1)
        self.assertIsNotNone(self.children[0].poll())

    def test_file_or_directory_fsync_failure_stays_closed_and_never_rolls_back(self):
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at):
                a = self.actual()
                pump = self.live_pump(a)
                a.microphone_owner_id = 'owner'
                a.voice = Mock()
                a.pending_pcm = a.resume_audio = b'fixture'
                calls = []
                original_sync = self.mic.os.fsync
                def fsync(fd):
                    calls.append(fd)
                    if len(calls) == fail_at: raise OSError('fixture fsync failure')
                    return original_sync(fd)
                with patch.object(self.mic.os, 'fsync', side_effect=fsync):
                    with self.assertRaisesRegex(OSError, 'fsync failure'):
                        a.manual('/say', dict(text='fixture'))
                self.assertEqual(a.microphone_epoch, 2)
                self.assertEqual(a.microphone.epoch, 2)
                self.assertFalse(a.microphone.enabled)
                self.assertIn('fsync failure', a.microphone.error)
                self.assertEqual(a.microphone_owner_id, 'owner')
                self.assertFalse(a.listening.is_set())
                self.assertFalse(a.capture_active)
                self.assertTrue(pump.retired.is_set())
                self.assertFalse(pump.permitted())
                self.assertIsNone(a.pending_pcm)
                self.assertIsNone(a.resume_audio)
                a.voice.assert_not_called()
                a.stop_speaker.assert_called()
                self.assertIsNotNone(self.children[-1].poll())
                self.assertEqual(list(a.microphone.path.parent.glob('*.tmp')), [])
                # File fsync failed before replace; directory failure is unknown
                # durability. Neither receipt licenses restoring an ON preimage.
                self.assertEqual(self.durable(a).epoch, 1 if fail_at == 1 else 2)
                with self.assertRaises(RuntimeError): a.set_listening(True, {})
                a.set_listening(False, {})
                self.assertEqual(a.microphone_epoch, 2)
                self.reap(); self.children.clear()

    def test_last_epoch_and_exhaustion_for_pause_and_microphone_never_wrap(self):
        maximum = 2**63-1
        for route in ('pause', 'microphone'):
            with self.subTest(route=route):
                a = self.actual()
                a.microphone_epoch = a.microphone.epoch = maximum-1
                pump = self.live_pump(a)
                if route == 'pause': a.set_listening(False, {})
                else: a.set_microphone(True, listen=False)
                self.assertEqual((a.microphone_epoch, a.microphone.epoch, self.durable(a).epoch),
                    (maximum, maximum, maximum))
                a.set_listening(False, {})  # Retired no-op even at max.
                self.assertEqual(a.microphone_epoch, maximum)
                a.listening.set()
                # A fresh source is allowed to open; its first withdrawal must
                # fail closed at exhaustion, without wrapping the authority.
                original = self.helper.CapturePump
                with patch.object(self.helper, 'CapturePump', side_effect=lambda agent, generation:
                        original(agent, generation, popen=self.popen)):
                    replacement = a._capture_get()
                self.addCleanup(replacement.close)
                continuous.wait_for(lambda: a.capture_active)
                with self.assertRaisesRegex(ValueError, 'epoch exhausted'):
                    if route == 'pause': a.set_listening(False, {})
                    else: a.set_microphone(True)
                self.assertEqual((a.microphone_epoch, a.microphone.epoch), (maximum, maximum))
                self.assertFalse(a.microphone.enabled)
                self.assertFalse(a.listening.is_set())
                self.assertFalse(a.capture_active)
                self.assertTrue(replacement.retired.is_set())
                self.assertIn('epoch exhausted', a.microphone.error)
                self.assertTrue(all(child.poll() is not None for child in self.children))
                self.reap(); self.children.clear()

    def test_actual_late_voice_response_and_roundtrip_revocation_never_output_or_restore(self):
        from reachy_companion.motion_policy import MotionPolicy
        for path in ('/say', '/ask'):
            for withdrawal in ('STOP', 'STOP-ON', 'mic-owner-roundtrip', 'privacy-roundtrip', 'policy-owner-roundtrip', 'quiet', 'shutdown'):
                with self.subTest(path=path, withdrawal=withdrawal):
                    a = self.actual()
                    a.motion_policy = MotionPolicy(a.microphone.path.parent/'policy.json')
                    a.motion_policy.save(dict(motor_enabled=False, quiet=False, privacy_all=False))
                    pump = self.live_pump(a)
                    class Config(dict): token = 'fixture'
                    a.config = Config(a.config)
                    entered, release = threading.Event(), threading.Event()
                    a.play = Mock(side_effect=AssertionError('No playback after revoke'))
                    class Response(io.BytesIO):
                        headers = SimpleNamespace(get_content_type=lambda: 'application/x-ndjson')
                        def readline(inner, *args):
                            entered.set()
                            if not release.wait(2): raise RuntimeError('Voice gate expired')
                            return super().readline(*args)
                    a.http = Mock()
                    a.http.open.side_effect = lambda *args, **kwargs: Response(
                        b'{"type":"reply","reply":"fixture"}\n')
                    errors, results = [], []
                    def manual():
                        try: results.append(a.manual(path, dict(text='fixture')))
                        except Exception as exc: errors.append(str(exc))
                    worker = threading.Thread(target=manual)
                    no_output = patch.object(self.module.subprocess, 'Popen', side_effect=AssertionError('No playback after revoke'))
                    no_output.start()
                    worker.start()
                    try:
                        self.assertTrue(entered.wait(1), errors)
                        self.assertTrue(pump.retired.is_set())
                        self.assertFalse(a.capture_active)
                        if withdrawal in ('STOP', 'STOP-ON', 'mic-owner-roundtrip'):
                            if withdrawal == 'mic-owner-roundtrip':
                                a.set_microphone(True, listen=False, expected_boot_id=a.agent_boot_id,
                                    expected_epoch=a.microphone_epoch, owner_id='temporary')
                                a.set_microphone(True, listen=False)
                            else:
                                a.set_microphone(False)
                                if withdrawal == 'STOP-ON': a.set_microphone(True, listen=False)
                        elif withdrawal == 'shutdown': a.stopping.set()
                        else:
                            fields = dict(motor_enabled=False, quiet=withdrawal == 'quiet', privacy_all=withdrawal == 'privacy-roundtrip')
                            if withdrawal == 'policy-owner-roundtrip':
                                a.set_motion_policy(dict(fields, expected_boot_id=a.agent_boot_id,
                                    expected_epoch=a.motion_policy.snapshot()['epoch'], owner_id='temporary'))
                            else: a.set_motion_policy(fields)
                            if withdrawal in ('privacy-roundtrip', 'policy-owner-roundtrip'):
                                a.set_motion_policy(dict(motor_enabled=False, quiet=False, privacy_all=False))
                        release.set(); worker.join(2)
                        self.assertFalse(worker.is_alive())
                        self.assertEqual(errors, [])
                        self.assertTrue(results[0]['cancelled'])
                        self.assertFalse(a.listening.is_set())
                        self.assertFalse(a.capture_active)
                        a.play.assert_not_called()
                        self.assertEqual(len(self.children), 1)
                        self.assertIsNotNone(self.children[0].poll())
                    finally:
                        release.set(); worker.join(3)
                        no_output.stop()
                        self.reap(); self.children.clear()

    def test_revocation_during_close_is_in_the_manual_receipt_not_rebased_after_reap(self):
        a = self.actual()
        pump = self.live_pump(a)
        close = pump.close
        revoked = []
        def retiring_close():
            close()
            if not revoked:
                revoked.append(True)
                a.set_microphone(False)
                a.set_microphone(True, listen=False)
        pump.close = retiring_close
        a.play = Mock()
        a.request = Mock(side_effect=AssertionError('No dispatch with stale pause receipt'))
        result = a.manual('/say', dict(text='fixture'))
        self.assertTrue(result['cancelled'])
        self.assertFalse(a.listening.is_set())
        a.request.assert_not_called(); a.play.assert_not_called()
        self.assertEqual(a.microphone_epoch, 4)

    def test_manual_normal_error_and_lock_failure_preserve_restoration(self):
        for path in ('/say', '/ask'):
            for listening in (False, True):
                for outcome in ('ok', 'error', 'busy'):
                    with self.subTest(path=path, listening=listening, outcome=outcome):
                        a = self.actual(); r8.operator_fixture(a)
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
                            self.assertEqual(options, dict(allow_barge_in=listening, expected_epoch=a.microphone_epoch, expected_policy_epoch=3))
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
                a = self.actual(); r8.operator_fixture(a)
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

    def test_busy_manual_cannot_restore_after_authority_roundtrip(self):
        for revoke in ('microphone', 'policy', 'shutdown'):
            with self.subTest(revoke=revoke):
                a = self.actual()
                policy = r8.operator_fixture(a)
                pump = self.live_pump(a)
                def acquire(**kwargs):
                    if revoke == 'microphone':
                        a.set_microphone(False)
                        a.set_microphone(True, listen=False)
                    elif revoke == 'policy':
                        # Actual policy mutator; fixture save models its durable
                        # monotonic result, while real persistence is tested above.
                        def save(value):
                            policy.update(value); policy['epoch'] += 1
                            return dict(policy)
                        a.motion_policy.save.side_effect = save
                        a.set_motion_policy(dict(motor_enabled=False, quiet=True, privacy_all=False))
                        a.set_motion_policy(dict(motor_enabled=False, quiet=False, privacy_all=False))
                    else: a.stopping.set()
                    return False
                a.audio_lock = SimpleNamespace(acquire=acquire)
                a.voice = Mock()
                with self.assertRaisesRegex(RuntimeError, 'processing a voice turn'):
                    a.manual('/say', dict(text='fixture'))
                self.assertFalse(a.listening.is_set())
                self.assertFalse(a.capture_active)
                self.assertTrue(pump.retired.is_set())
                a.voice.assert_not_called()
                self.reap(); self.children.clear()

    def test_actual_manual_stream_success_preserves_legacy_restoration(self):
        for path in ('/say', '/ask'):
            with self.subTest(path=path):
                a = self.actual()
                pump = self.live_pump(a)
                class Config(dict): token = 'fixture'
                a.config = Config(a.config)
                class Response(io.BytesIO):
                    headers = SimpleNamespace(get_content_type=lambda: 'application/x-ndjson')
                a.http = Mock()
                a.http.open.side_effect = lambda *args, **kwargs: Response(
                    b'{"type":"reply","reply":"fixture"}\n{"type":"done","ok":true,"reply":"fixture"}\n')
                with patch.object(self.module.subprocess, 'Popen', side_effect=AssertionError('No hardware')):
                    result = a.manual(path, dict(text='fixture'))
                self.assertEqual(result, dict(ok=True, reply='fixture'))
                self.assertEqual(a.http.open.call_count, 1)
                request = a.http.open.call_args.args[0]
                self.assertTrue(request.full_url.endswith('/stream/text' if path == '/ask' else '/stream/say'))
                self.assertTrue(a.listening.is_set())
                self.assertTrue(a.microphone.enabled)
                self.assertEqual(a.microphone_epoch, 2)
                self.assertTrue(pump.retired.is_set())
                self.assertFalse(a.capture_active)
                self.assertEqual(len(self.children), 1)
                self.assertIsNotNone(self.children[0].poll())
                self.reap(); self.children.clear()

    def test_R7_clear_boundary_remains_atomic(self):
        assert_manual_resume_boundary(self)

def assert_manual_resume_boundary(case):
    """Same R7 clear/reader barriers; R11 blocks then rejects changed authority."""
    from reachy_companion.autonomous.native_agent import NativeAgent, identity
    _, raw = builder.candidate()
    fixed = load(raw.decode())
    for path in ('/say', '/ask'):
        with case.subTest(path=path):
            a = fixed.Agent.__new__(fixed.Agent)
            a.__dict__.update(vars(case.actual()))
            policy = r8.operator_fixture(a)
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
                    if threading.current_thread().name == 'R11-resume': resume_attempt.set()
                    if threading.current_thread().name == 'R11-observer': read_attempt.set()
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
            worker = threading.Thread(target=manual, name='R11-manual')
            resumer = threading.Thread(target=resume, name='R11-resume')
            observer = threading.Thread(target=observe, name='R11-observer')
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
                case.assertNotEqual(identity(a.operator_status()), identity(operator))
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
                with case.assertRaisesRegex(ValueError, 'authority/listening withdrawn'):
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
                case.assertGreaterEqual(drained['read_bytes'], initial['pcm']['read_bytes'])
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
            case.assertEqual(a.microphone_epoch, 2)
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
            with case.assertRaisesRegex(ValueError, 'authority/listening withdrawn'):
                native.read()
            case.assertEqual(native.recoveries, 0)
            case.assertFalse(native.stock_allowed(time.monotonic()))
            replacement.close()
            case.receipts.append(dict(case='R11-legacy-manual-atomic-retire', path=path,
                initial=initial, blocked_at_clear=['resume', 'operator'],
                read_error=str(read_errors[0]), recoveries=native.recoveries,
                active_retired_pcm=retired_status['capture_pcm'], pcm=pump.snapshot(),
                replacement_pcm=replacement.snapshot(), final_listening=a.listening.is_set(),
                final_capture_active=a.capture_active, physical_closed_after_gap=native.physical_closed_after_gap))


class CandidateBoundListeningTests(bound.BoundListeningTests):
    @classmethod
    def setUpClass(cls):
        _, raw = builder.candidate()
        cls.module = load(raw.decode())
        cls.source = raw.decode()


if __name__ == '__main__': unittest.main()
