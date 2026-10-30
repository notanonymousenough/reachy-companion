"""Experimental same-reader interruption candidate. Default OFF; not AEC.

Waveform labels mean own-like/novel/unknown, never speaker identity. Novelty
requires an empirical own-match calibration in this exact playback generation.
No PCM/status export or output replay. A single worker owns VAD, matching, STT.
"""
import array
import base64
from collections import deque
import math
import re
import threading
import time


REFERENCE_MARKS = 128  # bounded write-receipt metadata, no duplicated PCM snapshots
REFERENCE_BYTES = 64000  # two seconds, mono S16/16kHz, accepted writes only
CANDIDATE_BYTES = 32000  # one second, no retained input history
TTL = 2.5


def waveform_match(pcm, reference):
    """Bounded coarse normalized correlation; not an acoustic clock estimate."""
    a = array.array('h', pcm)[::8]
    b = array.array('h', reference)[::8]
    if not a or len(b) < len(a):return None
    mean = sum(a)/len(a)
    a = [x-mean for x in a]
    energy = sum(x*x for x in a)
    if energy <= 1:return None
    best = 0.
    # 5ms search step at 2kHz, <=400 windows for the bounded reference.
    for start in range(0, len(b)-len(a)+1, 10):
        part = b[start:start+len(a)]
        avg = sum(part)/len(part)
        other = sum((x-avg)**2 for x in part)
        if other <= 1:continue
        value = abs(sum(x*(y-avg) for x,y in zip(a,part)))/math.sqrt(energy*other)
        best = max(best,value)
    return min(1.,best)


def own_text_veto(text, own):
    """Conservative text veto, not a speaker/alignment claim. Includes STOP."""
    words = lambda x:re.findall(r'\w+', x.lower().replace('ё','е').replace('reachy','ричи'))
    heard, spoken = words(text), set(words(own))
    return bool(heard and sum(word in spoken for word in heard)/len(heard) >= .75)


