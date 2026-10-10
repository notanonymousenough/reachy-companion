"""Finite real-model shadow acceptance; simulated state, no robot commands."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen
from pc_probe import digest
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.gateway import ModelBackend
from reachy_companion.autonomous.state import State
from reachy_companion.autonomous.gateway import Gateway
from reachy_companion.autonomous.runtime import Scheduler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('server', 'weights', 'main-weights', 'config', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--skip-main', action='store_true')
    parser.add_argument('--threads', type=int, choices=(2, 4, 8), default=2)
    parser.add_argument('--cache-ram-mb', type=int, choices=(0, 128), default=0)
    parser.add_argument('--period', type=float, default=1)
    parser.add_argument('--projection', choices=('full', 'task_only'), default='full')
    parser.add_argument('--decision-format', choices=('object','tuple'), default='object')
    args = parser.parse_args()
    import socket
    with socket.socket() as check:
        check.bind(('127.0.0.1', 18097))
    cfg = load(args.config)
    cfg['http_timeout_s'] = 12
    if not .5 <= args.period <= 5:
        parser.error('period must be between0.5 and5 seconds')
    cfg['period_s'] = args.period
    for role, weights in [('fast', args.weights), ('main', args.main_weights)]:
        model = cfg['models'][role]
        weight_hash = digest(weights)
        template_hash = hashlib.sha256(json.dumps([model['message_template'], model['assistant_prefix'], model['stop']]).encode()).hexdigest()
        model['audit'].update(verified=True, device='cpu_pc' if role=='fast' else 'gpu_pc',
            runtime_build=digest(args.server) if role=='fast' else 'LM Studio llama.cpp CUDA 2.55.0',
            weight_sha256=weight_hash, tokenizer_sha256=weight_hash, template_sha256=template_hash,
            runtime_context_tokens=4096 if role=='fast' else 32768)
    cfg['models']['fast'].update(id='reachy-shadow-fast-cpu', base_url='http://127.0.0.1:18097',
         completion_backend='llama_native', completion_path='/completion', tokenize_path='/tokenize', temperature=0,
         projection=args.projection, cache_ram_mb=args.cache_ram_mb,decision_format=args.decision_format)
    cfg['models']['main'].update(base_url='http://127.0.0.1:1234/v1', context_tokens=32768,
         admission_context_tokens=4096, tokenizer_backend='lmstudio_sdk', completion_backend='lmstudio_sdk')
    log_path = args.output.with_suffix('.log')
    report = {'mode': 'real_models_simulated_state', 'tokenizer_provenance': 'embedded in hashed GGUF; digest covers entire artifact',
              'models': cfg['models'], 'threads': args.threads, 'period_s':args.period, 'samples': []}
    command = [str(args.server), '-m', str(args.weights), '--host', '127.0.0.1', '--port', '18097',
               '--threads', str(args.threads), '--threads-batch', str(args.threads), '--ctx-size', '4096', '--parallel', '1',
               '--n-gpu-layers', '0', '--no-op-offload', '--cache-ram', str(args.cache_ram_mb), '--threads-http', '2',
               '--alias', 'reachy-shadow-fast-cpu']
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            deadline = time.monotonic()+30
            while time.monotonic()<deadline:
                if process.poll() is not None:
                    raise RuntimeError('CPU server exited')
                try:
                    with urlopen('http://127.0.0.1:18097/health', timeout=1): break
                except OSError: time.sleep(.1)
            else: raise TimeoutError('startup deadline')
            backend = ModelBackend(cfg)
            gateway = Gateway(backend)
            state = State(config=cfg)
            views = [('idle', state.snapshot(0))]
            state.ingest({'type':'utterance','text':'Коротко объясни, почему небо голубое.'}, 0)
            views.append(('new_turn', state.snapshot(0)))
            ref = next(iter(state.candidates))
            task = state.apply({'a':'think','why':'acceptance setup','start':{'type':'main','input_ref':ref}}, state.bind(0, 10), 0)
            views.append(('pending', state.snapshot(.1)))
            state.complete(task.task_id, task.attempt_id, task.authority, 'Молекулы воздуха сильнее рассеивают синий свет.', .2)
            views.append(('ready', state.snapshot(.3)))
            state.ingest({'type':'operator','muted':True}, .4)
            views.append(('muted', state.snapshot(.5)))
            for name, view in views:
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
            report['acceptance_passed'] = all(x['accepted'] for x in report['samples'])
            if not args.skip_main:
                started=time.monotonic()
                try:
                    result=gateway.generate('main','Коротко объясни, почему небо голубое.')
                    report['main']={'elapsed_s':time.monotonic()-started,**result}
                except Exception as exc:
                    report['main']={'elapsed_s':time.monotonic()-started,'error':repr(exc)}
            if report['acceptance_passed']:
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
                        result = gateway.generate('main', task.prompt)
                        report['mixed_main_s'] = time.monotonic()-started
                        return {**result, 'request_id': task.attempt_id}
                scheduler = Scheduler(cfg, LocalTransport())
                report['mixed_shadow'] = scheduler.run(12, [{'at_s':0,'type':'utterance','text':'Скажи одним предложением, почему небо голубое.'}])
                # No inference orphan: drain transport jobs before shutting down CPU runtime.
                for job in (scheduler.fast_job, scheduler.main_job):
                    if job:
                        try: job.future.result(timeout=cfg['http_timeout_s']+2)
                        except Exception as exc: report.setdefault('drain_errors', []).append(repr(exc))
                report['mixed_passed'] = (scheduler.state.counts['task_started']==1 and
                    scheduler.state.counts['simulated_speech']==1 and not gateway.health()['quarantined'])
                report['cadence_passed'] = (not scheduler.state.counts['tick_busy_gap'] and
                    not scheduler.state.counts['fast_failed'] and not scheduler.state.counts['fast_deadline_expired'])
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
            report['process_reaped']=process.poll() is not None
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(args.output),'acceptance_passed':report['acceptance_passed'],
                      'mixed_passed':report.get('mixed_passed'), 'samples':report['samples'],'main':report.get('main'),
                      'process_reaped':report['process_reaped']},ensure_ascii=False))
    if not report['acceptance_passed'] or not report.get('mixed_passed', False) or not report.get('cadence_passed', False):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
