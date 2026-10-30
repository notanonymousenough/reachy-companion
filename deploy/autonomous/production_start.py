"""Explicit service start for the existing production device or Hub owner.

Each invocation creates fresh authority and output paths. A stopped/withdrawn
session is never silently reconnected. Services should use Restart=no.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=('device', 'hub'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--token-file', type=Path)
    parser.add_argument('--controller', default='reachy-production')
    parser.add_argument('--peer-url', default='http://127.0.0.1:18780')
    parser.add_argument('--peer-stop-port', type=int, default=18781)
    parser.add_argument('--listen-device', default='127.0.0.1')
    parser.add_argument('--lease-datagram-port', type=int)
    parser.add_argument('--trusted-private-lan', action='store_true')
    args = parser.parse_args()
    from reachy_companion.config import Config
    from reachy_companion.autonomous.audio_peer import PeerClient
    root = args.root.resolve()
    companion = root / 'config.local.json'
    cfg = Config(companion)
    run = root / 'data' / ('production-' + uuid.uuid4().hex)
    run.mkdir(mode=0o700)
    if args.role == 'device':
        from device_audio_runtime import agent, main as device_main
        # Transfer capture from the legacy voice loop to one explicit lease.
        agent(cfg, '/microphone', dict(enabled=False, listen=False))
        deadline = time.monotonic() + 10
        while True:
            before = agent(cfg, '/operator')
            if not before['capture_active'] and not before['listening'] and before['phase'] == 'paused':
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Previous capture owner did not retire')
            time.sleep(.05)
        policy = before['motion_policy']
        if policy['quiet'] or policy['privacy_all']:
            raise RuntimeError('Operator privacy/quiet blocks capture')
        owner = dict(agent_boot_id=before['agent_boot_id'],
                     initial_microphone_epoch=before['microphone_epoch'],
                     owned_microphone_epoch=before['microphone_epoch'] + 1,
                     owner_id=uuid.uuid4().hex, policy_epoch=policy['epoch'])
        path = run / 'owner.json'
        path.write_text(json.dumps(owner)); path.chmod(0o600)
        agent(cfg, '/microphone', dict(enabled=True, listen=False,
              expected_boot_id=owner['agent_boot_id'], expected_epoch=owner['initial_microphone_epoch'],
              owner_id=owner['owner_id']))
        sys.argv = ['device-audio', '--config', str(companion), '--output', str(run / 'device.json'),
                    '--owner-file', str(path), '--controller', args.controller,
                    '--lifetime', 'lease', '--allow-capture-output', '--allow-agent-mute',
                    '--port', '8780', '--stop-port', '8781', '--listen', args.listen_device,
                    '--endpoint-max-seconds', '4', '--endpoint-silence-frames', '20']
        if args.lease_datagram_port:
            sys.argv += ['--lease-datagram-port', str(args.lease_datagram_port)]
        return device_main()
    if args.config is None or args.token_file is None:
        parser.error('Hub requires --config and --token-file')
    client = PeerClient(args.peer_url, cfg.token, args.controller,
                        trusted_private_lan=args.trusted_private_lan)
    deadline = time.monotonic() + 10
    while True:
        try:
            peer = client.call('/status')
            if peer.get('closed') is False:
                break
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Fresh device owner unavailable')
        time.sleep(.05)
    from reachy_companion.autonomous.companion_session import main as session_main
    sys.argv = ['companion-autonomous', '--mode', 'normal', '--config', str(args.config),
                '--companion-config', str(companion), '--token-file', str(args.token_file),
                '--output', str(run / 'hub.json'), '--controller', args.controller,
                '--peer-url', client.url, '--peer-stop-port', str(args.peer_stop_port),
                '--source-boot', peer['source_boot'], '--lifetime', 'lease',
                '--allow-capture-output', '--status-port', '8791', '--lease-progress-s', '.2']
    if json.loads(args.config.read_text()).get('motion',{}).get('enabled'):
        sys.argv.append('--allow-bounded-motion')
    if args.lease_datagram_port:
        sys.argv += ['--lease-datagram-port', str(args.lease_datagram_port)]
    if args.trusted_private_lan:
        sys.argv.append('--trusted-private-lan')
    return session_main()


if __name__ == '__main__':
    os.umask(0o077)
    raise SystemExit(main())
