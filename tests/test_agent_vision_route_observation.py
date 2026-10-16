"""Exact Agent9a status overlay; finite local turns, no hardware/model calls."""
import ast
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from test_spoken_vision import candidate as base_candidate, AgentSpokenOverlayTests, operator
from test_agent_live_latency_patch import load
from reachy_companion import spoken_vision as spoken

ROOT=Path(__file__).resolve().parents[1]
AFTER='289469a5de57f01295e6c8ddde3e78ba2804fe2f5e6c603a4789e3d70e6ebeb9'


def candidate():
    old=base_candidate()[1];lines=old.splitlines(True);hunks=[]
    for line in (ROOT/'deploy/patches/reachy-agent-9a-vision-route-observation.patch').read_text().splitlines(True):
        if line.startswith('@@ '):
            match=re.match(r'@@ -(\d+)(?:,(\d+))? ',line)
            start=int(match[1]);count=int(match[2] or 1)
            hunks.append((start if count==0 else start-1,[],[]))
        elif hunks and line[:1] in (' ','-','+'):
            _,before,after=hunks[-1]
            if line[0] in (' ','-'):before.append(line[1:])
            if line[0] in (' ','+'):after.append(line[1:])
    for index,before,after in reversed(hunks):
        if lines[index:index+len(before)]!=before:raise ValueError('Exact hunk position required')
        lines[index:index+len(before)]=after
    new=''.join(lines)
    if hashlib.sha256(new.encode()).hexdigest()!=AFTER:raise ValueError('Wrong overlay output')
    return old,new


