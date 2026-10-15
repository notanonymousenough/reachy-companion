"""Frozen independent audit and receipt rules for the finite PC-only smoke."""
from datetime import datetime,timezone
import copy
import hashlib
import json
import re
import time
from reachy_companion.autonomous.contracts import decode
from reachy_companion.autonomous.gateway import MAIN_SYSTEM

FAST_WEIGHT_SHA256='37ae482d336108d23516fa35e8e0c4126688d81018b87178a18d752a1357814f'
MAIN_INPUT='Скажи одним предложением, почему небо голубое.'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read_audit(path,expected_sha256):
    raw=path.read_bytes()
    if (len(raw)>1048576 or type(expected_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',expected_sha256)
            or hashlib.sha256(raw).hexdigest()!=expected_sha256):
        raise ValueError('Frozen independent audit hash mismatch')
    return decode(raw)


def template_hash(model):
    return hashlib.sha256(json.dumps([model['message_template'],model['assistant_prefix'],model['stop']]).encode()).hexdigest()


def knobs(args):
    return {key:getattr(args,key) for key in ('threads','cache_ram_mb','period','projection',
        'decision_format','gpu_layers','gpu_index','gpu_reserve_mib')}


def effective_config(config,args):
    """Offline profile projection, preserving all independently supplied audits."""
    cfg=copy.deepcopy(config);cfg.update(http_timeout_s=12,period_s=args.period)
    cfg['models']['fast'].update(id='reachy-shadow-fast-pc' if args.gpu_layers else 'reachy-shadow-fast-cpu',
        base_url='http://127.0.0.1:18097',completion_backend='llama_native',completion_path='/completion',
        tokenize_path='/tokenize',temperature=0,projection=args.projection,cache_ram_mb=args.cache_ram_mb,
        decision_format=args.decision_format,execution_profile='gpu_probe' if args.gpu_layers else 'cpu_baseline')
    cfg['models']['main'].update(base_url='http://127.0.0.1:1234/v1',context_tokens=32768,
        admission_context_tokens=4096,tokenizer_backend='lmstudio_sdk',completion_backend='lmstudio_sdk')
    return cfg


def verify_audit(audit,cfg,args,artifacts,main_before,gpu_before,*,now=None):
    """Match independently frozen evidence, never set an audit flag ourselves."""
    now=time.time() if now is None else now
    if (type(audit) is not dict or audit.get('kind')!='live-smoke-audit-1'
            or type(audit.get('audit_id')) is not str or not 1<=len(audit['audit_id'])<=128):
        raise ValueError('Independent frozen smoke audit required')
    stamps=[]
    for key in ('collected_at_utc','expires_at_utc'):
        stamp=datetime.fromisoformat(audit[key].replace('Z','+00:00'))
        if stamp.tzinfo is None or stamp.utcoffset()!=timezone.utc.utcoffset(stamp):
            raise ValueError('UTC audit timestamps required')
        stamps.append(stamp.timestamp())
    if not (0<stamps[1]-stamps[0]<=3600 and stamps[0]<=now<stamps[1]):
        raise ValueError('Fresh bounded audit evidence required')
    if (audit.get('config_sha256')!=fingerprint(cfg) or fingerprint(audit.get('knobs'))!=fingerprint(knobs(args))
            or fingerprint(audit.get('artifacts'))!=fingerprint(artifacts)
            or fingerprint(audit.get('main_identity'))!=fingerprint(main_before)):
        raise ValueError('Frozen config/artifact/load/instance identity changed')
    files=artifacts.get('main_runtime_files')
    hashes=[artifacts.get(key) for key in ('fast_server_sha256','fast_weights_sha256','main_weights_sha256')]
    if (type(files) is not dict or not files or any(type(path) is not str or not path for path in files)
            or any(type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value)
                for value in [*hashes,*files.values(),*artifacts.get('runtime_components',{}).values()])):
        raise ValueError('Independently audited exact runtime/artifact files required')
    main_model=cfg['models']['main']
    if (main_before.get('id')!=main_model['id'] or main_before.get('context_tokens')!=main_model['context_tokens']
            or type(main_before.get('instance_reference')) is not str or not main_before['instance_reference']
            or type(main_before.get('load_config')) is not str or not main_before['load_config']):
        raise ValueError('Fresh already-loaded main identity/context required')
    for role,weight in (('fast',artifacts['fast_weights_sha256']),('main',artifacts['main_weights_sha256'])):
        model=cfg['models'][role];record=model['audit']
        if (record.get('verified') is not True or record.get('weight_sha256')!=weight
                or record.get('tokenizer_sha256')!=weight or record.get('template_sha256')!=template_hash(model)
                or type(record.get('runtime_context_tokens')) is not int
                or record['runtime_context_tokens']!=model['context_tokens'] or not record.get('runtime_build')
                or record.get('device') not in ('cpu_pc','gpu_pc','hybrid_pc')):
            raise ValueError('Independently verified model/runtime/template/context audit required')
    fast=cfg['models']['fast']['audit'];main=cfg['models']['main']['audit']
    if (artifacts['fast_weights_sha256']!=FAST_WEIGHT_SHA256
            or fast['runtime_build']!=artifacts['fast_server_sha256']
            or main['runtime_build']!=audit.get('main_runtime_build')):
        raise ValueError('Audited 0.8B weight or runtime identity mismatch')
    expected=audit.get('fast_placement')
    if (type(expected) is not dict or expected.get('device')!=fast['device']
            or (not args.gpu_layers and fingerprint(expected)!=fingerprint(dict(device='cpu_pc',offloaded_layers=0,total_layers=None)))
            or (args.gpu_layers and (type(expected.get('offloaded_layers')) is not int
                or type(expected.get('total_layers')) is not int
                or not 0<expected['offloaded_layers']<=expected['total_layers']))):
        raise ValueError('Frozen placement receipt required')
    gpu=audit.get('gpu')
    if (type(gpu) is not dict or gpu.get('uuid')!=gpu_before['uuid']
            or gpu.get('total_mib')!=gpu_before['total_mib'] or gpu.get('reserve_mib')!=args.gpu_reserve_mib
            or type(gpu.get('minimum_start_free_mib')) is not int
            or gpu['minimum_start_free_mib']<args.gpu_reserve_mib+384
            or gpu_before['free_mib']<gpu['minimum_start_free_mib']):
        raise ValueError('Frozen GPU identity and fresh headroom evidence required')
    return dict(audit_id=audit['audit_id'],collected_at_utc=audit['collected_at_utc'],
        expires_at_utc=audit['expires_at_utc'],config_sha256=audit['config_sha256'])


