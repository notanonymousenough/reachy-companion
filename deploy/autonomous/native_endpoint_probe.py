"""Finite actual Hub -> Agent proxy -> native service client, no REST fallback."""
import argparse
import json
import math
from pathlib import Path
import time
from reachy_companion.config import Config
from reachy_companion.hub import Hub


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--agent-url',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--failure-mode',action='store_true')
    parser.add_argument('--replay-fixture',type=Path)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    config=Config(args.config)
    config.data['guarded_motion']['enabled']=True
    config.data['network']['agent_url']=args.agent_url
    hub=Hub(config);report=dict(mode='finite_hub_native_endpoint',accepted=False)
    # Includes SSH/root preflight/factory withdrawal/camera warmup, not lease
    # time. The independently bounded robot unit still ends after nine seconds.
    deadline=time.monotonic()+30
    while True:
        try:
            status=hub.agent('/status');actor=status['motion_actor']
            if actor['ready'] or (args.replay_fixture and actor.get('actor_boot_id')):break
        except Exception:pass
        if time.monotonic()>deadline:
            report['error']='native_endpoint_startup_timeout'
            with args.output.open('x') as output:json.dump(report,output,indent=2)
            raise SystemExit(2)
        time.sleep(.05)
    report['operator_before']={key:status[key] for key in ('agent_boot_id','microphone_epoch','microphone_enabled','capture_active','phase')}
    common=dict(agent_boot_id=status['agent_boot_id'],operator_epoch=status['microphone_epoch'],actor_boot_id=actor['actor_boot_id'])
    if args.replay_fixture:
        fixture=json.loads(args.replay_fixture.read_text())
        hub.boot_id=fixture['hub_boot_id']
        report['restart_ready']=actor['ready'];report['restart_quarantined']=actor['quarantined']
        report['replay_rejections']=[]
        for rebound in (False,True):
            old=dict(fixture['trajectory'])
            if rebound:old['actor_boot_id']=actor['actor_boot_id']
            try:hub.native_motion(old,command_id=fixture['command_id']);report['replay_rejections'].append(False)
            except Exception:report['replay_rejections'].append(True)
        report['after']=hub.agent('/status')['motion_actor']
        report['accepted']=all(report['replay_rejections']) and report['after']['target_writes']==0 and not report['after']['leased']
        with args.output.open('x') as output:json.dump(report,output,indent=2)
        print(json.dumps(report))
        if not report['accepted']:raise SystemExit(2)
        return
    def call(kind,**extra):return hub.native_motion(dict(common,kind=kind,**extra))
    lease=call('arm',motor_enabled=True,quiet=False,privacy_all=False)['lease_id']
    report['arm']=lease
    trajectory_id='endpoint-'+hub.boot_id
    trajectory=dict(common,kind='trajectory',lease_id=lease,offset_radians=math.radians(2),duration_s=2 if args.failure_mode else 1)
    report['dispatch']=hub.native_motion(trajectory,command_id=trajectory_id)
    if args.failure_mode:
        report.update(trajectory=trajectory,command_id=trajectory_id,hub_boot_id=hub.boot_id,owner_failure_observed=False)
        started=time.monotonic();sequence=0
        while time.monotonic()-started<2:
            try:
                sequence+=1;call('heartbeat',lease_id=lease,sequence=sequence);time.sleep(.04)
            except Exception:report['owner_failure_observed']=True;break
        report['accepted']=report['owner_failure_observed']
        with args.output.open('x') as output:json.dump(report,output,indent=2)
        print(json.dumps(report))
        if not report['accepted']:raise SystemExit(2)
        return
    started=time.monotonic();sequence=0
    while time.monotonic()-started<.65:
        sequence+=1;call('heartbeat',lease_id=lease,sequence=sequence)
        report['last_heartbeat']=time.monotonic();time.sleep(.04)
    time.sleep(.45)
    ended=hub.agent('/status');report['after_expiry']=ended['motion_actor']
    report['duplicate_rejected']=False
    try:hub.native_motion(trajectory,command_id=trajectory_id)
    except Exception:report['duplicate_rejected']=True
    report['revival_rejected']=False
    try:call('heartbeat',lease_id=lease,sequence=sequence+1)
    except Exception:report['revival_rejected']=True
    hold=report['after_expiry']['hold']
    # Calculated wholly inside the robot runtime's clock domain.
    report['heartbeat_to_verified_s']=report['after_expiry']['heartbeat_to_verified_s']
    report['hold_duration_s']=hold['completed']-hold['started'] if hold else None
    report['operator_unchanged']=report['operator_before']=={key:ended[key] for key in report['operator_before']}
    second=call('arm',motor_enabled=True,quiet=False,privacy_all=False)['lease_id']
    call('trajectory',lease_id=second,offset_radians=math.radians(2),duration_s=1)
    started=time.monotonic();sequence=0
    while time.monotonic()-started<.5:
        sequence+=1;call('heartbeat',lease_id=second,sequence=sequence);time.sleep(.04)
    report['explicit_revoke']=call('revoke',lease_id=second)
    report['accepted']=(report['duplicate_rejected'] and report['revival_rejected'] and report['operator_unchanged']
        and hold is not None and hold['verified'] is True
        and report['heartbeat_to_verified_s']<=.5 and report['explicit_revoke']['verified_stopped'] is True
        and report['after_expiry']['max_displacement_radians']>=3*2*math.pi/4096)
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps(report))
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
