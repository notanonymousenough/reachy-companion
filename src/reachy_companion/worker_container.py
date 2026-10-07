"""Docker launcher reads ports and volume paths from the same JSON config."""
import argparse
from pathlib import Path
import subprocess
from .config import Config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('build', 'prepare', 'start', 'stop', 'logs', 'command'))
    parser.add_argument('--config')
    args = parser.parse_args()
    config = Config(args.config)
    settings = config['container']
    if args.action == 'build':
        command = ['docker', 'build', '-f', str(config.root / 'worker/Dockerfile'),
                   '-t', settings['image'], str(config.root)]
    elif args.action in ('stop', 'logs'):
        command = ['docker', args.action, settings['name']]
    else:
        port = config['servers']['worker']['port']
        config.path(config['paths']['data_dir']).mkdir(parents=True, exist_ok=True)
        for model in config['models'].values():
            if Path(model['path']).is_absolute():
                raise ValueError('Container model paths must be relative to config')
        command = ['docker', 'run']
        if args.action in ('start', 'command'):
            command += ['-d', '--name', settings['name'], '--restart', 'unless-stopped',
                        '-p', settings['publish_address'] + ':' + str(port) + ':' + str(port)]
        else:
            command += ['--rm']
        if config['conversation'].get('recognition', {}).get('device') == 'cuda':
            command += ['--gpus', settings['gpu']]
        command += ['--mount', 'type=bind,source=' + str(config.root) + ',target=/config',
                    '--read-only', '--tmpfs', '/tmp', '-e', 'OMP_NUM_THREADS=' + str(settings['cpu_threads'])]
        # Pass named variables without exposing their VALUES on the command line.
        for selected in ('openclaw', 'hermes'):
            command += ['-e', config['brains'][selected]['api_key_env']]
        command += [settings['image'], '--config', '/config/' + config.filename.name,
                    'worker', 'prepare' if args.action == 'prepare' else 'serve']
    if args.action == 'command':
        import shlex
        print(shlex.join(command))
    else:
        subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
