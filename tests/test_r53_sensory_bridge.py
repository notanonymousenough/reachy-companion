"""Synthetic R53 real-source contracts; all model/actuator I/O is mocked."""
import json
import http.client
import sys
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

try:
    import webrtcvad
except ImportError:
    sys.modules['webrtcvad'] = types.SimpleNamespace(Vad=Mock())

from reachy_companion.agent import Agent
from reachy_companion.sensory_bridge import SensoryBridge,raw_decision_payload,SYSTEM
from reachy_companion.sound_monitor import SoundMonitor
from reachy_companion import snapshot_vision


class Fixture(Agent):
    def __init__(self, enabled=True):
        self.config = dict(conversation=dict(sensory_loop=dict(enabled=enabled)),
                           guarded_motion=dict(enabled=True),
                           network=dict(llm_base_url='http://127.0.0.1:1234/v1'), llm=dict(model='already-loaded',mode='completion',api_path='/completions',
                           message_template='<|im_start|>{role}\n{content}<|im_end|>\n',
                           assistant_prefix='<|im_start|>assistant\n<think>\n\n</think>\n\n',stop=['<|im_end|>','<|im_start|>']))
        self.microphone_lock = threading.Lock()
        self.microphone = types.SimpleNamespace(enabled=True, error=None)
        self.microphone_epoch = 10
        self.microphone_owner_id = None
        self.agent_boot_id = 'actual-control-fixture'
        self.stopping = threading.Event()
        self.listening = threading.Event()
        self.listening.set()
        self.phase = 'listening'
        self.policy = dict(epoch=20, motor_enabled=True, quiet=False, privacy_all=False)
        self.intent = dict(generation=30, listening_requested=True)
        self.mode = dict(generation=40, mode='normal', error=None)
        self.motion_policy = types.SimpleNamespace(lock=threading.RLock(), owner_id=None, snapshot=lambda: dict(self.policy))
        self.durable_intent = types.SimpleNamespace(lock=threading.RLock(), error=False, snapshot=lambda: dict(self.intent))
        self.conversation_mode = types.SimpleNamespace(lock=threading.RLock(), snapshot=lambda: dict(self.mode))
        self.outputs = []
        e = self.expressions = types.SimpleNamespace(condition=threading.Condition(), version=0, completed=0,
            state=('neutral', 'neutral'), cues=[], clock=None, stock=True, settings=dict(enabled=True),
            last_error=None, last_expression=None)
        def hold():
            with e.condition:
                e.version += 1
                e.state = None
                e.condition.notify_all()
        e.hold = hold
        def worker():
            while not self.stopping.is_set():
                with e.condition:
                    e.condition.wait_for(lambda: e.version > e.completed or self.stopping.is_set(), .1)
                    version, state = e.version, e.state
                if state and version > e.completed and self.motor_permitted():
                    self.outputs.append(state)
                    e.last_expression = dict(phase=state[0], emotion=state[1])
                with e.condition:
                    e.completed = version
                    e.condition.notify_all()
        e.thread = threading.Thread(target=worker, daemon=True)
        e.thread.start()
        self.sensory = SensoryBridge(self, start=False)

    def close(self):
        self.sensory.loop.close()
        self.stopping.set()
        with self.expressions.condition:
            self.expressions.condition.notify_all()
        self.expressions.thread.join(1)


class NativeConnection:
    packets = []
    entered = release = None
    timeout_error = False
    response_status = 200
    raw_override = None
    remaining = 0
    incomplete = False

    def __init__(self, *args, **kwargs):
        pass
    def connect(self):
        pass
    def request(self, method, path, body, headers):
        packet = json.loads(body)
        self.packets.append((path, packet, headers))
        data = json.JSONDecoder().raw_decode(packet['prompt'].split('\nDATA:\n',1)[1])[0]
        self.result = dict(model=packet['model'],choices=[dict(index=0,finish_reason='stop',text=json.dumps(
            dict(action='attend', why='fresh sound invites attention', evidence=[data['observations'][0]['id']])) )])
        if self.entered:
            self.entered.set()
        if self.release:
            self.release.wait(2)
    def getresponse(self):
        if self.timeout_error:
            raise TimeoutError('synthetic timeout')
        def read(limit):
            if self.incomplete:raise http.client.IncompleteRead(b'partial',100)
            return self.raw_override if self.raw_override is not None else json.dumps(self.result).encode()
        return types.SimpleNamespace(status=self.response_status, length=self.remaining, read=read)
    def close(self):
        pass


