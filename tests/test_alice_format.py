"""S2 exact installed S0 overlay: local model/TTS fixtures, no device/network."""
import ast
import base64
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

import test_alice_short_replies as s0_tests
from test_stream_cleanup_overlay import load

ROOT = Path(__file__).resolve().parents[1]
REAL_RUN = subprocess.run


class AliceFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('alice_format_builder',
            ROOT/'deploy/autonomous/prepare_alice_format.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)
        cls.original, cls.output = cls.builder.candidate()
        cls.module = load(cls.output['voice.py'])

    setUp = s0_tests.AliceShortRepliesTests.setUp
    test_actual_tts_boundaries_reject_unchecked_segments_before_first_dispatch = (
        s0_tests.AliceShortRepliesTests.test_actual_tts_boundaries_reject_unchecked_segments_before_first_dispatch)
    test_ack_disabled_in_mode_cancel_before_audio_and_stop_remain_silent = (
        s0_tests.AliceShortRepliesTests.test_ack_disabled_in_mode_cancel_before_audio_and_stop_remain_silent)
    test_existing_schema_constraints_still_require_unchanged_text = (
        s0_tests.AliceShortRepliesTests.test_existing_schema_constraints_still_require_unchanged_text)
    test_whole_phrase_limits_prefix_and_punctuation = (
        s0_tests.AliceShortRepliesTests.test_whole_phrase_limits_prefix_and_punctuation)

    def test_generation_receives_scoped_format_before_single_model_call(self):
        before = copy.deepcopy(self.config.data)
        for streaming in (False, True):
            for path in ('/text', '/turn'):
                self.p.sessions = {}; self.p.agent_sessions = {}; self.spoken.clear()
                def answer(config, messages, session):
                    # Assertions run inside the model boundary, before returning output.
                    self.assertEqual(config.data, before)
                    self.assertEqual(messages[0], dict(role='system', content=(
                        before['llm']['system_prompt'] + self.module.ALICE_SHORT_FORMAT)))
                    self.assertIn('11 слов', messages[0]['content'])
                    self.assertIn('10 слов после него', messages[0]['content'])
                    self.assertIn('Внутри предложения не меняй метки', messages[0]['content'])
                    self.assertEqual(messages[-1]['role'], 'user')
                    return '<emotion=curious><gesture=tilt>Алиса, Почему небо синее?'
                with patch('reachy_companion.brains.answer', side_effect=answer) as model:
                    payload = dict(text='Вопрос', pcm_base64=base64.b64encode(b'fixture').decode(), session='s')
                    result = list(self.p.stream(payload, path)) if streaming else self.p.turn(payload, path)
                model.assert_called_once()
                self.assertEqual(self.spoken, ['Алиса, Почему небо синее?'])
                self.assertEqual(self.p.sessions['s']['messages'][-1]['content'], 'Почему небо синее?')
                self.assertEqual((result[0] if streaming else result)['segments'], [dict(
                    text='Почему небо синее?', emotion='curious', gesture='tilt')])

    def test_harmless_style_splits_validate_all_words_then_single_dispatch(self):
        answers = (
            '<emotion=curious><gesture=tilt>АЛИСА, Почему <emotion=thoughtful>небо <gesture=nod>синее?',
            '<emotion=curious><gesture=tilt>Почему <emotion=thoughtful>небо <gesture=nod>синее?',
        )
        for answer in answers:
            for streaming in (False, True):
                self.spoken.clear()
                with patch('reachy_companion.brains.answer', return_value=answer) as model:
                    result = (list(self.p.stream(dict(text='Вопрос', session='s'), '/text')) if streaming
                              else self.p.turn(dict(text='Вопрос', session='s'), '/text'))
                model.assert_called_once()
                self.assertEqual(self.spoken, ['Алиса, Почему небо синее?'])
                row = result[0] if streaming else result
                self.assertEqual(row['reply'], 'Почему небо синее?')
                self.assertEqual(row['segments'], [dict(text=row['reply'], emotion='curious', gesture='tilt')])
                self.assertEqual(row['spoken_text'], self.spoken[0])
                self.assertEqual(self.p.sessions['s']['messages'][-1]['content'], row['reply'])
                if streaming:
                    self.assertGreater(sum(r['type']=='audio' for r in result), 2)
                    self.assertEqual(result[-1]['type'], 'done')

    def test_aggregate_eleven_word_limit_including_prefix_and_direct_audio_boundary(self):
        segment = lambda text: dict(text=text, emotion='neutral', gesture='auto')
        segments = [segment('Алиса, Один два три четыре пять'), segment('шесть семь восемь девять десять.')]
        before = copy.deepcopy(segments)
        events = list(self.p.audio_events(segments))
        self.assertEqual(segments, before)
        self.assertEqual(self.spoken, ['Алиса, Один два три четыре пять шесть семь восемь девять десять.'])
        self.assertTrue(any(r['type']=='audio' for r in events))
        self.spoken.clear()
        segments[-1]['text'] = 'шесть семь восемь девять десять одиннадцать.'
        with self.assertRaises(self.module.AlicePhraseRejected): list(self.p.audio_events(segments))
        self.assertEqual(self.spoken, [])

    def test_rejected_aggregates_have_no_events_tts_history_or_retry(self):
        candidates = (
            '<emotion=curious>Почему <emotion=thoughtful>небо синее',
            '<emotion=joy>Да. <emotion=neutral>Это верно.',
            '<emotion=curious>Почему небо синее? <gesture=tilt>А море?',
            '<emotion=neutral>Алиса, Один два три четыре пять <emotion=joy>шесть семь восемь девять десять одиннадцать.',
            '<emotion=neutral>Один два три четыре пять шесть семь восемь девять десять одиннадцать. <emotion=joy>Да.',
            'Алиса, <emotion=joy>Алиса, да.',
            '<emotion=curious>Алиса, Почему <emotion=joy>Алиса, небо синее?',
            '<emotion=curious>Почему <gesture=tilt>небо синее?..',
            'По<emotion=curious>чему небо синее?',
            'Почему<emotion=curious>небо синее?',
        )
        self.config.data['conversation']['interaction']['acknowledgements'] = dict(
            enabled=True, delay_seconds=0, phrases=dict(other='Сейчас отвечу.'))
        for answer in candidates:
            for streaming in (False, True):
                with self.subTest(answer=answer, streaming=streaming):
                    self.p.last_turn = None
                    self.p.sessions = {'bad': dict(used=100, messages=[dict(role='assistant', content='Ранее.')])}
                    previous = copy.deepcopy(self.p.sessions)
                    events = []
                    with patch('reachy_companion.brains.answer', return_value=answer) as model, \
                            patch.object(self.module.time, 'monotonic', return_value=100):
                        with self.assertRaises(self.module.AlicePhraseRejected):
                            if streaming:
                                for event in self.p.stream(dict(text='Вопрос', session='bad'), '/text'): events.append(event)
                            else: self.p.turn(dict(text='Вопрос', session='bad'), '/text')
                    model.assert_called_once()
                    self.assertEqual(events, [])
                    self.assertEqual(self.spoken, [])
                    self.assertEqual(self.p.sessions, previous)
                    self.assertIsNone(self.p.last_turn)
                    self.assertFalse(self.p.lock.locked())

    def test_existing_parser_eight_segment_cap_does_not_drop_tail(self):
        answer = ' '.join('<emotion=neutral>'+word for word in (
            'Один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять', 'десять.'))
        with patch('reachy_companion.brains.answer', return_value=answer):
            events = list(self.p.stream(dict(text='Вопрос'), '/text'))
        self.assertEqual(events[0]['reply'], 'Один два три четыре пять шесть семь восемь девять десять.')
        self.assertEqual(len(self.spoken), 1)
        self.spoken.clear()
        for tail in (' <gesture=tilt>Ещё.', ' <gesture=tilt>Продолжение'):
            with patch('reachy_companion.brains.answer', return_value=answer+tail) as model:
                with self.assertRaises(self.module.AlicePhraseRejected):
                    list(self.p.stream(dict(text='Вопрос'), '/text'))
            model.assert_called_once()
            self.assertEqual(self.spoken, [])

    def test_cancel_after_normalized_reply_before_audio_keeps_history_uncommitted(self):
        with patch('reachy_companion.brains.answer', return_value='Почему <emotion=curious>небо синее?') as model:
            iterator = self.p.stream(dict(text='Вопрос', session='cancel'), '/text')
            self.assertEqual(next(iterator)['segments'], [dict(text='Почему небо синее?', emotion='neutral', gesture='auto')])
            iterator.close()
        model.assert_called_once()
        self.assertEqual(self.spoken, [])
        self.assertNotIn('cancel', self.p.sessions)
        self.assertIsNone(self.p.last_turn)
        self.assertFalse(self.p.lock.locked())

    def test_next_model_sees_spoken_body_history_and_one_current_format(self):
        captured = []
        def answer(config, messages, session):
            captured.append(copy.deepcopy(messages))
            return 'Алиса, Запомнил <emotion=joy>клён.' if len(captured)==1 else 'Алиса, Клён.'
        with patch('reachy_companion.brains.answer', side_effect=answer) as model:
            for text in ('Мой маркер — клён.', 'Какой мой маркер?'):
                list(self.p.stream(dict(text=text, session='history', previous_reply_interrupted=True), '/text'))
        self.assertEqual(model.call_count, 2)
        self.assertEqual(captured[1][1:3], [dict(role='user', content='Мой маркер — клён.'),
                                         dict(role='assistant', content='Запомнил клён.')])
        self.assertEqual(captured[1][0]['content'].count(self.module.ALICE_SHORT_FORMAT), 1)
        self.assertIn('прерван', captured[1][-2]['content'])
        self.assertEqual(self.spoken, ['Алиса, Запомнил клён.', 'Алиса, Клён.'])

    def test_false_missing_flag_and_human_override_match_exact_s0(self):
        original = load(self.original['voice.py'])
        scenarios = ((False, 'Алиса, ', {}), (None, 'Алиса, ', {}), (True, '', {}),
                     (True, 'Алиса, ', dict(speech_address_prefix='')))
        for enabled, prefix, overrides in scenarios:
            self.config.data['conversation']['speech_address_prefix'] = prefix
            if enabled is None: self.config.data['conversation'].pop('alice_short_replies', None)
            else: self.config.data['conversation']['alice_short_replies'] = enabled
            for streaming in (False, True):
                observations = []
                for module in (original, self.module):
                    self.p.__class__ = module.Pipeline
                    self.p.sessions = {}; self.p.agent_sessions = {}; self.spoken.clear()
                    answer = '<emotion=joy>Да. <emotion=neutral>Это полный обычный ответ без ограничения краткости.'
                    with patch('reachy_companion.brains.answer', return_value=answer) as model, \
                            patch.object(module.time, 'monotonic', return_value=100), \
                            patch.object(module.uuid, 'uuid4', return_value=types.SimpleNamespace(hex='fixed')):
                        payload = dict(text='Вопрос', session='parity', **overrides)
                        result = list(self.p.stream(payload, '/text')) if streaming else self.p.turn(payload, '/text')
                    observations.append((result, list(self.spoken), copy.deepcopy(self.p.sessions), model.call_args))
                    self.assertNotIn(self.module.ALICE_SHORT_FORMAT, model.call_args.args[1][0]['content'])
                self.assertEqual(observations[0], observations[1])

    def test_request_opt_in_and_next_human_request_do_not_leak_format(self):
        self.config.data['conversation']['speech_address_prefix'] = ''
        before = copy.deepcopy(self.config.data)
        with patch('reachy_companion.brains.answer', return_value='Да.') as model:
            list(self.p.stream(dict(text='Вопрос', speech_address_prefix='Алиса, '), '/text'))
            list(self.p.stream(dict(text='Вопрос'), '/text'))
        self.assertTrue(model.call_args_list[0].args[1][0]['content'].endswith(self.module.ALICE_SHORT_FORMAT))
        self.assertEqual(model.call_args_list[1].args[1][0]['content'], before['llm']['system_prompt'])
        self.assertEqual(self.config.data, before)
        self.assertEqual(self.spoken, ['Алиса, Да.', 'Да.'])

    def test_exact_portable_builder_tamper_guards_and_ast_scope(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(subprocess, 'run', wraps=REAL_RUN):
            destination = Path(tmp)/'candidate'
            manifest = self.builder.build(destination)
            self.assertEqual(manifest['outputs'], {'voice.py': self.builder.OUTPUT})
            self.assertEqual(manifest['preimages'], {'voice.py': self.builder.PREIMAGE})
            self.assertEqual(manifest['unchanged_required_modules'], {'config.py': self.builder.CONFIG})
            self.assertEqual(json.loads((destination/'transfer-manifest.json').read_text())['files'], manifest['outputs'])
            self.assertFalse((destination/'config.py').exists())
            for name, digest in manifest['files'].items():
                self.assertEqual(self.builder.sha((destination/name).read_bytes()), digest)
            # Real portable patch tool; no git checkout or model needed to apply/reverse.
            work = Path(tmp)/'portable'; work.mkdir()
            (work/'voice.py').write_bytes(self.original['voice.py'])
            patch_path = destination/'patches/voice.py.patch'
            for options, expected in (([], self.output['voice.py']), (['-R'], self.original['voice.py'])):
                REAL_RUN(['patch', '--batch', '--fuzz=0', '-p1', *options, '-i', str(patch_path)], cwd=work,
                         check=True, capture_output=True)
                self.assertEqual((work/'voice.py').read_bytes(), expected)
            with self.assertRaises(FileExistsError): self.builder.build(destination)
            for pin in ('S0_BUILDER_SHA', 'PREIMAGE', 'CONFIG', 'PATCH', 'OUTPUT'):
                with patch.object(self.builder, pin, 'invalid'):
                    with self.assertRaises(ValueError): self.builder.build(Path(tmp)/pin)
                self.assertFalse((Path(tmp)/pin).exists())
        def unchanged(source):
            tree = ast.parse(source)
            tree.body = [node for node in tree.body if not (isinstance(node, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id=='ALICE_SHORT_FORMAT' for t in node.targets))]
            pipeline = next(n for n in tree.body if getattr(n, 'name', '')=='Pipeline')
            pipeline.body = [n for n in pipeline.body if getattr(n, 'name', '') not in ('answer', 'prepare', 'alice_short_segments')]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(unchanged(self.original['voice.py']), unchanged(self.output['voice.py']))


if __name__ == '__main__':
    unittest.main()
