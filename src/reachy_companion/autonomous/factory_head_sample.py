"""Read-only sampling through an already-open factory motor controller.

Never constructs a controller, SDK or UART owner. Native calls can block beyond
our freshness budget: an elapsed budget rejects a completed result, it does not
cancel the native queue slot. Installed motor-controller 1.5.6 retains the GIL in
raw reads; this module cannot supply an independent watchdog/owned stop.
"""
import math
import threading
import time
from .factory_head_guard import AXES, number, pose

MOTOR_IDS={'body_rotation':10, **{f'stewart_{n}':10+n for n in range(1,7)},
           'right_antenna':17,'left_antenna':18}
MODEL_IDS={**{n:1200 for n in range(10,17)},17:1190,18:1190}


def raw_bytes(value,length):
    if type(value) is not list or len(value)!=length or any(type(item) is not int or not 0<=item<=255 for item in value):
        raise ValueError('Exact native raw-byte response required')
    return bytes(value)


def xl330_position(value):
    # rustypot 1.4.2 XL330 present_position is signed i32 LE, in native radians.
    return int.from_bytes(raw_bytes(value,4),'little',signed=True)*(2*math.pi/4096)-math.pi


class ExistingFactorySampler:
    """Single actual read slot; freshness includes queue, reads and shared FK.

    Caller supplies a pinned already-open c, the SAME lock used around the
    factory's mutable kinematics update, and FK converting seven measured joint
    radians to exact XYZ(m)/RPY(rad). The factory process identity is not inferred
    from a URL. Model verification uses this same controller, once, before sample.
    No returned wall clock, cached pose or read completion time proves freshness.
    """
    def __init__(self,controller,factory_identity,fk,kinematics_lock,*,clock=time.monotonic):
        if not isinstance(factory_identity,str) or not 1<=len(factory_identity)<=256:raise ValueError('Pinned factory identity required')
        if not callable(fk) or not all(callable(getattr(controller,n,None)) for n in ('async_read_raw_bytes','get_motor_name_id')):
            raise ValueError('Installed native read/FK ABI required')
        if not all(callable(getattr(kinematics_lock,n,None)) for n in ('acquire','release')):raise ValueError('Shared factory kinematics lock required')
        self.c=controller;self.factory_identity=factory_identity;self.fk=fk;self.kinematics_lock=kinematics_lock
        self.clock=clock;self.slot=threading.Lock();self.sequence=0;self.models_verified=False;self.native_outcome_unknown=False
    @property
    def execution_busy(self):return self.slot.locked()
    def _raw(self,motor,address,length):
        try:return self.c.async_read_raw_bytes(motor,address,length)
        except BaseException:
            # A native response timeout may leave a queued command executing.
            # Only process replacement after verified cleanup can resolve this.
            self.native_outcome_unknown=True;raise
    def verify_models(self):
        if not self.slot.acquire(blocking=False):raise RuntimeError('Actual native sample slot occupied')
        self.models_verified=False
        try:
            if self.c.get_motor_name_id()!=MOTOR_IDS:raise ValueError('Pinned factory motor map mismatch')
            for motor,model in MODEL_IDS.items():
                actual=int.from_bytes(raw_bytes(self._raw(motor,0,2),2),'little')
                if actual!=model:raise ValueError('Unsupported factory motor model')
            self.models_verified=True
        finally:
            if not self.native_outcome_unknown:self.slot.release()
    def read(self):
        if not self.slot.acquire(blocking=False):raise RuntimeError('Actual native sample slot occupied')
        try:
            if not self.models_verified:raise ValueError('Actual native model reads required first')
            captured=number(self.clock()) # BEFORE first blocking native queue admission
            positions=[];torque=[]
            def fresh():
                if not 0<=number(self.clock())-captured<=.1:raise ValueError('Native read/FK exceeded 100ms freshness budget')
            for motor in range(10,19):
                fresh();positions.append(xl330_position(self._raw(motor,132,4)));fresh()
                enabled=raw_bytes(self._raw(motor,64,1),1)[0];fresh()
                if enabled not in (0,1):raise ValueError('Unknown native torque value')
                torque.append(bool(enabled))
            # Do not wait on a blocked FK producer or relabel its stale cache.
            if not self.kinematics_lock.acquire(blocking=False):raise RuntimeError('Actual factory kinematics slot occupied')
            try:
                head=self.fk(tuple(positions[:7]));pose(head);fresh()
            finally:self.kinematics_lock.release()
            self.sequence+=1
            return dict(factory_identity=self.factory_identity,provenance='native_controller_sample',
                sequence=self.sequence,captured_at=captured,head_pose=dict(zip(AXES,pose(head))),
                body_yaw=positions[0],antennas=positions[7:],torque=torque)
        finally:
            if not self.native_outcome_unknown:self.slot.release() # never release unknown native queue work


def installed_v156_admission():
    """Source-audited limitation, not hardware attestation or install action."""
    return dict(motor_controller_version='1.5.6',motion_admission=False,
        independent_watchdog=False,owner_scoped_stop=False,all_mutation_paths_fenced=False,
        native_adapter_required=True,head_hardware_acceptance=False,
        blockers=['raw_read_holds_python_gil','blocking_native_queue_before_response_timeout',
                  'native_generation_and_deadline_not_enforced','native_owner_scoped_stop_not_verified'])
