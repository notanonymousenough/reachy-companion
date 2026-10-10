"""Long local-only ordered ledger acceptance. Simulated driver; no devices/models."""
import argparse
import json
from pathlib import Path
import tempfile
import time
from reachy_companion.autonomous.motion_runtime import MotionRuntime
from reachy_companion.autonomous.actuator_guard import GuardRejected


class SimulatedDriver:
    exclusive=False
    def __init__(self):self.writes=0
    def prepare(self):return self.positions()
    def positions(self):return time.monotonic(),[0.]*9
    def pin_enable(self,pose):raise RuntimeError('This probe never admits a trajectory')
    def target(self,pose):self.writes+=1
    def release(self):pass
    def close(self):pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration',type=float,default=60)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 55<=args.duration<=75 or args.output.exists():raise ValueError('Finite fresh local receipt required')
    operator=dict(agent_boot_id='simulated-agent',microphone_epoch=0,microphone_enabled=False)
    policy=dict(motor_enabled=True,quiet=False,privacy_all=False,epoch=1)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        runtime=MotionRuntime(SimulatedDriver(),root/'guard',lambda:operator,root/'intent',owner_verified=True,policy=lambda:policy)
        counter=0
        def request(kind,**extra):
            nonlocal counter
            counter+=1
            payload=dict(kind=kind,agent_boot_id=operator['agent_boot_id'],operator_epoch=0,motor_epoch=1,
                actor_boot_id=runtime.guard.robot_boot_id,session_id=runtime.session_id,command_sequence=counter,**extra)
            return dict(command_id=str(counter),hub_boot_id='simulated-hub',path='/native/antenna',payload=payload)
        old_arm=request('arm',motor_enabled=True,quiet=False,privacy_all=False)
        lease=runtime.handle(old_arm)['result']['lease_id'];began=time.monotonic();count=0
        while time.monotonic()-began<args.duration:
            runtime.handle(request('heartbeat',lease_id=lease,sequence=count));count+=1;time.sleep(.1)
        report=dict(mode='long_local_simulated_native_ledger',duration_s=time.monotonic()-began,heartbeats=count,
                    watermark=runtime.guard.high_watermark,
                    watermark_rows=runtime.guard.db.execute('SELECT count(*) FROM ordered_watermark').fetchone()[0],
                    uuid_rows=runtime.guard.db.execute('SELECT count(*) FROM commands').fetchone()[0],hardware_commands=0,models=0)
        runtime.handle(request('revoke',lease_id=lease));runtime.close()
        restarted=MotionRuntime(SimulatedDriver(),root/'guard',lambda:operator,root/'intent2',owner_verified=True,policy=lambda:policy)
        report['replay_rejections']=[]
        try:
            for rebound in (False,True):
                payload=dict(old_arm['payload'])
                if rebound:payload.update(actor_boot_id=restarted.guard.robot_boot_id,session_id=restarted.session_id)
                try:restarted.handle(dict(old_arm,payload=payload));report['replay_rejections'].append(False)
                except GuardRejected:report['replay_rejections'].append(True)
            report['new_boot_watermark']=restarted.guard.high_watermark
            report['new_driver_writes']=restarted.driver.writes
        finally:restarted.close()
        report['accepted']=(count>256 and report['watermark_rows']==1 and report['uuid_rows']==0
            and all(report['replay_rejections']) and report['new_driver_writes']==0 and report['new_boot_watermark']==report['watermark'])
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps(report),flush=True)
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
