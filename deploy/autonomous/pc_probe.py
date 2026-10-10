"""Finite PC-only CPU runtime probe. Never loads or unloads LM Studio models."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen


def post(base, path, value):
    with urlopen(Request(base + path, data=json.dumps(value).encode(),
                         headers={'Content-Type': 'application/json'}), timeout=25) as response:
        return json.load(response)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18097)
    args = parser.parse_args()
    base = f'http://127.0.0.1:{args.port}'
    # Fail before spawning if this port belongs to another process.
    import socket
    with socket.socket() as check:
        check.bind(('127.0.0.1', args.port))
    report = {'weight_sha256': digest(args.weights), 'runtime_sha256': digest(args.server),
              'threads': 2, 'context': 4096, 'gpu_layers': 0, 'samples': []}
    log_path = args.output.with_suffix('.log')
    command = [str(args.server), '-m', str(args.weights), '--host', '127.0.0.1', '--port', str(args.port),
               '--threads', '2', '--threads-batch', '2', '--ctx-size', '4096', '--parallel', '1',
               '--n-gpu-layers', '0', '--no-op-offload', '--cache-ram', '0',
               '--threads-http', '2', '--alias', 'reachy-shadow-fast-cpu']
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            end = time.monotonic() + 30
            while time.monotonic() < end:
                if process.poll() is not None:
                    raise RuntimeError('CPU server exited; inspect probe log')
                try:
                    with urlopen(base + '/health', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.1)
            else:
                raise TimeoutError('CPU server startup deadline')
            report['tokenizer'] = post(base, '/tokenize', {'content': 'Тест точного tokenizer.'})
            prompt = ('<|im_start|>system\nТы управляешь shadow компаньоном. Верни JSON a=wait и краткую why. '
                      'Нет задачи, микрофон выключен.<|im_end|>\n<|im_start|>user\n'
                      '{"mic":"disabled","candidates":[],"ready":[]}<|im_end|>\n'
                      '<|im_start|>assistant\n<think>\n\n</think>\n\n')
            schema = {'type': 'object', 'properties': {'a': {'const': 'wait'}, 'why': {'type': 'string', 'maxLength': 96}},
                      'required': ['a', 'why'], 'additionalProperties': False}
            for _ in range(3):
                started = time.monotonic()
                result = post(base, '/completion', {'prompt': prompt, 'n_predict': 96, 'temperature': 0,
                              'stop': ['<|im_end|>', '<|im_start|>'], 'json_schema': schema, 'cache_prompt': True})
                report['samples'].append({'elapsed_s': time.monotonic()-started, 'result': result})
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
            report['process_reaped'] = process.poll() is not None
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'process_reaped': report['process_reaped'],
                      'elapsed_s': [x['elapsed_s'] for x in report['samples']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
