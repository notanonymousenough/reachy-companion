"""Finite source/authority/phase checks, no microphone/model/device access."""
import ast
import copy
import importlib.util
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock,patch
from reachy_companion.finite_alice_trial import CUE,CapturedPCM,ResponseGate,validate
from test_bound_audio_only import BoundAudioOnlyTests
from test_agent_live_latency_patch import load

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('finite_alice_builder',ROOT/'deploy/autonomous/prepare_finite_alice_trial.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.binding=dict(agent_boot_id='boot',microphone_epoch=12,policy_epoch=8,owner_id='owner',
            expires_at_monotonic=140,audio_only=True)
        self.trial=dict(kind='arithmetic_four',nonce='a'*32)
        self.value=dict(agent_boot_id='boot',microphone_epoch=12,microphone_owner_id='owner',
            motion_policy_owner_id='owner',microphone_enabled=True,listening=True,capture_active=False,
            phase='processing',microphone_state_error=None,
            motion_policy=dict(epoch=8,motor_enabled=False,quiet=False,privacy_all=False))
        self.receipt=dict(started=101,received=102,generation=1)
        self.gate=ResponseGate(self.trial,self.binding,100)

    def accept(self,text='четыре',now=103,receipt=None,generation=1):
        return self.gate.accept(text,self.value,now,self.receipt if receipt is None else receipt,generation)

    def test_exact_fresh_answer_consumed_once_no_transcript(self):
        self.assertTrue(self.accept());self.assertFalse(self.accept())
        self.assertEqual(self.gate.receipt()['speaker_identity'],'unknown')
        self.assertNotIn('четыре',str(self.gate.__dict__))

    def test_owncue_other_speech_variant_and_empty_never_admit(self):
        for text in (CUE,'два плюс два','два плюс два равно четыре','шесть','',None):
            self.assertFalse(self.accept(text))
        self.assertFalse(self.gate.consumed)
        self.assertTrue(self.accept('4'))

    def test_late_cached_prearmed_or_changed_source_never_admit(self):
        for receipt,now,generation in ((dict(self.receipt,started=99),103,1),
                (self.receipt,105,1),(self.receipt,103,2),({},103,1),
                (dict(self.receipt,generation=True),103,1),(self.receipt,121,1)):
            self.assertFalse(self.accept(now=now,receipt=receipt,generation=generation))

    def test_policy_owner_epoch_withdrawal_unknown_state_never_admit(self):
        original=copy.deepcopy(self.value)
        changes=[lambda v:v.update(agent_boot_id='new'),lambda v:v.update(microphone_epoch=13),
            lambda v:v.update(microphone_owner_id='other'),lambda v:v.update(motion_policy_owner_id='other'),
            lambda v:v.update(microphone_enabled=False),lambda v:v.update(listening=False),
            lambda v:v.update(capture_active=True),lambda v:v.update(microphone_state_error='unknown'),
            lambda v:v['motion_policy'].update(epoch=9),lambda v:v['motion_policy'].update(motor_enabled=True),
            lambda v:v['motion_policy'].update(quiet=True),lambda v:v['motion_policy'].update(privacy_all=True)]
        for change in changes:
            self.value=copy.deepcopy(original);change(self.value);self.assertFalse(self.accept())

    def test_descriptor_rejects_wrongcue_nonce_kind_and_mode(self):
        for trial,binding,text in ((self.trial,self.binding,'Алиса, три плюс три?'),
                (dict(self.trial,nonce='old'),self.binding,CUE),(dict(self.trial,kind='other'),self.binding,CUE),
                (self.trial,dict(self.binding,audio_only=False),CUE)):
            with self.assertRaises(ValueError):validate(trial,binding,text)


