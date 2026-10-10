"""Finite real network measurements with simulated LLM/PCM and no output."""
import argparse
import json
from pathlib import Path
import sys
import threading
import time
from urllib.request import Request,build_opener,ProxyHandler
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from reachy_companion.config import Config
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.playback import Playback,ReplayPCM
from reachy_companion.autonomous.speech_adapter import SpeechAdapter
from reachy_companion.autonomous.runtime import ReplayGateway,Scheduler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--scheduler-config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    cfg=Config(args.config);settings=load(args.scheduler_config);settings['period_s']=.01
    settings['context']['enabled']=False;settings['workflows']['enabled']=False
    opener=build_opener(ProxyHandler({}));samples={'agent':[],'pc':[]};sample_lock=threading.Lock();supported=[]
    def request(url,node):
        started=time.monotonic();error=None;value=None
        try:
            req=Request(url,headers={'Authorization':'Bearer '+cfg.token})
            with opener.open(req,timeout=1) as response:raw=response.read(65537)
            if len(raw)>65536:raise ValueError('Status cap')
            value=json.loads(raw)
        except Exception as exc:error=type(exc).__name__
        finally:
            with sample_lock:samples[node].append(dict(elapsed_ms=(time.monotonic()-started)*1000,error=error))
        if error:raise RuntimeError(error)
        return value
    def operator():
        # Old production Agent lacks /operator. /status is read-only; never
        # invent a missing motion policy to grant output in this measurement.
        value=request(cfg['network']['agent_url']+'/status','agent')
        with sample_lock:supported.append('motion_policy' in value)
        return {key:value[key] for key in ('agent_boot_id','microphone_epoch','microphone_enabled','motion_policy','microphone_state_error') if key in value}
    def pc():
        for _ in range(6):
            try:request(cfg['network']['compute_url']+'/health','pc')
            except Exception:pass
            time.sleep(.1)
    class NoTTS:
        def stream(self,*args):raise AssertionError('Probe never dispatches TTS')
        def cancel(self):pass
    backend=ReplayPCM();playback=Playback(backend,allow_simulated=True)
    adapter=SpeechAdapter(playback,NoTTS(),operator);startup=time.monotonic()
    gateway=ReplayGateway();scheduler=Scheduler(settings,gateway,speech_adapter=adapter)
    startup_ms=(time.monotonic()-startup)*1000
    job=threading.Thread(target=pc,daemon=True);job.start()
    start=time.monotonic();latencies=[]
    try:
        while time.monotonic()-start<3:
            before=time.monotonic();scheduler.advance();latencies.append((time.monotonic()-before)*1000);time.sleep(.002)
    finally:adapter.close();scheduler.closed=True
    job.join(1)
    with sample_lock:observed={key:list(value) for key,value in samples.items()};schema=all(supported) if supported else False
    report=dict(mode='real_hub_agent_pc_network_simulated_scheduler',accepted=False,
        physical_commands=0,model_inference=False,private_inputs_exported=0,
        network_samples=observed,agent_operator_schema_supported=schema,
        scheduler_startup_ms=startup_ms,
        max_scheduler_advance_ms=max(latencies),scheduler_fast_calls=gateway.fast_calls,
        pcm_streams=len(backend.streams),operator_execution_busy=adapter.status()['operator_execution_busy'],
        pc_execution_busy=job.is_alive(),rejected_refreshes=adapter.status()['rejected_refreshes'])
    report['accepted']=(gateway.fast_calls>20 and max(latencies)<100 and not backend.streams
        and all(observed.values()) and all(row['error'] is None for rows in observed.values() for row in rows))
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps(report),flush=True)
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
