"""Finite isolated PC CPU runtime + authenticated gateway, for hub shadow probes."""
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
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.gateway import create_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('server', 'weights', 'config', 'token-file', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--duration', type=int, choices=range(20, 121), default=60)
    parser.add_argument('--threads', type=int, choices=(2, 4, 8), default=4)
    parser.add_argument('--video-token-file',type=Path)
    args = parser.parse_args()
    cfg = load(args.config)
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
               '--n-gpu-layers', '0', '--no-op-offload', '--cache-ram', str(cfg['models']['fast'].get('cache_ram_mb', 0)), '--threads-http', '2',
               '--alias', cfg['models']['fast']['id']]
    report = {'actuators':'none', 'models':'real', 'duration_s':args.duration}
    with args.output.with_suffix('.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        api = None
        try:
            end = time.monotonic()+25
            while time.monotonic()<end:
                if process.poll() is not None: raise RuntimeError('CPU runtime exited')
                try:
                    with urlopen(cfg['models']['fast']['base_url']+'/health',timeout=1): break
                except OSError: time.sleep(.1)
            else: raise TimeoutError('CPU startup deadline')
            api = create_server(cfg)
            thread = threading.Thread(target=api.serve_forever, daemon=True)
            thread.start()
            print(json.dumps({'gateway':'ready', 'duration_s':args.duration}), flush=True)
            end = time.monotonic()+args.duration
            while time.monotonic()<end: time.sleep(.1)
        finally:
            if api:
                api.shutdown()
                end = time.monotonic()+cfg['http_timeout_s']+2
                while any(api.gateway.health()['busy'].values()) and time.monotonic()<end:
                    time.sleep(.1)
                report['health'] = api.gateway.health()
                if any(report['health']['busy'].values()) or report['health']['quarantined']:
                    marker.write_text(json.dumps(report['health']), encoding='utf-8')
                api.server_close()
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            report['process_reaped'] = process.poll() is not None
            args.output.write_text(json.dumps(report,indent=2), encoding='utf-8')
            print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
