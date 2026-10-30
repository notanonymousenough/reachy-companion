"""Local persisted experience; no model, identity inference, export or hardware."""
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reachy_companion.experience import Experience, MemoryConflict


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = Experience(self.root)
        self.addCleanup(lambda: self.memory.close())

    def turn(self, number=0, mode='normal', **changes):
        values = dict(turn_id='turn-' + str(number), session='local-session', source='worker.completed',
                      mode=mode, user_text='Мой маркер — клён.', reply_text='Запомнил сказанное.',
                      completed=True, at='2026-10-18T10:00:' + str(number).zfill(2) + 'Z')
        values.update(changes)
        return self.memory.record_turn(**values)

    def test_completed_episode_survives_new_instance_and_has_real_provenance(self):
        receipt = self.turn()
        second = Experience(self.root)
        try:
            recalled = second.recall('клён', 'normal')
        finally:
            second.close()
        item = recalled['items'][0]
        self.assertEqual(item['source'], 'worker.completed')
        self.assertEqual(item['at'], '2026-10-18T10:00:00Z')
        self.assertEqual(item['evidence'], [receipt['evidence_id']])
        self.assertEqual(item['content']['speaker'], 'unknown')
        self.assertNotEqual(item['content']['session'], 'local-session')
        self.assertEqual(self.turn()['duplicate'], True)
        self.assertEqual(len(self.memory.recall('', 'normal')['items']), 1)

    def test_normal_test_separation_before_recall_limit(self):
        for number in range(12):
            self.turn(number, 'alice_test', user_text='Тестовая Алиса: ' + str(number))
        self.turn(20, 'normal', user_text='Обычный собеседник')
        normal = self.memory.recall('', 'normal')
        test = self.memory.recall('', 'alice_test')
        self.assertEqual(len(normal['items']), 1)
        self.assertNotIn('Тестовая Алиса', normal['context'])
        self.assertNotIn('Обычный собеседник', test['context'])
        self.assertEqual(test['items'][0]['at'], '2026-10-18T10:00:11Z')

    def test_incomplete_private_and_secret_like_text_not_recorded(self):
        self.assertFalse(self.turn(completed=False)['recorded'])
        self.assertFalse(self.turn(private=True)['recorded'])
        for private in ('мой пароль — кот', 'Authorization: Bearer abc', 'sk-abcdef', 'A' * 40):
            with self.subTest(text=private), self.assertRaises(ValueError):
                self.turn(user_text=private)
        self.assertEqual(self.memory.recall('', 'normal')['items'], [])

    def test_versioned_persona_goal_reason_parent_and_rollback(self):
        evidence = self.turn()['evidence_id']
        options = dict(source='operator.charter', mode='normal', evidence_ids=[evidence], at='2026-10-18T10:01:00Z')
        first = self.memory.revise('persona', 'Прямой любопытный приятель.', reason='Начальный выбор пользователя.', **options)
        self.assertEqual(first['version'], 0)
        self.memory.revise('persona', 'Прямой спокойный приятель.', reason='Уменьшить колкости.', expected_version=0, **options)
        unchanged = self.memory.revise('persona', 'Прямой спокойный приятель.', reason='Повторный тик.', expected_version=1, **options)
        self.assertFalse(unchanged['changed'])
        restored = self.memory.revise('persona', 'Прямой любопытный приятель.', reason='Отмена изменения.',
                                      expected_version=1, restore_version=0, **options)
        self.assertEqual(restored['version'], 2)
        self.memory.revise('goal', 'Обсудить выбранный маркер.', reason='Продолжить реальный эпизод.', **options)
        entries = self.memory.recall('', 'normal')['items']
        persona = next(item for item in entries if item['id'].endswith(':persona'))
        self.assertEqual(persona['content']['restores'], 0)
        self.assertEqual(persona['parent'], persona['id'] + ':1')
        self.assertEqual(persona['content']['reason'], 'Отмена изменения.')
        with self.assertRaises(ValueError): self.memory.revise('goal', '', reason='Нет цели.', **options)

    def test_CAS_missing_crossmode_evidence_and_false_rollback_rejected(self):
        evidence = self.turn()['evidence_id']
        options = dict(reason='Реальное изменение.', source='operator', mode='normal', evidence_ids=[evidence])
        self.memory.revise('principles', 'Не выдумывать ощущения.', **options)
        with self.assertRaises(MemoryConflict):
            self.memory.revise('principles', 'Другая версия.', expected_version=3, **options)
        with self.assertRaises(MemoryConflict):
            self.memory.revise('goal', 'Рассмотреть тему.', **dict(options, evidence_ids=['invented']))
        with self.assertRaises(MemoryConflict):
            self.memory.revise('goal', 'Рассмотреть тему.', **dict(options, mode='alice_test'))
        with self.assertRaises(MemoryConflict):
            self.memory.revise('principles', 'Выдуманная старая версия.', expected_version=0, restore_version=0, **options)
        self.assertEqual(len(self.memory.recall('', 'normal')['items']), 2)

    def test_privacy_persists_and_forget_removes_dependents_without_resurrection(self):
        receipt = self.turn()
        self.memory.revise('goal', 'Обсудить маркер.', reason='Из реального эпизода.', source='operator',
                           mode='normal', evidence_ids=[receipt['evidence_id']])
        self.memory.set_enabled(False)
        second = Experience(self.root)
        try:
            self.assertEqual(second.recall('', 'normal'), dict(enabled=False, context='', items=[]))
            self.assertFalse(second.record_turn(turn_id='new', session='s', source='worker', mode='normal',
                                               user_text='Привет', reply_text='Привет', completed=True)['recorded'])
            self.assertEqual(second.forget(receipt['evidence_id'], 'normal'), 2)
            second.set_enabled(True)
        finally:
            second.close()
        self.assertEqual(self.memory.recall('', 'normal')['items'], [])
        with self.assertRaises(MemoryConflict): self.turn()

    def test_bounded_context_recent_projections_and_private_files(self):
        for number in range(20):
            self.turn(number, user_text='Длинная реплика ' * 100, reply_text='Короткий ответ ' * 100)
        recalled = self.memory.recall('', 'normal')
        self.assertLessEqual(len(recalled['items']), 8)
        self.assertLessEqual(len(recalled['context']), 2500)
        self.assertEqual(recalled['items'][0]['at'], '2026-10-18T10:00:19Z')
        self.assertLessEqual(len(recalled['items'][0]['content']['user']), 64)
        root = self.root / 'experience'
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        for file in root.iterdir(): self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError): self.memory.recall('x' * 1025, 'normal')

    def test_failure_before_item_commit_never_exposes_partial_episode(self):
        store = self.memory.stores['normal']
        with patch.object(store, 'commit', side_effect=MemoryConflict('capacity')):
            with self.assertRaises(MemoryConflict): self.turn()
        self.assertEqual(self.memory.recall('', 'normal')['items'], [])
        # An orphan is only a digest, not a transcript; the same completion can retry.
        self.assertTrue(self.turn()['recorded'])

    def test_two_instances_race_with_expected_parent_without_lost_update(self):
        evidence = self.turn()['evidence_id']
        second = Experience(self.root)
        options = dict(reason='Указание пользователя.', source='operator', mode='normal', evidence_ids=[evidence])
        try:
            self.memory.revise('goal', 'Обсудить первую тему.', **options)
            with self.assertRaises(MemoryConflict): second.revise('goal', 'Обсудить вторую тему.', **options)
            second.revise('goal', 'Обсудить вторую тему.', expected_version=0, **options)
        finally:
            second.close()
        goal = next(item for item in self.memory.recall('', 'normal')['items'] if item['id'].endswith(':goal'))
        self.assertEqual(goal['version'], 1)

    def test_privacy_OFF_between_provenance_and_commit_blocks_real_transaction(self):
        store = self.memory.stores['normal']
        second = Experience(self.root)
        original = store.commit
        def race(item, expected):
            second.set_enabled(False)
            return original(item, expected)
        try:
            with patch.object(store, 'commit', side_effect=race):
                with self.assertRaises(sqlite3.IntegrityError): self.turn()
            self.assertEqual(store.count('versions'), 0)
            self.assertEqual(self.memory.recall('', 'normal')['context'], '')
        finally:
            second.close()


if __name__ == '__main__':
    unittest.main()
