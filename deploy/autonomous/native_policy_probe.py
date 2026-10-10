"""Finite real IPC replay and quiet withdrawal. Idle lease; no trajectory/audio."""
import argparse,json,sys,time
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from reachy_companion.motion_proxy import MotionProxy
from reachy_companion.config import Config
from reachy_companion.autonomous.native_config import load
from reachy_companion.autonomous.contracts import uid
from native_actor_probe import operator


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('service-config','production-root','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    profile=load(a.service_config);cfg=Config(a.production_root/'config.local.json')
    proxy=MotionProxy(True,profile['socket_path'],lambda:operator(a.production_root));end=time.monotonic()+30
    while True:
        state=proxy.status()
        if state.get('ready'):break
        if time.monotonic()>end:raise RuntimeError('Managed owner startup timeout')
        time.sleep(.05)
    before=operator(a.production_root);boot=uid();sequence=state['command_high_watermark'];initial=sequence
    common=dict(agent_boot_id=before['agent_boot_id'],operator_epoch=before['microphone_epoch'],actor_boot_id=state['actor_boot_id'],session_id=state['session_id'],motor_epoch=state['policy']['epoch'])
    def envelope(payload):return dict(command_id=uid(),hub_boot_id=boot,path='/native/antenna',payload=payload)
    report=dict(mode='actual_idle_replay_quiet_withdrawal',accepted=False,initial_watermark=initial,operator_before=before,trajectory_commands=0,audio_commands=0)
    replays=[]
    for stale in (True,False):
        payload=dict(common,kind='arm',command_sequence=1,motor_enabled=True,quiet=False,privacy_all=False)
        if stale:payload.update(actor_boot_id=uid(),session_id=uid())
        reply=proxy.handle(envelope(payload));replays.append(reply.get('accepted') is False)
    report['replay_rejections']=replays
    payload=dict(common,kind='arm',command_sequence=initial+1,motor_enabled=True,quiet=False,privacy_all=False)
    arm=proxy.handle(envelope(payload))
    if arm.get('accepted') is not True:raise RuntimeError('Fresh issued idle lease failed')
    lease=arm['result']['lease_id']
    request=Request(f"http://127.0.0.1:{profile['port']}/motion-policy",data=json.dumps(dict(motor_enabled=False,quiet=True,privacy_all=False)).encode(),headers={'Authorization':'Bearer '+cfg.token,'Content-Type':'application/json'})
    try:
        with build_opener(ProxyHandler({})).open(request,timeout=1) as response:report['policy']=json.load(response)
        reply=proxy.handle(envelope(dict(common,kind='revoke',command_sequence=0,lease_id=lease)))
        report['verified_revoke_after_policy_withdrawal']=reply.get('accepted') is True and reply['result']['verified_stopped'] is True
        after=proxy.status();report['ready_after']=after['ready'];report['final_watermark']=after['command_high_watermark'];report['target_writes']=after['target_writes']
        report['operator_after']=operator(a.production_root)
        report['accepted']=all(replays) and initial>256 and report['verified_revoke_after_policy_withdrawal'] and not report['ready_after'] and report['final_watermark']==initial+1 and report['target_writes']==1 and before==report['operator_after']
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)[:120]
    finally:
        try:proxy.handle(envelope(dict(common,kind='revoke',command_sequence=0,lease_id=lease)))
        except Exception:pass
        with a.output.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(report),flush=True)
    if not report['accepted']:raise SystemExit(2)
if __name__=='__main__':main()
