"""R20 synthetic reader -> exact R15 status -> normal request construction.

No device, model, network, new conversation consumer or hardware claim.
R20_BUNDLE relocates the three-file frozen candidate.
"""
import ast
import copy
from concurrent.futures import Future
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_capture_pump import agent, Clock, LOUD, QUIET
from test_agent_live_latency_patch import load as load_agent
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.gateway import ModelBackend, BudgetRejected

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path(os.environ.get('R20_BUNDLE', ROOT/'tests/fixtures/legacy/r20'))
TRACES = []


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


native = module('reachy_companion.autonomous.r20_native', BUNDLE/'candidate/autonomous/native_agent.py')
pump_module = module('reachy_companion.r20_pump', BUNDLE/'candidate/capture_pump.py')
agent_module = load_agent((BUNDLE/'candidate/agent.py').read_text())


class AcousticFastViewTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket', 'subprocess.Popen'):
            guard = patch(target, side_effect=AssertionError('Offline only: no socket/device/process/model'))
            guard.start(); self.addCleanup(guard.stop)
        self.remote = Clock(); self.remote.now = 10000.
        self.local = Clock()
        self.a = agent_module.Agent.__new__(agent_module.Agent)
        self.a.__dict__.update(vars(agent()))
        a = self.a
        a.microphone_lock = threading.Lock()
        a.microphone.error = None
        a.microphone_owner_id = None
        a.agent_boot_id = '11111111-1111-4111-8111-111111111111'
        self.policy = dict(epoch=3, quiet=False, privacy_all=False, motor_enabled=True)
        a.motion_policy.snapshot.side_effect = lambda: dict(self.policy)
        a.motion_policy.owned_snapshot.side_effect = lambda: (dict(self.policy), None)
        a.motion_policy.lock = threading.RLock()
        a.expressions.version = 1
        a.expressions.last_expression = a.expressions.last_error = None
        a.volume = SimpleNamespace(percent=50)
        a.resume_audio = None
        a.last_error = a.barge_in_error = a.resume_blocked_reason = None
        a.last_transcript = 'PRIVATE_TRANSCRIPT_MUST_NOT_ESCAPE'
        a.turns = 1
        a.sounds.last_error = None
        a.stream_timing_status = lambda p: {}
        a.vision_route_status = lambda p: {}
        a.motion_actor_status = lambda: {}
        a.audio['echo_tail_seconds'] = .3
        self.pump = pump_module.CapturePump(a, 7, clock=self.remote)
        self.addCleanup(self.pump.close)
        a._capture_pump = self.pump
        a.capture_active = True
        self.get_status = a.status
        self.hub_get = lambda path: a.operator_status()
        self.native = native.NativeAgent(SimpleNamespace(get=self.agent_get),
            SimpleNamespace(get=lambda path: self.hub_get(path)), {}, a.operator_status(),
            'fixture-hub', allow_stock=True, clock=self.local)
        self.cfg = load(ROOT/'config.autonomous.native-agent.example.json')
        self.cfg['context']['enabled'] = False
        self.state = native.NativeState('fixture-compute', self.cfg, self.native)
        self.addCleanup(self.native.close)

    def agent_get(self, path):
        if path == '/operator': return self.a.operator_status()
        if path == '/status': return self.get_status()
        raise AssertionError(path)

    def feed(self, chunk=LOUD, seconds=.03):
        self.remote.now += seconds; self.local.now += seconds
        # Synthetic os.read receipt: the actual reader path is tested separately.
        p = self.pump
        with p.condition:
            p.counters['read_bytes'] += len(chunk)
            p.counters['read_frames'] = p.counters['read_bytes']//2
            p.counters['read_calls'] += 1
            p.counters['last_read_monotonic'] = self.remote()
            p._publish(chunk, self.remote())

    def view(self):
        self.native.latest = self.native.read()
        self.state.observe()
        return self.state.snapshot(self.local())

    def acoustic(self, view):
        return {v['id']: v for v in view['sensors'] if v['id'].startswith('native.acoustic')}

    def assert_unknown(self, view):
        fields = self.acoustic(view)
        self.assertEqual(fields, {'native.acoustic': dict(id='native.acoustic', state='UNKNOWN', age_ms=None, summary='')})
        self.assertFalse(view['op']['motion_allowed'])

    def construct(self, view):
        backend = ModelBackend(self.cfg)
        # Count is a deterministic fixture, never an exact production tokenizer.
        backend.count = lambda model, text: math.ceil(len(text)/4)
        def post(url, payload, timeout, env):
            self.assertEqual(url, 'http://fixture.invalid/completion')
            self.wire = copy.deepcopy(payload)
            return dict(content='{"a":"wait","why":"Synthetic passive choice"}', stop_type='eos', tokens_predicted=10)
        backend.post = post
        self.cfg['models']['fast'].update(base_url='http://fixture.invalid', completion_path='/completion',
            completion_backend='llama_native', projection='full')
        result = backend.generate_loaded('fast', view)
        self.assertEqual(result['output']['a'], 'wait')
        prompt = self.wire['prompt']
        content = prompt.split('<|im_start|>user\n', 1)[1].split('<|im_end|>', 1)[0]
        return json.loads(content), result

    def test_measured_quiet_to_onset_survives_actual_request_construction(self):
        self.feed(QUIET); self.feed(LOUD)
        view = self.view(); fields = self.acoustic(view)
        measured = json.loads(fields['native.acoustic']['summary'])
        self.assertEqual(measured, dict(seq=2, rms=1000., delta=1000., onset=True, vad=3, loud=True, window_ms=30.))
        binding = json.loads(fields['native.acoustic.binding']['summary'])
        self.assertEqual(binding, dict(seq=2, boot=self.a.agent_boot_id, mic=1, policy=3, source=7, mask=0, read_call=2))
        receipt = json.loads(fields['native.acoustic.receipt']['summary'])
        self.assertEqual(receipt['read_end'], self.remote())
        self.assertEqual(receipt['clock'], 'monotonic_read_receipt')
        self.assertIsNone(receipt['capture_age_upper_ms'])
        self.assertEqual(receipt['reaction'], 'UNKNOWN')
        self.assertLess(receipt['read_age_upper_ms'], 2)
        self.assertTrue(all(v['age_ms'] is None for v in fields.values()))
        wire, result = self.construct(view)
        self.assertEqual(self.acoustic(wire), fields)
        self.assertEqual(wire['candidates'], []); self.assertEqual(wire['ready'], [])
        self.assertEqual(wire['dialogue'], '')
        self.assertEqual(wire['pending'][0]['kind'], 'native_voice')
        self.assertNotIn('PRIVATE_TRANSCRIPT', json.dumps(self.wire))
        self.assertNotIn('pcm":', json.dumps(fields))
        self.assertFalse(wire['op']['motion_allowed'])
        self.assertEqual(len(self.wire['json_schema']['oneOf']), 1)
        TRACES.append(dict(fixture_not_live=True, sensors=list(fields.values()),
            request_bytes=len(json.dumps(self.wire).encode()), fixture_usage=result['usage'], effect_posts=0))

    def test_actual_reader_pipe_status_to_normal_request_no_second_consumer(self):
        read_fd, write_fd = os.pipe()
        stdout = os.fdopen(read_fd, 'rb', buffering=0)
        class PipeProcess:
            dead = False
            def poll(self): return 0 if self.dead else None
            def terminate(self): self.dead = True
            def kill(self): self.dead = True
            def wait(self, timeout): self.dead = True; return 0
        process = PipeProcess(); process.stdout = stdout
        commands = []
        def factory(command, **kwargs): commands.append(command); return process
        self.pump.popen = factory
        published = threading.Event()
        original = self.pump._publish
        def publish(chunk, now, **kwargs): original(chunk, now, **kwargs); published.set()
        self.pump._publish = publish
        try:
            self.pump.start()
            for chunk in (QUIET, LOUD):
                published.clear(); self.remote.now += .03; self.local.now += .03
                begin = self.remote()
                if chunk == LOUD:
                    os.write(write_fd, chunk[:200])
                    limit = time.monotonic()+1
                    while self.pump.counters['read_calls'] < 2 and time.monotonic() < limit:
                        time.sleep(.001)
                    self.assertEqual(self.pump.counters['read_calls'], 2)
                    self.remote.now += .01; self.local.now += .01
                    os.write(write_fd, chunk[200:])
                else:
                    os.write(write_fd, chunk)
                self.assertTrue(published.wait(1))
                self.assertEqual(self.pump.acoustic['read_begin'], begin)
                self.assertEqual(self.pump.acoustic['read_end'], self.remote())
            wire, _ = self.construct(self.view())
            self.assertEqual(json.loads(self.acoustic(wire)['native.acoustic']['summary'])['rms'], 1000.)
            self.assertEqual(self.pump.counters['read_calls'], 3)
            self.assertEqual(self.pump.counters['read_bytes'], 1920)
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0][0], 'arecord')
            self.assertIsNone(self.pump.error)
        finally:
            self.pump.close(); os.close(write_fd)
        self.assertIsNone(self.pump.acoustic)
        self.assertFalse(self.a.capture_active)
        self.assertIsNone(self.pump.process)

    def test_latest_only_window_and_no_rms_vad_recomputation(self):
        calls = []
        self.a.vad.is_speech = lambda frame, rate: calls.append(1) or any(frame)
        for _ in range(80): self.feed()
        self.assertEqual(len(calls), 80*3)
        self.assertEqual(self.pump.acoustic['seq'], 80)
        self.assertEqual(self.pump.acoustic['window_ms'], 30.)
        self.assertFalse(any(isinstance(v, bytes) for v in self.pump.acoustic.values()))
        self.assertLessEqual(len(json.dumps(self.pump.acoustic)), 700)

    def test_stop_privacy_quiet_epoch_boot_owner_error_terminal(self):
        for change in ('off', 'privacy', 'quiet', 'mic_epoch', 'policy_epoch', 'boot', 'owner', 'error', 'stop'):
            with self.subTest(change=change):
                self.setUp_case(change)

    def setUp_case(self, change):
        # Independent authority copies avoid restoring a revoked scope.
        self.feed(); value = copy.deepcopy(self.a.status())
        if change == 'off': value['microphone_enabled'] = False
        elif change in ('privacy', 'quiet'): value['motion_policy']['privacy_all' if change == 'privacy' else 'quiet'] = True
        elif change == 'mic_epoch': value['microphone_epoch'] += 2
        elif change == 'policy_epoch': value['motion_policy']['epoch'] += 2
        elif change == 'boot': value['agent_boot_id'] = 'other-boot'
        elif change == 'owner': value['microphone_owner_id'] = 'foreign'
        elif change == 'error': value['microphone_state_error'] = 'error'
        else: value['listening'] = False
        observer = native.NativeAgent(SimpleNamespace(get=lambda path: self.a.operator_status() if path == '/operator' else value),
            SimpleNamespace(get=lambda path: self.a.operator_status()), {}, self.a.operator_status(),
            'fixture-hub', clock=self.local)
        with self.assertRaises(ValueError): observer.read()
        self.assertIsNotNone(observer.withdrawn)
        self.assertIsNone(observer.acoustic_watermark)

    def test_pump_stop_privacy_retire_clear_even_if_late_publish(self):
        for change in ('retire', 'off', 'quiet', 'privacy', 'stopping', 'epoch', 'boot'):
            self.feed()
            before = self.a.microphone_epoch
            if change == 'retire': self.pump.retire()
            elif change == 'off': self.a.microphone.enabled = False
            elif change in ('quiet', 'privacy'): self.policy['privacy_all' if change == 'privacy' else change] = True
            elif change == 'stopping': self.a.stopping.set()
            elif change == 'epoch': self.a.microphone_epoch += 1
            else: self.a.agent_boot_id = 'changed'
            self.pump._publish(LOUD, self.remote())
            self.assertIsNone(self.pump.acoustic_snapshot())
            self.assertIsNone(self.pump.acoustic)
            self.assertIsNone(self.pump.assembler.measurement)
            # End the subcase by replacing the source, not reviving its binding.
            self.a.microphone.enabled = True; self.policy.update(quiet=False, privacy_all=False)
            self.a.stopping.clear(); self.a.microphone_epoch = before
            self.a.agent_boot_id = '11111111-1111-4111-8111-111111111111'
            self.pump.retire()
            self.pump = pump_module.CapturePump(self.a, 8, clock=self.remote)
            self.a._capture_pump = self.pump
            self.addCleanup(self.pump.close)

    def test_playback_mask_tail_requires_new_clean_window_no_cross_mask_delta(self):
        self.feed(QUIET); self.feed()
        self.assertTrue(self.pump.acoustic['onset'])
        self.pump.output(True); self.feed()
        self.assert_unknown(self.view())
        self.pump.output(False); self.feed()
        self.assert_unknown(self.view())
        self.remote.now += .31; self.local.now += .31
        self.assertIsNone(self.pump.acoustic_snapshot())
        self.feed()
        value = json.loads(self.acoustic(self.view())['native.acoustic']['summary'])
        self.assertIsNone(value['delta']); self.assertIsNone(value['onset'])
        self.assertEqual(self.pump.acoustic['mask_generation'], 2)

    def test_calibration_has_no_borrowed_measurement_and_window_over_one_second_unknown(self):
        self.feed(); self.a.calibrated = False
        self.feed()
        self.assertIsNone(self.pump.acoustic)
        self.feed(LOUD*34)
        self.assertIsNone(self.pump.acoustic)

    def test_local_receipt_age_never_reaged_or_subtracted_from_remote_clock(self):
        self.feed(); view = self.view()
        first = self.native.latest['acoustic']['receipt_expires']
        self.local.now += .1
        self.native.latest = self.native.read()  # remote clock did not advance
        self.assertEqual(self.native.latest['acoustic']['receipt_expires'], first)
        self.local.now = first
        self.assert_unknown(self.state.snapshot(self.local()))
        self.assertIsNone(self.native.read()['acoustic'])
        self.assertIsNotNone(self.pump.acoustic)  # remote age and native age differ
        self.remote.now += .31
        self.assertIsNone(self.pump.acoustic_snapshot())

    def test_malformed_stale_masked_aba_values_rejected_without_invitation(self):
        self.feed(); original = self.a.status()
        cases = [dict(clock='hardware'), dict(reaction_usable=True), dict(capture_age_upper_ms=0),
            dict(read_age_s=.3), dict(read_age_s=-1), dict(rms=float('nan')), dict(seq=True),
            dict(window_ms=1001), dict(mask='suppressed'), dict(binding=[self.a.agent_boot_id, True, 3]),
            dict(binding=[self.a.agent_boot_id, 3, 3]), dict(source_generation=8), dict(read_call=100),
            dict(mask_generation=3), dict(read_end=100), dict(raw_pcm='PRIVATE')]
        for edits in cases:
            with self.subTest(edits=edits):
                value = copy.deepcopy(original); value['capture_acoustic'].update(edits)
                self.get_status = lambda: value
                self.assert_unknown(self.view())
        self.get_status = self.a.status
        self.view()
        original = self.a.status(); original['capture_acoustic']['seq'] = 0
        self.get_status = lambda: original
        self.assert_unknown(self.view())

    def test_sequence_mask_regression_same_seq_mutation_and_generation_fences(self):
        self.feed(); self.view(); first = self.a.status()
        self.feed(QUIET); self.view()
        replay = self.a.status(); replay['capture_acoustic'] = first['capture_acoustic']
        self.get_status = lambda: replay
        self.assert_unknown(self.view())
        self.get_status = self.a.status
        original = self.a.status(); original['capture_acoustic']['rms'] += 1
        self.get_status = lambda: original
        self.assert_unknown(self.view())
        self.get_status = self.a.status
        self.pump.output(True); self.pump.output(False)
        self.remote.now += .31; self.local.now += .31
        self.feed(); self.view()
        value = self.a.status(); value['capture_pcm']['mask_generation'] = 0
        value['capture_acoustic']['mask_generation'] = 0
        value['capture_acoustic']['seq'] += 1
        self.get_status = lambda: value
        self.assert_unknown(self.view())
        self.get_status = self.a.status
        self.pump.generation += 1
        with self.assertRaises(ValueError): self.native.read()
        self.assertIsNotNone(self.native.withdrawn)

    def test_gap_overflow_and_native_recovery_never_rearm_physical_context(self):
        for counter in ('gap_events', 'overflow_events'):
            self.feed(); self.pump.counters[counter] += 1
            self.assertIsNone(self.pump.acoustic_snapshot())
            self.assert_unknown(self.view())
        self.feed(); self.view()
        self.native.unavailable_since('fixture-gap', self.local())
        self.assertIsNone(self.native.acoustic_watermark)
        receipt = self.native.read()
        future = Future(); future.set_result(receipt)
        self.native.poll_job = SimpleNamespace(future=future)
        self.native.next_poll = math.inf
        self.native.advance()
        self.assertTrue(self.native.fresh(self.local()))
        self.assertTrue(self.native.physical_closed_after_gap)
        self.assertFalse(self.native.stock_allowed(self.local()))
        self.assert_unknown(self.state.snapshot(self.local()))
        gateway = SimpleNamespace(boot_id='fixture-compute')
        scheduler = native.NativeScheduler(self.cfg, gateway, self.native)
        scheduler.observation_generation -= 1
        scheduler.next_tick = math.inf
        scheduler.advance(self.local())
        self.assertTrue(scheduler.context_closed_after_gap)
        self.assertEqual(scheduler.next_context, math.inf)
        self.assertIsNone(scheduler.main_job)

    def test_late_composite_receipt_and_old_future_cannot_be_applied(self):
        self.feed(); self.view()
        binding = self.state.bind(self.local(), 6)
        original_deadline = binding.deadline
        old = self.hub_get
        def late(path): self.local.now += .301; return old(path)
        self.hub_get = late
        with self.assertRaises(native.NativeReadExpired): self.native.read()
        self.native.unavailable_since('late', self.local())
        self.state.apply(dict(a='wait', why='Synthetic old completion'), binding, self.local())
        self.assertEqual(binding.deadline, original_deadline)
        self.assertEqual(self.state.counts['decision_accepted'], 0)
        self.assertIsNone(self.state.stock_proposal)

    def test_new_descriptor_observations_recover_after_poll_gap_without_effect_rearm(self):
        self.feed(); self.view()
        self.native.unavailable_since('synthetic-poll-gap', self.local())
        self.feed(QUIET)
        future = Future(); future.set_result(self.native.read())
        self.native.poll_job = SimpleNamespace(future=future)
        self.native.next_poll = math.inf
        self.native.advance()
        self.state.observe()
        view = self.state.snapshot(self.local())
        values = json.loads(self.acoustic(view)['native.acoustic']['summary'])
        self.assertEqual(values['rms'], 0.)
        self.assertEqual(values['seq'], 2)
        self.assertTrue(self.native.physical_closed_after_gap)
        self.assertFalse(view['op']['motion_allowed'])
        self.assertFalse(self.native.stock_allowed(self.local()))

    def test_unknown_acoustic_motion_reply_and_second_main_rejected(self):
        self.feed(); self.view()
        for choice in (dict(a='explore', why='Fixture', motion='settle'),
                       dict(a='converse', why='Fixture', say='forbidden')):
            self.state.apply(choice, self.state.bind(self.local(), 6), self.local())
            self.assertIsNone(self.state.stock_proposal)
        for kind in ('utterance', 'workflow'):
            with self.assertRaises(ValueError): self.state.ingest(dict(type=kind), self.local())
        backend = ModelBackend(self.cfg)
        with self.assertRaises(BudgetRejected): backend.generate('main', 'forbidden')
        self.assertIsNone(self.native.stock_job)

    def test_budget_caps_unchanged_and_rejection_precedes_post(self):
        self.feed(); view = self.view()
        for i in range(20):
            self.state.sensors[str(i)] = SimpleNamespace(view=lambda now, muted: dict(id='extra', state='UNKNOWN', age_ms=None, summary=''))
        view = self.state.snapshot(self.local())
        self.assertLessEqual(len(view['sensors']), 12)
        self.assertTrue(all(len(v['summary']) <= 256 for v in view['sensors']))
        backend = ModelBackend(self.cfg); backend.count = lambda m, s: 5000
        backend.post = Mock(side_effect=AssertionError('Budget rejection must precede transport'))
        with self.assertRaises(BudgetRejected): backend.generate_loaded('fast', view)
        backend.post.assert_not_called()
        self.assertEqual(self.cfg['models']['fast']['input_cap_tokens'], 2744)
        self.assertEqual(self.cfg['models']['fast']['context_tokens'], 4096)

    def test_narrow_source_scope_and_frozen_preimages(self):
        pins = json.loads((BUNDLE/'source-manifest.json').read_text())
        for name, value in pins['payload'].items():
            self.assertEqual(hashlib.sha256((BUNDLE/'preimages'/name).read_bytes()).hexdigest(), value['before'])
        def without(raw, names):
            tree = ast.parse(raw)
            for cls in tree.body:
                if isinstance(cls, ast.ClassDef):
                    cls.body = [n for n in cls.body if getattr(n, 'name', None) not in names]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(without((BUNDLE/'preimages/agent.py').read_bytes(), {'status'}),
                         without((BUNDLE/'candidate/agent.py').read_bytes(), {'status'}))
        old = ast.parse((BUNDLE/'preimages/autonomous/native_agent.py').read_bytes())
        new = ast.parse((BUNDLE/'candidate/autonomous/native_agent.py').read_bytes())
        for name in ('GoalClockNativeAgent', 'GoalClockBinding', 'GoalClockState', 'NativeScheduler'):
            self.assertEqual(ast.dump(next(n for n in old.body if getattr(n, 'name', '') == name)),
                             ast.dump(next(n for n in new.body if getattr(n, 'name', '') == name)))
        forbidden = ('dispatch', 'admit_stock', 'execute_stock', 'send_settle', 'stock_allowed')
        for name in forbidden:
            methods = lambda tree: next(n for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == 'NativeAgent'
                                        for n in cls.body if getattr(n, 'name', '') == name)
            self.assertEqual(ast.dump(methods(old)), ast.dump(methods(new)))
        for name in ('guarded_control',):
            self.assertEqual(ast.dump(next(n for n in old.body if getattr(n, 'name', '') == name)),
                             ast.dump(next(n for n in new.body if getattr(n, 'name', '') == name)))


if __name__ == '__main__': unittest.main()
