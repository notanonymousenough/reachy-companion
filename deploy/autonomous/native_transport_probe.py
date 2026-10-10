"""Read installed public SDK source and process roles; never initialize hardware."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();spec=importlib.util.find_spec('reachy_mini')
    root=Path(next(iter(spec.submodule_search_locations)))
    files=[]
    for path in root.rglob('*.py'):
        if path.stat().st_size>262144:continue
        body=path.read_bytes()
        if any(key in body for key in (b'def process_command',b'class Client',b'class ZenohClient',b'class WebRTCClient',b'def set_motor_control_mode',b'def set_target',b'def set_joint_positions')):
            files.append(dict(path=str(path),relative=str(path.relative_to(root)),sha256=hashlib.sha256(body).hexdigest(),
                              process_command=b'def process_command' in body,zenoh=b'zenoh' in body,webrtc=b'webrtc' in body))
    processes=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit() or int(path.name)==os.getpid():continue
        try:
            command=(path/'cmdline').read_bytes().split(b'\0')
            if not command or 'python' not in Path(command[0].decode()).name.lower():continue
            status=(path/'status').read_text();uid=next(line.split()[1] for line in status.splitlines() if line.startswith('Uid:'))
            groups=(path/'cgroup').read_text()
            units=['reachy-voice-agent.service','reachy-mini-daemon.service','reachy-mini.service']
            processes.append(dict(pid=int(path.name),uid=int(uid),known_service=next((unit for unit in units if unit in groups),'other'),
                 sdk_module_tokens=[name for name in ('reachy_companion','reachy_mini.daemon.app.main','reachy_mini') if name.encode() in command]))
        except (OSError,UnicodeError,StopIteration):pass
    report=dict(mode='installed_native_source_read_only',sdk_root=str(root),files=files[:32],processes=processes[:32],hardware_initializations=0)
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps(report))


if __name__=='__main__':main()
