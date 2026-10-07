"""Reproducible SSH deployment and device installation."""
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
import zipfile


def ssh_args(config, role, scp=False):
    target = config['deployment'][role]
    args = ['scp' if scp else 'ssh', '-o', 'ConnectTimeout=' + str(config['timeouts']['ssh_connect'])]
    if target['identity_file']:
        args += ['-i', str(config.path(target['identity_file']))]
    if role == 'robot':
        hub = config['deployment']['hub']
        args += ['-J', hub['user'] + '@' + hub['host']]
    return args


def ssh(config, role, command):
    target = config['deployment'][role]
    if command and command[0] == '--':
        command = command[1:]
    args = ssh_args(config, role) + [target['user'] + '@' + target['host']]
    if command:
        args += [shlex.join(command)]
    return subprocess.call(args)


def deploy(config, role, dry_run=False):
    for selected in ('hub', 'robot') if role == 'both' else (role,):
        target = config['deployment'][selected]
        peer = target['user'] + '@' + target['host']
        root = target['root']
        with tempfile.TemporaryDirectory(prefix='reachy-deploy-') as temporary:
            bundle = Path(temporary) / 'bundle'
            bundle.mkdir()
            for name in ('src', 'scripts', 'requirements', 'scenarios', 'docs', 'worker', 'profiles'):
                shutil.copytree(config.root / name, bundle / name, ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('pyproject.toml', 'README.md', 'config.example.json'):
                shutil.copy2(config.root / name, bundle / name)
            shutil.copy2(config.filename, bundle / 'config.local.json')
            token = bundle / config['paths']['token_file']
            # Deployment expects a relative token path so both hosts receive the same secret.
            if Path(config['paths']['token_file']).is_absolute():
                raise ValueError('Use a relative paths.token_file for deployment')
            token.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            token.write_text(config.token + '\n')
            token.chmod(0o600)
            commands = [ssh_args(config, selected) + [peer, shlex.join(['mkdir', '-p', root])],
                        ssh_args(config, selected, scp=True) + ['-r', str(bundle) + '/.', peer + ':' + shlex.quote(root)],
                        ssh_args(config, selected) + [peer, 'cd ' + shlex.quote(root) + ' && chmod 600 config.local.json ' + shlex.quote(config['paths']['token_file']) + ' && sudo ./scripts/companion install ' + selected]]
            for command in commands:
                if dry_run:
                    print(shlex.join(command))
                else:
                    subprocess.run(command, check=True)


def fetch(url, target, expected=''):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not expected or hashlib.sha256(target.read_bytes()).hexdigest() == expected:
            return
    partial = target.with_suffix(target.suffix + '.part')
    try:
        with urlopen(url, timeout=120) as source, partial.open('wb') as output:
            shutil.copyfileobj(source, output)
        if expected and hashlib.sha256(partial.read_bytes()).hexdigest() != expected:
            raise ValueError('Model SHA256 mismatch: ' + target.name)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def download_models(config):
    stt, tts = config['models']['stt'], config['models']['tts']
    from .recognition import prepare
    prepare(config)
    from .sound_events import prepare as prepare_sounds
    prepare_sounds(config)
    destination = config.path(stt['path'])
    if config['conversation'].get('recognition', {}).get('backend') != 'faster_whisper' and not destination.exists():
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'model.zip'
            fetch(stt['download_url'], archive, stt['sha256'])
            with zipfile.ZipFile(archive) as model:
                for member in model.infolist():
                    path = (Path(temporary) / member.filename).resolve()
                    if not path.is_relative_to(Path(temporary).resolve()):
                        raise ValueError('Unsafe model archive path')
                model.extractall(temporary)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(Path(temporary) / stt['archive_root']), destination)
    target = config.path(tts['path'])
    fetch(tts['download_url'], target, tts['sha256'])
    fetch(tts['config_url'], Path(str(target) + '.json'))


