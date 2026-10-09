"""Ordinary scp/SSH against explicit private config. Never reads secret contents."""
import argparse
import json
from pathlib import Path,PurePosixPath
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['copy','tunnel'])
    parser.add_argument('--config',default='config.workflows.local.json')
    parser.add_argument('--duration',type=int,default=60)
    parser.add_argument('files',nargs='*')
    args=parser.parse_args();config=json.loads(Path(args.config).read_text())
    for key in ('host','user','identity_file','known_hosts_file','host_key_alias'):
        if not config.get(key):raise ValueError('Configure '+key)
    remote=PurePosixPath(config['remote_dir'])
    if remote.is_absolute() or '..' in remote.parts:raise ValueError('Remote directory must be relative')
    options=['-o','UserKnownHostsFile='+config['known_hosts_file'],'-o','HostKeyAlias='+config['host_key_alias'],
             '-o','StrictHostKeyChecking=yes','-o','IdentitiesOnly=yes','-i',config['identity_file']]
    target=config['user']+'@'+config['host']
    if args.command=='copy':
        for filename in args.files:
            path=Path(filename).resolve()
            if path.parent != Path(__file__).resolve().parent or path.suffix not in ('.py','.json','.yaml') or '.local.' in path.name:
                raise ValueError('Only reviewed deployment source files may be copied')
        subprocess.run(['scp',*options,*args.files,target+':'+str(remote)+'/'],check=True)
    else:
        if not 1 <= args.duration <= 3600:raise ValueError('Bounded tunnel duration must be1–3600s')
        # Ports are localhost only; host key checked. No VPN/route changes.
        process=subprocess.Popen(['ssh',*options,'-o','ExitOnForwardFailure=yes','-N',
            '-L',f"127.0.0.1:{config['editor_local_port']}:127.0.0.1:{config['editor_remote_port']}",
            '-L',f"127.0.0.1:{config['broker_local_port']}:127.0.0.1:{config['broker_remote_port']}",target])
        try:
            try:code=process.wait(timeout=args.duration)
            except subprocess.TimeoutExpired:code=0
            if code:raise subprocess.CalledProcessError(code,process.args)
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


if __name__=='__main__':main()
