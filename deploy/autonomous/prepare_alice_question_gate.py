"""Exact existing raw-worker opt-in short-question overlay; source only."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '2865db30e92fcb069c241c34bae4419ad65ed594'
SOURCES = {
    'voice.py': ('92cf69096fd6f08551a13a9c44d85fbbfc0470ca2f17315616691044018ab865', '003306823660cd11ba5b3fcfa041d000a6a574a89857bd2d38c5c1d664b45fad', '19ae5a78b14a9519779f2246f8e7fdf1b0b1ef58a4a9b9b667fa2b596f73e4d8'),
    'config.py': ('c0b0e7a8470401a20b684ada3132784e0805333f9ab56c18b1f8d585d7eb3436', 'e7d3de62f3e098c4f2661d29a29baa21f4b866d8e9d61dbb7a63f49b386c50e9', '6134ecb4e9f1584df210cefd0c1cdb372aa1a0ef0687595adba215ecaaa79372'),
}


def candidate():
    path = ROOT/'deploy/autonomous/prepare_content_stream.py'
    spec = importlib.util.spec_from_file_location('question_exact_patch', path)
    patcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patcher)
    original, output = {}, {}
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    for name, (before, after, patch_sha) in SOURCES.items():
        raw = subprocess.check_output(['git', 'show', BASE+':src/reachy_companion/'+name], cwd=ROOT)
        patch = (ROOT/'deploy/patches'/('alice-question-gate-'+name+'.patch')).read_bytes()
        if digest(raw) != before or digest(patch) != patch_sha:
            raise ValueError('Exact question-gate preimage and patch required')
        result = patcher.apply_exact(raw.decode(), patch.decode()).encode()
        if digest(result) != after:
            raise ValueError('Exact question-gate output required')
        compile(result, name, 'exec')
        original[name], output[name] = raw, result
    return original, output


def build(destination):
    _, files = candidate()
    destination.mkdir(mode=0o700)
    for name, raw in files.items():
        with (destination/name).open('xb') as file:
            file.write(raw)
    manifest = dict(kind='same-raw-Alice-question-gate', sources=SOURCES,
        opt_in='conversation.alice_question_gate=true AND Alice speech prefix', default=False,
        max_regenerations=1, same_original_deadline=True, invalid_candidate_spoken_or_committed=False,
        model_endpoint_changed=False, Agent_changed=False, devices_modified=False, hardware_accepted=False,
        semantic_action_safety_proven=False)
    with (destination/'manifest.json').open('x') as file:
        file.write(json.dumps(manifest, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    print(json.dumps(build(parser.parse_args().destination), indent=2))
