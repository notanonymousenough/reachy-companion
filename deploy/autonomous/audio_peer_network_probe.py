"""Finite actual Hub-to-device lease preflight; no inference or PCM commands."""
import argparse
from collections import Counter
import json
from pathlib import Path
import threading
import time
from reachy_companion.config import Config
from reachy_companion.autonomous.audio_peer import PeerClient,PeerLease
from reachy_companion.autonomous.lease_datagram import DatagramRenewal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--peer-url',required=True)
    parser.add_argument('--controller',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=10)
    parser.add_argument('--status-interval',type=float,default=.02)
    parser.add_argument('--trusted-private-lan',action='store_true')
    parser.add_argument('--lease-datagram-port',type=int)
    args=parser.parse_args()
    if args.output.exists() or not 8<=args.duration<=20 or not .02<=args.status_interval<=1:raise ValueError('Fresh finite network probe required')
    if args.lease_datagram_port is not None and not 1<=args.lease_datagram_port<=65535:
        raise ValueError('Explicit valid datagram port required')
    config=Config(args.config)
    client=PeerClient(args.peer_url,config.token,args.controller,trusted_private_lan=args.trusted_private_lan)
    initial=client.call('/status')
    if not initial['operator_ready']:raise RuntimeError('Actual device owner not ready')
    source=initial['source_boot']
    datagram=DatagramRenewal(client,source,args.lease_datagram_port) if args.lease_datagram_port is not None else None
    lease=PeerLease(client,datagram=datagram)
    stop=threading.Event();samples=[];errors=Counter();withdrawn=threading.Event()
    def status_worker():
        while not stop.is_set():
            began=time.monotonic()
            try:
                receipt=client.call('/status')
                samples.append((time.monotonic()-began)*1000)
                if receipt['source_boot']!=source or not receipt['permitted']:withdrawn.set()
            except Exception as exc:errors[type(exc).__name__]+=1
            stop.wait(args.status_interval)
    worker=threading.Thread(target=status_worker,daemon=True);worker.start()
    began=time.monotonic()
    try:
        while time.monotonic()-began<args.duration and not withdrawn.is_set():
            lease.tick();time.sleep(.005)
    finally:
        stop.set();lease.close();worker.join(timeout=.5);lease.worker.join(timeout=.5)
    report=dict(mode='actual_hub_device_network_no_output',source_boot=source,
        elapsed_s=time.monotonic()-began,status_interval_s=args.status_interval,status_requests=len(samples),status_errors=dict(errors),
        max_status_ms=max(samples,default=None),lease=lease.status(),status_execution_busy=worker.is_alive(),
        physical_output_commands=0,inference_requests=0,raw_audio_retained=False)
    try:report['stop']=client.call('/stop')
    except Exception as exc:report['stop_error']=type(exc).__name__
    report['accepted']=(not withdrawn.is_set() and report['elapsed_s']>=args.duration
        and report['lease']['calls']-report['lease']['errors']>=300
        and not report['lease']['execution_busy'] and not worker.is_alive()
        and report.get('stop',{}).get('stop_known') is True
        and report.get('stop',{}).get('execution_busy') is False)
    with args.output.open('x') as handle:json.dump(report,handle,indent=2)
    print(json.dumps(report),flush=True)
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
