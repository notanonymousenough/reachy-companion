import argparse
import json
from pathlib import Path
import sys

from .config import Config, initialize


def main():
    parser = argparse.ArgumentParser(prog='companion')
    parser.add_argument('--config', help='JSON configuration; defaults to config.local.json or REACHY_COMPANION_CONFIG')
    commands = parser.add_subparsers(dest='group', required=True)
    setup = commands.add_parser('config')
    setup.add_argument('action', choices=('init', 'validate', 'value'))
    setup.add_argument('key', nargs='?')
    hub = commands.add_parser('hub')
    hub.add_argument('action', choices=('serve', 'status', 'hello', 'wake', 'sleep'))
    voice = commands.add_parser('voice')
    voice.add_argument('action', choices=('serve', 'status', 'pause', 'resume', 'reset', 'ask', 'say'))
    voice.add_argument('text', nargs='?')
    agent = commands.add_parser('agent')
    agent.add_argument('action', choices=('serve', 'test-speaker'))
    worker = commands.add_parser('worker')
    worker.add_argument('action', choices=('serve', 'prepare'))
    deploy = commands.add_parser('deploy')
    deploy.add_argument('role', choices=('hub', 'robot', 'worker', 'both'))
    deploy.add_argument('--dry-run', action='store_true')
    install = commands.add_parser('install')
    install.add_argument('role', choices=('hub', 'robot', 'worker'))
    install.add_argument('--skip-model-download', action='store_true')
    firewall = commands.add_parser('firewall')
    firewall.add_argument('action', choices=('render', 'apply', 'remove', 'arm', 'confirm', 'install'))
    ssh = commands.add_parser('ssh')
    ssh.add_argument('role', choices=('hub', 'robot', 'worker'))
    ssh.add_argument('command', nargs=argparse.REMAINDER)
    download = commands.add_parser('models')
    download.add_argument('action', choices=('download',))
    args = parser.parse_args()
    if args.group == 'config' and args.action == 'init':
        print(initialize(Path.cwd()))
        return 0
    config = Config(args.config, require_token=args.group not in ('config', 'firewall', 'ssh'))
    if args.group == 'config':
        if args.action == 'validate':
            print('Configuration is valid: ' + str(config.filename))
        else:
            if not args.key:
                parser.error('config value requires a dotted key')
            value = config.value(args.key)
            print(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list, bool)) else value)
    elif args.group in ('hub', 'voice'):
        if args.action == 'serve':
            if args.group == 'hub':
                from .hub import main as run
            else:
                if config['voice']['mode'] == 'remote':
                    from .router import main as run
                else:
                    from .voice import main as run
            run(config)
        else:
            if args.action in ('ask', 'say') and not args.text:
                parser.error('ask/say requires text')
            from .client import control
            return control(config, args.group, args.action, getattr(args, 'text', None))
    elif args.group == 'worker':
        if args.action == 'prepare':
            from .deployment import download_models
            download_models(config)
        else:
            from .voice import main
            main(config, worker=True)
    elif args.group == 'agent':
        from .agent import main as run
        run(config, test_speaker=args.action == 'test-speaker')
    elif args.group == 'firewall':
        from .firewall import main as run
        run(config, args.action)
    elif args.group == 'ssh':
        from .deployment import ssh as run
        return run(config, args.role, args.command)
    elif args.group == 'deploy':
        from .deployment import deploy as run
        run(config, args.role, dry_run=args.dry_run)
    elif args.group == 'install':
        from .deployment import install as run
        run(config, args.role, skip_models=args.skip_model_download)
    else:
        from .deployment import download_models
        download_models(config)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        sys.exit(1)
