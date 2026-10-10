"""Finite inference-free hub probe: real PC models, synthetic shadow events only."""
import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.runtime import RemoteGateway, Scheduler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('config','token-file','production-root','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    args = parser.parse_args()
    cfg = load(args.config)
    if not .5 <= cfg['period_s'] <= 3:
        raise ValueError('Finite hub probe requires period between0.5 and3 seconds')
    os.environ[cfg['gateway']['token_env']] = args.token_file.read_text().strip()
    production = json.loads((args.production_root/'config.local.json').read_text())
    token = (args.production_root/'secrets/token').read_text().strip()
    opener = build_opener(ProxyHandler({}))
    def operator():
        request = Request(production['network']['hub_url']+'/control/status',
                          headers={'Authorization':'Bearer '+token})
        with opener.open(request,timeout=4) as response: return json.load(response)
    before = operator()
    if before['microphone_enabled'] or before['capture_active']:
        raise RuntimeError('This test requires existing physical operator mute; never changes it')
    gateway = RemoteGateway(cfg)
    scheduler = Scheduler(cfg,gateway)
    period = cfg['period_s']
    events = [{'at_s':0,'type':'utterance','text':'Одним предложением: почему небо голубое?'},
              {'at_s':.5,'type':'sensor','id':'fixture.light','summary':'synthetic update','ttl_ms':1000},
              {'at_s':.6,'type':'sensor','id':'fixture.light','summary':'unrelated synthetic update','ttl_ms':1000},
              {'at_s':4*period,'type':'operator','muted':True},
              {'at_s':5*period,'type':'utterance','text':'Synthetic request while shadow muted.'}]
    report = scheduler.run(10*period,events)
    for job in (scheduler.fast_job,scheduler.main_job):
        if job: job.future.result(timeout=cfg['http_timeout_s']+2)
    report.update(physical_operator_before=before,physical_operator_after=operator(),
                  gateway_after=gateway.call('/health'),
                  transport='authenticated PC loopback through bounded SSH forwards',
                  event_origin='synthetic fixtures; physical microphone never enabled')
    counts=report['counts']
    report['accepted']=(counts.get('task_started')==1 and counts.get('simulated_speech')==1 and
        not counts.get('fast_failed') and not counts.get('fast_deadline_expired') and
        not counts.get('tick_busy_gap') and counts.get('fast_requested',0)>=9 and
        not any(report['gateway_after']['busy'].values()) and not report['gateway_after']['quarantined'] and
        report['physical_operator_after']['microphone_enabled'] is False and
        report['physical_operator_after']['capture_active'] is False)
    with args.output.open('x',encoding='utf-8') as output:json.dump(report,output,ensure_ascii=False,indent=2)
    print(json.dumps({'accepted':report['accepted'],'counts':counts,'physical_mute_preserved':
                     not report['physical_operator_after']['microphone_enabled']},ensure_ascii=True))
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
