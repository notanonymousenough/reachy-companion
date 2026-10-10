"""Persistent systemd entrypoint; each lifecycle retains its own recovery intent."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service-config',type=Path,required=True)
    parser.add_argument('--production-root',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
    from reachy_companion.autonomous.native_config import load
    profile=load(args.service_config)
    if not profile['enabled']:raise RuntimeError('Native owner default-off profile')
    import os
    guard=Path(profile['guard_directory'])
    if not guard.exists():
        guard.mkdir(mode=0o700,parents=True);os.chown(guard,1000,1000)
    if not guard.is_dir() or guard.stat().st_uid!=1000:raise RuntimeError('Native ledger directory owner unknown')
    directory=guard/'lifecycles'
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    # Receipts contain bounded metadata only. Keep bounded operator-owned
    # history; active intents and database authority are never removed here.
    os.chown(directory,1000,1000)
    import native_actor_probe
    if native_actor_probe.MARKER.exists():raise RuntimeError('Prior owner fence requires recovery audit')
    import json,re
    completed=[]
    for path in directory.glob('*.json'):
        if not re.fullmatch(r'[0-9a-f-]{36}\.json',path.name):continue
        try:
            if path.stat().st_size<=65536 and json.loads(path.read_text()).get('factory_restored') is True:completed.append(path)
        except Exception:continue
    for path in sorted(completed,key=lambda item:item.stat().st_mtime)[:-16]:
        for old in (path,path.with_suffix('.child.json'),path.with_suffix('.child.intent.json'),path.with_suffix('.child.closing.json')):old.unlink(missing_ok=True)
    sys.argv=[str(Path(__file__).with_name('native_actor_probe.py')),
        '--runtime-service','--service-config',str(args.service_config),
        '--production-root',str(args.production_root),'--output',str(directory/(str(uuid4())+'.json'))]
    native_actor_probe.main()


if __name__=='__main__':main()
