"""Finite read-only inventory; process names are clues, never an ownership proof."""
import argparse
from importlib import metadata
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler


def process_hint(command):
    """Export only fixed known roles, never arguments, paths or environment."""
    if b'-m' in command:
        index=command.index(b'-m')
        if command[index+1:index+2]==[b'reachy_companion'] and command[-2:]==[b'agent',b'serve']:return 'companion_agentserve'
    if any(Path(arg.decode(errors='replace')).name=='reachy-mini-daemon' for arg in command[1:3]):return 'factory_reachy_mini_daemon'
    return 'unknown_python_entrypoint'


def pcm_inventory(config,home=Path.home(),proc=Path('/proc/asound')):
    """Read files only; opening a PCM handle would initialize audio."""
    device=config['audio']['playback_device']
    report=dict(audio_open_attempts=0,cursor_verified=False,exclusive_writer_verified=False,
        pause_supported='not_probed',configured_device=device if device=='plug:reachymini_audio_sink' else 'other_configured_device',
        sink_type='unknown',slave_rate=None,slave_channels=None,playback_streams=[])
    path=home/'.asoundrc'
    if path.is_file() and path.stat().st_size<=65536:
        text=path.read_text();match=re.search(r'pcm\.reachymini_audio_sink\s*\{',text)
        if match:
            depth=1;end=match.end()
            while end<len(text) and depth:
                depth+=(text[end]=='{')-(text[end]=='}');end+=1
            if depth==0:
                block=text[match.end():end-1]
                kind=re.search(r'^\s*type\s+(\w+)',block,re.M)
                if kind and kind[1] in ('dmix','plug','hw'):report['sink_type']=kind[1]
                for name,key in [('rate','slave_rate'),('channels','slave_channels')]:
                    value=re.search(r'\b'+name+r'\s+(\d+)\b',block)
                    if value:report[key]=int(value[1])
    for path in sorted(proc.glob('card*/pcm*p/sub*/status'))[:16]:
        try:
            text=path.read_text()[:8192];state=re.search(r'^state:\s*(\w+)',text,re.M);owner=re.search(r'^owner_pid\s*:\s*(\d+)',text,re.M)
            report['playback_streams'].append(dict(state='closed' if text.strip()=='closed' else state[1] if state and state[1] in ('OPEN','SETUP','PREPARED','RUNNING','XRUN','DRAINING','PAUSED','SUSPENDED','DISCONNECTED') else 'unknown',
                owner_pid=int(owner[1]) if owner else None))
        except OSError:report['playback_streams'].append(dict(state='unreadable',owner_pid=None))
    report['libasound_present']=Path('/usr/lib/aarch64-linux-gnu/libasound.so.2').is_file()
    return report


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
        if not directory.name.isdigit() or int(directory.name)==os.getpid(): continue
        try:
            command = (directory/'cmdline').read_bytes().split(b'\0')
            executable = Path(command[0].decode()).name
            if 'python' not in executable.lower(): continue
            # Do not export argv/env: either can contain secrets or private text.
            hint = process_hint(command)
            report['python_process_hints'].append(dict(pid=int(directory.name), executable=executable, entrypoint=hint))
        except (OSError, UnicodeError): pass
    report['python_process_hints'] = report['python_process_hints'][:32]
    try: report['installed_sdk_version'] = metadata.version('reachy-mini')
    except metadata.PackageNotFoundError: report['installed_sdk_version'] = None
    report['exclusive_writer_verified'] = False
    report['pcm_readiness']=pcm_inventory(config)
    with args.output.open('x', encoding='utf-8') as out: json.dump(report, out, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(args.output), operator={key:report['operator'].get(key)
          for key in ('microphone_enabled','capture_active','phase','inventory_error')},
          motors=report['native']['motors'], sdk_version=report['installed_sdk_version'],
          python_process_hints=report['python_process_hints'], exclusive_writer_verified=False)))


if __name__ == '__main__': main()
