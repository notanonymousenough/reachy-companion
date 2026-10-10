"""Read-only fake-controller traces; no hardware or watchdog SLA proof."""
import math
import threading
import unittest
from reachy_companion.autonomous.factory_head_sample import ExistingFactorySampler,MOTOR_IDS,MODEL_IDS,xl330_position,installed_v156_admission
from reachy_companion.autonomous.factory_head_guard import FiniteHeadGuard,head_plan

class Native:
    def __init__(self):self.calls=[];self.delay=lambda:None;self.corrupt=None
    def get_motor_name_id(self):return MOTOR_IDS
    def async_read_raw_bytes(self,motor,address,length):
        self.calls.append((motor,address,length));self.delay()
        if self.corrupt is not None:return self.corrupt
        value=MODEL_IDS[motor] if address==0 else (2048 if address==132 else 0)
        return list(value.to_bytes(length,'little',signed=address==132))

class NativeSampleTests(unittest.TestCase):
    def setUp(self):
        self.now=10.;self.c=Native();self.lock=threading.Lock();self.fk_inputs=[]
        def fk(joints):self.fk_inputs.append(joints);return dict(x=0,y=0,z=0,roll=0,pitch=0,yaw=0)
        self.s=ExistingFactorySampler(self.c,'pinned-factory',fk,self.lock,clock=lambda:self.now)
        self.s.verify_models();self.c.calls.clear()
    def test_fresh_raw_positions_and_all_nine_torque_begin_before_reads(self):
        self.c.delay=lambda:setattr(self,'now',self.now+.001)
        result=self.s.read()
        self.assertEqual(result['captured_at'],10.)
        self.assertEqual(result['torque'],[False]*9);self.assertEqual(result['antennas'],[0.,0.])
        self.assertEqual(self.fk_inputs,[(0.,)*7]);self.assertEqual(result['sequence'],1)
        self.assertEqual(self.c.calls,[(n,a,l) for n in range(10,19) for a,l in ((132,4),(64,1))])
        self.assertFalse(self.s.execution_busy)
    def test_signed_decoder_and_typed_exact_bytes(self):
        for raw in (-4096,-1,0,2048,4095,2**31-1):
            value=list(raw.to_bytes(4,'little',signed=True))
            self.assertAlmostEqual(xl330_position(value),raw*2*math.pi/4096-math.pi)
        for bad in ([0]*3,[False]*4,[256]*4,b'0000'):
            with self.assertRaises(ValueError):xl330_position(bad)
    def test_full_read_span_and_fk_span_reject_stale_without_stamping_completion(self):
        self.c.delay=lambda:setattr(self,'now',self.now+.051)
        with self.assertRaises(ValueError):self.s.read()
        self.assertEqual(len(self.c.calls),2);self.assertFalse(self.s.execution_busy)
        self.c.delay=lambda:None
        def delayed_fk(joints):self.now+=.101;return dict.fromkeys(('x','y','z','roll','pitch','yaw'),0)
        self.s.fk=delayed_fk
        with self.assertRaises(ValueError):self.s.read()
        self.assertEqual(self.s.sequence,0)
    def test_native_timeout_retains_actual_occupied_slot_without_retry(self):
        def timeout():raise TimeoutError('queued response unknown')
        self.c.delay=timeout
        with self.assertRaises(TimeoutError):self.s.read()
        self.assertTrue(self.s.execution_busy);self.assertTrue(self.s.native_outcome_unknown)
        with self.assertRaises(RuntimeError):self.s.read()
        self.assertEqual(len(self.c.calls),1)
    def test_deferred_response_cannot_be_freed_by_caller_timeout(self):
        entered=threading.Event();release=threading.Event();errors=[]
        def block():entered.set();release.wait(1)
        self.c.delay=block
        def read():
            try:self.s.read()
            except Exception as error:errors.append(error)
        worker=threading.Thread(target=read);worker.start()
        try:
            self.assertTrue(entered.wait(.5));worker.join(.001);self.assertTrue(worker.is_alive())
            self.assertTrue(self.s.execution_busy)
            with self.assertRaises(RuntimeError):self.s.read()
            self.now+=.101
        finally:release.set();worker.join(1)
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],ValueError)
        self.assertFalse(self.s.execution_busy);self.assertEqual(self.s.sequence,0)
    def test_shared_fk_occupied_and_invalid_torque_do_not_produce_sample(self):
        self.lock.acquire()
        try:
            with self.assertRaises(RuntimeError):self.s.read()
        finally:self.lock.release()
        self.c.corrupt=[2]
        with self.assertRaises(ValueError):self.s.read()
        self.assertEqual(self.s.sequence,0)
    def test_wrong_models_map_and_native_model_timeout_disarm(self):
        self.c.corrupt=[0,0]
        with self.assertRaises(ValueError):self.s.verify_models()
        with self.assertRaises(ValueError):self.s.read()
        self.c.corrupt=None;self.c.get_motor_name_id=lambda:{}
        with self.assertRaises(ValueError):self.s.verify_models()
        self.c.get_motor_name_id=lambda:MOTOR_IDS
        def timeout():raise TimeoutError('model request unknown')
        self.c.delay=timeout
        with self.assertRaises(TimeoutError):self.s.verify_models()
        self.assertTrue(self.s.execution_busy)
    def test_source_preflight_cannot_supply_motion_capabilities(self):
        report=installed_v156_admission();self.assertFalse(report['motion_admission'])
        operator=dict(agent_boot_id='a',microphone_epoch=0,motion_policy_owner_id='o',motion_policy=dict(epoch=0,motor_enabled=True,quiet=False,privacy_all=False))
        sample=self.s.read();plan=head_plan(sample['head_pose'],lift_mm=1,yaw_degrees=0)
        with self.assertRaises(ValueError):FiniteHeadGuard('pinned-factory',operator,sample,report,plan,clock=lambda:self.now)

if __name__=='__main__':unittest.main()