class AgentTrialTests(BoundAudioOnlyTests):
    @classmethod
    def setUpClass(cls):
        before,after,_=builder.candidate();cls.old=before.decode();cls.new=after.decode();cls.module=load(cls.new)

    # Combined proposal changes only these established paths and one helper.
    def test_only_manual_method_changes(self):
        def outside(source):
            tree=ast.parse(source);agent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Agent')
            agent.body=[n for n in agent.body if getattr(n,'name',None) not in
                ('manual','capture','status','run','voice','_alice_input_allowed')]
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(outside(self.old),outside(self.new))

    def test_overlay_only_voice_manual_changed_legacy_manual_path_identical(self):
        # Parent's legacy structural assertion predates this combined carrier.
        self.a.manual('/say',dict(text='FINAL'))
        self.a.operator_status.assert_not_called()
        self.assertEqual(self.a.voice.call_args.kwargs,dict(allow_barge_in=False))

    def test_trial_arms_only_after_owned_non_cancelled_cue(self):
        self.value['motion_policy']['motor_enabled']=False
        payload=dict(text=CUE,operator_binding=dict(self.binding,audio_only=True),
            alice_trial=dict(kind='arithmetic_four',nonce='a'*32))
        def completed(*args,**kwargs):
            self.assertIsNone(getattr(self.a,'_finite_alice_trial',None))
            self.value['phase']='speaking'  # Real voice finally reaps before manual resets phase.
            return dict(ok=True)
        self.a.voice.side_effect=completed
        with patch.object(self.module.time,'monotonic',return_value=100):self.a.manual('/say',payload)
        self.assertIsNotNone(self.a._finite_alice_trial)
        with self.assertRaises(RuntimeError):self.a.manual('/say',payload)

    def test_cancelled_cue_never_arms_gate(self):
        self.value['motion_policy']['motor_enabled']=False
        self.a.voice.return_value=dict(cancelled=True)
        with patch.object(self.module.time,'monotonic',return_value=100),self.assertRaises(RuntimeError):
            self.a.manual('/say',dict(text=CUE,operator_binding=dict(self.binding,audio_only=True),
                alice_trial=dict(kind='arithmetic_four',nonce='a'*32)))
        self.assertIsNone(getattr(self.a,'_finite_alice_trial',None))

    def test_capture_receipt_tied_to_exact_normal_buffer_and_stop_has_priority(self):
        self.a._finite_alice_trial=Mock();self.a._finite_alice_trial.accept.return_value=False
        self.a._alice_capture_generation=7
        plain=b'pcm';receipt=dict(started=100,received=101,generation=7)
        pcm=CapturedPCM(plain,receipt)
        with patch.object(self.module.time,'monotonic',return_value=102):
            self.assertFalse(self.a._alice_input_allowed('четыре','answer',pcm))
            self.assertEqual(self.a._finite_alice_trial.accept.call_args.args[-2:],(receipt,7))
            self.assertFalse(self.a._alice_input_allowed('четыре','answer',plain))
            self.assertIsNone(self.a._finite_alice_trial.accept.call_args.args[-2])
            self.a._finite_alice_trial.accept.reset_mock()
            self.assertTrue(self.a._alice_input_allowed('стоп','stop',plain))
            self.a._finite_alice_trial.accept.assert_not_called()

    def test_both_stt_branches_gate_before_model_and_address_reply(self):
        tree=ast.parse(self.new);run=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='run')
        gates=[n for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='_alice_input_allowed']
        self.assertEqual(len(gates),2)
        texts=[n for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
            and n.func.attr=='voice' and n.args and isinstance(n.args[0],ast.Constant) and n.args[0].value=='/text']
        self.assertEqual(len(texts),2)
        for call in texts:
            self.assertTrue(any(g.lineno<call.lineno for g in gates))
            self.assertIn('speech_address_prefix',ast.unparse(call))
            keywords={k.arg:ast.unparse(k.value) for k in call.keywords}
            self.assertIn("binding['policy_epoch']",keywords['expected_policy_epoch'])
            self.assertIn('_finite_alice_trial.deadline',keywords['valid_until'])

    def test_new_normal_capture_attaches_original_receipt_no_pending_alias(self):
        self.a._finite_alice_trial=Mock()
        self.a._finite_capture=Mock(return_value=b'new-pcm')
        with patch.object(self.module.time,'monotonic',side_effect=[100,101]):pcm=self.a.capture()
        self.assertIsInstance(pcm,CapturedPCM)
        self.assertEqual(pcm.receipt,dict(started=100,received=101,generation=1))
        plain=self.a.capture(during_reply=True)
        self.assertNotIsInstance(plain,CapturedPCM)
        self.assertEqual(self.a._alice_capture_generation,1)

    def test_pending_or_still_playing_audio_cannot_arm_trial(self):
        self.value['motion_policy']['motor_enabled']=False
        payload=dict(text=CUE,operator_binding=dict(self.binding,audio_only=True),
            alice_trial=dict(kind='arithmetic_four',nonce='a'*32))
        for key in ('pending_pcm','resume_audio','playback_process'):
            setattr(self.a,key,object())
            with patch.object(self.module.time,'monotonic',return_value=100),self.assertRaises(RuntimeError):
                self.a.manual('/say',payload)
            setattr(self.a,key,None)
        self.a.voice.assert_not_called()

    def test_trial_prefix_survives_real_voice_config_assignment_only_after_admission(self):
        import types
        tree=ast.parse(self.new);voice=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='voice')
        start=next(i for i,n in enumerate(voice.body) if isinstance(n,ast.Assign) and any(getattr(t,'id',None)=='prefix' for t in n.targets))
        nodes=voice.body[start:start+4]
        self.assertIn('speech_address_prefix',ast.unparse(nodes[-1]))
        for gate,expected in ((None,''),(types.SimpleNamespace(consumed=False),''),(types.SimpleNamespace(consumed=True),'Алиса, ')):
            holder=types.SimpleNamespace(config={'conversation':{'speech_address_prefix':''}},_finite_alice_trial=gate)
            namespace=dict(self=holder,payload={'speech_address_prefix':'untrusted'})
            exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual-voice-prefix','exec'),namespace)
            self.assertEqual(namespace['payload']['speech_address_prefix'],expected)

    def test_trial_suppresses_startup_greeting_and_client_never_initially_listens(self):
        import types
        tree=ast.parse(self.new);run=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='run')
        gate=next(n for n in ast.walk(run) if isinstance(n,ast.If) and any(
            isinstance(x,ast.Assign) and any(getattr(t,'id',None)=='greeted' for t in x.targets) for x in n.body))
        for trial,expected in ((None,False),(object(),True)):
            namespace=dict(self=types.SimpleNamespace(_finite_alice_trial=trial),greeted=False)
            exec(compile(ast.Module(body=[gate],type_ignores=[]),'trial-greeting','exec'),namespace)
            self.assertEqual(namespace['greeted'],expected)
        client=builder.client_candidate().decode()
        tree=ast.parse(client)
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='dict'
            and any(k.arg=='enabled' and isinstance(k.value,ast.Constant) and k.value.value is True for k in n.keywords)]
        self.assertEqual(len(calls),1)
        self.assertTrue(any(k.arg=='listen' and isinstance(k.value,ast.Constant) and k.value.value is False for k in calls[0].keywords))

    def test_policy_or_mic_takeover_after_admission_cannot_open_model_or_emit_motion(self):
        self.a.http=Mock();self.a.expressions=Mock();self.a.motion_policy=Mock()
        self.a.motion_policy.snapshot.return_value=dict(epoch=9,motor_enabled=True,quiet=False,privacy_all=False)
        with patch.object(self.module.time,'monotonic',return_value=103):
            result=self.module.Agent.voice(self.a,'/text',dict(text='четыре'),expected_epoch=12,
                expected_policy_epoch=8,valid_until=120)
        self.assertTrue(result['cancelled']);self.a.http.open.assert_not_called()
        self.a.expressions.set.assert_not_called()
        self.a.motion_policy.snapshot.return_value=dict(epoch=8,motor_enabled=False,quiet=False,privacy_all=False)
        self.a.microphone_epoch=13
        with patch.object(self.module.time,'monotonic',return_value=103):
            result=self.module.Agent.voice(self.a,'/text',dict(text='четыре'),expected_epoch=12,
                expected_policy_epoch=8,valid_until=120)
        self.assertTrue(result['cancelled']);self.a.http.open.assert_not_called()

    def test_policy_takeover_after_http_open_discards_stream_without_aplay_or_pcm(self):
        import functools
        from test_agent_stream_timing import AgentStreamTimingTests
        fixture=AgentStreamTimingTests()
        a=fixture.agent(self.module)
        a._finite_alice_trial=Mock(consumed=True)
        a.motion_policy.snapshot.side_effect=[dict(epoch=6,motor_enabled=False,quiet=False,privacy_all=False),
            *[dict(epoch=7,motor_enabled=True,quiet=False,privacy_all=False)]*50]
        a.voice=functools.partial(self.module.Agent.voice,a,expected_epoch=17,expected_policy_epoch=6,valid_until=120)
        fixture.agent=lambda module:a
        _,result,order,writes,_=fixture.stream(module=self.module)
        self.assertTrue(result['cancelled']);self.assertIn('open',order)
        self.assertNotIn('popen',order);self.assertEqual(writes,[])


if __name__=='__main__':unittest.main()