class RouteObservationTests(AgentSpokenOverlayTests):
    @classmethod
    def setUpClass(cls):cls.old,cls.new=candidate();cls.module=load(cls.new)

    def test_only_status_run_and_observation_methods_change(self):
        def outside(source):
            tree=ast.parse(source)
            agent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Agent')
            agent.body=[n for n in agent.body if getattr(n,'name',None) not in
                ('status','run','vision_route_update','vision_route_status','vision_route_failure')]
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(outside(self.old),outside(self.new))

    # The inherited test correctly describes the older overlay, not this one.
    def test_only_run_changed_preserving_installed_say_stop_voice_and_capability(self):
        self.test_only_status_run_and_observation_methods_change()

    def test_success_mismatch_action_rejection_and_interruption_are_distinct(self):
        for text,action,pending,result,exact,attempt in (
            ('Что перед тобой?','answer',False,'returned',True,True),
            ('PRIVATE ordinary transcript','answer',False,'nonmatching_stt',False,False),
            ('Что перед тобой?','pause',False,'action_rejected',True,False),
            ('Что перед тобой?','untrusted PRIVATE action',False,'action_rejected',True,False),
            ('Что перед тобой?','answer',True,'existing_interruption_path',False,False)):
            a,called=self.run_turn(text,action,pending)
            bound,value=a._vision_route
            self.assertEqual(bound,spoken.binding(operator()))
            self.assertEqual(value['result'],result);self.assertEqual(value['normalized_exact_visual'],exact)
            self.assertEqual(value['route_attempted'],attempt)
            self.assertEqual(called.call_count,int(attempt))
            self.assertNotIn('PRIVATE',json.dumps(value))
            self.assertEqual(value['action_allowlisted'],not pending and action in ('answer','stop','pause','reset'))

    def test_echo_is_observed_without_relaxing_original_match_gate(self):
        original=spoken.matches
        def side_effect(text,*args):
            if not args:return original(text)
            return original(text,'Ты спросил: что перед тобой')
        with patch.object(spoken,'matches',side_effect=side_effect):
            a,called=self.run_turn('Что перед тобой?')
        called.assert_not_called()
        self.assertTrue(a._vision_route[1]['own_echo_match'])
        self.assertEqual(a._vision_route[1]['result'],'echo_rejected')

    def test_dispatch_failure_survives_before_legacy_last_transcript_assignment(self):
        # Reuse real run fixture, replacing only dispatch's finite behavior.
        original_run_turn=self.run_turn
        def fail(*args):
            a=args[0];a.stopping.set()
            raise RuntimeError('Spoken snapshot child failed phase=capture error_class=ValueError')
        real_patch=patch.object
        # run_turn installs its own dispatch mock; replace its side effect via the context factory.
        def patched(target,name,*args,**kwargs):
            if target is spoken and name=='dispatch':kwargs['side_effect']=fail
            return real_patch(target,name,*args,**kwargs)
        with patch('test_spoken_vision.patch.object',side_effect=patched), patch.object(self.module.LOG,'exception'):
            a,_=original_run_turn('Что перед тобой?')
        self.assertIsNone(a.last_transcript);self.assertEqual(a.turns,0)
        self.assertEqual(a._vision_route[1]['result'],'typed_child_failure')
        self.assertEqual(a._vision_route[1]['child_phase'],'capture')
        self.assertTrue(a._vision_route[1]['route_attempted'])

    def test_untyped_or_forged_failure_never_reflects_private_exception(self):
        a=self.module.Agent.__new__(self.module.Agent)
        for exc in (RuntimeError('PRIVATE image token transcript'),
                RuntimeError('Spoken snapshot child failed phase=capture error_class=ValueError PRIVATE'),
                ValueError('Spoken snapshot child failed phase=capture error_class=ValueError')):
            a._vision_route=(spoken.binding(operator()),dict(child_phase=None,child_error_class=None))
            a.vision_route_failure(exc)
            self.assertEqual(a._vision_route[1]['result'],'untyped_failure')
            self.assertNotIn('PRIVATE',json.dumps(a._vision_route[1]))
            self.assertIsNone(a._vision_route[1]['child_phase'])

    def test_status_projection_is_generation_bound_copied_and_empty_before_first_turn(self):
        a=self.module.Agent.__new__(self.module.Agent)
        a.agent_boot_id='fixture-boot';a.microphone_epoch=17
        self.assertIsNone(a.vision_route_status(dict(epoch=6)))
        a._vision_route=(spoken.binding(operator()),dict(route_attempted=True))
        result=a.vision_route_status(dict(epoch=6));result['route_attempted']=False
        self.assertTrue(a.vision_route_status(dict(epoch=6))['route_attempted'])
        self.assertIsNone(a.vision_route_status(dict(epoch=7)))
        a.microphone_epoch=18;self.assertIsNone(a.vision_route_status(dict(epoch=6)))
        a.microphone_epoch=17;a.agent_boot_id='other'
        self.assertIsNone(a.vision_route_status(dict(epoch=6)))

    def test_existing_status_exposes_only_current_copied_observation(self):
        a,_=self.run_turn('Что перед тобой?')
        a.agent_boot_id='fixture-boot';a.microphone_lock=__import__('threading').Lock()
        a.motion_actor_status=Mock(return_value={'ready':False})
        a.motion_policy=Mock();a.motion_policy.snapshot.return_value=dict(epoch=6)
        a.phase='stopped';a.threshold=1;a.last_error=None;a.interruptions=0
        a.barge_in_error=None;a.resume_blocked_reason=None;a.volume=SimpleNamespace(percent=100)
        a.audio={};a.capture_active=False;a.sounds=SimpleNamespace(music=False,last_error=None)
        a.microphone.error=None
        status=a.status()
        self.assertEqual(status['vision_route']['result'],'returned')
        self.assertEqual(status['volume_percent'],100)
        self.assertEqual(status['motion_policy'],dict(epoch=6))
        a.motion_policy.snapshot.return_value=dict(epoch=7)
        self.assertIsNone(a.status()['vision_route'])

    def test_new_capture_replaces_previous_route_before_stt(self):
        a,_=self.run_turn('Что перед тобой?')
        a.stopping.clear();a.current_reply_text='';a.last_transcript=None
        def capture():
            self.assertEqual(a._vision_route[1]['result'],'returned')
            self.assertTrue(a._vision_route[1]['route_attempted'])
            return b'fresh second phrase'
        a.capture.side_effect=capture
        previous=a.request.side_effect
        def request(base,path,*args,**kwargs):
            if path=='/transcribe':
                self.assertFalse(a._vision_route[1]['route_attempted'])
                self.assertEqual(a._vision_route[1]['stage'],'stt')
                a.stopping.set()
                return dict(ok=True,transcript='',decision=dict(action='answer'))
            return previous(base,path,*args,**kwargs)
        a.request.side_effect=request
        a.run()
        self.assertEqual(a._vision_route[1]['result'],'empty_stt')
        self.assertFalse(a._vision_route[1]['route_attempted'])


if __name__=='__main__':unittest.main()
