"""Explicit once-per-arm camera question, consumed by the existing audio loop.

No listener, audio owner, motion grant, transcript, queued speech or saved image.
"""
import http.client
from contextlib import nullcontext
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

PURPOSE = 'Задай один короткий вопрос по новому кадру.'
NO_BASIS = 'НЕТ_ОСНОВАНИЯ'
BINDING = {'agent_boot_id','microphone_epoch','policy_epoch','owner_id','expires_at_monotonic'}


def binding(value):
    return dict(agent_boot_id=value['agent_boot_id'],microphone_epoch=value['microphone_epoch'],
                policy_epoch=value['motion_policy']['epoch'],owner_id=value['microphone_owner_id'])


OPERATOR_FIELDS = {'agent_boot_id','microphone_epoch','microphone_owner_id','microphone_enabled',
    'capture_active','phase','listening','microphone_state_error','motion_policy','motion_policy_owner_id','expression_version'}
POLICY_FIELDS = {'motor_enabled','quiet','privacy_all','epoch'}
PHASES = {'starting','paused','listening','recording','processing','speaking','waiting_to_resume','music','error','stopped'}


def guard(value, expected, deadline, *, processing=False):
    def identity(item):return type(item) is str and 1<=len(item)<=128
    def epoch(item):return type(item) is int and 0<=item<2**63
    policy=value.get('motion_policy') if type(value) is dict else None
    if (type(value) is not dict or set(value)!=OPERATOR_FIELDS
            or type(policy) is not dict or set(policy)!=POLICY_FIELDS
            or type(expected) is not dict or set(expected)!=BINDING-{'expires_at_monotonic'}
            or not identity(value['agent_boot_id']) or not identity(expected['agent_boot_id'])
            or any(not epoch(item) for item in (value['microphone_epoch'],policy['epoch'],value['expression_version'],
                                                expected['microphone_epoch'],expected['policy_epoch']))
            or any(item is not None and not identity(item) for item in
                   (value['microphone_owner_id'],value['motion_policy_owner_id'],expected['owner_id']))
            or any(type(value[key]) is not bool for key in ('microphone_enabled','listening','capture_active'))
            or any(type(policy[key]) is not bool for key in ('motor_enabled','quiet','privacy_all'))
            or type(value['phase']) is not str or value['phase'] not in PHASES
            or type(deadline) not in (int,float) or not math.isfinite(deadline)):
        raise ValueError('Typed local initiative authority required')
    if (binding(value)!=expected or value['motion_policy_owner_id']!=expected['owner_id']
            or value['microphone_enabled'] is not True or value['listening'] is not True
            or value['microphone_state_error'] is not None or policy['quiet'] is not False
            or policy['privacy_all'] is not False
            or (processing and (value['capture_active'] is not False or value['phase']!='processing'))
            or not 0<deadline-time.monotonic()<=60):
        raise RuntimeError('Initiative authority changed')


def local_operator(agent):
    began=time.monotonic()
    value=agent.operator_status()
    if time.monotonic()-began>.3:raise RuntimeError('Local initiative read expired')
    return value


def question(result):
    from_tags=('<think','</think','<|analysis|>','<|im_start|>','<analysis','[analysis]')
    text=result.get('final_text'); expires=result.get('expires_at_monotonic'); frame=result.get('frame')
    if (result.get('kind')!='companion-vision-snapshot' or type(text) is not str
            or not 3<=len(text)<=180 or text!=text.strip()
            or (text!=NO_BASIS and (text.count('?')!=1 or not text.endswith('?')))
            or '\n' in text or any(tag in text.lower() for tag in from_tags) or not re.search('[А-Яа-яЁё]',text)
            or type(expires) not in (int,float) or not math.isfinite(expires) or not 0<expires-time.monotonic()<=60
            or type(frame) is not dict or frame.get('camera_closed') is not True
            or frame.get('model_instance_preserved') is not True or frame.get('raw_pixel_files')!=0
            or type(frame.get('frame_id')) is not str or not re.fullmatch('[0-9a-f]{32}',frame['frame_id'])):
        raise ValueError('One bounded fresh Russian question required')
    return (None if text==NO_BASIS else text),expires


