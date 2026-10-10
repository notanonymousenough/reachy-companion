"""Protocol/state/fence traces only; no installed factory adapter or device proof."""
import copy
from dataclasses import replace
import math
import unittest
from reachy_companion.autonomous.factory_head_guard import FiniteHeadGuard,head_plan,AXES

CAPS={key:True for key in ('all_mutation_paths_fenced','native_sample_clock','native_all_torque_read',
    'owner_scoped_stop','enable_pins_present_before_torque','independent_watchdog')}
ORIGIN=dict(x=-.0218,y=.00385,z=-.0476,roll=.0684,pitch=.5088,yaw=-.033)


class HeadGuardTests(unittest.TestCase):
    def setUp(self):self.now=10.;self.seq=0
    def operator(self):return dict(agent_boot_id='agent',microphone_epoch=2,motion_policy_owner_id='owner',
        motion_policy=dict(epoch=3,motor_enabled=True,quiet=False,privacy_all=False))
    def sample(self,head=None,torque=False):
        self.seq+=1;return dict(factory_identity='factory-process-start',provenance='native_controller_sample',
            sequence=self.seq,captured_at=self.now,head_pose=head or ORIGIN,body_yaw=-.0337,antennas=[-3.0127,3.0449],torque=[torque]*9)
    def guard(self,**kw):
        return FiniteHeadGuard('factory-process-start',self.operator(),self.sample(),kw.pop('caps',CAPS),
            kw.pop('plan',head_plan(ORIGIN,lift_mm=5,yaw_degrees=3)),clock=lambda:self.now,**kw)
    def receipt(self,action,**kw):return dict(action_id=action.id,guard_boot=action.guard_boot,factory_identity=action.factory_identity,
        generation=action.generation,operator_binding=action.operator_binding,execution_busy=False,accepted=True,**kw)
    def settle(self,g,head,torque):
        for _ in range(3):
            self.now+=.051
            if not g.closed:g.observe_operator(self.operator(),self.now)
            g.accept_sample(self.sample(head,torque))
    def enabled(self,g):
        action=g.issue('pin_enable');self.assertTrue(g.admit(action,g.factory_identity,(g.boot,g.binding)))
        self.assertTrue(g.complete(action,self.receipt(action)))
        with self.assertRaises(RuntimeError):g.issue('outward') # ACK alone cannot prove safe enable
        self.settle(g,ORIGIN,True);return g
    def test_relative_plan_preserves_nonneutral_baseline_and_unrelated_axes(self):
        plan=head_plan(ORIGIN,lift_mm=5,yaw_degrees=-3,pitch_degrees=-3)
        self.assertAlmostEqual(plan['target'][2],ORIGIN['z']+.005)
        self.assertAlmostEqual(plan['target'][4],ORIGIN['pitch']-math.radians(3))
        self.assertEqual(plan['target'][:2],(ORIGIN['x'],ORIGIN['y']));self.assertEqual(plan['target'][3],ORIGIN['roll'])
        self.guard(plan=plan) # exact5mm survives floating-point subtraction
        for fields in (dict(lift_mm=6,yaw_degrees=0),dict(lift_mm=True,yaw_degrees=0),dict(lift_mm=0,yaw_degrees=4),
                       dict(lift_mm=1,yaw_degrees=0,duration=.5),dict(lift_mm=0,yaw_degrees=0)):
            with self.assertRaises(ValueError):head_plan(ORIGIN,**fields)
    def test_missing_native_capability_and_untimed_cached_pose_disarm(self):
        for name in CAPS:
            caps=dict(CAPS);caps[name]=False
            with self.assertRaises(ValueError):self.guard(caps=caps)
        g=self.guard();sample=self.sample();sample['provenance']='http_receipt_time'
        with self.assertRaises(ValueError):g.accept_sample(sample)
        self.assertTrue(g.closed)
    def test_unknown_stale_repeated_and_invalid_torque_samples_withdraw(self):
        for field,value in (('captured_at',9.),('sequence',1),('torque',[False]*8),('torque',[0]*9),('factory_identity','new-factory')):
            with self.subTest(field=field,value=value):
                g=self.guard();sample=self.sample();sample[field]=value
                if field=='sequence':sample[field]=g.last_sequence
                with self.assertRaises(ValueError):g.accept_sample(sample)
                self.assertTrue(g.closed)
    def test_operator_epoch_quiet_and_mic_change_revoke_without_revival(self):
        for change in ('epoch','quiet','microphone_epoch','owner','boot'):
            g=self.guard();action=g.issue('pin_enable');operator=self.operator()
            if change=='epoch':operator['motion_policy']['epoch']+=1
            elif change=='quiet':operator['motion_policy']['quiet']=True
            elif change=='microphone_epoch':operator['microphone_epoch']+=1
            elif change=='owner':operator['motion_policy_owner_id']='new-human'
            else:operator['agent_boot_id']='new-agent'
            self.assertFalse(g.observe_operator(operator,self.now));self.assertFalse(g.admit(action,g.factory_identity,(g.boot,g.binding)))
            self.assertFalse(g.observe_operator(self.operator(),self.now));self.assertTrue(g.closed)
            stop=g.issue('stop_owned');self.assertFalse(g.admit(stop,g.factory_identity,('foreign',g.binding)))
    def test_unknown_or_stale_operator_withdraws_before_ttl(self):
        for operator,started in (({},self.now),(self.operator(),self.now-.101)):
            g=self.guard();action=g.issue('pin_enable')
            with self.assertRaises((ValueError,KeyError)):g.observe_operator(operator,started)
            self.assertTrue(g.closed);self.assertFalse(g.admit(action,g.factory_identity,(g.boot,g.binding)))
    def test_late_fresh_poll_cannot_revive_expired_policy(self):
        g=self.guard();self.now+=.301
        self.assertFalse(g.observe_operator(self.operator(),self.now));self.assertTrue(g.closed)
    def test_deadline_not_extended_by_fresh_operator_and_forged_action_rejected(self):
        g=self.guard(duration=4);action=g.issue('pin_enable')
        self.assertFalse(g.admit(replace(action),g.factory_identity,(g.boot,g.binding)))
        self.now=13.99;g.observe_operator(self.operator(),self.now);self.now=14.;g.expire()
        self.assertTrue(g.closed);self.assertFalse(g.admit(action,g.factory_identity,(g.boot,g.binding)))
    def test_deferred_native_completion_remains_busy_and_requires_new_stop_after_drain(self):
        g=self.guard();action=g.issue('pin_enable');self.now+=.301;g.expire()
        stop=g.issue('stop_owned');g.complete(stop,self.receipt(stop,stop_known=True))
        self.assertTrue(g.status()['execution_busy']);self.assertFalse(g.cleanup_verified())
        self.assertFalse(g.complete(action,self.receipt(action)));self.assertFalse(g.stop_verified)
        self.assertFalse(g.admit(action,g.factory_identity,(g.boot,g.binding)))
        stop=g.issue('stop_owned');g.complete(stop,self.receipt(stop,stop_known=True));self.settle(g,ORIGIN,False)
        self.assertTrue(g.cleanup_verified())
    def test_enable_drift_and_return_ack_without_pose_proof_are_not_accepted(self):
        g=self.guard();action=g.issue('pin_enable');g.complete(action,self.receipt(action));self.now+=.01
        bad=dict(ORIGIN,z=ORIGIN['z']+.002)
        with self.assertRaises(ValueError):g.accept_sample(self.sample(bad,True))
        self.assertTrue(g.closed)
        g=self.enabled(self.guard());outward=g.issue('outward');g.complete(outward,self.receipt(outward))
        with self.assertRaises(RuntimeError):g.issue('return')
        self.settle(g,dict(zip(AXES,g.plan['target'])),True);self.assertEqual(g.phase,'outward_done')
        g.observe_operator(self.operator(),self.now);back=g.issue('return');g.complete(back,self.receipt(back))
        self.assertEqual(g.phase,'return_wait_sample');self.assertFalse(g.cleanup_verified())
    def test_stop_uuid_scope_moving_pose_torque_and_actual_fresh_completion_clock(self):
        for failure in ('velocity','torque','late_clock','unknown_stop'):
            g=self.guard();g.withdraw('finite_done');stop=g.issue('stop_owned')
            g.complete(stop,self.receipt(stop,stop_known=failure!='unknown_stop'))
            for i in range(3):
                self.now+=.051;head=dict(ORIGIN,z=ORIGIN['z']+.001*i) if failure=='velocity' else ORIGIN
                g.accept_sample(self.sample(head,failure=='torque'))
            if failure=='late_clock':self.now=g.stop_at+.501
            self.assertFalse(g.cleanup_verified())
    def test_body_antennas_scope_and_unknown_native_receipt_withdraw(self):
        for field,value in (('body_yaw',.5),('antennas',[0,0])):
            g=self.guard();sample=self.sample();sample[field]=value
            with self.assertRaises(ValueError):g.accept_sample(sample)
            self.assertTrue(g.closed)
        g=self.guard();action=g.issue('pin_enable');bad=self.receipt(action);bad['execution_busy']=True
        self.assertFalse(g.complete(action,bad));self.assertTrue(g.closed);self.assertFalse(g.stop_verified)


if __name__=='__main__':unittest.main()