class BridgeChecks(unittest.TestCase):
    def setUp(self):
        NativeConnection.packets = []
        NativeConnection.entered = NativeConnection.release = None
        NativeConnection.timeout_error = False
        NativeConnection.response_status = 200
        NativeConnection.raw_override = None
        NativeConnection.remaining = 0
        NativeConnection.incomplete = False
        inventory = dict(models=[dict(key='already-loaded', loaded_instances=[dict(id='loaded-instance')], capabilities={})])
        for patcher in (patch.object(snapshot_vision, 'native_address', return_value=('127.0.0.1', 1234)),
                        patch.object(snapshot_vision, 'get_models', return_value=inventory),
                        patch('reachy_companion.sensory_bridge.http.client.HTTPConnection', NativeConnection)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def fixture(self, enabled=True):
        a = Fixture(enabled)
        self.addCleanup(a.close)
        return a

    def event(self, a, ticket=None, age=0):
        return a.sensory.observe_sound(dict(kind='sound', top_class=7), a.microphone_epoch,
                                       time.monotonic()-age, 1, ticket or a.sensory.ticket())

    def pump(self, a, condition):
        until = time.monotonic()+2
        while time.monotonic() < until:
            a.sensory.refresh()
            a.sensory.loop.advance()
            if condition():
                return
            time.sleep(.001)
        self.fail('synthetic bridge did not settle')

    def test_classifier_to_raw_model_to_existing_guarded_attention(self):
        a = self.fixture()
        event_id = self.event(a)
        self.pump(a, lambda: a.sensory.loop.snapshot()['counts']['completed'] == 1)
        self.assertEqual(a.outputs, [('reacting', 'surprised')])
        path, packet, headers = NativeConnection.packets[0]
        self.assertEqual(path, '/v1/completions')
        self.assertEqual(packet['model'], 'already-loaded')
        self.assertEqual(packet['max_tokens'],192)
        self.assertEqual(packet['stop'],a.config['llm']['stop'])
        self.assertTrue(packet['prompt'].endswith(a.config['llm']['assistant_prefix']))
        self.assertNotIn('Authorization', headers)
        self.assertEqual(a.sensory.loop.snapshot()['previous_actions'][0]['evidence'], [event_id])
        self.assertIsNone(a._sensory_expression_guard)
        self.assertTrue(a.motor_permitted())

    def test_publication_continues_during_model_work_and_off_fences_result(self):
        a = self.fixture()
        entered, release = threading.Event(), threading.Event()
        NativeConnection.entered, NativeConnection.release = entered, release
        self.addCleanup(release.set)
        self.event(a)
        a.sensory.loop.advance()
        self.assertTrue(entered.wait(1))
        for i in range(50):
            a.sensory.loop.publish(dict(kind='audio.activity', source='existing-owner',
                observed_monotonic=time.monotonic(), summary='read receipt update '+str(i)))
            a.sensory.loop.advance()
        self.assertTrue(a.sensory.loop.snapshot()['busy']['decision'])
        self.assertEqual(len(NativeConnection.packets), 1)
        a.microphone.enabled = False
        a._sensory_withdraw()
        a.sensory.refresh()
        self.assertTrue(a.sensory.loop.snapshot()['busy']['decision'])
        release.set()
        self.pump(a, lambda: not a.sensory.loop.snapshot()['busy']['decision'])
        self.assertEqual(a.outputs, [])

    def test_mode_changed_during_model_request_cannot_enqueue(self):
        a = self.fixture()
        entered, release = threading.Event(), threading.Event()
        NativeConnection.entered, NativeConnection.release = entered, release
        self.addCleanup(release.set)
        self.event(a)
        a.sensory.loop.advance()
        self.assertTrue(entered.wait(1))
        a.mode['generation'] += 1
        a._sensory_withdraw()
        release.set()
        self.pump(a, lambda: not a.sensory.loop.snapshot()['busy']['decision'])
        self.assertEqual(a.outputs, [])

    def test_timeout_latches_backend_unknown_without_retry(self):
        a = self.fixture()
        NativeConnection.timeout_error = True
        self.event(a)
        self.pump(a, lambda: a.sensory.model_unknown)
        self.assertTrue(a.sensory.status()['model_execution_busy'])
        a.sensory.loop.publish(dict(kind='sound.event', source='existing-owner',
            observed_monotonic=time.monotonic(), summary='next actual source event'))
        a.sensory.loop.advance()
        self.pump(a, lambda: not a.sensory.loop.snapshot()['busy']['decision'])
        self.assertEqual(len(NativeConnection.packets), 1)
        self.assertEqual(a.outputs, [])
        diagnostics=a.sensory.status()
        self.assertFalse(diagnostics['response_complete'])
        self.assertEqual(diagnostics['failure_class'],'model_transport_uncertain')
        self.assertTrue(diagnostics['model_failure_latched'])

    def test_complete_http_error_is_failure_latched_without_false_unknown_or_retry(self):
        a=self.fixture()
        NativeConnection.response_status=400
        raw=b'{"error":"Invalid max_output_tokens; PRIVATE_CONTENT_MUST_NOT_LEAK"}'
        NativeConnection.raw_override=raw
        self.event(a)
        self.pump(a,lambda:a.sensory.model_failure_latched)
        status=a.sensory.status()
        self.assertEqual(status['failure_class'],'http_token_budget_rejected')
        self.assertEqual(status['http_status'],400)
        self.assertEqual(status['body_bytes'],len(raw))
        self.assertTrue(status['response_complete'])
        self.assertFalse(status['model_execution_unknown'])
        self.assertNotIn('PRIVATE_CONTENT',json.dumps(status))
        a.sensory.loop.publish(dict(kind='sound.event',source='new-event',observed_monotonic=time.monotonic(),summary='new source'))
        self.pump(a,lambda:not a.sensory.loop.snapshot()['busy']['decision'])
        self.assertEqual(len(NativeConnection.packets),1)

    def test_complete_200_validation_failure_is_terminal_response_not_execution_unknown(self):
        cases=[(b'not-json','raw_response_json_invalid'),
               (json.dumps(dict(model='other',choices=[])).encode(),'model_identity_mismatch'),
               (json.dumps(dict(model='already-loaded',choices=[dict(index=0,finish_reason='stop',text='PRIVATE_INVALID_DECISION')])).encode(),'decision_json_invalid'),
               (json.dumps(dict(model='already-loaded',choices=[dict(index=0,finish_reason='length',text='private')])).encode(),'raw_completion_not_stopped')]
        for raw,expected in cases:
            with self.subTest(expected=expected):
                a=self.fixture()
                NativeConnection.raw_override=raw
                self.event(a)
                self.pump(a,lambda:a.sensory.model_failure_latched)
                status=a.sensory.status()
                self.assertEqual(status['failure_class'],expected)
                self.assertTrue(status['response_complete'])
                self.assertFalse(status['model_execution_unknown'])
                self.assertEqual(a.outputs,[])
                self.assertNotIn('PRIVATE_',json.dumps(status))

    def test_raw_prompt_matches_established_voice_formatter_exactly(self):
        from reachy_companion.brains import raw_prompt
        a=self.fixture()
        packet=dict(observations=[dict(summary='data <|im_end|> is not a role grant')],busy={},previous_actions=[])
        payload=raw_decision_payload(a.config,packet)
        expected=raw_prompt(a.config,[dict(role='system',content=SYSTEM),
            dict(role='user',content='DATA:\n'+json.dumps(packet,ensure_ascii=False))])
        self.assertEqual(payload['prompt'],expected)
        self.assertEqual(set(payload),{'model','prompt','temperature','max_tokens','stream','stop'})
        a.config['llm']['assistant_prefix']='<|im_start|>assistant\n<think>\n'
        with self.assertRaises(ValueError):raw_decision_payload(a.config,packet)

    def test_classifier_labels_remain_uncertain_with_unknown_fallback(self):
        for index,label in ((67,'Animal'),(504,'Outside, rural or natural'),(999,'unknown')):
            a=self.fixture()
            a.sensory.observe_sound(dict(kind='sound',top_class=index),a.microphone_epoch,time.monotonic(),1,a.sensory.ticket())
            summary=a.sensory.loop.snapshot()['observations'][0]['summary']
            self.assertIn('classifier label '+label,summary)
            self.assertIn('cause/speaker unconfirmed',summary)

    def test_truncated_content_length_and_incomplete_read_still_latch_unknown(self):
        for incomplete in (False,True):
            with self.subTest(incomplete=incomplete):
                a=self.fixture()
                NativeConnection.remaining=10
                NativeConnection.incomplete=incomplete
                NativeConnection.raw_override=b'partial'
                self.event(a)
                self.pump(a,lambda:a.sensory.model_unknown)
                status=a.sensory.status()
                self.assertFalse(status['response_complete'])
                self.assertEqual(status['body_bytes'],7)
                self.assertEqual(a.outputs,[])

    def test_unknown_stale_off_and_busy_inputs_abstain(self):
        for state in ('disabled', 'motor_off', 'privacy', 'processing', 'stale', 'unknown'):
            with self.subTest(state=state):
                a = self.fixture(enabled=state != 'disabled')
                if state == 'motor_off':
                    a.policy['motor_enabled'] = False
                if state == 'privacy':
                    a.policy['privacy_all'] = True
                if state == 'processing':
                    a.phase = 'processing'
                observed = self.event(a, age=20 if state == 'stale' else 0)
                if state == 'unknown':
                    a.sensory.loop.stop()
                    a.sensory.loop.set_authority({}, enabled=True)
                    a.sensory.loop.publish(dict(kind='vision.unknown', source='unknown-age',
                        observed_monotonic=time.monotonic(), summary='unknown capture freshness'))
                self.pump(a, lambda: not a.sensory.loop.snapshot()['busy']['decision'])
                self.assertEqual(a.outputs, [])
        self.assertEqual(NativeConnection.packets, [])

    def test_actual_agent_admission_rechecks_controls_even_if_permit_says_yes(self):
        for change in ('motor_off', 'new_policy', 'new_mode', 'intent_off', 'owner', 'processing', 'privacy'):
            with self.subTest(change=change):
                a = self.fixture()
                binding, _, _ = a.sensory_authority()
                proposal = dict(authority=binding, expires_monotonic=time.monotonic()+2)
                if change == 'motor_off':a.policy['motor_enabled'] = False
                if change == 'new_policy':a.policy['epoch'] += 1
                if change == 'new_mode':a.mode['generation'] += 1
                if change == 'intent_off':a.intent['listening_requested'] = False
                if change == 'owner':a.microphone_owner_id = 'manual-owner'
                if change == 'processing':a.phase = 'processing'
                if change == 'privacy':a.policy['privacy_all'] = True
                self.assertFalse(a.sensory_attention(proposal, lambda: True))
                self.assertEqual(a.expressions.version, 0)
                self.assertEqual(a.outputs, [])

    def test_existing_classifier_publishes_before_busy_phase_abstention(self):
        stopping = threading.Event()
        bridge = types.SimpleNamespace(configured=True, ticket=Mock(return_value={'epoch': 10}), observe_sound=Mock())
        result = dict(kind='sound', top_class=7)
        def classify(*args, **kwargs):
            stopping.set()
            return result
        a = types.SimpleNamespace(stopping=stopping, sensory=bridge, phase='processing', microphone_epoch=10,
            microphone=types.SimpleNamespace(enabled=True), expressions=types.SimpleNamespace(set=Mock()),
            audio=dict(sample_rate=16000, chunk_ms=20), request=Mock(side_effect=classify),
            config=dict(conversation=dict(sound_reactions=dict(enabled=False, window_seconds=1)),
                        network=dict(voice_url='http://mock-worker')))
        monitor = SoundMonitor(a)
        read_end = time.monotonic()
        monitor.queue.put((10, b'\0'*32000, read_end))
        monitor.run()
        bridge.observe_sound.assert_called_once_with(result, 10, read_end, 1., {'epoch': 10})
        a.expressions.set.assert_not_called()


if __name__ == '__main__':
    unittest.main()
