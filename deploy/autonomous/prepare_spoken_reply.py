#!/usr/bin/env python3
"""Build the three-file overlay for the exact audited legacy worker. No deploy."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BASE='049083a878280ed23e3732a1881354db37d0eb84'
LEGACY='94fd73d906e75d90829562f58a7f62c83d7e4ff8'
PREFIX='src/reachy_companion/'
PREIMAGES={'voice.py':'95be315c7ed0af376fd9fc9dd6fb319f90776d10b2df04507b5daa0addd5e3c2',
           'brains.py':'9c69d27979dce500148c06ee8d1dc58e90aabae3e5a2b1d3fc8edfb9e754642d'}


def sha(data):return hashlib.sha256(data).hexdigest()

def git_file(commit,name):
    return subprocess.check_output(['git','show',commit+':'+PREFIX+name],cwd=ROOT)


def overlay_voice():
    # Transfer ONLY this feature's exact-source edits; omit intervening STT diagnostics.
    baseline=git_file(BASE,'voice.py').decode().splitlines(keepends=True)
    updated=(ROOT/PREFIX/'voice.py').read_text().splitlines(keepends=True)
    legacy=git_file(LEGACY,'voice.py').decode()
    if sha(legacy.encode())!=PREIMAGES['voice.py']:raise ValueError('Legacy voice preimage mismatch')
    groups=list(difflib.SequenceMatcher(a=baseline,b=updated,autojunk=False).get_grouped_opcodes(2))
    for group in reversed(groups):
        i,j=group[0][1],group[-1][2];k,l=group[0][3],group[-1][4]
        before=''.join(baseline[i:j]);after=''.join(updated[k:l])
        if legacy.count(before)!=1:raise ValueError('Legacy feature patch context is not unique')
        legacy=legacy.replace(before,after,1)
    compile(legacy,'voice.py','exec')
    return legacy.encode()


def build(destination,include_decoder=False,include_sdk=False):
    # No existing directory overwritten. Private ownership/deploy/rollback is runner responsibility.
    files={'voice.py':overlay_voice(),'brains.py':(ROOT/PREFIX/'brains.py').read_bytes(),
           'spoken_reply.py':(ROOT/PREFIX/'spoken_reply.py').read_bytes()}
    if sha(git_file(BASE,'brains.py'))!=PREIMAGES['brains.py']:raise ValueError('Brains preimage mismatch')
    if include_sdk:files['spoken_reply_sdk.py']=(ROOT/PREFIX/'spoken_reply_sdk.py').read_bytes()
    dependencies=('autonomous/__init__.py','autonomous/contracts.py')
    if include_decoder:
        for name in dependencies:files[name]=(ROOT/PREFIX/name).read_bytes()
    for name,data in files.items():compile(data,name,'exec')
    manifest={'kind':'spoken-reply-overlay-1','preimages':{**PREIMAGES,'spoken_reply.py':None,**({'spoken_reply_sdk.py':None} if include_sdk else {}),**({name:None for name in dependencies} if include_decoder else {})},
        'required_absent_directory':'autonomous' if include_decoder else None,
        'outputs':{name:sha(data) for name,data in files.items()},
        'required_existing_dependencies':{name:sha((ROOT/PREFIX/name).read_bytes()) for name in dependencies if not include_decoder},
        'default_config_changed':False,'actual_model_capability_verified':False,
        'hardware_acceptance':False,
        'sdk_route':{'mode':'sdk_raw_instance_v1','sdk_version':'1.5.0','dependency_installation_performed':False,
                     'fixed_reference_capability_verified':False} if include_sdk else None}
    destination.mkdir(mode=0o700)
    for name,data in files.items():
        output=destination/name;output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(data)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    parser.add_argument('--include-decoder',action='store_true',help='Only for a proven absent autonomous package; include its audited minimal decoder closure')
    parser.add_argument('--include-sdk',action='store_true',help='Include the optional source-pinned SDK adapter; installs no SDK or dependencies')
    args=parser.parse_args()
    print(json.dumps(build(args.destination,args.include_decoder,args.include_sdk),indent=2))
