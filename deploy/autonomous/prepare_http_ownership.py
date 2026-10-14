#!/usr/bin/env python3
"""Generate only the HTTP ownership delta over the audited legacy brains.py."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
SOURCE='src/reachy_companion/brains.py'
BASE='049083a878280ed23e3732a1881354db37d0eb84'
PREIMAGE='9c69d27979dce500148c06ee8d1dc58e90aabae3e5a2b1d3fc8edfb9e754642d'


def build(destination):
    legacy=subprocess.check_output(['git','show',BASE+':'+SOURCE],cwd=ROOT)
    if hashlib.sha256(legacy).hexdigest()!=PREIMAGE:raise ValueError('Legacy brains preimage mismatch')
    current=(ROOT/SOURCE).read_text();tree=ast.parse(current)
    names=('ModelExecutionOwnership','MODEL_EXECUTION','model_identity','http_model_choice')
    blocks=[]
    for name in names:
        matches=[n for n in tree.body if getattr(n,'name',None)==name or
                 isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
        if len(matches)!=1:raise ValueError('Unique ownership source node required')
        blocks.append(ast.get_source_segment(current,matches[0]))
    text=legacy.decode()
    before="from urllib.request import Request, build_opener, ProxyHandler\n"
    after=before+'import threading\nfrom contextlib import contextmanager\n\n\n'+'\n\n'.join(blocks)+'\n'
    if text.count(before)!=1:raise ValueError('Legacy import anchor mismatch')
    text=text.replace(before,after,1)
    before="    with build_opener(ProxyHandler({})).open(request, timeout=config['timeouts']['llm']) as response:\n        choice = json.load(response)['choices'][0]"
    after="    if selected=='lm_studio':choice=http_model_choice(config,request)\n    else:\n        with build_opener(ProxyHandler({})).open(request, timeout=config['timeouts']['llm']) as response:\n            choice = json.load(response)['choices'][0]"
    if text.count(before)!=1:raise ValueError('Legacy prediction anchor mismatch')
    text=text.replace(before,after,1);compile(text,'brains.py','exec')
    data=text.encode()
    manifest=dict(kind='http-ownership-legacy-1',preimages={'brains.py':PREIMAGE},
        outputs={'brains.py':hashlib.sha256(data).hexdigest()},default_config_changed=False,
        sdk_dependency_added=False,actual_model_identity_verified=False,hardware_acceptance=False)
    destination.mkdir(mode=0o700)
    (destination/'brains.py').write_bytes(data)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    print(json.dumps(build(parser.parse_args().destination),indent=2))
