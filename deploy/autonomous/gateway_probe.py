"""Finite isolated PC runtime + authenticated gateway, for hub shadow probes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen
from pc_probe import digest
from compute_probe import native_environment, main_identity, gpu_sample, placement, GPUHeadroom
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.gateway import create_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('server', 'weights', 'config', 'token-file', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--duration', type=int, choices=range(20, 121), default=60)
    parser.add_argument('--threads', type=int, choices=(2, 4, 8), default=4)
    parser.add_argument('--video-token-file',type=Path)
    parser.add_argument('--gpu-layers',type=int,choices=(0,8),default=0)
    parser.add_argument('--vendor-dir',type=Path)
    parser.add_argument('--gpu-index',type=int,choices=range(8),default=0)
    parser.add_argument('--gpu-reserve-mib',type=int,choices=range(256,2049),default=512)
    args = parser.parse_args()
    if bool(args.gpu_layers)!=bool(args.vendor_dir):parser.error('GPU probe requires installed vendor package')
    cfg = load(args.config)
    if bool(args.gpu_layers)!=(cfg['models']['fast'].get('execution_profile','cpu_baseline')=='gpu_probe'):
        parser.error('Execution profile must match isolated runtime')
    fast_url = urlsplit(cfg['models']['fast']['base_url'])
    if (cfg['gateway']['bind'] != '127.0.0.1' or fast_url.scheme != 'http' or fast_url.hostname != '127.0.0.1'
            or not fast_url.port or fast_url.path or cfg['models']['fast']['context_tokens'] != 4096):
        parser.error('probe requires isolated loopback endpoints')
    audit = cfg['models']['fast']['audit']
    if digest(args.weights) != audit['weight_sha256'] or digest(args.server) != audit['runtime_build']:
        raise ValueError('Fast runtime/artifact differs from accepted manifest')
    marker = args.output.parent / 'inference-quarantine.local.json'
    if marker.exists():
        raise RuntimeError('Previous unknown execution requires operator audit before another gateway')
    os.environ[cfg['gateway']['token_env']] = args.token_file.read_text().strip()
    if cfg.get('context',{}).get('video_url'):
        if args.video_token_file is None:parser.error('Video token file required for enabled producer')
        os.environ[cfg['context']['video_token_env']]=args.video_token_file.read_text().strip()
    import socket
    for port in (fast_url.port, cfg['gateway']['port']):
        with socket.socket() as check:
            check.bind(('127.0.0.1', port))
    command = [str(args.server), '-m', str(args.weights), '--host', '127.0.0.1', '--port', str(fast_url.port),
               '--threads', str(args.threads), '--threads-batch', str(args.threads), '--ctx-size', '4096', '--parallel', '1',
               '--n-gpu-layers', str(args.gpu_layers), '--cache-ram', str(cfg['models']['fast'].get('cache_ram_mb', 0)), '--threads-http', '2',
               '--alias', cfg['models']['fast']['id']]
    if args.gpu_layers:command.extend(['--batch-size','512','--ubatch-size','256','--verbosity','4','--fit','off'])
    else:command.append('--no-op-offload')
    environment=native_environment(args.server,args.vendor_dir)
    main_before=main_identity(cfg['models']['main'])
    gpu_before=gpu_sample(args.gpu_index) if args.gpu_layers else None
    if gpu_before:
        if gpu_before['free_mib']<args.gpu_reserve_mib+384:raise RuntimeError('Insufficient initial GPU headroom')
        environment['CUDA_VISIBLE_DEVICES']=gpu_before['uuid']
    report = {'actuators':'none', 'models':'real', 'duration_s':args.duration,
              'main_before':main_before,'gpu_before':gpu_before}
    with args.output.with_suffix('.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log,env=environment)
        api = monitor = None
        completed=False
        try:
            if args.gpu_layers:monitor=GPUHeadroom(process,args.gpu_index,args.gpu_reserve_mib,gpu_before)
            end = time.monotonic()+25
            while time.monotonic()<end:
                if process.poll() is not None: raise RuntimeError('Private runtime exited')
                try:
                    with urlopen(cfg['models']['fast']['base_url']+'/health',timeout=1): break
                except OSError: time.sleep(.1)
            else: raise TimeoutError('Private runtime startup deadline')
            if args.gpu_layers:
                report['placement']=placement(args.output.with_suffix('.log'),args.gpu_layers)
                if report['placement']['device']!=audit['device']:raise RuntimeError('Placement differs from accepted profile')
            api = create_server(cfg)
            thread = threading.Thread(target=api.serve_forever, daemon=True)
            thread.start()
            print(json.dumps({'gateway':'ready', 'duration_s':args.duration}), flush=True)
            end = time.monotonic()+args.duration
            while time.monotonic()<end:
                if process.poll() is not None:raise RuntimeError('Private runtime stopped during gateway probe')
                time.sleep(.1)
            completed=True
        finally:
            try:
                if api:
                    api.shutdown()
                    end = time.monotonic()+cfg['http_timeout_s']+2
                    while any(api.gateway.health()['busy'].values()) and time.monotonic()<end:
                        time.sleep(.1)
                    report['health'] = api.gateway.health()
                    if any(report['health']['busy'].values()) or report['health']['quarantined']:
                        marker.write_text(json.dumps(report['health']), encoding='utf-8')
                    api.server_close()
            except Exception as exc:
                report['cleanup_error']=type(exc).__name__
                try:
                    marker.write_text(json.dumps(dict(reason='gateway_cleanup_unknown',cleanup_error=report['cleanup_error'])),encoding='utf-8')
                except Exception as marker_error:report['quarantine_marker_error']=type(marker_error).__name__
            finally:
                if monitor:
                    monitor.close()
                    report['gpu_monitor']=dict(minimum_free_mib=monitor.minimum_free_mib,samples=monitor.samples,
                        reserve_mib=args.gpu_reserve_mib,abort_reason=monitor.abort_reason)
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
                report['process_reaped'] = process.poll() is not None
                try:
                    report['main_after']=main_identity(cfg['models']['main'])
                    report['main_preserved']=report['main_after']==main_before
                    if args.gpu_layers:report['gpu_after']=gpu_sample(args.gpu_index)
                except Exception as exc:
                    report['main_preserved']=False;report['post_audit_error']=type(exc).__name__
                report['accepted']=bool(completed and api and not report.get('cleanup_error') and report['process_reaped'] and report['main_preserved']
                    and not any(report.get('health',{}).get('busy',{}).values())
                    and not report.get('health',{}).get('quarantined') and not report.get('gpu_monitor',{}).get('abort_reason'))
                args.output.write_text(json.dumps(report,indent=2), encoding='utf-8')
                print(json.dumps(report), flush=True)
    if not report['accepted']:raise SystemExit(2)


if __name__ == '__main__':
    main()
