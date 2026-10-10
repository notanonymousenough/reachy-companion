import math
from pathlib import Path
import tempfile
import time
import unittest
from reachy_companion.autonomous.actuator_guard import GuardRejected
from reachy_companion.autonomous.motion_runtime import MotionRuntime,RuntimeServer
from reachy_companion.motion_proxy import MotionProxy


class Driver:
    def __init__(self):self.pose=[0.]*9;self.enabled=False;self.closed=False;self.writes=0;self.exclusive=True
    def prepare(self):return self.positions()
    def positions(self):return time.monotonic(),list(self.pose)
    def pin_enable(self,pose):self.enabled=True
    def target(self,antennas):self.pose[-2:]=antennas;self.writes+=1
    def release(self):self.enabled=False
    def close(self):self.closed=True


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.driver=Driver()
        self.op=dict(agent_boot_id='agent',microphone_epoch=2,microphone_enabled=False,capture_active=False,phase='paused')
        self.policy=dict(motor_enabled=True,quiet=False,privacy_all=False,epoch=0)
        self.runtime=MotionRuntime(self.driver,self.root/'guard',lambda:dict(self.op),self.root/'intent',owner_verified=True,
                                   policy=lambda:dict(self.policy))
        self.addCleanup(self.runtime.close)
        self.server=RuntimeServer(self.runtime,self.root/'actor.sock');self.addCleanup(self.server.close)
        self.emergency=RuntimeServer(self.runtime,self.root/'actor.sock.stop',emergency=True);self.addCleanup(self.emergency.close)
        self.proxy=MotionProxy(True,self.root/'actor.sock',lambda:dict(self.op))
        self.sequence=self.runtime.guard.high_watermark
    def request(self,kind,**extra):
        self.sequence+=1
        payload=dict(kind=kind,agent_boot_id='agent',operator_epoch=2,
                     actor_boot_id=self.runtime.guard.robot_boot_id,session_id=self.runtime.session_id,command_sequence=self.sequence,motor_epoch=self.policy['epoch'],**extra)
        return dict(command_id=str(self.sequence),hub_boot_id='hub',path='/native/antenna',payload=payload)
    def arm(self):
        reply=self.proxy.handle(self.request('arm',motor_enabled=True,quiet=False,privacy_all=False))
        self.assertTrue(reply['accepted']);return reply['result']['lease_id']
    def test_proxy_motion_lease_ignores_mic_permission_but_expires_and_cannot_revive(self):
        self.assertTrue(self.proxy.status()['ready'])
        lease=self.arm()
        command=self.request('trajectory',lease_id=lease,offset_radians=math.radians(2),duration_s=1)
        self.assertTrue(self.proxy.handle(command)['accepted'])
        self.assertFalse(self.proxy.handle(command)['accepted'])
        self.assertTrue(self.runtime.actor.stopped.wait(.8))
        self.assertTrue(self.runtime.actor.receipt['verified'])
        count=self.driver.writes
        self.assertFalse(self.proxy.handle(self.request('heartbeat',lease_id=lease,sequence=1))['accepted'])
        time.sleep(.03);self.assertEqual(self.driver.writes,count)
    def test_stale_boot_epoch_overbounds_and_legacy_routes_never_enqueue(self):
        lease=self.arm()
        for key,value in (('operator_epoch',1),('agent_boot_id','old'),('actor_boot_id','old')):
            request=self.request('trajectory',lease_id=lease,offset_radians=.01,duration_s=1)
            request['payload'][key]=value
            if key in ('operator_epoch','agent_boot_id'):
                with self.assertRaises(RuntimeError):self.proxy.handle(request)
            else:self.assertFalse(self.proxy.handle(request)['accepted'])
        self.assertFalse(self.proxy.handle(self.request('trajectory',lease_id=lease,offset_radians=.1,duration_s=1))['accepted'])
        request=self.request('trajectory',lease_id=lease,offset_radians=.01,duration_s=1)
        request['path']='/api/move/goto'
        with self.assertRaises(ValueError):self.proxy.handle(request)
        self.assertFalse(self.driver.enabled)
    def test_operator_change_revokes_independently_and_keeps_runtime_unready(self):
        lease=self.arm()
        self.proxy.handle(self.request('trajectory',lease_id=lease,offset_radians=.01,duration_s=1))
        self.op['microphone_epoch']=3
        self.assertTrue(self.runtime.actor.stopped.wait(.8))
        self.assertFalse(self.proxy.status()['ready'])
        self.assertTrue(self.runtime.actor.receipt['verified'])
    def test_crash_active_row_quarantines_restart_and_old_boot_command_is_not_replayed(self):
        lease=self.arm();old=self.request('trajectory',lease_id=lease,offset_radians=.01,duration_s=1)
        self.proxy.handle(old)
        self.runtime.guard.db.execute('INSERT OR REPLACE INTO state VALUES(1,?)',('{"status":"active"}',))
        self.runtime.guard.db.commit()
        # Independent restart DB fixture, not a second owner of the same lock.
        other=self.root/'crashed';other.mkdir()
        import shutil
        shutil.copy(self.root/'guard/guard.sqlite3',other/'guard.sqlite3')
        new=MotionRuntime(Driver(),other,lambda:dict(self.op),self.root/'intent2',owner_verified=True,policy=lambda:dict(self.policy))
        try:
            self.assertFalse(new.status()['ready'])
            with self.assertRaises(GuardRejected):new.handle(old)
            self.assertEqual(new.driver.writes,0)
        finally:new.close()
        audited=MotionRuntime(Driver(),other,lambda:dict(self.op),self.root/'intent3',
                              owner_verified=True,recovery_audited=True,policy=lambda:dict(self.policy))
        try:
            self.assertTrue(audited.status()['ready'])
            rebound=dict(old,payload=dict(old['payload'],actor_boot_id=audited.guard.robot_boot_id,session_id=audited.session_id))
            with self.assertRaises(GuardRejected):audited.handle(rebound)
            self.assertEqual(audited.driver.writes,0)
        finally:audited.close()

    def test_authoritative_quiet_privacy_and_motor_grant_withdraw_cannot_be_overridden_by_payload(self):
        for patch in ({'quiet':True},{'privacy_all':True},{'motor_enabled':False},{'motor_enabled':1},{'quiet':0}):
            self.policy.update(patch)
            self.assertFalse(self.proxy.status()['ready'])
            reply=self.proxy.handle(self.request('arm',motor_enabled=True,quiet=False,privacy_all=False))
            self.assertFalse(reply['accepted'])
            self.assertFalse(self.driver.enabled)
            self.policy.update(motor_enabled=True,quiet=False,privacy_all=False)

    def test_privacy_withdraws_an_active_trajectory_and_cannot_be_revived_by_restoring_policy(self):
        lease=self.arm()
        self.proxy.handle(self.request('trajectory',lease_id=lease,offset_radians=.01,duration_s=1))
        self.policy['privacy_all']=True
        self.assertTrue(self.runtime.actor.stopped.wait(.8))
        self.assertTrue(self.runtime.actor.receipt['verified'])
        self.policy['privacy_all']=False
        self.assertFalse(self.proxy.status()['ready'])
        self.assertFalse(self.proxy.handle(self.request('heartbeat',lease_id=lease,sequence=1))['accepted'])

    def test_more_than_256_heartbeats_use_one_persisted_watermark_and_revoke_remains_available(self):
        lease=self.arm()
        for sequence in range(600):
            self.assertTrue(self.proxy.handle(self.request('heartbeat',lease_id=lease,sequence=sequence))['accepted'])
            if sequence%50==0:time.sleep(.01)
        self.assertEqual(self.runtime.guard.db.execute('SELECT count(*) FROM ordered_watermark').fetchone()[0],1)
        self.assertEqual(self.runtime.guard.db.execute('SELECT count(*) FROM commands').fetchone()[0],0)
        self.assertTrue(self.proxy.status()['ready'])
        trajectory=self.request('trajectory',lease_id=lease,offset_radians=.01,duration_s=1)
        self.assertTrue(self.proxy.handle(trajectory)['accepted'])
        self.assertTrue(self.proxy.handle(self.request('revoke',lease_id=lease))['result']['verified_stopped'])
        self.assertFalse(self.proxy.handle(trajectory)['accepted'])

    def test_emergency_socket_stops_while_normal_ipc_is_blocked_on_sqlite(self):
        import sqlite3
        import threading
        from contextlib import contextmanager
        lease=self.arm()
        self.proxy.handle(self.request('trajectory',lease_id=lease,offset_radians=.01,duration_s=1))
        blocker=sqlite3.connect(self.root/'guard/guard.sqlite3')
        blocker.execute('BEGIN EXCLUSIVE')
        entered=threading.Event();original=self.runtime.guard.transaction
        @contextmanager
        def transaction():
            entered.set()
            with original():yield
        self.runtime.guard.transaction=transaction
        pending=self.request('heartbeat',lease_id=lease,sequence=1)
        errors=[]
        def blocked_request():
            try:self.proxy.handle(pending)
            except Exception as exc:errors.append(type(exc).__name__)
        thread=threading.Thread(target=blocked_request);thread.start()
        try:
            self.assertTrue(entered.wait(.2))
            started=time.monotonic()
            reply=self.proxy.handle(self.request('revoke',lease_id=lease))
            self.assertTrue(reply['result']['verified_stopped'])
            self.assertLess(time.monotonic()-started,.5)
            self.assertTrue(thread.is_alive())
        finally:
            blocker.rollback();blocker.close();thread.join(1)
        self.assertFalse(thread.is_alive())

    def test_storage_failure_and_sequence_exhaustion_cannot_block_verified_revoke(self):
        lease=self.arm()
        self.proxy.handle(self.request('trajectory',lease_id=lease,offset_radians=.01,duration_s=1))
        self.runtime.guard.db.close()
        self.assertFalse(self.proxy.handle(self.request('heartbeat',lease_id=lease,sequence=1))['accepted'])
        self.assertTrue(self.runtime.guard.storage_failed)
        self.runtime.guard.high_watermark=2**63-1
        self.assertTrue(self.proxy.handle(self.request('revoke',lease_id=lease))['result']['verified_stopped'])
        self.assertFalse(self.proxy.status()['ready'])

    def test_acquired_lease_revoke_bypasses_withdrawn_policy_and_unavailable_operator_provider(self):
        lease=self.arm()
        self.proxy.handle(self.request('trajectory',lease_id=lease,offset_radians=.01,duration_s=1))
        revoke=self.request('revoke',lease_id=lease)
        self.policy.update(motor_enabled=False,quiet=True,epoch=1)
        def unavailable():raise RuntimeError('Operator transport unavailable')
        self.proxy.operator=unavailable
        self.assertTrue(self.proxy.handle(revoke)['result']['verified_stopped'])
        self.assertFalse(self.proxy.status()['ready'])

    def test_closing_rejects_admission_and_still_verifies_stop(self):
        lease=self.arm()
        self.proxy.handle(self.request('trajectory',lease_id=lease,offset_radians=.01,duration_s=1))
        self.runtime.closing=True
        self.assertFalse(self.proxy.status()['ready'])
        self.assertFalse(self.proxy.handle(self.request('heartbeat',lease_id=lease,sequence=1))['accepted'])
        self.assertTrue(self.proxy.handle(self.request('revoke',lease_id=lease))['result']['verified_stopped'])


if __name__=='__main__':unittest.main()
