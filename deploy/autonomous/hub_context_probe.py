"""Finite real L0/L1/context integration; fixture memory, actual camera pixels."""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.request import Request, build_opener, ProxyHandler
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.runtime import RemoteGateway,Scheduler
from reachy_companion.autonomous.contracts import uid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('config','token-file','production-root','output'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--fixture-id',default='fixture-color')
    args=parser.parse_args();cfg=load(args.config)
    os.environ[cfg['gateway']['token_env']]=args.token_file.read_text().strip()
    production=json.loads((args.production_root/'config.local.json').read_text())
    token=(args.production_root/'secrets/token').read_text().strip();opener=build_opener(ProxyHandler({}))
    def operator():
        with opener.open(Request(production['network']['hub_url']+'/control/status',headers={'Authorization':'Bearer '+token}),timeout=3) as response:value=json.load(response)
        return {key:value.get(key) for key in ('microphone_enabled','capture_active','phase')}
    before=operator()
    if before['microphone_enabled'] is not False or before['capture_active'] is not False:raise RuntimeError('Requires existing physical mute')
    gateway=RemoteGateway(cfg);scheduler=Scheduler(cfg,gateway)
    started=time.monotonic();stage=0;samples=[];last_tick=0;privacy_start=None
    while time.monotonic()-started<45:
        now=time.monotonic();scheduler.advance(now)
        if scheduler.state.counts['fast_requested']!=last_tick:
            last_tick=scheduler.state.counts['fast_requested'];view=scheduler.state.snapshot(now)
            samples.append(dict(at_s=now-started,memory=view['memory'],sensors=view['sensors'],privacy_all=view['op']['privacy_all']))
        memory=[item for item in scheduler.state.memory_items.values() if item['id']==args.fixture_id]
        if stage==0 and memory and scheduler.context_job is not None and now-started>3:
            scheduler.ingest(dict(type='utterance',text='Какой любимый цвет указан именно в синтетическом fixture? Одно предложение.'),now);stage=1
        elif stage==1 and scheduler.state.counts['simulated_speech']==1:
            print(json.dumps(dict(milestone='first_commit')),flush=True);stage=2
        elif stage==2 and memory and memory[0]['version']==1:
            scheduler.ingest(dict(type='utterance',text='После correction какой любимый цвет указан именно в синтетическом fixture? Одно предложение.'),now);stage=3
        elif stage==3 and scheduler.state.counts['simulated_speech']==2:
            print(json.dumps(dict(milestone='second_commit')),flush=True);stage=4
        elif stage==4 and not memory:
            scheduler.ingest(dict(type='operator',muted=True,privacy_all=True),now);privacy_start=now;stage=5
        elif stage==5 and now-privacy_start>4:
            scheduler.ingest(dict(type='operator',muted=False,privacy_all=False),now);stage=6
        elif stage==6 and now-privacy_start>8:break
        time.sleep(.01)
    scheduler.ingest(dict(type='operator',muted=True,privacy_all=True))
    for job in (scheduler.context_job,scheduler.fast_job,scheduler.main_job):
        if job:
            try:job.future.result(timeout=cfg['http_timeout_s']+2)
            except Exception:pass
    # Deliver the final owner epoch after all earlier context requests have drained.
    closed=gateway.context(uid(),'',True,scheduler.state.authority)
    if (closed['compute_boot_id']!=gateway.boot_id or closed['output']['memory']['items']
            or any(sensor['state']!='disabled' for sensor in closed['output']['sensors'])):
        raise RuntimeError('Final private context did not clear PC caches')
    after=operator();counts=dict(scheduler.state.counts);speeches=[x['text'] for x in scheduler.state.ledger if x['kind']=='simulated_speech']
    latest_samples=[x for x in samples if any('source_id' in sensor for sensor in x['sensors'])]
    private_samples=[x for x in samples if x['privacy_all']]
    report=dict(mode='real_models_and_camera_fixture_memory_canonical_shadow',counts=counts,stage=stage,
                snapshots=samples,ledger=list(scheduler.state.ledger),physical_operator_before=before,physical_operator_after=after,
                elapsed_s=time.monotonic()-started,gateway_after=gateway.call('/health'),physical_commands=0)
    report['accepted']=(stage==6 and counts.get('simulated_speech')==2 and len(latest_samples)>=2 and private_samples
        and all(not x['memory'] and all(s['state']=='disabled' for s in x['sensors']) for x in private_samples)
        and not counts.get('tick_busy_gap') and before==after and any('син' in text.lower() for text in speeches[:1])
        and any('зел' in text.lower() for text in speeches[1:]) and not scheduler.state.memory_items)
    with args.output.open('x',encoding='utf-8') as out:json.dump(report,out,ensure_ascii=False,indent=2)
    print(json.dumps(dict(accepted=bool(report['accepted']),stage=stage,counts=counts,camera_snapshots=len(latest_samples),elapsed_s=report['elapsed_s'])),flush=True)
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
