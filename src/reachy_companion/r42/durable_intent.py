"""Explicit durable user intent, never a persisted boot/epoch/owner grant."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time

FIELDS={'version','generation','listening_requested','automatic_questions_requested'}

class DurableIntent:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.RLock();self.error=False
        self.value=dict(version=1,generation=0,listening_requested=False,automatic_questions_requested=False)
        self.recovery_state='off';self.recovery_used=False;self.recovery_token=None;self.recovery_sample=None;self.recovery_progress=0;self.recovery_source=None;self.recovery_grant_boot=None
        self.bootstrap_state='off';self.source_generation=None;self.grant_boot=None;self.sample=None
        try:
            raw=self.path.read_bytes()
            if len(raw)>1024:raise ValueError('Intent bound')
            def unique(pairs):
                out={}
                for key,value in pairs:
                    if key in out:raise ValueError('Duplicate intent field')
                    out[key]=value
                return out
            value=json.loads(raw,object_pairs_hook=unique)
            if (type(value) is not dict or set(value)!=FIELDS or type(value['version']) is not int or value['version']!=1
                or type(value['generation']) is not int or not 0<=value['generation']<2**63
                or any(type(value[k]) is not bool for k in ('listening_requested','automatic_questions_requested'))
                or value['automatic_questions_requested'] and not value['listening_requested']):raise ValueError('Intent schema')
            self.value=value
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError):self.error=True;self.bootstrap_state='error'

    def snapshot(self):
        with self.lock:return dict(self.value)

    def update(self,*,listening=None,automatic=None):
        with self.lock:
            after=dict(self.value)
            if listening is not None:after['listening_requested']=listening
            if automatic is not None:after['automatic_questions_requested']=automatic
            if any(type(after[k]) is not bool for k in ('listening_requested','automatic_questions_requested')):raise ValueError('Boolean intent required')
            if automatic is True and not after['listening_requested']:raise ValueError('Listening intent required')
            if not after['listening_requested']:after['automatic_questions_requested']=False
            if after==self.value and not self.error:return after
            if after['generation']>=2**63-1:raise ValueError('Intent generation exhausted')
            after['generation']+=1;temporary=None
            try:
                self.path.parent.mkdir(parents=True,exist_ok=True)
                fd,name=tempfile.mkstemp(prefix=self.path.name+'.',dir=self.path.parent);temporary=Path(name)
                with os.fdopen(fd,'w') as f:json.dump(after,f);f.flush();os.fsync(f.fileno())
                temporary.replace(self.path)
                directory=os.open(self.path.parent,os.O_RDONLY)
                try:os.fsync(directory)
                finally:os.close(directory)
                self.value=after;self.error=False
            except BaseException:
                self.error=True;self.value=dict(after,listening_requested=False,automatic_questions_requested=False)
                self.bootstrap_state='error';raise
            finally:
                if temporary is not None:temporary.unlink(missing_ok=True)
            if self.bootstrap_state in ('waiting','admitting'):self.bootstrap_state='withdrawn'
            return dict(after)

    def listening_allowed(self,agent):
        p=agent.motion_policy.snapshot();v=self.snapshot()
        return (not self.error and v['listening_requested'] and agent.microphone.enabled
            and agent.microphone.error is None and not p['quiet'] and not p['privacy_all']
            and p['epoch'] is not None and agent.microphone_owner_id is None and agent.motion_policy.owner_id is None)

    def begin(self,agent):
        v=self.snapshot()
        if self.listening_allowed(agent) and v['automatic_questions_requested']:
            p=agent.motion_policy.snapshot();self.expected=(agent.agent_boot_id,agent.microphone_epoch,p['epoch'])
            self.intent_generation=v['generation'];self.deadline=time.monotonic()+60;self.bootstrap_state='waiting'

    def pending(self):return self.bootstrap_state=='waiting'

    def status(self,agent=None):
        v=self.snapshot()
        active=(agent is None or (agent.initiative.schedule_enabled and agent.agent_boot_id==self.grant_boot))
        return dict(state=self.bootstrap_state,intent_generation=v['generation'],listening_requested=v['listening_requested'],automatic_questions_requested=v['automatic_questions_requested'],source_generation=self.source_generation,current_grant_boot=self.grant_boot if active else None,persistence_error=self.error,recovery=dict(state=self.recovery_state,budget_used=self.recovery_used,source_generation=self.recovery_source,current_grant_boot=self.recovery_grant_boot if (agent is not None and self.recovery_state=='admitted' and self.recovery_token is not None and agent.initiative.schedule_enabled and agent.initiative.schedule_generation==self.recovery_token['schedule_generation']+1) else None))

    def tick(self,agent):
        if not self.pending():return
        now=time.monotonic();v=self.snapshot();p=agent.motion_policy.snapshot()
        current=(agent.agent_boot_id,agent.microphone_epoch,p['epoch'])
        if (v['generation']!=self.intent_generation or not v['automatic_questions_requested']
            or not self.listening_allowed(agent) or current!=self.expected or agent.stopping.is_set()):
            self.bootstrap_state='withdrawn';return
        if now>=self.deadline:self.bootstrap_state='expired';return
        if not agent.listening.is_set():return  # A temporary manual pause is not opt-out.
        pump=getattr(agent,'_capture_pump',None)
        if pump is None:return
        with pump.condition:
            receipt=pump.counters['last_read_monotonic'];count=pump.counters['read_bytes']
            if (not pump.permitted() or pump.error is not None or receipt is None or not 0<=now-receipt<=.3
                or type(count) is not int or count<=0):return
            sample=(pump.generation,count)
            if self.sample is None or self.sample[0]!=sample[0]:self.sample=sample;return
            if sample[1]<=self.sample[1]:return
            if (agent.phase!='listening' or not agent.capture_active or agent.pending_pcm is not None
                or agent.resume_audio is not None or agent.playback_process is not None or agent.voice_response is not None):return
            self.source_generation=pump.generation
        self.bootstrap_state='admitting'
        try:
            # SAME admission function/CAS/typed fresh binding as explicit controls.
            result=agent.initiative.schedule_control(dict(enabled=True,expected_generation=agent.initiative.schedule_status()['generation'],operator_binding=dict(agent_boot_id=current[0],microphone_epoch=current[1],policy_epoch=current[2],owner_id=None,expires_at_monotonic=time.monotonic()+59)),startup_intent_generation=self.intent_generation)
            if result['enabled']:self.bootstrap_state='admitted';self.grant_boot=current[0]
            else:self.bootstrap_state='withdrawn'
        except Exception:self.bootstrap_state='withdrawn'

    def recovery_pending(self):return self.recovery_state=='waiting'

    def recovery_valid(self,a,token,*,admitting=False):
        v=self.snapshot();p=a.motion_policy.snapshot();i=a.initiative
        if admitting:
            source=token.get('source') if token is not None else None
            if (source is None or a._capture_pump is not source or source.generation!=token['source_generation']
                or not source.permitted() or source.error is not None
                or source.counters['last_read_monotonic'] is None or not 0<=time.monotonic()-source.counters['last_read_monotonic']<=.3):return False
        return (token is not None and self.recovery_token is token and self.recovery_used and not self.error
            and self.recovery_state==('admitting' if admitting else 'waiting') and time.monotonic()<token['expires']
            and v['generation']==token['intent_generation'] and v['listening_requested'] and v['automatic_questions_requested']
            and (a.agent_boot_id,a.microphone_epoch,p['epoch'])==token['binding'] and p==token['policy']
            and a.microphone.enabled and a.microphone.error is None and a.listening.is_set() and not a.stopping.is_set()
            and a.microphone_owner_id is None and a.motion_policy.owner_id is None and not p['quiet'] and not p['privacy_all']
            and i.schedule_generation==token['schedule_generation'] and not i.schedule_enabled
            and i.schedule_reason=='audio_loop_error' and i.schedule_child is None)

    def audio_error(self,a,reason='audio_loop_error'):
        # Called only by the real audio-loop exception handler, never status scan.
        if reason!='audio_loop_error':raise ValueError('Exact recovery reason required')
        i=a.initiative
        with a.microphone_lock,a.motion_policy.lock,i.lock,self.lock:
            v=self.snapshot();p=a.motion_policy.snapshot();generation=i.schedule_generation
            eligible=(not self.recovery_used and i.schedule_enabled and i.schedule_child is None
                and i.schedule_expected==dict(agent_boot_id=a.agent_boot_id,microphone_epoch=a.microphone_epoch,policy_epoch=p['epoch'],owner_id=None)
                and self.listening_allowed(a) and a.listening.is_set() and v['automatic_questions_requested']
                and not a.stopping.is_set())
            if self.recovery_used:self.recovery_state='withdrawn'
            if eligible:
                self.recovery_used=True
                # No child is owned, so this exact baseline withdrawal needs no
                # socket/speaker cleanup while authority locks are held.
                i._schedule_off_locked('audio_loop_error')
                self.recovery_token=dict(binding=(a.agent_boot_id,a.microphone_epoch,p['epoch']),policy=dict(p),intent_generation=v['generation'],schedule_generation=i.schedule_generation,expires=time.monotonic()+60)
                self.recovery_state='waiting';self.recovery_sample=None;self.recovery_progress=0
        if eligible:i.wake.set()
        else:
            # Running/noneligible baseline cancellation retains its normal path,
            # including speaker/socket cleanup OUTSIDE all authority locks.
            i.schedule_withdraw('audio_loop_error',generation)

    def recovery_tick(self,a):
        if not self.recovery_pending():return
        token=self.recovery_token;now=time.monotonic()
        if not self.recovery_valid(a,token):self.recovery_state='withdrawn';return
        # This tick is reached only from the existing successful health/Hub
        # admission before capture; exceptions set last_error and invalidate us.
        if a.last_error is not None:return
        pump=getattr(a,'_capture_pump',None)
        if pump is None:return
        with pump.condition:
            receipt=pump.counters['last_read_monotonic'];count=pump.counters['read_bytes']
            if (not pump.permitted() or pump.error is not None or receipt is None or not 0<=now-receipt<=.3
                or type(count) is not int or count<=0):return
            sample=(pump.generation,count)
            if self.recovery_sample is None or self.recovery_sample[0]!=sample[0]:self.recovery_sample=sample;self.recovery_progress=0;return
            if count<=self.recovery_sample[1]:return
            self.recovery_progress+=1;self.recovery_sample=sample
            if self.recovery_progress<2:return
            if (a.phase!='listening' or not a.capture_active or a.pending_pcm is not None or a.resume_audio is not None
                or a.playback_process is not None or a.voice_response is not None):return
            self.recovery_source=pump.generation;token['source']=pump;token['source_generation']=pump.generation
        self.recovery_state='admitting'
        try:
            result=a.initiative.schedule_control(dict(enabled=True,expected_generation=token['schedule_generation'],operator_binding=dict(agent_boot_id=a.agent_boot_id,microphone_epoch=a.microphone_epoch,policy_epoch=a.motion_policy.snapshot()['epoch'],owner_id=None,expires_at_monotonic=time.monotonic()+59)),recovery_token=token)
            self.recovery_state='admitted' if result['enabled'] else 'withdrawn'
            if result['enabled']:self.recovery_grant_boot=a.agent_boot_id
        except Exception:self.recovery_state='withdrawn'
