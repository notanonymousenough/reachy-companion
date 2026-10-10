"""One authorized neutral voice question, bounded local capture and PC STT.

No automatic dialogue/LLM reply or repeat wake phrase. Raw audio stays in RAM
and travels only to the configured owned compute PC. Unknown speaker identity.
"""
import argparse,base64,json,re,select,subprocess,sys,threading,time
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from reachy_companion.config import Config
from reachy_companion.hub import Hub
from reachy_companion.autonomous.alsa_pcm import AlsaPCM
from reachy_companion.autonomous.speech_adapter import HttpTTS
from reachy_companion.autonomous.contracts import uid


def cleanup(config,owner_file):
    if not owner_file.exists():return
    owner=json.loads(owner_file.read_text());hub=Hub(Config(config));actual=hub.agent('/operator')
    if actual['agent_boot_id']==owner['agent_boot_id'] and actual['microphone_epoch']==owner['owned_microphone_epoch']:
        hub.agent('/microphone',dict(enabled=False))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('config','output','owner-file'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--allow-capture-output',action='store_true');p.add_argument('--cleanup-only',action='store_true');a=p.parse_args()
    if a.cleanup_only:cleanup(a.config,a.owner_file);return
    if not a.allow_capture_output or a.output.exists() or a.owner_file.exists():raise ValueError('Explicit fresh finite physical voice practice required')
    cfg=Config(a.config);hub=Hub(cfg);before=hub.agent('/operator')
    if before['microphone_enabled'] or before['capture_active'] or before['phase']!='paused':raise RuntimeError('Idle test owner baseline required')
    if before['motion_policy']['quiet'] or before['motion_policy']['privacy_all']:raise RuntimeError('Operator quiet/privacy blocks practice')
    question='Алиса, сколько будет два плюс два?';opener=build_opener(ProxyHandler({}));pcm=bytearray();captured=bytearray();capture=None;backend=None;stream=uid()
    report=dict(mode='one_finite_external_speaker_practice',accepted=False,question=question,rounds=1,
        private_cloud_inputs=0,automatic_repeat_wake_phrase=False,raw_audio_retained=False,operator_before=before,motor_commands=0)
    owner=dict(agent_boot_id=before['agent_boot_id'],owned_microphone_epoch=before['microphone_epoch']+1)
    with a.owner_file.open('x') as f:json.dump(owner,f);f.flush();__import__('os').fsync(f.fileno())
    try:
        enabled=hub.agent('/microphone',dict(enabled=True,listen=False))
        report['microphone_enabled']=enabled['microphone_enabled'];owned_epoch=enabled['microphone_epoch']
        if owned_epoch!=owner['owned_microphone_epoch']:raise RuntimeError('Operator changed during test activation')
        def valid():
            actual=hub.agent('/operator');policy=actual['motion_policy']
            return (actual['agent_boot_id']==owner['agent_boot_id'] and actual['microphone_epoch']==owned_epoch
                and actual['microphone_enabled'] is True and not policy['quiet'] and not policy['privacy_all']
                and policy['epoch']==before['motion_policy']['epoch'])
        start=time.monotonic();first=None
        for chunk in HttpTTS(cfg['network']['voice_url'],cfg.token,rate=16000,max_event=cfg['streaming']['max_event_bytes'],timeout=10).stream(question,threading.Event()):
            if first is None:first=time.monotonic()-start
            if len(pcm)+len(chunk)>16000*2*15 or not valid():raise RuntimeError('TTS/authority bound')
            pcm.extend(chunk)
        report.update(tts_elapsed_s=time.monotonic()-start,tts_first_pcm_s=first)
        backend=AlsaPCM(cfg['audio']['playback_device']);backend.reserve(stream);backend.start(stream,16000)
        written=0;start=time.monotonic();deadline=start+6;next_policy=0;max_consumed=0
        while True:
            now=time.monotonic()
            if now>=deadline:raise RuntimeError('Finite question playback timeout')
            if now>=next_policy:
                if not valid():raise RuntimeError('Operator withdrew speaker/capture')
                next_policy=now+.1
            if written<len(pcm)//2:written+=backend.write(stream,bytes(pcm[written*2:(written+1600)*2]))
            else:
                if backend.finish(stream):break
            max_consumed=max(max_consumed,backend.progress(stream)['consumed_frames']);time.sleep(.005)
        report['playback_elapsed_s']=time.monotonic()-start;report['question_frames_consumed']=backend.progress(stream)['consumed_frames']
        report['speaker_stop']=backend.stop(stream);backend=None;pcm.clear()
        # This window excludes the owned playback itself. The response speaker
        # remains unknown; an arithmetic match is not biometric identity.
        capture=subprocess.Popen(['arecord','-q','-D',cfg['audio']['capture_device'],'-t','raw','-f','S16_LE','-r','16000','-c','1','-d','8'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        __import__('os').set_blocking(capture.stdout.fileno(),False);start=time.monotonic();deadline=start+9;next_policy=0
        while capture.poll() is None:
            now=time.monotonic()
            if now>=deadline:raise RuntimeError('Capture deadline')
            if now>=next_policy:
                if not valid():raise RuntimeError('Operator withdrew capture')
                next_policy=now+.1
            ready,_,_=select.select([capture.stdout],[],[],.02)
            if ready:
                part=__import__('os').read(capture.stdout.fileno(),8192)
                if len(captured)+len(part)>16000*2*8:raise RuntimeError('Capture byte cap')
                captured.extend(part)
        captured.extend(capture.stdout.read() or b'');capture.wait(timeout=1)
        if capture.returncode or len(captured)>16000*2*8 or len(captured)%2:raise RuntimeError('Capture failed')
        report.update(capture_elapsed_s=time.monotonic()-start,captured_frames=len(captured)//2,capture_reaped=True)
        start=time.monotonic()
        request=Request(cfg['network']['compute_url']+'/transcribe',data=json.dumps(dict(pcm_base64=base64.b64encode(captured).decode())).encode(),headers={'Authorization':'Bearer '+cfg.token,'Content-Type':'application/json'})
        with opener.open(request,timeout=12) as response:recognized=json.load(response)['transcript']
        report['stt_elapsed_s']=time.monotonic()-start;captured.clear()
        words=re.findall(r'\w+',recognized.lower());own=set(re.findall(r'\w+',question.lower()))
        overlap=sum(w in own for w in words)/len(words) if words else 0
        report.update(speech_detected=bool(words),own_text_overlap=overlap,speaker_identity='unknown',speaker_identity_confidence=0,
            external_answer='4' if any(w in ('4','четыре') for w in words) and not any(w in ('нет','не') for w in words) else None,
            transcript_retained=False,automatic_reply=False)
        report['accepted']=report['external_answer']=='4' and overlap<.75 and report['speaker_stop']['verified_stopped']
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)[:128]
    finally:
        if capture:
            if capture.poll() is None:capture.terminate()
            try:capture.wait(timeout=1)
            except subprocess.TimeoutExpired:capture.kill();capture.wait(timeout=1)
            report['capture_reaped']=capture.poll() is not None
        if backend:report['failure_speaker_stop']=backend.stop(stream)
        pcm.clear();captured.clear();cleanup(a.config,a.owner_file)
        report['operator_after']=hub.agent('/operator');report['microphone_restored']=report['operator_after']['microphone_enabled'] is False
        report['accepted']=report['accepted'] and report['microphone_restored']
        with a.output.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if not report['accepted']:raise SystemExit(2)
if __name__=='__main__':main()
