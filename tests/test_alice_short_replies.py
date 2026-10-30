"""Exact installed worker candidate: one bounded phrase before real TTS calls."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
REAL_RUN = subprocess.run
import types
import unittest
from unittest.mock import patch

import test_alice_speech_address as address_fixture
from test_stream_cleanup_overlay import load

ROOT = Path(__file__).resolve().parents[1]


class AliceShortRepliesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('alice_short_builder',
            ROOT/'deploy/autonomous/prepare_alice_short_replies.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)
        cls.original, cls.output = cls.builder.candidate()
        cls.module = load(cls.output['voice.py'])
        cls.config_module = types.ModuleType('alice_short_config')
        cls.config_module.__package__ = 'reachy_companion'
        exec(compile(cls.output['config.py'], 'config.py', 'exec'), cls.config_module.__dict__)

    def setUp(self):
        fixture = address_fixture.AliceSpeechAddressTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.p = fixture.pipeline
        self.p.__class__ = self.module.Pipeline
        self.spoken = fixture.spoken
        self.config = fixture.config
        self.config.data['conversation']['alice_short_replies'] = True

    def test_typed_config_default_off_profile_opt_in(self):
        self.assertFalse(self.config_module.Config(self.config.filename)['conversation']['alice_short_replies'])
        data = json.loads(self.config.filename.read_text())
        for value in (None, 0, 1, 'true', [], {}):
            data['conversation']['alice_short_replies'] = value
            self.config.filename.write_text(json.dumps(data))
            with self.assertRaises(ValueError): self.config_module.Config(self.config.filename)
        data['conversation'].pop('alice_short_replies')
        data['runtime']['profile'] = 'short.json'
        (self.config.root/'short.json').write_text(json.dumps(dict(conversation=dict(alice_short_replies=True))))
        self.config.filename.write_text(json.dumps(data))
        self.assertTrue(self.config_module.Config(self.config.filename)['conversation']['alice_short_replies'])

    def test_whole_phrase_limits_prefix_and_punctuation(self):
        valid = ('Да.', 'Почему небо синее?', 'Спасибо!', 'Да, это верно.',
                 'Один два три четыре пять шесть семь восемь девять десять.')
        for text in valid:
            for prefix in ('', 'Алиса, ', 'АЛИСА, '):
                self.assertEqual(self.module.validate_alice_phrase(prefix+text), text)
        invalid = ('', 'Без завершения', 'Почему небо синее', 'Да. Но это неверно.',
                   'Почему небо синее? А море?', 'Продолжение…', 'Да...', 'Да?!',
                   'Да？ Ещё.', 'Да؟ Ещё.', '<think>секрет</think>Да.', '**Да.**',
                   'Алиса, Алиса, да.', 'Алиса! Да.', 'Да, Alisa.', 'Да, Аlиса.',
                   'Один два три четыре пять шесть семь восемь девять десять одиннадцать.',
                   'Оченьдлинноеслово'*9+'.', 'Да.\n', 'Да\nверно.', 'Вероятность 3.14 процента.')
        for text in invalid:
            with self.subTest(text=text):
                with self.assertRaises(self.module.AlicePhraseRejected): self.module.validate_alice_phrase(text)

    def test_real_model_answer_unary_and_stream_only_one_dispatch_with_exact_prefix(self):
        for streaming in (False, True):
            self.spoken.clear()
            answer = '<emotion=curious>АЛИСА, Почему небо синее?'
            with patch('reachy_companion.brains.answer', return_value=answer) as model:
                result = (list(self.p.stream(dict(text='Вопрос', session='s'), '/text')) if streaming
                          else self.p.turn(dict(text='Вопрос', session='s'), '/text'))
            model.assert_called_once()
            self.assertEqual(self.spoken, ['Алиса, Почему небо синее?'])
            self.assertEqual(self.p.sessions['s']['messages'][-1]['content'], 'Почему небо синее?')
            row = result[0] if streaming else result
            self.assertEqual(row['spoken_text'], self.spoken[0])
            self.assertEqual(row['segments'], [dict(text='Почему небо синее?', emotion='curious', gesture='auto')])
            if streaming:
                # Two Piper chunks, then multiple PCM chunks, still one synthesize call.
                self.assertGreater(len([r for r in result if r['type']=='audio']), 2)
                self.assertEqual(result[-1]['type'], 'done')

    def test_rejected_full_answer_never_speaks_emits_or_commits_and_never_retries(self):
        candidates = ('Один два три четыре пять шесть семь восемь девять десять одиннадцать. Да.',
                      'Незаконченная реплика', 'Почему так? Почему иначе?',
                      'Алиса, Алиса, привет.', '<emotion=joy>Да. <emotion=neutral>Но это неверно.',
                      'Почему <emotion=curious>небо синее?')
        self.config.data['conversation']['interaction']['acknowledgements'] = dict(
            enabled=True, delay_seconds=0, phrases=dict(other='Сейчас отвечу.'))
        for answer in candidates:
            for streaming in (False, True):
                with self.subTest(answer=answer, streaming=streaming):
                    events = []
                    with patch('reachy_companion.brains.answer', return_value=answer) as model:
                        with self.assertRaises(self.module.AlicePhraseRejected):
                            if streaming:
                                for event in self.p.stream(dict(text='Вопрос', session='bad'), '/text'): events.append(event)
                            else: self.p.turn(dict(text='Вопрос', session='bad'), '/text')
                    model.assert_called_once()
                    self.assertEqual(events, [])
                    self.assertEqual(self.spoken, [])
                    self.assertNotIn('bad', self.p.sessions)
                    self.assertIsNone(self.p.last_turn)
                    self.assertFalse(self.p.lock.locked())

    def test_actual_tts_boundaries_reject_unchecked_segments_before_first_dispatch(self):
        segment = lambda text: dict(text=text, emotion='neutral', gesture='auto')
        for text in ('Слишком длинный ответ без законченного предложения', 'Да. Ещё.', 'Алиса, Алиса, да.'):
            with self.assertRaises(self.module.AlicePhraseRejected): self.p.synthesize(text)
            with self.assertRaises(self.module.AlicePhraseRejected): list(self.p.audio_events([segment(text)]))
        with self.assertRaises(self.module.AlicePhraseRejected):
            list(self.p.audio_events([segment('Да.'), segment('Нет.')]))
        self.assertEqual(self.spoken, [])

    def test_ack_disabled_in_mode_cancel_before_audio_and_stop_remain_silent(self):
        self.config.data['conversation']['interaction']['acknowledgements'] = dict(
            enabled=True, delay_seconds=0, phrases=dict(other='Сейчас отвечу.'))
        with patch('reachy_companion.brains.answer', return_value='Да.') as model:
            events = list(self.p.stream(dict(text='Вопрос'), '/text'))
        model.assert_called_once()
        self.assertEqual(self.spoken, ['Алиса, Да.'])
        self.assertFalse(any(r.get('acknowledgement') for r in events))
        self.spoken.clear()
        iterator = self.p.stream(dict(text='Привет.'), '/say')
        self.assertEqual(next(iterator)['type'], 'reply')
        iterator.close()
        self.assertEqual(self.spoken, [])
        self.p.classify = lambda text: dict(action='stop')
        events = list(self.p.stream(dict(text='Стоп'), '/text'))
        self.assertFalse(any(r['type']=='audio' for r in events))
        self.assertEqual(self.spoken, [])

    def test_outside_mode_default_and_request_override_keep_ordinary_voice(self):
        before = copy.deepcopy(self.config.data)
        self.config.data['conversation']['speech_address_prefix'] = ''
        list(self.p.stream(dict(text='Обычная длинная реплика. Продолжение!'), '/say'))
        self.assertEqual(self.spoken, ['Обычная длинная реплика. Продолжение!'])
        self.spoken.clear()
        list(self.p.stream(dict(text='Да.', speech_address_prefix='Алиса, '), '/say'))
        self.assertEqual(self.spoken, ['Алиса, Да.'])
        self.config.data = before
        self.config.data['conversation']['alice_short_replies'] = False
        self.spoken.clear()
        list(self.p.stream(dict(text='Алиса, длинный ответ. Ещё.'), '/say'))
        self.assertEqual(self.spoken, ['Алиса, длинный ответ. Ещё.'])

    def test_existing_schema_constraints_still_require_unchanged_text(self):
        rules = dict(schema_version='reply-1', max_chars=120, no_question=False, no_wake=False)
        with patch('reachy_companion.spoken_reply.check_profile'), \
                patch('reachy_companion.brains.answer', return_value='Алиса, Да.') as model:
            with self.assertRaisesRegex(RuntimeError, 'must remain unchanged'):
                self.p.turn(dict(text='Вопрос', session='schema', reply_constraints=rules), '/text')
        model.assert_called_once()
        self.assertEqual(model.call_args.kwargs['reply_constraints'], rules)
        self.assertEqual(self.spoken, [])
        self.assertNotIn('schema', self.p.sessions)
        with patch('reachy_companion.spoken_reply.check_profile'), \
                patch('reachy_companion.brains.answer', return_value='Да.'):
            result = self.p.turn(dict(text='Вопрос', reply_constraints=rules), '/text')
        self.assertEqual(result['reply'], 'Да.')
        self.assertEqual(self.spoken, ['Алиса, Да.'])

    def test_default_and_human_scope_match_exact_effective_worker(self):
        original = load(self.original['voice.py'])
        for enabled, prefix in ((False, 'Алиса, '), (True, '')):
            self.config.data['conversation'].update(alice_short_replies=enabled, speech_address_prefix=prefix)
            for streaming in (False, True):
                observations = []
                for module in (original, self.module):
                    self.p.__class__ = module.Pipeline
                    self.p.sessions = {}; self.p.agent_sessions = {}; self.spoken.clear()
                    answer = '<emotion=joy>Да. <emotion=neutral>Это полный обычный ответ без ограничения краткости.'
                    with patch('reachy_companion.brains.answer', return_value=answer) as model, \
                            patch.object(module.time, 'monotonic', return_value=100), \
                            patch.object(module.uuid, 'uuid4', return_value=types.SimpleNamespace(hex='fixed')):
                        payload = dict(text='Вопрос', session='parity')
                        result = (list(self.p.stream(payload, '/text')) if streaming else self.p.turn(payload, '/text'))
                    observations.append((result, list(self.spoken), copy.deepcopy(self.p.sessions), model.call_args))
                self.assertEqual(observations[0], observations[1])

    def test_exact_builder_portable_preimages_tamper_and_scope(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(subprocess, 'run', wraps=REAL_RUN):
            destination = Path(tmp)/'candidate'
            manifest = self.builder.build(destination)
            self.assertEqual(manifest['preimages'], {n:v[0] for n,v in self.builder.SOURCES.items()})
            for name, digest in manifest['files'].items():
                self.assertEqual(self.builder.sha((destination/name).read_bytes()), digest)
            self.assertFalse(manifest['devices_modified'])
            self.assertFalse(manifest['physical_dialogue_accepted'])
            with self.assertRaises(FileExistsError): self.builder.build(destination)
            with patch.object(self.builder.subprocess, 'check_output', return_value=b'HEAD is not baseline'):
                with self.assertRaises(ValueError): self.builder.build(Path(tmp)/'bad')
            self.assertFalse((Path(tmp)/'bad').exists())
        # No model/STT/audio-lifecycle/HTTP functions changed by the overlay.
        allowed = {'synthesize', 'prepare', 'audio_events', 'stream', 'alice_short_mode', 'alice_short_segments'}
        def unchanged(source):
            tree = ast.parse(source)
            tree.body = [n for n in tree.body if getattr(n, 'name', '') not in ('AlicePhraseRejected', 'validate_alice_phrase')]
            pipeline = next(n for n in tree.body if getattr(n, 'name', '')=='Pipeline')
            pipeline.body = [n for n in pipeline.body if getattr(n, 'name', '') not in allowed]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(unchanged(self.original['voice.py']), unchanged(self.output['voice.py']))


if __name__ == '__main__':
    unittest.main()
