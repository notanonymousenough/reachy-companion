"""Reusable bounded native service. Caller must establish the root deployment fence."""
import json
import math
import os
from pathlib import Path
import socket
import threading
import time
from collections import deque
from .actuator_guard import ActuatorGuard, GuardRejected
from .contracts import Authority, uid
from .native_motion import HoldActor
from ..motion_proxy import receive, send


class MotionRuntime:
    def __init__(self, driver, directory, operator, intent_path, *, owner_verified=False, recovery_audited=False, policy=None):
        if owner_verified is not True: raise RuntimeError('Deployment ownership gate')
        self.driver, self.operator, self.intent_path = driver, operator, Path(intent_path)
        self.policy=policy or (lambda:dict(motor_enabled=False,quiet=False,privacy_all=True,epoch=0))
        self.lock = threading.RLock()
        self.actor = None
        self.binding = self.lease = None
        self.last_heartbeat = None
        self.session_id=uid()
        self.events = deque(maxlen=32)
        self.operator_initial = operator()
        if (not isinstance(self.operator_initial.get('agent_boot_id'),str)
                or not 1<=len(self.operator_initial['agent_boot_id'])<=128
                or type(self.operator_initial.get('microphone_epoch')) is not int
                or not 0<=self.operator_initial['microphone_epoch']<2**63
                or type(self.operator_initial.get('microphone_enabled')) is not bool
                or self.operator_initial.get('microphone_state_error')):
            raise RuntimeError('Actual operator authority unknown')
        self.closed = self.operator_invalid = self.closing = False
        self.done = threading.Event()
        self.policy_initial=self.policy()
        self.initial = driver.prepare()
        self.guard = ActuatorGuard(directory,self.stop,ttl=.24,poll=.005)
        # No automatic recovery acknowledgement. A prior active/stopping row
        # remains quarantined even when the newly observed baseline is off.
        if recovery_audited is True:
            # Explicit trusted deployment operation, after the root fence and
            # fresh driver.prepare() verified all torque off/stationary. Never
            # an HTTP/model operation; no old lease or command is restored.
            self.guard.acknowledge_stopped(verified_stopped=True)
        self.monitor = threading.Thread(target=self.watch_operator,daemon=True)
        self.monitor.start()

    def stop(self):
        actor = self.actor
        return actor is None or actor.stop()

    def watch_operator(self):
        while not self.done.wait(.05):
            try: valid = self.policy_allows() and self.operator_signature(self.operator()) == self.operator_signature(self.operator_initial)
            except Exception: valid = False
            if not valid:
                self.operator_invalid = True
                self.guard.revoke()
                return

    @staticmethod
    def operator_signature(value):
        return tuple(value.get(key) for key in ('agent_boot_id','microphone_epoch','microphone_enabled','microphone_state_error'))

    def policy_allows(self):
        try:
            value=self.policy()
            return (isinstance(value,dict) and set(value)=={'motor_enabled','quiet','privacy_all','epoch'}
                    and type(value['epoch']) is int and 0<=value['epoch']<2**63 and value['epoch']==self.policy_initial.get('epoch')
                    and value['motor_enabled'] is True and value['quiet'] is False and value['privacy_all'] is False)
        except Exception:return False

    def status(self):
        status = self.guard.status()
        actor = self.actor
        return dict(protocol='ordered-native-v2',owner_verified=True,actor_boot_id=self.guard.robot_boot_id,
                    writer_pid=os.getpid(),kernel_exclusive=getattr(self.driver,'exclusive',False),
                    ready=not self.closed and not self.closing and not self.operator_invalid and self.policy_allows() and not status['quarantined']
                          and not self.guard.storage_failed and self.guard.high_watermark<2**63-1,
                    policy=self.policy(),session_id=self.session_id,command_high_watermark=self.guard.high_watermark,
                    operator=self.operator_initial,leased=status['leased'],quarantined=status['quarantined'],
                    binding=self.binding,hold=actor.receipt if actor else None,
                    target_writes=actor.target_writes if actor else 0,
                    heartbeat_to_verified_s=(actor.receipt['completed']-self.last_heartbeat
                        if actor and actor.receipt and actor.receipt.get('verified') and self.last_heartbeat is not None else None),
                    max_displacement_radians=(max((abs(p[7]-actor.origin[7]) for _,p in actor.samples),default=0) if actor else 0),
                    supported='bounded_antenna17_only',stop_reason=actor.stop_reason if actor else None,
                    recent_requests=list(self.events))

    def finish_actor(self):
        if self.actor:
            if not self.actor.stop(): raise RuntimeError('Physical hold unknown')
            self.actor.close(close_driver=False)
            self.actor = None

    def handle(self, envelope):
        if envelope == {'kind':'status'}: return self.status()
        if set(envelope) != {'command_id','hub_boot_id','path','payload'} or envelope['path'] != '/native/antenna':
            raise ValueError('Typed antenna envelope required')
        payload = envelope['payload']
        common = {'kind','agent_boot_id','operator_epoch','actor_boot_id','session_id','command_sequence','motor_epoch'}
        kind = payload.get('kind') if isinstance(payload,dict) else None
        extra = {'arm':{'motor_enabled','quiet','privacy_all'},'heartbeat':{'lease_id','sequence'},
                 'trajectory':{'lease_id','offset_radians','duration_s'},'revoke':{'lease_id'}}.get(kind)
        if extra is None or set(payload) != common | extra: raise ValueError('Unknown typed trajectory operation')
        for key in ('command_id','hub_boot_id'):
            if not isinstance(envelope[key],str) or not 1 <= len(envelope[key]) <= 128: raise ValueError('Identity bound')
        if (type(payload['motor_epoch']) is not int or payload['motor_epoch']!=self.policy_initial.get('epoch')
                or payload['session_id'] != self.session_id or payload['actor_boot_id'] != self.guard.robot_boot_id
                or payload['agent_boot_id'] != self.operator_initial['agent_boot_id']
                or type(payload['operator_epoch']) is not int
                or payload['operator_epoch'] != self.operator_initial['microphone_epoch']
                or (kind!='revoke' and (self.operator_invalid or self.closed or self.closing or not self.policy_allows()))): raise GuardRejected('Stale boot/operator/policy authority')
        binding = (envelope['hub_boot_id'],payload['agent_boot_id'],payload['operator_epoch'])
        command_id = envelope['command_id']
        if kind=='revoke':
            # Separate IPC listener enters here without the normal command/DB
            # lock, including when fsync is stalled or the ledger is exhausted.
            if binding!=self.binding or not self.lease or payload['lease_id']!=self.lease.lease_id:
                raise GuardRejected('Lease/owner mismatch')
            known=self.guard.emergency_output_stop()
            receipt=self.actor.receipt if self.actor else None
            if not known or receipt is None or not receipt.get('verified'):raise RuntimeError('Physical stop unknown')
            return dict(accepted=True,command_id=command_id,hub_boot_id=binding[0],
                        result=dict(verified_stopped=True,hold=receipt),actor_boot_id=self.guard.robot_boot_id,writer_pid=os.getpid())
        with self.lock:
            if self.operator_signature(self.operator()) != self.operator_signature(self.operator_initial): raise GuardRejected('Actual operator changed')
            if kind == 'arm':
                if ((self.binding is not None and binding!=self.binding) or self.guard.lease or self.guard.quarantined
                        or payload['motor_enabled'] is not True or payload['quiet'] is not False
                        or payload['privacy_all'] is not False): raise GuardRejected('Motor policy/lease gate')
                self.guard.admit_ordered(payload['command_sequence'])
                self.finish_actor()
                self.actor = HoldActor(self.driver)
                if self.operator_invalid or not self.policy_allows() or self.operator_signature(self.operator())!=self.operator_signature(self.operator_initial):
                    raise GuardRejected('Operator changed during preparation')
                if not self.intent_path.exists():
                    with self.intent_path.open('x') as output:
                        json.dump({'baseline_torque':[0]*9,'enabled_ids':[17]},output)
                        output.flush();os.fsync(output.fileno())
                self.lease = self.guard.arm(Authority(binding[0], 'native-endpoint',
                    robot_boot_id=self.guard.robot_boot_id,operator_epoch=binding[2]),
                    microphone_enabled=self.operator_initial['microphone_enabled'],channel='motion',
                    motor_enabled=True,quiet=False,privacy_all=False,fence_attested=True)
                self.binding = binding
                self.last_heartbeat = None
                result = dict(lease_id=self.lease.lease_id,actor_boot_id=self.guard.robot_boot_id)
            else:
                if binding != self.binding or not self.lease or payload['lease_id'] != self.lease.lease_id:
                    raise GuardRejected('Lease/owner mismatch')
                if kind == 'trajectory':
                    offset,duration = payload['offset_radians'],payload['duration_s']
                    if (type(offset) not in (int,float) or not math.isfinite(offset) or abs(offset)>math.radians(2)
                            or type(duration) not in (int,float) or not math.isfinite(duration) or not .4<=duration<=2):
                        raise ValueError('Finite antenna bounds')
                    self.guard.admit_ordered(payload['command_sequence'],self.lease)
                    try:self.guard.output.enqueue(self.lease,lambda:self.actor.enqueue(offset,duration,self.guard.deadline))
                    except BaseException:
                        self.guard.emergency_output_stop();raise
                    result = dict(queued=True,lease_id=self.lease.lease_id)
                elif kind == 'heartbeat':
                    # Validate sequence before consuming its durable ID.
                    sequence = payload['sequence']
                    if type(sequence) is not int or not 0<=sequence<=2**63-1 or sequence<=self.guard.sequence:
                        raise GuardRejected('Stale heartbeat sequence')
                    self.guard.admit_ordered(payload['command_sequence'],self.lease)
                    self.guard.heartbeat(self.lease,sequence)
                    if self.actor.plan is not None:
                        try:self.actor.heartbeat(self.guard.deadline)
                        except BaseException:
                            self.guard.emergency_output_stop();raise
                    self.last_heartbeat = self.guard.deadline-self.guard.ttl
                    result = dict(live=True)
            return dict(accepted=True,command_id=command_id,hub_boot_id=binding[0],result=result,
                        actor_boot_id=self.guard.robot_boot_id,writer_pid=os.getpid())

    def close(self):
        if self.closed:return
        self.closed = True
        self.done.set();self.monitor.join(.5)
        self.guard.close()
        try: self.finish_actor()
        finally: self.driver.close()


