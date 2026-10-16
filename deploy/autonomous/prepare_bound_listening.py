"""Prepare an exact cf50 overlay for bound pause/resume; never deploy it."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEFORE = 'cf50c54680d8e30fb97090e80d0e687a9dad903159f464d2211414aefcaca069'
AFTER = '4e2dcafdde29ba667ae40c240723954d48b8462f9641e50ffb32e56fe0ce575a'
PATCH = '66203d5521303dcd7da9804ec12f0fdfb3e6a53bf676da75006e5519fc57c07b'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'deploy/autonomous'/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def candidate():
    _, files = module('bound_listening_base', 'prepare_capture_pump.py').candidate()
    original = files['agent.py']
    patch = (ROOT/'deploy/patches/reachy-agent-cf50-bound-listening.patch').read_bytes()
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    if digest(original) != BEFORE or digest(patch) != PATCH:
        raise ValueError('Exact bound-listening source and patch required')
    output = module('bound_listening_patch', 'prepare_content_stream.py').apply_exact(
        original.decode(), patch.decode()).encode()
    if digest(output) != AFTER:
        raise ValueError('Exact bound-listening output required')
    compile(output, 'agent-bound-listening.py', 'exec')
    return original, output


def build(destination):
    _, output = candidate()
    destination.mkdir(mode=0o700)
    with (destination/'agent.py').open('xb') as file:
        file.write(output)
    manifest = dict(kind='bound-listening-proposal', before=BEFORE, after=AFTER,
        patch=PATCH, devices_modified=False, hardware_accepted=False,
        payload='existing operator_binding shape; expected owner None only matches paired manual owners None; legacy empty manual payload retained',
        mutations='listening Event only, under microphone and policy locks',
        epochs_changed=False, service_added=False)
    with (destination/'manifest.json').open('x') as file:
        file.write(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    print(json.dumps(build(parser.parse_args().destination), indent=2))
