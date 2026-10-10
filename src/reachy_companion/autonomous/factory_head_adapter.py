"""Finite native .2 bridge for an already-open, fenced factory process.

No constructor, deployment, endpoint, listener or hardware acceptance is implied.
The runtime must install all producer fences and exact source/build proofs before
using this bridge. Each native subcommand remains occupied until its actual
receipt, even when a caller's deadline expires.
"""
import math
import threading
import time
from .factory_head_guard import AXES,number,pose

NATIVE_METHODS=('finite_arm','finite_refresh','finite_revoke','finite_enable','finite_goals',
                'finite_receipt','finite_status')


class NativeHeadBridge:
    def __init__(self,controller,guard,fk,ik,kinematics_lock,*,clock=time.monotonic):
        if any(not callable(getattr(controller,n,None)) for n in NATIVE_METHODS):raise ValueError('Native finite-head.2 ABI required')
        if not callable(fk) or not callable(ik):raise ValueError('Reviewed measured FK/bounded IK required')
        self.c=controller;self.guard=guard;self.fk=fk;self.ik=ik;self.kinematics_lock=kinematics_lock;self.clock=clock
        self.owner=guard.boot;self.pending={};self.arm_done=False;self.last_native_sequence=0;self.lock=threading.RLock()
    def arm(self):
        now=self.clock();remaining=int((self.guard.deadline-now)*1000);policy=int((self.guard.policy_until-now)*1000)
        if not 4000<=remaining<=12000 or not 1<=policy<=300:raise ValueError('Fresh finite owner budgets required')
        if self.arm_done:raise RuntimeError('Native owner already armed')
        self.c.finite_arm(self.owner,remaining,policy);self.arm_done=True
    def refresh(self,operator,request_started):
        if not self.guard.observe_operator(operator,request_started):self.revoke();return False
        remaining=int((self.guard.policy_until-self.clock())*1000)
        if not 1<=remaining<=300:self.guard.withdraw('policy_unknown');self.revoke();return False
        try:self.c.finite_refresh(self.owner,remaining)
        except BaseException:
            self.guard.withdraw('native_policy_unknown');self.revoke();raise
        return True
    def revoke(self):
        if not self.guard.closed:self.guard.withdraw('owner_withdrawn')
        if self.arm_done:self.c.finite_revoke(self.owner) # latch only; never claim completed stop from its ACK
    def submit(self,action,*,target=None,sub_id=None):
        with self.lock:
            if not self.arm_done:raise RuntimeError('Native owner not armed')
            if self.pending:raise RuntimeError('Actual native subcommand slot occupied')
            if action.kind=='stop_owned':raise ValueError('Use revoke then measured stop polling')
            if not self.guard.admit(action,self.guard.factory_identity,(self.guard.boot,self.guard.binding)):
                self.revoke();return False
            native_id=sub_id or action.id
            if not isinstance(native_id,str) or not 1<=len(native_id)<=128:raise ValueError('Native action ID required')
            if action.kind=='pin_enable':values=None
            else:
                requested=tuple(target) if target is not None else action.target
                if len(requested)!=6:raise ValueError('Exact bounded interpolated pose required')
                origin=self.guard.plan['target'] if action.kind=='return' else self.guard.plan['origin'];endpoint=action.target
                for value,start,end in zip(requested,origin,endpoint):
                    number(value)
                    if not min(start,end)-1e-12<=value<=max(start,end)+1e-12:raise ValueError('Interpolation left relative head plan')
                if not self.kinematics_lock.acquire(blocking=False):raise RuntimeError('Actual factory IK slot occupied')
                began=self.clock()
                try:head=tuple(self.ik(dict(zip(AXES,requested)),action.body_yaw))
                finally:self.kinematics_lock.release()
                if (len(head)!=7 or any(not math.isfinite(number(v)) for v in head)
                        or abs(head[0]-action.body_yaw)>.0001 or self.clock()-began>.1):
                    self.guard.withdraw('native_ik_unknown');self.revoke();raise ValueError('Fresh preserved-body native IK required')
                values=(*head,*action.antennas)
                # Includes FK/IK elapsed time; fresh policy alone cannot refresh measurements.
                if not self.guard.admit(action,self.guard.factory_identity,(self.guard.boot,self.guard.binding)):
                    self.revoke();return False
            self.pending[native_id]=action # set BEFORE potentially uncertain enqueue outcome
            try:
                if values is None:self.c.finite_enable(self.owner,native_id,0)
                else:self.c.finite_goals(self.owner,native_id,0,list(values))
            except BaseException:
                self.guard.withdraw('native_enqueue_unknown');self.revoke();raise
            return True # QUEUED, not an actual native ACK or measured movement
    def poll(self,native_id):
        with self.lock:
            action=self.pending.get(native_id)
            if action is None:raise ValueError('Actual occupied native ID required')
            result=self.c.finite_receipt(native_id)
            if result in ('pending','unknown'):return dict(execution_busy=True,accepted=False)
            if result!='accepted' and not (isinstance(result,str) and result.startswith('rejected:')):
                self.guard.withdraw('native_receipt_unknown');self.revoke();return dict(execution_busy=True,accepted=False)
            del self.pending[native_id]
            accepted=result=='accepted'
            if not accepted:self.guard.withdraw('native_rejected');self.revoke()
            return dict(execution_busy=False,accepted=accepted,action_id=action.id,guard_boot=action.guard_boot,
                factory_identity=action.factory_identity,generation=action.generation,operator_binding=action.operator_binding)
    def stop_sample(self):
        try:return self._stop_sample()
        except (ValueError,KeyError,TypeError,RuntimeError):
            self.guard.invalidate_sample();raise
    def _stop_sample(self):
        """Fresh native read-group sample AFTER withdrawal, including actual FK time."""
        with self.lock:
            if not self.guard.closed:raise ValueError('Withdraw before stop sampling')
            started=self.clock();state=self.c.finite_status()
            if not isinstance(state,(list,tuple)) or len(state)!=7:raise ValueError('Exact native status ABI required')
            withdrawn,busy,known,age,positions,torque,sequence=state
            if any(type(v) is not bool for v in (withdrawn,busy,known)) or not withdrawn:raise ValueError('Native withdrawal unknown')
            if (type(sequence) is not int or sequence<=self.last_native_sequence
                    or not 0<=number(age)<=.1 or len(positions)!=9 or len(torque)!=9
                    or any(type(v) is not bool for v in torque)):raise ValueError('Fresh advancing all-nine native status required')
            values=tuple(number(v) for v in positions);captured=started-age # conservative BEGIN clock, never receipt timestamp
            if not self.kinematics_lock.acquire(blocking=False):raise RuntimeError('Actual factory FK slot occupied')
            try:head=self.fk(values[:7]);pose(head)
            finally:self.kinematics_lock.release()
            if not 0<=self.clock()-captured<=.1:raise ValueError('Native group/FK status stale')
            self.last_native_sequence=sequence
            sample=dict(factory_identity=self.guard.factory_identity,provenance='native_controller_sample',sequence=sequence,
                captured_at=captured,head_pose=head,body_yaw=values[0],antennas=values[7:],torque=list(torque),native_sequence=sequence)
            sample['sequence']=self.guard.last_sequence+1 # map advancing native source to this guard's observation stream
            self.guard.accept_sample(sample)
            return dict(execution_busy=busy or bool(self.pending),stop_known=known and not busy and not self.pending,sample=sample)
