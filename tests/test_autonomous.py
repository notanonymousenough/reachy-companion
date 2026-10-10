"""Adversarial finite shadow checks; no hardware, models, or external network."""
import copy
import json
import os
from pathlib import Path
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.contracts import decode, validate
from reachy_companion.autonomous.gateway import BudgetRejected, ExecutionUnknown, Gateway, ModelBackend, create_server, fast_schema, fast_projection
from reachy_companion.autonomous.runtime import ReplayGateway, Scheduler
from reachy_companion.autonomous.state import State

ROOT = Path(__file__).resolve().parents[1]


def config():
    value = load(ROOT / 'config.autonomous.example.json')
    value.update(period_s=.01, fast_deadline_s=.03, task_timeout_s=.15)
    return value


def spin(scheduler, condition, timeout=1):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        scheduler.advance()
        if condition(): return
        time.sleep(.002)
    raise AssertionError('finite condition deadline')


class StateTests(unittest.TestCase):
    def setUp(self):
        self.state = State(config=config())
    def turn(self, text='test'):
        self.state.ingest(dict(type='utterance', text=text), 0)
        return next(iter(self.state.candidates))
    def start(self):
        ref = self.turn()
        task = self.state.apply(dict(a='think', why='new task', start=dict(type='main', input_ref=ref)), self.state.bind(0, 1), 0)
        self.assertIsNotNone(task)
        return task
    def test_schema_copy_does_not_drift(self):
        self.assertEqual(json.loads((ROOT/'docs/autonomous-companion/schemas/contracts.schema.json').read_text()),
                         json.loads((ROOT/'src/reachy_companion/assets/autonomous-contracts.json').read_text()))
    def test_long_silence_keeps_bounded_projection_and_ledger(self):
        for i in range(2000):
            self.state.apply(dict(a='wait', why='no evidence'), self.state.bind(i, 1), i)
        view = self.state.snapshot(2000)
        self.assertLess(len(json.dumps(view)), 2000)
        self.assertEqual(len(view['prev']), 3)
        self.assertEqual(len(self.state.ledger), 256)
        self.assertEqual(self.state.counts['decision_accepted'], 2000)
    def test_mute_and_unmute_never_restore_old_binding(self):
        ref = self.turn()
        binding = self.state.bind(0, 1)
        self.state.ingest(dict(type='operator', muted=True), .1)
        self.state.ingest(dict(type='operator', muted=False), .2)
        self.state.apply(dict(a='think', why='stale', start=dict(type='main', input_ref=ref)), binding, .3)
        self.assertFalse(self.state.tasks)
        self.assertEqual(self.state.counts['decision_stale'], 1)
    def test_new_turn_old_attempt_and_compute_restart_reject_results(self):
        for race in ('turn', 'attempt', 'compute'):
            with self.subTest(race=race):
                self.state = State(config=config()); task = self.start()
                attempt = task.attempt_id
                if race == 'turn': self.state.ingest(dict(type='utterance', text='new'), .01)
                if race == 'attempt': attempt = 'wrong-attempt'
                if race == 'compute': self.state.set_compute_boot('new-boot', 1)
                self.state.complete(task.task_id, attempt, task.authority, 'old', .02)
                self.assertIsNone(task.result)
                self.assertEqual(self.state.counts['task_result_stale'], 1)
    def test_result_never_speaks_until_fresh_commit_and_never_repeats(self):
        task = self.start()
        self.state.complete(task.task_id, task.attempt_id, task.authority, 'reply', .01)
        self.assertEqual(self.state.counts['simulated_speech'], 0)
        binding = self.state.bind(.02, 1)
        choice = dict(a='converse', why='ready', commit=task.task_id)
        self.state.apply(choice, binding, .03); self.state.apply(choice, binding, .04)
        self.assertEqual(self.state.counts['simulated_speech'], 1)
        self.assertEqual(self.state.counts['decision_duplicate'], 1)
    def test_unknown_alias_direct_tools_and_muted_commit_are_blocked(self):
        self.state.apply(dict(a='think', why='bad', start=dict(type='main', input_ref='invented')), self.state.bind(0, 1), 0)
        self.state.apply(dict(a='wait', why='bad', say='hello'), self.state.bind(0, 1), 0)
        self.assertFalse(self.state.tasks)
        self.assertEqual(self.state.counts['alias_rejected'], 1)
        self.assertEqual(self.state.counts['capability_rejected'], 1)
        task = self.start()
        self.state.complete(task.task_id, task.attempt_id, task.authority, 'reply', .01)
        self.state.ingest(dict(type='operator', muted=True), .02)
        self.state.apply(dict(a='converse', why='ready', commit=task.task_id), self.state.bind(.03, 1), .04)
        self.assertEqual(self.state.counts['simulated_speech'], 0)
    def test_sensor_age_is_not_renewed_by_snapshot_and_unknown_is_not_silence(self):
        self.state.ingest(dict(type='sensor', id='audio.rms', summary='quiet', ttl_ms=100), 0)
        self.assertEqual(self.state.snapshot(.2)['sensors'][0]['state'], 'stale')
        self.assertEqual(self.state.snapshot(.3)['sensors'][0]['age_ms'], 300)
        self.state.ingest(dict(type='sensor', id='battery', summary='100%', availability='unknown'), .4)
        unknown = self.state.snapshot(.4)['sensors'][1]
        self.assertIsNone(unknown['age_ms']); self.assertEqual(unknown['summary'], '')
        self.state.ingest(dict(type='operator', muted=True), .5)
        self.assertEqual(self.state.snapshot(.5)['sensors'][0]['state'], 'disabled')
    def test_deadline_and_sensor_capacity(self):
        task = self.start()
        self.state.complete(task.task_id, task.attempt_id, task.authority, 'late', 2)
        self.assertEqual(self.state.counts['task_result_stale'], 1)
        for i in range(50): self.state.ingest(dict(type='sensor', id=str(i)), i)
        self.assertEqual(len(self.state.sensors), 12)
    def test_nonfinite_duplicate_keys_and_oversized_mandatory_turn_reject(self):
        for text in ('{"x":NaN}', '{"a":1,"a":2}'):
            with self.assertRaises(ValueError): decode(text)
        with self.assertRaises(ValueError): self.turn('x'*1025)
        self.assertFalse(self.state.candidates)


