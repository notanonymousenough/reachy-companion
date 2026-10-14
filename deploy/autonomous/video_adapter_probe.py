"""Finite PC-only one-frame adapter check over an existing isolated video reader.

No SDK/audio/motor/model imports. Only RAM frame transport; output is metadata and
pixel aggregates. Never promotes PTS/receipt into a verified capture timestamp.
"""
import argparse
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler
from uuid import uuid4
from reachy_companion.autonomous.context import LatestVideo
from reachy_companion.autonomous.video_adapter import LatestFrameProcessor,decode_packet


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--video-url',required=True);parser.add_argument('--token-env',default='REACHY_VIDEO_TOKEN')
    parser.add_argument('--operator-epoch',required=True,type=int);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--duration',type=float,default=6)
    args=parser.parse_args();url=urlsplit(args.video_url)
    if (url.scheme!='http' or url.hostname not in ('localhost','127.0.0.1','::1') or url.username or url.password or url.query or url.fragment
            or not 0<=args.operator_epoch<2**63 or not 2<=args.duration<=10):raise ValueError('Finite loopback/private video bounds')
    token=os.environ.get(args.token_env,'')
    if len(token)<32:raise ValueError('Separate video bearer environment required')
    # Reserve report before any sidecar policy change; never overwrite a receipt.
    descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    scope=dict(hub_boot_id=str(uuid4()),compute_boot_id=str(uuid4()),operator_epoch=args.operator_epoch)
    admission=str(uuid4());cache=LatestVideo();done=threading.Event();errors=0;sequence=0
    def deliver(worker,job,metrics):
        def publish():
            accepted=cache.publish(job[1],metrics,job[3])
            if accepted:done.set()
            return accepted
        worker.commit(job,publish)
    worker=LatestFrameProcessor(deliver);http=build_opener(ProxyHandler({}));report={}
    def policy(private):
        nonlocal sequence
        sequence+=1;body=json.dumps(dict(scope=scope,seq=sequence,privacy_all=private,admission_id=admission)).encode()
        request=Request(args.video_url.rstrip('/')+'/policy',data=body,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with http.open(request,timeout=.5) as response:response.read(1024)
    try:
        deadline=time.monotonic()+args.duration
        while time.monotonic()<deadline and not done.is_set():
            payload=raw=None
            try:
                policy(False)
                request=Request(args.video_url.rstrip('/')+'/latest',headers={'Authorization':'Bearer '+token})
                with http.open(request,timeout=.5) as response:payload=response.read(1048577)
                received=time.monotonic();metadata,raw=decode_packet(payload)
                if metadata['scope']!=scope or metadata['admission_id']!=admission:raise ValueError('Old source admission')
                worker.submit(metadata,raw,received,admission)
            except Exception:errors+=1
            finally:payload=raw=None
            done.wait(.1)
        with cache.lock:current=cache.current
        report=dict(mode='finite_pc_video_adapter_observation',observed=current is not None,
            camera_only=True,raw_files_created=0,model_requests=0,audio_or_motor_commands=0,
            source_capture_time_verified=False,hardware_camera_acceptance=False,poll_errors=errors)
        if current:
            metadata,metrics,_=current;report.update(provenance=metadata,metrics=metrics,sensor=cache.snapshot(time.monotonic()))
        try:policy(True) # exact private owner; producer rejects retired/foreign/newer scope/sequence
        except Exception:report['owned_policy_close_unknown']=True
    finally:
        reaped=worker.close();cache.clear();report.update(processor_reaped=reaped,processor_status=worker.status())
        with os.fdopen(descriptor,'w') as output:json.dump(report,output,allow_nan=False,indent=2)
    print(json.dumps({key:value for key,value in report.items() if key not in ('provenance','metrics')}))
    if not report.get('observed') or not report['processor_reaped']:raise SystemExit(2)

if __name__=='__main__':main()
