"""Latest-only captured utterances -> one occupied PC STT slot -> fresh events.

Capture clock mapping and source boot binding belong to the authenticated
transport owner. Model output cannot supply them. Unknown audio is dialogue
data, never a confirmed human identity or operator permission.
"""
import base64
import hashlib
import math
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler
from .contracts import decode,Authority


class HttpSTT:
    def __init__(self, url, token, *, timeout=2):
        self.url = url.rstrip('/') + '/transcribe'
        self.token, self.timeout = token, timeout
        self.opener=build_opener(ProxyHandler({}))

    def transcribe(self, pcm):
        request = Request(self.url, data=__import__('json').dumps(
            dict(pcm_base64=base64.b64encode(pcm).decode())).encode(),
            headers={'Authorization': 'Bearer ' + self.token,
                     'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=self.timeout) as response:
            raw = response.read(8193)
        if len(raw) > 8192:
            raise ValueError('STT receipt cap')
        text = decode(raw)['transcript']
        if not isinstance(text, str) or len(text) > 1024:
            raise ValueError('Bounded STT text required')
        return text


class AudioAdapter:
    def __init__(self, stt, *, clock=time.monotonic,continuous_input=False):
        if type(continuous_input) is not bool:raise ValueError('Explicit continuous input mode')
        self.continuous_input=continuous_input
        self.stt, self.clock = stt, clock
        self.lock = threading.RLock()
        self.source = None
        self.source_generation = -1
        self.sequence = self.latest_utterance_sequence = -1
        self.authority = self.operator_signature = None
        self.operator_deadline = 0
        self.allowed = False
        self.closed = False
        self.generation = 0
        self.level=None
        self.pending = self.result = self.job = None
        self.counts = dict(submitted=0, overwritten=0, stale=0, echo=0,
                           started=0, completed=0, no_response=0)

    def same_capture_scope(self,left,right):
        if self.continuous_input and isinstance(left,Authority) and isinstance(right,Authority):
            fields=('hub_boot_id','compute_boot_id','robot_boot_id','operator_epoch','microphone_epoch')
            return all(getattr(left,key)==getattr(right,key) for key in fields)
        return left==right

    def bind_source(self, boot, generation):
        if not isinstance(boot, str) or not 1 <= len(boot) <= 128 or type(generation) is not int:
            raise ValueError('Authenticated capture source required')
        with self.lock:
            if self.closed or generation <= self.source_generation:
                return False
            self.source, self.source_generation, self.sequence = boot, generation, -1
            self.latest_utterance_sequence=-1
            self._withdraw()
            return True

    def _withdraw(self):
        self.generation += 1
        self.pending = self.result = None
        self.level=None

    def advance(self, authority, operator):
        """Only local mailbox work; no HTTP/capture/STT waits on scheduler."""
        with self.lock:
            now = self.clock()
            signature = None
            allowed = False
            if operator:
                signature = (tuple(operator['binding']), operator['microphone_enabled'],
                             operator['quiet'], operator['privacy_all'])
                allowed = (operator['microphone_enabled'] is True and operator['quiet'] is False
                           and operator['privacy_all'] is False and now < operator['valid_until'])
            if not self.same_capture_scope(authority,self.authority) or signature != self.operator_signature or not allowed:
                self._withdraw()
            self.authority, self.operator_signature, self.allowed = authority, signature, allowed
            self.operator_deadline = operator['valid_until'] if allowed else 0
            event = None
            if self.job and not self.job.is_alive():
                self.job = None
                result, self.result = self.result, None
                if result:
                    observation, generation, text, error = result
                    if self._fresh(observation, generation):
                        if error or not text.strip():
                            self.counts['no_response'] += 1
                        else:
                            self.counts['completed'] += 1
                            event = dict(type='utterance', text=text, audio=dict(
                                source_boot=observation['source_boot'], sequence=observation['sequence'],
                                operator_binding=list(observation['operator_signature'][0]),
                                lineage_id=observation['lineage_id'], pcm_sha256=observation['pcm_sha256'],
                                origin='unknown', speaker_identity='unknown', speaker_confidence=0,
                                echo_reference=observation['echo_reference'],
                                capture_age_ms=int((now-observation['captured_end'])*1000),
                                ttl_ms=2000, confirmed=False))
                            event['audio']['stt_provenance']='pc_http_stt' if type(self.stt) is HttpSTT else 'fixture_or_unverified_stt'
                    else:
                        self.counts['stale'] += 1
            if self.pending and not self.job:
                observation, self.pending = self.pending, None
                if self._fresh(observation, self.generation):
                    generation = self.generation
                    self.counts['started'] += 1
                    def work():
                        text, error = '', None
                        pcm = observation.pop('pcm')
                        try:
                            text = self.stt.transcribe(pcm)
                            if not isinstance(text, str) or len(text) > 1024:
                                raise ValueError('STT text cap')
                        except Exception as exc:
                            error = type(exc).__name__
                        finally:
                            del pcm
                        with self.lock:
                            if self._fresh(observation, generation):
                                self.result = observation, generation, text, error
                            else:
                                self.counts['stale'] += 1
                    self.job = threading.Thread(target=work, daemon=True)
                    self.job.start()
                else:
                    self.counts['stale'] += 1
            return event

    def _fresh(self, observation, generation):
        now = self.clock()
        return (not self.closed and self.allowed and now < self.operator_deadline
                and generation == self.generation and self.same_capture_scope(observation['authority'],self.authority)
                and observation['operator_signature'] == self.operator_signature
                and observation['source_boot'] == self.source
                and (self.continuous_input or observation['sequence']==self.latest_utterance_sequence)
                and now < observation['deadline'])

    def observe_level(self, level, *, started, source_boot, authority, operator_binding):
        with self.lock:
            now=self.clock()
            age=level.get('capture_age_s');rms=level.get('rms');delta=level.get('delta')
            if (type(age) not in (int,float) or not 0<=age<=.25 or type(rms) not in (int,float) or not 0<=rms<=1
                    or delta is not None and (type(delta) not in (int,float) or not -1<=delta<=1)):
                raise ValueError('Measured audio level contract')
            if (not self.allowed or now>=self.operator_deadline or source_boot!=self.source or authority!=self.authority
                    or tuple(operator_binding)!=self.operator_signature[0] or now-started+age>.5):return False
            self.level=(dict(type='sensor',id='audio.level',summary=f'rms={rms:.5f}; delta={delta}',
                source_id=source_boot,ttl_ms=1000),started-age,authority)
            return True

    def drain_level(self, authority):
        with self.lock:
            level,self.level=self.level,None
            if not level or not self.allowed or authority!=level[2] or self.clock()>=self.operator_deadline:return None
            event,captured,_=level
            event['age_ms']=max(0,int((self.clock()-captured)*1000))
            return event

    def submit(self, pcm, *, source_boot, sequence, captured_end, authority,
               operator_binding, origin='unknown', echo_reference=None):
        """Called by trusted source adapter after conservative capture-clock mapping."""
        if (not isinstance(pcm, bytes) or not pcm or len(pcm) % 2 or len(pcm) > 16000*2*8
                or type(sequence) is not int or sequence < 0
                or type(captured_end) not in (int, float) or not math.isfinite(captured_end)
                or origin not in ('unknown', 'owned_playback')):
            raise ValueError('Bounded captured PCM/provenance required')
        if echo_reference is not None and (not isinstance(echo_reference, str) or not 1 <= len(echo_reference) <= 128):
            raise ValueError('Bounded owned playback reference')
        if origin == 'owned_playback' and echo_reference is None:
            raise ValueError('Owned echo requires reference')
        with self.lock:
            now = self.clock()
            if (self.closed or not self.allowed or now >= self.operator_deadline
                    or source_boot != self.source or sequence <= self.sequence
                    or not 0 <= now-captured_end <= .25 or authority != self.authority
                    or tuple(operator_binding) != self.operator_signature[0]):
                self.counts['stale'] += 1
                return False
            self.sequence = sequence
            if origin == 'owned_playback':
                self.counts['echo'] += 1
                return False
            self.latest_utterance_sequence=sequence
            if self.pending:
                self.counts['overwritten'] += 1
            self.pending = dict(pcm=pcm, pcm_sha256=hashlib.sha256(pcm).hexdigest(),
                source_boot=source_boot, sequence=sequence, captured_end=captured_end,
                deadline=captured_end+2, authority=authority,
                operator_signature=self.operator_signature, echo_reference=echo_reference,
                lineage_id=source_boot+':'+str(sequence))
            self.counts['submitted'] += 1
            return True

    def interrupt(self):
        with self.lock:
            self._withdraw()

    def close(self):
        with self.lock:
            self.closed = True
            self.allowed = False
            self._withdraw()

    def status(self):
        with self.lock:
            return dict(execution_busy=bool(self.job and self.job.is_alive()),
                        pending=self.pending is not None, source_boot=self.source,
                        last_sequence=self.sequence,latest_utterance_sequence=self.latest_utterance_sequence, counts=dict(self.counts))
