"""Native metadata and existing Hub executor, entirely in process and offline."""
import copy
from concurrent.futures import Future
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from reachy_companion.client import compare_control_operator
from reachy_companion.config import Config, initialize
from reachy_companion.hub import Hub
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.context import ContextProvider
from reachy_companion.autonomous.gateway import ModelBackend, BudgetRejected, Gateway, fast_schema, fast_tuple_schema, tuple_choice
from reachy_companion.autonomous.native_agent import (NativeAgent, NativeScheduler, NativeClient,
    transient_read)
from reachy_companion.autonomous.native_agent_session import (
    NativeGateway, run_native_session, validate_lifecycle, MetadataSnapshots, exit_code)
from reachy_companion.autonomous.video_adapter import LatestFrameProcessor, decode_packet

ROOT = Path(__file__).resolve().parents[1]
MOVE = '00000000-0000-4000-8000-000000000001'


class FixtureGateway:
    boot_id = 'fixture-compute'
    def __init__(self, provider):
        self.provider = provider; self.views = []; self.ids = []; self.frames = 0
        self.choice = dict(a='wait', why='Fixture idle')
        self.entered = threading.Event(); self.release = threading.Event(); self.hold = False
        self.active = 0; self.max_active = 0; self.main_calls = 0
        self.quarantined = []
    def call(self, path):
        if path != '/health': raise AssertionError(path)
        return dict(compute_boot_id=self.boot_id, quarantined=self.quarantined,
                    busy=dict(fast=bool(self.active), main=False), conversation_owner='native_agent')
    def fast(self, request_id, view):
        self.active += 1; self.max_active = max(self.max_active, self.active)
        self.views.append(copy.deepcopy(view)); self.ids.append(request_id)
        try:
            if self.hold: self.entered.set(); self.release.wait(4)
            choice = copy.deepcopy(self.choice)
            if choice.get('motion') == 'settle' and not view['op']['motion_allowed']:
                choice = dict(a='wait', why='Fixture respects withdrawn motion capability')
            return dict(output=choice, request_id=request_id, compute_boot_id=self.boot_id)
        finally: self.active -= 1
    def main(self, task):
        self.main_calls += 1; raise AssertionError('Second conversation owner')
    def context(self, request_id, query, privacy, authority):
        output = self.provider.snapshot(query, privacy, authority.hub_boot_id, authority.operator_epoch)
        with self.provider.policy_lock:
            ticket = (dict(self.provider.scope), self.provider.video_generation, self.provider.video_admission)
        self.frames += 1
        pixels = b'P6\n1 1\n255\n' + bytes([self.frames % 256, 0, 0])
        meta = dict(video_protocol=2, audio_initialised=False, scope=ticket[0], admission_id=ticket[2],
            producer_boot_id='fixture-camera', seq=self.frames, frame_id='fixture-frame-'+str(self.frames),
            lineage_id='fixture-camera', frame_sha256=hashlib.sha256(pixels).hexdigest(), pts_ns=0, buffer_running_time_ns=0)
        raw = json.dumps(meta).encode()
        metadata, raw_pixels = decode_packet(struct.pack('!I', len(raw))+raw+pixels)
        self.provider.admit_video(metadata, raw_pixels, time.monotonic(), ticket)
        return dict(output=output, request_id=request_id, compute_boot_id=self.boot_id)
    def revoke_context(self, authority, terminal=False):
        return dict(output=self.provider.revoke(authority.hub_boot_id, authority.operator_epoch, terminal),
                    request_id='fixture-revoke', compute_boot_id=self.boot_id)


