"""Finite actual PCM cursor capability. Synthetic beep RAM only, no capture/TTS."""
import argparse,json,math,struct,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from reachy_companion.autonomous.alsa_pcm import AlsaPCM
from reachy_companion.config import Config
from reachy_companion.hub import Hub
from reachy_companion.autonomous.contracts import uid


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--allow-output',action='store_true');p.add_argument('--complete',action='store_true');a=p.parse_args()
    if not a.allow_output or a.output.exists():raise ValueError('Explicit finite synthetic speaker test required')
    cfg=Config(a.config);hub=Hub(cfg)
    def operator():
        s=hub.agent('/status');return {k:s[k] for k in ('agent_boot_id','microphone_epoch','microphone_enabled','capture_active','phase')}
    before=operator()
    backend=AlsaPCM(cfg['audio']['playback_device']);stream=uid();backend.reserve(stream)
    report=dict(mode='actual_owned_alsa_synthetic_pcm',accepted=False,capture_commands=0,motor_commands=0,raw_audio_retained=False,operator_before=before)
    samples=[];written=0;began=time.monotonic()
    try:
        backend.start(stream,16000)
        while time.monotonic()-began<.6:
            count=min(1600,max(0,4000-written)) if a.complete else 1600
            if count:
                pcm=b''.join(struct.pack('<h',int(400*math.sin(2*math.pi*440*(written+i)/16000))) for i in range(count))
                written+=backend.write(stream,pcm)
            elif a.complete:report['drain_complete']=backend.finish(stream)
            samples.append(backend.progress(stream));time.sleep(.005)
        report['written_frames']=written;report['progress_samples']=len(samples);report['max_consumed_frames']=max(x['consumed_frames'] for x in samples)
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)[:128]
    finally:
        stop_at=time.monotonic();report['stop']=backend.stop(stream);report['stop_elapsed_s']=time.monotonic()-stop_at
        report['operator_after']=operator();report['operator_unchanged']=before==report['operator_after']
        report['consumed_progress_verified']=bool(samples) and all(s['verified'] is True for s in samples) and max(s['consumed_frames'] for s in samples)>0
        report['accepted']=report['consumed_progress_verified'] and report['stop']['verified_stopped'] and report['stop_elapsed_s']<=.3 and report['operator_unchanged']
        report['terminal_cursor_verified']=report['stop']['verified']
        report['resume_cursor_verified']=report['stop']['verified'] and report['stop']['consumed_frames']<written
        with a.output.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(report),flush=True)
    if not report['accepted']:raise SystemExit(2)
if __name__=='__main__':main()
