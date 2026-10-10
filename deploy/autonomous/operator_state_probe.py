"""Finite isolated Agent restart probe; production state is read-only, no actors."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler

from reachy_companion.agent import Agent
from reachy_companion.config import Config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('production-root','directory','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();config=Config(args.production_root/'config.local.json')
    opener=build_opener(ProxyHandler({}));port=urlsplit(config['network']['agent_url']).port
    def operator():
        request=Request('http://127.0.0.1:'+str(port)+'/status',headers={'Authorization':'Bearer '+config.token})
        with opener.open(request,timeout=2) as response:value=json.load(response)
        return {key:value.get(key) for key in ('microphone_enabled','capture_active','phase','agent_boot_id','microphone_epoch','microphone_state_error')}
    before=operator()
    if before['microphone_enabled'] is not False or before['capture_active'] is not False:raise RuntimeError('Actual operator mute gate')
    state_path=config.path(config['paths']['data_dir'])/'microphone-state.json'
    original=state_path.read_bytes()
    if len(original)>4096 or json.loads(original).get('enabled') is not False:raise RuntimeError('Persisted operator mute gate')
    args.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    instances=[]
    try:
        with tempfile.TemporaryDirectory(prefix='operator-probe-',dir=args.directory) as directory:
            fixture_path=Path(directory)/'microphone-state.json';fixture_path.write_bytes(original);fixture_path.chmod(0o600)
            config.data['paths']['data_dir']=directory
            for name in ('expressions','barge_in','sound_reactions'):config.data['conversation'][name]['enabled']=False
            def forbidden(*args,**kwargs):raise RuntimeError('Probe actor/network call forbidden')
            with patch('reachy_companion.agent.subprocess.Popen',side_effect=forbidden),patch('reachy_companion.agent.subprocess.run',side_effect=forbidden),patch.object(Agent,'request',side_effect=forbidden):
                first=Agent(config);instances.append(first);old=first.microphone_epoch
                started=time.monotonic();first.set_microphone(False);persist_s=time.monotonic()-started
                second=Agent(config);instances.append(second)
                restarted=second.status()
                checks=dict(mute_survives_restart=restarted['microphone_enabled'] is False and not restarted['listening'],
                            epoch_survives_restart=second.microphone_epoch==old+1,
                            process_boot_changes=first.agent_boot_id!=second.agent_boot_id,
                            stale_reply_cancelled=first.voice('/say',{'text':'synthetic probe'},expected_epoch=old)['cancelled'],
                            muted_manual_cancelled=second.manual('/say',{'text':'synthetic probe'})['cancelled'])
                # Change only the isolated fixture RAM gate; the production
                # switch/file and physical capture stay disabled throughout.
                second.microphone.enabled=True
                replay={'pcm':b'\0\0','cursor':0}
                result=second.voice('/say',{},replay=replay)
                checks['unverified_resume_cancelled']=result.get('cancelled') is True and result.get('resume_blocked_reason')=='unverified_pcm_cursor' and second.resume_audio is None
                second.microphone.enabled=False
                if not all(checks.values()):raise RuntimeError('Isolated Agent acceptance failed')
        after=operator()
        unchanged=hashlib.sha256(original).digest()==hashlib.sha256(state_path.read_bytes()).digest()
        if not unchanged or after!=before:raise RuntimeError('Actual production operator state changed')
        report=dict(mode='isolated_operator_agent_restart',checks=checks,durable_switch_s=persist_s,
                    actual_operator_before=before,actual_operator_after=after,production_state_unchanged=unchanged,
                    physical_commands=0,audio_capture_started=False,production_restarted=False,fixture_files_removed=True)
        with args.output.open('x') as output:json.dump(report,output,indent=2)
        print(json.dumps(report))
    finally:
        for agent in instances:agent.stopping.set()


if __name__=='__main__':main()