class SchedulerTests(unittest.TestCase):
    def test_background_task_does_not_stop_ticks_including_waits(self):
        gateway = ReplayGateway(main_delay=.25)
        scheduler = Scheduler(config(), gateway)
        scheduler.ingest(dict(type='utterance', text='hello'))
        spin(scheduler, lambda: scheduler.main_job is not None)
        spin(scheduler, lambda: gateway.fast_calls >= 8)
        self.assertFalse(scheduler.main_job.future.done())
        self.assertGreater(scheduler.state.counts['decision_accepted'], 3)
        spin(scheduler, lambda: scheduler.main_job is None)
        self.assertEqual(scheduler.state.counts['task_started'], 1)
    def test_fast_timeout_keeps_execution_slot_and_rejects_late_result(self):
        release = threading.Event()
        class Hung(ReplayGateway):
            def fast(self, request_id, view):
                self.fast_calls += 1
                release.wait(1)
                return dict(output=dict(a='wait', why='late'), compute_boot_id=self.boot_id, request_id=request_id)
        gateway = Hung(); scheduler = Scheduler(config(), gateway)
        try:
            spin(scheduler, lambda: scheduler.state.counts['fast_deadline_expired'] == 1)
            spin(scheduler, lambda: scheduler.state.counts['tick_busy_gap'] >= 5)
            self.assertEqual(gateway.fast_calls, 1)
            release.set()
            spin(scheduler, lambda: scheduler.state.counts['decision_stale'] == 1)
        finally: release.set()
    def test_expired_main_does_not_grant_new_execution_permit(self):
        release = threading.Event()
        class Hung(ReplayGateway):
            views = []
            def fast(self, request_id, view):
                self.views.append(view)
                return super().fast(request_id, view)
            def main(self, task):
                release.wait(1)
                return dict(output='late', compute_boot_id=self.boot_id, request_id=task.attempt_id)
        scheduler = Scheduler(config(), Hung())
        try:
            scheduler.ingest(dict(type='utterance', text='first'))
            spin(scheduler, lambda: scheduler.main_job is not None)
            spin(scheduler, lambda: scheduler.state.counts['task_expired'] == 1)
            scheduler.ingest(dict(type='utterance', text='second'))
            spin(scheduler, lambda: scheduler.state.counts['main_execution_busy'] >= 2)
            self.assertEqual(scheduler.state.counts['task_started'], 1)
            self.assertTrue(scheduler.state.candidates)
            self.assertTrue(any(any(p['status']=='execution_busy_result_revoked' for p in v['pending']) for v in scheduler.gateway.views))
            release.set()
            spin(scheduler, lambda: scheduler.state.counts['task_result_stale'] == 1)
        finally: release.set()


