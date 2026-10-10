"""Pinned, muted-only Agent update with preflight and rollback; no actor API."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production-root',type=Path,required=True)
    parser.add_argument('--expected-base',required=True);parser.add_argument('--target',required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if any(not re.fullmatch('[0-9a-f]{40}',value) for value in (args.expected_base,args.target)):parser.error('Pinned full commit SHA required')
    if args.output.exists():raise FileExistsError(args.output)
    root=args.production_root.resolve();cfg_path=root/'config.local.json';cfg_bytes=cfg_path.read_bytes();cfg=json.loads(cfg_bytes)
    token_path=Path(cfg['paths']['token_file']);token_path=token_path if token_path.is_absolute() else root/token_path
    token=token_path.read_text().strip();port=urlsplit(cfg['network']['agent_url']).port
    data=Path(cfg['paths']['data_dir']);data=data if data.is_absolute() else root/data
    state_path=data/'microphone-state.json';state_bytes=state_path.read_bytes()
    if len(state_bytes)>4096 or json.loads(state_bytes).get('enabled') is not False:raise RuntimeError('Persisted operator mute required')
    opener=build_opener(ProxyHandler({}))
    def get(path,agent=False):
        request=Request(('http://127.0.0.1:'+str(port) if agent else 'http://127.0.0.1:8000/api')+path,
                        headers={'Authorization':'Bearer '+token} if agent else {})
        with opener.open(request,timeout=2) as response:raw=response.read(65537)
        if len(raw)>65536:raise ValueError('Status bound')
        return json.loads(raw)
    def operator():
        value=get('/status',True)
        return {key:value.get(key) for key in ('microphone_enabled','capture_active','phase','agent_boot_id','microphone_epoch','microphone_state_error','volume_percent')}
    def gate():
        value=operator()
        if value['microphone_enabled'] is not False or value['capture_active'] is not False or value['phase']!='paused' or value['microphone_state_error'] is not None:
            raise RuntimeError('Actual operator paused/muted gate')
        if get('/motors/status')!={'mode':'disabled'} or get('/move/running')!=[]:raise RuntimeError('Native disabled/no-move gate')
        return value
    def command(argv,timeout=15):
        result=subprocess.run(argv,cwd=root,capture_output=True,text=True,timeout=timeout)
        if result.returncode:raise RuntimeError('Command failed: '+argv[0])
        return result.stdout.strip()
    def git(*parts):return command(['git',*parts])
    before=gate()
    pid=command(['systemctl','show','reachy-voice-agent.service','--property=MainPID','--value'])
    if not pid.isdigit() or int(pid)<=0:raise RuntimeError('Active Agent PID required')
    process=Path('/proc')/pid
    argv=[arg.decode() for arg in (process/'cmdline').read_bytes().split(b'\0') if arg]
    if ((process/'cwd').resolve()!=root or '-m' not in argv or argv[argv.index('-m')+1]!='reachy_companion'
            or argv[-2:]!=['agent','serve'] or '--config' not in argv or Path(argv[argv.index('--config')+1]).resolve()!=cfg_path):
        raise RuntimeError('Unexpected service entrypoint')
    if git('rev-parse','HEAD')!=args.expected_base or git('status','--porcelain'):raise RuntimeError('Production base/clean-worktree gate')
    # Fetch does not change the checkout or start services. Review the exact diff.
    git('fetch','origin','codex/autonomous-shadow')
    if git('rev-parse',args.target)!=args.target:raise RuntimeError('Target missing')
    changed=git('diff','--name-only',args.expected_base,args.target).splitlines()
    critical=[path for path in changed if path.startswith('src/reachy_companion/')
              and path not in ('src/reachy_companion/agent.py','src/reachy_companion/microphone.py','src/reachy_companion/assets/autonomous-contracts.json')
              and not path.startswith('src/reachy_companion/autonomous/')]
    if critical or any(path in changed for path in ('config.example.json','src/reachy_companion/deployment.py')):
        raise RuntimeError('Unexpected active-runtime changes')
    report=dict(mode='pinned_muted_agent_update',base=args.expected_base,target=args.target,apply=args.apply,
                operator_before=before,changed_active_modules=[path for path in changed if path in ('src/reachy_companion/agent.py','src/reachy_companion/microphone.py')],
                rollback=False,motor_or_speech_commands_by_probe=0,microphone_enabled_by_probe=False)
    if args.apply:
        try:
            gate()  # Refuse a changed operator state immediately before stop.
            command(['sudo','-n','systemctl','stop','reachy-voice-agent.service'])
            if state_path.read_bytes()!=state_bytes:raise RuntimeError('Operator file changed before update')
            git('checkout','--detach',args.target)
            command(['sudo','-n','systemctl','start','reachy-voice-agent.service'])
            end=time.monotonic()+15
            while time.monotonic()<end:
                try:
                    after=gate()
                    if not isinstance(after['agent_boot_id'],str) or type(after['microphone_epoch']) is not int or after['microphone_epoch']!=json.loads(state_bytes).get('epoch',0):raise RuntimeError('New boot/epoch gate')
                    if after['agent_boot_id']==before['agent_boot_id'] or after['volume_percent']!=before['volume_percent']:raise RuntimeError('Boot/volume preservation gate')
                    break
                except (OSError,RuntimeError):time.sleep(.2)
            else:raise TimeoutError('Updated Agent readiness')
            if state_path.read_bytes()!=state_bytes or cfg_path.read_bytes()!=cfg_bytes:raise RuntimeError('Private configuration/operator state changed')
            report.update(operator_after=after,production_state_unchanged=True,configuration_unchanged=True,
                          active=command(['systemctl','is-active','reachy-voice-agent.service'])=='active')
        except BaseException:
            # Never auto-unmute or change native daemon/motor state to recover.
            command(['sudo','-n','systemctl','stop','reachy-voice-agent.service'])
            git('checkout','--detach',args.expected_base)
            report['rollback']=True
            if state_path.read_bytes()==state_bytes and cfg_path.read_bytes()==cfg_bytes:
                command(['sudo','-n','systemctl','start','reachy-voice-agent.service'])
            else:report['recovery_start_withheld']='Operator/configuration changed; manual audit required'
            with args.output.open('x') as output:json.dump(report,output,indent=2)
            raise
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps(report))


if __name__=='__main__':main()