def control_binding(payload):
    if (type(payload) is not dict or set(payload)!={'enabled','expected_generation','operator_binding'}
            or type(payload['enabled']) is not bool or type(payload['expected_generation']) is not int
            or not 0<=payload['expected_generation']<2**63-1):
        raise ValueError('Exact initiative control required')
    given=payload['operator_binding']
    if (type(given) is not dict or set(given)!=BINDING
            or type(given['agent_boot_id']) is not str or not 1<=len(given['agent_boot_id'])<=128
            or any(type(given[k]) is not int or not 0<=given[k]<2**63 for k in ('microphone_epoch','policy_epoch'))
            or (given['owner_id'] is not None and (type(given['owner_id']) is not str or not 1<=len(given['owner_id'])<=128))
            or type(given['expires_at_monotonic']) not in (int,float) or not math.isfinite(given['expires_at_monotonic'])
            or not 0<given['expires_at_monotonic']-time.monotonic()<=60):
        raise ValueError('Fresh initiative operator binding required')
    expected={k:v for k,v in given.items() if k!='expires_at_monotonic'}
    return expected


class Initiative:
    def __init__(self, agent):
        self.agent=agent
        self.lock=threading.Lock()
        self.wake=threading.Event()
        self.generation=0
        self.state='off'
        self.expected=None
        self.deadline=0.
        self.quiet=None
        self.frame=None
        self.schedule_generation=0
        self.schedule_enabled=False
        self.schedule_expected=None
        self.schedule_child=None
        self.schedule_next_due=0.
        self.schedule_reason='default_off'
        self.schedule_quiet=None
        self.caption_autonomy=None

    @property
    def pending(self):
        with self.lock:return self.state=='armed'

    def idle_deadline(self):
        now=time.monotonic()
        intent=getattr(self.agent,'durable_intent',None)
        if intent is not None and (intent.pending() or intent.recovery_pending()):return now+.25
        with self.lock:
            if self.state=='armed':return now+.25
            if not self.schedule_enabled:return None
            # Sleep through cooldown on the existing capture event. Foreground
            # PCM and explicit authority controls still wake capture normally.
            return self.schedule_next_due if self.schedule_next_due>now else now+.25

    def schedule_status(self):
        with self.lock:
            return dict(enabled=self.schedule_enabled,generation=self.schedule_generation,
                interval_seconds=300,next_due_monotonic=self.schedule_next_due,
                owned_child_generation=self.schedule_child,reason=self.schedule_reason,
                state=('OFF' if not self.schedule_enabled else 'RUNNING' if self.state=='running'
                       else 'COOLDOWN' if time.monotonic()<self.schedule_next_due else 'WAITING_FOR_IDLE'))

    def _schedule_off_locked(self, reason):
        if self.schedule_enabled:
            self.schedule_generation+=1
        self.schedule_enabled=False
        self.schedule_expected=None
        self.schedule_child=None
        self.schedule_reason=reason
        self.schedule_quiet=None

    def schedule_control(self, payload, *, startup_intent_generation=None, recovery_token=None, panel_intent_generation=None):
        expected=control_binding(payload)
        a=self.agent;began=time.monotonic()
        with a.microphone_lock,a.motion_policy.lock:
            value=self._locked_operator()
            guard(value,expected,payload['operator_binding']['expires_at_monotonic'])
            if payload['enabled']:
                if expected['owner_id'] is not None or not a._capture_enabled() or a.stopping.is_set():
                    raise RuntimeError('Unowned current capture authority required')
                if (a.phase!='listening' or not a.capture_active or a.pending_pcm is not None
                        or a.resume_audio is not None or a.playback_process is not None or a.voice_response is not None):
                    raise RuntimeError('Schedule requires ordinary listening without queued output')
            with self.lock, (a.durable_intent.lock if hasattr(a,'durable_intent') else nullcontext()):
                if panel_intent_generation is not None:
                    iv=a.durable_intent.snapshot()
                    if (type(panel_intent_generation) is not int or iv['generation']!=panel_intent_generation
                        or a.durable_intent.error or not iv['listening_requested']):raise RuntimeError('Panel intent changed')
                if startup_intent_generation is not None:
                    intent=a.durable_intent;iv=intent.snapshot()
                    if (type(startup_intent_generation) is not int or intent.error
                        or intent.bootstrap_state!='admitting' or iv['generation']!=startup_intent_generation
                        or not iv['listening_requested'] or not iv['automatic_questions_requested']):
                        raise RuntimeError('Startup intent generation withdrawn')
                if recovery_token is not None and not a.durable_intent.recovery_valid(a,recovery_token,admitting=True):
                    raise RuntimeError('Recovery authority withdrawn')
                if payload['expected_generation']!=self.schedule_generation:
                    raise RuntimeError('Schedule generation changed')
                if time.monotonic()-began>.3:raise RuntimeError('Schedule admission expired')
                if payload['enabled']:
                    if self.schedule_enabled or self.state in ('armed','running'):
                        raise RuntimeError('Schedule or manual initiative already active')
                    if hasattr(a,'durable_intent'):
                        a.durable_update(automatic=True)
                        try:
                            guard(self._locked_operator(),expected,payload['operator_binding']['expires_at_monotonic'])
                            if time.monotonic()-began>.3:raise RuntimeError('Schedule admission expired after persistence')
                            if recovery_token is not None and not a.durable_intent.recovery_valid(a,recovery_token,admitting=True):raise RuntimeError('Recovery changed before commit')
                        except BaseException:
                            a.durable_update(automatic=False)
                            raise
                    self.schedule_generation+=1
                    self.schedule_enabled=True
                    self.schedule_expected=expected
                    self.schedule_child=None
                    self.schedule_reason='waiting_for_idle'
                    self.schedule_quiet=None
                    self.state='off';self.expected=None;self.deadline=0.
                    self.quiet=None;self.frame=None
                else:
                    if hasattr(a,'durable_intent'):a.durable_update(automatic=False)
                    owned=self.schedule_child==self.generation and self.schedule_enabled
                    running=owned and self.state=='running'
                    was_enabled=self.schedule_enabled
                    self._schedule_off_locked('explicit_off')
                    # Every explicit OFF consumes its CAS, including default OFF.
                    if not was_enabled:self.schedule_generation+=1
                    if owned and self.state in ('armed','running'):
                        self.generation+=1;self.state='cancelled';self.quiet=None
        self.wake.set()
        if not payload['enabled'] and running:a.stop_speaker()
        return self.schedule_status()

    def schedule_withdraw(self, reason, generation):
        with self.lock:
            if not self.schedule_enabled or self.schedule_generation!=generation:return
            owned=self.schedule_child==self.generation
            running=owned and self.state=='running'
            self._schedule_off_locked(reason)
            if owned and self.state in ('armed','running'):
                self.generation+=1;self.state='cancelled';self.quiet=None
        self.wake.set()
        if running:self.agent.stop_speaker()

    def _locked_operator(self):
        a=self.agent
        return dict(agent_boot_id=a.agent_boot_id,microphone_epoch=a.microphone_epoch,
            microphone_owner_id=a.microphone_owner_id,motion_policy_owner_id=a.motion_policy.owner_id,
            microphone_enabled=a.microphone.enabled,listening=a.listening.is_set(),
            microphone_state_error=a.microphone.error,motion_policy=a.motion_policy.snapshot(),
            capture_active=a.capture_active,phase=a.phase,expression_version=a.expressions.version)

    def schedule_tick(self):
        with self.lock:
            if not self.schedule_enabled:return
            generation=self.schedule_generation;expected=dict(self.schedule_expected)
        try:
            value=local_operator(self.agent)
            guard(value,expected,time.monotonic()+59)
            if self.agent.stopping.is_set() or not self.agent._capture_enabled():
                raise RuntimeError('Schedule authority withdrawn')
            with self.lock:
                if not self.schedule_enabled or generation!=self.schedule_generation:return
                if self.schedule_child is not None:
                    if self.schedule_child!=self.generation or self.state in ('failed','cancelled'):
                        raise RuntimeError('Schedule child withdrawn')
                    if self.state in ('armed','running'):return
                    if self.state not in ('done','abstained'):raise RuntimeError('Unknown schedule child')
                    self.schedule_child=None
                elif self.state in ('armed','running'):
                    raise RuntimeError('Foreign manual initiative')
                if time.monotonic()<self.schedule_next_due:return
                self.state='off';self.expected=None;self.deadline=0.;self.frame=None
            return self._schedule_commit(generation,expected)
        except Exception:
            self.schedule_withdraw('schedule_withdrawn',generation)

    def _schedule_commit(self, schedule_generation, expected):
        a=self.agent;began=time.monotonic()
        pump=getattr(a,'_capture_pump',None)
        if pump is None:
            with self.lock:
                if self.schedule_generation==schedule_generation:self.schedule_quiet=None
            return None
        # Existing Agent order: microphone -> pump -> policy -> initiative.
        # Never hold policy while waiting for pump: the reader takes pump -> policy.
        # No network/model or reader join under these admission locks.
        with a.microphone_lock,pump.condition,a.motion_policy.lock:
            value=self._locked_operator()
            guard(value,expected,time.monotonic()+59)
            if a.stopping.is_set() or expected['owner_id'] is not None:
                raise RuntimeError('Schedule authority withdrawn')
            now=time.monotonic()
            receipt=pump.counters['last_read_monotonic']
            idle=(a._capture_pump is pump and pump.permitted() and pump.error is None
                  and value['phase']=='listening' and value['capture_active']
                  and a.pending_pcm is None and a.resume_audio is None
                  and a.playback_process is None and a.voice_response is None
                  and a.audio_lock.locked() and a.calibrated and not pump.assembler.frames
                  and pump.latest is None and not pump.output_active and now>=pump.suppress_until
                  and not a.sounds.music and receipt is not None and 0<=now-receipt<=.3)
            stamp=(pump,pump.generation,pump.assembler.number)
            seen=pump.assembler.seen
            with self.lock:
                if not self.schedule_enabled or self.schedule_generation!=schedule_generation:return None
                if self.schedule_expected!=expected or self.schedule_child is not None or self.state in ('armed','running'):
                    raise RuntimeError('Schedule admission changed')
                if time.monotonic()-began>.3:raise RuntimeError('Schedule admission expired')
                if now<self.schedule_next_due or not idle:
                    self.schedule_quiet=None;return None
                if self.schedule_quiet is None or self.schedule_quiet[:3]!=stamp:
                    self.schedule_quiet=(*stamp,seen,now);return None
                if now-self.schedule_quiet[4]<3 or seen-self.schedule_quiet[3]<math.ceil(3000/a.audio['chunk_ms']):return None
                # Only this final, same-source quiet observation creates a child.
                # It starts RUNNING immediately; there is no second quiet wait.
                self.generation+=1
                self.state='running';self.expected=dict(expected);self.deadline=now+59
                self.quiet=None;self.frame=None
                self.schedule_child=self.generation;self.schedule_quiet=None
                self.schedule_reason='running';self.schedule_next_due=now+300
                pump.retire()
                return self.generation

    def status(self):
        with self.lock:
            return dict(generation=self.generation,state=self.state,once_per_arm=True,frame=self.frame)

    def _cancel_locked(self, reason):
        if self.caption_autonomy is not None:self.caption_autonomy.withdraw(clear_history=True)
        running=self.state=='running'
        self._schedule_off_locked(reason)
        if self.state in ('armed','running'):
            self.generation+=1
            self.state='cancelled'
            self.quiet=None
        return running

    def cancel(self, reason='cancelled', *, stop_audio=True):
        with self.lock:running=self._cancel_locked(reason)
        self.wake.set()
        if running and stop_audio:self.agent.stop_speaker()
        return running

    def input_activity(self):
        caption=self.caption_autonomy
        speaking=caption.speaking_generation if caption is not None else None
        if caption is not None:caption.withdraw()
        if speaking is not None:
            with self.lock:
                if self.schedule_enabled and self.state=='running' and self.generation==speaking:
                    # Ordinary input supersedes only this caption speech. The
                    # live voice generation/callback fence withdraws output;
                    # stop_speaker() would also revoke retained AUTO here.
                    self.generation+=1;self.state='cancelled';self.schedule_child=None
                    self.quiet=self.schedule_quiet=None
                    self.schedule_reason='foreground_cancelled_caption'
                    self.wake.set()
                    return
        # Foreground PCM resets quiet while the same unexpired request waits.
        # It does not establish a speaker, create an arm or renew authority.
        with self.lock:
            running=self.state=='running'
            self.schedule_quiet=None
            if self.state=='armed' and 0<self.deadline-time.monotonic()<=60:
                self.quiet=None
            elif self.state in ('armed','running'):
                self._schedule_off_locked('input_cancelled')
                self.generation+=1
                self.state='cancelled'
                self.quiet=None
        self.wake.set()
        if running:self.agent.stop_speaker()

    def arm(self, payload):
        expected=control_binding(payload)
        given=payload['operator_binding']
        a=self.agent
        if not a._capture_enabled():raise RuntimeError('Continuous capture required')
        began=time.monotonic()
        # Same order as the existing control paths; no network under locks.
        with a.microphone_lock,a.motion_policy.lock:
            value=self._locked_operator()
            guard(value,expected,given['expires_at_monotonic'])
            if a.stopping.is_set():raise RuntimeError('Agent stopped')
            if payload['enabled'] and (a.phase!='listening' or not a.capture_active
                    or a.pending_pcm is not None or a.resume_audio is not None
                    or a.playback_process is not None or a.voice_response is not None):
                raise RuntimeError('Initiative requires actual listening without queued output')
            with self.lock:
                if payload['enabled'] and self.schedule_enabled:
                    raise RuntimeError('Disable automatic schedule before manual arm')
                if payload['expected_generation']!=self.generation or (payload['enabled'] and self.state in ('armed','running')):
                    raise RuntimeError('Initiative generation changed or busy')
                if time.monotonic()-began>.3:raise RuntimeError('Local initiative admission expired')
                if not payload['enabled']:self._schedule_off_locked('manual_off')
                running=self.state=='running'
                self.generation+=1
                self.state='armed' if payload['enabled'] else 'cancelled'
                self.expected=expected;self.deadline=given['expires_at_monotonic']
                self.quiet=None;self.frame=None
        self.wake.set()
        if running:a.stop_speaker()
        return self.status()

    def valid(self, generation):
        with self.lock:
            if self.generation!=generation or self.state not in ('armed','running'):return False
            expected=dict(self.expected);deadline=self.deadline
        try:
            if self.agent.stopping.is_set():return False
            guard(local_operator(self.agent),expected,deadline)
            return True
        except (KeyError,ValueError,TypeError,RuntimeError):return False

    def inspect(self):
        began=time.monotonic()
        status=self.status(); generation=status['generation']
        if not self.valid(generation):raise RuntimeError('Initiative inactive')
        value=local_operator(self.agent)
        guard(value,self.expected,self.deadline)
        if not self.valid(generation) or time.monotonic()-began>.3:
            raise RuntimeError('Local initiative changed or expired')
        return dict(initiative=status,operator=value)

    def maybe_run(self):
        intent=getattr(self.agent,'durable_intent',None)
        if intent is not None:
            intent.tick(self.agent)
            intent.recovery_tick(self.agent)
        self.wake.clear()
        if (self.caption_autonomy is not None
                and ((self.caption_autonomy.applicable() and self.schedule_enabled) or self.caption_autonomy.has_work())):
            return self.caption_autonomy.advance()
        generation=self.schedule_tick();a=self.agent
        scheduled_attempt=generation is not None
        if not scheduled_attempt:
            if not self.pending:return False
            generation=self.status()['generation'];a=self.agent
            if not self.valid(generation):self.cancel();return False
            pump=getattr(a,'_capture_pump',None)
            if pump is None:return False
            now=time.monotonic()
            with pump.condition:
                receipt=pump.counters['last_read_monotonic']
                idle=(pump.permitted() and pump.error is None and a.calibrated and not pump.assembler.frames
                      and pump.latest is None and not pump.output_active and now>=pump.suppress_until
                      and not a.sounds.music and receipt is not None and 0<=now-receipt<=.3)
                stamp=(pump.generation,pump.assembler.number)
                seen=pump.assembler.seen
                with self.lock:
                    if self.generation!=generation or self.state!='armed':return False
                    if not idle:self.quiet=None;return False
                    if self.quiet is None or self.quiet[:2]!=stamp:
                        self.quiet=(*stamp,seen,now);return False
                    if now-self.quiet[3]<3 or seen-self.quiet[2]<math.ceil(3000/a.audio['chunk_ms']):return False
                    self.state='running'
                    # Commit the final quiet observation and withdraw this source
                    # under its publication lock: no speech event can slip between.
                    pump.retire()
        try:
            if not a.audio_lock.locked():raise RuntimeError('Existing audio owner required')
            # Reuse the exact camera transition: retire/reap PCM then restore it
            # before existing voice('/say') owns playback and output suppression.
            a.phase='processing'
            response=a._capture_visual(lambda agent,text,epoch,expected:self.dispatch(generation),
                                       PURPOSE,self.expected['microphone_epoch'],self.expected)
            if response.get('cancelled'):self.cancel()
            with self.lock:
                if self.generation==generation and self.state=='running':
                    self.state='abstained' if response.get('initiative_abstained') else 'done'
            return True
        except Exception:
            if not self.valid(generation):
                self.cancel()
                return True
            with self.lock:
                if self.generation==generation:
                    self.state='failed'
                    self._schedule_off_locked('child_failed')
            raise RuntimeError('Initiative failed without queued output') from None
        finally:
            if scheduled_attempt:
                with self.lock:
                    # Completion fence covers variable model/playback latency,
                    # and survives OFF/ON or cancellation of this attempt.
                    self.schedule_next_due=max(self.schedule_next_due,time.monotonic()+300)
            a.pending_pcm=None;a.resume_audio=None
            a.phase='listening' if a.listening.is_set() else 'paused'

    def dispatch(self, generation):
        a=self.agent
        info=self.inspect();guard(info['operator'],self.expected,self.deadline,processing=True)
        packet=dict(config=dict(network=dict(llm_base_url=a.config['network']['llm_base_url']),llm=dict(model=a.config['llm']['model'])),
                    port=a.config['servers']['agent']['port'],token=a.config.token,expected=self.expected,
                    deadline=self.deadline,generation=generation)
        process=subprocess.Popen(['/venvs/mini_daemon/bin/python',str(Path(__file__).resolve()),'--snapshot-child'],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        try:
            data=json.dumps(packet).encode()
            while True:
                if not self.valid(generation):raise RuntimeError('Initiative cancelled')
                try:output,_=process.communicate(data,timeout=.2);break
                except subprocess.TimeoutExpired:data=None
            from .spoken_vision import child_result
            result=child_result(output,process.returncode)
            answer,expires=question(result)
            info=self.inspect();guard(info['operator'],self.expected,self.deadline,processing=True)
            with self.lock:
                if self.generation!=generation or self.state!='running':raise RuntimeError('Initiative cancelled')
                self.frame=result['frame']
            if answer is None:return dict(initiative_abstained=True)
            return a.voice('/say',dict(text=answer,session=a.config['conversation']['session']),
                expected_epoch=self.expected['microphone_epoch'],expected_policy_epoch=self.expected['policy_epoch'],
                valid_until=min(expires,self.deadline),allow_barge_in=False,initiative_generation=generation)
        finally:
            if process.poll() is None:process.kill();process.communicate()


def child(packet, snapshot):
    if type(packet) is not dict or set(packet)!={'config','port','token','expected','deadline','generation'}:
        raise ValueError('Exact local initiative packet required')
    deadline=packet['deadline']
    if (type(packet['generation']) is not int or not 0<=packet['generation']<2**63
            or type(deadline) not in (int,float) or not math.isfinite(deadline) or not 0<deadline-time.monotonic()<=60
            or type(packet['port']) is not int or not 1<=packet['port']<=65535
            or type(packet['token']) is not str or len(packet['token'])<32):raise ValueError('Bounded initiative packet required')
    def check():
        began=time.monotonic();conn=http.client.HTTPConnection('127.0.0.1',packet['port'],timeout=.3)
        try:
            conn.request('GET','/initiative',headers={'Authorization':'Bearer '+packet['token']})
            response=conn.getresponse();data=response.read(16001)
            if response.status!=200 or len(data)>16000:raise RuntimeError('Initiative unavailable')
            value=json.loads(data)
            if (type(value) is not dict or set(value)!={'initiative','operator'}
                    or type(value['initiative']) is not dict
                    or type(value['initiative'].get('generation')) is not int
                    or value['initiative']['generation']!=packet['generation']
                    or value['initiative'].get('state')!='running'):
                raise RuntimeError('Initiative changed')
            guard(value['operator'],packet['expected'],deadline,processing=True)
            if time.monotonic()-began>.3:raise RuntimeError('Initiative read expired')
            return began
        finally:conn.close()
    check()
    return snapshot.caption_checked(packet['config'],deadline,PURPOSE,check,question_only=True)


def control(enabled, *, schedule=False, config=None):
    """Thin local authenticated opt-in client; credentials never leave memory."""
    from .config import Config
    from urllib.request import Request,build_opener,ProxyHandler
    from urllib.error import HTTPError
    config=Config() if config is None else config
    opener=build_opener(ProxyHandler({}))
    base='http://127.0.0.1:'+str(config['servers']['agent']['port'])
    def request(path,payload=None):
        item=Request(base+path,data=None if payload is None else json.dumps(payload).encode(),
            headers={'Authorization':'Bearer '+config.token,'Content-Type':'application/json'})
        began=time.monotonic()
        try:
            with opener.open(item,timeout=.3) as response:
                data=response.read(16001)
                if len(data)>16000 or time.monotonic()-began>.3:
                    raise RuntimeError('Local initiative control read expired')
                return json.loads(data)
        except HTTPError as error:
            if path!='/initiative' or payload is not None:raise
            data=error.read(16001)
            if len(data)>16000 or time.monotonic()-began>.3:raise RuntimeError('Local initiative control read expired')
            value=json.loads(data)
            if 'initiative' not in value:raise
            return value
    path='/initiative/schedule' if schedule else '/initiative'
    if enabled is None:
        print(json.dumps(request(path),ensure_ascii=False));return
    value=request('/operator')
    state=request(path) if schedule else request(path)['initiative']
    payload=dict(enabled=enabled,expected_generation=state['generation'],
                 operator_binding=dict(binding(value),expires_at_monotonic=time.monotonic()+59))
    print(json.dumps(request(path,payload),ensure_ascii=False))


def main():
    if sys.argv[1:] in (['auto-on'],['auto-off'],['auto-status']):
        control({'auto-on':True,'auto-off':False,'auto-status':None}[sys.argv[1]],schedule=True)
        return
    if sys.argv[1:] in (['arm'],['off']):
        control(sys.argv[1]=='arm')
        return
    if sys.argv[1:]!=['--snapshot-child']:raise ValueError('Use arm or off')
    path=Path(__file__).with_name('snapshot_vision.py')
    spec=importlib.util.spec_from_file_location('initiative_snapshot',path)
    snapshot=importlib.util.module_from_spec(spec);spec.loader.exec_module(snapshot)
    snapshot.bind_parent_lifetime()
    packet=json.loads(sys.stdin.buffer.read(16001))
    print(json.dumps(child(packet,snapshot)),flush=True)


if __name__=='__main__':
    try:main()
    except BaseException:
        print(json.dumps(dict(kind='companion-spoken-vision-error',phase='operator_other',error_class='RuntimeError')),flush=True)
        raise SystemExit(1)
