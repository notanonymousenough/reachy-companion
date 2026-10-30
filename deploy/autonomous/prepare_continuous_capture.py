#!/usr/bin/env python3
"""Build A0 against installed 4e2d/S1, offline; never installs or opens audio."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    'agent.py': (
        '4e2dcafdde29ba667ae40c240723954d48b8462f9641e50ffb32e56fe0ce575a',
        'reachy-agent-4e2d-a0-continuous.patch',
        '52913ef59ff3719459c8eba94008c89123917c199db223dd524964993a317d2b',
        'de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b'),
    'capture_pump.py': (
        'b7b1ffa551d8b3ad4346cc2920f0e17d04e37c2300d8583abf336ea90fb9e5b0',
        'reachy-capture-b7b1-a0-continuous.patch',
        'f5f41c4b8a3435de137b1224202a1ded2dcb7c17ec157116d68f4b2d83b9bc08',
        '5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6'),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'deploy/autonomous'/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def candidate():
    # Reconstruct the witnessed baseline, not HEAD. The historical builders
    # verify every layer including original Git bytes, S1 and bound listening.
    _, agent = module('a0_bound_base', 'prepare_bound_listening.py').candidate()
    before = {'agent.py': agent,
              'capture_pump.py': (ROOT/'src/reachy_companion/capture_pump.py').read_bytes()}
    patcher = module('a0_exact_patch', 'prepare_content_stream.py')
    data = {}
    for name, (pre, patch_name, patch_sha, post) in PINS.items():
        patch = (ROOT/'deploy/patches'/patch_name).read_bytes()
        if digest(before[name]) != pre or digest(patch) != patch_sha:
            raise ValueError('Exact A0 source/patch mismatch')
        raw = patcher.apply_exact(before[name].decode(), patch.decode()).encode()
        if digest(raw) != post:
            raise ValueError('Exact A0 output mismatch')
        compile(raw, name, 'exec')
        data[name] = raw
    return before, data


def build(destination):
    before, data = candidate()
    manifest = dict(kind='A0-exact-4e2d-continuous-capture',
        preimages={name: digest(raw) for name, raw in before.items()},
        outputs={name: digest(raw) for name, raw in data.items()},
        patches={row[1]: row[2] for row in PINS.values()},
        required_unchanged=dict(
            barge_in='28831114f2cf0f60f47d3bdd77c4f8d120b6447101ff5adc56df46204eb247bf',
            microphone='d35ef6d3e0cc289e8043a0da68480ecd110ef3fff98afb81da0afad25e416129',
            motion_policy='d224385e999a0c6056db42e1fc3a3c90afaa2009336eaf1ef364037dc98a8466',
            config='c0b0e7a8470401a20b684ada3132784e0805333f9ab56c18b1f8d585d7eb3436',
            sound_monitor='89e7f782aade878f84fdb0760f95605d97d266c0a476bdb56a213b3d932d7c29',
            spoken_vision='486cfb8f23c9d9d5797910eab6ebf3143e64f1cfe4a686b4f50fe38db975a025'),
        installed_dependency_recheck_required=True,
        opt_in='conversation.capture_pump_enabled', default_enabled=False,
        pending_ttl_seconds=2, own_output='PCM drain with STT suppression and bounded echo tail',
        counters='os.read bytes/mono-S16_LE frames; monotonic software receipts per generation',
        hardware_time_verified=False, continuous_acceptance=False, aec_verified=False,
        barge_in=False, partial_stt=False, devices_modified=False, dependencies_added=False)
    destination.mkdir(mode=0o700)
    for name, raw in data.items():
        with (destination/name).open('xb') as file:
            file.write(raw)
    with (destination/'manifest.json').open('x') as file:
        file.write(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    print(json.dumps(build(parser.parse_args().destination), indent=2))
