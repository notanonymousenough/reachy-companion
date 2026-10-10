"""Read installed mmproj GGUF geometry; no inference, tensor load or image upload."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from compute_probe import gpu_sample, main_identity, native_environment
from reachy_companion.autonomous.config import load

FORMATS = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i', 6: 'f', 7: '?', 10: 'Q', 11: 'q', 12: 'd'}


def geometry(path):
    with path.open('rb') as source:
        def scalar(fmt):
            size = struct.calcsize('<'+fmt)
            raw = source.read(size)
            if len(raw) != size: raise ValueError('Truncated GGUF metadata')
            return struct.unpack('<'+fmt, raw)[0]
        def string(keep):
            count = scalar('Q')
            if count > 1048576: raise ValueError('GGUF string bound')
            if keep:
                raw = source.read(count)
                if len(raw) != count: raise ValueError('Truncated GGUF string')
                return raw.decode('utf-8')
            source.seek(count, 1)
        def value(kind, keep):
            if kind in FORMATS: return scalar(FORMATS[kind])
            if kind == 8: return string(keep)
            if kind == 9:
                element, count = scalar('I'), scalar('Q')
                if count > 1048576 or element == 9: raise ValueError('GGUF array bound')
                if keep and count <= 64: return [value(element, True) for _ in range(count)]
                if element in FORMATS: source.seek(count*struct.calcsize('<'+FORMATS[element]), 1)
                elif element == 8:
                    for _ in range(count): string(False)
                else: raise ValueError('Unknown GGUF array type')
                return None
            raise ValueError('Unknown GGUF metadata type')
        if source.read(4) != b'GGUF' or scalar('I') != 3: raise ValueError('Expected GGUF3')
        tensors, count = scalar('Q'), scalar('Q')
        if count > 16384: raise ValueError('GGUF key bound')
        fields = {}
        for _ in range(count):
            key = string(True)
            if len(key) > 256: raise ValueError('GGUF key length')
            keep = key.startswith('clip.') or key == 'general.architecture'
            result = value(scalar('I'), keep)
            if keep: fields[key] = result
            if source.tell() > min(path.stat().st_size, 67108864): raise ValueError('GGUF metadata extent')
        size = source.tell()
        source.seek(0)
        return dict(fields=fields, metadata_bytes=size, tensors=tensors,
                    metadata_sha256=hashlib.sha256(source.read(size)).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--mmproj', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--server', type=Path)
    parser.add_argument('--vendor', type=Path)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    model = load(args.config)['models']['main']
    before = main_identity(model)
    report = geometry(args.mmproj)
    report.update(mode='installed_vision_geometry_read_only', main_before=before,
                  gpu=gpu_sample(0), image_requests=0, model_load_calls=0)
    import lmstudio
    import lmstudio.sync_api as sdk
    from urllib.parse import urlsplit
    original = sdk.parse_server_config
    captured = []
    def capture(config):
        fields = config.get('fields', [])
        for field in fields:
            key = field['key']
            if any(word in key.lower() for word in ('image', 'vision')):
                value = field.get('value')
                captured.append({'key': key, 'value': value if type(value) in (int, float, bool) else 'non_numeric'})
        report['raw_load_field_names'] = [field['key'] for field in fields]
        return original(config)
    sdk.parse_server_config = capture
    try:
        with lmstudio.Client(urlsplit(model['base_url']).netloc) as client:
            handles = [handle for handle in client.llm.list_loaded() if handle.get_info().identifier == model['id']]
            if len(handles) != 1: raise RuntimeError('Existing single main required')
            handles[0].get_load_config()
    finally: sdk.parse_server_config = original
    report['raw_image_load_fields'] = captured
    if args.server:
        import subprocess
        version = subprocess.run([str(args.server), '--version'], env=native_environment(args.server, args.vendor),
                                 capture_output=True, text=True, timeout=5, check=True)
        report['native_version'] = (version.stdout+version.stderr)[-2048:]
    report['main_after'] = main_identity(model)
    report['main_preserved'] = report['main_after'] == before
    with args.output.open('x') as output: json.dump(report, output, indent=2)
    print(json.dumps(report))
    if not report['main_preserved']: raise SystemExit(2)


if __name__ == '__main__': main()
