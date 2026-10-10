"""Finite head admission core for an adapter inside the existing factory daemon.

No device, SDK constructor, transport, install hook or UART owner is created.
Native sampling/fencing/stop capabilities must be supplied by a reviewed adapter;
HTTP receipt time, cached mode and move-list disappearance cannot qualify them.
"""
from dataclasses import dataclass
import math
import time
import threading
from functools import wraps
from .contracts import uid

AXES=('x','y','z','roll','pitch','yaw')


def number(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Finite head value required')
    return value


def pose(value):
    if not isinstance(value,dict) or set(value)!=set(AXES):raise ValueError('Exact XYZ/RPY pose required')
    return tuple(number(value[axis]) for axis in AXES)


def head_plan(origin,*,lift_mm,yaw_degrees,pitch_degrees=0,duration=1.5):
    origin=pose(origin)
    if (not 0<=number(lift_mm)<=5 or abs(number(yaw_degrees))>3 or abs(number(pitch_degrees))>3
            or not 1<=number(duration)<=2 or not any((lift_mm,yaw_degrees,pitch_degrees))):
        raise ValueError('Bounded relative head lift/turn required')
    target=list(origin);target[2]+=lift_mm/1000;target[4]+=math.radians(pitch_degrees);target[5]+=math.radians(yaw_degrees)
    return dict(origin=origin,target=tuple(target),duration=duration,interpolation='minjerk',
        lift_mm=lift_mm,yaw_degrees=yaw_degrees,pitch_degrees=pitch_degrees)


def policy_binding(value):
    policy=value['motion_policy']
    if (not isinstance(value.get('agent_boot_id'),str) or not 1<=len(value['agent_boot_id'])<=128
            or type(policy.get('epoch')) is not int or not 0<=policy['epoch']<2**63
            or not isinstance(value.get('motion_policy_owner_id'),str) or not 1<=len(value['motion_policy_owner_id'])<=128
            or any(type(policy.get(key)) is not bool for key in ('motor_enabled','quiet','privacy_all'))
            or type(value.get('microphone_epoch')) is not int or not 0<=value['microphone_epoch']<2**63):
        raise ValueError('Typed factory operator binding required')
    return value['agent_boot_id'],policy['epoch'],value['motion_policy_owner_id'],value['microphone_epoch']


@dataclass(frozen=True)
class HeadAction:
    id:str
    guard_boot:str
    factory_identity:str
    generation:int
    kind:str
    target:tuple|None
    body_yaw:float
    antennas:tuple
    operator_binding:tuple
    issued_at:float
    deadline:float


def locked(method):
    @wraps(method)
    def call(self,*args,**kwargs):
        with self.lock:return method(self,*args,**kwargs)
    return call


class FiniteHeadGuard:
    """One finite owner, immutable issued actions and actual occupied slots.

    The adapter must call admit() immediately at native mutation admission,
    fence later factory writes against generation withdrawal, and provide an
    atomically owner-scoped stop. Never map stop to an unscoped REST disable.
    It must run expire() on an independent watchdog and seal every competing
    REST/WS/SDK mutation path before constructing this core.
    """
    def __init__(self,factory_identity,operator,sample,capabilities,plan,*,clock=time.monotonic,duration=12):
        self.lock=threading.RLock();self.clock=clock;now=number(clock())
        if not isinstance(factory_identity,str) or not 1<=len(factory_identity)<=256:raise ValueError('Pinned factory identity required')
        if not 4<=number(duration)<=12:raise ValueError('Absolute finite head duration required')
        if (not isinstance(capabilities,dict) or any(capabilities.get(name) is not True for name in
                ('all_mutation_paths_fenced','native_sample_clock','native_all_torque_read','owner_scoped_stop',
                 'enable_pins_present_before_torque','independent_watchdog'))):
            raise ValueError('Reviewed native factory capabilities required')
        self.factory_identity=factory_identity;self.boot=uid();self.binding=policy_binding(operator)
        self.generation=0;self.phase='armed';self.inflight={};self.closed=False;self.stop_verified=False;self.reason=None
        self.policy_until=now+.3;self.deadline=now+duration;self.stop_at=None;self.samples=[];self.last_sequence=-1;self.motion_completed_at=None
        self.plan=head_plan(dict(zip(AXES,plan['origin'])),lift_mm=plan['lift_mm'],
            yaw_degrees=plan['yaw_degrees'],pitch_degrees=plan['pitch_degrees'],
            duration=plan['duration'])
        if tuple(plan['target'])!=self.plan['target']:raise ValueError('Head plan changed unrelated axes')
        self.body_yaw=number(sample['body_yaw']);self.antennas=tuple(sample['antennas'])
        if len(self.antennas)!=2:raise ValueError('Two preserved antennas required')
        for item in self.antennas:number(item)
        self.accept_sample(sample)
        if any(sample['torque']) or pose(sample['head_pose'])!=self.plan['origin']:raise ValueError('Actual disabled baseline required')
        self.observe_operator(operator,now)
    @locked
    def observe_operator(self,value,request_started):
        self.expire() # a missed policy TTL cannot be revived by a late poll
        try:
            now=self.clock();request_started=number(request_started)
            if not 0<=now-request_started<=.1:raise ValueError('Fresh actual operator request required')
            binding=policy_binding(value);policy=value['motion_policy']
        except (ValueError,KeyError,TypeError):
            self.withdraw('operator_unknown');raise
        if (binding!=self.binding or policy['motor_enabled'] is not True or policy['quiet'] or policy['privacy_all']):
            self.withdraw('operator_changed');return False
        if self.closed:return False
        self.policy_until=request_started+.3;return True
    @locked
    def accept_sample(self,value):
        try:return self._accept_sample(value)
        except (ValueError,KeyError,TypeError):
            self.invalidate_sample();raise
    @locked
    def invalidate_sample(self):
        self.withdraw('native_sample_unknown');self.samples.clear();self.stop_verified=False
    def _accept_sample(self,value):
        self.expire()
        now=self.clock()
        if (value.get('factory_identity')!=self.factory_identity or value.get('provenance')!='native_controller_sample'
                or type(value.get('sequence')) is not int or not self.last_sequence<value['sequence']<2**63
                or not 0<=now-number(value.get('captured_at'))<=.1
                or type(value.get('torque')) is not list or len(value['torque'])!=9
                or any(type(item) is not bool for item in value['torque'])):
            raise ValueError('Fresh native position/torque sample required')
        head=pose(value['head_pose']);body=number(value['body_yaw']);antennas=tuple(value['antennas'])
        if abs(body-self.body_yaw)>.01 or len(antennas)!=2:raise ValueError('Body yaw/antennas changed')
        for item in antennas:number(item)
        if any(abs(a-b)>.01 for a,b in zip(antennas,self.antennas)):raise ValueError('Antennas left baseline')
        captured=value['captured_at']
        if self.samples and captured<=self.samples[-1][0]:raise ValueError('Native sample clock did not advance')
        if not self.closed and any(abs(a-b)>limit for a,b,limit in zip(head,self.plan['origin'],
                (.001,.001,.006,math.radians(.5),math.radians(3.5),math.radians(3.5)))):
            raise ValueError('Observed head left finite scope')
        self.last_sequence=value['sequence'];self.samples.append((captured,head,tuple(value['torque'])));del self.samples[:-16]
        if self.phase in ('enabled_wait_sample','outward_wait_sample','return_wait_sample'):
            target=self.plan['target'] if self.phase=='outward_wait_sample' else self.plan['origin']
            reached=all(abs(a-b)<=limit for a,b,limit in zip(head,target,(.001,.001,.001,*([math.radians(.5)]*3))))
            if self.phase=='enabled_wait_sample' and not reached:raise ValueError('Enable did not hold baseline')
            if (all(all(sample[2]) for sample in self.samples) and captured>self.motion_completed_at and reached and self.held()):
                self.phase={'enabled_wait_sample':'enabled','outward_wait_sample':'outward_done','return_wait_sample':'returned'}[self.phase]
    @locked
    def expire(self):
        if not self.closed and (self.clock()>=self.deadline or self.clock()>=self.policy_until):self.withdraw('deadline_or_policy_expired')
    @locked
    def withdraw(self,reason):
        if not self.closed:
            self.closed=True;self.phase='closing';self.generation+=1;self.reason=reason;self.stop_at=self.clock();self.samples.clear()
    @locked
    def issue(self,kind):
        self.expire()
        if kind not in ('pin_enable','outward','return','stop_owned'):raise ValueError('Known finite head action required')
        if kind=='stop_owned':
            if not self.closed:raise ValueError('Withdraw before owned stop')
            if any(action.kind=='stop_owned' for action in self.inflight.values()):raise RuntimeError('Actual stop slot occupied')
            target=None
        else:
            if self.closed or self.inflight:raise RuntimeError('Actual head slot occupied/withdrawn')
            expected={'pin_enable':'armed','outward':'enabled','return':'outward_done'}
            if self.phase!=expected[kind]:raise RuntimeError('Head action order')
            target=self.plan['target'] if kind=='outward' else self.plan['origin']
        action=HeadAction(uid(),self.boot,self.factory_identity,self.generation,kind,target,self.body_yaw,self.antennas,
            self.binding,self.clock(),self.deadline)
        self.inflight[action.id]=action;return action
    @locked
    def admit(self,action,factory_identity,physical_owner):
        self.expire()
        if (self.inflight.get(action.id) is not action or action.factory_identity!=factory_identity
                or physical_owner!=(self.boot,self.binding) or action.generation!=self.generation):return False
        if action.kind=='stop_owned':return self.closed
        if not self.samples or not 0<=self.clock()-self.samples[-1][0]<=.1:
            self.withdraw('native_sample_stale_at_admission');return False
        return not self.closed and self.clock()<action.deadline and self.clock()<self.policy_until
    @locked
    def complete(self,action,receipt):
        # Called only after the actual native slot has completed, never a client timeout.
        if self.inflight.get(action.id) is not action:raise ValueError('Actual action slot mismatch')
        self.expire()
        if not isinstance(receipt,dict) or receipt.get('execution_busy') is not False:
            self.withdraw('native_slot_not_drained');return False
        del self.inflight[action.id]
        if (not isinstance(receipt,dict) or receipt.get('action_id')!=action.id or receipt.get('guard_boot')!=self.boot
                or receipt.get('factory_identity')!=self.factory_identity or receipt.get('generation')!=action.generation
                or tuple(receipt.get('operator_binding',()))!=self.binding or receipt.get('execution_busy') is not False
                or receipt.get('accepted') is not True):
            self.withdraw('native_outcome_unknown');return False
        if action.kind=='stop_owned':
            self.stop_verified=receipt.get('stop_known') is True;return self.stop_verified
        if self.closed or action.generation!=self.generation:
            self.stop_verified=False;self.samples.clear();return False # stop again after late slot drains
        self.motion_completed_at=self.clock();self.samples.clear()
        self.phase={'pin_enable':'enabled_wait_sample','outward':'outward_wait_sample','return':'return_wait_sample'}[action.kind];return True
    @locked
    def held(self):
        if len(self.samples)<3 or self.samples[-1][0]-self.samples[0][0]<.1:return False
        for before,after in zip(self.samples,self.samples[1:]):
            dt=after[0]-before[0]
            if any(abs(a-b)/dt>limit for index,(a,b) in enumerate(zip(before[1],after[1]))
                    for limit in ([.001] if index<3 else [.05])):return False
        return self.clock()-self.samples[-1][0]<=.1
    @locked
    def cleanup_verified(self):
        # Physical proof still requires native source clock and all-nine torque
        # samples AFTER withdrawal plus completed actual stop and drained slots.
        now=self.clock()
        return (self.closed and self.stop_verified and not self.inflight and self.held()
            and all(not any(sample[2]) for sample in self.samples)
            and self.samples[0][0]>=self.stop_at and 0<=now-self.stop_at<=.5)
    @locked
    def status(self):return dict(guard_boot=self.boot,phase=self.phase,reason=self.reason,closed=self.closed,
        execution_busy=bool(self.inflight),stop_known=self.cleanup_verified(),cleanup_verified=self.cleanup_verified(),
        native_adapter_required=True,head_hardware_acceptance=False)
