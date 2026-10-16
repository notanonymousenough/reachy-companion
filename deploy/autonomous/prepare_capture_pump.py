#!/usr/bin/env python3
"""Build opt-in S1 against installed Agent c2fc and barge-in 3761; no devices."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
AGENT_BEFORE = 'c2fcb832501c55dd56a86abd7b87c71b05c013f968a2482dbfc1a27d3283f2f5'
AGENT_AFTER = 'cf50c54680d8e30fb97090e80d0e687a9dad903159f464d2211414aefcaca069'
BARGE_BEFORE = '3761dffb2daeee06bb3402618d98a0e8f68d4d67f3b5e77b5fb9a03e5143047f'
BARGE_AFTER = '28831114f2cf0f60f47d3bdd77c4f8d120b6447101ff5adc56df46204eb247bf'
HELPER = 'b7b1ffa551d8b3ad4346cc2920f0e17d04e37c2300d8583abf336ea90fb9e5b0'
PATCHES = {'reachy-agent-c2fc-capture-pump.patch': '557e3fd29ab0c62c4865ef295704625bdcf77242a6b4369dc09f77e624b28a95',
           'reachy-barge-3761-capture-permit.patch': 'd6e402ceb103768758cd27ea9e18cc65edf902cb4d059ed4298eb9620187671d'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'deploy/autonomous'/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def candidate():
    timing = module('capture_timing_base', 'prepare_agent_stream_timing.py')
    patcher = module('capture_exact_patch', 'prepare_content_stream.py')
    _, agent = timing.candidate()
    barge = subprocess.check_output(['git', 'show', timing.BASE+':src/reachy_companion/barge_in.py'], cwd=ROOT)
    before = {'agent.py': agent, 'barge_in.py': barge}
    data = {}
    for name, raw, pre, post, patch_name in (
            ('agent.py', agent, AGENT_BEFORE, AGENT_AFTER, 'reachy-agent-c2fc-capture-pump.patch'),
            ('barge_in.py', barge, BARGE_BEFORE, BARGE_AFTER, 'reachy-barge-3761-capture-permit.patch')):
        patch = (ROOT/'deploy/patches'/patch_name).read_bytes()
        if digest(raw) != pre or digest(patch) != PATCHES[patch_name]:
            raise ValueError('Exact capture preimage/patch mismatch')
        output = patcher.apply_exact(raw.decode(), patch.decode()).encode()
        if digest(output) != post:
            raise ValueError('Exact capture output mismatch')
        data[name] = output
    helper = (ROOT/'src/reachy_companion/capture_pump.py').read_bytes()
    if digest(helper) != HELPER:
        raise ValueError('Exact capture helper mismatch')
    data['capture_pump.py'] = helper
    for name, raw in data.items():
        compile(raw, name, 'exec')
    return before, data


def build(destination):
    before, data = candidate()
    manifest = dict(kind='exact-c2fc-capture-pump-S1',
        preimages={name: digest(raw) for name, raw in before.items()},
        outputs={name: digest(raw) for name, raw in data.items()},
        required_unchanged=dict(microphone='d35ef6d3e0cc289e8043a0da68480ecd110ef3fff98afb81da0afad25e416129',
            motion_policy='d224385e999a0c6056db42e1fc3a3c90afaa2009336eaf1ef364037dc98a8466',
            config='c0b0e7a8470401a20b684ada3132784e0805333f9ab56c18b1f8d585d7eb3436',
            sound_monitor='89e7f782aade878f84fdb0760f95605d97d266c0a476bdb56a213b3d932d7c29',
            spoken_vision='486cfb8f23c9d9d5797910eab6ebf3143e64f1cfe4a686b4f50fe38db975a025'),
        opt_in='conversation.capture_pump_enabled', default_enabled=False,
        hardware_time_verified=False, continuous_acceptance=False, partial_stt=False,
        devices_modified=False, dependencies_added=False)
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
