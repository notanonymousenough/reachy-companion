"""Finite scheduler and real local IPC with synthetic already-open controllers."""
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
import test_factory_head_guard as fixture
from reachy_companion.autonomous.factory_head_runtime import FactoryHeadRuntime,PrivateFactoryHeadIPC
from reachy_companion.motion_proxy import receive,send

class World:
    def __init__(self):
        self.now=10.;self.head=dict(fixture.ORIGIN);self.torque=False;self.seq=0;self.stop_at=None
        self.calls=[];self.receipts={};self.ready=True
    def finite_clock_ns(self):return int(self.now*1e9)
    def finite_arm_at(self,*args):self.calls.append(('arm',args))
    def finite_refresh_at(self,*args):
        if self.stop_at is not None:raise RuntimeError('withdrawn')
    def finite_revoke(self,*args):
        if self.stop_at is None:self.stop_at=self.now
        self.torque=False;self.calls.append(('revoke',args))
    def finite_enable(self,owner,action,generation):self.torque=True;self.receipts[action]='accepted';self.calls.append(('enable',None))
    def finite_goals(self,owner,action,generation,values):
        self.head=dict(zip(fixture.AXES,values[1:7]));self.receipts[action]='accepted';self.calls.append(('target',dict(self.head)))
    def finite_receipt(self,action):return self.receipts.get(action,'unknown')
    def finite_status(self):
        self.now+=.001;self.seq+=1
        return (True,False,self.now-self.stop_at>=.1,0,[-.0337,*[self.head[k] for k in fixture.AXES],-3.0127,3.0449],[False]*9,self.seq)
    def verify_models(self):pass
    def read(self):
        self.now+=.001;self.seq+=1
        return dict(factory_identity='factory-process-start',provenance='native_controller_sample',sequence=self.seq,
            captured_at=self.now,head_pose=dict(self.head),body_yaw=-.0337,antennas=[-3.0127,3.0449],torque=[self.torque]*9)
    def operator(self):return fixture.HeadGuardTests.operator(self)
    def sleep(self,seconds):self.now+=seconds
    def runtime(self,caps=None):
        return FactoryHeadRuntime(self,self,self.operator,lambda joints:dict(zip(fixture.AXES,joints[1:])),
            lambda pose,body:(body,*[pose[k] for k in fixture.AXES]),threading.RLock(),caps or fixture.CAPS,
            'factory-process-start',readiness=lambda:self.ready,clock=lambda:self.now,sleep=self.sleep)

class RuntimeTests(unittest.TestCase):
    def command(self,runtime):return dict(kind='run',runtime_boot=runtime.boot,lift_mm=5,yaw_degrees=3,pitch_degrees=0,duration=1)
    def test_complete_relative_cycle_returns_nonneutral_baseline_and_verifies_cleanup(self):
        world=World();runtime=world.runtime();runtime.handle(self.command(runtime));self.assertTrue(runtime.done.wait(2))
        self.assertTrue(runtime.result['accepted'],runtime.result);self.assertTrue(runtime.result['cleanup_verified'])
        self.assertEqual(world.head,fixture.ORIGIN);self.assertFalse(world.torque)
        targets=[value for kind,value in world.calls if kind=='target'];self.assertGreater(len(targets),20)
        for value in targets:
            self.assertEqual((value['x'],value['y'],value['roll']),(fixture.ORIGIN['x'],fixture.ORIGIN['y'],fixture.ORIGIN['roll']))
            self.assertLessEqual(value['z'],fixture.ORIGIN['z']+.005+1e-12)
        with self.assertRaises(RuntimeError):runtime.handle(self.command(runtime))
    def test_missing_capability_or_unready_factory_never_enables(self):
        for fail in ('capability','readiness'):
            world=World();caps=dict(fixture.CAPS)
            if fail=='capability':caps['independent_watchdog']=False
            else:world.ready=False
            runtime=world.runtime(caps);runtime.handle(self.command(runtime));self.assertTrue(runtime.done.wait(2))
            self.assertFalse(runtime.result['accepted']);self.assertNotIn('enable',[name for name,_ in world.calls])
    def test_stop_while_preparation_blocked_is_latched_before_enable(self):
        world=World();runtime=world.runtime();entered=threading.Event();release=threading.Event()
        def models():entered.set();release.wait(1)
        world.verify_models=models;runtime.handle(self.command(runtime));self.assertTrue(entered.wait(.5))
        result=runtime.handle(dict(kind='stop',runtime_boot=runtime.boot));self.assertFalse(result['stop_known'])
        release.set();self.assertTrue(runtime.done.wait(2));self.assertNotIn('enable',[name for name,_ in world.calls])
        self.assertFalse(runtime.result['accepted'])
    def test_operator_mic_epoch_change_during_motion_withdraws_without_restoration(self):
        world=World();runtime=world.runtime();original=world.operator
        def operator():
            value=original()
            if any(name=='target' for name,_ in world.calls):value['microphone_epoch']+=1
            return value
        world.operator=operator;runtime.operator=operator;runtime.handle(self.command(runtime));self.assertTrue(runtime.done.wait(2))
        self.assertFalse(runtime.result['accepted']);self.assertFalse(world.torque)
        self.assertEqual(operator()['microphone_epoch'],3)
    def test_actual_unknown_native_slot_is_not_released_after_deadline(self):
        world=World();runtime=world.runtime()
        world.finite_enable=lambda owner,action,generation:world.receipts.update({action:'unknown'})
        runtime.handle(self.command(runtime));self.assertTrue(runtime.done.wait(2))
        self.assertFalse(runtime.result['accepted']);self.assertTrue(runtime.bridge.pending)
        self.assertTrue(runtime.guard.status()['execution_busy']);self.assertFalse(runtime.result['cleanup_verified'])
    def test_polling_faster_than_native_sampling_does_not_invent_or_erase_measurements(self):
        world=World();runtime=world.runtime();original=world.finite_status;calls=[0]
        def status():
            calls[0]+=1
            if calls[0]%2:return (True,True,False,float('inf'),[],[],0)
            return original()
        world.finite_status=status
        runtime.handle(self.command(runtime));self.assertTrue(runtime.done.wait(2))
        self.assertTrue(runtime.result['accepted'],runtime.result)

class IPCTests(unittest.TestCase):
    def test_real_unix_socket_bound_mode_boot_and_no_stale_reclaim(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory,0o700);runtime=World().runtime();ipc=PrivateFactoryHeadIPC(runtime,directory)
            self.assertEqual(ipc.path.stat().st_mode&0o777,0o600)
            thread=threading.Thread(target=ipc.serve);thread.start()
            try:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                    client.settimeout(1);client.connect(str(ipc.path));send(client,{'kind':'status'})
                    self.assertEqual(receive(client,16384)['result']['runtime_boot'],runtime.boot)
                with self.assertRaises(ValueError):PrivateFactoryHeadIPC(runtime,directory)
            finally:ipc.close();thread.join(1)
            self.assertFalse(thread.is_alive());self.assertTrue(ipc.path.exists());self.assertTrue(runtime.cancelled.is_set())
    def test_world_readable_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory,0o755)
            with self.assertRaises(ValueError):PrivateFactoryHeadIPC(World().runtime(),directory)

if __name__=='__main__':unittest.main()
