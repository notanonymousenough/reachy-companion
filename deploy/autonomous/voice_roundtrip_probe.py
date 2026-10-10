"""Real PC TTS/STT via existing Hub endpoints. Synthetic bytes in RAM only."""
import argparse,base64,json,sys,threading,time
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from reachy_companion.config import Config
from reachy_companion.autonomous.speech_adapter import HttpTTS


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    cfg=Config(a.config);http=build_opener(ProxyHandler({}));text='Алиса, сколько будет два плюс два?'
    def call(url,payload=None):
        q=Request(url,data=None if payload is None else json.dumps(payload).encode(),headers={'Authorization':'Bearer '+cfg.token,'Content-Type':'application/json'})
        with http.open(q,timeout=30) as response:return json.load(response)
    report=dict(mode='actual_pc_synthetic_tts_stt_roundtrip',accepted=False,speaker_commands=0,capture_commands=0,motor_commands=0,raw_retained=False)
    report['worker_before']=call(cfg['network']['compute_url']+'/health');report['hub_voice']=call(cfg['network']['voice_url']+'/health')
    pcm=bytearray();start=time.monotonic();first=None
    try:
        for chunk in HttpTTS(cfg['network']['voice_url'],cfg.token,rate=16000,max_event=cfg['streaming']['max_event_bytes'],timeout=20).stream(text,threading.Event()):
            if first is None:first=time.monotonic()-start
            if len(pcm)+len(chunk)>16000*2*15:raise RuntimeError('Finite synthetic PCM bound')
            pcm.extend(chunk)
        report.update(tts_elapsed_s=time.monotonic()-start,tts_first_pcm_s=first,pcm_frames=len(pcm)//2)
        start=time.monotonic();result=call(cfg['network']['compute_url']+'/transcribe',dict(pcm_base64=base64.b64encode(pcm).decode()))
        report.update(stt_elapsed_s=time.monotonic()-start,synthetic_transcript=result['transcript'])
        normalized=__import__('re').sub(r'\b2\b','два',result['transcript'].lower())
        report['accepted']=normalized.count('два')>=2 and 'плюс' in normalized and ('алис' in result['transcript'].lower() or 'сколько' in result['transcript'].lower())
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)[:128]
    finally:
        pcm.clear();report['worker_after']=call(cfg['network']['compute_url']+'/health')
        with a.output.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if not report['accepted']:raise SystemExit(2)
if __name__=='__main__':main()
