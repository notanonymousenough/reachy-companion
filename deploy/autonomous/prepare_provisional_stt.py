#!/usr/bin/env python3
"""Source-only S2 exact overlays; keeps published S1 and model/runtime intact."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = '2865db30e92fcb069c241c34bae4419ad65ed594'
RECOGNITION_BASE = 'b79a709bb3167c0fba380aafa687c846db592c8ec0ecdeec88742179ec548344'
RECOGNITION_INSTALLED = '6211a01e8d4ecf515636d4407856fddcf6e5deec4ddbd5639ae977770111f15f'
PINS = {'reachy-recognition-b79-installed-6211.patch': '93ae5b8ebaea2b807ce973e1d1338bb05e76754220ffc9262af999569319ce22', 'reachy-recognition-6211-provisional.patch': '72f5146f63f2b85a00a138a1b7c5b96eda1116fe4a89c665235b0e654f683093', 'reachy-worker-bbdb-provisional.patch': '12e1b957d7c205dd7aedd50b9589a2365217891f60446295e31e3ba5c69f2de8', 'reachy-agent-cf50-provisional.patch': 'c7f022c643473f543cd070a1a806244949ffe29e017b4b9e20b74fe11a804b0f', 'reachy-capture-b7b1-provisional.patch': '4fec624069e3afa3d6ed7d3d2f2979fa89f4a8cfdbc99aa764470e6113901ea7'}
OUTPUTS = {'recognition': '4bc6bd6e786e58328f56f825e6ce3307c8e3c320878b3d7ea882d67bc594cebb', 'voice': 'd55a06c805aa0e3e4ce6b1b38da92e2d9a934a0f99b8c6ada0830d80a26cf914', 'agent': '0702628df0014672bc80445052c8ea00cd9f2922c84dc7177e1db443d1f9a034', 'capture': '9b9f9dabc29e24571177998cbe3433517fcaa3c57aafd2a54f5058c47de3eec2'}
HELPERS = {'provisional_stt.py': '17af5dadaad84cc8c3e30a32d8efde7974f60be429aabfd864345a16ee1e7d6e', 'owned_http.py': '2864cdae7268e0b5e2d28c9c04ded63655cb3d6049de4d044a134917d5e18a1c'}
TRANSPORT_SOURCE = 'a4aa26d375b46cfd0348f6cb42df6adb1f82a0f1b4252afb11df571f4edc539d'


def digest(raw): return hashlib.sha256(raw).hexdigest()


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'deploy/autonomous'/filename)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def transport_derivation():
    source = (ROOT/'src/reachy_companion/token_stream.py').read_bytes()
    if digest(source) != TRANSPORT_SOURCE: raise ValueError('Exact transport derivation source required')
    text = source.decode(); tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'owned_response')
    derived = ''.join(text.splitlines(True)[node.lineno-2:node.end_lineno])
    derived = derived.replace('def owned_response(request,deadline,submitted=None):',
                              'def owned_response(request,deadline,target,submitted=None):')
    derived = derived.replace('need(request.full_url in ENDPOINTS)\n    endpoint,addresses=ENDPOINTS[request.full_url]',
                              'need(request.full_url == target[0])\n    endpoint,addresses=target[1:]')
    helper = ast.parse((ROOT/'src/reachy_companion/owned_http.py').read_bytes())
    actual = next(n for n in helper.body if isinstance(n, ast.FunctionDef) and n.name == 'owned_response')
    if ast.dump(actual, include_attributes=False) != ast.dump(ast.parse(derived).body[0], include_attributes=False):
        raise ValueError('Owned transport watchdog derivation drift')


def candidate():
    patcher = module('s2_patch', 'prepare_content_stream.py')
    s1 = module('s2_s1', 'prepare_capture_pump.py')
    _, robot = s1.candidate()
    with tempfile.TemporaryDirectory() as directory:
        destination = Path(directory)/'bundle'; patcher.build(destination)
        voice = (destination/'voice.py').read_bytes()
    recognition = subprocess.check_output(['git', 'show', BASE+':src/reachy_companion/recognition.py'], cwd=ROOT)
    if digest(recognition) != RECOGNITION_BASE: raise ValueError('Exact public recognizer base required')
    def apply(raw, name, expected):
        patch = (ROOT/'deploy/patches'/name).read_bytes()
        if digest(patch) != PINS[name]: raise ValueError('Exact provisional patch required')
        result = patcher.apply_exact(raw.decode(), patch.decode()).encode()
        if digest(result) != expected: raise ValueError('Exact provisional overlay output required')
        return result
    recognition = apply(recognition, 'reachy-recognition-b79-installed-6211.patch', RECOGNITION_INSTALLED)
    before = dict(recognition=recognition, voice=voice, agent=robot['agent.py'], capture=robot['capture_pump.py'])
    results = {}
    for role, name, key, patch_name in (
            ('PC', 'recognition.py', 'recognition', 'reachy-recognition-6211-provisional.patch'),
            ('PC', 'voice.py', 'voice', 'reachy-worker-bbdb-provisional.patch'),
            ('Robot', 'agent.py', 'agent', 'reachy-agent-cf50-provisional.patch'),
            ('Robot', 'capture_pump.py', 'capture', 'reachy-capture-b7b1-provisional.patch')):
        results[role+'/'+name] = apply(before[key], patch_name, OUTPUTS[key])
    transport_derivation()
    for name, pin in HELPERS.items():
        raw = (ROOT/'src/reachy_companion'/name).read_bytes()
        if digest(raw) != pin: raise ValueError('Exact provisional helper required')
        for role in ('Robot', 'PC'): results[role+'/'+name] = raw
    for name, raw in results.items(): compile(raw, name, 'exec')
    return before, results


def build(destination):
    before, data = candidate()
    manifest = dict(kind='exact-S1-provisional-STT-S2',
        preimages={key: digest(value) for key, value in before.items()},
        outputs={key: digest(value) for key, value in data.items()},
        required_unchanged=dict(Robot_barge='28831114f2cf0f60f47d3bdd77c4f8d120b6447101ff5adc56df46204eb247bf',
            PC_brains='020e435e37602271d2d40160b055650f781b60a8ee9fc601e3b28d82444bdae6',
            PC_token_stream=TRANSPORT_SOURCE),
        opt_in='conversation.provisional_stt_enabled', default_enabled=False,
        loaded_backend_required='faster_whisper', native_online=False, partial_acceptance=False,
        devices_modified=False, model_or_backend_changed=False, final_dispatch='unchanged S1 VAD claim')
    destination.mkdir(mode=0o700)
    for role in ('PC', 'Robot'): (destination/role).mkdir(mode=0o700)
    for name, raw in data.items():
        with (destination/name).open('xb') as file: file.write(raw)
    with (destination/'manifest.json').open('x') as file: file.write(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('destination', type=Path)
    print(json.dumps(build(parser.parse_args().destination), indent=2))
