"""Native .2 bridge traces; no factory startup/physical timing attestation."""
import threading
import unittest
import test_factory_head_guard as fixture
ORIGIN=fixture.ORIGIN
from reachy_companion.autonomous.factory_head_adapter import NativeHeadBridge

class Controller:
    def __init__(self):self.calls=[];self.receipt='pending';self.state=None
    def finite_arm_at(self,*args):self.calls.append(('arm',args))
    def finite_refresh_at(self,*args):self.calls.append(('refresh',args))
    def finite_clock_ns(self):return 0
    def finite_revoke(self,*args):self.calls.append(('revoke',args))
    def finite_enable(self,*args):self.calls.append(('enable',args))
    def finite_goals(self,*args):self.calls.append(('goals',args))
    def finite_receipt(self,*args):return self.receipt
    def finite_status(self):return self.state

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.trace=fixture.HeadGuardTests();self.trace.setUp();self.g=self.trace.guard();self.c=Controller();self.lock=threading.Lock()
        self.bridge=NativeHeadBridge(self.c,self.g,lambda joints:dict(ORIGIN),lambda pose,body:(body,0,0,0,0,0,0),self.lock,clock=lambda:self.trace.now)
        self.c.finite_clock_ns=lambda:int(self.trace.now*1e9)
        self.bridge.arm()
    def test_native_pending_survives_caller_deadline_until_actual_receipt(self):
        action=self.g.issue('pin_enable');self.assertTrue(self.bridge.submit(action))
        self.trace.now+=.2
        self.assertTrue(self.bridge.poll(action.id)['execution_busy']);self.assertIn(action.id,self.bridge.pending)
        with self.assertRaises(RuntimeError):self.bridge.submit(action)
        self.c.receipt='accepted';receipt=self.bridge.poll(action.id)
        self.assertFalse(receipt['execution_busy']);self.assertTrue(receipt['accepted']);self.g.complete(action,receipt)
    def test_stale_measurement_and_delayed_ik_block_actual_native_enqueue(self):
        action=self.g.issue('pin_enable');self.trace.now+=.2
        self.bridge.refresh(self.trace.operator(),self.trace.now)
        self.assertFalse(self.bridge.submit(action));self.assertNotIn('enable',[name for name,args in self.c.calls])
        self.setUp();self.trace.enabled(self.g);action=self.g.issue('outward')
        def slow(pose,body):self.trace.now+=.101;return (body,0,0,0,0,0,0)
        self.bridge.ik=slow
        with self.assertRaises(ValueError):self.bridge.submit(action)
        self.assertNotIn('goals',[name for name,args in self.c.calls]);self.assertTrue(self.g.closed)
    def test_native_revoke_ack_does_not_complete_stop_and_fresh_status_is_source_begin(self):
        self.bridge.revoke();stop=self.g.issue('stop_owned');self.assertFalse(self.g.stop_verified)
        for seq in range(1,4):
            self.trace.now+=.051
            self.c.state=(True,False,seq==3,.005,[-.0337,0,0,0,0,0,0,-3.0127,3.0449],[False]*9,seq)
            state=self.bridge.stop_sample()
            self.assertAlmostEqual(state['sample']['captured_at'],self.trace.now-.005)
        self.assertTrue(state['stop_known']);self.assertTrue(self.g.held());self.assertFalse(self.g.cleanup_verified())
        self.g.complete(stop,self.trace.receipt(stop,stop_known=True));self.assertTrue(self.g.cleanup_verified())
        self.assertFalse(self.bridge.stop_sample()['stop_known']) # repetition supplies no new measurement/proof
        self.assertFalse(self.g.cleanup_verified())
    def test_stop_fk_time_and_unknown_native_outcome_invalidate_prior_observations(self):
        self.bridge.revoke();self.trace.now+=.01
        self.c.state=(True,False,True,.05,[-.0337,0,0,0,0,0,0,-3.0127,3.0449],[False]*9,1)
        def slow(joints):self.trace.now+=.051;return ORIGIN
        self.bridge.fk=slow
        with self.assertRaises(ValueError):self.bridge.stop_sample()
        self.assertFalse(self.g.samples);self.assertFalse(self.g.stop_verified)
        self.setUp();action=self.g.issue('pin_enable');self.bridge.submit(action);self.c.receipt='unknown'
        self.assertTrue(self.bridge.poll(action.id)['execution_busy']);self.assertIn(action.id,self.bridge.pending)
    def test_original_absolute_deadlines_survive_native_entry_delay(self):
        c=Controller();c.finite_clock_ns=lambda:int(self.trace.now*1e9);received=[]
        def arm(owner,deadline,policy):
            self.trace.now+=.201;received.append((deadline,policy))
        c.finite_arm_at=arm
        bridge=NativeHeadBridge(c,self.g,lambda joints:ORIGIN,lambda pose,body:(body,0,0,0,0,0,0),self.lock,clock=lambda:self.trace.now)
        deadline=self.g.deadline;policy=self.g.policy_until;bridge.arm()
        self.assertEqual(received,[(int(deadline*1e9),int(policy*1e9))])
        self.assertLess(received[0][1]-int(self.trace.now*1e9),100_000_000)
        def refresh(owner,policy):self.trace.now+=.05;received.append(policy)
        c.finite_refresh_at=refresh;began=self.trace.now
        self.assertTrue(bridge.refresh(self.trace.operator(),began));self.assertEqual(received[-1],int((began+.3)*1e9))
    def test_unknown_clock_domain_type_or_unbounded_handshake_blocks_arm(self):
        for value in (1,float('nan'),True,2**64):
            self.setUp();self.bridge.arm_done=False;before=len(self.c.calls);self.c.finite_clock_ns=lambda:value
            with self.assertRaises(ValueError):self.bridge.arm()
            self.assertTrue(self.g.closed);self.assertEqual(len(self.c.calls),before)
        self.setUp();self.bridge.arm_done=False
        def slow_clock():self.trace.now+=.101;return int(self.trace.now*1e9)
        self.c.finite_clock_ns=slow_clock
        with self.assertRaises(ValueError):self.bridge.arm()
        self.assertTrue(self.g.closed)
    def test_deadline_conversion_never_rounds_up_or_accepts_overflow_types(self):
        from fractions import Fraction
        for value in (10.001,10.3,12345678.12345678):
            converted=self.bridge.deadline_ns(value)
            self.assertLessEqual(Fraction(converted,1_000_000_000),Fraction.from_float(value))
        for value in (True,float('nan'),float('inf'),-1,10**1000,2**64):
            with self.assertRaises(ValueError):self.bridge.deadline_ns(value)
    def test_closed_operator_during_clock_probe_never_arms_native(self):
        self.bridge.arm_done=False;before=len(self.c.calls)
        def cancelled():self.g.withdraw('operator_stop');return int(self.trace.now*1e9)
        self.c.finite_clock_ns=cancelled
        with self.assertRaises(RuntimeError):self.bridge.arm()
        self.assertEqual(len(self.c.calls),before)

if __name__=='__main__':unittest.main()
