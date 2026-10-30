import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from reachy_companion.conversation_context import mode_payload, mode_prompt, mode_session
from test_alice_speech_address import AliceSpeechAddressTests
from test_stream_cleanup_overlay import load

ROOT = Path(__file__).resolve().parents[1]


class ConversationContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('mode_worker_builder',ROOT/'tests/fixtures/legacy/r52/build_pc.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.worker = load(module.candidate())

    def setUp(self):
        fixture = AliceSpeechAddressTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.p = fixture.pipeline
        self.p.__class__ = self.worker.Pipeline
        self.spoken = fixture.spoken
        self.p.config.data['llm']['system_prompt'] = 'Ты Ричи, робот.\nВ текущей автономной беседе с Алисой только вопросы.'
        self.p.config.data['conversation']['alice_short_replies'] = False

    def test_modes_use_distinct_history_and_context_in_real_stream_pipeline(self):
        captured=[]
        def answer(config,messages,*args,**kwargs):
            captured.append(copy.deepcopy(messages))
            return 'Понял.'
        with patch('reachy_companion.brains.answer',side_effect=answer):
            for mode in ('alice_test','normal','alice_test'):
                list(self.p.stream(dict(text='Вопрос',session='same',conversation_mode=mode),'/text'))
        self.assertIn('Тест с Алисой',captured[0][0]['content'])
        self.assertNotIn('Алис',captured[1][0]['content'])
        self.assertEqual(len(captured[1]),2)
        self.assertEqual(len(captured[2]),4)
        self.assertEqual(self.spoken,['Алиса, Понял.','Понял.','Алиса, Понял.'])
        self.assertEqual(len(self.p.sessions),2)

    def test_unary_and_legacy_clients_preserve_contract(self):
        with patch('reachy_companion.brains.answer',return_value='Понял.') as answer:
            self.p.turn(dict(text='Вопрос',session='legacy'),'/text')
            self.assertIn('текущей автономной беседе',answer.call_args.args[1][0]['content'])
            self.assertIn('legacy',self.p.sessions)
            self.p.turn(dict(text='Вопрос',session='s',conversation_mode='normal'),'/text')
            self.assertNotIn('Алис',answer.call_args.args[1][0]['content'])
        self.assertEqual(self.spoken,['Алиса, Понял.','Понял.'])

    def test_actual_installed_prompt_is_losslessly_repaired_and_test_suffix_removed(self):
        source=json.loads((ROOT/'tests/fixtures/legacy/r52/baseline/pc-conversation-contract.json').read_text())['system_prompt']
        normal=mode_prompt(source,'normal')
        self.assertTrue(normal.startswith('Ты Ричи,'))
        self.assertNotIn('автономной беседе с Алисой',normal)
        self.assertNotIn('РўС',normal)
        self.assertIn('собственным мнением',normal)
        self.assertEqual(mode_prompt(source,None),source)

    def test_invalid_mode_or_contradictory_prefix_never_synthesizes(self):
        for value in (False,1,'alice',{},[]):
            with self.assertRaises(ValueError):
                list(self.p.stream(dict(text='Вопрос',conversation_mode=value),'/text'))
        with self.assertRaises(ValueError):
            self.p.turn(dict(text='Вопрос',conversation_mode='normal',speech_address_prefix='Алиса, '),'/text')
        self.assertEqual(self.spoken,[])

    def test_session_namespace_bounded_and_payload_unchanged(self):
        original=dict(conversation_mode='normal',text='x')
        self.assertEqual(mode_payload(original)['speech_address_prefix'],'')
        self.assertNotIn('speech_address_prefix',original)
        self.assertLess(len(mode_session('x'*10000,'normal')),64)
        self.assertNotEqual(mode_session('s','normal'),mode_session('s','alice_test'))
        self.assertEqual(mode_prompt('Normal base','normal'),'Normal base')

    def test_acknowledgement_path_uses_same_scoped_session_and_context(self):
        self.p.config.data['conversation']['interaction']['acknowledgements']=dict(
            enabled=True,delay_seconds=2,phrases=dict(other='Сейчас отвечу.'))
        with patch('reachy_companion.brains.answer',return_value='Понял.') as answer:
            list(self.p.stream(dict(text='Вопрос',session='ack',conversation_mode='alice_test'),'/text'))
        self.assertIn('Тест с Алисой',answer.call_args.args[1][0]['content'])
        self.assertIn(mode_session('ack','alice_test'),self.p.sessions)
        self.assertEqual(self.spoken,['Алиса, Понял.'])


if __name__=='__main__':unittest.main()
