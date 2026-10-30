"""Canonical voice mode context, history, acknowledgements and legacy callers."""
import copy
import threading
import unittest
from unittest.mock import patch

import test_alice_speech_address as address_fixture
from reachy_companion.conversation_context import ALICE_CONTEXT, LEGACY_ALICE_CONTEXT, mode_session


class VoiceConversationModeTests(unittest.TestCase):
    setUp = address_fixture.AliceSpeechAddressTests.setUp

    def test_same_explicit_session_has_separate_test_normal_and_legacy_history(self):
        self.config.data['llm']['system_prompt'] = 'Ты Ричи, приятель.' + LEGACY_ALICE_CONTEXT + 'задавай вопросы.'
        before = copy.deepcopy(self.config.data)
        calls = []
        def answer(config, messages, *args, **kwargs):
            calls.append(copy.deepcopy(messages))
            return 'Ответ ' + str(len(calls))
        with patch('reachy_companion.brains.answer', side_effect=answer):
            for mode, text in [('normal', 'Человек: первая'), ('alice_test', 'Тест: первая'),
                               ('normal', 'Человек: вторая'), ('alice_test', 'Тест: вторая')]:
                self.pipeline.turn(dict(text=text, session='shared', conversation_mode=mode), '/text')
        self.assertEqual(self.spoken, ['Ответ 1', 'Алиса, Ответ 2', 'Ответ 3', 'Алиса, Ответ 4'])
        self.assertNotIn(LEGACY_ALICE_CONTEXT, calls[0][0]['content'])
        self.assertNotIn(ALICE_CONTEXT, calls[2][0]['content'])
        self.assertTrue(calls[1][0]['content'].endswith(ALICE_CONTEXT))
        self.assertEqual([m['content'] for m in calls[2][1:]], ['Человек: первая', 'Ответ 1', 'Человек: вторая'])
        self.assertEqual([m['content'] for m in calls[3][1:]], ['Тест: первая', 'Ответ 2', 'Тест: вторая'])
        self.assertEqual(set(self.pipeline.sessions), {mode_session('shared', 'normal'), mode_session('shared', 'alice_test')})
        self.assertEqual(self.config.data, before)

    def test_legacy_answer_mock_gets_no_new_keyword_and_original_session(self):
        def legacy_answer(text, session, interrupted=False):
            self.assertEqual(session, 'legacy')
            return 'Совместимо.', dict(used=0, messages=[dict(role='assistant', content='Совместимо.')])
        self.pipeline.answer = legacy_answer
        self.pipeline.turn(dict(text='Вопрос', session='legacy'), '/text')
        self.assertIn('legacy', self.pipeline.sessions)
        self.assertEqual(self.spoken, ['Алиса, Совместимо.'])

    def test_ack_and_final_use_same_mode_and_history_even_if_request_mutated(self):
        self.config.data['conversation']['interaction']['acknowledgements'] = dict(
            enabled=True, delay_seconds=0, phrases=dict(other='Сейчас отвечу.'))
        original = self.pipeline.answer
        for mode in ('normal', 'alice_test'):
            with self.subTest(mode=mode):
                released = threading.Event()
                def delayed(*args, **kwargs):
                    released.wait(2)
                    return original(*args, **kwargs)
                payload = dict(text='Вопрос ' + mode, session='same-ack', conversation_mode=mode)
                with patch.object(self.pipeline, 'answer', side_effect=delayed) as actual, \
                     patch('reachy_companion.brains.answer', return_value='Да.') as backend:
                    iterator = self.pipeline.stream(payload, '/text')
                    try:
                        first = next(iterator)
                        self.assertTrue(first['acknowledgement'])
                        payload['conversation_mode'] = 'alice_test' if mode == 'normal' else 'normal'
                    finally:
                        released.set()
                    rest = list(iterator)
                    self.assertEqual(actual.call_args.kwargs, dict(conversation_mode=mode))
                    self.assertEqual(actual.call_args.args[1], mode_session('same-ack', mode))
                    self.assertEqual(ALICE_CONTEXT in backend.call_args.args[1][0]['content'], mode == 'alice_test')
                final = next(v for v in rest if v['type'] == 'reply')
                if mode == 'alice_test':
                    self.assertEqual(first['spoken_text'], 'Алиса, Сейчас отвечу.')
                    self.assertEqual(final['spoken_text'], 'Алиса, Да.')
                else:
                    self.assertNotIn('spoken_text', first)
                    self.assertNotIn('spoken_text', final)
                self.assertEqual(rest[-1]['type'], 'done')
                self.assertIn(mode_session('same-ack', mode), self.pipeline.sessions)
        self.assertEqual(self.spoken, ['Сейчас отвечу.', 'Да.', 'Алиса, Сейчас отвечу.', 'Алиса, Да.'])

    def test_bad_enum_and_conflicting_prefix_rejected_before_side_effects(self):
        for fields in [dict(conversation_mode='unknown'), dict(conversation_mode=True),
                       dict(conversation_mode='normal', speech_address_prefix='Алиса, '),
                       dict(conversation_mode='alice_test', speech_address_prefix='')]:
            for path in ('/text', '/turn', '/say'):
                body = dict(text='Вопрос', pcm_base64='', **fields)
                with self.subTest(fields=fields, path=path):
                    with self.assertRaises(ValueError): self.pipeline.prepare(body, path)
                    with self.assertRaises(ValueError): self.pipeline.turn(body, path)
                    with self.assertRaises(ValueError): list(self.pipeline.stream(body, path))
        self.assertEqual(self.spoken, [])
        self.pipeline.check_robot.assert_not_called()
        self.pipeline.transcribe.assert_not_called()
        self.assertEqual(self.pipeline.sessions, {})
        self.assertFalse(self.pipeline.lock.locked())

    def test_raw_session_bounds_checked_before_hash_and_reset_only_selected_mode(self):
        too_long = 'x' * (self.config['limits']['max_session_chars'] + 1)
        for ack in (False, True):
            self.config.data['conversation']['interaction']['acknowledgements']['enabled'] = ack
            with self.assertRaises(ValueError):
                list(self.pipeline.stream(dict(text='Вопрос', session=too_long, conversation_mode='normal'), '/text'))
        with patch('reachy_companion.brains.answer', return_value='Да.'):
            for mode in ('normal', 'alice_test'):
                self.pipeline.turn(dict(text='Вопрос', session='reset', conversation_mode=mode), '/text')
        self.pipeline.classify = lambda text: dict(action='reset', intent='other', emotion='neutral')
        self.pipeline.turn(dict(text='Сброс', session='reset', conversation_mode='normal'), '/text')
        self.assertNotIn(mode_session('reset', 'normal'), self.pipeline.sessions)
        self.assertIn(mode_session('reset', 'alice_test'), self.pipeline.sessions)


if __name__ == '__main__':
    unittest.main()
