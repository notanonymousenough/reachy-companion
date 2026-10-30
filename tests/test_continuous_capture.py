"""A0 exact-baseline checks using real subprocess pipes, never ALSA or network."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
from types import ModuleType
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_agent_live_latency_patch import load
from test_capture_pump import agent, Clock, LOUD, QUIET
import test_agent_stream_timing as timing_fixture
import test_bound_listening as bound_fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('a0_builder',
    ROOT/'deploy/autonomous/prepare_continuous_capture.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

# One actual child owns the stdout pipe. The injected factory substitutes this
# deterministic writer for arecord; no subprocess ever opens an audio device.
WRITER = """
import os, sys, time
for line in sys.stdin:
    count, delay, loud = line.split()
    pcm = (b'\\xe8\\x03' if int(loud) else b'\\0\\0') * 480
    if float(delay) == 0:
        os.write(1, pcm * int(count))
    else:
        for _ in range(int(count)):
            os.write(1, pcm)
            time.sleep(float(delay))
"""


def wait_for(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.003)
    raise AssertionError('Bounded fixture wait expired')


class ContinuousCaptureTests(unittest.TestCase):
    receipts = []

    @classmethod
    def setUpClass(cls):
        cls.before, cls.data = builder.candidate()
        cls.module = load(cls.data['agent.py'].decode())
        cls.old = load(cls.before['agent.py'].decode())
        cls.helper = ModuleType('reachy_companion.capture_pump')
        with patch.dict(sys.modules, {'reachy_companion.capture_pump': cls.helper}):
            exec(compile(cls.data['capture_pump.py'], 'capture-pump-A0.py', 'exec'), cls.helper.__dict__)

    def setUp(self):
        self.modules = patch.dict(sys.modules, {'reachy_companion.capture_pump': self.helper})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.children = []
        self.commands = []
        self.addCleanup(self.reap)

    def reap(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=2)
            for stream in (child.stdin, child.stdout):
                if not stream.closed:
                    stream.close()

    def popen(self, command, **kwargs):
        # A replacement source is never opened while the previous child lives.
        self.assertTrue(all(child.poll() is not None for child in self.children))
        self.commands.append(command)
        child = subprocess.Popen([sys.executable, '-u', '-c', WRITER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.children.append(child)
        return child

    def send(self, count, delay=.01, loud=False):
        self.children[-1].stdin.write(f'{count} {delay} {int(loud)}\n'.encode())

    def actual(self):
        a = self.module.Agent.__new__(self.module.Agent)
        a.__dict__.update(vars(agent()))
        del a.set_microphone  # Exercise the candidate method, not fixture Mock.
        a.config['conversation'].update(capture_pump_enabled=True, wake_on_start=False, greet_on_start=False)
        a.config['audio']['echo_tail_seconds'] = .3
        a.microphone_lock = threading.Lock()
        a.microphone_owner_id = None
        a.microphone.error = None
        a.motion_policy.lock = threading.RLock()
        a.microphone.save = Mock(side_effect=lambda enabled: setattr(a.microphone, 'enabled', enabled))
        a.audio_lock = threading.Lock()
        a._capture_pump = a._capture_packet = a.pending_pcm = a.resume_audio = None
        a._capture_source_generation = 0
        a._capture_suspended = False
        a.playback_configured = True
        a.turns = 0
        return a

    def pump(self, a=None, clock=None):
        a = a or agent()
        pump = self.helper.CapturePump(a, 1, clock=clock or time.monotonic, popen=self.popen)
        self.addCleanup(pump.close)
        return a, pump

    def phrase(self, pump, clock):
        for chunk in (LOUD, LOUD, QUIET, QUIET):
            clock.now += .03
            pump._publish(chunk, clock())
        return pump.latest

    def test_exact_bundle_and_only_audio_lifecycle_changes(self):
        for name, raw in self.before.items():
            self.assertEqual(builder.digest(raw), builder.PINS[name][0])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'bundle'
            manifest = builder.build(target)
            self.assertEqual(set(manifest['outputs']), {'agent.py', 'capture_pump.py'})
            self.assertFalse(manifest['continuous_acceptance'])
            self.assertFalse(manifest['default_enabled'])
            self.assertFalse(manifest['barge_in'])
            with self.assertRaises(FileExistsError):
                builder.build(target)
        def outside(raw):
            tree = ast.parse(raw)
            a = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Agent')
            changed = {'status', '_capture_fresh', 'voice', 'run', 'set_listening', 'manual'}
            a.body = [n for n in a.body if getattr(n, 'name', None) not in changed]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(outside(self.before['agent.py']), outside(self.data['agent.py']))

    def test_real_pipe_advances_during_slow_consumer_processing_and_output(self):
        a, pump = self.pump()
        pump.start(); pump.start()
        wait_for(lambda: a.capture_active)
        self.send(150, .005, True)
        samples = []
        for phase in ('listening', 'processing', 'speaking'):
            a.phase = phase
            pump.mode(phase != 'listening')
            if phase == 'speaking':
                pump.output(True)
            before = pump.snapshot()['read_bytes']
            wait_for(lambda: pump.snapshot()['read_bytes'] >= before + 12*len(LOUD))
            row = dict(phase=phase, **pump.snapshot())
            self.assertLessEqual(row['pending_events'], 1)
            self.assertLessEqual(row['assembler_bytes'], 34*len(LOUD))
            self.assertEqual(row['gap_events'], 0)
            samples.append(row)
        self.assertGreater(samples[-1]['suppressed_frames'], 0)
        self.assertIsNone(pump.latest)
        a.request.assert_not_called()
        self.assertEqual(len(self.children), 1)
        self.assertEqual(self.commands[0][0], 'arecord')
        pump.close()
        self.assertIsNotNone(self.children[0].poll())
        self.assertTrue(self.children[0].stdout.closed)
        self.assertFalse(pump.thread.is_alive())
        self.assertFalse(a.capture_active)
        self.receipts.append(dict(case='real_pipe_slow_consumer', samples=samples))

    def test_real_pipe_burst_overflow_is_bounded_counted_and_does_not_restart(self):
        # Prefill a real pipe before the reader starts, to make the burst exact.
        a = agent()
        def prefilled(command, **kwargs):
            child = self.popen(command, **kwargs)
            self.send(8, 0, True)
            time.sleep(.08)
            return child
        pump = self.helper.CapturePump(a, 1, popen=prefilled)
        self.addCleanup(pump.close)
        pump.start()
        wait_for(lambda: pump.snapshot()['read_bytes'] == 8*len(LOUD))
        row = pump.snapshot()
        self.assertEqual(row['read_frames'], 8*480)
        self.assertEqual(row['overflow_events'], 1)
        self.assertEqual(row['overflow_bytes'], 7*len(LOUD))
        self.assertEqual(row['chunks'], 1)
        self.assertLessEqual(row['raw_buffer_peak_bytes'], 9*len(LOUD)-1)
        self.assertIsNone(pump.error)
        self.send(10, .01)
        wait_for(lambda: pump.snapshot()['read_bytes'] > row['read_bytes'])
        self.assertEqual(len(self.children), 1)
        self.receipts.append(dict(case='real_pipe_burst', sample=row))

    def test_latest_slot_bounds_slow_consumer_and_expires_queued_pcm(self):
        clock = Clock()
        _, pump = self.pump(clock=clock)
        previous = None
        for _ in range(100):
            packet = self.phrase(pump, clock)
            self.assertIsNotNone(packet)
            if previous is not None:
                self.assertFalse(pump.fresh(previous))
            previous = packet
            self.assertLessEqual(len(packet.pcm), 34*len(LOUD))
        self.assertEqual(pump.snapshot()['pending_events'], 1)
        self.assertGreaterEqual(pump.snapshot()['superseded_events'], 99)
        clock.now += 3
        self.assertIsNone(pump.event(idle_deadline=clock(), final_only=True))
        self.assertFalse(pump.claim(previous))

    def test_queue_ttl_does_not_expire_admitted_stt_but_revocation_does(self):
        for change in ('off', 'epoch', 'boot', 'privacy', 'policy', 'retire'):
            clock = Clock()
            a, pump = self.pump(clock=clock)
            packet = self.phrase(pump, clock)
            self.assertTrue(pump.claim(packet))
            clock.now += 40
            self.assertFalse(pump.fresh(packet))
            self.assertTrue(pump.admitted(packet))
            if change == 'off': a.microphone.enabled = False
            elif change == 'epoch': a.microphone_epoch += 1
            elif change == 'boot': a.agent_boot_id = 'new-boot'
            elif change == 'privacy': a.motion_policy.snapshot.return_value['privacy_all'] = True
            elif change == 'policy': a.motion_policy.snapshot.return_value['epoch'] += 1
            else: pump.retire()
            self.assertFalse(pump.admitted(packet), change)

    def test_own_output_and_tail_never_reappear_on_idle_or_revoke(self):
        clock = Clock()
        _, pump = self.pump(clock=clock)
        pump.mode(True)
        before = self.phrase(pump, clock)
        self.assertIsNotNone(before)
        pump.output(True)
        self.assertFalse(pump.fresh(before))
        self.assertFalse(pump.claim(before))
        self.assertIsNone(self.phrase(pump, clock))
        pump.output(False)
        pump.mode(False)
        self.assertIsNone(self.phrase(pump, clock))
        clock.now += 1
        fresh = self.phrase(pump, clock)
        self.assertIsNotNone(fresh)
        self.assertGreater(fresh.number, before.number)
        pump.retire()
        self.assertIsNone(self.phrase(pump, clock))
        self.assertFalse(pump.claim(fresh))

    def test_fresh_input_during_processing_is_available_when_idle_without_output(self):
        clock = Clock()
        _, pump = self.pump(clock=clock)
        pump.mode(True)
        packet = self.phrase(pump, clock)
        pump.mode(False)
        self.assertIs(pump.event(final_only=True), packet)
        self.assertTrue(pump.claim(packet))

    def test_actual_agent_blocked_stt_keeps_reading_then_off_blocks_late_result(self):
        a = self.actual()
        a.operator_status = Mock(return_value=dict(agent_boot_id='fixture', microphone_epoch=1,
            microphone_owner_id=None, motion_policy=dict(epoch=3)))
        a.voice = Mock()
        entered = threading.Event(); release = threading.Event()
        def request(base, path, *args, **kwargs):
            if path == '/health': return dict(ok=True)
            if path == '/status': return dict(ownership=dict(state='free'))
            self.assertEqual(path, '/transcribe')
            entered.set()
            if not release.wait(2): raise AssertionError('STT fixture release expired')
            return dict(ok=True, transcript='fresh external request', decision=dict(action='answer'))
        a.request = request
        _, pump = self.pump(a)
        a._capture_pump = pump
        pump.start()
        thread = threading.Thread(target=a.run)
        thread.start()
        try:
            wait_for(lambda: a.capture_active)
            self.send(2, .03, True); self.send(2, .03)
            self.assertTrue(entered.wait(1))
            before = pump.snapshot()['read_bytes']
            self.send(30, .01)
            wait_for(lambda: pump.snapshot()['read_bytes'] >= before+12*len(QUIET))
            a.set_microphone(False)
            self.assertIsNone(pump.process)
            self.assertTrue(self.children[0].stdout.closed)
            self.assertIsNone(a._capture_packet)
            a.stopping.set(); release.set()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            a.voice.assert_not_called()
            self.assertEqual(a.turns, 0)
        finally:
            a.stopping.set(); release.set(); thread.join(3)

    def test_same_epoch_pause_retires_and_restart_uses_new_generation(self):
        from reachy_companion.autonomous.native_agent import NativeAgent, identity
        a = self.actual()
        _, pump = self.pump(a)
        a._capture_pump = pump
        pump.start()
        wait_for(lambda: a.capture_active)
        # Feed actual exact-A1 Agent operator/status + real pump metadata into
        # the native observer, rather than inventing generation continuity.
        self.assertEqual(builder.digest(self.data['agent.py']),
                         'de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b')
        self.assertEqual(builder.digest(self.data['capture_pump.py']),
                         '5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6')
        policy = dict(epoch=3, motor_enabled=True, quiet=False, privacy_all=False)
        a.motion_policy.snapshot.return_value = policy
        a.motion_policy.owned_snapshot.return_value = (policy, None)
        a.expressions.version = 1
        a.motion_actor_status = Mock(return_value={})
        a.stream_timing_status = Mock(return_value=None)
        a.vision_route_status = Mock(return_value=None)
        a.last_error = a.last_transcript = a.resume_blocked_reason = None
        a.volume = SimpleNamespace(percent=100)
        operator = a.operator_status()
        def get(path):
            return a.status() if path == '/status' else a.operator_status()
        client = SimpleNamespace(get=get)
        native = NativeAgent(client, client, {}, operator, 'fixture-hub', allow_stock=True)
        native.latest = native.read()
        self.assertTrue(native.stock_allowed(time.monotonic()))
        native.unavailable_since('hidden-pause', time.monotonic())
        a.set_listening(False, {})
        self.assertTrue(pump.retired.is_set())
        self.assertFalse(a.capture_active)
        a.set_listening(True, {})
        # _capture_get imports the candidate; inject only its process factory.
        original = self.helper.CapturePump
        def source(agent, generation):
            return original(agent, generation, popen=self.popen)
        a._capture_source_generation = 1
        with patch.object(self.helper, 'CapturePump', side_effect=source):
            replacement = a._capture_get()
        self.addCleanup(replacement.close)
        wait_for(lambda: a.capture_active)
        self.assertEqual(replacement.generation, 2)
        self.assertEqual(len(self.children), 2)
        self.assertIsNotNone(self.children[0].poll())
        self.assertIsNone(self.children[1].poll())
        self.assertEqual(a.microphone_epoch, 1)
        self.assertEqual(identity(a.operator_status()), identity(operator))
        self.assertTrue(a.listening.is_set()); self.assertTrue(a.capture_active)
        self.assertFalse(replacement.snapshot()['retired'])
        with self.assertRaisesRegex(ValueError, 'source changed'):
            native.read()
        self.assertIsNotNone(native.withdrawn)
        self.assertFalse(native.stock_allowed(time.monotonic()))
        self.assertTrue(native.physical_closed_after_gap)
        pump.start()
        self.assertEqual(len(self.children), 2)

    def test_legacy_manual_resume_cannot_recover_same_source_before_pending_retire(self):
        """R7 counterexample becomes blocked/retired on the exact R8 candidate.

        Original trace and source remain frozen in R7-evidence and R8 preimages.
        """
        from test_manual_retire_fix import assert_manual_resume_boundary
        assert_manual_resume_boundary(self)

    def test_off_persistence_failure_still_reaps_and_privacy_reaps_outside_locks(self):
        for privacy in (False, True):
            a = self.actual()
            _, pump = self.pump(a)
            a._capture_pump = pump
            pump.start()
            wait_for(lambda: a.capture_active)
            original_close = pump.close
            def checked_close(a=a, original_close=original_close):
                self.assertFalse(a.microphone_lock.locked())
                self.assertFalse(a.motion_policy.lock._is_owned())
                original_close()
            pump.close = checked_close
            if privacy:
                result = dict(epoch=4, quiet=False, privacy_all=True, motor_enabled=False)
                a.motion_policy.snapshot.return_value = result
                a.motion_policy.save.return_value = result
                a.set_motion_policy(dict(privacy_all=True))
            else:
                a.microphone.save.side_effect = OSError('fixture persistence failure')
                with self.assertRaises(OSError):
                    a.set_microphone(False)
            self.assertFalse(pump.permitted())
            self.assertIsNone(pump.process)
            self.assertFalse(a.capture_active)
            self.assertTrue(self.children[-1].stdout.closed)

    def test_failed_reap_keeps_ownership_and_refuses_replacement(self):
        a = self.actual()
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        process = Mock(stdout=os.fdopen(read_fd, 'rb', buffering=0))
        self.addCleanup(process.stdout.close)
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired('fixture', .01)
        factory = Mock(return_value=process)
        pump = self.helper.CapturePump(a, 1, popen=factory)
        a._capture_pump = pump
        pump._read()
        self.assertEqual(pump.error, 'Capture reap unavailable')
        self.assertIs(pump.process, process)
        self.assertTrue(a.capture_active)
        with self.assertRaises(RuntimeError):
            a._capture_get()
        factory.assert_called_once()

    def test_actual_agent_admitted_stt_over_two_seconds_reaches_one_model_turn(self):
        a = self.actual()
        a.operator_status = Mock(return_value=dict(agent_boot_id='fixture', microphone_epoch=1,
            microphone_owner_id=None, motion_policy=dict(epoch=3)))
        clock = Clock()
        _, pump = self.pump(a, clock)
        packet = self.phrase(pump, clock)
        pump.claim(packet); pump.mode(True)
        a._capture_pump = pump; a._capture_packet = packet
        a.capture = Mock(return_value=packet.pcm)
        a.voice = Mock(return_value=dict(ok=True, reply='fixture reply'))
        def request(base, path, *args, **kwargs):
            if path == '/health': return dict(ok=True)
            if path == '/status': return dict(ownership=dict(state='free'))
            self.assertEqual(path, '/transcribe')
            clock.now += 3
            return dict(ok=True, transcript='external request', decision=dict(action='answer'))
        a.request = request
        waits = []
        def waiting(**kwargs):
            if not waits:
                waits.append(True); return True
            a.stopping.set(); return False
        a.listening.wait = waiting
        a.run()
        a.voice.assert_called_once()
        self.assertEqual(a.turns, 1)
        self.assertIsNone(pump.accepted)

    def test_real_pipe_gap_fails_closed_and_records_gap(self):
        a, pump = self.pump()
        pump.start()
        wait_for(lambda: a.capture_active)
        wait_for(lambda: pump.retired.is_set())
        pump.close()
        row = pump.snapshot()
        self.assertEqual(row['gap_events'], 1)
        self.assertGreaterEqual(row['max_read_gap_seconds'], .25)
        self.assertEqual(row['read_bytes'], 0)
        self.assertEqual(pump.error, 'Capture source unavailable')
        self.assertFalse(a.capture_active)

    def test_voice_masks_before_aplay_and_never_starts_a_barge_stt_consumer(self):
        timing_fixture.AgentStreamTimingTests.setUpClass()
        fixture = timing_fixture.AgentStreamTimingTests()
        original = fixture.agent
        source = Mock()
        def configured(module=None):
            a = original(module)
            a.config['conversation']['capture_pump_enabled'] = True
            a.config['conversation']['barge_in']['confirm_with_stt'] = True
            a.current_reply_text = ''
            a._capture_get = Mock(return_value=source)
            def output(active):
                if active:
                    self.assertFalse(hasattr(a, 'observed_popen'))
                else:
                    self.assertIsNone(a.playback_process)
            source.output.side_effect = output
            return a
        fixture.agent = configured
        with patch.object(self.helper, 'barge_monitor', side_effect=AssertionError('No A0 barge consumer')):
            a, result, order, writes, _ = fixture.stream(module=self.module, barge=True)
        self.assertTrue(writes)
        self.assertNotIn('monitor', order)
        self.assertEqual(source.output.call_args_list, [unittest.mock.call(True), unittest.mock.call(False)])

    def test_default_false_voice_parity_and_primed_listen_false_has_no_reader(self):
        timing_fixture.AgentStreamTimingTests.setUpClass()
        fixture = timing_fixture.AgentStreamTimingTests()
        _, old_result, old_order, old_writes, _ = fixture.stream(module=self.old)
        _, result, order, writes, _ = fixture.stream(module=self.module)
        self.assertEqual((result, order, writes), (old_result, old_order, old_writes))
        a = self.actual(); a.listening.clear()
        with patch.object(self.helper, 'CapturePump') as constructor:
            self.assertIsNone(a.capture())
        constructor.assert_not_called()

    def test_status_exposes_only_bounded_pcm_metadata(self):
        a = self.actual()
        _, pump = self.pump(a)
        a._capture_pump = pump
        a.motion_actor_status = Mock(return_value={})
        a.stream_timing_status = Mock(return_value=None)
        a.vision_route_status = Mock(return_value=None)
        a.last_error = a.last_transcript = a.resume_blocked_reason = None
        a.volume = SimpleNamespace(percent=100)
        a.expressions.last_expression = 'neutral'
        a.expressions.last_error = a.sounds.last_error = None
        row = a.status()['capture_pcm']
        self.assertEqual(row, pump.snapshot())
        self.assertEqual(row['clock'], 'monotonic_read_receipt')
        self.assertLess(len(json.dumps(row)), 1200)
        self.assertNotIn('pcm', row)
        self.assertNotIn('transcript', row)


class CandidateBoundListeningTests(bound_fixture.BoundListeningTests):
    @classmethod
    def setUpClass(cls):
        _, files = builder.candidate()
        cls.module = load(files['agent.py'].decode())
        cls.source = files['agent.py'].decode()


if __name__ == '__main__':
    unittest.main()