def main_request_identity(cfg,text):
    if text!=MAIN_INPUT:raise ValueError('Baseline and mixed must use the identical main input')
    model=cfg['models']['main']
    prompt=''.join(model['message_template'].format(role=role,content=content)
        for role,content in (('system',MAIN_SYSTEM),('user',text)))+model['assistant_prefix']
    return fingerprint(dict(prompt=prompt,model=model))


def idle_health(health):
    return (type(health) is dict and type(health.get('busy')) is dict
        and set(health['busy'])=={'fast','main'} and all(value is False for value in health['busy'].values())
        and type(health.get('quarantined')) is list and health['quarantined']==[])


def accepted(report):
    return (all(report.get(key) is True for key in ('audit_matched','placement_matched','acceptance_passed',
        'main_passed','mixed_passed','cadence_passed','main_preserved','process_reaped','main_prompt_matched'))
        and idle_health(report.get('gateway_final')) and not report.get('drain_errors')
        and type(report.get('jobs_final_busy')) is dict and set(report['jobs_final_busy'])=={'fast','main'}
        and all(value is False for value in report['jobs_final_busy'].values())
        and not report.get('error') and not report.get('cleanup_errors')
        and report.get('gpu_monitor',{}).get('thread_busy') is False
        and report['gpu_monitor'].get('abort_reason') is None)
