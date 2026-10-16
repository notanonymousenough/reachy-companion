"""Exact installed Agent /say binding overlay; no actual playback or control."""
import ast
import copy
import hashlib
from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import Mock,patch
from test_agent_live_latency_patch import load

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'deploy/patches/reachy-agent-0a7-bound-vision-speech.patch'


def source():
    result=subprocess.run(['git','show','2865db30e92fcb069c241c34bae4419ad65ed594:src/reachy_companion/agent.py'],cwd=ROOT,capture_output=True)
    if result.returncode:raise unittest.SkipTest('Exact legacy source unavailable; no fetch')
    old=result.stdout.decode()
    if hashlib.sha256(result.stdout).hexdigest()!='0a7c0a3d7cbd542eabf9412291fda052c559db8c6bac123db31676b0137bd908':
        raise ValueError('Wrong Agent preimage')
    new=old;hunks=[]
    for line in PATCH.read_text().splitlines(True):
        if line.startswith('@@ '):hunks.append(([],[]))
        elif hunks and line[:1] in (' ','-','+'):
            before,after=hunks[-1]
            if line[0] in (' ','-'):before.append(line[1:])
            if line[0] in (' ','+'):after.append(line[1:])
    for before,after in hunks:
        before=''.join(before)
        if new.count(before)!=1:raise ValueError('No fuzzy application')
        new=new.replace(before,''.join(after),1)
    if hashlib.sha256(new.encode()).hexdigest()!='53a43647c4744dde3c7b112d12212477943ce22f9f33b90ffbeeb916d28f23c3':
        raise ValueError('Wrong overlay output')
    return old,new


class BoundSpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old,cls.new=source();cls.module=load(cls.new)

    def setUp(self):
        self.a=self.module.Agent.__new__(self.module.Agent)
        self.a.config=dict(timeouts=dict(manual_audio_lock=.1),conversation=dict(session='fixture'))
        self.a.listening=threading.Event();self.a.audio_lock=threading.Lock();self.a.stopping=threading.Event()
        self.a.microphone=Mock(enabled=True);self.a.microphone_epoch=12
        self.value=dict(agent_boot_id='boot',microphone_epoch=12,microphone_owner_id='owner',motion_policy_owner_id='owner',
            microphone_enabled=True,capture_active=False,listening=False,phase='paused',
            motion_policy=dict(epoch=8,motor_enabled=True,quiet=False,privacy_all=False))
        self.a.operator_status=Mock(side_effect=lambda:copy.deepcopy(self.value))
        self.a.voice=Mock(return_value=dict(ok=True,reply='FINAL',audio_base64='never-return'))
        self.binding=dict(agent_boot_id='boot',microphone_epoch=12,policy_epoch=8,owner_id='owner',expires_at_monotonic=120)

    def test_overlay_only_voice_manual_changed_legacy_manual_path_identical(self):
        def outside(text):
            tree=ast.parse(text);agent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Agent')
            agent.body=[n for n in agent.body if getattr(n,'name',None) not in ('voice','manual')]
            for node in ast.walk(tree):
                if isinstance(node,ast.ClassDef) and node.name=='Handler':
                    node.body=[method for method in node.body if getattr(method,'name',None)!='do_GET']
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(outside(self.old),outside(self.new))
        result=self.a.manual('/say',dict(text='FINAL'))
        self.assertNotIn('audio_base64',result);self.a.operator_status.assert_not_called()
        self.assertEqual(self.a.voice.call_args.kwargs,dict(allow_barge_in=False))

    def test_readonly_capability_requires_auth_and_identifies_current_boot(self):
        tree=ast.parse(self.new)
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and n.name=='Handler')
        namespace=dict(self.module.__dict__,agent=Mock(agent_boot_id='boot'))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'capability-handler','exec'),namespace)
        handler=namespace['Handler'].__new__(namespace['Handler'])
        handler.path='/vision-capabilities';handler.reply=Mock();handler.auth=Mock(return_value=False)
        handler.do_GET();handler.reply.assert_not_called()
        handler.auth.return_value=True;handler.do_GET()
        handler.reply.assert_called_once_with(200,dict(bound_snapshot_say=1,agent_boot_id='boot'))

    def test_bound_say_uses_existing_voice_with_exact_epochs_deadline_and_no_capture(self):
        with patch.object(self.module.time,'monotonic',return_value=100):
            self.a.manual('/say',dict(text='FINAL',operator_binding=self.binding))
        self.assertEqual(self.a.voice.call_args.kwargs,dict(allow_barge_in=False,expected_epoch=12,expected_policy_epoch=8,valid_until=120))
        self.assertFalse(self.a.listening.is_set());self.assertFalse(self.a.audio_lock.locked())

    def test_new_boot_epoch_owner_capture_quiet_or_expiry_denies_before_voice(self):
        original=copy.deepcopy(self.value)
        mutations=[lambda v:v.update(agent_boot_id='new'),lambda v:v.update(microphone_epoch=13),
            lambda v:v['motion_policy'].update(epoch=9),lambda v:v.update(microphone_owner_id='foreign'),
            lambda v:v.update(motion_policy_owner_id='foreign'),lambda v:v.update(capture_active=True),
            lambda v:v.update(listening=True),lambda v:v['motion_policy'].update(quiet=True),
            lambda v:v['motion_policy'].update(privacy_all=True)]
        for mutate in mutations:
            self.value=copy.deepcopy(original);mutate(self.value)
            with patch.object(self.module.time,'monotonic',return_value=100),self.assertRaises(RuntimeError):
                self.a.manual('/say',dict(text='FINAL',operator_binding=self.binding))
        self.value=original
        with patch.object(self.module.time,'monotonic',return_value=121),self.assertRaises(RuntimeError):
            self.a.manual('/say',dict(text='FINAL',operator_binding=self.binding))
        self.a.voice.assert_not_called()

    def test_takeover_after_audio_lock_and_voice_entry_cannot_legitimize_stale_result(self):
        changed=copy.deepcopy(self.value);changed['microphone_epoch']=13
        self.a.operator_status.side_effect=[copy.deepcopy(self.value),changed]
        with patch.object(self.module.time,'monotonic',return_value=100),self.assertRaises(RuntimeError):
            self.a.manual('/say',dict(text='FINAL',operator_binding=self.binding))
        self.a.voice.assert_not_called();self.assertFalse(self.a.audio_lock.locked())
        a=self.a;a.http=Mock();a.resume_audio=None;a.resume_blocked_reason=None
        a.motion_policy=Mock();a.motion_policy.snapshot.return_value=dict(epoch=9,quiet=False,privacy_all=False)
        with patch.object(self.module.time,'monotonic',return_value=100):
            result=self.module.Agent.voice(a,'/say',dict(text='FINAL'),expected_epoch=12,expected_policy_epoch=8,valid_until=120)
        self.assertTrue(result['cancelled']);a.http.open.assert_not_called()

    def test_binding_fields_cannot_be_null_aliases_or_unbounded_and_ask_is_not_vision_say(self):
        for binding in (None,dict(self.binding,microphone_epoch=True),dict(self.binding,expires_at_monotonic=float('nan')),
                dict(self.binding,owner_id=''),dict(self.binding,extra=True)):
            with self.subTest(binding=binding),self.assertRaises(ValueError):
                self.a.manual('/say',dict(text='FINAL',operator_binding=binding))
        with self.assertRaises(ValueError):self.a.manual('/ask',dict(text='FINAL',operator_binding=self.binding))
        self.a.voice.assert_not_called()


if __name__=='__main__':unittest.main()
