"""Build S2 offline on exact installed S0 bytes; never deploy or call a model."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S0_BUILDER_SHA = 'c5c7ffcc93c338c97035b38797aa1b83e74db526ddc087a442de5f8ed66bfc9f'
PREIMAGE = 'b4afda9d2ead77e405612badfea12f5fc8674f4c4e7fc480404f0334d774ddc7'
CONFIG = '9773283044a22b2abefdebb885f1711592e6a22facd22988c4847ee815b1c703'
PATCH = 'bbca1531b0faace5267d3e414c9580b8654c46ae1f34c2140b1c88d1e4deb6c5'
OUTPUT = 'cfd55a2e930869a6d82b77325fab913d18dae2f42a888ca1e670775edf532681'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_exact(name, path, digest):
    if sha(path.read_bytes()) != digest:
        raise ValueError('Exact pinned builder/parser required')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate():
    s0 = load_exact('alice_format_s0', ROOT/'deploy/autonomous/prepare_alice_short_replies.py', S0_BUILDER_SHA)
    _, installed = s0.candidate()  # Frozen S0 verifies its git base, both patches and outputs.
    patch = (ROOT/'deploy/patches/alice-format-voice.py.patch').read_bytes()
    if sha(installed['voice.py']) != PREIMAGE or sha(installed['config.py']) != CONFIG or sha(patch) != PATCH:
        raise ValueError('Exact installed S0 source and S2 patch required')
    parser = load_exact('alice_format_parser', ROOT/'deploy/autonomous/prepare_content_stream.py', s0.PATCHER_SHA)
    result = parser.apply_exact(installed['voice.py'].decode(), patch.decode()).encode()
    if sha(result) != OUTPUT:
        raise ValueError('Exact S2 Alice format output required')
    compile(result, 'voice.py', 'exec')
    return {'voice.py': installed['voice.py']}, {'voice.py': result}


def build(destination):
    original, output = candidate()  # All verification precedes output creation.
    files = dict(output)
    files['preimage/voice.py'] = original['voice.py']
    files['patches/voice.py.patch'] = (ROOT/'deploy/patches/alice-format-voice.py.patch').read_bytes()
    transfer = dict(files={'voice.py': OUTPUT},
                    effective_import_root='/usr/local/lib/python3.13/site-packages/reachy_companion')
    files['transfer-manifest.json'] = (json.dumps(transfer, indent=2)+'\n').encode()
    manifest = dict(kind='S2-exact-S0-Alice-generation-format-1',
        source_base_commit='2865db30e92fcb069c241c34bae4419ad65ed594',
        s0_builder_sha256=S0_BUILDER_SHA, preimages={'voice.py': PREIMAGE}, outputs={'voice.py': OUTPUT},
        unchanged_required_modules={'config.py': CONFIG}, patch_sha256=PATCH,
        files={name: sha(raw) for name, raw in files.items()},
        effective_import_root=transfer['effective_import_root'],
        opt_in={'conversation.alice_short_replies': True, 'speech_address_prefix': 'Алиса, '},
        default_enabled=False, max_words_including_address=11, max_chars_including_address=120,
        generation_retries=0, fallback='AlicePhraseRejected before TTS; no replacement speech',
        style_merge='All segment words in order; initial emotion/gesture; validate entire aggregate',
        dependencies_added=False, config_modified=False, devices_modified=False,
        model_or_voice_changed=False, actual_model_format_verified=False, physical_dialogue_accepted=False)
    destination.mkdir(mode=0o700)
    for name, raw in files.items():
        path = destination/name
        path.parent.mkdir(exist_ok=True)
        with path.open('xb') as file:
            file.write(raw)
    with (destination/'manifest.json').open('x') as file:
        file.write(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    print(json.dumps(build(parser.parse_args().destination), ensure_ascii=False, indent=2))
