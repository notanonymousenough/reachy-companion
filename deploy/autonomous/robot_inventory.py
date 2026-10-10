"""Finite read-only inventory; process names are clues, never an ownership proof."""
import argparse
from importlib import metadata
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((args.production_root/'config.local.json').read_text())
    token_path = Path(config['paths']['token_file'])
    if not token_path.is_absolute(): token_path = args.production_root/token_path
    token = token_path.read_text().strip()
    opener = build_opener(ProxyHandler({}))
    def get(url, authenticated=False):
        headers = {'Authorization':'Bearer '+token} if authenticated else {}
        try:
            with opener.open(Request(url, headers=headers), timeout=3) as response:
                raw = response.read(65537)
            if len(raw)>65536: raise ValueError('Response too large')
            return json.loads(raw)
        except Exception as exc:
            return {'inventory_error':type(exc).__name__}
    agent = urlsplit(config['network']['agent_url'])
    operator = get('http://127.0.0.1:'+str(agent.port)+'/status', True)
    report = dict(mode='read_only_robot_inventory', physical_commands=0,
                  operator={key: operator[key] for key in ('microphone_enabled','capture_active','phase',
                    'agent_boot_id','operator_epoch','microphone_epoch','speech_epoch','microphone_state_error','inventory_error') if key in operator}, native={})
    for name, path in [('daemon','daemon/status'), ('ownership','daemon/robot-app-lock-status'),
                       ('moves','move/running'), ('motors','motors/status'), ('media','media/status'),
                       ('camera_specs','camera/specs')]:
        report['native'][name] = get('http://127.0.0.1:8000/api/'+path)
    report['python_process_hints'] = []
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit(): continue
        try:
            command = (directory/'cmdline').read_bytes().split(b'\0')
            executable = Path(command[0].decode()).name
            if 'python' not in executable.lower(): continue
            # Do not export argv/env: either can contain secrets or private text.
            hint = next((Path(arg.decode()).name for arg in command[1:3]
                         if arg.endswith(b'.py')), 'unknown_python_entrypoint')
            report['python_process_hints'].append(dict(pid=int(directory.name), executable=executable, entrypoint=hint))
        except (OSError, UnicodeError): pass
    report['python_process_hints'] = report['python_process_hints'][:32]
    try: report['installed_sdk_version'] = metadata.version('reachy-mini')
    except metadata.PackageNotFoundError: report['installed_sdk_version'] = None
    report['exclusive_writer_verified'] = False
    with args.output.open('x', encoding='utf-8') as out: json.dump(report, out, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(args.output), operator={key:report['operator'].get(key)
          for key in ('microphone_enabled','capture_active','phase','inventory_error')},
          motors=report['native']['motors'], sdk_version=report['installed_sdk_version'],
          python_process_hints=report['python_process_hints'], exclusive_writer_verified=False)))


if __name__ == '__main__': main()
