#!/usr/bin/env python3
"""Build an offline local timeline-armed proposal against exact Expression7a5."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BASE='9a2c510908fdfd70bb55b6a3b0a3bc920a05df23'
BEFORE='7a5f7a0019352ecf8ceb2d3b6cf958e206655ab3a58387671c163aa86730bfdb'
AFTER='a8c149ac3986dcfc95886c4224a647857903b3e2fb03eb91b0aa0b6bedd97ebe'
PATCH='15bd63bc653bad53f1e8753c9994eebe449fb3fe7b93b83deedfe451f13c695d'


def digest(raw): return hashlib.sha256(raw).hexdigest()


def candidate():
    raw=subprocess.check_output(['git','show',BASE+':src/reachy_companion/expression_player.py'],cwd=ROOT)
    patch=(ROOT/'deploy/patches/reachy-expression-7a5-local-armed.patch').read_bytes()
    if digest(raw)!=BEFORE or digest(patch)!=PATCH:raise ValueError('Exact expression preimage/patch required')
    spec=importlib.util.spec_from_file_location('timeline_exact',ROOT/'deploy/autonomous/prepare_content_stream.py')
    patcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(patcher)
    result=patcher.apply_exact(raw.decode(),patch.decode()).encode()
    if digest(result)!=AFTER:raise ValueError('Exact local timeline output required')
    compile(result,'expression-local-armed-proposal.py','exec')
    return raw,result


def build(destination):
    before,after=candidate()
    manifest=dict(kind='exact-7a5-local-timeline-armed-proposal',preimage_sha256=digest(before),
        output_sha256=digest(after),patch_sha256=PATCH,
        option='conversation.expressions.timeline_gate',default='completion',opt_in='local_armed',
        semantics='local scheduler ready, not remote SDK admission or physical motion',
        proposal=True,hardware_accepted=False,devices_modified=False,antenna_targets_or_sdk_modified=False,
        remote_admission_verified=False,latency_improvement_verified=False,
        current_expression_pin=BEFORE,current_Agent_pin='cf50c54680d8e30fb97090e80d0e687a9dad903159f464d2211414aefcaca069',
        current_router_pin='f51365c97b997b827fcc5a9d8c31b6d7082f78bb44301b12b278d19c684cbb4f')
    destination.mkdir(mode=0o700)
    with (destination/'expression_player.py').open('xb') as file:file.write(after)
    with (destination/'manifest.json').open('x') as file:file.write(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    print(json.dumps(build(parser.parse_args().destination),indent=2))
