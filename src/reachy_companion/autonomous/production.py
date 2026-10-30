"""Deployment hooks for the single Scheduler in companion_session.

Use companion autonomous with the existing normal configuration. Model gateway
runs separately on the Mac; configure gateway.client_url on Hub, models.*.base_url
and tokenizer/audit settings on Mac, and the existing companion network endpoints
for remote STT/TTS. Nothing here starts models, devices or extra listeners.
"""
import os
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from urllib.parse import urlsplit
from .contracts import decode
from .durable import DurableStore, Delivery


def http_reader(settings, *, tool=False, updates=False):
    url=settings['url'];parts=urlsplit(url)
    if (parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password
            or parts.fragment or (parts.scheme=='http' and parts.hostname not in ('localhost','127.0.0.1','::1'))):
        raise ValueError('IO endpoint requires HTTPS or explicit localhost tunnel')
    opener=build_opener(ProxyHandler({}))
    def call(argument=None):
        import json
        token=os.environ.get(settings.get('token_env',''),'')
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        request=Request(url,headers=headers,data=json.dumps(argument).encode() if tool else None)
        with opener.open(request,timeout=settings.get('timeout_s',2)) as response:
            raw=response.read(8193)
        if len(raw)>8192:raise ValueError('IO response bound')
        value=decode(raw)
        # Sensor HTTP contract: availability, summary, age_ms, ttl_ms. Age is
        # increased by the full round trip by Services; no remote clock guessing.
        if not tool and not updates and (not isinstance(value,dict) or set(value)-{'availability','summary','age_ms','ttl_ms'} or not {'availability','ttl_ms'}<=set(value) or value.get('availability')=='available' and not {'summary','age_ms'}<=set(value)):
            raise ValueError('Sensor contract')
        if tool:
            if (not isinstance(value,dict) or value.get('request_id')!=argument['request_id']
                    or value.get('accepted') is not True or value.get('terminal') is not True or 'output' not in value):
                raise ValueError('Tool terminal receipt required; unknown completion is not success')
            return value['output']
        return value
    return call


def attach(scheduler, config_path):
    settings=scheduler.config.get('production',{})
    if not settings.get('state_path'):raise ValueError('production.state_path is required (private local durable SQLite)')
    if scheduler.config['models']['fast'].get('projection','full')!='full' or scheduler.config['models']['fast'].get('decision_format','object')!='object':
        raise ValueError('Production requires full object decision protocol')
    sensors={}
    for name,item in settings.get('sensors',{}).items():
        sensors[name]=(http_reader(item),item.get('period_s',.5),item['source_id'])
    tools={name:http_reader(item,tool=True) for name,item in settings.get('tools',{}).items()}
    deliveries={name:Delivery(name,item) for name,item in settings.get('delivery',{}).items() if item.get('enabled') and scheduler.config['export_enabled']}
    store=DurableStore(Path(config_path).resolve().parent/settings['state_path'],settings.get('outbox_cap',10000))
    try:
        scheduler.enable_production(store,sensors,deliveries,tools)
        if settings.get('updates',{}).get('enabled'):
            scheduler.services.update_reader=http_reader(settings['updates'],updates=True)
    except BaseException:store.close();raise


def main():
    """Offline version inspection/rollback hook; no service or device commands."""
    import argparse
    import json
    parser=argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('action',choices=('inspect','rollback'))
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--target',type=int)
    parser.add_argument('--expected',type=int)
    parser.add_argument('--reason')
    args=parser.parse_args()
    if not args.state.is_file():parser.error('Existing state database required')
    store=DurableStore(args.state)
    try:
        if args.action=='rollback':
            if args.target is None or args.expected is None or not args.reason:parser.error('Rollback requires target, expected and reason')
            store.rollback(args.target,args.expected,args.reason)
        revision,body=store.current()
        print(json.dumps(dict(revision=revision,state=body),ensure_ascii=False))
    finally:store.close()


if __name__=='__main__':main()