class NativeSessionTests(unittest.TestCase):
    def test_startup_timeout_is_explicit_bounded_and_does_not_change_default(self):
        client = NativeClient('http://127.0.0.1:8080', 'f'*32)
        with patch.object(client.opener, 'open', side_effect=TimeoutError('startup status line')) as opened:
            with self.assertRaisesRegex(TimeoutError, 'startup status line'):
                client.get('/status', setup_hardware=True)
            self.assertEqual(opened.call_args.kwargs['timeout'], 2)
            with self.assertRaises(TimeoutError): client.get('/status')
            self.assertEqual(opened.call_args.kwargs['timeout'], .3)
            opened.reset_mock()
            with self.assertRaises(ValueError): client.get('/control/operator', setup_hardware=True)
            opened.assert_not_called()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size):
                self.size = size
                return b'x' * size
        response = Response()
        with patch.object(client.opener, 'open', return_value=response):
            with self.assertRaisesRegex(ValueError, 'Bounded native receipt'):
                client.get('/status', setup_hardware=True)
        self.assertEqual(response.size, 65537)

    def test_startup_failure_prevents_scheduler_and_requires_fresh_native_read(self):
        import sys
        from types import SimpleNamespace
        from reachy_companion.autonomous import native_agent_session as session
        output = Path(self.tmp.name)/'startup-report.json'
        token = Path(self.tmp.name)/'token'; token.write_text('f'*32)
        argv = ['native', '--config', 'unused', '--companion-config', 'unused',
                '--token-file', str(token), '--output', str(output),
                '--agent-url', 'http://127.0.0.1:8090', '--hub-url', 'http://127.0.0.1:8080',
                '--agent-boot', 'fixture-agent', '--microphone-epoch', '1', '--policy-epoch', '2',
                '--controller', 'fixture', '--allow-native-observation']
        for failure in ('bootstrap', 'native'):
            calls = []
            def get(path, **kwargs):
                calls.append((path, kwargs))
                if path == '/control/operator': return self.operator
                if failure == 'bootstrap': raise TimeoutError('bootstrap')
                return dict(stock_motion=dict(hub_boot_id='fixture-hub'))
            client = SimpleNamespace(get=get)
            with patch.object(sys, 'argv', argv), patch.object(session, 'load', return_value=self.cfg), \
                    patch.object(session, 'session_context'), patch('reachy_companion.config.Config', return_value=self.companion), \
                    patch.object(session, 'NativeClient', return_value=client), \
                    patch.object(session, 'NativeAgent') as native, patch.object(session, 'NativeScheduler') as scheduler:
                native.return_value.read.side_effect = TimeoutError('native')
                with self.assertRaisesRegex(TimeoutError, failure): session.main()
                scheduler.assert_not_called()
                self.assertEqual(calls, [('/control/operator', {}), ('/status', dict(setup_hardware=True))])
                if failure == 'bootstrap': native.assert_not_called()
                else: native.return_value.read.assert_called_once_with()
                self.assertFalse(output.exists())

    def test_configured_status_transport_keeps_endpoint_pin_and_acks_before_body(self):
        from types import SimpleNamespace
        configured = 'http://192.168.2.158:8090'
        for url in (configured+'/', 'http://192.168.2.159:8090', configured+'/status',
                    'http://user@192.168.2.158:8090', configured+'?x=1'):
            with self.assertRaises(ValueError):
                NativeClient(url, 'f'*32, configured_url=configured)
        events = []
        sock = SimpleNamespace(setsockopt=lambda *args: events.append(('ack', args)))
        class Response:
            fp = SimpleNamespace(raw=SimpleNamespace(_sock=sock))
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): events.append(('read', size)); return b'{"ok":true}'
        with patch('socket.TCP_QUICKACK', 12, create=True):
            client = NativeClient(configured, 'f'*32, configured_url=configured, quick_ack=True)
            with patch.object(client.opener, 'open', return_value=Response()) as opened:
                self.assertEqual(client.get('/operator'), {'ok': True})
            self.assertEqual([x[0] for x in events], ['ack', 'read'])
            self.assertEqual(events[-1][1], 65537)
            self.assertEqual(opened.call_args.kwargs['timeout'], .3)
            self.assertEqual(opened.call_args.args[0].get_header('Authorization'), 'Bearer '+'f'*32)

    def test_explicit_operator_goal_is_data_without_utterance(self):
        goal = dict(id='one-settle', version=1, text='One small settle, then observe',
                    changed_at='2026-10-17T02:00:00Z', reason='Operator movement request',
                    evidence_ids=[], origin='operator')
        self.cfg['native_agent']['operator_goal'] = goal
        path = Path(self.tmp.name)/'goal.json'
        valid_config = load(ROOT/'config.autonomous.native-agent.example.json')
        valid_config['native_agent']['operator_goal'] = goal
        path.write_text(json.dumps(valid_config))
        self.assertEqual(load(path)['native_agent']['operator_goal'], goal)
        self.native.latest = self.native.read()
        self.scheduler.state.observe()
        view = self.scheduler.state.snapshot(time.monotonic())
        self.assertEqual(view['goal'], goal)
        self.assertEqual(view['candidates'], [])
        self.assertEqual(view['dialogue'], '')
        view['goal']['text'] = 'must not mutate config'
        self.assertEqual(goal['text'], 'One small settle, then observe')
        valid_config['native_agent']['operator_goal']['origin'] = 'agent'
        path.write_text(json.dumps(valid_config))
        with self.assertRaises(ValueError): load(path)

    def setUp(self):
        for name in ('socket.socket', 'subprocess.Popen'):
            guard = patch(name, side_effect=AssertionError('Offline only: no socket/process/device'))
            guard.start(); self.addCleanup(guard.stop)
        for module, name in [('audio_peer','AudioPeer'), ('audio_adapter','AudioAdapter'),
                             ('speech_adapter','SpeechAdapter'), ('motion_adapter','MotionAdapter')]:
            guard = patch('reachy_companion.autonomous.'+module+'.'+name,
                          side_effect=AssertionError('No second owner'))
            guard.start(); self.addCleanup(guard.stop)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        shutil.copy(ROOT/'config.example.json', root); shutil.copytree(ROOT/'profiles', root/'profiles')
        initialize(root); self.companion = Config(root/'config.local.json')
        self.companion.data['guarded_motion'].update(enabled=True, transport='stock')
        self.companion.data['motion']['move_poll_seconds'] = .001
        self.hub = Hub(self.companion)
        self.operator = dict(agent_boot_id='fixture-agent', microphone_epoch=1, microphone_enabled=True,
            microphone_owner_id=None, motion_policy_owner_id=None, expression_version=1,
            microphone_state_error=None, phase='processing', capture_active=True, listening=True,
            motion_policy=dict(epoch=2, motor_enabled=True, quiet=False, privacy_all=False))
        self.pcm = dict(source_generation=3, read_bytes=0, read_frames=0, read_calls=0, gap_events=0,
                        overflow_events=0, retired=False, clock='monotonic_read_receipt')
        self.turns = 0; self.active_moves = []; self.writes = []; self.gets = []
        self.status_entered = threading.Event(); self.status_release = threading.Event(); self.hold_status = False
        self.hub.agent = lambda path: copy.deepcopy(self.operator)
        self.hub.factory = self.factory
        outer = self
        class Agent:
            def get(_, path):
                outer.gets.append(('agent', path))
                if path == '/operator': return copy.deepcopy(outer.operator)
                if path != '/status': raise AssertionError(path)
                if outer.hold_status: outer.status_entered.set(); outer.status_release.wait(4)
                outer.pcm['read_bytes'] += 3200; outer.pcm['read_frames'] += 1600; outer.pcm['read_calls'] += 1
                return dict(copy.deepcopy(outer.operator), capture_pcm=copy.deepcopy(outer.pcm), turns=outer.turns,
                            last_transcript='private fixture text must never enter the bridge')
        class HubClient:
            url = 'http://127.0.0.1:8080'
            def get(_, path, **kwargs):
                outer.gets.append(('hub', path))
                if path == '/control/operator': return copy.deepcopy(outer.operator)
                if path == '/status': return outer.hub.status()
                raise AssertionError(path)
        self.native = NativeAgent(Agent(), HubClient(), self.companion, copy.deepcopy(self.operator), self.hub.boot_id)
        self.provider = ContextProvider(dict(memory_path=str(root/'context.sqlite'), namespaces=['normal']), 'fixture-compute')
        self.provider.video_worker = LatestFrameProcessor(self.provider.video_completed)
        self.addCleanup(self.provider.close)
        self.gateway = FixtureGateway(self.provider)
        self.cfg = load(ROOT/'config.autonomous.native-agent.example.json')
        self.cfg.update(period_s=.015, fast_deadline_s=1); self.cfg['context']['refresh_s'] = .02
        self.scheduler = NativeScheduler(self.cfg, self.gateway, self.native)
        self.addCleanup(self.scheduler.close)
        self.stop = threading.Event(); self.report = []; self.runner = None
        self.addCleanup(self.finish)

    def factory(self, path, payload=None):
        if payload is not None:
            self.writes.append((path, copy.deepcopy(payload)))
            if path == '/api/move/goto': self.active_moves = [dict(uuid=MOVE)]; return dict(uuid=MOVE)
            if path == '/api/move/stop': self.active_moves = []; return {}
            raise AssertionError(path)
        if path == '/api/daemon/status': return dict(state='running', error=None, backend_status=dict(ready=True))
        if path == '/api/daemon/robot-app-lock-status': return dict(state='free')
        if path == '/api/state/full': return dict(control_mode='enabled')
        if path == '/api/move/running': self.active_moves = []; return []
        raise AssertionError(path)

    def guarded(self, config, url, path, payload, expected, **kwargs):
        self.assertEqual(path, '/actions/expression'); self.assertLess(time.monotonic(), kwargs['deadline'])
        compare_control_operator(self.operator, expected)
        self.assertTrue(kwargs['admission']())
        return self.hub.expression(payload)

    def start(self):
        self.runner = threading.Thread(target=lambda: self.report.append(run_native_session(
            self.scheduler, self.stop, 2, lambda value: None)))
        self.runner.start()

    def wait(self, predicate):
        deadline = time.monotonic()+2
        while not predicate() and time.monotonic() < deadline: time.sleep(.005)
        self.assertTrue(predicate(), self.report)

    def finish(self):
        self.stop.set(); self.gateway.release.set(); self.status_release.set()
        if self.runner: self.runner.join(3)
        for job in (self.scheduler.fast_job, self.scheduler.context_job, self.scheduler.context_terminal_job,
                    self.native.poll_job, self.native.stock_job):
            if job: job.thread.join(1)

    def test_silent_ticks_native_pcm_busy_voice_unknown_camera_and_no_second_main(self):
        self.start()
        self.wait(lambda: self.scheduler.state.counts['decision_accepted'] >= 12 and self.native.polls >= 4)
        views = list(self.gateway.views)
        pcm = [json.loads(next(s['summary'] for s in v['sensors'] if s['id']=='native.pcm')) for v in views]
        elapsed = [json.loads(next(s['summary'] for s in v['sensors'] if s['id']=='native.elapsed'))['elapsed_ms'] for v in views]
        self.assertGreater(pcm[-1]['read_bytes'], pcm[0]['read_bytes'])
        self.assertGreater(pcm[-1]['read_frames'], pcm[0]['read_frames'])
        self.assertEqual({p['source_generation'] for p in pcm}, {3})
        self.assertGreater(elapsed[-1], elapsed[0])
        for view in views:
            self.assertEqual(view['dialogue'], ''); self.assertEqual(view['candidates'], [])
            self.assertEqual(view['pending'][0]['status'], 'execution_busy_phase_observed_completion_UNKNOWN')
            self.assertLessEqual(len(view['sensors']), 12); self.assertLessEqual(len(view['pending']), 8)
            for sensor in view['sensors']:
                if sensor['id'] == 'camera.pixel_quality':
                    self.assertIn(sensor['state'], ('unknown','no_data','stale'))
                    self.assertIsNone(sensor['age_bounds_ms']['upper']); self.assertEqual(sensor['summary'], '')
        self.assertTrue(any(s['id']=='camera.pixel_quality' and s.get('source_id') for v in views for s in v['sensors']))
        self.assertLessEqual(self.provider.video_worker.status()['pending_raw_frames'], 1)
        self.assertEqual(self.gateway.max_active, 1); self.assertEqual(self.gateway.main_calls, 0)
        self.assertIsNone(self.scheduler.audio_adapter); self.assertIsNone(self.scheduler.speech_adapter)
        self.assertIsNone(self.scheduler.motion_adapter); self.assertIsNone(self.scheduler.main_job)
        self.assertEqual(self.scheduler.state.counts['new_turn'], 0)
        self.turns = 1; self.operator['phase'] = 'listening'
        self.wait(lambda: any(json.loads(s['summary']).get('turns') == 1 and not v['pending']
            for v in self.gateway.views for s in v['sensors'] if s['id']=='native.voice'))
        self.assertEqual(self.scheduler.state.counts['new_turn'], 0)
        self.stop.set(); self.runner.join(3)
        report = self.report[0]
        self.assertTrue(report['accepted'], report); self.assertTrue(report['cleanup_verified'], report)
        self.assertGreaterEqual(len({d['request_id'] for d in report['decisions']}), 12)
        self.assertNotIn('private fixture text', json.dumps(report)); self.assertFalse(report['live_acceptance'])
        self.assertFalse(report['normal_agent_stopped']); self.assertFalse(report['scheduler_speech_enabled'])
        self.assertLessEqual(self.native.polls, int(report['elapsed_s']/.1)+1)
        self.offline_metrics = dict(accepted_ids=len(report['decisions']), native_polls=self.native.polls,
            pcm_delta_bytes=pcm[-1]['read_bytes']-pcm[0]['read_bytes'], max_fast_slots=self.gateway.max_active,
            fixture_not_hardware=True)

    def test_held_fast_does_not_block_polling_or_start_second_slot(self):
        self.gateway.hold = True; self.start(); self.assertTrue(self.gateway.entered.wait(1))
        self.wait(lambda: self.native.polls >= 4)
        self.assertEqual(len(self.gateway.ids), 1); self.assertEqual(self.gateway.max_active, 1)
        self.assertGreater(self.native.latest['pcm']['read_bytes'], 3200)
        self.assertGreater(self.scheduler.state.counts['tick_busy_gap'], 4)
        self.gateway.hold = False; self.gateway.release.set()
        self.wait(lambda: self.scheduler.state.counts['decision_accepted'] >= 10)

    def test_remote_unknown_is_not_cleaned_up_by_completed_local_futures(self):
        self.start(); self.wait(lambda: self.scheduler.state.counts['decision_accepted'] >= 10)
        self.gateway.quarantined = ['fast']; self.stop.set(); self.runner.join(3)
        self.assertFalse(self.report[0]['accepted']); self.assertFalse(self.report[0]['cleanup_verified'])
        self.assertEqual(self.report[0]['compute_after']['quarantined'], ['fast'])

    def test_observation_without_accepted_decisions_is_not_endpoint_readiness(self):
        self.gateway.hold = True; self.start(); self.assertTrue(self.gateway.entered.wait(1))
        self.stop.set(); self.gateway.release.set(); self.runner.join(3)
        self.assertFalse(self.report[0]['accepted'])
        self.assertEqual(self.report[0]['minimum_accepted_decisions'], 10)
        self.assertEqual(self.report[0]['counts'].get('decision_accepted', 0), 0)

    def test_unavailable_keeps_slots_no_grants_and_controller_stop_is_finite(self):
        self.gateway.hold = True; self.start(); self.assertTrue(self.gateway.entered.wait(1))
        self.hold_status = True; self.assertTrue(self.status_entered.wait(1))
        self.wait(lambda: self.native.unavailable)
        self.assertFalse(self.scheduler.closed); self.assertIsNone(self.native.withdrawn)
        fast, poll = self.scheduler.fast_job, self.native.poll_job
        frames, calls = self.gateway.frames, len(self.gateway.ids)
        time.sleep(.12)
        self.assertIs(self.scheduler.fast_job, fast); self.assertIs(self.native.poll_job, poll)
        self.assertEqual((self.gateway.frames, len(self.gateway.ids)), (frames, calls))
        self.assertEqual(self.native.polls, 2); self.assertTrue(self.native.busy()['native_poll'])
        self.stop.set()
        self.gateway.release.set(); self.status_release.set(); self.runner.join(3)
        self.assertFalse(self.runner.is_alive())
        self.assertFalse(self.report[0]['accepted']); self.assertEqual(self.report[0]['reason'], 'controller_stop')
        self.assertTrue(self.report[0]['cleanup_verified'], self.report[0])
        self.assertGreater(self.report[0]['observation']['unavailable_s'], .1)
        self.assertTrue(self.report[0]['context_terminal_revoke']['output']['terminal'])
        self.assertEqual(self.scheduler.state.counts['decision_accepted'], 0)
        self.scheduler.advance(); self.assertEqual(len(self.gateway.ids), 1)

    @staticmethod
    def pending(*args):
        return SimpleNamespace(future=Future(), thread=SimpleNamespace(join=lambda *_: None), args=args)

    def test_n2_exact_timestamps_pending_read_recovers_but_old_fast_never_does(self):
        clock = [228988.631225]
        self.native.clock = lambda: clock[0]
        self.native.latest = self.native.read(); self.scheduler.state.observe()
        self.native.allow_stock = True
        state = self.scheduler.state
        binding = state.bind(clock[0], 6)
        self.scheduler.binding = binding
        fast = self.scheduler.fast_job = self.pending()
        poll = self.native.poll_job = self.pending()
        self.native.next_poll = 228988.735255+.1
        self.scheduler.next_tick = 228988.7
        receipt = copy.deepcopy(self.native.latest)
        receipt['received'] = 228988.735255
        receipt['pcm'].update(read_bytes=6400, read_frames=3200, read_calls=2)
        with patch('reachy_companion.autonomous.native_agent.Job', side_effect=self.pending), \
                patch('reachy_companion.autonomous.runtime.Job', side_effect=self.pending):
            clock[0] = 228988.931226
            self.scheduler.advance()
            self.assertTrue(self.native.unavailable); self.assertFalse(self.scheduler.closed)
            self.assertIs(self.native.poll_job, poll); self.assertIs(self.scheduler.fast_job, fast)
            self.assertEqual(self.native.generation, 1)
            stale = state.snapshot(clock[0])
            pcm = next(s for s in stale['sensors'] if s['id']=='native.pcm')
            voice = next(s for s in stale['sensors'] if s['id']=='native.voice')
            self.assertEqual(pcm['state'], 'stale'); self.assertGreaterEqual(pcm['age_ms'], 300)
            self.assertEqual(json.loads(voice['summary'])['phase'], 'UNKNOWN')
            self.assertFalse(stale['op']['motion_allowed'])
            self.assertTrue(self.scheduler.context_closed_after_gap)
            clock[0] = 228988.994917
            poll.future.set_result(receipt); self.scheduler.advance()
            self.assertFalse(self.native.unavailable); self.assertEqual(self.native.recoveries, 1)
            self.assertEqual(self.native.latest['received'], 228988.735255)
            self.assertIs(self.scheduler.fast_job, fast)  # busy was never cancelled/replaced
            fast.future.set_result(dict(output=dict(a='wait', why='Old response'),
                request_id=binding.request_id, compute_boot_id=self.gateway.boot_id))
            clock[0] += .02; self.scheduler.advance()
            self.assertEqual(state.counts['native_decision_discarded'], 1)
            self.assertEqual(state.counts['decision_accepted'], 0)
            self.assertIsNot(self.scheduler.fast_job, fast)
            new = self.scheduler.binding
            self.assertNotEqual(new.request_id, binding.request_id)
            self.scheduler.fast_job.future.set_result(dict(output=dict(a='wait', why='Fresh response'),
                request_id=new.request_id, compute_boot_id=self.gateway.boot_id))
            clock[0] += .005; self.scheduler.advance()
            self.assertEqual(state.counts['decision_accepted'], 1)
            self.assertFalse(self.native.stock_allowed(clock[0]))  # conservative physical closure persists
            report = self.native.observation_report(clock[0])
            self.assertAlmostEqual(report['unavailable_s'], 228988.994917-(228988.631225+.3))
            self.assertTrue(report['physical_closed_after_gap'])

    def test_only_narrow_read_failures_recover_at_normal_cadence(self):
        from urllib.error import HTTPError, URLError
        failures = [TimeoutError(), ConnectionResetError(), URLError(ConnectionRefusedError())]
        terminal = [HTTPError('fixture', 503, 'unavailable', {}, None),
                    HTTPError('fixture', 401, 'auth', {}, None), ValueError(), RuntimeError(), OSError('unknown')]
        for exc in terminal: self.assertFalse(transient_read(exc), type(exc).__name__)
        clock = [100.]
        self.native.clock = lambda: clock[0]
        with patch('reachy_companion.autonomous.native_agent.Job', side_effect=self.pending):
            for exc in failures:
                job = self.native.poll_job = self.pending(); job.future.set_exception(exc)
                self.native.advance()
                self.assertIsNone(self.native.withdrawn); self.assertTrue(self.native.unavailable)
                replacement, polls = self.native.poll_job, self.native.polls
                self.native.advance(); self.native.advance()
                self.assertIs(self.native.poll_job, replacement); self.assertEqual(self.native.polls, polls)
                clock[0] += .1
            self.assertEqual(self.native.read_failures, 3)
            late = self.native.read(); late['received'] -= .31
            self.native.poll_job = self.pending(); self.native.poll_job.future.set_result(late)
            self.native.advance()
            self.assertTrue(self.native.unavailable); self.assertIsNone(self.native.latest)
            self.assertEqual(self.native.late_receipts, 1)

    def test_terminal_evidence_is_checked_before_next_read_or_expiry(self):
        original = copy.deepcopy(self.operator)
        for field, value in [('agent_boot_id', 'new'), ('microphone_epoch', 2),
                ('microphone_owner_id', 'owner'), ('motion_policy_owner_id', 'owner'),
                ('listening', False), ('microphone_epoch', True)]:
            self.native.withdrawn = None  # independent fixture session per case
            self.operator.clear(); self.operator.update(copy.deepcopy(original)); self.operator[field] = value
            self.gets.clear()
            with self.assertRaises(ValueError): self.native.read()
            self.assertEqual(self.gets, [('agent', '/operator')])
            self.assertIsNotNone(self.native.withdrawn)
        self.native.withdrawn = None
        self.operator.clear(); self.operator.update(original)
        self.native.latest = self.native.read()
        # Revoke in status must be retained even though the final leg would time out.
        self.operator['motion_policy']['privacy_all'] = True
        with patch.object(self.native.hub, 'get', side_effect=TimeoutError()) as hub:
            with self.assertRaises(ValueError): self.native.read()
            hub.assert_not_called()
        self.operator['motion_policy']['privacy_all'] = False
        self.native.poll_job = self.pending()
        self.native.poll_job.future.set_result(copy.deepcopy(self.native.latest))
        self.scheduler.advance()
        self.assertTrue(self.scheduler.closed); self.assertIsNotNone(self.native.withdrawn)

    def test_regression_status_revoke_precedes_later_hub_timeout(self):
        self.native.latest = self.native.read()
        self.pcm['read_calls'] = -1  # next actual fixture read becomes 0, below the previous 1
        with patch.object(self.native.hub, 'get', side_effect=TimeoutError()) as hub:
            with self.assertRaisesRegex(ValueError, 'regression'): self.native.read()
            hub.assert_not_called()
        self.assertIsNotNone(self.native.withdrawn)

    def test_stock_proposal_uses_original_receipt_deadline(self):
        clock = [100.]
        self.native.clock = lambda: clock[0]
        self.native.latest = self.native.read(); self.scheduler.state.observe(); self.native.allow_stock = True
        state = self.scheduler.state; binding = state.bind(clock[0], 6)
        clock[0] += .25
        state.apply(dict(a='explore', why='Fixture', motion='settle'), binding, clock[0])
        self.assertEqual(state.stock_proposal['deadline'], 100.3)
        self.assertEqual(state.stock_proposal['generation'], 0)
        self.native.unavailable_since('fixture', clock[0]); self.scheduler.advance()
        self.assertIsNone(state.stock_proposal)

    def stock_transport(self, before_send=None):
        sent = []
        sock = SimpleNamespace(settimeout=lambda *_: None, close=lambda: None,
                               send=lambda raw: sent.append(bytes(raw)) or len(raw))
        def connect(connection): connection.sock = sock
        def read(*args, **kwargs):
            if before_send: before_send()
            return copy.deepcopy(self.operator), time.monotonic()
        for guard in (patch('http.client.HTTPConnection.connect', connect),
                      patch('reachy_companion.autonomous.native_agent._demo_read', side_effect=read)):
            guard.start(); self.addCleanup(guard.stop)
        return sent

    def proposal(self):
        self.native.latest = self.native.read(); self.native.allow_stock = True
        return dict(request_id='fixture-stock', operator=copy.deepcopy(self.operator),
                    generation=self.native.generation, deadline=self.native.latest['received']+.3)

    def test_stock_gap_between_guarded_authority_read_and_socket_send_has_zero_post(self):
        proposal = self.proposal()
        def recover_before_send():
            self.native.unavailable_since('barrier', time.monotonic())
            self.native.poll_job = self.pending()
            self.native.poll_job.future.set_result(self.native.read())
            with patch('reachy_companion.autonomous.native_agent.Job', side_effect=self.pending):
                self.native.advance()
            self.assertFalse(self.native.unavailable)
            self.assertEqual(self.native.recoveries, 1)
        sent = self.stock_transport(recover_before_send)
        self.assertTrue(self.native.dispatch(proposal))
        self.wait(lambda: self.native.stock_job.future.done())
        self.native.advance()
        self.assertEqual(sent, [])
        self.assertTrue(self.native.stock_used); self.assertFalse(self.native.stock_unknown)
        self.assertEqual(self.native.stock_receipt['completion'], 'not_dispatched')
        self.assertFalse(self.native.dispatch(proposal))

    def test_sent_stock_lost_response_is_terminal_unknown_and_never_replayed(self):
        proposal = self.proposal(); sent = self.stock_transport()
        with patch('http.client.HTTPConnection.getresponse', side_effect=TimeoutError('lost response')):
            self.assertTrue(self.native.dispatch(proposal))
            self.wait(lambda: self.native.stock_job.future.done())
        self.scheduler.advance()
        self.assertTrue(self.scheduler.closed); self.assertEqual(self.native.withdrawn, 'stock_outcome_UNKNOWN')
        self.assertTrue(self.native.stock_used); self.assertTrue(self.native.stock_unknown)
        self.assertEqual(self.native.stock_receipt['completion'], 'UNKNOWN')
        self.native.latest = self.native.read()  # same values cannot restore a terminal session
        self.scheduler.advance(); self.assertFalse(self.native.dispatch(proposal))
        self.assertEqual(sum(raw.startswith(b'POST ') for raw in sent), 1)

    def test_authority_and_privacy_revoke_no_late_decision_no_auto_reconnect(self):
        self.gateway.hold = True; self.start(); self.assertTrue(self.gateway.entered.wait(1))
        with self.provider.policy_lock:
            old = (dict(self.provider.scope), self.provider.video_generation, self.provider.video_admission)
        self.operator['microphone_epoch'] += 1; self.operator['motion_policy']['privacy_all'] = True
        self.wait(lambda: self.scheduler.closed)
        self.gateway.release.set(); self.runner.join(3)
        self.assertFalse(self.report[0]['accepted']); self.assertEqual(self.scheduler.state.counts['decision_accepted'], 0)
        self.assertFalse(self.provider.video_current(old))
        self.assertFalse(self.writes)

    def test_stock_settle_once_through_existing_hub_with_valid_grant(self):
        self.native.allow_stock = True; self.gateway.choice = dict(a='explore', why='Fixture settle', motion='settle')
        with patch('reachy_companion.autonomous.native_agent.guarded_control', side_effect=self.guarded) as send:
            self.start(); self.wait(lambda: self.native.stock_receipt is not None)
            self.wait(lambda: len(self.gateway.ids) >= 12)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(self.native.stock_receipt['completion'], 'observed')
            self.assertFalse(self.native.stock_receipt['pose_verified'])
            self.assertEqual([path for path, _ in self.writes], ['/api/move/goto']*2)
            self.assertIsNone(self.hub.stock_owned); self.assertFalse(self.hub.stock_unknown)
            self.assertFalse(self.hub.lock.locked())
            self.stop.set(); self.runner.join(3)
            self.assertTrue(self.report[0]['accepted'], self.report[0])
            self.assertTrue(self.report[0]['stock_dispatch_observed'])

    def test_revoke_inside_existing_hub_before_effect_makes_no_move_no_retry(self):
        self.native.allow_stock = True; self.gateway.choice = dict(a='explore', why='Fixture settle', motion='settle')
        def revoke(config, url, path, payload, expected, **kwargs):
            self.operator['motion_policy']['epoch'] += 1
            return self.hub.expression(payload)
        with patch('reachy_companion.autonomous.native_agent.guarded_control', side_effect=revoke) as send:
            self.start(); self.wait(lambda: self.native.stock_unknown)
            self.assertEqual(send.call_count, 1); self.assertFalse(self.writes)
            self.assertEqual(self.native.stock_receipt['completion'], 'UNKNOWN')

    def test_local_close_or_expression_revoke_before_post_makes_no_dispatch(self):
        self.native.allow_stock = True
        for kind in ('close', 'expression'):
            with self.subTest(kind=kind):
                self.native.closed = False
                receipt = self.native.read(); self.native.latest = receipt
                proposal = dict(request_id='fixture', operator=copy.deepcopy(self.operator),
                                generation=self.native.generation, deadline=receipt['received']+.3)
                if kind == 'close': self.native.close()
                else: self.operator['expression_version'] += 1
                with patch('reachy_companion.autonomous.native_agent.guarded_control') as send:
                    result = self.native.execute_stock(proposal)
                    self.assertEqual(result['completion'], 'not_dispatched'); send.assert_not_called()
        self.assertFalse(self.writes)

    def test_legacy_main_speech_and_other_motor_capabilities_are_rejected(self):
        self.native.latest = self.native.read(); self.scheduler.state.observe()
        for event in (dict(type='utterance', text='fixture'), dict(type='workflow', value='fixture')):
            with self.assertRaises(ValueError): self.scheduler.ingest(event)
        for choice in (dict(a='think', why='fixture', start=dict(type='main', input_ref='fake')),
                       dict(a='converse', why='fixture', commit='fake'), dict(a='converse', why='fixture', say='fixture'),
                       dict(a='explore', why='fixture', motion='attentive')):
            now=time.monotonic(); self.scheduler.state.apply(choice, self.scheduler.state.bind(now, 1), now)
        self.assertFalse(self.scheduler.state.tasks); self.assertFalse(self.scheduler.state.speech_proposals)
        self.assertFalse(self.writes); self.assertEqual(self.gateway.main_calls, 0)
        backend = ModelBackend(self.cfg)
        with self.assertRaises(BudgetRejected): backend.generate('main', 'fixture')
        with self.assertRaises(BudgetRejected): backend.generate_loaded('main', 'fixture')
        gateway = NativeGateway.__new__(NativeGateway)
        with self.assertRaises(ValueError): gateway.call('/main', {})
        with self.assertRaises(ValueError): gateway.main(None)
        self.assertEqual(Gateway(backend).health()['conversation_owner'], 'native_agent')

    def test_gateway_native_object_and_tuple_schema_admit_settle_only(self):
        from jsonschema import Draft202012Validator, Draft7Validator
        self.native.latest = self.native.read(); self.scheduler.state.observe(); self.native.allow_stock = True
        view = self.scheduler.state.snapshot(time.monotonic())
        Draft202012Validator(fast_schema(view, 'settle')).validate(dict(a='explore', why='fixture', motion='settle'))
        Draft7Validator(fast_tuple_schema(view, 'settle')).validate(['explore','settle','fixture'])
        self.assertEqual(tuple_choice(['explore','settle','fixture'],view,'settle')['motion'], 'settle')
        with self.assertRaises(ValueError): tuple_choice(['explore','attentive','fixture'],view,'settle')
        self.assertFalse(Draft202012Validator(fast_schema(view,'settle')).is_valid(dict(a='explore',why='fixture',motion='attentive')))
        for wire in ('object', 'tuple'):
            self.cfg['models']['fast'].update(completion_backend='llama_native', decision_format=wire,
                base_url='http://127.0.0.1:1')
            backend = ModelBackend(self.cfg)
            text = json.dumps(['explore','settle','fixture'] if wire == 'tuple' else dict(a='explore',why='fixture',motion='settle'))
            with patch.object(backend, 'count', return_value=8), patch.object(backend, 'post',
                    return_value=dict(content=text, stop_type='eos')) as generate:
                self.assertEqual(backend.generate_loaded('fast',view)['output']['motion'], 'settle')
                payload = generate.call_args.args[1]
                self.assertIn('normal Agent', payload['prompt'])
                self.assertIn('settle',json.dumps(payload['json_schema']))

    def test_read_auth_bounds_and_a1_required_metadata(self):
        for url in ('http://192.168.2.158:8090', 'http://user@localhost', 'https://localhost', 'http://localhost/x'):
            with self.assertRaises(ValueError): NativeClient(url, 'f'*32)
        client = NativeClient('http://127.0.0.1:1', 'f'*32)
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size):
                self.size = size; return b'x'*size
        response = Response()
        with patch.object(client.opener, 'open', return_value=response) as request:
            with self.assertRaises(ValueError): client.get('/status')
            self.assertEqual(response.size, 65537)
            self.assertEqual(request.call_args.args[0].get_header('Authorization'), 'Bearer '+'f'*32)
            self.assertEqual(request.call_args.kwargs['timeout'], .3)
        self.pcm.pop('clock')
        with self.assertRaises(ValueError): self.native.read()

    @staticmethod
    def immediate(function, *args):
        future = Future()
        try: future.set_result(function(*args))
        except Exception as exc: future.set_exception(exc)
        return SimpleNamespace(future=future, thread=SimpleNamespace(join=lambda *_: None))

    def test_service_crosses_finite_cap_with_one_scheduler_and_terminal_revoke(self):
        self.cfg['context']['enabled'] = False
        self.cfg.update(period_s=3, fast_deadline_s=6, ledger_cap=16)
        self.scheduler.state.ledger = __import__('collections').deque(maxlen=16)
        clock = [100.]
        self.native.clock = lambda: clock[0]
        outer = self
        class Stop:
            stopped = False
            def is_set(self): return self.stopped
            def set(self): self.stopped = True
            def wait(self, seconds):
                clock[0] += .05
                if clock[0] > 290: outer.operator['motion_policy']['privacy_all'] = True
        stop = Stop(); published = []
        with patch('time.monotonic', side_effect=lambda: clock[0]), \
                patch('reachy_companion.autonomous.native_agent.Job', side_effect=self.immediate), \
                patch('reachy_companion.autonomous.runtime.Job', side_effect=self.immediate), \
                patch('reachy_companion.autonomous.native_agent_session.Job', side_effect=self.immediate):
            report = run_native_session(self.scheduler, stop, None,
                lambda row: published.append(row.get('accepted', False)), service=True)
            self.assertGreater(report['elapsed_s'], 180)
            self.assertEqual(report['reason'], 'native_withdrawn')
            self.assertEqual(report['lifecycle'], 'service')
            self.assertTrue(report['cleanup_verified'], report)
            self.assertFalse(report['accepted']); self.assertEqual(exit_code(report, service=True), 0)
            self.assertGreater(report['decisions_total'], 50)
            self.assertGreater(report['decisions_omitted'], 0)
            self.assertLessEqual(len(report['decisions']), 16)
            self.assertFalse(any(published))
            calls = len(self.gateway.ids)
            self.operator['motion_policy']['privacy_all'] = False
            self.scheduler.advance(); self.native.advance()
            self.assertEqual(len(self.gateway.ids), calls)
            self.assertTrue(self.scheduler.closed); self.assertTrue(self.native.closed)
        self.assertEqual(self.gateway.main_calls, 0); self.assertEqual(self.gateway.frames, 0)
        self.assertFalse(self.writes)

    def test_bounded_gap_suffix_keeps_total_durations_after_eviction(self):
        clock = [100.]; self.native.clock = lambda: clock[0]
        self.native.latest = self.native.read()
        with patch('reachy_companion.autonomous.native_agent.Job', side_effect=self.pending):
            for _ in range(600):
                self.native.unavailable_since('fixture', clock[0])
                clock[0] += .1
                job = self.native.poll_job = self.pending(); job.future.set_result(self.native.read())
                self.native.advance()
            report = self.native.observation_report(clock[0])
        self.assertEqual(len(self.native.gaps), 256)
        self.assertEqual(report['gap_count'], 600); self.assertEqual(report['gaps_omitted'], 344)
        self.assertEqual(report['recoveries'], 600)
        self.assertAlmostEqual(report['unavailable_s'], 60)
        self.native.unavailable_since('open', clock[0]); clock[0] += 2
        self.assertAlmostEqual(self.native.observation_report(clock[0])['unavailable_s'], 62)
        self.assertTrue(self.native.physical_closed_after_gap)

    def test_service_stop_keeps_occupied_slots_until_actual_cleanup(self):
        self.cfg['context']['enabled'] = False
        self.gateway.hold = self.hold_status = True
        self.runner = threading.Thread(target=lambda: self.report.append(run_native_session(
            self.scheduler, self.stop, None, lambda _: None, service=True)))
        self.runner.start()
        self.assertTrue(self.status_entered.wait(1))
        self.wait(lambda: self.native.poll_job is not None)
        # Existing finite STOP test covers an occupied model+poll after a gap;
        # service uses the same close/drain path and must not replace this poll.
        poll = self.native.poll_job
        self.stop.set(); time.sleep(.03)
        self.assertIs(self.native.poll_job, poll); self.assertTrue(self.runner.is_alive())
        self.status_release.set(); self.gateway.release.set(); self.runner.join(3)
        report = self.report[0]
        self.assertEqual(report['reason'], 'controller_stop')
        self.assertTrue(report['cleanup_verified'], report)
        self.assertFalse(report['accepted']); self.assertEqual(exit_code(report, service=True), 0)
        self.assertFalse(any(report['execution_busy'].values()))

    def test_service_main_sigterm_drains_model_and_poll_and_restores_handlers(self):
        import signal
        import sys
        from reachy_companion.autonomous import native_agent_session as session
        self.cfg['context']['enabled'] = False
        output = Path(self.tmp.name)/'signal-report.json'
        metadata = Path(self.tmp.name)/'signal-metadata.json'
        token = Path(self.tmp.name)/'token'; token.write_text('f'*32)
        listener_stop = threading.Event()
        ready = threading.Event(); sent = []
        server = SimpleNamespace(serve_forever=lambda: listener_stop.wait(3),
            shutdown=listener_stop.set, server_close=lambda: None,
            transport_status=lambda: dict(execution_busy=False, handlers=0))
        def create(*args, **kwargs):
            self.hold_status = self.gateway.hold = True
            self.status_entered.clear(); ready.set()
            return server
        def terminate():
            if not ready.wait(1): return
            self.status_entered.wait(1)
            # Wait for assignment of both actual jobs before sending a real signal.
            deadline = time.monotonic()+1
            while (self.native.poll_job is None or self.scheduler.fast_job is None) and time.monotonic()<deadline:
                time.sleep(.005)
            if self.native.poll_job is None or self.scheduler.fast_job is None:
                self.status_release.set(); self.gateway.release.set(); return
            if signal.getsignal(signal.SIGTERM) != previous:
                sent.append(True); signal.raise_signal(signal.SIGTERM)
            time.sleep(.03)
            self.status_release.set(); self.gateway.release.set()
        helper = threading.Thread(target=terminate)
        argv = ['native', '--config', 'unused', '--companion-config', 'unused',
                '--token-file', str(token), '--output', str(output), '--metadata', str(metadata),
                '--agent-url', 'http://127.0.0.1:8090', '--hub-url', 'http://127.0.0.1:8080',
                '--agent-boot', 'fixture-agent', '--microphone-epoch', '1', '--policy-epoch', '2',
                '--controller', 'fixture', '--allow-native-observation', '--service']
        previous = signal.getsignal(signal.SIGTERM)
        helper.start()
        try:
            with patch.object(sys, 'argv', argv), patch.object(session, 'load', return_value=self.cfg), \
                    patch('reachy_companion.config.Config', return_value=self.companion), \
                    patch.object(session, 'NativeClient', side_effect=[self.native.agent, self.native.hub]), \
                    patch.object(session, 'NativeAgent', return_value=self.native), \
                    patch.object(session, 'NativeGateway', return_value=self.gateway), \
                    patch.object(session, 'NativeScheduler', return_value=self.scheduler), \
                    patch.object(session, 'create_server', side_effect=create):
                self.assertEqual(session.main(), 0)
        finally:
            helper.join(3)
        report = json.loads(output.read_text())
        self.assertEqual(report['reason'], 'controller_stop')
        self.assertEqual(sent, [True])
        self.assertTrue(report['cleanup_verified'], report)
        self.assertFalse(any(report['execution_busy'].values()))
        self.assertFalse(report['control_listener_execution_busy'])
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)
        self.assertEqual(json.loads(metadata.read_text()), report)

    def test_service_opt_in_and_snapshot_rotation_do_not_change_finite_default(self):
        for duration in (None, 0, 181, float('inf'), True):
            with self.assertRaises(ValueError): validate_lifecycle(self.cfg, duration=duration)
        validate_lifecycle(self.cfg)  # finite60 still permits its explicit context lane
        with self.assertRaises(ValueError): validate_lifecycle(self.cfg, service=True, duration=None)
        self.cfg['context']['enabled'] = False
        validate_lifecycle(self.cfg, service=True, duration=None)
        for options in (dict(duration=90), dict(duration=None, allow_stock=True),
                        dict(duration=None, allow_camera=True)):
            with self.assertRaises(ValueError): validate_lifecycle(self.cfg, service=True, **options)
        path = Path(self.tmp.name)/'metadata.json'; snapshots = MetadataSnapshots(path)
        for count in range(20): snapshots.write(dict(stage='ACTIVE', accepted=False, count=count), force=True)
        self.assertEqual(json.loads(path.read_text())['count'], 19)
        self.assertEqual(json.loads(path.with_name(path.name+'.previous').read_text())['count'], 18)
        self.assertFalse(path.with_name(path.name+'.tmp').exists())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError): snapshots.write(dict(invalid='x'*(1024*1024)), force=True)


if __name__ == '__main__': unittest.main()
