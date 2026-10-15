"""Finite real-model shadow acceptance; simulated state, no robot commands."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen
from pc_probe import digest
from compute_probe import native_environment,gpu_sample,placement,GPUHeadroom
from reachy_companion.autonomous.config import load
from frozen_main import FrozenModelBackend as ModelBackend,main_identity,verify_sdk
from smoke_execution import ExecutionLease,execution_scopes
from reachy_companion.autonomous.state import State
from reachy_companion.autonomous.gateway import Gateway
from reachy_companion.autonomous.runtime import Scheduler
from smoke_contract import (MAIN_INPUT,read_audit,verify_audit,main_request_identity,
    fingerprint,idle_health,accepted,effective_config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('server', 'weights', 'main-weights', 'config', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--audit-file',type=Path,required=True)
    parser.add_argument('--audit-sha256',required=True)
    parser.add_argument('--skip-main', action='store_true')
    parser.add_argument('--threads', type=int, choices=(2, 4, 8), default=2)
    parser.add_argument('--cache-ram-mb', type=int, choices=(0, 128), default=0)
    parser.add_argument('--period', type=float, default=1)
    parser.add_argument('--projection', choices=('full', 'task_only'), default='full')
    parser.add_argument('--decision-format', choices=('object','tuple'), default='object')
    parser.add_argument('--gpu-layers',type=int,choices=(0,8,16,32),default=0)
    parser.add_argument('--vendor-dir',type=Path)
    parser.add_argument('--gpu-index',type=int,default=0)
    parser.add_argument('--gpu-reserve-mib',type=int,default=512)
    args = parser.parse_args()
    if not 0<=args.gpu_index<=7 or not 256<=args.gpu_reserve_mib<=2048:parser.error('GPU probe bounds')
    if bool(args.gpu_layers)!=bool(args.vendor_dir):parser.error('GPU offload requires installed vendor package, CPU baseline omits it')
    marker=args.output.parent/'inference-quarantine.local.json'
    if marker.exists():raise RuntimeError('Previous unknown execution requires independent operator audit')
    audit=read_audit(args.audit_file,args.audit_sha256)
    if not .5 <= args.period <= 5:
        parser.error('period must be between0.5 and5 seconds')
    cfg=effective_config(load(args.config),args)
    if (cfg['actuators']!='simulated' or any(cfg.get(key,{}).get('enabled',False)
            for key in ('context','motion','speech','workflows'))):
        raise ValueError('PC-only smoke requires simulated actors and disabled context/physical adapters')
    verify_sdk(audit.get('sdk'))
    lease=ExecutionLease(execution_scopes(cfg,audit['main_identity'])).acquire()
    try:return run_guarded(args,cfg,audit,lease)
    finally:
        if not lease.closed:lease.finish(known=not lease.producer_started)


def run_guarded(args,cfg,audit,lease):
    marker=args.output.parent/'inference-quarantine.local.json'
    main_before=main_identity(cfg['models']['main'],audit['main_identity'],audit['sdk'])
    gpu_before=gpu_sample(args.gpu_index)
    environment=native_environment(args.server,args.vendor_dir)
    if args.gpu_layers:environment['CUDA_VISIBLE_DEVICES']=gpu_before['uuid']
    runtime_components={}
    if args.gpu_layers:
        for directory,names in [(args.server.parent,('ggml-cuda.dll','llama-server-impl.dll','llama.dll')),
                                (args.vendor_dir,('cudart64_12.dll','cublas64_12.dll','cublasLt64_12.dll'))]:
            for name in names:runtime_components[name]=digest(directory/name)
    files=audit.get('artifacts',{}).get('main_runtime_files')
    if type(files) is not dict or not files:raise ValueError('Frozen main runtime file audit required')
    artifacts=dict(fast_server_sha256=digest(args.server),fast_weights_sha256=digest(args.weights),
        main_weights_sha256=digest(args.main_weights),runtime_components=runtime_components,
        main_runtime_files={path:digest(Path(path)) for path in files})
    audit_identity=verify_audit(audit,cfg,args,artifacts,main_before,gpu_before)
    import socket
    with socket.socket() as check:check.bind(('127.0.0.1',18097))
    log_path = args.output.with_suffix('.log')
    report = {'mode': 'real_models_simulated_state', 'tokenizer_provenance': 'embedded in hashed GGUF; digest covers entire artifact',
              'models': cfg['models'], 'threads': args.threads, 'period_s':args.period, 'samples': [],
              'gpu_layers':args.gpu_layers,'main_before':main_before,'gpu_before':gpu_before,'runtime_components':runtime_components,
              'audit_identity':{**audit_identity,'file_sha256':args.audit_sha256},'audit_matched':True,
              'acceptance_passed':False,'accepted':False}
    main_request=main_request_identity(cfg,MAIN_INPUT)
    command = [str(args.server), '-m', str(args.weights), '--host', '127.0.0.1', '--port', '18097',
               '--threads', str(args.threads), '--threads-batch', str(args.threads), '--ctx-size', '4096', '--parallel', '1',
               '--n-gpu-layers', str(args.gpu_layers), '--cache-ram', str(args.cache_ram_mb), '--threads-http', '2',
               '--alias', cfg['models']['fast']['id']]
    if not args.gpu_layers:command.append('--no-op-offload')
    else:command.extend(['--batch-size','512','--ubatch-size','256','--verbosity','4','--fit','off'])
    if args.output.exists():raise FileExistsError('Fresh output receipt required')
    with log_path.open('x', encoding='utf-8') as log:
        lease.producer_started=True # Popen failure does not prove that no child was started
        process = subprocess.Popen(command, stdout=log, stderr=log,env=environment)
        report['owned_fast_pid']=process.pid
        monitor=gateway=scheduler=None
        try:
            monitor=GPUHeadroom(process,args.gpu_index,args.gpu_reserve_mib,gpu_before)
            deadline = time.monotonic()+30
            while time.monotonic()<deadline:
                if process.poll() is not None:
                    raise RuntimeError('CPU server exited')
                try:
                    with urlopen('http://127.0.0.1:18097/health', timeout=1): break
                except OSError: time.sleep(.1)
            else: raise TimeoutError('startup deadline')
            receipt=placement(log_path,args.gpu_layers);report['placement']=receipt
            if fingerprint(receipt)!=fingerprint(audit['fast_placement']):
                raise RuntimeError('Fresh placement differs from independent frozen audit')
            report['placement_matched']=True
            backend = ModelBackend(cfg,main_binding=audit['main_identity'],sdk_audit=audit['sdk'])
            gateway = Gateway(backend)
            state = State(config=cfg)
            views = [('idle', state.snapshot(0))]
            state.ingest({'type':'utterance','text':MAIN_INPUT}, 0)
            views.append(('new_turn', state.snapshot(0)))
            ref = next(iter(state.candidates))
            task = state.apply({'a':'think','why':'acceptance setup','start':{'type':'main','input_ref':ref}}, state.bind(0, 10), 0)
            views.append(('pending', state.snapshot(.1)))
            state.complete(task.task_id, task.attempt_id, task.authority, 'Молекулы воздуха сильнее рассеивают синий свет.', .2)
            views.append(('ready', state.snapshot(.3)))
            state.ingest({'type':'operator','muted':True}, .4)
            views.append(('muted', state.snapshot(.5)))
            for name, view in views:
                if monitor and monitor.abort_reason:break
                started=time.monotonic()
                try:
                    result=gateway.generate('fast', view)
                    report['samples'].append({'case':name,'elapsed_s':time.monotonic()-started,**result})
                except Exception as exc:
                    report['samples'].append({'case':name,'elapsed_s':time.monotonic()-started,'error':repr(exc),
                                             'transport_status':getattr(exc.__cause__,'code',None)})
            expected = {'idle': lambda x: x.get('a')=='wait',
                        'new_turn': lambda x: x.get('start')=={'type':'main','input_ref':ref},
                        'pending': lambda x: not x.get('start') and not x.get('commit'),
                        'ready': lambda x: x.get('commit')==task.task_id,
                        'muted': lambda x: x.get('a')=='wait' and not x.get('start') and not x.get('commit')}
            for sample in report['samples']:
                sample['accepted'] = expected[sample['case']](sample.get('output', {})) and 'error' not in sample
            report['acceptance_passed'] = len(report['samples'])==len(views) and all(x['accepted'] for x in report['samples'])
            if not args.skip_main and not (monitor and monitor.abort_reason):
                started=time.monotonic()
                try:
                    if main_request_identity(cfg,MAIN_INPUT)!=main_request:raise RuntimeError('Main request identity changed')
                    result=gateway.generate('main',MAIN_INPUT)
                    report['main']={'elapsed_s':time.monotonic()-started,'request_identity':main_request,**result}
                    report['main_passed']=isinstance(result.get('output'),str) and bool(result['output'].strip())
                except Exception as exc:
                    report['main']={'elapsed_s':time.monotonic()-started,'error':repr(exc)}
            if report['acceptance_passed'] and report.get('main_passed'):
                class LocalTransport:
                    boot_id = gateway.boot_id
                    def fast(self, request_id, view):
                        started = time.monotonic()
                        result = gateway.generate('fast', view)
                        report.setdefault('mixed_fast', []).append({'elapsed_s':time.monotonic()-started,
                                                                  'a':result['output']['a'], 'usage':result['usage']})
                        return {**result, 'request_id': request_id}
                    def main(self, task):
                        started = time.monotonic()
                        if main_request_identity(cfg,task.prompt)!=main_request:raise RuntimeError('Baseline/mixed request mismatch')
                        result = gateway.generate('main', task.prompt)
                        report['mixed_main_s'] = time.monotonic()-started
                        report['mixed_main_request_identity']=main_request
                        report['main_prompt_matched']=True
                        return {**result, 'request_id': task.attempt_id}
                scheduler = Scheduler(cfg, LocalTransport())
                report['mixed_shadow'] = scheduler.run(12, [{'at_s':0,'type':'utterance','text':MAIN_INPUT}])
                report['mixed_passed'] = (scheduler.state.counts['task_started']==1 and
                    scheduler.state.counts['simulated_speech']==1 and not gateway.health()['quarantined'])
                report['cadence_passed'] = (not scheduler.state.counts['tick_busy_gap'] and
                    not scheduler.state.counts['fast_failed'] and not scheduler.state.counts['fast_deadline_expired'])
        except Exception as exc:report['error']=type(exc).__name__
        finally:
            if scheduler:
                try:scheduler.close()
                except Exception as exc:report.setdefault('cleanup_errors',[]).append(type(exc).__name__)
                for role in ('fast','main'):
                    job=getattr(scheduler,role+'_job')
                    if job:
                        try:job.future.result(timeout=cfg['http_timeout_s']+2)
                        except Exception as exc:report.setdefault('drain_errors',[]).append(type(exc).__name__)
                report['jobs_final_busy']={role:bool(getattr(scheduler,role+'_job') and
                    not getattr(scheduler,role+'_job').future.done()) for role in ('fast','main')}
            if monitor:
                try:monitor.close()
                except Exception as exc:report.setdefault('cleanup_errors',[]).append(type(exc).__name__)
                report['gpu_monitor']=dict(minimum_free_mib=monitor.minimum_free_mib,samples=monitor.samples,
                    reserve_mib=args.gpu_reserve_mib,abort_reason=monitor.abort_reason,thread_busy=monitor.thread.is_alive())
            try:
                if process.poll() is None:process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            except Exception as exc:report.setdefault('cleanup_errors',[]).append(type(exc).__name__)
            report['process_returncode']=process.poll();report['process_reaped']=report['process_returncode'] is not None
            try:
                report['main_after']=main_identity(cfg['models']['main'],audit['main_identity'],audit['sdk'])
                report['main_preserved']=report['main_after']==main_before
                verify_audit(audit,cfg,args,artifacts,report['main_after'],gpu_before)
                report['gpu_after']=gpu_sample(args.gpu_index)
                if (report['gpu_after']['uuid']!=gpu_before['uuid'] or report['gpu_after']['total_mib']!=gpu_before['total_mib']
                        or report['gpu_after']['free_mib']<args.gpu_reserve_mib):raise RuntimeError('Final GPU audit changed')
            except Exception as exc:
                report['main_preserved']=False;report['post_audit_error']=type(exc).__name__
            try:report['gateway_final']=gateway.health() if gateway else None
            except Exception as exc:report.setdefault('cleanup_errors',[]).append(type(exc).__name__)
            if ((gateway and not idle_health(report.get('gateway_final'))) or not report['process_reaped']
                    or any(report.get('jobs_final_busy',{}).values())):
                try:
                    with marker.open('x',encoding='utf-8') as handle:
                        json.dump(dict(reason='execution_unknown',health=report.get('gateway_final')),handle)
                except Exception as exc:report.setdefault('cleanup_errors',[]).append(type(exc).__name__)
            known=(idle_health(report.get('gateway_final')) and report['process_reaped']
                and report.get('main_preserved') is True and not any(report.get('jobs_final_busy',{}).values())
                and not report.get('drain_errors') and not report.get('cleanup_errors'))
            try:lease.finish(known=known)
            except Exception as exc:report.setdefault('cleanup_errors',[]).append(type(exc).__name__)
            report['execution_guard']=lease.status()
            report['accepted']=accepted(report)
            with args.output.open('x',encoding='utf-8') as handle:json.dump(report,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'output':str(args.output),'acceptance_passed':report['acceptance_passed'],
                      'mixed_passed':report.get('mixed_passed'), 'samples':report['samples'],'main':report.get('main'),
                      'process_reaped':report['process_reaped'],'accepted':report['accepted'],
                      'gateway_final':report.get('gateway_final'),'jobs_final_busy':report.get('jobs_final_busy')},ensure_ascii=False))
    if not report['accepted']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
