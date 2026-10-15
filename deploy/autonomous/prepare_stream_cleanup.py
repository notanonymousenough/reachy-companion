#!/usr/bin/env python3
"""Generate only the successful-stream cleanup delta over exact legacy voice."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
SOURCE='src/reachy_companion/voice.py'
BASE='94fd73d906e75d90829562f58a7f62c83d7e4ff8'
PREIMAGE='95be315c7ed0af376fd9fc9dd6fb319f90776d10b2df04507b5daa0addd5e3c2'
CLEANUP_SOURCE='086d1598ca48c472e7cf931f528adfe45c038055'
CLEANUP_SHA='64a30eca4abda9efa6a94cce55fac0d5ff322c1a1ae7555055ee2ee0ce340791'
BEFORE="""            yield {'type': 'done', 'ok': True, **self.completed(result, session, pending, started)}
        finally:
            if executor is not None:
                executor.shutdown(wait=True)
            self.phase = 'idle'
            self.lock.release()
"""
AFTER="""            terminal = {'type': 'done', 'ok': True, **self.completed(result, session, pending, started)}
        finally:
            try:
                if executor is not None:
                    executor.shutdown(wait=True)
            finally:
                self.phase = 'idle'
                self.lock.release()
        # A received successful terminal event must follow producer cleanup.
        # Exceptions and generator.close() leave through finally without done.
        yield terminal
"""


def git_file(pin):
    return subprocess.check_output(['git','show',pin+':'+SOURCE],cwd=ROOT)


def sha(data):return hashlib.sha256(data).hexdigest()


def build(destination):
    legacy=git_file(BASE);reviewed=git_file(CLEANUP_SOURCE)
    if sha(legacy)!=PREIMAGE:raise ValueError('Legacy voice preimage mismatch')
    if sha(reviewed)!=CLEANUP_SHA:raise ValueError('Reviewed cleanup source mismatch')
    text=legacy.decode()
    if text.count(BEFORE)!=1 or reviewed.decode().count(AFTER)!=1:
        raise ValueError('Unique exact stream cleanup delta required')
    data=text.replace(BEFORE,AFTER,1).encode();compile(data,'voice.py','exec')
    manifest=dict(kind='stream-cleanup-legacy-1',base_pin=BASE,
        cleanup_source_pin=CLEANUP_SOURCE,cleanup_source_sha256=CLEANUP_SHA,
        preimages={'voice.py':PREIMAGE},outputs={'voice.py':sha(data)},
        default_config_changed=False,dependencies_added=False,
        actual_model_capability_verified=False,hardware_acceptance=False)
    destination.mkdir(mode=0o700)
    (destination/'voice.py').write_bytes(data)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    print(json.dumps(build(parser.parse_args().destination),indent=2))
