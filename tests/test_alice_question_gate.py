"""Same raw model: complete question admission before any speech/history."""
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from test_alice_speech_address import AliceSpeechAddressTests as Fixture

ROOT = Path(__file__).resolve().parents[1]
VALID = 'Почему свет преломляется?'
INVALID = 'Почему это так? Как это изменяется?'


class AliceQuestionGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('question_gate_builder',
            ROOT/'deploy/autonomous/prepare_alice_question_gate.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)
        _, files = cls.builder.candidate()
        cls.module = types.ModuleType('reachy_companion.question_gate_fixture')
        cls.module.__package__ = 'reachy_companion'
        piper = types.SimpleNamespace(PiperVoice=object, SynthesisConfig=object)
        vosk = types.SimpleNamespace(Model=object, KaldiRecognizer=object, SetLogLevel=object)
        with patch.dict(sys.modules, {'piper': piper, 'vosk': vosk}):
            exec(compile(files['voice.py'], 'voice-question-gate.py', 'exec'), cls.module.__dict__)
        cls.cfg_module = types.ModuleType('question_gate_config')
        cls.cfg_module.__package__ = 'reachy_companion'
        exec(compile(files['config.py'], 'config-question-gate.py', 'exec'), cls.cfg_module.__dict__)

    def setUp(self):
        fixture = Fixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.p = fixture.pipeline
        self.p.__class__ = self.module.Pipeline
        self.spoken = fixture.spoken
        self.config = fixture.config
        self.config.data['conversation']['alice_question_gate'] = True
        self.config.data['timeouts']['llm'] = 10
        self.now = 100.
        clock = patch.object(self.module.time, 'monotonic', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.op = dict(agent_boot_id='boot', microphone_epoch=11, microphone_owner_id=None,
            microphone_enabled=True, capture_active=False, phase='processing', listening=True,
            microphone_state_error=None, motion_policy=dict(epoch=7, motor_enabled=True, quiet=False, privacy_all=False),
            motion_policy_owner_id=None, expression_version=0)
        self.p.request = Mock(side_effect=lambda *a, **k: copy.deepcopy(self.op))

    def turn(self, text='Почему облака белые?'):
        return self.p.turn(dict(text=text, session='s'), '/text')

    def test_config_default_off_and_typed_profile_opt_in(self):
        cfg = self.cfg_module.Config(self.config.filename)
        self.assertFalse(cfg['conversation']['alice_question_gate'])
        import json
        data = json.loads(self.config.filename.read_text())
        for value in (None, 0, 1, 'true', []):
            data['conversation']['alice_question_gate'] = value
            self.config.filename.write_text(json.dumps(data))
            with self.assertRaises(ValueError): self.cfg_module.Config(self.config.filename)
        data['conversation']['alice_question_gate'] = True
        self.config.filename.write_text(json.dumps(data))
        self.assertTrue(self.cfg_module.Config(self.config.filename)['conversation']['alice_question_gate'])

    def test_whole_question_validator_never_selects_or_repairs(self):
        self.assertEqual(self.module.validate_alice_question(VALID), VALID)
        self.assertEqual(self.module.validate_alice_question('<emotion=curious>'+VALID), VALID)
        for text in (INVALID, 'Почему облака становятся белыми при таком рассеянии света?',
                     'Почему?', 'Включишь музыку прямо сейчас?', 'Алиса, почему свет преломляется?',
                     'Почему свет преломляется.', '<think><think>x</think>'+VALID+'</think>'):
            with self.subTest(text=text):
                with self.assertRaises(self.module.AliceQuestionRejected):
                    self.module.validate_alice_question(text)

    def test_valid_candidate_once_is_only_speech_and_history(self):
        with patch('reachy_companion.brains.answer', return_value=VALID) as backend:
            result = self.turn()
        backend.assert_called_once()
        self.assertEqual(self.spoken, ['Алиса, '+VALID])
        self.assertEqual(self.p.sessions['s']['messages'][-1]['content'], VALID)
        self.assertEqual(result['alice_question_generation_attempts'], 1)
        self.assertTrue(result['alice_question_gate_validated'])
        self.assertEqual(self.config['timeouts']['llm'], 10)
        self.assertEqual(backend.call_args.args[0]['network'], self.config['network'])
        self.assertEqual(backend.call_args.args[0]['llm'], self.config['llm'])

    def test_one_regeneration_shares_deadline_original_input_and_no_invalid_history(self):
        calls = []
        def backend(config, messages, session):
            calls.append((config['timeouts']['llm'], copy.deepcopy(messages), session))
            if len(calls) == 1:
                self.now += 4
                return INVALID
            return VALID
        with patch('reachy_companion.brains.answer', side_effect=backend):
            result = self.turn()
        self.assertEqual([c[0] for c in calls], [10, 6])
        self.assertEqual(calls[0][1][-1], calls[1][1][-1])
        self.assertEqual(calls[0][2], calls[1][2])
        self.assertNotIn(INVALID, str(calls[1][1]))
        self.assertEqual(result['alice_question_generation_attempts'], 2)
        self.assertEqual(self.spoken, ['Алиса, '+VALID])
        self.assertNotIn(INVALID, str(self.p.sessions))
        self.assertEqual(self.config['timeouts']['llm'], 10)

    def test_two_invalid_candidates_never_ack_speak_or_commit(self):
        self.config.data['conversation']['interaction']['acknowledgements']['enabled'] = True
        events = []
        with patch('reachy_companion.brains.answer', return_value=INVALID) as backend:
            with self.assertRaises(self.module.AliceQuestionRejected):
                for event in self.p.stream(dict(text='Почему облака белые?', session='s'), '/text'):
                    events.append(event)
        self.assertEqual(backend.call_count, 2)
        self.assertEqual(events, [])
        self.assertEqual(self.spoken, [])
        self.assertEqual(self.p.sessions, {})
        self.assertIsNone(self.p.last_turn)
        self.assertFalse(self.p.lock.locked())

    def test_valid_stream_regeneration_speaks_only_valid_final_without_ack(self):
        self.config.data['conversation']['interaction']['acknowledgements']['enabled'] = True
        with patch('reachy_companion.brains.answer', side_effect=[INVALID, VALID]) as backend:
            events = list(self.p.stream(dict(text='Почему облака белые?', session='s'), '/text'))
        self.assertEqual(backend.call_count, 2)
        self.assertEqual(self.spoken, ['Алиса, '+VALID])
        self.assertTrue(any(row['type'] == 'audio' for row in events))
        self.assertEqual(events[-1]['type'], 'done')
        self.assertEqual(events[-1]['alice_question_generation_attempts'], 2)
        self.assertNotIn(INVALID, str(events)+str(self.p.sessions))
        self.assertFalse(any(row.get('acknowledgement') for row in events))

    def test_stop_at_final_pretts_guard_prevents_output(self):
        calls = []
        def request(*a, **k):
            calls.append(True)
            if len(calls) == 6: self.op['microphone_enabled'] = False
            return copy.deepcopy(self.op)
        self.p.request.side_effect = request
        with patch('reachy_companion.brains.answer', return_value=VALID) as backend:
            with self.assertRaises(RuntimeError): self.turn()
        backend.assert_called_once()
        self.assertEqual(self.spoken, [])
        self.assertEqual(self.p.sessions, {})

    def test_backend_errors_and_unknown_completions_are_never_retried(self):
        errors = (TimeoutError('unknown model completion'), RuntimeError('incomplete model terminal'),
                  HTTPError('http://test', 503, 'failed', {}, None))
        for error in errors:
            with self.subTest(error=type(error).__name__):
                with patch('reachy_companion.brains.answer', side_effect=error) as backend:
                    with self.assertRaises(type(error)): self.turn()
                backend.assert_called_once()
                self.assertEqual(self.spoken, [])
                self.assertEqual(self.p.sessions, {})

    def test_deadline_expiry_after_model_blocks_speech_and_regeneration(self):
        for result in (VALID, INVALID):
            def backend(*a, **k): self.now += 11; return result
            with patch('reachy_companion.brains.answer', side_effect=backend) as called:
                with self.assertRaises(TimeoutError): self.turn()
            called.assert_called_once()
            self.assertEqual(self.spoken, [])
            self.assertEqual(self.p.sessions, {})

    def test_stop_new_epoch_and_pause_after_model_block_all_output(self):
        for change in ('off', 'epoch', 'owner', 'pause'):
            with self.subTest(change=change):
                before = copy.deepcopy(self.op)
                def backend(*a, **k):
                    if change == 'off': self.op['microphone_enabled'] = False
                    if change == 'epoch': self.op['microphone_epoch'] += 1
                    if change == 'owner':
                        self.op['microphone_owner_id'] = self.op['motion_policy_owner_id'] = 'new'
                    if change == 'pause': self.op['listening'] = False
                    return INVALID
                with patch('reachy_companion.brains.answer', side_effect=backend) as called:
                    with self.assertRaises(RuntimeError): self.turn()
                called.assert_called_once()
                self.assertEqual(self.spoken, [])
                self.assertEqual(self.p.sessions, {})
                self.op = before

    def test_stop_during_stt_prevents_first_model(self):
        def stt(pcm): self.op['microphone_epoch'] += 1; return 'Почему облака белые?'
        self.p.transcribe.side_effect = stt
        import base64
        with patch('reachy_companion.brains.answer') as backend:
            with self.assertRaises(RuntimeError):
                self.p.turn(dict(pcm_base64=base64.b64encode(b'pcm').decode(), session='s'), '/turn')
        backend.assert_not_called()
        self.assertEqual(self.spoken, [])

    def test_unknown_or_slow_authority_prevents_any_model(self):
        for change in ('phase', 'owners', 'slow'):
            before = copy.deepcopy(self.op)
            if change == 'phase': self.op['phase'] = 'unknown'
            if change == 'owners': self.op['microphone_owner_id'] = 'one-owner'
            if change == 'slow':
                def slow(*a, **k): self.now += .31; return copy.deepcopy(self.op)
                self.p.request.side_effect = slow
            with patch('reachy_companion.brains.answer') as backend:
                with self.assertRaises((RuntimeError, TimeoutError)): self.turn()
            backend.assert_not_called()
            self.op = before
            self.p.request.side_effect = lambda *a, **k: copy.deepcopy(self.op)

    def test_explicit_details_bypasses_shortness_and_keeps_original_budget(self):
        long = 'Свет рассеивается каплями воды, поэтому облака выглядят белыми. Размер капель влияет на рассеяние.'
        with patch('reachy_companion.brains.answer', return_value=long) as backend:
            result = self.turn('Раскрой подробнее, почему облака белые.')
        backend.assert_called_once()
        self.assertIs(backend.call_args.args[0], self.config)
        self.assertEqual(self.spoken, ['Алиса, '+long])
        self.assertNotIn('alice_question_gate_validated', result)
        self.assertEqual(self.p.sessions['s']['messages'][-1]['content'], long)
        for text in ('Не надо подробно.', 'Хочешь узнать подробнее?', 'Что значит подробно?'):
            self.assertFalse(self.module.explicit_details(text))

    def test_gate_off_or_human_prefix_retains_legacy_generation(self):
        for enabled, prefix in ((False, 'Алиса, '), (True, '')):
            self.config.data['conversation']['alice_question_gate'] = enabled
            self.config.data['conversation']['speech_address_prefix'] = prefix
            with patch('reachy_companion.brains.answer', return_value=INVALID) as backend:
                result = self.turn()
            backend.assert_called_once()
            self.assertNotIn('alice_question_gate_validated', result)

    def test_manual_say_and_stop_do_not_generate_or_use_gate(self):
        with patch('reachy_companion.brains.answer') as backend:
            result = self.p.turn(dict(text='Алиса, почему облака белые?', session='s'), '/say')
        backend.assert_not_called()
        self.assertEqual(result['reply'], 'Алиса, почему облака белые?')
        self.assertEqual(self.p.request.call_count, 0)
        self.p.classify = lambda text: dict(action='stop', intent='request', emotion='neutral')
        with patch('reachy_companion.brains.answer') as backend:
            result = self.turn('Стоп')
        backend.assert_not_called()
        self.assertEqual(result['command'], 'stop')

    def test_precomputed_invalid_candidate_cannot_bypass_gate(self):
        with patch('reachy_companion.brains.answer') as backend:
            with self.assertRaises(ValueError):
                self.p.prepare(dict(text='Почему облака белые?', session='s'), '/text',
                               answer_result=(INVALID, {}))
        backend.assert_not_called()
        self.assertEqual(self.spoken, [])
