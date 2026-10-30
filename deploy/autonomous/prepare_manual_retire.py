#!/usr/bin/env python3
"""Build the R8 Agent-only overlay on exact installed A1; offline, no install."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEFORE = 'de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b'
AFTER = '001be4ec456141b41d0146b49d06e737ced5383dcba2201c288fa3ed35b667f6'
PATCH = 'reachy-agent-de362b-r8-manual-retire.patch'
PATCH_SHA = 'f42426d28c94b592ab6213b85d89450b03c810215b61c290e964d823932c8c0e'
PUMP = '5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'deploy/autonomous'/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def candidate():
    _, a1 = module('r8_a1_base', 'prepare_continuous_capture.py').candidate()
    original = a1['agent.py']
    patch = (ROOT/'deploy/patches'/PATCH).read_bytes()
    if digest(original) != BEFORE or digest(a1['capture_pump.py']) != PUMP or digest(patch) != PATCH_SHA:
        raise ValueError('Exact R8 A1 source/pump/patch required')
    output = module('r8_exact_patch', 'prepare_content_stream.py').apply_exact(
        original.decode(), patch.decode()).encode()
    if digest(output) != AFTER:
        raise ValueError('Exact R8 output required')
    compile(output, 'agent-R8.py', 'exec')
    return original, output


def build(destination):
    original, output = candidate()
    manifest = dict(kind='R8-exact-A1-legacy-manual-retire', before=BEFORE, after=AFTER,
        patch={PATCH: PATCH_SHA}, required_unchanged={'capture_pump.py': PUMP},
        dependency_manifest='A0 required_unchanged pins still apply; recheck installed imports',
        epochs_changed=False, protocol_changed=False, default_enabled=False,
        devices_modified=False, hardware_accepted=False, physical_rearm=False,
        payload=['agent.py'], rollback='agent-A1-preimage.py',
        note='Retire under microphone/policy locks; close outside; restoration respects OFF/privacy/quiet/stop')
    destination.mkdir(mode=0o700)
    for name, raw in (('agent.py', output), ('agent-A1-preimage.py', original)):
        with (destination/name).open('xb') as file:
            file.write(raw)
    with (destination/'manifest.json').open('x') as file:
        file.write(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    print(json.dumps(build(parser.parse_args().destination), indent=2))
