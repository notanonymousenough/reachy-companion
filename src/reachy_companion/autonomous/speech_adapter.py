"""Scheduler -> bounded TTS stream -> owned PCM. Explicit local audio opt-in."""
import base64
import json
import threading
import time
from urllib.request import Request,build_opener,ProxyHandler
from .contracts import decode


class HttpTTS:
    def __init__(self,url,token,*,rate=16000,max_event=65536,timeout=5):
        self.url=url.rstrip('/')+'/stream/say';self.token=token;self.rate=rate;self.max_event=max_event;self.timeout=timeout
        self.lock=threading.Lock();self.response=None
    def stream(self,text,cancel):
        request=Request(self.url,data=json.dumps({'text':text}).encode(),headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with build_opener(ProxyHandler({})).open(request,timeout=self.timeout) as response:
            with self.lock:self.response=response
            try:
                while not cancel.is_set():
                    line=response.readline(self.max_event+1)
                    if not line or len(line)>self.max_event or not line.endswith(b'\n'):raise RuntimeError('Bounded TTS completion required')
                    event=decode(line)
                    if event['type']=='audio':
                        if event.get('sample_rate')!=self.rate or event.get('format')!='S16_LE' or event.get('channels')!=1:raise ValueError('TTS PCM format')
                        yield base64.b64decode(event['pcm_base64'],validate=True)
                    elif event['type']=='done':
                        if event.get('ok') is not True:raise RuntimeError('TTS failure')
                        return
                    elif event['type'] not in ('reply','motion'):raise RuntimeError('TTS event rejected')
                raise RuntimeError('TTS cancelled')
            finally:
                with self.lock:self.response=None
    def cancel(self):
        with self.lock:response=self.response
        if response:response.close()


class SpeechAdapter:
    def __init__(self,playback,tts,operator):
        self.playback=playback;self.tts=tts;self.operator=operator
        self.cancelled=threading.Event();self.closed=False;self.binding=None;self.authority=None
        self.cancel_job=None;self.worker=None;self.receipts=[];self.lock=threading.Lock();self.next_refresh=0
    def refresh(self,authority):
        actual=self.operator();policy=actual['motion_policy']
        binding=(actual['agent_boot_id'],actual['microphone_epoch'],policy['epoch'])
        if (not isinstance(binding[0],str) or type(binding[1]) is not int or type(binding[2]) is not int
                or actual.get('microphone_state_error')):raise RuntimeError('Speech operator unknown')
        combined=(authority,binding)
        if self.authority is not None and self.authority!=combined:self.interrupt('operator',False)
        self.authority=combined;self.binding=binding
        self.playback.operator(combined,microphone_enabled=actual['microphone_enabled'],quiet=policy['quiet'],privacy_all=policy['privacy_all'])
        self.next_refresh=time.monotonic()+.1
    def advance(self,authority):
        if self.closed:return
        if time.monotonic()>=self.next_refresh:
            try:self.refresh(authority)
            except Exception:self.interrupt('operator_unknown',False)
        self.playback.resume()  # requires explicit completed no-utterance window
    def execute(self,proposal):
        if not isinstance(proposal.get('text'),str) or not 0<len(proposal['text'])<=1024:raise ValueError('Bounded speech text')
        with self.lock:
            if self.closed or self.worker and self.worker.is_alive():raise RuntimeError('TTS execution busy/closed')
            self.refresh(proposal['authority']);self.cancelled=threading.Event();cancel=self.cancelled
            stream=self.playback.begin(self.authority,proposal['request_id'],deadline=min(proposal['deadline'],time.monotonic()+60))
            def work():
                report=dict(request_id=proposal['request_id'],stream_id=stream,tts_complete=False)
                try:
                    for pcm in self.tts.stream(proposal['text'],cancel):
                        if cancel.is_set():break
                        # Voice chunks may be larger than the local playback queue chunk.
                        size=self.playback.chunk_frames*2
                        for offset in range(0,len(pcm),size):
                            if not self.playback.push(stream,pcm[offset:offset+size]):raise RuntimeError('Late TTS chunk withdrawn')
                    if not cancel.is_set():report['tts_complete']=self.playback.finish(stream)
                except Exception as exc:
                    report['error']=type(exc).__name__
                    self.playback.interrupt('tts_failure',preserve=False)
                finally:
                    report['cancelled']=cancel.is_set()
                    with self.lock:self.receipts=(self.receipts+[report])[-32:]
            self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
    def interrupt(self,reason,preserve=True):
        if reason=='echo':return self.playback.status()
        self.cancelled.set()
        # Do not await a blocked HTTP close before withdrawing PCM/motion.
        if not self.cancel_job or not self.cancel_job.is_alive():
            self.cancel_job=threading.Thread(target=self.tts.cancel,daemon=True);self.cancel_job.start()
        job=self.cancel_job
        result=self.playback.interrupt(reason,preserve=preserve)
        with self.playback.lock:
            if job not in self.playback.stop_jobs:self.playback.stop_jobs.append(job)
        return result
    def confirm_no_utterance(self,*,since,until):
        return self.playback.confirm_no_utterance(since=since,until=until,authority=self.authority)
    def status(self):
        return dict(self.playback.status(),tts_execution_busy=bool(self.worker and self.worker.is_alive()),receipts=list(self.receipts))
    def close(self):
        self.closed=True;self.interrupt('shutdown',False)
        return self.status()
