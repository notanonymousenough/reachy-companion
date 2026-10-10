"""Hub bounded antenna adapter. Inference only proposes; current actor gates dispatch."""
import math
import threading
import time
from .contracts import uid


class MotionAdapter:
    def __init__(self,hub,*,cooldown_s=4,heartbeat_s=.04):
        if not 3<=cooldown_s<=60 or not .02<=heartbeat_s<=.05:raise ValueError('Bounded motion adapter timing')
        self.hub=hub;self.cooldown_s=cooldown_s;self.heartbeat_s=heartbeat_s
        self.lock=threading.Lock();self.busy=self.closed=self.failed=False
        self.next_motion=0;self.lease=None;self.common=None
        self.completed=0;self.receipts=[];self.cached=None

    @staticmethod
    def binding(status):
        actor=status['motion_actor'];policy=actor['policy']
        return dict(agent_boot_id=status['agent_boot_id'],operator_epoch=status['microphone_epoch'],
                    actor_boot_id=actor['actor_boot_id'],session_id=actor['session_id'],motor_epoch=policy['epoch'])

    def refresh(self):
        with self.lock:busy=self.busy;cached=self.cached
        if busy and cached:
            operator=self.hub.agent('/operator');policy=operator['motion_policy']
            binding=dict(cached['binding'],agent_boot_id=operator['agent_boot_id'],operator_epoch=operator['microphone_epoch'],motor_epoch=policy['epoch'])
            return dict(cached,binding=binding,policy=policy,microphone_enabled=operator['microphone_enabled'],motion_allowed=False,received=time.monotonic())
        status=self.hub.agent('/status');actor=status['motion_actor'];policy=actor['policy']
        binding=self.binding(status)
        if (actor.get('binding') is not None and actor['binding'][0]!=self.hub.boot_id):
            raise RuntimeError('Prior Hub owner requires coordinated actor restart')
        if (actor['operator']['agent_boot_id']!=status['agent_boot_id']
                or actor['operator']['microphone_epoch']!=status['microphone_epoch']
                or type(status['microphone_enabled']) is not bool or type(policy['epoch']) is not int):
            raise RuntimeError('Actual actor/operator authority unknown')
        allowed=(actor['ready'] is True and actor['owner_verified'] is True and actor['kernel_exclusive'] is True
                 and policy['motor_enabled'] is True and policy['quiet'] is False and policy['privacy_all'] is False)
        with self.lock:
            allowed=allowed and not (self.busy or self.closed or self.failed) and time.monotonic()>=self.next_motion
        self.cached=dict(binding=binding,policy=policy,microphone_enabled=status['microphone_enabled'],
                    motion_allowed=allowed,received=time.monotonic(),high_watermark=actor['command_high_watermark'])
        return self.cached

    def execute(self,proposal):
        with self.lock:
            if self.closed or self.failed or self.busy or time.monotonic()<self.next_motion:raise RuntimeError('Motion admission unavailable')
            self.busy=True
        report=dict(accepted=False,request_id=proposal['request_id'],source='scheduler_fresh_model_proposal',audio_commands=0)
        try:
            fresh=self.hub.agent('/status');actor=fresh['motion_actor'];policy=actor['policy']
            if (time.monotonic()>proposal['deadline'] or proposal['motion']!='attentive'
                    or self.binding(fresh)!=proposal['actual_binding'] or not actor['ready']
                    or policy['motor_enabled'] is not True or policy['quiet'] is not False or policy['privacy_all'] is not False):
                raise RuntimeError('Motion proposal stale or policy withdrawn')
            self.common=self.binding(fresh);sequence=actor['command_high_watermark']
            def call(kind,**extra):
                nonlocal sequence
                if self.closed and kind!='revoke':raise RuntimeError('Hub owner withdrawn')
                sequence+=1
                value=dict(self.common,kind=kind,command_sequence=sequence,**extra)
                command_id=uid()
                if kind=='trajectory':report.update(trajectory=value,command_id=command_id,hub_boot_id=self.hub.boot_id)
                return self.hub.native_motion(value,command_id=command_id)
            self.lease=call('arm',motor_enabled=True,quiet=False,privacy_all=False)['lease_id']
            report['dispatch']=call('trajectory',lease_id=self.lease,offset_radians=math.radians(-2 if self.completed%2==0 else 2),duration_s=2)
            started=time.monotonic();heartbeat=0
            while time.monotonic()-started<1.2:
                heartbeat+=1;call('heartbeat',lease_id=self.lease,sequence=heartbeat);time.sleep(self.heartbeat_s)
            mode='expiry' if self.completed%2==0 else 'revoke'
            if mode=='revoke':
                began=time.monotonic();reply=call('revoke',lease_id=self.lease)
                report['request_to_verified_s']=time.monotonic()-began
                if reply.get('verified_stopped') is not True:raise RuntimeError('Explicit physical stop unknown')
            else:time.sleep(.47)
            after=self.hub.agent('/status');state=after['motion_actor'];hold=state['hold']
            report.update(stop_mode=mode,heartbeat_to_verified_s=state['heartbeat_to_verified_s'],hold=hold,
                          max_displacement_radians=state['max_displacement_radians'],target_writes=state['target_writes'])
            bound=state['heartbeat_to_verified_s'] if mode=='expiry' else report['request_to_verified_s']
            report['accepted']=(self.binding(after)==self.common and hold is not None and hold['verified'] is True
                and bound is not None and bound<=.5 and hold['trajectory_updates_after_hold']==0
                and state['max_displacement_radians']>=3*2*math.pi/4096)
            if not report['accepted']:raise RuntimeError('Bounded movement/500ms stop acceptance failed')
            self.completed+=1
            self.lease=None
        except Exception as exc:
            report['error']=type(exc).__name__+': '+str(exc)[:120]
            self.failed=True
            report['stop_verified']=self.stop()
            if report['stop_verified']:self.lease=None
        finally:
            self.receipts.append(report);self.receipts=self.receipts[-32:]
            with self.lock:self.busy=False;self.next_motion=time.monotonic()+self.cooldown_s
        return report

    def stop(self):
        if self.lease and self.common:
            try:
                reply=self.hub.native_motion(dict(self.common,kind='revoke',command_sequence=0,lease_id=self.lease))
                return reply.get('verified_stopped') is True
            except Exception:return False
        return True

    def close(self):
        self.closed=True
        return self.stop()
