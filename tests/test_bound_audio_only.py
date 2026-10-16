"""Opt-in bound speech authority, exact-source fixtures; no devices/audio."""
import ast
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from test_agent_bound_speech_patch import BoundSpeechTests
from test_agent_live_latency_patch import load

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bound_audio_builder',ROOT/'deploy/autonomous/prepare_bound_audio_only.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class BoundAudioOnlyTests(BoundSpeechTests):
    @classmethod
    def setUpClass(cls):
        before,after=builder.candidate();cls.old=before.decode();cls.new=after.decode();cls.module=load(cls.new)

    def test_only_manual_method_changes(self):
        def outside(source):
            tree=ast.parse(source)
            agent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Agent')
            agent.body=[n for n in agent.body if getattr(n,'name',None)!='manual']
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(outside(self.old),outside(self.new))

    def test_explicit_audio_only_false_policy_uses_same_bound_voice_and_no_motion(self):
        self.value['motion_policy']['motor_enabled']=False
        binding=dict(self.binding,audio_only=True)
        with patch.object(self.module.time,'monotonic',return_value=100):
            self.a.manual('/say',dict(text='Алиса, сколько будет два плюс два?',operator_binding=binding))
        self.assertEqual(self.a.voice.call_args.kwargs,dict(allow_barge_in=False,expected_epoch=12,
            expected_policy_epoch=8,valid_until=120))
        self.assertFalse(self.a.listening.is_set());self.assertFalse(self.a.audio_lock.locked())

    def test_motor_modes_are_literal_and_never_implicitly_widened(self):
        for flag,motor in ((None,False),(True,True),(True,None),(True,0),(True,1),(None,1)):
            self.value['motion_policy']['motor_enabled']=motor
            binding=dict(self.binding)
            if flag is not None:binding['audio_only']=flag
            with self.subTest(flag=flag,motor=motor),patch.object(self.module.time,'monotonic',return_value=100),self.assertRaises(RuntimeError):
                self.a.manual('/say',dict(text='Алиса, вопрос.',operator_binding=binding))
        for flag in (False,None,1,'true',[]):
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                self.a.manual('/say',dict(text='Алиса, вопрос.',operator_binding=dict(self.binding,audio_only=flag)))
        self.a.voice.assert_not_called()

    def test_false_policy_stale_withdrawal_foreign_capture_privacy_still_rejected(self):
        original=copy.deepcopy(self.value);original['motion_policy']['motor_enabled']=False
        mutations=[lambda v:v.update(microphone_enabled=False),lambda v:v.update(microphone_epoch=13),
            lambda v:v.update(agent_boot_id='new'),lambda v:v.update(microphone_owner_id='other'),
            lambda v:v.update(motion_policy_owner_id='other'),lambda v:v.update(capture_active=True),
            lambda v:v.update(listening=True),lambda v:v.update(phase='processing'),
            lambda v:v['motion_policy'].update(epoch=9),lambda v:v['motion_policy'].update(quiet=True),
            lambda v:v['motion_policy'].update(privacy_all=True)]
        for mutate in mutations:
            self.value=copy.deepcopy(original);mutate(self.value)
            with patch.object(self.module.time,'monotonic',return_value=100),self.assertRaises(RuntimeError):
                self.a.manual('/say',dict(text='Алиса, вопрос.',operator_binding=dict(self.binding,audio_only=True)))
        self.a.voice.assert_not_called()


if __name__=='__main__':unittest.main()
