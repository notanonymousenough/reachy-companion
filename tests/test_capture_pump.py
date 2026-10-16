"""S1 fake mono PCM/process checks; never opens a device or calls a model."""
import array
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from reachy_companion.capture_pump import CapturePump, Utterance, barge_monitor
from test_agent_live_latency_patch import load
from test_agent_stream_timing import AgentStreamTimingTests

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('s1_builder', ROOT/'deploy/autonomous/prepare_capture_pump.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class Clock:
    def __init__(self): self.now = 100.
    def __call__(self): return self.now


def agent():
    config = json.loads((ROOT/'config.example.json').read_text())
    config['conversation']['barge_in'].update(enabled=True, confirm_with_stt=True, warmup_chunks=0,
                                            min_voiced_chunks=2, threshold_multiplier=1)
    config['audio'].update(sample_rate=16000, chunk_ms=30, vad_frame_ms=10, pre_roll_chunks=2,
        min_speech_frames=1, min_voiced_chunks=2, silence_chunks=2, calibration_chunks=1,
        max_recording_seconds=1, rms_floor=10)
    a = SimpleNamespace(config=config, audio=config['audio'], agent_boot_id='fixture', microphone_epoch=1,
        microphone=SimpleNamespace(enabled=True), stopping=threading.Event(), listening=threading.Event(),
        calibrated=True, threshold=10, chunk_bytes=960, vad_bytes=320, capture_active=False,
        motion_policy=Mock(), sounds=Mock(), expressions=Mock(), last_voice_at=None,
        current_reply_text='own answer', interruptions=0, phase='processing', barge_in_error=None,
        request=Mock(), stop_speaker=Mock(), set_microphone=Mock())
    a.listening.set()
    a.motion_policy.snapshot.return_value = dict(epoch=3, quiet=False, privacy_all=False)
    a.sounds.music = False
    a.vad = SimpleNamespace(is_speech=lambda frame, rate: any(frame))
    return a


LOUD = array.array('h', [1000]*480).tobytes()
QUIET = bytes(960)


def phrase(pump, clock):
    for chunk in (LOUD, LOUD, QUIET, QUIET):
        clock.now += .03
        pump._publish(chunk, clock())
    return pump.latest


class CapturePumpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before, cls.data = builder.candidate()
        cls.module = load(cls.data['agent.py'].decode())
        cls.barge = ModuleType('reachy_companion.barge_in')
        exec(compile(cls.data['barge_in.py'], 'exact-barge-S1.py', 'exec'), cls.barge.__dict__)

    def pump(self):
        a = agent(); clock = Clock()
        return a, clock, CapturePump(a, 1, clock=clock)

    def test_exact_builder_and_exclusive_output(self):
        self.assertEqual(builder.digest(self.before['agent.py']), builder.AGENT_BEFORE)
        self.assertEqual(builder.digest(self.before['barge_in.py']), builder.BARGE_BEFORE)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'bundle'; manifest = builder.build(target)
            self.assertFalse(manifest['default_enabled'])
            self.assertFalse(manifest['continuous_acceptance'])
            self.assertEqual(set(manifest['outputs']), {'agent.py', 'barge_in.py', 'capture_pump.py'})
            with self.assertRaises(FileExistsError): builder.build(target)

    def test_vad_one_final_claim_and_bounded_frames(self):
        a, clock, pump = self.pump(); packet = phrase(pump, clock)
        self.assertTrue(packet.final); self.assertEqual(packet.number, 1)
        self.assertEqual(packet.clock, 'monotonic_read_receipt')
        self.assertTrue(pump.claim(packet)); self.assertFalse(pump.claim(packet))
        self.assertEqual(pump.assembler.frames, [])
        sizes = []
        for _ in range(100):
            pump._publish(LOUD, clock())
            self.assertLessEqual(len(pump.assembler.frames), 34)
            if pump.latest is not None: sizes.append(len(pump.latest.pcm))
        self.assertTrue(sizes); self.assertLessEqual(max(sizes), 34*len(LOUD))

    def test_ttl_copy_and_40_second_drain_never_reage(self):
        a, clock, pump = self.pump(); packet = phrase(pump, clock)
        copied = Utterance(**vars(packet))
        clock.now += 2.001
        self.assertFalse(pump.fresh(copied)); self.assertFalse(pump.claim(copied))
        clock.now += 40
        self.assertFalse(pump.fresh(packet))
        fresh = phrase(pump, clock)
        self.assertTrue(pump.claim(fresh)); self.assertGreater(fresh.number, packet.number)

    def test_new_utterance_binding_and_generation_withdraw_old_pcm(self):
        a, clock, pump = self.pump(); packet = phrase(pump, clock)
        pump._publish(LOUD, clock())
        self.assertFalse(pump.fresh(packet)); self.assertIsNone(pump.latest)
        packet = phrase(pump, clock)
        for change in ('epoch', 'boot', 'policy', 'off', 'privacy', 'paused'):
            a, clock, pump = self.pump(); packet = phrase(pump, clock)
            if change == 'epoch': a.microphone_epoch += 1
            elif change == 'boot': a.agent_boot_id = 'other'
            elif change == 'policy': a.motion_policy.snapshot.return_value['epoch'] += 1
            elif change == 'off': a.microphone.enabled = False
            elif change == 'privacy': a.motion_policy.snapshot.return_value['privacy_all'] = True
            else: a.listening.clear()
            self.assertFalse(pump.fresh(packet), change)
        a, clock, pump = self.pump(); packet = phrase(pump, clock)
        replacement = CapturePump(a, 2, clock=clock)
        self.assertFalse(replacement.fresh(packet))
        pump.retire(); self.assertIsNone(pump.latest); self.assertEqual(pump.assembler.frames, [])

    def test_return_to_idle_drops_unconfirmed_reply_tail(self):
        a, clock, pump = self.pump(); pump.mode(True)
        packet = phrase(pump, clock); self.assertIsNotNone(packet)
        pump.mode(False)
        self.assertIsNone(pump.latest); self.assertEqual(pump.assembler.frames, [])

    def test_latest_event_probe_superseded_by_final(self):
        a, clock, pump = self.pump(); pump.mode(True)
        pump._publish(LOUD, clock()); pump._publish(LOUD, clock())
        probe = pump.latest; self.assertFalse(probe.final)
        pump._publish(QUIET, clock()); pump._publish(QUIET, clock())
        final = pump.latest
        self.assertTrue(final.final); self.assertEqual(final.number, probe.number)
        self.assertGreater(final.revision, probe.revision)
        self.assertFalse(pump.fresh(probe)); self.assertTrue(pump.fresh(final))
        pump.reject(probe); self.assertIs(pump.latest, final)

    def test_slow_stt_does_not_block_reader_and_expired_confirmation_has_no_action(self):
        a, clock, pump = self.pump(); pump.mode(True)
        entered = threading.Event(); release = threading.Event()
        def request(*args, **kwargs):
            entered.set(); release.wait(1)
            return dict(transcript='a different request', decision=dict(action='answer'))
        a.request.side_effect = request
        with patch.dict(sys.modules, {'reachy_companion.barge_in': self.barge}):
            monitor = barge_monitor(a, pump); monitor.start()
            pump._publish(LOUD, clock()); pump._publish(LOUD, clock())
            self.assertTrue(entered.wait(1))
            # Reader keeps assembling while the one control thread waits on STT.
            pump._publish(QUIET, clock()); pump._publish(QUIET, clock())
            self.assertTrue(pump.latest.final)
            clock.now += 3; release.set()
            monitor.stop.set(); monitor.thread.join(1)
            self.assertFalse(monitor.interrupted.is_set()); a.stop_speaker.assert_not_called()
            a.set_microphone.assert_not_called()

    def test_stale_stop_confirmation_cannot_withdraw_new_grant(self):
        a, clock, pump = self.pump(); packet = phrase(pump, clock)
        monitor = self.barge.BargeInMonitor(a)
        monitor.capture_permitted = lambda: pump.fresh(packet)
        def request(*args, **kwargs):
            a.microphone_epoch += 1
            return dict(transcript='stop', decision=dict(action='stop'))
        a.request.side_effect = request
        self.assertFalse(monitor.trigger(packet.pcm)); a.set_microphone.assert_not_called()

    def test_pump_stop_uses_existing_boot_epoch_compare_and_swap(self):
        a, clock, pump = self.pump(); packet = phrase(pump, clock)
        a.request.return_value = dict(transcript='stop', decision=dict(action='stop'))
        with patch.dict(sys.modules, {'reachy_companion.barge_in': self.barge}):
            monitor = barge_monitor(a, pump)
            monitor.capture_permitted = lambda: pump.fresh(packet)
            self.assertTrue(monitor.trigger(packet.pcm))
        a.set_microphone.assert_called_once_with(False, expected_boot_id='fixture', expected_epoch=1)

    def test_fresh_non_echo_confirmation_claims_final_once_on_consumer_thread(self):
        a, clock, pump = self.pump(); pump.mode(True)
        a.request.return_value = dict(transcript='different request', decision=dict(action='answer'))
        packet = phrase(pump, clock)
        with patch.dict(sys.modules, {'reachy_companion.barge_in': self.barge}):
            monitor = barge_monitor(a, pump); monitor.start(); monitor.thread.join(1)
            self.assertFalse(monitor.thread.is_alive())
            self.assertIs(monitor.finish(), packet)
            self.assertIsNone(monitor.pcm); self.assertFalse(monitor.capture_permitted())
        self.assertEqual(a.interruptions, 1); a.stop_speaker.assert_called_once_with(abort_stream=False)
        self.assertEqual(pump.claimed, packet.number); self.assertFalse(pump.claim(packet))

    def test_existing_echo_confirmation_rejects_own_voice(self):
        a, clock, pump = self.pump(); packet = phrase(pump, clock)
        monitor = self.barge.BargeInMonitor(a)
        monitor.capture_permitted = lambda: pump.fresh(packet)
        a.request.return_value = dict(transcript='own answer', decision=dict(action='answer'))
        self.assertFalse(monitor.trigger(packet.pcm)); a.stop_speaker.assert_not_called()

    def test_previous_unknown_control_work_blocks_duplicate_confirmation_and_capture(self):
        a, clock, pump = self.pump()
        a._capture_control = SimpleNamespace(thread=SimpleNamespace(is_alive=lambda: True))
        with patch.dict(sys.modules, {'reachy_companion.barge_in': self.barge}):
            with self.assertRaises(RuntimeError): barge_monitor(a, pump)
        actual = self.module.Agent.__new__(self.module.Agent); actual.__dict__.update(vars(a))
        actual.config['conversation']['capture_pump_enabled'] = True; actual._capture_suspended = False
        with patch('reachy_companion.capture_pump.CapturePump') as constructor:
            with self.assertRaises(RuntimeError): actual.capture()
            constructor.assert_not_called()

    def test_source_failure_control_wakes_only_its_current_owned_reply(self):
        for newer_grant in (False, True):
            a, clock, pump = self.pump(); pump.error = 'Capture source unavailable'; pump.retire()
            if newer_grant: a.microphone_epoch += 1
            with patch.dict(sys.modules, {'reachy_companion.barge_in': self.barge}):
                monitor = barge_monitor(a, pump); monitor.start(); monitor.thread.join(1)
            self.assertFalse(monitor.thread.is_alive())
            if newer_grant: a.stop_speaker.assert_not_called()
            else: a.stop_speaker.assert_called_once_with()

    def test_source_error_event_raise_race_wakes_once_and_never_new_grant_or_stop(self):
        for newer, withdrawn, wake_raises in ((False, False, False), (False, False, True),
                                              (True, False, False), (False, True, False)):
            a, clock, pump = self.pump(); pump.error = 'Capture source unavailable'
            # Reader has set error, but has not reached retire() yet.
            pump.event = Mock(side_effect=RuntimeError('fixture event race'))
            if newer: a.microphone_epoch += 1
            if wake_raises: a.stop_speaker.side_effect = OSError('fixture')
            with patch.dict(sys.modules, {'reachy_companion.barge_in': self.barge}):
                monitor = barge_monitor(a, pump)
                if withdrawn: monitor.stop.set()
                monitor.start(); monitor.thread.join(1)
                monitor.source_failed()
            self.assertFalse(monitor.thread.is_alive())
            if newer or withdrawn: a.stop_speaker.assert_not_called()
            else: a.stop_speaker.assert_called_once_with()

    def test_quiet_privacy_withdraw_before_blocked_or_raising_reap_without_late_effects(self):
        for privacy in (False, True):
            for blocked in (False, True):
                a = self.module.Agent.__new__(self.module.Agent); a.__dict__.update(vars(agent()))
                a.config['conversation']['capture_pump_enabled'] = True
                a.microphone_lock = threading.Lock(); a.capture_active = True
                a._capture_pump = Mock(); a.resume_audio = object(); a.pending_pcm = (1, object())
                result = dict(epoch=4, motor_enabled=True, quiet=not privacy, privacy_all=privacy)
                a.motion_policy.save.return_value = result
                entered = threading.Event(); release = threading.Event(); errors = []
                def close():
                    self.assertFalse(a.microphone_lock.locked())
                    a.stop_speaker.assert_called_once_with(); a.expressions.hold.assert_called_once_with()
                    self.assertIsNone(a.resume_audio); self.assertIsNone(a.pending_pcm)
                    self.assertEqual(a.listening.is_set(), not privacy)
                    entered.set()
                    if blocked: self.assertTrue(release.wait(1))
                    else: raise RuntimeError('fixture reap failure')
                a._capture_pump.close.side_effect = close
                def update():
                    try: a.set_motion_policy(dict(quiet=not privacy, privacy_all=privacy))
                    except Exception as error: errors.append(error)
                if blocked:
                    thread = threading.Thread(target=update); thread.start()
                    self.assertTrue(entered.wait(1))
                    # A newer grant while reap is stalled must not be cleared
                    # or have its speaker stopped after the old reap returns.
                    a.microphone_epoch += 1; a.listening.set()
                    release.set(); thread.join(1); self.assertFalse(thread.is_alive())
                    self.assertEqual(errors, []); self.assertTrue(a.listening.is_set())
                else:
                    update(); self.assertEqual(len(errors), 1)
                    self.assertIsInstance(errors[0], RuntimeError)
                a.stop_speaker.assert_called_once_with(); a.expressions.hold.assert_called_once_with()
                self.assertTrue(a.capture_active)  # Never fake a failed reap.

    def test_off_reaps_outside_microphone_lock_even_if_persistence_fails(self):
        for fail in (False, True):
            a = self.module.Agent.__new__(self.module.Agent); a.__dict__.update(vars(agent()))
            a.config['conversation']['capture_pump_enabled'] = True
            a.microphone_lock = threading.Lock(); a.microphone_owner_id = None
            a.microphone.save = Mock(side_effect=OSError() if fail else None)
            pump = CapturePump(a, 1); a._capture_pump = pump; a._capture_packet = object()
            control = SimpleNamespace(stop=threading.Event(), pcm=object(), capture_permitted=lambda: True)
            a._capture_control = control; a.pending_pcm = (1, object())
            def close():
                self.assertFalse(a.microphone_lock.locked())
                self.assertTrue(pump.retired.is_set()); self.assertIsNone(a._capture_packet)
                self.assertIsNone(a.pending_pcm); self.assertIsNone(control.pcm)
                self.assertTrue(control.stop.is_set()); self.assertFalse(control.capture_permitted())
            pump.close = Mock(side_effect=close)
            if fail:
                with self.assertRaises(OSError): self.module.Agent.set_microphone(a, False)
            else:
                result = self.module.Agent.set_microphone(a, False)
                self.assertFalse(result['microphone_enabled'])
            self.assertGreater(pump.close.call_count, 0)
            self.assertFalse(pump.permitted())

    def test_one_owned_reader_process_across_inference_and_playback_then_reap(self):
        a = agent(); opened = []; processes = []
        class Process:
            def __init__(self):
                read, self.write = os.pipe(); self.stdout = os.fdopen(read, 'rb', buffering=0)
                self.returncode = None
            def poll(self): return self.returncode
            def terminate(self): self.returncode = 0; os.close(self.write)
            def kill(self): self.terminate()
            def wait(self, **kwargs): return self.returncode
        def popen(command, **kwargs):
            opened.append(command); process = Process(); processes.append(process); return process
        pump = CapturePump(a, 1, popen=popen); pump.start(); pump.start()
        deadline = time.monotonic()+1
        while not a.capture_active and time.monotonic() < deadline: time.sleep(.005)
        self.assertTrue(a.capture_active); process = processes[0]
        for phase in ('listening', 'processing', 'speaking'):
            a.phase = phase
            os.write(process.write, QUIET)
            time.sleep(.02)
            self.assertIs(pump.process, process); self.assertTrue(a.capture_active)
        pump.close()
        self.assertFalse(a.capture_active); self.assertIsNone(pump.process)
        self.assertFalse(pump.thread.is_alive()); self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0][-3:], ['1', '-t', 'raw'])
        pump.start()
        self.assertIsNone(pump.process); self.assertEqual(len(opened), 1)

    def test_read_gap_and_backlog_retire_source_without_reaging_pcm(self):
        for backlog in (False, True):
            a = agent(); clock = Clock(); process = Mock()
            process.poll.return_value = None
            pump = CapturePump(a, 1, clock=clock, popen=Mock(return_value=process))
            selector = Mock()
            def select(**kwargs):
                if not backlog: clock.now += .5
                return [object()] if backlog else []
            selector.select.side_effect = select
            with patch('reachy_companion.capture_pump.selectors.DefaultSelector', return_value=selector), \
                    patch('reachy_companion.capture_pump.os.set_blocking'), \
                    patch('reachy_companion.capture_pump.os.read', return_value=LOUD*2):
                pump._read()
            self.assertTrue(pump.retired.is_set()); self.assertIsNone(pump.latest)
            self.assertIsNone(pump.process); self.assertFalse(a.capture_active)
            self.assertEqual(pump.error, 'Capture source unavailable')
            process.terminate.assert_called_once(); process.wait.assert_called_once()

    def test_prime_listen_false_never_opens_pump(self):
        a = self.module.Agent.__new__(self.module.Agent)
        a.__dict__.update(vars(agent())); a.config['conversation']['capture_pump_enabled'] = True
        a.listening.clear(); a._capture_suspended = False
        with patch('reachy_companion.capture_pump.CapturePump') as constructor:
            self.assertIsNone(a.capture()); constructor.assert_not_called()

    def test_default_capture_delegates_unchanged_finite_body(self):
        a = self.module.Agent.__new__(self.module.Agent); a.__dict__.update(vars(agent()))
        a._finite_capture = Mock(return_value=b'legacy')
        with patch('reachy_companion.capture_pump.CapturePump') as constructor:
            self.assertEqual(a.capture(), b'legacy'); constructor.assert_not_called()
        def method(raw, name):
            cls = next(n for n in ast.parse(raw).body if isinstance(n, ast.ClassDef) and n.name == 'Agent')
            node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
            node.name = 'capture'
            return ast.dump(node, include_attributes=False)
        self.assertEqual(method(self.before['agent.py'], 'capture'), method(self.data['agent.py'], '_finite_capture'))

    def test_expired_main_stt_result_never_reaches_model_or_turn_commit(self):
        a = self.module.Agent.__new__(self.module.Agent); a.__dict__.update(vars(agent()))
        a.config['conversation'].update(capture_pump_enabled=True, wake_on_start=False, greet_on_start=False)
        a.audio_lock = threading.Lock(); a.playback_configured = True
        a.pending_pcm = a.resume_audio = None; a.turns = 0
        clock = Clock(); pump = CapturePump(a, 1, clock=clock)
        packet = phrase(pump, clock); pump.claim(packet); pump.mode(True)
        a._capture_pump = pump; a._capture_packet = packet
        a.capture = Mock(return_value=packet.pcm); a.voice = Mock()
        a.operator_status = Mock(return_value=dict(agent_boot_id='fixture', microphone_epoch=1,
            microphone_owner_id='fixture-owner', motion_policy=dict(epoch=3)))
        requests = []
        def request(base, path, *args, **kwargs):
            requests.append(path)
            if path == '/health': return dict(ok=True)
            if path == '/status': return dict(ownership=dict(state='free'))
            self.assertEqual(path, '/transcribe'); clock.now += 3
            return dict(ok=True, transcript='fixture request', decision=dict(action='answer'))
        a.request = request
        waits = []
        def wait(**kwargs):
            if not waits: waits.append(True); return True
            a.stopping.set(); return False
        a.listening.wait = wait
        a.run()
        self.assertEqual(requests.count('/transcribe'), 1)
        a.voice.assert_not_called(); self.assertEqual(a.turns, 0)

    def test_vision_quiesce_is_honest_and_off_during_child_prevents_resume(self):
        a = self.module.Agent.__new__(self.module.Agent)
        a.__dict__.update(vars(agent())); a.config['conversation']['capture_pump_enabled'] = True
        a._capture_packet = object(); a._capture_suspended = False
        pump = Mock()
        pump.close.side_effect = lambda: setattr(a, 'capture_active', False)
        a.capture_active = True; a._capture_pump = pump
        a._capture_get = Mock()
        def dispatch(instance, text, epoch, expected):
            self.assertFalse(instance.capture_active)
            self.assertTrue(instance._capture_suspended)
            self.assertIsNone(instance._capture_packet)
            instance.microphone.enabled = False
            return dict(ok=True)
        self.assertTrue(a._capture_visual(dispatch, 'fixture', 1, dict(policy_epoch=3))['ok'])
        pump.close.assert_called_once(); a._capture_get.assert_not_called()

    def test_vision_resume_uses_current_binding_and_new_source(self):
        a = self.module.Agent.__new__(self.module.Agent)
        a.__dict__.update(vars(agent())); a.config['conversation']['capture_pump_enabled'] = True
        a._capture_pump = Mock(); a._capture_packet = None
        replacement = Mock(); a._capture_get = Mock(return_value=replacement)
        a._capture_visual(lambda *args: dict(ok=True), 'fixture', 1, dict(policy_epoch=3))
        a._capture_get.assert_called_once()

    def test_failed_vision_reap_never_fakes_closed_capture_or_dispatches_child(self):
        a = self.module.Agent.__new__(self.module.Agent); a.__dict__.update(vars(agent()))
        a.config['conversation']['capture_pump_enabled'] = True
        a._capture_pump = Mock(); a._capture_pump.close.side_effect = RuntimeError('fixture reap failure')
        a.capture_active = True; a._capture_get = Mock(); dispatch = Mock()
        with self.assertRaises(RuntimeError): a._capture_visual(dispatch, 'fixture', 1, dict(policy_epoch=3))
        self.assertTrue(a.capture_active); dispatch.assert_not_called(); a._capture_get.assert_not_called()

    def test_retired_pending_pcm_is_not_reintroduced_into_agent(self):
        a = self.module.Agent.__new__(self.module.Agent); a.__dict__.update(vars(agent()))
        a.config['conversation']['capture_pump_enabled'] = True; a.microphone_lock = threading.Lock()
        clock = Clock(); pump = CapturePump(a, 1, clock=clock); packet = phrase(pump, clock)
        a._capture_pump = pump; pump.retire()
        self.assertIsNone(a._capture_pending(packet)); self.assertIsNone(a._capture_packet)

    def test_default_false_exact_voice_operation_parity(self):
        AgentStreamTimingTests.setUpClass(); fixture = AgentStreamTimingTests()
        _, old_result, old_order, old_writes, _ = fixture.stream()
        _, result, order, writes, _ = fixture.stream(module=self.module)
        self.assertEqual(result, old_result); self.assertEqual(order, old_order); self.assertEqual(writes, old_writes)

    def test_shared_control_starts_before_model_open_and_failed_open_joins_it(self):
        AgentStreamTimingTests.setUpClass(); fixture = AgentStreamTimingTests()
        original = fixture.agent
        def configured(module=None):
            a = original(module)
            a.config['conversation']['capture_pump_enabled'] = True
            a.config['conversation']['barge_in']['confirm_with_stt'] = True
            a.current_reply_text = 'previous bounded echo context'
            a._capture_get = Mock()
            return a
        fixture.agent = configured
        for fail in (False, True):
            monitor = SimpleNamespace(interrupted=threading.Event(), start=Mock(), finish=Mock(return_value=None))
            with patch('reachy_companion.capture_pump.barge_monitor', return_value=monitor) as factory:
                a, result, order, writes, clock = fixture.stream(module=self.module, barge=True, fail_open=fail)
            factory.assert_called_once(); monitor.start.assert_called_once(); monitor.finish.assert_called_once()
            row = a.stream_timing_status(dict(epoch=6))
            self.assertLessEqual(row['monitor_start_return'], row['response_open_begin'])
            if not fail:
                self.assertNotIn('previous bounded echo context', a.current_reply_text)
                self.assertTrue(writes)

    def test_primed_voice_can_play_without_creating_any_reader(self):
        AgentStreamTimingTests.setUpClass(); fixture = AgentStreamTimingTests(); original = fixture.agent
        def configured(module=None):
            a = original(module)
            a.config['conversation']['capture_pump_enabled'] = True
            a.config['conversation']['barge_in']['confirm_with_stt'] = True
            a.current_reply_text = ''; a.listening.clear(); a._capture_get = Mock()
            return a
        fixture.agent = configured
        with patch('reachy_companion.capture_pump.barge_monitor') as factory:
            a, result, order, writes, clock = fixture.stream(module=self.module, barge=True)
        factory.assert_not_called(); a._capture_get.assert_not_called(); self.assertTrue(writes)

    def test_optin_is_strict_and_keeps_existing_stt_confirmation(self):
        a = self.module.Agent.__new__(self.module.Agent); a.__dict__.update(vars(agent()))
        self.assertFalse(a._capture_enabled())
        for value in (1, 'true', None):
            a.config['conversation']['capture_pump_enabled'] = value
            with self.assertRaises(ValueError): a._capture_enabled()
        a.config['conversation']['capture_pump_enabled'] = True
        self.assertTrue(a._capture_enabled())
        a.config['conversation']['barge_in']['confirm_with_stt'] = False
        with self.assertRaises(ValueError): a._capture_enabled()


if __name__ == '__main__': unittest.main()
