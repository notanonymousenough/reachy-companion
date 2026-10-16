#!/usr/bin/env python3
"""Build three exact legacy overlay files locally; no devices/config/models."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
SOURCES={
    'brains.py':('39dffa0f1b4d3201765f851be4a932b0a0e079aa',
        '9c69d27979dce500148c06ee8d1dc58e90aabae3e5a2b1d3fc8edfb9e754642d',
        'reachy-brains-9c69-content-stream.patch',
        'b5dd1591b7005b859534c1b2f79fe50313d260fff7eccbf5c8b3715908b50fd7',
        '020e435e37602271d2d40160b055650f781b60a8ee9fc601e3b28d82444bdae6'),
    'voice.py':('2865db30e92fcb069c241c34bae4419ad65ed594',
        '92cf69096fd6f08551a13a9c44d85fbbfc0470ca2f17315616691044018ab865',
        'reachy-worker-92cf-content-stream.patch',
        '804d7889d0a08f8c722d086021c157500a02c166c4f1dd5e56d294c870cd4d41',
        '0bc7617cdce2b61e5b80ad9ffab79e3f35d97e9b7bdb4ceae432028f5b665d8a')}
HELPER='34764e2a00915821cfefbb9b480d17d595db12cf6178f75bb8e6d90246715201'


def sha(value):return hashlib.sha256(value).hexdigest()


def apply_exact(old,patch):
    lines=old.splitlines(True);hunks=[]
    for line in patch.splitlines(True):
        if line.startswith('@@ '):
            match=re.match(r'@@ -(\d+)(?:,(\d+))? ',line)
            if match is None:raise ValueError('Invalid exact patch header')
            start=int(match[1]);count=int(match[2] or 1)
            hunks.append((start if count==0 else start-1,[],[]))
        elif hunks and line[:1] in (' ','-','+'):
            _,before,after=hunks[-1]
            if line[0] in (' ','-'):before.append(line[1:])
            if line[0] in (' ','+'):after.append(line[1:])
    if not hunks:raise ValueError('No exact patch hunks')
    for start,before,after in reversed(hunks):
        if lines[start:start+len(before)]!=before:raise ValueError('Exact patch preimage mismatch')
        lines[start:start+len(before)]=after
    return ''.join(lines)


def build(destination):
    data={};pins={}
    for name,(pin,before,patch_name,patch_sha,after) in SOURCES.items():
        old=subprocess.check_output(['git','show',pin+':src/reachy_companion/'+name],cwd=ROOT)
        patch=(ROOT/'deploy/patches'/patch_name).read_bytes()
        if sha(old)!=before or sha(patch)!=patch_sha:raise ValueError('Frozen source/patch hash mismatch')
        new=apply_exact(old.decode(),patch.decode()).encode()
        if sha(new)!=after:raise ValueError('Frozen overlay output mismatch')
        data[name]=new;pins[name]=dict(public_preimage_pin=pin,preimage_sha256=before,patch_sha256=patch_sha)
    helper=(ROOT/'src/reachy_companion/token_stream.py').read_bytes()
    if sha(helper)!=HELPER:raise ValueError('Frozen helper mismatch')
    data['token_stream.py']=helper
    for name,raw in data.items():compile(raw,name,'exec')
    manifest=dict(kind='content-stream-exact-legacy-2',sources=pins,outputs={k:sha(v) for k,v in data.items()},
        dependencies_added=False,default_config_changed=False,devices_modified=False,
        actual_voice_acceptance=False,required_acceptance_config={'streaming.content_tokens':True,'streaming.content_request_seconds':40})
    destination.mkdir(mode=0o700)
    for name,raw in data.items():
        with (destination/name).open('xb') as file:file.write(raw)
    with (destination/'manifest.json').open('x') as file:file.write(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    print(json.dumps(build(parser.parse_args().destination),indent=2))
