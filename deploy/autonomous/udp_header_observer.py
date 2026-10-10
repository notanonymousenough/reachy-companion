"""Finite header-only kernel observer; run synthetic preflight before device capture."""
import argparse
import json
import os
from pathlib import Path
from reachy_companion.autonomous.header_observer import kernel_preflight,observe


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--interface');parser.add_argument('--client-ip');parser.add_argument('--server-ip')
    parser.add_argument('--server-port',type=int,default=8781)
    parser.add_argument('--duration',type=float,default=20);parser.add_argument('--max-records',type=int,default=2000)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh private metadata output required')
    if args.self_test:report=kernel_preflight()
    else:
        if not all((args.interface,args.client_ip,args.server_ip)):raise ValueError('Exact local interface and endpoint pair required')
        report=observe(args.interface,args.client_ip,args.server_ip,args.server_port,duration=args.duration,cap=args.max_records)
    descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as file:json.dump(report,file,indent=2)
    print(json.dumps({name:value for name,value in report.items() if name!='records'}))
    if report.get('accepted',report.get('observer_complete')) is not True:raise SystemExit(2)


if __name__=='__main__':main()
