"""Finite scheduler/private Unix IPC for a reviewed already-open factory.

No device/SDK/UART constructor or factory deployment. Runner supplies actual
source/build/producer/bounded-I/O capability proofs and the measured FK/IK bridge.
A control stop only latches withdrawal; actual cleanup is measured separately.
"""
import os
from pathlib import Path
import socket
import stat
import threading
import time
from .contracts import uid
from .factory_head_guard import FiniteHeadGuard,head_plan,AXES
from .factory_head_adapter import NativeHeadBridge
from ..motion_proxy import receive,send

class FactoryHeadRuntime:
    def __init__(self,controller,sampler,operator,fk,ik,kinematics_lock,capabilities,factory_identity,
                 *,readiness,clock=time.monotonic,sleep=time.sleep):
        if not callable(readiness):raise ValueError('Actual factory readiness callback required')
        self.c=controller;self.sampler=sampler;self.operator=operator;self.fk=fk;self.ik=ik;self.kinematics_lock=kinematics_lock
        self.capabilities=dict(capabilities);self.factory_identity=factory_identity;self.clock=clock;self.sleep=sleep
        self.readiness=readiness
        self.boot=uid();self.guard=None;self.bridge=None;self.worker=None;self.result=None;self.lock=threading.RLock()
        self.done=threading.Event();self.claimed=False
        self.cancelled=threading.Event()
    def status(self):
        with self.lock:
            return dict(runtime_boot=self.boot,writer_pid=os.getpid(),factory_identity=self.factory_identity,
                claimed=self.claimed,execution_busy=bool(self.worker and self.worker.is_alive()),
                guard=self.guard.status() if self.guard else None,result=self.result,
                head_hardware_acceptance=False) # runner must correlate this with actual source/build/native evidence
    def _operator(self):
        began=self.clock();value=self.operator();return value,began
    def _tick(self,sample=True):
        if self.readiness() is not True:self.bridge.revoke();raise RuntimeError('Factory producer fence changed')
        value,began=self._operator()
        if not self.bridge.refresh(value,began):raise RuntimeError('Actual operator withdrew')
        self.guard.expire()
        if self.guard.closed:raise RuntimeError('Finite head withdrawn')
        if sample:self.guard.accept_sample(self.sampler.read())
        if self.cancelled.is_set():self.bridge.revoke();raise RuntimeError('Private runtime stopped')
    def _receipt(self,native_id):
        while True:
            receipt=self.bridge.poll(native_id)
            if not receipt['execution_busy']:
                if not receipt['accepted']:raise RuntimeError('Actual native action rejected')
                return receipt
            self._tick();self.sleep(.005)
    def _settle(self,phase):
        while self.guard.phase!=phase:
            self._tick();self.sleep(.04)
    def _movement(self,kind):
        action=self.guard.issue(kind);start=self.clock();duration=self.guard.plan['duration'];sequence=0
        origin=self.guard.plan['origin'] if kind=='outward' else self.guard.plan['target']
        target=action.target
        while True:
            self._tick() # measured source freshness BEFORE every actual native target
            fraction=min(1.,max(0.,(self.clock()-start)/duration));weight=10*fraction**3-15*fraction**4+6*fraction**5
            point=tuple(a+(b-a)*weight for a,b in zip(origin,target));sequence+=1
            if not self.bridge.submit(action,target=point,sub_id=f'{action.id}:{sequence}'):raise RuntimeError('Head admission withdrew')
            receipt=self._receipt(f'{action.id}:{sequence}')
            if fraction==1.:
                self.guard.complete(action,receipt);break
            self.sleep(.04)
        self._settle('outward_done' if kind=='outward' else 'returned')
    def _cleanup(self):
        self.bridge.revoke();stop=self.guard.issue('stop_owned')
        # No fake release after a timeout. Rejected/late native receipts must
        # actually return before draining their containing scheduler action.
        deadline=self.guard.stop_at+.5
        while self.clock()<deadline:
            for native_id in list(self.bridge.pending):self.bridge.poll(native_id)
            if not self.bridge.pending:
                for action in list(self.guard.inflight.values()):
                    if action.kind!='stop_owned':
                        self.guard.complete(action,dict(action_id=action.id,guard_boot=action.guard_boot,
                            factory_identity=action.factory_identity,generation=action.generation,
                            operator_binding=action.operator_binding,accepted=False,execution_busy=False))
            try:state=self.bridge.stop_sample()
            except (ValueError,RuntimeError):state=None
            if state and state['stop_known'] and not state['execution_busy'] and self.guard.held():
                self.guard.complete(stop,dict(action_id=stop.id,guard_boot=stop.guard_boot,factory_identity=stop.factory_identity,
                    generation=stop.generation,operator_binding=stop.operator_binding,accepted=True,execution_busy=False,stop_known=True))
                return self.guard.cleanup_verified()
            self.sleep(.005)
        return False # preserve unresolved actual native/core slots and source proof failure
    def _run(self,plan):
        error=None;verified=False
        try:
            if self.readiness() is not True:raise RuntimeError('Actual factory not ready/fenced')
            self.sampler.verify_models();sample=self.sampler.read();value,began=self._operator()
            prepared=head_plan(sample['head_pose'],**plan)
            guard=FiniteHeadGuard(self.factory_identity,value,sample,self.capabilities,prepared,clock=self.clock)
            guard.observe_operator(value,began)
            self.guard=guard
            self.bridge=NativeHeadBridge(self.c,guard,self.fk,self.ik,self.kinematics_lock,clock=self.clock)
            if self.cancelled.is_set():raise RuntimeError('Private runtime stopped before arm')
            self.bridge.arm();self._tick();enable=guard.issue('pin_enable')
            if not self.bridge.submit(enable):raise RuntimeError('Enable admission withdrew')
            guard.complete(enable,self._receipt(enable.id));self._settle('enabled')
            self._movement('outward');self._movement('return')
        except BaseException as exc:error=type(exc).__name__
        finally:
            if self.bridge:
                try:verified=self._cleanup()
                except BaseException as exc:error=error or type(exc).__name__
            with self.lock:
                self.result=dict(finite_sequence_completed=error is None,cleanup_verified=verified,accepted=error is None and verified,
                    error=error,guard=self.guard.status() if self.guard else None,head_hardware_acceptance=False)
            self.done.set()
    def handle(self,body):
        if body=={'kind':'status'}:return self.status()
        if not isinstance(body,dict) or body.get('runtime_boot')!=self.boot:raise ValueError('Current private runtime binding required')
        if body.get('kind')=='stop' and set(body)=={'kind','runtime_boot'}:
            self.cancelled.set() # a stop during preparation also prevents subsequent arm/enable
            bridge=self.bridge
            if bridge is None:return dict(cancelled=True,withdrawn=False,stop_known=False)
            bridge.revoke();return dict(cancelled=True,withdrawn=True,stop_known=False) # latch receipt only; never physical ACK
        if body.get('kind')!='run' or set(body)!={'kind','runtime_boot','lift_mm','yaw_degrees','pitch_degrees','duration'}:
            raise ValueError('Exact finite head command required')
        plan={key:body[key] for key in ('lift_mm','yaw_degrees','pitch_degrees','duration')}
        head_plan(dict.fromkeys(AXES,0),**plan) # typed bounded validation before occupying single-use run
        with self.lock:
            if self.claimed:raise RuntimeError('Finite factory runtime cannot rearm')
            self.claimed=True
            self.worker=threading.Thread(target=self._run,args=(plan,),daemon=True)
            self.worker.start()
        return dict(queued=True,runtime_boot=self.boot) # no physical acceptance implied

