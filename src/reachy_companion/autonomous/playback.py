"""Bounded PCM adapter. Backend receipts, never elapsed time, authorize resume.

No device is opened by import. Production backend must implement start/write/
progress/stop with owned stream identity and an actual consumed-frame cursor.
ReplayPCM is explicitly simulated and requires allow_simulated=True.
"""
from collections import deque
import math
import threading
import time
from .contracts import uid


class Playback:
    def __init__(self, backend, *, rate=16000, max_seconds=30, chunk_frames=1600,
                 stop_timeout=.3, allow_simulated=False, clock=time.monotonic, motion=None):
        if type(rate) is not int or not 8000<=rate<=48000 or not 1<=max_seconds<=60 or not 1<=chunk_frames<=4096 or not .01<=stop_timeout<=.5:
            raise ValueError('Bounded PCM settings')
        self.backend=backend;self.rate=rate;self.cap=rate*max_seconds*2;self.chunk_frames=chunk_frames
        self.stop_timeout=stop_timeout;self.allow_simulated=allow_simulated;self.clock=clock;self.motion=motion
        self.lock=threading.RLock();self.wake=threading.Event();self.closed=False;self.quarantined=False
        self.generation=0;self.authority=None;self.policy_deadline=0;self.permitted=False;self.active=None;self.paused=None
        self.audio_stops={};self.motion_stop_job=None;self.motion_stop_result={}
        self.motion_stop_known=True;self.worker=None;self.stop_jobs=[];self.timeline=deque(maxlen=64);self.stop_known=True

    def record(self,kind,**fields):
        self.timeline.append(dict(kind=kind,at=self.clock(),**fields))

    def operator(self,authority,*,microphone_enabled,quiet=False,privacy_all=False,valid_until=None):
        if any(type(x) is not bool for x in (microphone_enabled,quiet,privacy_all)):
            raise ValueError('Exact operator bools required')
        with self.lock:
            changed=self.authority!=authority or self.permitted!=(microphone_enabled and not quiet and not privacy_all)
            self.policy_deadline=self.clock()+.3 if valid_until is None else valid_until
            self.authority=authority;self.permitted=microphone_enabled and not quiet and not privacy_all
        if changed:self.interrupt('operator',preserve=False)

    def begin(self,authority,request_id,*,deadline):
        with self.lock:
            if (self.closed or self.quarantined or not self.permitted or authority!=self.authority
                    or type(deadline) not in (int,float) or not math.isfinite(deadline) or self.clock()>=deadline
                    or not isinstance(request_id,str) or not 1<=len(request_id)<=128 or self.active or self.worker and self.worker.is_alive()
                    or any(j.is_alive() for j in self.stop_jobs)):
                raise RuntimeError('Playback owner/admission unavailable')
            self.generation+=1;stream=uid();self.backend.reserve(stream)
            self.active=dict(stream_id=stream,generation=self.generation,authority=authority,request_id=request_id,
                pcm=bytearray(),written=0,consumed=0,done=False,deadline=deadline,started=False)
            self.stop_known=False
            self.worker=threading.Thread(target=self.run,args=(self.active,),daemon=True)
            self.worker.start();return stream

    def push(self,stream,pcm):
        if not isinstance(pcm,bytes) or not pcm or len(pcm)%2 or len(pcm)>self.chunk_frames*2:
            raise ValueError('Bounded S16_LE mono chunk required')
        with self.lock:
            s=self.active
            if not s or s['stream_id']!=stream or s['generation']!=self.generation or s['done']:
                return False
            if len(s['pcm'])+len(pcm)>self.cap:raise ValueError('PCM duration cap')
            s['pcm'].extend(pcm);self.wake.set();return True

    def finish(self,stream):
        with self.lock:
            if not self.active or self.active['stream_id']!=stream:return False
            self.active['done']=True;self.wake.set();return True

    def current(self,s):
        return (self.active is s and s['generation']==self.generation and not self.closed
                and not self.quarantined and self.permitted and s['authority']==self.authority
                and self.clock()<s['deadline'] and self.clock()<self.policy_deadline)

    def cursor(self,s,receipt):
        value=receipt.get('consumed_frames');provenance=receipt.get('provenance')
        if (receipt.get('stream_id')!=s['stream_id'] or receipt.get('verified') is not True
                or type(value) is not int or not s['consumed']<=value<=s['written']
                or provenance not in ('device_consumed_pcm','simulated_consumed_pcm')
                or provenance=='simulated_consumed_pcm' and not self.allow_simulated):
            raise RuntimeError('Consumed PCM cursor unverified')
        return value

    def run(self,s):
        try:
            # The backend start has no output. A delayed start is stopped below;
            # it cannot reach write after local generation withdrawal.
            self.backend.start(s['stream_id'],self.rate)
            s['started']=True
            while True:
                with self.lock:
                    if not self.current(s):break
                    remaining=bytes(s['pcm'][s['written']*2:(s['written']+self.chunk_frames)*2])
                if remaining:
                    # Backend MUST fence write against stop of this exact stream.
                    n=self.backend.write(s['stream_id'],remaining)
                    if type(n) is not int or not 0<=n<=len(remaining)//2:raise RuntimeError('PCM write receipt invalid')
                    with self.lock:s['written']+=n
                with self.lock:written_all=s['done'] and s['written']==len(s['pcm'])//2
                if written_all:self.backend.finish(s['stream_id'])
                receipt=self.backend.progress(s['stream_id'])
                with self.lock:
                    s['consumed']=self.cursor(s,receipt)
                    if self.current(s):
                        self.record('speech_progress',stream_id=s['stream_id'],request_id=s['request_id'],
                            generation=s['generation'],consumed_frames=s['consumed'],provenance=receipt['provenance'])
                    complete=s['done'] and s['consumed']==len(s['pcm'])//2
                if complete:break
                self.wake.wait(.005);self.wake.clear()
        except Exception as exc:
            with self.lock:
                self.quarantined=True;self.paused=None
                self.record('playback_failure',stream_id=s['stream_id'],error=type(exc).__name__)
        finally:
            known=self.bounded_stop(s['stream_id'])
            with self.lock:
                self.stop_known=known and self.motion_stop_known
                if not known:self.quarantined=True;self.paused=None
                if self.active is s:self.active=None
                self.record('speech_stopped',stream_id=s['stream_id'],stop_known=known)

    def request_stop(self,stream):
        with self.lock:
            if stream in self.audio_stops:return self.audio_stops[stream]
            result={}
            def stop():
                try:result['receipt']=self.backend.stop(stream)
                except Exception:pass
            job=threading.Thread(target=stop,daemon=True)
            self.audio_stops={k:v for k,v in self.audio_stops.items() if v[0].is_alive()}
            self.audio_stops[stream]=(job,result)
            self.stop_jobs=[j for j in self.stop_jobs if j.is_alive()]+[job]
            job.start();return job,result

    def bounded_stop(self,stream):
        job,result=self.request_stop(stream);job.join(self.stop_timeout)
        r=result.get('receipt',{})
        return not job.is_alive() and r.get('stream_id')==stream and r.get('verified_stopped') is True

    def interrupt(self,reason='human_activity',*,preserve=True):
        if reason=='echo':return self.status()  # self speech is not a human turn
        with self.lock:
            self.generation+=1;s=self.active;self.active=None;self.paused=None
            self.wake.set();self.stop_known=s is None and not (self.worker and self.worker.is_alive())
        known=True;motion_known=True;cursor=None
        if s:
            # One stop job per stream; repeated interrupts cannot spawn more
            # output threads or manufacture a new consumed cursor.
            job,result=self.request_stop(s['stream_id'])
            if not preserve:
                with self.lock:s['pcm'].clear()
        if self.motion:
            # Motion stop is independent of the audio backend stop worker.
            with self.lock:
                if not self.motion_stop_job or not self.motion_stop_job.is_alive():
                    self.motion_stop_result={};outcome=self.motion_stop_result
                    def stop_motion():
                        try:outcome['known']=self.motion.stop()
                        except Exception:pass
                    self.motion_stop_job=threading.Thread(target=stop_motion,daemon=True)
                    self.stop_jobs=[j for j in self.stop_jobs if j.is_alive()]+[self.motion_stop_job]
                    self.motion_stop_job.start()
                motion_job=self.motion_stop_job;outcome=self.motion_stop_result
            motion_job.join(self.stop_timeout)
            motion_known=not motion_job.is_alive() and outcome.get('known') is True
        if s:
            job.join(self.stop_timeout);r=result.get('receipt',{})
            known=not job.is_alive() and r.get('stream_id')==s['stream_id'] and r.get('verified_stopped') is True
            try:cursor=self.cursor(s,r) if known else None
            except Exception:cursor=None
        with self.lock:
            self.motion_stop_known=motion_known
            self.stop_known=known and motion_known
            if not self.stop_known:self.quarantined=True
            if s and preserve and reason=='human_activity' and s['done'] and cursor is not None and cursor<len(s['pcm'])//2 and self.stop_known:
                self.paused=dict(pcm=bytes(s['pcm']),cursor=cursor,authority=s['authority'],request_id=s['request_id'],
                    interrupted_at=self.clock(),generation=self.generation,confirmed=False)
            self.record('joint_stop',reason=reason,stream_id=s['stream_id'] if s else None,
                consumed_frames=cursor,speech_stop_known=known,motion_stop_known=motion_known,resumable=self.paused is not None)
        return self.status()

    def confirm_no_utterance(self,*,since,until,authority):
        # Trusted completed listening/VAD window only. No utterance event alone
        # and a timer firing do not establish a negative human observation.
        with self.lock:
            p=self.paused
            if (not p or authority!=self.authority or p['authority']!=authority
                    or type(since) not in (int,float) or type(until) not in (int,float)
                    or not math.isfinite(since) or not math.isfinite(until)
                    or since>p['interrupted_at'] or until<p['interrupted_at']+3 or until>self.clock()):return False
            p['confirmed']=True;return True

    def resume(self):
        with self.lock:
            p=self.paused
            if (not p or not p['confirmed'] or self.clock()<p['interrupted_at']+3 or p['generation']!=self.generation
                    or p['authority']!=self.authority or not self.permitted or self.closed or self.quarantined
                    or self.worker and self.worker.is_alive() or any(j.is_alive() for j in self.stop_jobs)):return None
            pcm=p['pcm'][p['cursor']*2:];self.paused=None
            stream=self.begin(p['authority'],p['request_id'],deadline=self.clock()+60)
            # Already-bounded retained PCM; copied only within the same authority.
            self.active['pcm'].extend(pcm);self.active['done']=True;self.wake.set()
            self.record('speech_resumed',stream_id=stream,from_consumed_frames=p['cursor'])
            return stream

    def human_utterance(self):return self.interrupt('human_utterance',preserve=False)

    def status(self):
        with self.lock:
            self.stop_jobs=[j for j in self.stop_jobs if j.is_alive()]
            return dict(execution_busy=bool(self.worker and self.worker.is_alive()) or any(j.is_alive() for j in self.stop_jobs),
                stop_known=self.stop_known,quarantined=self.quarantined,closed=self.closed,
                resumable=self.paused is not None,timeline=list(self.timeline))

    def close(self):
        with self.lock:self.closed=True
        return self.interrupt('shutdown',preserve=False)


