"""Default-OFF, finite two-case acoustic trial; existing audio/reader owners only."""
import copy
import math
import threading
import time
from uuid import uuid4

TEXT = ('Сколько будет два плюс два? Сейчас я спокойно продолжу говорить, чтобы проверить разговор одновременно со звуком вокруг. '
        'Я рассказываю о простом утре: на столе стоит чашка, за окном светло, рядом лежит книга. '
        'Я могу остановиться, когда услышу новую речь. Это конечная проверка, после которой я снова буду слушать.')
FIELDS = {'agent_boot_id','microphone_epoch','policy_epoch','intent_generation','mode_generation','source_generation','expires_at_monotonic'}

class EitherEvent:
    def __init__(self, first, second):self.first,self.second=first,second
    def is_set(self):return self.first.is_set() or self.second.is_set()

class BargeTrial:
    def __init__(self, agent, *, clock=time.monotonic):
        self.agent,self.clock=agent,clock
        self.lock=threading.RLock();self.wake=threading.Event()
        self.pending=self.running=self.last=None
        self.used=set();self.next_due=0.

    def configured(self):
        config=self.agent.config['conversation']
        value=config.get('barge_trial_enabled',False)
        candidate=config.get('barge_candidate_enabled',False)
        trial_only=config.get('barge_candidate_trial_only',False)
        if any(type(flag) is not bool for flag in (value,candidate,trial_only)):
            raise ValueError('Boolean trial/candidate/trial-only opt-ins required')
        if value and candidate and (not self.agent._capture_enabled() or config['barge_in'].get('confirm_with_stt') is not True):
            raise ValueError('Trial requires existing shared capture and STT confirmation')
        # Admission reads raw flags: conditional runtime gating would recurse
        # and prevent queueing the first trial while ordinary barge is OFF.
        return value and candidate

    def active(self):
        with self.lock:
            return bool(self.running is not None and not self.running['cancel'].is_set()
                and self.clock()<self.running['binding']['expires_at_monotonic'])

    def snapshot(self):
        with self.lock:
            return dict(configured=self.configured(),pending=self.pending is not None,running=self.running is not None,
                remaining_cases=2-len(self.used),next_due_monotonic=self.next_due,last=copy.deepcopy(self.last),
                external_identity_verified=False,acoustic_onset_verified=False)

    def _valid(self, job, *, idle=False):
        a=self.agent;b=job['binding'];p=getattr(a,'_capture_pump',None)
        if p is None:return False
        # Same order as candidate; never hold trial mailbox while acquiring controls.
        with a.microphone_lock,p.condition,a.motion_policy.lock,a.durable_intent.lock,a.conversation_mode.lock:
            policy=a.motion_policy.snapshot();intent=a.durable_intent.snapshot();mode=a.conversation_mode.snapshot()
            good=(self.configured() and self.clock()<b['expires_at_monotonic'] and not job['cancel'].is_set()
                and a.agent_boot_id==b['agent_boot_id'] and a.microphone_epoch==b['microphone_epoch']
                and policy['epoch']==b['policy_epoch'] and intent['generation']==b['intent_generation']
                and mode['generation']==b['mode_generation'] and p.generation==b['source_generation']
                and mode['mode']==('normal' if job['case']=='own_only' else 'alice_test')
                and not mode['error'] and not a.durable_intent.error and a.microphone.error is None
                and a.microphone.enabled and a.listening.is_set() and a.capture_active and p.permitted()
                and intent['listening_requested'] and a.microphone_owner_id is None and a.motion_policy.owner_id is None
                and not policy['privacy_all'] and not policy['quiet'] and not a.stopping.is_set())
            if idle:
                receipt=p.counters['last_read_monotonic']
                good=(good and a.phase=='listening' and a.pending_pcm is None and a.resume_audio is None
                    and a.playback_process is None and a.voice_response is None and p.error is None
                    and p.thread is not None and p.thread.is_alive() and a.calibrated
                    and receipt is not None and 0<=self.clock()-receipt<=.3
                    and not p.assembler.frames and p.latest is None and not p.output_active and not a.sounds.music)
            return bool(good)

    def submit(self, payload):
        if type(payload) is not dict or set(payload)!={'case','binding'} or payload['case'] not in ('own_only','alice_overlap'):
            raise ValueError('Exact finite trial case/binding required')
        b=payload['binding']
        if (type(b) is not dict or set(b)!=FIELDS or type(b['agent_boot_id']) is not str or not 1<=len(b['agent_boot_id'])<=128
            or any(type(b[k]) is not int or not 0<=b[k]<2**63 for k in FIELDS-{'agent_boot_id','expires_at_monotonic'})
            or type(b['expires_at_monotonic']) not in (int,float) or not math.isfinite(b['expires_at_monotonic'])
            or not 0<b['expires_at_monotonic']-self.clock()<=45):raise ValueError('Exact fresh bounded trial binding required')
        job=dict(id=uuid4().hex,case=payload['case'],binding=dict(b),cancel=threading.Event(),measurement=None)
        if not self._valid(job,idle=True):raise RuntimeError('Trial authority unavailable')
        with self.lock:
            if self.pending or self.running or job['case'] in self.used or self.clock()<self.next_due:raise RuntimeError('Trial busy/used/cooling down')
            if job['case']=='alice_overlap' and (self.last is None or self.last['case']!='own_only' or self.last['outcome']!='OWN_NEGATIVE_PASS'):
                raise RuntimeError('Calibrated own-only negative required first')
            self.used.add(job['case']);self.pending=job;self.wake.set()
            return dict(accepted=True,trial_id=job['id'],case=job['case'],expires_at_monotonic=b['expires_at_monotonic'])

    def cancel(self):
        with self.lock:
            for job in (self.pending,self.running):
                if job is not None:job['cancel'].set()
            if self.pending is not None:
                self.last=dict(trial_id=self.pending['id'],case=self.pending['case'],outcome='WITHDRAWN')
            self.pending=None;self.wake.clear()

    def observe(self, candidate):
        if candidate is None:return
        value=candidate.status()
        with self.lock:
            job=self.running
            if job is None:return
            old=job['measurement']
            # Only one playback is admitted. Final observation is taken before output(False).
            if value['reference_player_pid'] is not None:
                if old is not None and (old['reference_player_pid']!=value['reference_player_pid'] or old['playback_generation']!=value['playback_generation']):
                    job['cancel'].set();return
                job['measurement']=value

    def consume(self):
        with self.lock:
            job=self.pending;self.pending=None;self.wake.clear()
            if job is None:return False
            self.running=job
        a=self.agent;result={};failure=False
        try:
            if not a.audio_lock.locked() or not self._valid(job,idle=True):raise RuntimeError('Trial admission withdrawn')
            result=a.voice('/say',dict(text=TEXT,session=a.config['conversation']['session']),
                expected_epoch=job['binding']['microphone_epoch'],expected_policy_epoch=job['binding']['policy_epoch'],
                valid_until=job['binding']['expires_at_monotonic'],allow_barge_in=True,manual_authority=lambda:self._valid(job))
        except Exception:failure=True
        finally:
            a.pending_pcm=a.resume_audio=None
            with self.lock:
                measured=job['measurement']
                calibrated=bool(measured and measured['own_matches']>=3)
                accepted=measured['counts']['accepted'] if measured else 0
                outcome=('WITHDRAWN' if job['cancel'].is_set() or self.clock()>=job['binding']['expires_at_monotonic'] else
                         'FAILED' if failure else 'OWN_FALSE_INTERRUPT' if job['case']=='own_only' and accepted else
                         'OWN_NEGATIVE_PASS' if job['case']=='own_only' and calibrated and result.get('ok') and not result.get('cancelled') else
                         'EXTERNAL_CANDIDATE_INTERRUPTED_UNVERIFIED' if job['case']=='alice_overlap' and calibrated and accepted else 'NOT_EXERCISED')
                self.last=dict(trial_id=job['id'],case=job['case'],outcome=outcome,measurement=measured,
                    reply_interrupted=bool(result.get('interrupted')),external_source_verified=False,
                    external_acceptance='NOT_EXERCISED',acoustic_onset_verified=False)
                self.running=None;self.next_due=self.clock()+30
            a.phase='listening' if a.listening.is_set() else 'paused'
        return True