class PrivateFactoryHeadIPC:
    """Operator-only local socket; exclusive operator-owned directory contract.

    No network listener. Never remove stale/foreign paths or reclaim a previous
    runtime. Runner owns quarantined-path cleanup after actual physical proof.
    """
    def __init__(self,runtime,directory):
        self.runtime=runtime;self.directory=Path(directory);self.path=self.directory/'factory-head.sock'
        info=self.directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700
                or self.directory.is_symlink() or os.path.lexists(self.path)):
            raise ValueError('Existing exclusive owned 0700 directory and absent socket required')
        self.directory_identity=(info.st_dev,info.st_ino);self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            self.socket.bind(str(self.path));os.chmod(self.path,0o600)
        except BaseException:self.socket.close();raise
        self.socket.listen(4);self.socket.settimeout(.1);self.closed=threading.Event()
    def _connection(self,connection):
        try:
            with connection:
                connection.settimeout(.2);request=receive(connection,4096)
                if not isinstance(request,dict):raise ValueError('Typed private request required')
                result=self.runtime.handle(request);send(connection,dict(ok=True,result=result))
        except (OSError,ValueError,RuntimeError):pass # no contents/credentials in logs
    def serve(self):
        try:
            while not self.closed.is_set():
                info=self.directory.lstat()
                if (info.st_dev,info.st_ino)!=self.directory_identity:raise RuntimeError('Private IPC directory rebound')
                try:connection,_=self.socket.accept()
                except socket.timeout:continue
                # Separate workers keep the stop latch independent of an occupied request.
                threading.Thread(target=self._connection,args=(connection,),daemon=True).start()
        except OSError:
            if not self.closed.is_set():raise
        finally:self.close()
    def close(self):
        self.closed.set();self.socket.close()
        self.runtime.cancelled.set()
        if self.runtime.bridge:self.runtime.bridge.revoke()
        # Deliberately retain the socket pathname; no stale auto-recovery/unlink.