class ReplayPCM:
    """Explicit fake consumption controlled by advance(), never wall time."""
    def __init__(self):self.lock=threading.Lock();self.streams={};self.current=None
    def reserve(self,stream):
        with self.lock:
            if self.current and not self.streams[self.current]['stopped']:raise RuntimeError('Backend owned')
            self.streams={self.current:self.streams[self.current]} if self.current else {}
            self.current=stream;self.streams[stream]=dict(written=0,consumed=0,stopped=False)
    def start(self,stream,rate):
        with self.lock:
            if stream!=self.current:raise RuntimeError('Stale stream')
            s=self.streams[stream]
            # stop-before-start tombstone prevents delayed start resurrection.
            if s['stopped']:raise RuntimeError('Stream already withdrawn')
    def write(self,stream,pcm):
        with self.lock:
            s=self.streams[stream]
            if s['stopped']:return 0
            s['written']+=len(pcm)//2;return len(pcm)//2
    def advance(self,stream,frames):
        with self.lock:
            s=self.streams[stream]
            if not s['stopped']:s['consumed']=min(s['written'],s['consumed']+frames)
    def finish(self,stream):
        with self.lock:return self.streams[stream]['consumed']==self.streams[stream]['written']
    def progress(self,stream):
        with self.lock:
            return dict(stream_id=stream,verified=True,provenance='simulated_consumed_pcm',consumed_frames=self.streams[stream]['consumed'])
    def stop(self,stream):
        with self.lock:
            s=self.streams.setdefault(stream,dict(written=0,consumed=0,stopped=True));s['stopped']=True
            return dict(stream_id=stream,verified=True,verified_stopped=True,provenance='simulated_consumed_pcm',consumed_frames=s['consumed'])