def service_unit(config, role, group):
    target = config['deployment'][role]
    root = target['root']
    if any(c.isspace() or c in '%"\\' for c in root):
        raise ValueError('Service installation path cannot contain whitespace or escapes')
    python = str(Path(root) / target['venv_dir'] / 'bin/python')
    data = str(config.path(config['paths']['data_dir']))
    return f'''[Unit]
Description=Reachy Companion {group}
Wants=network-online.target
After=network-online.target
[Service]
User={target['user']}
WorkingDirectory={root}
Environment=PYTHONPATH={root}/src
Environment=OMP_NUM_THREADS=2
ExecStart={python} -m reachy_companion --config {root}/config.local.json {group} serve
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={data}
UMask=0077
KillMode=control-group
[Install]
WantedBy=multi-user.target
'''


def install(config, role, skip_models=False):
    if os.geteuid() != 0:
        raise PermissionError('Run install with sudo on the target device')
    target = config['deployment'][role]
    if config.root != Path(target['root']).resolve():
        raise ValueError('Configuration directory must match deployment.' + role + '.root')
    subprocess.run(['apt-get', 'update'], check=True)
    packages = list(target['apt_packages'])
    if role == 'hub' and config['voice']['mode'] == 'local':
        packages = list(dict.fromkeys(packages + config['deployment']['worker']['apt_packages']))
    subprocess.run(['apt-get', 'install', '-y', *packages], check=True)
    venv = config.root / target['venv_dir']
    if not (venv / 'bin/python').exists():
        subprocess.run([target['python'], '-m', 'venv', str(venv)], check=True)
    pip = str(venv / 'bin/pip')
    subprocess.run([pip, 'install', '-r', str(config.root / 'requirements' / (('worker' if role == 'hub' and config['voice']['mode'] == 'local' else role) + '.lock'))], check=True)
    subprocess.run([pip, 'install', '--no-deps', str(config.root)], check=True)
    data = config.path(config['paths']['data_dir'])
    data.mkdir(parents=True, exist_ok=True)
    if (role == 'worker' or (role == 'hub' and config['voice']['mode'] == 'local')) and not skip_models:
        download_models(config)
    subprocess.run(['chown', '-R', target['user'] + ':' + target['user'], str(config.root)], check=True)
    groups = ('hub', 'voice') if role == 'hub' else (('worker',) if role == 'worker' else ('agent',))
    if len(target['services']) != len(groups):
        raise ValueError('Invalid number of service names')
    for name, group in zip(target['services'], groups):
        if not name.replace('-', '').isalnum():
            raise ValueError('Invalid service name')
        (Path('/etc/systemd/system') / (name + '.service')).write_text(service_unit(config, role, group))
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', *target['services']], check=True)
    subprocess.run(['systemctl', 'restart', *target['services']], check=True)
    if role == 'robot' and config['security']['robot']['restrict_to_hub']:
        from .firewall import main
        main(config, 'install')


def update(config, role):
    """Update dependencies and units after git pull; preserve robot firewall."""
    if os.geteuid() != 0:
        raise PermissionError('Run update with sudo on the device')
    target = config['deployment'][role]
    if config.root != Path(target['root']).resolve():
        raise ValueError('Configuration directory must match deployment root')
    venv = config.root / target['venv_dir']
    if not (venv / 'bin/python').exists():
        raise ValueError('Run install first to create the device environment')
    selected = 'worker' if role == 'hub' and config['voice']['mode'] == 'local' else role
    lock = config.root / 'requirements' / (selected + '.lock')
    data = config.path(config['paths']['data_dir'])
    data.mkdir(parents=True, exist_ok=True)
    marker = data / (role + '-dependencies.sha256')
    digest = hashlib.sha256(lock.read_bytes()).hexdigest()
    if not marker.exists() or marker.read_text().strip() != digest:
        subprocess.run([str(venv / 'bin/pip'), 'install', '-r', str(lock)], check=True)
        marker.write_text(digest + '\n')
    groups = ('hub', 'voice') if role == 'hub' else (('worker',) if role == 'worker' else ('agent',))
    if len(groups) != len(target['services']):
        raise ValueError('Invalid service list')
    for name, group in zip(target['services'], groups):
        if not name.replace('-', '').isalnum():
            raise ValueError('Invalid service name')
        (Path('/etc/systemd/system') / (name + '.service')).write_text(service_unit(config, role, group))
    # Units use PYTHONPATH=src: pulled code is used without rebuilding the wheel.
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'restart', *target['services']], check=True)
    subprocess.run(['systemctl', 'is-active', *target['services']], check=True)
    print('Updated services; firewall was preserved.')
