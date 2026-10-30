"""Finite stock-daemon expressions through Hub's permission and UUID fences.

Completion means the owned factory UUID disappeared; it does not certify pose
or a hardware stop deadline. No SDK, UART or additional motor owner is opened.
"""
import math
import threading
import time


class StockMotionAdapter:
    def __init__(self, hub, *, cooldown_s=6):
        if not hub.stock_selected() or not 3 <= cooldown_s <= 60:
            raise ValueError('Explicit stock transport and bounded cooldown required')
        self.hub = hub
        self.cooldown_s = cooldown_s
        self.session = hub.boot_id
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.hub.stock_cancel = self.cancel
        self.busy = self.closed = self.failed = False
        self.next_motion = 0
        self.cached = None
        self.receipts = []
        self.completed = 0
        self.done = threading.Event()
        self.done.set()

    def binding(self, operator):
        return dict(agent_boot_id=operator['agent_boot_id'],
                    actor_boot_id=operator['agent_boot_id'], session_id=self.session,
                    operator_epoch=operator['microphone_epoch'],
                    motor_epoch=operator['motion_policy']['epoch'], transport='stock')

    def refresh(self):
        operator, _ = self.hub.operator_proxy()
        policy = operator['motion_policy']
        with self.lock:
            allowed = (not (self.busy or self.closed or self.failed or self.hub.stock_unknown)
                       and time.monotonic() >= self.next_motion
                       and operator['microphone_enabled'] and policy['motor_enabled']
                       and not policy['quiet'] and not policy['privacy_all'])
        value = dict(binding=self.binding(operator), policy=policy,
                     microphone_enabled=operator['microphone_enabled'], motion_allowed=allowed,
                     received=time.monotonic())
        self.cached = value
        return value

    def execute(self, proposal):
        with self.lock:
            if self.busy or self.closed or self.failed or time.monotonic() < self.next_motion:
                raise RuntimeError('Stock expression unavailable')
            self.busy = True
            self.cancel.clear()
            self.done.clear()
        report = dict(accepted=False, request_id=proposal['request_id'], transport='stock',
                      pose_verified=False, hard_stop_certified=False)
        try:
            operator, _ = self.hub.operator_proxy()
            policy = operator['motion_policy']
            if (time.monotonic() >= proposal['deadline'] or proposal['motion'] != 'attentive'
                    or self.binding(operator) != proposal['actual_binding']
                    or not operator['microphone_enabled'] or not policy['motor_enabled']
                    or policy['quiet'] or policy['privacy_all'] or self.cancel.is_set()):
                raise RuntimeError('Stock proposal stale or permission withdrawn')
            angle = math.radians(4 if self.completed % 2 == 0 else -4)
            def step(yaw, antenna):
                return dict(head_pose=dict(x=0,y=0,z=0,roll=0,pitch=0,yaw=yaw),
                            antennas=[antenna,-antenna], duration=.6, interpolation='minjerk')
            binding = dict(agent_boot_id=operator['agent_boot_id'],
                           microphone_epoch=operator['microphone_epoch'],
                           microphone_enabled=operator['microphone_enabled'],
                           policy_epoch=policy['epoch'], expression_version=operator['expression_version'])
            result = self.hub.expression(dict(steps=[step(angle,angle),step(0,0)],
                                              operator_binding=binding))
            report.update(result)
            report['accepted'] = result.get('ok') is True and result.get('steps_observed') == 2
            if report['accepted']: self.completed += 1
        except Exception as exc:
            report['error'] = type(exc).__name__
            # Unknown output must be reconciled explicitly, never retried.
            if self.hub.stock_unknown: self.failed = True
        finally:
            with self.lock:
                self.busy = False
                self.next_motion = time.monotonic() + self.cooldown_s
            self.receipts.append(report)
            del self.receipts[:-32]
            self.done.set()
        return report

    def stop(self):
        self.cancel.set()
        self.done.wait(.3)
        return not self.busy and not self.hub.stock_unknown

    def close(self):
        with self.lock: self.closed = True
        return self.stop()

    def status(self):
        with self.lock:
            return dict(execution_busy=self.busy, closed=self.closed,
                        stop_known=not self.busy and not self.hub.stock_unknown,
                        hard_stop_certified=False)