class RuntimeServer:
    """One bounded Unix request at a time; watchdogs run independently."""
    def __init__(self, runtime, path, *, emergency=False):
        self.runtime,self.path = runtime,Path(path)
        self.emergency=emergency
        if self.path.exists(): raise RuntimeError('Preexisting native socket must be audited')
        self.server = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.server.bind(str(self.path));os.chmod(self.path,0o600)
        self.server.listen(2);self.server.settimeout(.1)
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        while not self.done.is_set():
            try: connection,_ = self.server.accept()
            except socket.timeout: continue
            except OSError: return
            with connection:
                connection.settimeout(.8)
                request = None
                started=time.monotonic();error=None
                try:
                    request = receive(connection,4096)
                    if self.emergency and (not isinstance(request,dict) or not isinstance(request.get('payload'),dict) or request['payload'].get('kind')!='revoke'):
                        raise ValueError('Emergency listener only accepts revoke')
                    reply = self.runtime.handle(request)
                except Exception as exc:
                    error=type(exc).__name__+': '+str(exc)[:160]
                    reply = dict(accepted=False,error=type(exc).__name__)
                    if isinstance(request,dict):
                        reply.update({key:request.get(key) for key in ('command_id','hub_boot_id')})
                    reply.update(writer_pid=os.getpid(),actor_boot_id=self.runtime.guard.robot_boot_id)
                if isinstance(request,dict) and request!={'kind':'status'}:
                    payload=request.get('payload')
                    kind=payload.get('kind') if isinstance(payload,dict) else None
                    self.runtime.events.append(dict(kind=kind if kind in ('arm','trajectory','heartbeat','revoke') else 'unsupported',
                        accepted=reply.get('accepted',False),error=error,
                        elapsed_s=time.monotonic()-started,lease_remaining_s=self.runtime.guard.deadline-time.monotonic()))
                try: send(connection,reply)
                except OSError: pass
    def close(self):
        self.done.set();self.server.close();self.thread.join(1)
        self.path.unlink(missing_ok=True)
