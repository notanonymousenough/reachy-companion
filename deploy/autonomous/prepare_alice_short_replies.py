"""Build the exact effective R1/A1 worker phrase gate offline; never deploy."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '2865db30e92fcb069c241c34bae4419ad65ed594'
PATCHER_SHA = '5c102dd8379a061d15a40a76929665c0e2fee11f4465a26e850e1e704b9ffffe'
SOURCES = {
    'voice.py': ('92cf69096fd6f08551a13a9c44d85fbbfc0470ca2f17315616691044018ab865',
                 'e9f98fea8a088eb82fbebd5916c8e98f633d86d884cd210302253879ea714457',
                 'b4afda9d2ead77e405612badfea12f5fc8674f4c4e7fc480404f0334d774ddc7'),
    'config.py': ('c0b0e7a8470401a20b684ada3132784e0805333f9ab56c18b1f8d585d7eb3436',
                  '83a24b8de0f3d3ef7469e9e3594ca8e5460df9309175164addd966f7d7b8e4af',
                  '9773283044a22b2abefdebb885f1711592e6a22facd22988c4847ee815b1c703'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def candidate():
    path = ROOT/'deploy/autonomous/prepare_content_stream.py'
    if sha(path.read_bytes()) != PATCHER_SHA:
        raise ValueError('Exact existing patch parser required')
    spec = importlib.util.spec_from_file_location('alice_short_exact_patch', path)
    patcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patcher)
    original, output = {}, {}
    for name, (before, patch_sha, after) in SOURCES.items():
        raw = subprocess.check_output(['git', 'show', BASE+':src/reachy_companion/'+name], cwd=ROOT)
        patch = (ROOT/'deploy/patches'/('alice-short-replies-'+name+'.patch')).read_bytes()
        if sha(raw) != before or sha(patch) != patch_sha:
            raise ValueError('Exact effective worker preimage and patch required')
        result = patcher.apply_exact(raw.decode(), patch.decode()).encode()
        if sha(result) != after:
            raise ValueError('Exact Alice short-reply output required')
        compile(result, name, 'exec')
        original[name], output[name] = raw, result
    return original, output


def build(destination):
    original, output = candidate()  # Verify everything before creating output.
    destination.mkdir(mode=0o700)
    files = dict(output)
    for name, raw in original.items():
        files['preimage/'+name] = raw
        files['patches/'+name+'.patch'] = (ROOT/'deploy/patches'/('alice-short-replies-'+name+'.patch')).read_bytes()
    for name, raw in files.items():
        path = destination/name
        path.parent.mkdir(exist_ok=True)
        with path.open('xb') as file:
            file.write(raw)
    manifest = dict(kind='S0-exact-effective-Alice-short-replies-1', source_commit=BASE,
        preimages={name:values[0] for name,values in SOURCES.items()},
        outputs={name:values[2] for name,values in SOURCES.items()},
        files={name:sha(raw) for name,raw in files.items()}, patch_parser_sha256=PATCHER_SHA,
        effective_import_root='/usr/local/lib/python3.13/site-packages/reachy_companion',
        opt_in={'conversation.alice_short_replies':True, 'speech_address_prefix':'Алиса, '},
        default_enabled=False, max_words_including_address=11, max_chars_including_address=120,
        generation_retries=0, fallback='AlicePhraseRejected before TTS; no replacement speech',
        dependencies_added=False, model_or_voice_changed=False, devices_modified=False,
        physical_dialogue_accepted=False)
    with (destination/'manifest.json').open('x') as file:
        file.write(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    print(json.dumps(build(parser.parse_args().destination), ensure_ascii=False, indent=2))