class BargeCandidate:
    def __init__(self, agent, pump, *, clock=time.monotonic, vad=None):
        self.agent,self.pump,self.clock = agent,pump,clock
        if agent.audio['sample_rate'] != 16000 or agent.audio['chunk_ms'] != 100:
            raise ValueError('Candidate requires existing 16kHz/100ms mono reader')
        if vad is None:
            import webrtcvad
            vad=webrtcvad.Vad(agent.audio['vad_mode'])
        self.vad=vad
        self.condition=threading.Condition()
        self.stop=threading.Event();self.interrupted=threading.Event()
        self.thread=threading.Thread(target=self.run,name='reachy-barge-candidate',daemon=True)
        self.binding=self.ticket()
        if self.binding is None:raise RuntimeError('Candidate authority unavailable')
        self.serial=self.generation=self.seen=0
        self.output=False;self.slot=None;self.inflight=False
        self.reference=bytearray();self.reference_marks=deque();self.reference_end=0;self.player=self.attempt=None
        self.reference_at=None;self.last_offer=self.last_measured=None
        self.own_matches=0;self.echo_rms=0.;self.novel_run=0;self.frames=deque(maxlen=10)
        self.submitted=False;self.failure=None;self.last_gate='waiting_for_output'
        self.metrics=dict(rms=None,vad_frames=0,correlation=None,threshold=None,warmup_remaining=0,novel_consecutive=0)
        self.counts={key:0 for key in ('offered','replaced','contended','measured','own','novel','unknown',
            'below_rms','below_vad','warmup','uncalibrated','echo_envelope','stt_submitted','stt_empty',
            'text_veto','stale_after_stt','accepted','cancelled','source_gap')}

    def ticket(self):
        a=self.agent;p=self.pump
        # Called outside the mailbox lock. Agent's MIC -> pump -> policy order.
        with a.microphone_lock,p.condition,a.motion_policy.lock,a.durable_intent.lock,a.conversation_mode.lock:
            policy=a.motion_policy.snapshot();intent=a.durable_intent.snapshot();mode=a.conversation_mode.snapshot()
            if (not p.permitted() or a._capture_pump is not p or a.stopping.is_set()
                or a.microphone.error is not None or a.microphone_owner_id is not None or a.motion_policy.owner_id is not None
                or a.durable_intent.error or not intent['listening_requested'] or mode['error'] is not None):return None
            return (p.binding,p.generation,intent['generation'],mode['generation'])

    def transition(self, generation, active):
        with self.condition:
            self.serial+=1;self.generation=generation;self.output=active;self.slot=None
            self.reference.clear();self.reference_marks.clear();self.reference_end=0;self.player=self.attempt=None;self.reference_at=None
            self.seen=self.own_matches=self.novel_run=0;self.echo_rms=0.;self.frames.clear();self.submitted=False
            self.last_offer=self.last_measured=None
            self.condition.notify_all()

    def cancel(self):
        self.stop.set()
        with self.condition:
            self.serial+=1;self.slot=None;self.reference.clear();self.reference_marks.clear();self.frames.clear()
            self.counts['cancelled']+=1;self.last_gate='withdrawn'
            self.condition.notify_all()

    def offer(self, pcm, received, generation):
        """Reader path: immutable reference and nonblocking latest mailbox only."""
        if self.stop.is_set():return
        if not self.condition.acquire(blocking=False):
            self.counts['contended']+=1
            return
        try:
            if not self.output or generation != self.generation:return
            self.counts['offered']+=1
            if self.last_offer is not None and received-self.last_offer > .3:
                self.serial+=1;self.own_matches=0;self.echo_rms=0.;self.novel_run=0;self.frames.clear()
                self.counts['source_gap']+=1
            self.last_offer=received
            if self.slot is not None:self.counts['replaced']+=1
            self.slot=(pcm,received,self.serial,generation)
            self.condition.notify()
        finally:self.condition.release()

    def written(self, pcm, player, attempt, start, rate):
        """Voice owner passes EXACT bytes accepted by os.write, never planned PCM."""
        with self.condition:
            if self.stop.is_set() or not self.output:return
            if (rate != 16000 or type(start) is not int or start != self.reference_end
                or type(player) is not int or player <= 0
                or (attempt is not None and (type(attempt) is not str or len(attempt) != 32
                    or any(c not in '0123456789abcdef' for c in attempt)))
                or len(pcm)%2 or not 0<len(pcm)<=REFERENCE_BYTES
                or (self.player is not None and player!=self.player)):
                self.failure='reference_discontinuity';self.stop.set();self.slot=None;return
            self.player,self.attempt=player,attempt
            self.reference.extend(pcm);self.reference_end+=len(pcm)
            if len(self.reference)>REFERENCE_BYTES:del self.reference[:-REFERENCE_BYTES]
            self.reference_at=self.clock()
            self.reference_marks.append((self.reference_end,self.reference_at))
            first=self.reference_end-len(self.reference)
            while self.reference_marks and (len(self.reference_marks)>REFERENCE_MARKS or self.reference_marks[0][0]<=first):
                self.reference_marks.popleft()

    def reference_before(self, received):
        """Under mailbox lock: only bytes accepted no later than mic receipt.

        Later writes may have advanced the ring while this microphone item was
        pending. A bounded mark history selects its eligible prefix; overwritten
        or unmarked past data is UNKNOWN, never assigned a newer receipt time.
        """
        first=self.reference_end-len(self.reference)
        eligible=next(((end,at) for end,at in reversed(self.reference_marks) if at<=received and end>first),None)
        if eligible is None:return b'',None,None
        end,at=eligible
        return bytes(self.reference[:end-first]),at,end

    def valid_locked(self, token):
        """After STT, caller holds actual MIC/policy/intent locks. No waiting."""
        serial,generation,received,player=token
        a=self.agent;p=self.pump
        intent=a.durable_intent.snapshot();mode=a.conversation_mode.snapshot()
        return (not self.stop.is_set() and not self.interrupted.is_set() and self.serial==serial
            and self.generation==generation==p.playback_generation and p.output_active
            and received<=self.clock()<=received+TTL and a._capture_pump is p and p.permitted()
            and self.binding==(p.binding,p.generation,intent['generation'],mode['generation'])
            and a.microphone.error is None and a.microphone_owner_id is None and a.motion_policy.owner_id is None
            and not a.durable_intent.error and intent['listening_requested'] and mode['error'] is None
            and a.playback_process is not None and a.playback_process.pid==player and a.playback_process.poll() is None
            and getattr(a,'_capture_control',None) is self)

    def _measure(self, item):
        pcm,received,serial,generation=item
        if self.clock()-received>.3 or self.ticket()!=self.binding:return
        with self.condition:
            if serial!=self.serial or generation!=self.generation or not self.output:return
            ref,ref_at,ref_end=self.reference_before(received);player=self.player
        samples=array.array('h',pcm)
        rms=math.sqrt(sum(x*x for x in samples)/len(samples))
        a=self.agent;b=a.config['conversation']['barge_in']
        vad_frames=sum(self.vad.is_speech(pcm[i:i+a.vad_bytes],16000) for i in range(0,len(pcm),a.vad_bytes))
        correlation=waveform_match(pcm,ref) if ref_at is not None and 0<=received-ref_at<=1. else None
        threshold=a.threshold*b.get('threshold_multiplier',1.4)
        with self.condition:
            if serial!=self.serial or generation!=self.generation or self.stop.is_set():return
            if self.last_measured is not None and received-self.last_measured>.15:
                self.novel_run=0;self.frames.clear();self.counts['source_gap']+=1
            self.last_measured=received
            self.seen+=1;self.counts['measured']+=1
            self.metrics=dict(rms=round(rms,2),vad_frames=vad_frames,correlation=correlation,threshold=threshold,
                selected_reference_end_byte=ref_end,reference_receipt_age_s=None if ref_at is None else received-ref_at,
                warmup_remaining=max(0,b.get('warmup_chunks',6)-self.seen+1),novel_consecutive=self.novel_run)
            if correlation is not None and correlation>=.75:
                label='own';self.own_matches=min(100,self.own_matches+1);self.echo_rms=max(self.echo_rms,rms)
            elif correlation is None or correlation>.20:label='unknown'
            elif self.own_matches<3:label='unknown';self.counts['uncalibrated']+=1
            elif rms < max(threshold,self.echo_rms*1.8):label='unknown';self.counts['echo_envelope']+=1
            else:label='novel'
            self.counts[label]+=1;self.last_gate=label
            loud=rms>=threshold;voiced=vad_frames>=a.audio['min_speech_frames']
            warm=self.seen>b.get('warmup_chunks',6)
            if not loud:self.counts['below_rms']+=1
            if not voiced:self.counts['below_vad']+=1
            if not warm:self.counts['warmup']+=1
            eligible=label=='novel' and loud and voiced and warm
            self.novel_run=self.novel_run+1 if eligible else 0
            self.metrics['novel_consecutive']=self.novel_run
            self.frames.append(pcm if eligible else b'')
            if (not eligible or self.novel_run<b['min_voiced_chunks'] or self.submitted):return
            candidate=b''.join(self.frames)[-CANDIDATE_BYTES:]
            self.submitted=True;self.counts['stt_submitted']+=1
            token=(serial,generation,received,player)
        self._confirm(candidate,token)

    def _confirm(self, pcm, token):
        a=self.agent
        try:
            reply=a.request(a.config['network']['voice_url'],'/transcribe',
                {'pcm_base64':base64.b64encode(pcm).decode()},timeout=2.)
            text=reply.get('transcript');action=(reply.get('decision') or {}).get('action')
            if type(text) is not str or not 0<len(text)<=2000 or action not in ('answer','stop'):
                with self.condition:self.counts['stt_empty']+=1;self.last_gate='stt_empty_or_invalid'
                return
            if own_text_veto(text,a.current_reply_text):
                with self.condition:self.counts['text_veto']+=1;self.last_gate='text_veto'
                return
            if not a.barge_candidate_effect(self,token,action):
                with self.condition:self.counts['stale_after_stt']+=1;self.last_gate='stale_after_stt'
        except Exception:
            with self.condition:self.failure='confirmation_failed';self.last_gate='confirmation_failed'

    def run(self):
        try:
            while not self.stop.is_set():
                with self.condition:
                    self.condition.wait_for(lambda:self.slot is not None or self.stop.is_set(),.05)
                    item,self.slot=self.slot,None
                    self.inflight=item is not None
                if item is not None:self._measure(item)
                with self.condition:self.inflight=False
        except Exception:
            with self.condition:self.failure='candidate_worker_failed'
        finally:
            self.stop.set()
            with self.condition:
                self.inflight=False;self.slot=None;self.reference.clear();self.reference_marks.clear();self.frames.clear()

    def finish(self):
        self.cancel()
        self.thread.join(timeout=2.5)
        if self.thread.is_alive():raise RuntimeError('Barge candidate confirmation still active')
        return None  # Never inject/replay candidate PCM or resume old output.

    def status(self):
        with self.condition:
            return dict(configured=True,enabled=not self.stop.is_set() and self.thread.is_alive(),
                worker_alive=self.thread.is_alive(),execution_busy=self.inflight,
                pending=int(self.slot is not None),counts=dict(self.counts),last_gate=self.last_gate,error=self.failure,
                metrics=dict(self.metrics),own_matches=self.own_matches,learned_echo_rms=self.echo_rms,
                reference_bytes=len(self.reference),reference_history_entries=len(self.reference_marks),candidate_bytes=sum(map(len,self.frames)),
                accepted_reference_end_byte=self.reference_end,reference_player_pid=self.player,
                reference_written_receipt_monotonic=self.reference_at,last_measured_receipt_monotonic=self.last_measured,
                calibrated_in_current_playback=self.own_matches>=3,
                source_generation=self.pump.generation,playback_generation=self.generation,
                acoustic_alignment_verified=False,speaker_identity='unknown',pcm_export_bytes=0,
                output_resume_enabled=False)
