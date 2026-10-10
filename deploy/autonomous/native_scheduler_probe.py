"""Finite real PC inference -> existing scheduler -> actual guarded antenna adapter."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.runtime import Scheduler,RemoteGateway
from reachy_companion.autonomous.motion_adapter import MotionAdapter
from reachy_companion.config import Config
from reachy_companion.hub import Hub


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('config','token-file','companion-config','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    cfg=load(args.config)
    if not cfg['motion']['enabled']:raise RuntimeError('Native scheduler explicit opt-in')
    os.environ[cfg['gateway']['token_env']]=args.token_file.read_text().strip()
    hub_config=Config(args.companion_config);hub=Hub(hub_config)
    physical_url=hub_config['network']['agent_url']
    def operator():
        current=hub_config.data['network']['agent_url'];hub_config.data['network']['agent_url']=physical_url
        try:
            value=hub.agent('/status')
            return {key:value[key] for key in ('agent_boot_id','microphone_epoch','microphone_enabled','capture_active','phase')}
        finally:hub_config.data['network']['agent_url']=current
    before=operator()
    if before['microphone_enabled'] is not False or before['capture_active'] is not False or before['phase']!='paused':
        raise RuntimeError('Actual operator mute required')
    hub_config.data['guarded_motion']['enabled']=True
    hub_config.data['network']['agent_url']=cfg['motion']['agent_url']
    hub_config.data['timeouts']['http']=1
    deadline=time.monotonic()+30
    while True:
        try:
            value=hub.agent('/status')
            if value['motion_actor']['ready']:break
        except Exception:pass
        if time.monotonic()>deadline:raise RuntimeError('Managed actor readiness timeout')
        time.sleep(.05)
    model_inputs=[]
    class AuditedGateway(RemoteGateway):
        def fast(self,request_id,view):
            result=super().fast(request_id,view)
            model_inputs.append(dict(op=view['op'],output=result['output'],usage=result.get('usage')))
            del model_inputs[:-32]
            return result
    gateway=AuditedGateway(cfg)
    adapter=MotionAdapter(hub,cooldown_s=cfg['motion']['cooldown_s'],heartbeat_s=cfg['motion']['heartbeat_s'])
    scheduler=Scheduler(cfg,gateway,adapter)
    scheduler.ingest(dict(type='sensor',id='fixture.motion_invitation',ttl_ms=60000,
        summary='Synthetic finite acceptance invitation: choose an attentive antenna17 gesture when motion_allowed. No speech. No private sensor input.'))
    report=dict(mode='actual_inference_scheduler_native_owner',accepted=False,operator_before=before,
                event_origin='synthetic invitation; actual PC inference; actual bounded antenna17 output',audio_commands=0,
                private_image_uploads=0)
    try:
        end=time.monotonic()+25
        while time.monotonic()<end and adapter.completed<3 and not adapter.failed:
            scheduler.advance();time.sleep(.01)
        report['motion_receipts']=list(adapter.receipts)
        report['model_inputs']=model_inputs
        report['counts']=dict(scheduler.state.counts);report['last_model_choices']=list(scheduler.state.previous)
        if adapter.completed!=3 or adapter.failed:raise RuntimeError('Three actual model motion proposals did not pass acceptance')
        # Keep one idle lease through >256 real heartbeat commands. No trajectory
        # is admitted here; this measures steady service/ledger, never movement.
        state=hub.agent('/status')['motion_actor'];common=MotionAdapter.binding(hub.agent('/status'))
        sequence=state['command_high_watermark']
        def call(kind,**extra):
            nonlocal sequence
            sequence+=1
            return hub.native_motion(dict(common,kind=kind,command_sequence=sequence,**extra))
        lease=call('arm',motor_enabled=True,quiet=False,privacy_all=False)['lease_id']
        began=time.monotonic()
        for index in range(300):
            call('heartbeat',lease_id=lease,sequence=index);time.sleep(.02)
        stopped=call('revoke',lease_id=lease)
        steady=hub.agent('/status')['motion_actor']
        report['steady_heartbeat']=dict(count=300,elapsed_s=time.monotonic()-began,high_watermark=steady['command_high_watermark'],
            verified_stopped=stopped['verified_stopped'],target_writes=steady['target_writes'],ready=steady['ready'])
        report['policy_withdrawal']=hub.agent('/motion-policy',dict(motor_enabled=False,quiet=True,privacy_all=False))
        time.sleep(.2)
        try:
            call('heartbeat',lease_id=lease,sequence=301)
            report['withdrawn_heartbeat_rejected']=False
        except Exception:report['withdrawn_heartbeat_rejected']=True
        report['accepted']=(len(report['motion_receipts'])==3 and all(item['accepted'] for item in report['motion_receipts'])
            and report['steady_heartbeat']['verified_stopped'] and report['steady_heartbeat']['ready']
            and report['withdrawn_heartbeat_rejected'])
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)[:160]
    finally:
        adapter.close()
        scheduler.ingest(dict(type='operator',muted=True))
        for job in (scheduler.fast_job,scheduler.main_job,scheduler.actor_job,scheduler.motion_job):
            if job:
                try:job.future.result(timeout=cfg['http_timeout_s']+2)
                except Exception:pass
        report['motion_receipts']=list(adapter.receipts)
        report['operator_after']=operator();report['operator_unchanged']=before==report['operator_after']
        report['accepted']=report['accepted'] and report['operator_unchanged']
        report['gateway_after']=gateway.call('/health')
        report['accepted']=report['accepted'] and not report['gateway_after']['quarantined'] and not any(report['gateway_after']['busy'].values())
        with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps({key:value for key,value in report.items() if key not in ('gateway_after','motion_receipts','model_inputs')},ensure_ascii=False),flush=True)
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
