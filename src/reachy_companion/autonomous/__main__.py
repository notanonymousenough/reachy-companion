"""Separate opt-in entrypoint; does not deploy or import hardware services."""
import argparse
import json
from pathlib import Path
from .config import load
from .contracts import decode
from .runtime import ReplayGateway, RemoteGateway, Scheduler


def main():
    parser = argparse.ArgumentParser(description='Autonomous companion shadow/replay only')
    parser.add_argument('command', choices=['validate', 'replay', 'shadow', 'gateway'])
    parser.add_argument('--config', default='config.autonomous.example.json')
    parser.add_argument('--events')
    parser.add_argument('--duration', type=float, default=5)
    parser.add_argument('--main-delay', type=float, default=0.1)
    parser.add_argument('--output')
    args = parser.parse_args()
    config = load(args.config)
    if args.command == 'validate':
        print('PASS: simulated actuators, bounded budgets, no model/device execution'); return
    if args.command == 'gateway':
        from .gateway import serve
        serve(config); return
    if not 0 < args.duration <= 1800 or not 0 <= args.main_delay <= 120:
        parser.error('Finite run requires duration≤1800s and main-delay≤120s')
    events = decode(Path(args.events).read_text()) if args.events else []
    if not isinstance(events, list) or len(events) > 10000:
        parser.error('Replay events must be a bounded list')
    previous = -1
    for event in events:
        at = event.get('at_s')
        if type(at) not in (int,float) or not previous <= at <= args.duration:
            parser.error('Events must have ordered nonnegative at_s within run duration')
        previous = at
    gateway = ReplayGateway(args.main_delay) if args.command=='replay' else RemoteGateway(config)
    report = Scheduler(config, gateway).run(args.duration, events, args.output)
    print(json.dumps({k:v for k,v in report.items() if k != 'ledger'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