class GatewayTests(unittest.TestCase):
    def test_sdk_counts_and_completion_share_loaded_handle_and_timeout_quarantines(self):
        cfg = config(); model = cfg['models']['main']
        model.update(id='loaded-main', base_url='http://127.0.0.1:1234/v1',
                     tokenizer_backend='lmstudio_sdk', completion_backend='lmstudio_sdk')
        model['audit'].update(verified=True, runtime_build='fixture', weight_sha256='x',
                              template_sha256='x', tokenizer_sha256='x', runtime_context_tokens=4096)
        calls = []; clients = []
        class Handle:
            fail = False
            def get_info(self): return SimpleNamespace(identifier='loaded-main', context_length=4096)
            def tokenize(self, text): calls.append('tokenize'); return [1, 2, 3]
            def complete(self, prompt, config):
                calls.append('complete')
                if self.fail: raise TimeoutError('unknown prediction completion')
                return SimpleNamespace(content='reply', stats=SimpleNamespace(stop_reason='eosFound',
                    predicted_tokens_count=1, time_to_first_token_sec=.1))
        handle = Handle()
        class Client:
            def __init__(self, host):
                clients.append(host)
                self.llm = SimpleNamespace(list_loaded=lambda: [handle])
            def __enter__(self): return self
            def __exit__(self, *args): pass
        sdk = SimpleNamespace(Client=Client, set_sync_api_timeout=lambda value: None)
        with patch.dict('sys.modules', {'lmstudio': sdk}):
            gateway = Gateway(ModelBackend(cfg))
            result = gateway.generate('main', 'hello')
            self.assertEqual(calls, ['tokenize', 'tokenize', 'complete'])
            self.assertEqual(clients, ['127.0.0.1:1234'])
            self.assertEqual(result['usage']['time_to_first_token_s'], .1)
            handle.fail = True
            with self.assertRaises(ExecutionUnknown): gateway.generate('main', 'timeout')
            with self.assertRaises(BlockingIOError): gateway.generate('main', 'do not duplicate')
            self.assertEqual(gateway.health()['quarantined'], ['main'])

    def test_native_grammar_only_exposes_current_aliases(self):
        from jsonschema import validate as validate_schema
        state = State(config=config())
        view = state.snapshot(0)
        with self.assertRaises(Exception):
            validate_schema({'a':'think','why':'invented','start':{'type':'main','input_ref':'ghost'}}, fast_schema(view))
        state.ingest({'type':'utterance','text':'hello'}, 0)
        view = state.snapshot(0)
        ref = view['candidates'][0]['alias']
        validate_schema({'a':'think','why':'new','start':{'type':'main','input_ref':ref}}, fast_schema(view))
        with self.assertRaises(Exception):
            validate_schema({'a':'converse','why':'not ready','commit':ref}, fast_schema(view))
        projected, aliases = fast_projection(view)
        self.assertEqual(aliases['c0'], ref)
        self.assertEqual(projected['candidates'][0]['alias'], 'c0')
        self.assertEqual(view['candidates'][0]['alias'], ref)
        projected['muted'] = True
        with self.assertRaises(Exception):
            validate_schema({'a':'think','why':'muted','start':{'type':'main','input_ref':'c0'}}, fast_schema(projected))

    def test_native_token_limit_and_smaller_admission_context_reject(self):
        class Backend(ModelBackend):
            def count(self, model, content): return 200
            def post(self, url, payload, *args):
                self.payload = payload
                return {'content':'{"a":"wait","why":"limited"}', 'stop_type':'limit', 'stop':True}
        cfg = config(); model = cfg['models']['fast']
        model.update(id='fixture', base_url='http://127.0.0.1', completion_backend='llama_native')
        model['audit'].update(verified=True, device='cpu_pc', runtime_build='fixture', weight_sha256='x',
                              template_sha256='x', tokenizer_sha256='x', runtime_context_tokens=4096)
        backend = Backend(cfg)
        with self.assertRaises(ValueError): backend.generate('fast', State().snapshot(0))
        self.assertIn('json_schema', backend.payload)
        self.assertEqual(backend.payload['n_predict'], 192)
        self.assertNotIn('max_tokens', backend.payload)
        model['admission_context_tokens'] = 300
        del backend.payload
        with self.assertRaises(BudgetRejected): backend.generate('fast', State().snapshot(0))
        self.assertFalse(hasattr(backend, 'payload'))

    def test_unknown_completion_quarantines_without_freeing_slot(self):
        class Failed:
            def generate(self, role, data): raise ExecutionUnknown('unknown')
        gateway = Gateway(Failed())
        with self.assertRaises(ExecutionUnknown): gateway.generate('fast', {})
        with self.assertRaises(BlockingIOError): gateway.generate('fast', {})
        self.assertEqual(gateway.health()['quarantined'], ['fast'])
    def test_exact_token_budget_blocks_inference_before_completion(self):
        class Backend(ModelBackend):
            calls = []
            def count(self, model, content): return 100000
            def post(self, *args): self.calls.append(args); raise AssertionError('must not infer')
        cfg = config(); model = cfg['models']['fast']
        model.update(id='fixture', base_url='http://127.0.0.1', tokenize_path='/tokenize')
        model['audit'].update(verified=True, device='cpu_pc', runtime_build='fixture', weight_sha256='x',
                              template_sha256='x', tokenizer_sha256='x', runtime_context_tokens=4096)
        backend = Backend(cfg)
        with self.assertRaises(BudgetRejected): backend.generate('fast', State().snapshot(0))
        self.assertFalse(backend.calls)
    def test_unaudited_runtime_cannot_execute(self):
        with self.assertRaises(BudgetRejected): ModelBackend(config()).generate('fast', {})
    def test_incomplete_or_unknown_fields_cannot_be_salvaged(self):
        with self.assertRaises(Exception): validate('FastChoice', dict(a='wait', why='ok', epoch=999))
        with self.assertRaises(ValueError): decode('{"a":"wait"')
    def test_authenticated_http_round_trip_with_mock_model_and_tokenizer(self):
        calls = []
        class FixtureModel(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                data = decode(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(self.path)
                body = {'tokens': list(range(len(data['content'].split())))} if self.path=='/tokenize' else {
                    'choices': [{'text':'{"a":"wait","why":"fixture"}', 'finish_reason':'stop'}]}
                raw = json.dumps(body).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
        model_server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureModel)
        thread = threading.Thread(target=model_server.serve_forever, daemon=True); thread.start()
        cfg = config(); cfg['gateway']['port'] = 0
        model = cfg['models']['fast']; model.update(id='fixture', base_url='http://127.0.0.1:'+str(model_server.server_port), tokenize_path='/tokenize')
        model['audit'].update(verified=True, device='cpu_pc', runtime_build='fixture', weight_sha256='fixture',
                             template_sha256='fixture', tokenizer_sha256='fixture', runtime_context_tokens=4096)
        with patch.dict(os.environ, {'REACHY_SHADOW_TOKEN': 't'*32}):
            server = create_server(cfg)
            thread2 = threading.Thread(target=server.serve_forever, daemon=True); thread2.start()
            url = 'http://127.0.0.1:'+str(server.server_port)
            try:
                with self.assertRaises(HTTPError) as error: urlopen(url+'/health')
                self.assertEqual(error.exception.code, 401)
                payload = dict(request_id='fixture-r1', data=State().snapshot(0))
                request = Request(url+'/decision', data=json.dumps(payload).encode(), headers={'Authorization':'Bearer '+'t'*32})
                with urlopen(request) as response: result = decode(response.read())
                self.assertEqual(result['output']['a'], 'wait')
                self.assertEqual(result['request_id'], 'fixture-r1')
                self.assertEqual(calls, ['/tokenize','/tokenize','/completions'])
                self.assertFalse(server.gateway.health()['busy']['fast'])
            finally:
                server.shutdown(); server.server_close(); model_server.shutdown(); model_server.server_close()



class CausalityRegressionTests(unittest.TestCase):
    def test_pending_fast_accepts_wait_start_and_commit_after_unrelated_sensors(self):
        for action in ('wait', 'start', 'commit'):
            with self.subTest(action=action):
                entered, release = threading.Event(), threading.Event()
                class Controlled(ReplayGateway):
                    def fast(self, request_id, view):
                        entered.set(); release.wait(2)
                        choice = dict(a='wait', why='independent')
                        if action == 'start':
                            choice = dict(a='think', why='same input', start=dict(type='main', input_ref=view['candidates'][0]['alias']))
                        if action == 'commit':
                            choice = dict(a='converse', why='same proposal', commit=view['ready'][0]['alias'])
                        return dict(output=choice, compute_boot_id=self.boot_id, request_id=request_id)
                cfg = config(); cfg.update(period_s=1, fast_deadline_s=1, task_timeout_s=2)
                scheduler = Scheduler(cfg, Controlled())
                if action in ('start', 'commit'):
                    scheduler.ingest(dict(type='utterance', text='original input'))
                if action == 'commit':
                    now = time.monotonic(); state = scheduler.state; ref = next(iter(state.candidates))
                    task = state.apply(dict(a='think', why='prepare', start=dict(type='main', input_ref=ref)), state.bind(now, 1), now)
                    state.complete(task.task_id, task.attempt_id, task.authority, 'ready response', now)
                baseline = scheduler.state.counts['decision_accepted']
                try:
                    scheduler.advance(); self.assertTrue(entered.wait(1))
                    for i in range(5):
                        scheduler.ingest(dict(type='sensor', id='ambient', summary=str(i)))
                    release.set()
                    spin(scheduler, lambda: scheduler.state.counts['decision_accepted'] > baseline)
                    self.assertEqual(scheduler.state.counts['decision_stale'], 0)
                    if action == 'start': self.assertEqual(scheduler.state.counts['task_started'], 1)
                    if action == 'commit': self.assertEqual(scheduler.state.counts['simulated_speech'], 1)
                finally: release.set()

    def test_changed_or_removed_bound_input_and_proposal_cannot_act(self):
        for change in ('changed_input', 'removed_alias', 'changed_proposal'):
            with self.subTest(change=change):
                state = State(config=config()); state.ingest(dict(type='utterance', text='original'), 0)
                ref = next(iter(state.candidates))
                choice = dict(a='think', why='same input', start=dict(type='main', input_ref=ref))
                if change == 'changed_proposal':
                    task = state.apply(choice, state.bind(0, 1), 0)
                    state.complete(task.task_id, task.attempt_id, task.authority, 'original result', .01)
                    choice = dict(a='converse', why='ready', commit=task.task_id)
                binding = state.bind(.02, 1)
                baseline = state.counts['decision_accepted']
                if change == 'changed_input': state.candidates[ref] = 'corrected input'
                elif change == 'removed_alias': state.candidates.pop(ref)
                else: task.result = 'revised result'
                state.apply(choice, binding, .03)
                self.assertEqual(state.counts['decision_accepted'], baseline)
                self.assertEqual(state.counts['simulated_speech'], 0)

    def test_unrelated_updates_do_not_weaken_turn_and_operator_fencing(self):
        for event in (dict(type='utterance', text='new turn'), dict(type='operator', muted=True)):
            state = State(config=config()); state.ingest(dict(type='utterance', text='original'), 0)
            binding = state.bind(0, 1)
            state.ingest(dict(type='sensor', id='ambient'), .01)
            state.ingest(event, .02)
            state.apply(dict(a='wait', why='old'), binding, .03)
            self.assertEqual(state.counts['decision_stale'], 1)

    def test_late_a_main_cannot_rollback_b_or_invalidate_pending_b_fast(self):
        entered, release = threading.Event(), threading.Event()
        class Controlled(ReplayGateway):
            boot_id = 'B'
            def fast(self, request_id, view):
                entered.set(); release.wait(2)
                return dict(output=dict(a='wait', why='B choice'), compute_boot_id='B', request_id=request_id)
        cfg = config(); cfg.update(period_s=1, fast_deadline_s=1, task_timeout_s=2)
        scheduler = Scheduler(cfg, Controlled())
        # Initial authenticated A handshake precedes this independent B gateway fixture.
        scheduler.state = State('A', cfg)
        state = scheduler.state; now = time.monotonic()
        state.ingest(dict(type='utterance', text='A turn'), now)
        ref = next(iter(state.candidates))
        task = state.apply(dict(a='think', why='A task', start=dict(type='main', input_ref=ref)), state.bind(now, 1), now)
        from concurrent.futures import Future
        from types import SimpleNamespace
        future = Future(); scheduler.main_task = task; scheduler.main_job = SimpleNamespace(future=future)
        self.assertTrue(scheduler.handshake_compute('B', 1))
        try:
            scheduler.advance(); self.assertTrue(entered.wait(1))
            binding_b = scheduler.binding
            future.set_result(dict(output='late A', compute_boot_id='A', request_id=task.attempt_id))
            scheduler.advance()
            self.assertEqual(state.authority.compute_boot_id, 'B')
            self.assertEqual(binding_b.authority, state.authority)
            self.assertEqual(state.counts['task_result_stale'], 1)
            release.set(); spin(scheduler, lambda: state.counts['decision_accepted'] == 2)
            self.assertEqual(state.authority.compute_boot_id, 'B')
            self.assertFalse(scheduler.handshake_compute('A', 2))
            self.assertFalse(scheduler.handshake_compute('C', 0))
            self.assertEqual(state.authority.compute_boot_id, 'B')
        finally: release.set()

    def test_late_a_fast_and_mismatched_envelope_never_change_compute_boot(self):
        from concurrent.futures import Future
        from types import SimpleNamespace
        cfg = config(); scheduler = Scheduler(cfg, ReplayGateway())
        now = time.monotonic(); scheduler.next_tick = now + 10
        original = scheduler.state.authority.compute_boot_id
        scheduler.binding = scheduler.state.bind(now, 1)
        future = Future(); scheduler.fast_job = SimpleNamespace(future=future)
        self.assertTrue(scheduler.handshake_compute('B', 1))
        future.set_result(dict(output=dict(a='wait', why='late A'), compute_boot_id=original,
                               request_id=scheduler.binding.request_id))
        scheduler.advance()
        self.assertEqual(scheduler.state.authority.compute_boot_id, 'B')
        self.assertEqual(scheduler.state.counts['decision_stale'], 1)
        scheduler.binding = scheduler.state.bind(now, 1)
        future = Future(); scheduler.fast_job = SimpleNamespace(future=future)
        future.set_result(dict(output=dict(a='wait', why='wrong producer'), compute_boot_id='C',
                               request_id=scheduler.binding.request_id))
        scheduler.advance()
        self.assertEqual(scheduler.state.authority.compute_boot_id, 'B')
        self.assertEqual(scheduler.state.counts['decision_accepted'], 0)

if __name__ == '__main__': unittest.main()
