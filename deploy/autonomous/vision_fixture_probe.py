"""One synthetic image on the existing main; empirical budget, no camera admission."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import threading
import time
from urllib.parse import urlsplit
import zlib

from compute_probe import gpu_sample, main_identity
from reachy_companion.autonomous.config import load


def fixture_png():
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    rows = bytearray()
    for y in range(256):
        rows.append(0)
        for x in range(256):
            if (x-64)**2+(y-128)**2 <= 40**2: color = (0, 0, 255)
            elif 160 <= x < 224 and 96 <= y < 160: color = (255, 0, 0)
            else: color = (255, 255, 255)
            rows.extend(color)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', 256, 256, 8, 2, 0, 0, 0))
            +chunk(b'IDAT', zlib.compress(rows))+chunk(b'IEND', b''))


def run_fixture(args, report):
    model = load(args.config)['models']['main']
    before = main_identity(model)
    gpu = gpu_sample(0)
    if gpu['free_mib'] < 1024: raise RuntimeError('Insufficient initial fixture headroom')
    image = fixture_png()
    report.update(mode='synthetic_vision_empirical_fixture_only', main_before=before,
                  image_sha256=hashlib.sha256(image).hexdigest(), image_bytes=len(image),
                  raster=[256, 256], image_requests=0, model_load_calls=0, physical_commands=0,
                  private_frames=0, effective_image_token_cap_verified=False,
                  production_camera_admitted=False, gpu_reserve_mib=512,
                  minimum_free_mib=gpu['free_mib'], gpu_samples=0, accepted=False)
    import lmstudio
    done = threading.Event()
    outcome = {}
    started = time.monotonic()
    with lmstudio.Client(urlsplit(model['base_url']).netloc) as client:
        handles = [h for h in client.llm.list_loaded() if h.get_info().identifier == model['id']]
        if len(handles) != 1 or handles[0].get_info().instance_reference != before['instance_reference']:
            raise RuntimeError('Exact existing main handle required')
        handle = handles[0]
        if not handle.get_info().vision: raise RuntimeError('Vision unavailable')
        # Synthetic data only: SDK server-side upload cache retention is unknown.
        prepared = client.files.prepare_image(image)
        chat = lmstudio.Chat()
        chat.add_user_message('Identify the color and shape on the left and on the right. '
                              'Return only JSON with left_color,left_shape,right_color,right_shape. /no_think',
                              images=[prepared])
        schema = dict(type='object', additionalProperties=False,
                      properties={key: dict(type='string', enum=values) for key, values in {
                          'left_color':['red','blue','green','white'], 'right_color':['red','blue','green','white'],
                          'left_shape':['circle','square','triangle'], 'right_shape':['circle','square','triangle']}.items()},
                      required=['left_color','left_shape','right_color','right_shape'])
        stream = handle.respond_stream(chat, response_format=schema,
                                       config={'maxTokens':96, 'temperature':0,
                                               'contextOverflowPolicy':'stopAtLimit'})
        report['image_requests'] = 1
        def consume():
            try:
                for _ in stream: pass
                outcome['result'] = stream.result()
            except Exception as exc: outcome['error'] = type(exc).__name__
            finally: done.set()
        worker = threading.Thread(target=consume, daemon=True)
        worker.start()
        abort = None
        while not done.wait(.2):
            try:
                sample = gpu_sample(0)
                report['gpu_samples'] += 1
                report['minimum_free_mib'] = min(report['minimum_free_mib'], sample['free_mib'])
                if sample['uuid'] != gpu['uuid'] or sample['free_mib'] < 512: abort = 'gpu_headroom'
            except Exception: abort = 'gpu_unknown'
            if time.monotonic()-started >= 20: abort = 'fixture_deadline'
            if abort:
                stream.cancel()  # Only this owned prediction; never unload/kill main.
                break
        worker.join(5)
        final_gpu = gpu_sample(0)
        report['minimum_free_mib'] = min(report['minimum_free_mib'], final_gpu['free_mib'])
        if final_gpu['uuid'] != gpu['uuid'] or final_gpu['free_mib'] < 512: abort = 'gpu_headroom'
        report.update(abort_reason=abort, prediction_drained=not worker.is_alive(),
                      elapsed_s=time.monotonic()-started, error=outcome.get('error'))
        result = outcome.get('result')
        if result is not None:
            report['answer'] = result.parsed
            report['stats'] = repr(result.stats)[:2048]
            # Prediction LlmInfo has no instance reference in SDK1.5. The
            # request uses the exact loaded handle; recheck its identity below.
            report['same_handle_instance'] = handle.get_info().instance_reference == before['instance_reference']
            report['finished'] = result.stats.stop_reason in ('eosFound', 'stopStringFound')
            report['output_tokens'] = result.stats.predicted_tokens_count
            report['prompt_tokens'] = result.stats.prompt_tokens_count
            report['accepted'] = (not abort and report['finished'] and report['same_handle_instance']
                                  and 0 < report['prompt_tokens'] <= 256 and 0 < report['output_tokens'] <= 96
                                  and report['answer'] == dict(left_color='blue', left_shape='circle',
                                                              right_color='red', right_shape='square'))
    report['main_after'] = main_identity(model)
    report['main_preserved'] = before == report['main_after']
    report['accepted'] = report['accepted'] and report['main_preserved'] and report['prediction_drained']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    report = dict(accepted=False, image_requests=0, production_camera_admitted=False)
    try: run_fixture(args, report)
    except Exception as exc:
        report.update(accepted=False, error=type(exc).__name__)
        try:
            report['main_after'] = main_identity(load(args.config)['models']['main'])
            report['main_preserved'] = report['main_after'] == report.get('main_before')
        except Exception: report['main_preserved'] = False
    with args.output.open('x') as output: json.dump(report, output, indent=2)
    print(json.dumps(report))
    if not report['accepted']: raise SystemExit(2)


if __name__ == '__main__': main()
