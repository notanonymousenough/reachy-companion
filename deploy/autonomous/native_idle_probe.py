"""Finite robot-local real IPC ledger proof; no trajectory, pin-enable or audio."""
import argparse,json,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from reachy_companion.motion_proxy import MotionProxy
from reachy_companion.autonomous.native_config import load
from reachy_companion.autonomous.contracts import uid
from native_actor_probe import operator


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--service-config',type=Path,required=True);p.add_argument('--production-root',type=Path,required=True)
    p.add_argument('--hub-boot',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    profile=load(a.service_config);proxy=MotionProxy(True,profile['socket_path'],lambda:operator(a.production_root))
    end=time.monotonic()+30
    while True:
        state=proxy.status()
        if state.get('ready') and not state.get('leased'):break
        if time.monotonic()>end:raise RuntimeError('Idle owner readiness timeout')
        time.sleep(.05)
    op=operator(a.production_root)
    if not state['ready'] or state['leased'] or (state['binding'] is not None and state['binding'][0]!=a.hub_boot):raise RuntimeError('Existing idle sole-writer binding required')
    common=dict(agent_boot_id=op['agent_boot_id'],operator_epoch=op['microphone_epoch'],actor_boot_id=state['actor_boot_id'],session_id=state['session_id'],motor_epoch=state['policy']['epoch'])
    sequence=state['command_high_watermark'];initial=sequence;lease=None
    def call(kind,**extra):
        nonlocal sequence
        sequence+=1
        reply=proxy.handle(dict(command_id=uid(),hub_boot_id=a.hub_boot,path='/native/antenna',payload=dict(common,kind=kind,command_sequence=sequence,**extra)))
        if reply.get('accepted') is not True:raise RuntimeError('Real IPC command rejected')
        return reply['result']
    report=dict(mode='actual_robot_local_idle_ipc',accepted=False,common=common,hub_boot_id=a.hub_boot,heartbeats=0,initial_watermark=initial,trajectory_commands=0,audio_commands=0)
    began=time.monotonic()
    try:
        lease=call('arm',motor_enabled=True,quiet=False,privacy_all=False)['lease_id']
        for index in range(300):call('heartbeat',lease_id=lease,sequence=index);report['heartbeats']+=1;time.sleep(.03)
        stop=call('revoke',lease_id=lease);lease=None;after=proxy.status()
        report.update(elapsed_s=time.monotonic()-began,verified_stopped=stop['verified_stopped'],final_watermark=after['command_high_watermark'],ready=after['ready'],target_writes=after['target_writes'])
        report['accepted']=report['heartbeats']==300 and report['verified_stopped'] and report['ready'] and report['final_watermark']>=initial+301 and report['target_writes']==1
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)[:120]
    finally:
        if lease:
            try:report['failure_stop_known']=call('revoke',lease_id=lease)['verified_stopped']
            except Exception:report['failure_stop_known']=False
        with a.output.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(report),flush=True)
    if not report['accepted']:raise SystemExit(2)
if __name__=='__main__':main()
