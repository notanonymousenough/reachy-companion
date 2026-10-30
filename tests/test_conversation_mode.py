"""Saved panel selection and actual Agent request paths, without devices/network."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

from reachy_companion.r42.conversation_mode import ConversationMode
with patch.dict(sys.modules, {'webrtcvad': types.SimpleNamespace(Vad=Mock())}):
    from reachy_companion.r42.agent import Agent
from reachy_companion.r42.durable_intent import DurableIntent
from reachy_companion.r42.initiative import Initiative
from reachy_companion.r42.microphone import MicrophoneState
from reachy_companion.r42.motion_policy import MotionPolicy
from reachy_companion.hub import Hub


class ConversationModeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def agent(self):
        a = Agent.__new__(Agent)
        a.conversation_mode = ConversationMode(self.root / 'mode.json', 'alice_test')
        a.durable_intent = DurableIntent(self.root / 'intent.json')
        a.durable_intent.update(listening=True, automatic=True)
        a.microphone = MicrophoneState(self.root / 'mic.json')
        a.microphone_epoch = 0
        a.microphone_owner_id = None
        a.microphone_lock = threading.Lock()
        a.motion_policy = MotionPolicy(self.root / 'policy.json')
        a.agent_boot_id = 'boot'
        a.listening = threading.Event()
        a.listening.set()
        a.stopping = threading.Event()
        a.initiative = Initiative(a)
        a.capture_active = False
        a.volume = types.SimpleNamespace(percent=70)
        a.audio = {'playback_mixer': {'enabled': True}}
        a.phase = 'listening'
        a.config = types.SimpleNamespace(token='local-test-only')
        a.config = type('Config', (dict,), {'token': 'local-test-only'})(
            network={'voice_url': 'http://worker.invalid'}, streaming={'enabled': False},
            limits={'max_speech_chars': 2000, 'max_text_chars': 2000},
            timeouts={'client': 1}, conversation={'speech_address_prefix': 'Алиса, '})
        a._capture_enabled = lambda: False
        a.expressions = Mock()
        a.play = Mock()
        a.playback_process = a.voice_response = a.resume_audio = None
        a.request = Mock(return_value={'ok': True, 'reply': 'Да.'})
        return a

    def mode_command(self, a, mode, binding=None, generation=None):
        return a.panel_control(dict(action='mode_' + mode,
            binding=a.panel_state()['binding'] if binding is None else binding,
            mode_generation=a.conversation_mode.snapshot()['generation'] if generation is None else generation))

    def test_setting_survives_restart_and_legacy_default_is_only_initial(self):
        path = self.root / 'mode.json'
        state = ConversationMode(path, 'alice_test')
        state.save('normal', 0)
        self.assertEqual(ConversationMode(path, 'alice_test').snapshot(),
                         dict(version=1, mode='normal', generation=1, error=None))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_invalid_file_and_failed_write_never_claim_saved_test_mode(self):
        path = self.root / 'mode.json'
        path.write_text('{"version":1,"mode":"invalid","generation":true}')
        state = ConversationMode(path, 'alice_test')
        self.assertEqual(state.snapshot()['mode'], 'normal')
        self.assertTrue(state.snapshot()['error'])
        with patch.object(state, '_write', side_effect=OSError('disk')):
            with self.assertRaises(OSError): state.save('alice_test', 0)
        self.assertEqual(state.snapshot()['mode'], 'normal')
        state.save('normal', 0)
        self.assertIsNone(state.snapshot()['error'])

    def test_mode_does_not_change_any_audio_initiative_motion_or_intent(self):
        a = self.agent()
        before = (a.microphone.enabled, a.microphone_epoch, a.listening.is_set(),
                  a.durable_intent.path.read_bytes(), a.motion_policy.snapshot(),
                  a.initiative.schedule_status())
        result = self.mode_command(a, 'normal')
        after = (a.microphone.enabled, a.microphone_epoch, a.listening.is_set(),
                 a.durable_intent.path.read_bytes(), a.motion_policy.snapshot(),
                 a.initiative.schedule_status())
        self.assertEqual(before, after)
        self.assertEqual(result['scope'], ['conversation_mode'])
        a.play.assert_not_called()
        a.request.assert_not_called()

    def test_stale_binding_and_owner_privacy_rejected_without_mode_mutation(self):
        a = self.agent()
        for change in ('epoch', 'privacy', 'mic_owner', 'motion_owner', 'stop'):
            with self.subTest(change=change):
                original = a.panel_state()['binding']
                if change == 'epoch': original['microphone_epoch'] += 1
                if change == 'privacy': a.motion_policy.save(dict(motor_enabled=False, quiet=False, privacy_all=True))
                if change == 'mic_owner': a.microphone_owner_id = 'other'
                if change == 'motion_owner': a.motion_policy.owner_id = 'other'
                if change == 'stop': a.stopping.set()
                with self.assertRaises(RuntimeError): self.mode_command(a, 'normal', original)
                self.assertEqual(a.conversation_mode.snapshot()['mode'], 'alice_test')
                a.microphone_owner_id = a.motion_policy.owner_id = None
                a.stopping.clear()
                if change == 'privacy': a.motion_policy.save(dict(motor_enabled=False, quiet=False, privacy_all=False))
        self.mode_command(a, 'normal')
        with self.assertRaises(RuntimeError): self.mode_command(a, 'alice_test', generation=0)

    def test_mode_after_mic_off_never_reenables_capture_or_saved_intent(self):
        a = self.agent()
        a.microphone.enabled = False
        a.listening.clear()
        a.durable_intent.update(listening=False, automatic=False)
        self.mode_command(a, 'normal')
        self.assertFalse(a.microphone.enabled)
        self.assertFalse(a.listening.is_set())
        self.assertFalse(a.durable_intent.snapshot()['listening_requested'])
        self.assertFalse(a.durable_intent.snapshot()['automatic_questions_requested'])

    def test_unary_payload_is_one_snapshot_even_when_setting_changes_in_request(self):
        a = self.agent()
        payload = {'text': 'Вопрос', 'session': 'same'}
        original = copy.deepcopy(payload)
        sent = []
        def request(base, path, body):
            sent.append(copy.deepcopy(body))
            if len(sent) == 1: self.mode_command(a, 'normal')
            return {'ok': True, 'reply': 'Да.'}
        a.request.side_effect = request
        for _ in range(2): a.voice('/text', payload)
        self.assertEqual([v['speech_address_prefix'] for v in sent], ['Алиса, ', ''])
        self.assertEqual([v['conversation_mode'] for v in sent], ['alice_test', 'normal'])
        self.assertEqual(payload, original)
        self.assertEqual(a.config['conversation']['speech_address_prefix'], 'Алиса, ')

    def test_stream_and_initiative_say_use_same_saved_mode(self):
        a = self.agent()
        a.config['streaming'].update(enabled=True, sample_rate=16000,
            max_output_seconds=5, playback_latency_seconds=.08, max_event_bytes=4096)
        sent = []
        def open_request(request, **kwargs):
            sent.append(json.loads(request.data))
            response = io.BytesIO('{"type":"reply","reply":"Да."}\n{"type":"done","ok":true}\n'.encode())
            response.headers = types.SimpleNamespace(get_content_type=lambda: 'application/x-ndjson')
            return response
        a.http = types.SimpleNamespace(open=open_request)
        a.voice('/text', {'text': 'Вопрос', 'session': 'same'})
        self.mode_command(a, 'normal')
        a.voice('/say', {'text': 'Вопрос по кадру', 'session': 'same'}, initiative_generation=5)
        # A stale initiative still has its existing cancellation gate.
        self.assertEqual(len(sent), 1)
        a.initiative.valid = lambda generation: True
        a.voice('/say', {'text': 'Вопрос по кадру', 'session': 'same'}, initiative_generation=5)
        self.assertEqual([v['speech_address_prefix'] for v in sent], ['Алиса, ', ''])
        self.assertEqual([v['conversation_mode'] for v in sent], ['alice_test', 'normal'])

    def test_old_addressed_audio_is_not_resumed_after_mode_change(self):
        a = self.agent()
        self.mode_command(a, 'normal')
        result = a.voice('/say', {}, replay=dict(cursor_verified=True,
            spoken_text='Алиса, прежний ответ', conversation_mode='alice_test'))
        self.assertTrue(result['cancelled'])
        self.assertEqual(result['resume_blocked_reason'], 'conversation_mode_changed')
        a.request.assert_not_called()
        a.play.assert_not_called()

    def test_STOP_wins_stale_mode_command_and_never_receives_ON(self):
        a = self.agent()
        binding = a.panel_state()['binding']
        def off(enabled, **kwargs):
            self.assertIs(enabled, False)
            a.microphone.enabled = False
            a.microphone_epoch += 1
            a.listening.clear()
            a.durable_intent.update(listening=False, automatic=False)
        a.set_microphone = off
        a.set_motion_policy = Mock(return_value={'motor_enabled': False})
        a.panel_control({'action': 'stop'})
        with self.assertRaises(RuntimeError): self.mode_command(a, 'normal', binding)
        self.assertFalse(a.microphone.enabled)
        self.assertFalse(a.durable_intent.snapshot()['automatic_questions_requested'])

    def test_hub_forwards_only_exact_mode_command(self):
        h = Hub.__new__(Hub)
        h.config = {'timeouts': {'http': 5}}
        body = dict(action='mode_normal', binding={'agent_boot_id': 'boot'}, mode_generation=0)
        h.agent = Mock(return_value=dict(accepted=True, action='mode_normal', state={}))
        h.panel_control(body)
        self.assertEqual(h.agent.call_args.args, ('/panel-control', body))
        h.agent.reset_mock()
        for invalid in (dict(body, path='/microphone'), dict(body, mode_generation=True),
                        {'action': 'mode_normal'}, dict(body, action='mode_unknown')):
            with self.assertRaises(ValueError): h.panel_control(invalid)
        h.agent.assert_not_called()


if __name__ == '__main__':
    unittest.main()
