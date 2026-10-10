"""Scheduler -> bounded TTS stream -> owned PCM. Explicit local audio opt-in."""
import base64
import json
import math
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
    """Nonblocking scheduler facade; one operator transport and one output slot."""
    def __init__(self,playback,tts,operator):
        self.playback=playback;self.tts=tts;self.operator=operator
        self.cancelled=threading.Event();self.closed=False;self.binding=None;self.authority=None
        self.cancel_job=None;self.worker=None;self.receipts=[];self.lock=threading.RLock()
        self.current_authority=None;self.generation=0;self.pending=None;self.operator_receipt=None
        self.refresh_job=None;self.refresh_result=None;self.next_refresh=0
        self.policy_deadline=0;self.policy_live=False;self.rejected_refreshes=0;self.refresh_calls=0
        self.control=threading.Thread(target=self._control,daemon=True);self.control.start()

    def advance(self,authority):
        with self.lock:
            changed=self.current_authority is not None and self.current_authority!=authority
            self.current_authority=authority
        if changed:self.interrupt('authority',False)

    def _launch_refresh(self):
        with self.lock:
            if self.closed or self.current_authority is None or self.refresh_job and self.refresh_job.is_alive():return
            authority=self.current_authority;generation=self.generation;started=time.monotonic()
            self.refresh_result=None;self.refresh_calls+=1;self.next_refresh=started+.1
            def work():
                try:result=dict(actual=self.operator())
                except Exception as exc:result=dict(error=type(exc).__name__)
                with self.lock:
                    if self.closed or generation!=self.generation or authority!=self.current_authority or time.monotonic()>=started+.3:
                        self.rejected_refreshes+=1
                    else:self.refresh_result=(authority,generation,started,result)
            self.refresh_job=threading.Thread(target=work,daemon=True);self.refresh_job.start()

    def _accept_refresh(self):
        with self.lock:
            if not self.refresh_job or self.refresh_job.is_alive():return
            receipt=self.refresh_result;self.refresh_job=None;self.refresh_result=None
            if receipt is None:return
            authority,generation,started,result=receipt
            if (self.closed or generation!=self.generation or authority!=self.current_authority
                    or time.monotonic()>=started+.3 or 'error' in result):
                self.rejected_refreshes+=1;return
            actual=result['actual'];policy=actual['motion_policy']
            binding=(actual['agent_boot_id'],actual['microphone_epoch'],policy['epoch'])
            if (not isinstance(binding[0],str) or not binding[0] or type(binding[1]) is not int or binding[1]<0
                    or type(binding[2]) is not int or binding[2]<0 or actual.get('microphone_state_error')):
                self.rejected_refreshes+=1;return
            if any(type(value) is not bool for value in (actual['microphone_enabled'],policy['quiet'],policy['privacy_all'])):
                self.rejected_refreshes+=1;self.interrupt('operator_unknown',False);return
            if self.binding and binding[0]==self.binding[0] and (binding[1]<self.binding[1] or binding[2]<self.binding[2]):
                self.rejected_refreshes+=1;return
            combined=(authority,binding)
            if self.authority is not None and combined!=self.authority:
                self.interrupt('operator',False)
            self.authority=combined;self.binding=binding;self.policy_deadline=started+.3
            self.policy_live=True
            self.operator_receipt=dict(binding=binding,microphone_enabled=actual['microphone_enabled'],
                quiet=policy['quiet'],privacy_all=policy['privacy_all'],valid_until=self.policy_deadline)
            self.playback.operator(combined,microphone_enabled=actual['microphone_enabled'],quiet=policy['quiet'],
                privacy_all=policy['privacy_all'],valid_until=self.policy_deadline,wait=False)

    def _control(self):
        while True:
            with self.lock:
                if self.closed:return
            try:
                self._accept_refresh()
                if time.monotonic()>=self.next_refresh:self._launch_refresh()
                with self.lock:
                    fresh=time.monotonic()<self.policy_deadline
                    expired=self.policy_live and not fresh
                    if expired:self.policy_live=False
                    proposal=self.pending
                    if proposal and (proposal['authority']!=self.current_authority or time.monotonic()>=proposal['deadline']):
                        self.pending=None;proposal=None
                    if proposal and fresh and not (self.worker and self.worker.is_alive()) and not (self.cancel_job and self.cancel_job.is_alive()) and not self.playback.status()['execution_busy']:
                        self.pending=None;self._execute(proposal)
                if expired:self.interrupt('operator_expired',False)
                # Backend reserve on resume runs on this control slot, never scheduler.
                if fresh:self.playback.resume()
            except Exception:
                with self.lock:self.rejected_refreshes+=1
                self.interrupt('operator_unknown',False)
            time.sleep(.005)

    def execute(self,proposal):
        if not isinstance(proposal.get('text'),str) or not 0<len(proposal['text'])<=1024:raise ValueError('Bounded speech text')
        if type(proposal.get('deadline')) not in (int,float) or not math.isfinite(proposal['deadline']):raise ValueError('Speech deadline')
        with self.lock:
            if self.current_authority is None:self.current_authority=proposal['authority']
            if proposal['authority']!=self.current_authority:raise RuntimeError('Stale speech proposal authority')
            if self.closed or self.pending or self.worker and self.worker.is_alive() or self.cancel_job and self.cancel_job.is_alive():raise RuntimeError('TTS execution busy/closed')
            self.pending=dict(proposal)

    def _execute(self,proposal):
        self.cancelled=threading.Event();cancel=self.cancelled
        authority=self.authority
        def work():
            report=dict(request_id=proposal['request_id'],tts_complete=False)
            try:
                if cancel.is_set():return
                stream=self.playback.begin(authority,proposal['request_id'],deadline=min(proposal['deadline'],time.monotonic()+60))
                report['stream_id']=stream
                if cancel.is_set():return
                for pcm in self.tts.stream(proposal['text'],cancel):
                    if cancel.is_set():break
                    size=self.playback.chunk_frames*2
                    for offset in range(0,len(pcm),size):
                        if not self.playback.push(stream,pcm[offset:offset+size]):raise RuntimeError('Late TTS chunk withdrawn')
                if not cancel.is_set():report['tts_complete']=self.playback.finish(stream)
            except Exception as exc:
                report['error']=type(exc).__name__
                self.playback.interrupt('tts_failure',preserve=False,wait=False)
            finally:
                report['cancelled']=cancel.is_set()
                with self.lock:self.receipts=(self.receipts+[report])[-32:]
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def interrupt(self,reason,preserve=True):
        if reason=='echo':return self.status()
        with self.lock:
            self.generation+=1;self.pending=None;self.cancelled.set()
            if reason not in ('human_activity',):self.policy_deadline=0;self.policy_live=False
            if not self.cancel_job or not self.cancel_job.is_alive():
                self.cancel_job=threading.Thread(target=self.tts.cancel,daemon=True);self.cancel_job.start()
        self.playback.interrupt(reason,preserve=preserve,wait=False)
        return self.status()

    def confirm_no_utterance(self,*,since,until):
        return self.playback.confirm_no_utterance(since=since,until=until,authority=self.authority)

    def operator_view(self):
        with self.lock:
            return dict(self.operator_receipt) if self.operator_receipt and self.policy_live and not self.closed and time.monotonic()<self.policy_deadline else None

    def status(self):
        with self.lock:
            transport=bool(self.refresh_job and self.refresh_job.is_alive())
            output=bool(self.worker and self.worker.is_alive())
            cancellation=bool(self.cancel_job and self.cancel_job.is_alive())
            result=dict(self.playback.status(),tts_execution_busy=output,operator_execution_busy=transport,
                cancellation_execution_busy=cancellation,control_execution_busy=self.closed and self.control.is_alive(),
                operator_receipt_fresh=time.monotonic()<self.policy_deadline,
                pending_proposal=self.pending is not None,rejected_refreshes=self.rejected_refreshes,
                refresh_calls=self.refresh_calls,receipts=list(self.receipts))
            result['execution_busy']=result['execution_busy'] or transport or output or cancellation or result['control_execution_busy']
            return result

    def close(self):
        with self.lock:self.closed=True
        with self.playback.lock:self.playback.closed=True
        self.interrupt('shutdown',False)
        return self.status()
