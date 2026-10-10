#!/usr/bin/env python3
"""Read-only exact two-module overlay check. Never import models or deploy."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

BEFORE={'voice.py':'95be315c7ed0af376fd9fc9dd6fb319f90776d10b2df04507b5daa0addd5e3c2',
    'recognition.py':'6211a01e8d4ecf515636d4407856fddcf6e5deec4ddbd5639ae977770111f15f',
    'sound_events.py':'6e26da0e477ba819f2339ab6b3923bd9742c0495139f958abd078da28d9b7e4a'}
AFTER={'voice.py':'46c0343fd47e085098be6ffd7828673986caca0e4bd924d6f2e3178508708c73',
    'recognition.py':'b79a709bb3167c0fba380aafa687c846db592c8ec0ecdeec88742179ec548344'}

def check(directory,pins):
    for name,expected in pins.items():
        data=(directory/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Module hash mismatch: '+name)
        ast.parse(data,filename=name) # no imports, model loading or pyc writes

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--before-dir',type=Path,required=True);parser.add_argument('--patched-dir',type=Path,required=True)
    args=parser.parse_args()
    try:check(args.before_dir,BEFORE);check(args.patched_dir,AFTER)
    except (ValueError,OSError,SyntaxError):parser.exit(1,'Exact STT overlay preflight failed; no deployment performed.\n')
    print(json.dumps(dict(exact_source_pins=True,patch_modules=list(AFTER),unchanged_sound_events=True,
        inference_calls=0,audio_capture=False,production_mutations=False)))

if __name__=='__main__':main()
