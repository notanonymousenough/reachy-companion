"""Finite same-producer lineage audit across factory/native camera IPC handoff."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
from urllib.request import Request,build_opener,ProxyHandler
from uuid import uuid4


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('production-root','policy-file','token-file','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    if json.loads(args.policy_file.read_text())!={'camera_enabled':True,'privacy_all':False}:
        raise RuntimeError('Explicit camera-only capture policy required')
    leaf=args.output.with_suffix('.producer.json')
    child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('video_server.py')),
        '--production-root',str(args.production_root),'--policy-file',str(args.policy_file),
        '--token-file',str(args.token_file),'--output',str(leaf),'--duration','50'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    token=args.token_file.read_text().strip();opener=build_opener(ProxyHandler({}))
    import native_actor_probe
    operator=native_actor_probe.operator(args.production_root)
    scope=dict(hub_boot_id=str(uuid4()),compute_boot_id='camera-continuity-no-inference',operator_epoch=operator['microphone_epoch'])
    seq=0;rows=[];seen=set();errors=0;deadline=time.monotonic()+47
    try:
        while time.monotonic()<deadline:
            try:
                body=json.dumps(dict(scope=scope,privacy_all=False,seq=seq)).encode();seq+=1
                with opener.open(Request('http://127.0.0.1:8772/policy',data=body,
                    headers={'Authorization':'Bearer '+token}),timeout=.5) as response:response.read(2048)
                with opener.open(Request('http://127.0.0.1:8772/latest',headers={'Authorization':'Bearer '+token}),timeout=.5) as response:
                    packet=response.read(1000001)
                if not 4<len(packet)<=1000000:raise ValueError('Frame packet bound')
                size=struct.unpack('!I',packet[:4])[0]
                if not 0<size<8192:raise ValueError('Frame metadata bound')
                metadata=json.loads(packet[4:4+size])
                factory=subprocess.run(['systemctl','is-active',native_actor_probe.FACTORY],capture_output=True,text=True).stdout.strip()=='active'
                key=(metadata['frame_id'],factory)
                if key not in seen:
                    seen.add(key);rows.append(dict(factory_active=factory,seq=metadata['seq'],
                        lineage_id=metadata['lineage_id'],frame_id=metadata['frame_id'],audio_initialised=metadata['audio_initialised']))
                packet=metadata=None
            except Exception:errors+=1
            time.sleep(.35)
    finally:
        child.wait(timeout=8)
    producer=json.loads(leaf.read_text())
    first_native=next((i for i,row in enumerate(rows) if not row['factory_active']),None)
    report=dict(mode='actual_video_producer_camera_handoff',frames=rows,transient_poll_errors=errors,
                producer=producer,private_frames_exported=0,semantic_inference_requests=0,
                operator_unchanged=operator==native_actor_probe.operator(args.production_root))
    report['accepted']=(first_native is not None and any(row['factory_active'] for row in rows[:first_native])
        and any(row['factory_active'] for row in rows[first_native+1:])
        and len({row['lineage_id'] for row in rows})==1
        and all(row['audio_initialised'] is False for row in rows) and producer['capture_thread_reaped']
        and report['operator_unchanged'])
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps({key:value for key,value in report.items() if key!='frames'}))
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
