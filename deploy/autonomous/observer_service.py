"""Offline-reviewed Hub launcher; one consumed preflight arm per service start."""
import argparse
import json
import os
from pathlib import Path
import sys


def consume_arm(path):
    consumed = path.with_name(path.name+'.consumed')
    if consumed.exists(): raise ValueError('Previous arm consumed; fresh coordinator preflight required')
    # Coordinator writes this private local file with no other arm writer active.
    # Rename removes the launch authorization even on startup failure/SIGKILL.
    os.rename(path, consumed)
    with consumed.open('rb') as handle: raw = handle.read(16385)
    if len(raw) > 16384: raise ValueError('Bounded arm required')
    value = json.loads(raw)
    if set(value) != {'agent_url', 'hub_url', 'agent_boot', 'microphone_epoch', 'policy_epoch', 'controller'}:
        raise ValueError('Exact fresh authority fields required; credentials forbidden in arm')
    if (any(type(value[key]) is not int or value[key] < 0 for key in ('microphone_epoch', 'policy_epoch'))
            or any(type(value[key]) is not str or not 1 <= len(value[key]) <= 256
                   for key in ('agent_url', 'hub_url', 'agent_boot', 'controller'))):
        raise ValueError('Typed fresh authority required')
    return value


def production_arguments(args, launch):
    """Render one reviewed existing-owner launch; no SSH, model or device startup.

    Gateway role belongs on Mac; session role belongs on Hub. The production
    branch never invokes NativeAgent/NativeScheduler or the old observer lane.
    launch keys name existing peer endpoints/source/controller, never secrets.
    """
    required={'peer_url','peer_stop_port','source_boot','controller','status_port'}
    optional={'lease_datagram_port','trusted_private_lan','camera_context','bounded_motion'}
    if not isinstance(launch,dict) or not required<=set(launch) or set(launch)-required-optional:
        raise ValueError('Exact production launch fields required')
    for name in ('peer_url','source_boot','controller'):
        if not isinstance(launch[name],str) or not 1<=len(launch[name])<=256:raise ValueError('Launch identity')
    for name in ('peer_stop_port','status_port','lease_datagram_port'):
        if name in launch and (type(launch[name]) is not int or not 1<=launch[name]<=65535):raise ValueError('Launch port')
    for name in ('trusted_private_lan','camera_context','bounded_motion'):
        if name in launch and type(launch[name]) is not bool:raise ValueError('Launch permission')
    if any(value is None for value in (args.companion_config,args.output)):raise ValueError('Production companion/output paths required')
    argv=['companion-autonomous','--mode','normal','--lifetime','lease','--allow-capture-output']
    for name in ('config','token_file','companion_config','output'):
        argv.extend(('--'+name.replace('_','-'),str(getattr(args,name))))
    for name in required|{'lease_datagram_port'}:
        if name in launch:argv.extend(('--'+name.replace('_','-'),str(launch[name])))
    for name,flag in [('trusted_private_lan','--trusted-private-lan'),('camera_context','--allow-camera-context'),('bounded_motion','--allow-bounded-motion')]:
        if launch.get(name):argv.append(flag)
    return argv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=('gateway', 'session'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--companion-config', type=Path)
    parser.add_argument('--arm-file', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--metadata', type=Path)
    args = parser.parse_args()
    from reachy_companion.autonomous.config import load
    cfg = load(args.config)
    if cfg.get('production'):
        if cfg.get('native_agent',{}).get('enabled'):raise ValueError('Production forbids native observer orchestration')
        if args.role=='gateway':
            token=args.token_file.read_text().strip()
            if len(token)<32:raise ValueError('Gateway token file required')
            os.environ[cfg['gateway']['token_env']]=token
            from reachy_companion.autonomous.gateway import serve
            serve(cfg);return 0
        if args.arm_file is None:raise ValueError('Reviewed production launch required')
        consumed=args.arm_file.with_name(args.arm_file.name+'.consumed')
        if consumed.exists():raise ValueError('Fresh production launch required')
        raw=args.arm_file.read_bytes()
        if len(raw)>16384:raise ValueError('Launch bound')
        argv=production_arguments(args,json.loads(raw))
        os.rename(args.arm_file,consumed)
        from reachy_companion.autonomous.companion_session import main as session
        sys.argv=argv
        return session()
    from reachy_companion.autonomous.native_agent_session import validate_lifecycle
    validate_lifecycle(cfg, service=True, duration=None)
    if cfg.get('native_agent', {}).get('enabled') is not True:
        raise ValueError('Native profile required')
    if args.role == 'gateway':
        token = args.token_file.read_text().strip()
        if len(token) < 32: raise ValueError('Gateway token file required')
        os.environ[cfg['gateway']['token_env']] = token
        from reachy_companion.autonomous.gateway import serve
        serve(cfg)
        return 0
    if any(value is None for value in (args.companion_config, args.arm_file, args.output, args.metadata)):
        raise ValueError('Session paths required')
    arm = consume_arm(args.arm_file)
    argv = ['native-observer', '--service', '--allow-native-observation', '--allow-configured-agent-url']
    for name in ('config', 'token_file', 'companion_config', 'output', 'metadata'):
        argv.extend(('--'+name.replace('_', '-'), str(getattr(args, name))))
    for name, value in arm.items(): argv.extend(('--'+name.replace('_', '-'), str(value)))
    from reachy_companion.autonomous.native_agent_session import main as session
    sys.argv = argv
    return session()


if __name__ == '__main__': raise SystemExit(main())
