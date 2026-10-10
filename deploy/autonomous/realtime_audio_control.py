"""Inspect/stop one pinned finite session or audit its completed cleanup receipts."""
import argparse
import json
from pathlib import Path
from reachy_companion.config import Config
from reachy_companion.autonomous.audio_session_control import SessionClient,cleanup_receipts
from reachy_companion.autonomous.contracts import decode


def read_receipt(path):
    with path.open('rb') as file:raw=file.read(1048577)
    if len(raw)>1048576:raise ValueError('Finite receipt size bound')
    return decode(raw)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('status','stop','check-cleanup'))
    parser.add_argument('--controller',required=True)
    parser.add_argument('--session-boot');parser.add_argument('--source-boot')
    parser.add_argument('--config',type=Path);parser.add_argument('--url',default='http://127.0.0.1:8790')
    parser.add_argument('--hub-receipt',type=Path);parser.add_argument('--device-receipt',type=Path)
    args=parser.parse_args()
    if args.action!='status' and (not args.session_boot or not args.source_boot):
        raise ValueError('Explicit pinned session/source required')
    if args.action=='check-cleanup':
        if not args.hub_receipt or not args.device_receipt:raise ValueError('Both finite receipts required')
        result=cleanup_receipts(read_receipt(args.hub_receipt),read_receipt(args.device_receipt),
            controller=args.controller,session_boot=args.session_boot,source_boot=args.source_boot)
        print(json.dumps(result));return 0 if result['receipt_cleanup_verified'] else 2
    if not args.config:raise ValueError('Local companion config required')
    client=SessionClient(args.url,Config(args.config).token,args.controller,timeout=.5)
    if args.action=='status':
        result=client.status()
        if result['controller']!=args.controller:raise ValueError('Status owner mismatch')
    else:result=client.stop(args.session_boot,args.source_boot)
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
