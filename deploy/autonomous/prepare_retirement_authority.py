#!/usr/bin/env python3
"""Build the R11 Agent-only retirement authority overlay on exact R8, offline."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEFORE = '001be4ec456141b41d0146b49d06e737ced5383dcba2201c288fa3ed35b667f6'
AFTER = 'ec3a1ad998ec9e9d05d835deda19934f6930b52aba03f374e790bae4128531b9'
PATCH = 'reachy-agent-001be4-r11-retirement-authority.patch'
PATCH_SHA = 'f6068ac993207055ed2a1a8cac96e8cd4f800de73b645f5ebd5f18789aeea17d'
PUMP = '5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'deploy/autonomous'/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def candidate():
    _, original = module('r11_r8_base', 'prepare_manual_retire.py').candidate()
    _, a1 = module('r11_a1_pins', 'prepare_continuous_capture.py').candidate()
    patch = (ROOT/'deploy/patches'/PATCH).read_bytes()
    if digest(original) != BEFORE or digest(a1['capture_pump.py']) != PUMP or digest(patch) != PATCH_SHA:
        raise ValueError('Exact R11 R8 source/pump/patch required')
    output = module('r11_exact_patch', 'prepare_content_stream.py').apply_exact(
        original.decode(), patch.decode()).encode()
    if digest(output) != AFTER:
        raise ValueError('Exact R11 output required')
    compile(output, 'agent-R11.py', 'exec')
    return original, output


def build(destination):
    original, output = candidate()
    manifest = dict(kind='R11-exact-R8-retirement-authority', before=BEFORE, after=AFTER,
        patch={PATCH: PATCH_SHA}, required_unchanged={'capture_pump.py': PUMP},
        dependency_manifest='All A0 required_unchanged pins apply; recheck installed imports',
        epochs_changed=True, protocol_changed=False, devices_modified=False,
        hardware_accepted=False, physical_rearm=False, payload=['agent.py'], rollback='agent-R8-preimage.py',
        note='First retirement persists mic epoch, preserves enabled/owner; old bound requests must refresh; '
             'private mutation receipt fences legacy manual restoration/output; never restore persisted ON')
    destination.mkdir(mode=0o700)
    for name, raw in (('agent.py', output), ('agent-R8-preimage.py', original)):
        with (destination/name).open('xb') as file:
            file.write(raw)
    with (destination/'manifest.json').open('x') as file:
        file.write(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    print(json.dumps(build(parser.parse_args().destination), indent=2))
