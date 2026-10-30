#!/usr/bin/env python3
"""Reachy Mini microphone/speaker bridge. Uses the daemon's shared ALSA devices."""
import array
import base64
from collections import deque
from contextlib import nullcontext
import hmac
import hashlib
import io
import json
import logging
import math
import os
import selectors
import signal
import statistics
import subprocess
import threading
import time
import wave
from uuid import uuid4
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
import webrtcvad
from .logging_utils import TurnLatency, measured, checked_latency

LOG = logging.getLogger('reachy-voice-agent')



STREAM_TIMING_MARKS = ('response_open_begin','response_open_end','first_reply_received',
    'first_motion_enqueued','first_audio_line_received','timeline_wait_begin','timeline_wait_end',
    'aplay_popen_begin','aplay_popen_end','monitor_start_return','first_positive_write')
STREAM_TIMING_FIELDS = frozenset(STREAM_TIMING_MARKS) | {
    'version','agent_boot_id','microphone_epoch','policy_epoch','content_attempt_id',
    'content_binding','started_monotonic','first_positive_write_bytes',
    'consumption_verified','acoustic_verified'}


def validate_stream_timing(value):
    """Exact shared status/finite-consumer contract; no raw content or coercion."""
    def require(good):
        if not good:raise ValueError('Invalid bounded Agent stream timing')
    def number(item, maximum):
        return type(item) in (int,float) and 0<=item<=maximum and math.isfinite(item)
    def identity(item):
        return type(item) is str and len(item)==32 and all(c in '0123456789abcdef' for c in item)
    require(type(value) is dict and set(value)==STREAM_TIMING_FIELDS)
    require(type(value['version']) is int and value['version']==1)
    require(type(value['agent_boot_id']) is str and 1<=len(value['agent_boot_id'])<=128)
    for key in ('microphone_epoch','policy_epoch'):
        require(type(value[key]) is int and 0<=value[key]<2**63)
    require(number(value['started_monotonic'],1e15))
    require(type(value['content_binding']) is str and value['content_binding'] in ('pending','bound','invalid'))
    attempt=value['content_attempt_id']
    require(attempt is None or identity(attempt))
    require(value['content_binding']!='bound' or identity(attempt))
    require(value['content_binding']!='pending' or attempt is None)
    for key in STREAM_TIMING_MARKS:
        require(value[key] is None or number(value[key],86400))
    for begin,end in (('response_open_begin','response_open_end'),('timeline_wait_begin','timeline_wait_end'),
                      ('aplay_popen_begin','aplay_popen_end')):
        require(value[end] is None or (value[begin] is not None and value[end]>=value[begin]))
    count=value['first_positive_write_bytes']
    require((count is None and value['first_positive_write'] is None) or
            (type(count) is int and 0<count<2**31 and value['first_positive_write'] is not None))
    require(value['consumption_verified'] is False and value['acoustic_verified'] is False)
    return dict(value)


class Agent:
    def __init__(self, config):
        self.config = config
        self.audio = config['audio']
        self._capture_source_generation = 0
        self._capture_pump = None
        self._capture_packet = None
        self._capture_suspended = False
        self._capture_enabled()
        self.http = build_opener(ProxyHandler({}))
        self.listening = threading.Event()
        from .microphone import MicrophoneState
        self.microphone = MicrophoneState(config.path(config['paths']['data_dir']) / 'microphone-state.json',
                                          config['conversation']['listen_on_start'])
        from .conversation_mode import ConversationMode
        self.conversation_mode = ConversationMode(config.path(config['paths']['data_dir']) / 'conversation-mode.json',
            'alice_test' if config['conversation'].get('speech_address_prefix') == 'Алиса, ' else 'normal')
        from .motion_policy import MotionPolicy
        self.motion_policy=MotionPolicy(config.path(config['guarded_motion']['policy_path']))
        self.agent_boot_id = str(uuid4())
        self.microphone_epoch = self.microphone.epoch
        self.microphone_owner_id = None
        self.microphone_lock = threading.Lock()
        self.playback_process = None
        self.voice_response = None
        self.pending_pcm = None
        self.resume_audio = None
        self.resume_blocked_reason = None
        self.last_voice_at = None
        self.current_reply_text = ''
        self.interruptions = 0
        self.barge_in_error = None
        self.capture_active = False
        from .durable_intent import DurableIntent
        self.durable_intent=DurableIntent(config.path(config['paths']['data_dir'])/'durable-intent.json',
            default_listening=config['conversation']['listen_on_start'])
        if self.durable_intent.listening_allowed(self):
            self.listening.set()
        self.stopping = threading.Event()
        self.audio_lock = threading.Lock()
        self.phase = 'starting'
        self.threshold = self.audio['rms_floor']
        self.last_error = None
        self.last_transcript = None
        self.last_input = None
        self.turns = 0
        self.calibrated = False
        self.playback_configured = False
        from .volume import PlaybackVolume
        self.volume = PlaybackVolume(config.path(config['paths']['data_dir']) / 'volume-state.json',
                                     self.audio.get('playback_mixer', {}).get('volume_percent', 95))
        self.volume_lock = threading.Lock()
        self.vad = webrtcvad.Vad(self.audio['vad_mode'])
        from .expression_player import ExpressionPlayer
        self.expressions = ExpressionPlayer(config, self.request, self.stopping,
            permitted=self.motor_permitted,binding=self.expression_binding)
        self.chunk_bytes = self.audio['sample_rate'] * 2 * self.audio['chunk_ms'] // 1000
        from .sound_monitor import SoundMonitor
        self.sounds = SoundMonitor(self)
        from .motion_proxy import MotionProxy
        self.motion_proxy = MotionProxy(config['guarded_motion']['enabled'] and config['guarded_motion'].get('transport','native')=='native',
                                        config.path(config['guarded_motion']['socket_path']),self.operator_status)
        self.vad_bytes = self.audio['sample_rate'] * 2 * self.audio['vad_frame_ms'] // 1000
        from .initiative import Initiative
        self.initiative = Initiative(self)
        self.durable_intent.begin(self)
        from .sensory_bridge import SensoryBridge
        self.sensory = SensoryBridge(self)
        from .barge_trial import BargeTrial
        self.barge_trial = BargeTrial(self)

    def stop_speaker(self, abort_stream=True):
        trial=getattr(self,'barge_trial',None)
        if trial is not None:trial.cancel()
        candidate = getattr(getattr(self, '_capture_pump', None), 'candidate', None)
        if candidate is not None:candidate.cancel()
        if hasattr(self,'sensory'):self._sensory_withdraw()
        self._premask_off('speaker_stop')
        if hasattr(self,'initiative'):self.initiative.cancel(stop_audio=False)
        process = self.playback_process
        if process is not None and process.poll() is None:
            process.terminate()
        # Wake a blocked urllib reader as well as stopping physical playback.
        response = self.voice_response
        if abort_stream and response is not None:
            try:
                import socket
                response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
            except (AttributeError, OSError):
                pass

    def _premask_off(self, reason='off'):
        observer = getattr(self, '_premask_last', None)
        if observer is not None:
            try: observer.off(reason)
            except Exception: pass

    def premask_status(self):
        observer = getattr(self, '_premask_last', None)
        if observer is None:
            return dict(enabled=False, purpose='local_premask_activity_only', reason='default_off')
        try: return observer.snapshot()
        except Exception:
            self._premask_off('status_failure')
            return dict(enabled=False, purpose='local_premask_activity_only', reason='status_failure')

    def set_premask(self, payload):
        """Diagnostic opt-in only: never grants microphone or starts a reader."""
        if type(payload) is not dict or type(payload.get('enabled')) is not bool:
            raise ValueError('Boolean diagnostic opt-in required')
        if payload['enabled'] is False:
            if set(payload) != {'enabled'}: raise ValueError('Exact diagnostic off required')
            self._premask_off()
            observer = getattr(self, '_premask_last', None)
            if observer is not None and observer.thread is not threading.current_thread():
                try: observer.thread.join(timeout=.2)
                except RuntimeError: pass
            return self.premask_status()
        if set(payload) != {'enabled', 'binding'} or type(payload['binding']) is not dict:
            raise ValueError('Exact diagnostic authority required')
        b = payload['binding']
        if (set(b) != {'agent_boot_id', 'microphone_epoch', 'policy_epoch', 'source_generation',
                       'owner_id', 'expires_at_monotonic'}
                or type(b['agent_boot_id']) is not str or not 1 <= len(b['agent_boot_id']) <= 128
                or b['owner_id'] is not None
                or any(type(b[k]) is not int or not 0 <= b[k] < 2**63
                       for k in ('microphone_epoch', 'policy_epoch', 'source_generation'))
                or type(b['expires_at_monotonic']) not in (int, float)
                or not math.isfinite(b['expires_at_monotonic'])):
            raise ValueError('Exact bounded diagnostic authority required')
        # Do not acquire pump.condition while holding policy.lock: the existing
        # reader takes a policy snapshot under pump.condition.
        with self.microphone_lock:
            pump = getattr(self, '_capture_pump', None)
            if pump is None: raise RuntimeError('Existing reader required')
            with pump.condition:
                policy, owner = self.motion_policy.owned_snapshot()
                previous = getattr(self, '_premask_last', None)
                if previous is not None and (previous.active or previous.thread.is_alive()):
                    raise RuntimeError('Previous diagnostic worker not reaped')
                if (b['agent_boot_id'] != self.agent_boot_id
                        or b['microphone_epoch'] != self.microphone_epoch
                        or b['policy_epoch'] != policy['epoch']
                        or b['source_generation'] != pump.generation
                        or self.microphone_owner_id is not None or owner is not None
                        or self.microphone.error is not None or not pump.permitted()
                        or pump.thread is None or not pump.thread.is_alive()
                        or not 0 < b['expires_at_monotonic']-time.monotonic() <= 60):
                    raise RuntimeError('Diagnostic authority or source changed')
                from .capture_pump import PremaskCanary
                observer = PremaskCanary(pump, b['expires_at_monotonic'])
                self._premask_last = pump.canary = observer
                try: observer.thread.start()
                except Exception:
                    observer.off('worker_start_failure')
                    raise RuntimeError('Diagnostic worker unavailable') from None
        return self.premask_status()

    def _premask_written(self, pump, process, attempt, start, count, rate):
        if pump is None or pump.canary is None or not pump.canary.active:
            return
        try:
            with pump.condition:
                if not pump.canary.permitted():
                    pump.canary.off('authority_or_deadline')
                    return
                pump.canary.written(pump.playback_generation, process.pid, attempt,
                                    start, count, rate, time.monotonic())
        except Exception:
            self._premask_off('reference_failure')

    def motor_permitted(self):
        policy=self.motion_policy.snapshot()
        permitted=(self.config['guarded_motion']['enabled'] is True and policy['motor_enabled'] is True
                and policy['quiet'] is False and policy['privacy_all'] is False)
        guard=getattr(self,'_sensory_expression_guard',None)
        if guard is not None and guard['version']==self.expressions.version:
            b=guard['authority'];mode=self.conversation_mode.snapshot();intent=self.durable_intent.snapshot()
            permitted=bool(permitted and guard['permit']() and time.monotonic()<guard['expires']
                and self.agent_boot_id==b['agent_boot_id'] and self.microphone_epoch==b['microphone_epoch']
                and self.microphone.enabled and self.listening.is_set() and self.microphone.error is None
                and self.microphone_owner_id is None and self.motion_policy.owner_id is None
                and policy['epoch']==b['policy_epoch'] and mode['generation']==b['mode_generation']
                and intent['generation']==b['intent_generation'] and not self.stopping.is_set()
                and self.phase in ('listening','music'))
        return permitted

    def sensory_authority(self):
        """Trusted control snapshot; never inferred from a model/sound event."""
        with self.microphone_lock,self.motion_policy.lock,self.durable_intent.lock,self.conversation_mode.lock:
            policy=self.motion_policy.snapshot();intent=self.durable_intent.snapshot();mode=self.conversation_mode.snapshot()
            binding=dict(agent_boot_id=self.agent_boot_id,microphone_epoch=self.microphone_epoch,
                policy_epoch=policy['epoch'],intent_generation=intent['generation'],mode_generation=mode['generation'],
                microphone_owner_id=self.microphone_owner_id,motion_policy_owner_id=self.motion_policy.owner_id,
                motor_enabled=policy['motor_enabled'])
            enabled=bool(self.microphone.enabled and self.listening.is_set() and intent['listening_requested']
                and not self.durable_intent.error and self.microphone.error is None and mode['error'] is None
                and self.microphone_owner_id is None and self.motion_policy.owner_id is None
                and policy['epoch'] is not None and not policy['quiet'] and not policy['privacy_all'] and not self.stopping.is_set())
            return binding,enabled,policy['privacy_all']

    def _sensory_withdraw(self, preserve_visual=False):
        trial=getattr(self,'barge_trial',None)
        if not preserve_visual and trial is not None:trial.cancel()
        candidate = getattr(getattr(self, '_capture_pump', None), 'candidate', None)
        if not preserve_visual and candidate is not None:candidate.cancel()
        bridge=getattr(self,'sensory',None)
        if bridge is not None:bridge.invalidate(preserve_visual=preserve_visual)
        guard=getattr(self,'_sensory_expression_guard',None)
        if guard is not None:
            with self.expressions.condition:
                if guard['version']==self.expressions.version:self.expressions.hold()

    def sensory_attention(self,proposal,permit):
        """One finite attention in the existing expression lane; no new owner."""
        if not permit():return False
        e=self.expressions
        # Existing locks serialize enqueue with real OFF/STOP/mode controls.
        with self.microphone_lock,self.motion_policy.lock,self.durable_intent.lock,self.conversation_mode.lock:
            p=self.motion_policy.snapshot();iv=self.durable_intent.snapshot();mode=self.conversation_mode.snapshot();b=proposal['authority']
            if (not permit() or not self.microphone.enabled or not self.listening.is_set() or self.microphone.error is not None
                or self.durable_intent.error or not iv['listening_requested'] or mode['error'] is not None
                or self.microphone_owner_id is not None or self.motion_policy.owner_id is not None
                or self.agent_boot_id!=b['agent_boot_id'] or self.microphone_epoch!=b['microphone_epoch']
                or p['epoch']!=b['policy_epoch'] or iv['generation']!=b['intent_generation'] or mode['generation']!=b['mode_generation']
                or not self.config['guarded_motion']['enabled'] or not p['motor_enabled'] or p['quiet'] or p['privacy_all']
                or self.phase not in ('listening','music') or self.stopping.is_set() or not e.settings.get('enabled') or not e.thread.is_alive()):return False
            with e.condition:
                # Do not preempt an existing motion/timeline or a foreground turn.
                if e.completed<e.version or e.state and e.state[0] in ('timeline','speaking','processing','dance'):return False
                e.cues=[];e.clock=None;e.state=('reacting','surprised');e.version+=1
                version=e.version
                e.state_binding=(dict(agent_boot_id=self.agent_boot_id,microphone_epoch=self.microphone_epoch,
                    microphone_enabled=True,policy_epoch=p['epoch']) if e.stock else None)
                self._sensory_expression_guard=dict(version=version,authority=dict(b),permit=permit,expires=proposal['expires_monotonic'])
                e.condition.notify_all()
        # A hold withdraws future output; it does not pretend an active HTTP
        # expression has settled. Retain this callback until its terminal return.
        with e.condition:
            while e.completed<version and e.thread.is_alive():
                if not permit() and e.version==version:e.hold()
                e.condition.wait(.05)
            accepted=bool(permit() and e.version==version and e.completed>=version and e.last_error is None
                and e.last_expression and e.last_expression.get('phase')=='reacting')
            # Retire only our own finite state. An expired sensory guard must
            # never keep blocking later normal speech/attention expressions.
            if e.version==version:e.hold()
            guard=getattr(self,'_sensory_expression_guard',None)
            if guard is not None and guard['version']==version:self._sensory_expression_guard=None
            return accepted

    def expression_binding(self):
        with self.microphone_lock:
            return dict(agent_boot_id=self.agent_boot_id,microphone_epoch=self.microphone_epoch,
                microphone_enabled=self.microphone.enabled,policy_epoch=self.motion_policy.snapshot()['epoch'])

    def durable_update(self, **fields):
        try:return self.durable_intent.update(**fields)
        except BaseException:
            self.listening.clear()
            pump=getattr(self,'_capture_pump',None)
            if pump is not None:pump.retired.set()
            self.pending_pcm=None;self.resume_audio=None
            self.microphone.enabled=False;self.microphone.error='Durable intent persistence failed'
            process=self.playback_process
            if process is not None and process.poll() is None:process.terminate()
            raise

    def set_motion_policy(self,value):
        if not isinstance(value,dict):raise ValueError('Policy object required')
        value=dict(value)
        parameters={key:value.pop(key) for key in ('expected_boot_id','expected_epoch','owner_id','expected_owner_id') if key in value}
        if parameters:
            if (parameters.get('expected_boot_id')!=self.agent_boot_id or type(parameters.get('expected_epoch')) is not int
                    or not 0<=parameters['expected_epoch']<2**63):raise RuntimeError('Complete current policy boot/epoch required')
            if any(key in parameters and parameters[key] is None for key in ('owner_id','expected_owner_id')):
                raise ValueError('Policy owner cannot be null')
            parameters.pop('expected_boot_id')
        with self.motion_policy.lock:
            if (set(value)!={'motor_enabled','quiet','privacy_all'} or any(type(x) is not bool for x in value.values())):
                raise ValueError('Expected boolean motion policy')
            epoch=parameters.get('expected_epoch')
            if epoch is not None and (type(epoch) is not int or not 0<=epoch<2**63):raise ValueError('Policy epoch required')
            for key in ('owner_id','expected_owner_id'):
                owner=parameters.get(key)
                if owner is not None and (type(owner) is not str or not 1<=len(owner)<=128 or epoch is None):raise ValueError('Policy owner required')
            before=self.motion_policy.snapshot()
            if (before['epoch'] is None or before['epoch']>=2**63-1 or ('expected_epoch' in parameters and parameters['expected_epoch']!=before['epoch'])
                or ('expected_owner_id' in parameters and parameters['expected_owner_id']!=self.motion_policy.owner_id)):
                raise RuntimeError('Policy authority changed')
            if value['quiet'] or value['privacy_all'] or parameters.get('owner_id') is not None:
                self.durable_update(listening=False,automatic=False)
            result=self.motion_policy.save(value,**parameters)
        if hasattr(self,'initiative'):self.initiative.cancel()
        if hasattr(self,'sensory'):self._sensory_withdraw()
        pump = self._capture_retire() if self._capture_enabled() else None
        try:
            if result['quiet'] or result['privacy_all']:
                self.stop_speaker();self.resume_audio=None;self.pending_pcm=None
            if not result['motor_enabled'] or result['quiet'] or result['privacy_all']:self.expressions.hold()
            if result['quiet'] or result['privacy_all']:self.listening.clear()
            return result
        finally:
            if pump is not None: pump.close()

    def set_microphone(self, enabled, listen=True, *, expected_boot_id=None, expected_epoch=None,
                       owner_id=None,expected_owner_id=None, admission=None, preserve_owner=False):
        retired_capture = None
        changed=False
        try:
            if type(preserve_owner) is not bool or (preserve_owner and enabled is not False):raise ValueError('Owner preservation is OFF-only')
            if type(listen) is not bool:raise ValueError('listen must be boolean')
            if not isinstance(enabled, bool):
                raise ValueError('enabled must be boolean')
            if expected_boot_id is not None or expected_epoch is not None:
                if not isinstance(expected_boot_id,str) or not expected_boot_id or type(expected_epoch) is not int or not 0<=expected_epoch<2**63:
                    raise ValueError('Complete microphone authority required')
            for owner in (owner_id,expected_owner_id):
                if owner is not None and (not isinstance(owner,str) or not 1<=len(owner)<=128 or expected_boot_id is None):
                    raise ValueError('Bounded microphone owner requires authority')
            with self.microphone_lock:
                try:
                    with (self.motion_policy.lock if admission is not None else nullcontext()), (self.initiative.lock if admission is not None else nullcontext()), (self.durable_intent.lock if admission is not None else nullcontext()):
                        if expected_boot_id is not None and (expected_boot_id!=self.agent_boot_id or expected_epoch!=self.microphone_epoch):
                            raise RuntimeError('Microphone authority changed')
                        if expected_owner_id is not None and expected_owner_id!=self.microphone_owner_id:
                            raise RuntimeError('Microphone owner changed')
                        if admission is not None:admission()
                        if preserve_owner:owner_id=self.microphone_owner_id
                        if self.microphone.epoch>=2**63-1:raise ValueError('Microphone epoch exhausted')
                        previous_owner=self.microphone_owner_id
                        if not enabled or not listen or owner_id is not None:
                            self.durable_update(listening=False,automatic=False)
                        self.microphone_epoch += 1
                        changed=True
                        self.microphone_owner_id=owner_id
                        self.listening.clear()
                        if not enabled:self.microphone.enabled=False
                        try:self.microphone.save(enabled)
                        except (OSError, ValueError):
                            self.microphone.enabled=False
                            raise
                        if enabled and listen:
                            policy=self.motion_policy.snapshot()
                            if (owner_id is None and previous_owner is None and self.motion_policy.owner_id is None
                                and self.microphone.error is None and not policy['quiet'] and not policy['privacy_all']):
                                self.durable_update(listening=True)
                            self.listening.set()
                finally:
                    # No pump.condition or output shutdown while policy/intent
                    # locks are held. A changed epoch already fences the reader.
                    if changed:
                        if hasattr(self,'sensory'):self._sensory_withdraw()
                        if hasattr(self,'initiative'):self.initiative.cancel()
                        retired_capture = self._capture_retire() if self._capture_enabled() else None
                        if not enabled or self.microphone.error is not None or not self.microphone.enabled:
                            self.expressions.hold();self.pending_pcm=None;self.resume_audio=None;self.stop_speaker()
                self.sounds.reset()
            if retired_capture is not None: retired_capture.close()
            return {'ok': True, 'microphone_enabled': enabled, 'capture_active': self.capture_active,
                    'agent_boot_id': self.agent_boot_id, 'microphone_epoch': self.microphone_epoch,
                    'microphone_owner_id':self.microphone_owner_id,'listening':self.listening.is_set()}
        finally:
            if retired_capture is not None: retired_capture.close()

    def vision_route_update(self, **fields):
        bound, previous = self._vision_route
        self._vision_route = (bound, dict(previous, **fields))

    def vision_route_status(self, policy):
        bound, result = getattr(self, '_vision_route', (None, None))
        if (bound is None or bound['agent_boot_id'] != self.agent_boot_id
                or bound['microphone_epoch'] != self.microphone_epoch
                or bound['policy_epoch'] != policy['epoch']):
            return None
        return dict(result)

    def vision_route_failure(self, exc):
        from .spoken_vision import ERROR_PHASES, ERROR_CLASSES
        # Compare only complete, fixed allowlisted messages; never retain exc text.
        for phase in ERROR_PHASES:
            for name in ERROR_CLASSES:
                if (type(exc) is RuntimeError and exc.args ==
                        ('Spoken snapshot child failed phase='+phase+' error_class='+name,)):
                    self.vision_route_update(stage='dispatch', result='typed_child_failure',
                                             child_phase=phase, child_error_class=name)
                    return
        self.vision_route_update(stage='dispatch', result='untyped_failure')

    def _stream_timing_begin(self, epoch, policy_epoch):
        row=dict.fromkeys(STREAM_TIMING_MARKS)
        row.update(version=1,agent_boot_id=self.agent_boot_id,microphone_epoch=epoch,policy_epoch=policy_epoch,
                   content_attempt_id=None,content_binding='pending',started_monotonic=time.monotonic(),
                   first_positive_write_bytes=None,consumption_verified=False,acoustic_verified=False)
        probe=[row]
        self._stream_timing=probe
        return probe

    def _stream_timing_mark(self, probe, name, count=None):
        if (probe is None or getattr(self,'_stream_timing',None) is not probe
                or name not in STREAM_TIMING_MARKS or probe[0][name] is not None):return
        elapsed=time.monotonic()-probe[0]['started_monotonic']
        if not math.isfinite(elapsed) or not 0<=elapsed<=86400:return
        if name=='first_positive_write' and (type(count) is not int or not 0<count<2**31):return
        row=dict(probe[0]);row[name]=round(elapsed,6)
        if name=='first_positive_write':row['first_positive_write_bytes']=count
        probe[0]=row

    def _stream_timing_bind(self, probe, attempt):
        if probe is None or getattr(self,'_stream_timing',None) is not probe or attempt is None:return
        row=probe[0]
        valid=type(attempt) is str and len(attempt)==32 and all(c in '0123456789abcdef' for c in attempt)
        if row['content_binding']=='invalid':return
        if not valid or (row['content_attempt_id'] is not None and row['content_attempt_id']!=attempt):
            probe[0]=dict(row,content_binding='invalid')
        elif row['content_attempt_id'] is None:
            probe[0]=dict(row,content_attempt_id=attempt,content_binding='bound')

    def stream_timing_status(self, policy):
        probe=getattr(self,'_stream_timing',None)
        if probe is None:return None
        row=probe[0]
        if (row['agent_boot_id']!=self.agent_boot_id or row['microphone_epoch']!=self.microphone_epoch
                or row['policy_epoch']!=policy['epoch']):return None
        try:return validate_stream_timing(row)
        except ValueError:return None

    def status(self):
        motion_status = self.motion_actor_status()
        latency = self.latency_status()
        with self.microphone_lock:
            policy = self.motion_policy.snapshot()
            return {**({'last_voice_latency':latency} if latency is not None else {}), 'stream_timing': self.stream_timing_status(policy), 'vision_route': self.vision_route_status(policy), 'listening': self.listening.is_set(), 'phase': self.phase,
                             'agent_boot_id': self.agent_boot_id, 'microphone_epoch': self.microphone_epoch,
                             'threshold_rms': self.threshold, 'last_error': self.last_error,
                             'last_transcript': self.last_transcript, 'turns': self.turns,
                             'last_input': dict(self.last_input) if self.last_input is not None else None,
                             'durable_startup': self.durable_intent.status(self),
                             'microphone_enabled': self.microphone.enabled,
                             'interruptions': self.interruptions, 'resumable_reply': self.resume_audio is not None, 'barge_in_error': self.barge_in_error,
                             'barge_candidate': self.barge_candidate_status(),
                             'barge_trial': self.barge_trial.snapshot() if hasattr(self,'barge_trial') else None,
                             'resume_blocked_reason': self.resume_blocked_reason,
                             'playback_cursor_provenance': 'wall_time_estimate',
                             'motion_actor': motion_status,'motion_policy':policy,
                             'volume_percent': self.volume.percent,
                             'volume_control_enabled': self.audio.get('playback_mixer', {}).get('enabled', False),
                             'capture_active': self.capture_active,
                             'capture_pcm': (self._capture_pump.snapshot()
                                 if getattr(self, '_capture_pump', None) is not None else None),
                             'sound_mode': 'music' if self.sounds.music else 'conversation', 'sound_error': self.sounds.last_error,
                             'sensory': self.sensory.status() if hasattr(self,'sensory') else None,
                             'microphone_state_error': self.microphone.error,
                             'expression': self.expressions.last_expression,
                             'expression_error': self.expressions.last_error}

    def motion_actor_status(self):
        if self.config['guarded_motion'].get('transport','native')=='stock':
            return dict(enabled=self.config['guarded_motion']['enabled'],ready=False,transport='stock',
                reason='stock_factory_api_not_native_actor')
        return self.motion_proxy.status()

    def operator_status(self):
        # Separate from /status: the native monitor must not recursively ask
        # its own IPC server for readiness while fetching operator authority.
        with self.microphone_lock:
            policy,policy_owner=self.motion_policy.owned_snapshot()
            return dict(agent_boot_id=self.agent_boot_id,microphone_epoch=self.microphone_epoch,
                        microphone_owner_id=self.microphone_owner_id,
                        microphone_enabled=self.microphone.enabled,capture_active=self.capture_active,
                        phase=self.phase,listening=self.listening.is_set(),microphone_state_error=self.microphone.error,
                        motion_policy=policy,motion_policy_owner_id=policy_owner,
                        expression_version=self.expressions.version)

    def set_volume(self, percent):
        from .volume import validate_percent
        validate_percent(percent)
        if not self.audio.get('playback_mixer', {}).get('enabled', False):
            raise ValueError('Playback mixer control is disabled in configuration')
        with self.volume_lock:
            self.configure_playback(percent)
            self.volume.save(percent)
            self.playback_configured = True
        return {'ok': True, 'volume_percent': self.volume.percent}

    def configure_playback(self, percent=None):
        settings = self.audio.get('playback_mixer', {})
        if not settings.get('enabled', False):
            return
        percent = self.volume.percent if percent is None else percent
        subprocess.run(['amixer', '-c', str(settings['card']), 'sset',
                        settings['control'], str(percent) + '%', 'mute' if percent == 0 else 'unmute'],
                       capture_output=True, check=True, timeout=self.config['timeouts']['http'])
        LOG.info('playback_mixer card=%s control=%s volume=%s%%', settings['card'],
                 settings['control'], percent)

    def request(self, base, path, payload=None, timeout=None):
        request = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json',
                                   'Authorization': 'Bearer ' + self.config.token})
        try:
            with self.http.open(request, timeout=timeout or self.config['timeouts']['client']) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError('Hub HTTP %s: %s' % (exc.code, exc.read().decode()[:600])) from exc

    def _barge_candidate_enabled(self):
        enabled=self.config['conversation'].get('barge_candidate_enabled',False)
        trial_only=self.config['conversation'].get('barge_candidate_trial_only',False)
        if type(enabled) is not bool or type(trial_only) is not bool:
            raise ValueError('Boolean barge candidate/trial-only opt-ins required')
        if enabled and (not self._capture_enabled() or self.config['conversation']['barge_in'].get('confirm_with_stt') is not True):
            raise ValueError('Candidate requires existing shared capture and STT confirmation')
        if enabled and trial_only:
            trial=getattr(self,'barge_trial',None)
            return trial is not None and trial.active()
        return enabled

    def barge_candidate_status(self):
        candidate=getattr(getattr(self,'_capture_pump',None),'candidate',None)
        return candidate.status() if candidate is not None else dict(enabled=False,reason='default_off')

    def barge_candidate_effect(self, candidate, token, action):
        """Candidate has no grants. Re-admit AFTER STT at actual output controls."""
        def admit():
            if (self.config['conversation'].get('barge_candidate_trial_only',False)
                    and not self._barge_candidate_enabled()):raise RuntimeError('Barge trial authority withdrawn')
            if not candidate.valid_locked(token):raise RuntimeError('Barge candidate authority withdrawn')
            candidate.interrupted.set()
            self.interruptions+=1
            self.pending_pcm=self.resume_audio=None
            self.resume_blocked_reason='candidate_output_resume_disabled'
            with candidate.condition:
                candidate.counts['accepted']+=1;candidate.last_gate='accepted_'+action
        if action=='stop':
            # Existing MIC mutation performs the final callback under real
            # MIC/policy/initiative/intent locks, with boot+epoch CAS.
            try:
                self.set_microphone(False,expected_boot_id=candidate.binding[0][0],
                    expected_epoch=candidate.binding[0][1],admission=admit)
                return True
            except RuntimeError:return False
        if action!='answer':return False
        pump=candidate.pump
        with self.microphone_lock,pump.condition,self.motion_policy.lock,self.initiative.lock,self.durable_intent.lock,self.conversation_mode.lock:
            if not candidate.valid_locked(token):return False
            process=self.playback_process
            try:admit()
            except RuntimeError:return False
            self.phase='recording'
            self.expressions.hold()
            # Stop only the exact admitted owned player, never a newer reply.
            # Voice finally still owns terminal/reap. No output resume/input replay.
            process.terminate()
            self.barge_in_error=None
            return True

    def _capture_enabled(self):
        enabled = self.config['conversation'].get('capture_pump_enabled', False)
        if type(enabled) is not bool:
            raise ValueError('Boolean capture pump opt-in required')
        if enabled:
            barge = self.config['conversation']['barge_in']
            if (self.config['streaming']['enabled'] is not True or barge['enabled'] is not True
                    or barge.get('confirm_with_stt', False) is not True or self.audio['sample_rate'] != 16000):
                raise ValueError('Capture pump requires existing streaming mono AEC and confirmed barge-in')
        return enabled

    def _capture_retire(self):
        trial=getattr(self,'barge_trial',None)
        if trial is not None:trial.cancel()
        pump = getattr(self, '_capture_pump', None)
        if pump is not None:
            pump.retire()
        self._capture_packet = None
        self.pending_pcm = None
        control = getattr(self, '_capture_control', None)
        if control is not None:
            control.stop.set()
            control.pcm = None
            control.capture_permitted = lambda: False
        return pump

    def _capture_get(self):
        from .capture_pump import CapturePump
        pump = getattr(self, '_capture_pump', None)
        if pump is not None and not pump.permitted():
            pump.close()
            self._capture_pump = pump = None
        if pump is None:
            self._capture_source_generation = getattr(self, '_capture_source_generation', 0) + 1
            pump = CapturePump(self, self._capture_source_generation)
            self._capture_pump = pump
            pump.start()
        return pump

    def _capture_fresh(self):
        pump = getattr(self, '_capture_pump', None)
        return pump is not None and pump.admitted(getattr(self, '_capture_packet', None))

    def _capture_pending(self, value):
        from .capture_pump import Utterance
        with self.microphone_lock:
            self._capture_packet = value if isinstance(value, Utterance) else None
            if self._capture_fresh():
                return value.pcm
            self._capture_packet = None
            return None

    def _capture_visual(self, dispatch, text, epoch, expected):
        if not self._capture_enabled():
            return dispatch(self, text, epoch, expected)
        pump = self._capture_retire()
        if pump is not None:
            pump.close()
        self._capture_suspended = True
        try:
            return dispatch(self, text, epoch, expected)
        finally:
            self._capture_suspended = False
            policy = self.motion_policy.snapshot()
            if (self.microphone.enabled and self.listening.is_set() and not self.stopping.is_set()
                    and epoch == self.microphone_epoch and policy['epoch'] == expected['policy_epoch']
                    and not policy['quiet'] and not policy['privacy_all']):
                self._capture_get()

    def capture(self, during_reply=False, on_speech=None, stop_event=None, idle_deadline=None, skip_expression=False):
        if not self._capture_enabled():
            return self._finite_capture(during_reply, on_speech, stop_event, idle_deadline, skip_expression)
        if during_reply or on_speech is not None:
            raise RuntimeError('Capture pump barge-in requires the shared consumer')
        if (not self.microphone.enabled or not self.listening.is_set() or self.stopping.is_set()
                or self._capture_suspended):
            return None
        if not skip_expression:
            self.expressions.set('neutral')
            self.phase = 'listening'
        previous = getattr(self, '_capture_control', None)
        if previous is not None and previous.thread.is_alive():
            raise RuntimeError('Previous capture control still active')
        pump = self._capture_get()
        pump.mode(False)
        packet = pump.event(stop=stop_event, idle_deadline=idle_deadline, final_only=True)
        with self.microphone_lock:
            if packet is not None and pump.claim(packet):
                self._capture_packet = packet
                pump.mode(True)
                return packet.pcm
        if pump.error is not None:
            raise RuntimeError(pump.error)
        return None

    def _finite_capture(self, during_reply=False, on_speech=None, stop_event=None, idle_deadline=None, skip_expression=False):
        epoch = self.microphone_epoch
        def active():
            return self.microphone.enabled and (during_reply or self.listening.is_set()) and not self.stopping.is_set() and epoch == self.microphone_epoch and not (stop_event and stop_event.is_set())
        if not active():
            return None
        if not during_reply and not skip_expression:
            # Optional movement is queued independently; factory completion
            # must not delay microphone readiness.
            self.expressions.set('neutral')
            self.phase = 'listening'
        if not active():
            return None
        confirmed = False
        barge_voiced = 0
        chunks_seen = 0
        barge = self.config['conversation'].get('barge_in', {})
        command = ['arecord', '-q', '-D', self.audio['capture_device'], '-f', 'S16_LE',
                   '-r', str(self.audio['sample_rate']), '-c', '1', '-t', 'raw']
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            self.capture_active = True
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            pre = deque(maxlen=self.audio['pre_roll_chunks'])
            frames = []
            noise = []
            voiced = 0
            silent = 0
            calibrating = not self.calibrated
            try:
                while active():
                    if idle_deadline is not None and time.monotonic() >= idle_deadline and not frames:
                        return None
                    if not selector.select(timeout=1):
                        if process.poll() is not None:
                            raise RuntimeError(process.stderr.read().decode()[:500])
                        continue
                    chunk = process.stdout.read(self.chunk_bytes)
                    if len(chunk) != self.chunk_bytes:
                        raise RuntimeError('Microphone stream ended: ' + process.stderr.read().decode()[:500])
                    chunks_seen += 1
                    if not during_reply:
                        self.sounds.feed(chunk)
                        if self.sounds.music:
                            frames = []; voiced = silent = 0
                            pre.clear()
                            self.phase = 'music'
                            continue
                    samples = array.array('h', chunk)
                    rms = math.sqrt(sum(s*s for s in samples) / len(samples))
                    if calibrating:
                        noise.append(rms)
                        pre.append(chunk)
                        if len(noise) >= self.audio['calibration_chunks']:
                            floor = self.audio['rms_floor']
                            self.threshold = max(floor, statistics.median(noise) * self.audio['noise_multiplier'])
                            LOG.info('listening threshold_rms=%.1f', self.threshold)
                            calibrating = False
                            self.calibrated = True
                        continue
                    speech_frames = sum(self.vad.is_speech(chunk[i:i+self.vad_bytes], self.audio['sample_rate'])
                                        for i in range(0, len(chunk), self.vad_bytes))
                    threshold = self.threshold * (barge.get('threshold_multiplier', 1) if during_reply else 1)
                    loud = rms >= threshold and speech_frames >= self.audio['min_speech_frames']
                    if during_reply and not confirmed:
                        eligible = chunks_seen > barge.get('warmup_chunks', 9)
                        barge_voiced = barge_voiced + 1 if loud and eligible else 0
                    if not frames:
                        pre.append(chunk)
                        if loud:
                            frames = list(pre)
                            voiced = 1
                            if not during_reply:
                                self.phase = 'recording'
                                self.expressions.set('listening', force=True)
                        continue
                    frames.append(chunk)
                    if loud:
                        self.last_voice_at = time.monotonic()
                        voiced += 1
                        silent = 0
                    else:
                        silent += 1
                    if during_reply and not confirmed and loud and barge_voiced >= barge['min_voiced_chunks']:
                        accepted = on_speech(b''.join(frames)) if on_speech else True
                        confirmed = accepted is not False
                        if not confirmed:
                            barge_voiced = 0
                            frames = []
                            voiced = silent = 0
                            continue
                    if silent >= self.audio['silence_chunks'] or len(frames) >= self.audio['max_recording_seconds'] * 1000 / self.audio['chunk_ms']:
                        if voiced >= self.audio['min_voiced_chunks'] and (not during_reply or confirmed):
                            return b''.join(frames) if active() else None
                        frames = []
                        voiced = silent = 0
                        if not during_reply:
                            self.phase = 'listening'
                return None
            finally:
                selector.close()
                process.terminate()
                try:
                    process.wait(timeout=self.config['timeouts']['process_stop'])
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                self.capture_active = False

    def play(self, encoded, epoch=None, *, latency=None):
        policy=self.motion_policy.snapshot()
        policy_epoch=policy['epoch']
        if policy['quiet'] or policy['privacy_all']:return
        if not encoded or not self.microphone.enabled or (epoch is not None and epoch != self.microphone_epoch):
            return
        self.phase = 'speaking'
        wav = base64.b64decode(encoded, validate=True)
        with wave.open(io.BytesIO(wav), 'rb') as stream:
            seconds = stream.getnframes() / stream.getframerate()
        with subprocess.Popen(['aplay', '-q', '-D', self.audio['playback_device']],
                              stdin=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            self.playback_process = process
            try:
                if (not self.microphone.enabled or (epoch is not None and epoch != self.microphone_epoch)
                        or self.motion_policy.snapshot()['epoch']!=policy_epoch):
                    if latency is not None:latency.mark('cancel_observed')
                    measured(latency,'aplay_cancel',process.terminate)
                    return
                _, error = measured(latency,'aplay_communicate',process.communicate,wav,timeout=seconds + self.config['timeouts']['playback_margin'])
                if process.returncode and (epoch is None or epoch == self.microphone_epoch):
                    raise RuntimeError('Playback failed: ' + error.decode()[:500])
            finally:
                self.playback_process = None
                if process.poll() is None:
                    def cancel_play():
                        process.kill()
                        process.wait()
                    measured(latency,'aplay_cancel',cancel_play)
        time.sleep(self.audio['echo_tail_seconds'])

    def observe_normal_input(self, event, path, epoch, policy_epoch, source, before_playback):
        text=event.get('transcript');attempt=event.get('content_attempt_id')
        if (path not in ('/turn','/text') or not before_playback or self.last_input is not None
            or type(text) is not str or not 0<len(text)<=self.config['limits']['max_text_chars']
            or type(attempt) is not str or len(attempt)!=32 or any(c not in '0123456789abcdef' for c in attempt)):
            return
        self.last_input=dict(content_attempt_id=attempt,transcript_sha256=hashlib.sha256(text.encode()).hexdigest(),
            transcript_chars=len(text),agent_boot_id=self.agent_boot_id,microphone_epoch=epoch,policy_epoch=policy_epoch,
            source_generation=source.generation if source is not None else None,
            observed_before_playback=True,observed_monotonic=time.monotonic())

    def voice(self, path, payload, *args, **kwargs):
        bridge = getattr(self, 'sensory', None)
        with bridge.foreground_model() if bridge is not None else nullcontext():
            return self._measured_voice(path, payload, *args, **kwargs)

    def latency_status(self):
        if (self.config['logging'].get('latency_diagnostics',False) is not True
                or time.monotonic() >= getattr(self,'last_voice_latency_expires',0)):
            self.last_voice_latency=None
            return None
        value=getattr(self,'last_voice_latency',None)
        return json.loads(json.dumps(value)) if value is not None else None

    def _measured_voice(self, path, payload, expected_epoch=None, allow_barge_in=True, replay=None, **kwargs):
        if self.config['logging'].get('latency_diagnostics',False) is not True:
            return self._voice(path,payload,expected_epoch,allow_barge_in,replay,**kwargs)
        latency=TurnLatency(uuid4().hex,'agent','replay' if replay is not None else 'live')
        request=dict(payload,latency_diagnostics=True,latency_request_id=latency.request_id)
        response=None;worker=None;outcome='error'
        try:
            response=dict(self._voice(path,request,expected_epoch,allow_barge_in,replay,**kwargs,latency=latency))
            upstream=response.pop('latency',None)
            if replay is None:worker=checked_latency(upstream,latency.request_id)
            outcome='interrupted' if response.get('interrupted') else 'cancelled' if response.get('cancelled') else 'complete'
            return response
        finally:
            report=dict(request_id=latency.request_id,agent=latency.report(outcome),worker=worker)
            if response is not None:response['latency']=report
            self.last_voice_latency=json.loads(json.dumps(report))
            self.last_voice_latency_expires=time.monotonic()+300

    def _voice(self, path, payload, expected_epoch=None, allow_barge_in=True, replay=None, expected_policy_epoch=None, valid_until=None, initiative_generation=None, manual_authority=None, *, latency=None):
        epoch = self.microphone_epoch if expected_epoch is None else expected_epoch
        if path in ('/turn','/text') and replay is None:self.last_input=None
        motor_policy_epoch=(self.motion_policy.snapshot()['epoch'] if expected_policy_epoch is None else expected_policy_epoch)
        monitor = None
        pump_reply_seen = False
        capture_source = None
        premask_attempt = None
        premask_written = 0
        previous_capture_control = getattr(self, '_capture_control', None)
        if self._capture_enabled() and previous_capture_control is not None and previous_capture_control.thread.is_alive():
            raise RuntimeError('Previous capture control still active')
        timing = None
        self._stream_timing = None
        self.current_reply_text = (replay.get('spoken_text', '') if replay else
                                   self.current_reply_text[-self.config['limits']['max_speech_chars']:] if self._capture_enabled() else '')
        def cancelled():
            policy=self.motion_policy.snapshot()
            return ((manual_authority is not None and not manual_authority())
                    or (initiative_generation is not None and not self.initiative.valid(initiative_generation))
                    or not self.microphone.enabled or epoch != self.microphone_epoch or self.stopping.is_set()
                    or (capture_source is not None and not capture_source.permitted())
                    or policy['epoch']!=motor_policy_epoch or policy['quiet'] or policy['privacy_all']
                    or (valid_until is not None and time.monotonic()>=valid_until))
        def interrupted():
            return bool(monitor and monitor.interrupted.is_set())
        def cancelled_result():
            if latency is not None:latency.mark('cancel_observed')
            return {'ok': True, 'cancelled': True, 'interrupted': bool(monitor and monitor.interrupted.is_set())}
        if cancelled():
            return cancelled_result()
        mode=self.conversation_mode.snapshot()
        if mode['error']:raise RuntimeError('Conversation mode unavailable')
        payload=dict(payload,conversation_mode=mode['mode'],
                     speech_address_prefix='Алиса, ' if mode['mode']=='alice_test' else '')
        if replay is not None and replay.get('cursor_verified') is not True:
            self.resume_audio=None
            self.resume_blocked_reason='unverified_pcm_cursor'
            return {**cancelled_result(),'cancelled':True,'resume_blocked_reason':self.resume_blocked_reason}
        if replay is not None and replay.get('conversation_mode') != mode['mode']:
            self.resume_audio=None
            self.resume_blocked_reason='conversation_mode_changed'
            return {**cancelled_result(),'cancelled':True,'resume_blocked_reason':self.resume_blocked_reason}
        self.resume_blocked_reason=None
        if path in ('/text', '/turn'):
            # Take one real cache snapshot at dispatch, after foreground owns
            # the shared model slot. Never accept caller-supplied vision.
            payload.pop('visual_context', None)
            bridge = getattr(self, 'sensory', None)
            context = bridge.visual_context() if bridge is not None else None
            if context is not None:payload['visual_context'] = context
        if path in ('/text', '/turn'):
            self.expressions.set('processing')
        if not self.config['streaming']['enabled']:
            response = measured(latency,'worker_request',self.request,self.config['network']['voice_url'], path, payload)
            if cancelled():
                return cancelled_result()
            self.expressions.set('speaking', response.get('emotion', 'neutral'))
            try:
                self.play(response.get('audio_base64', ''), epoch,**({} if latency is None else dict(latency=latency)))
            finally:
                self.expressions.hold()
                if not cancelled():self.expressions.set('neutral')
            return response
        if path in ('/text','/turn') and replay is None:
            timing = self._stream_timing_begin(epoch,motor_policy_epoch)
        item = Request(self.config['network']['voice_url'] + '/stream' + path,
                       data=json.dumps(payload).encode(),
                       headers={'Content-Type': 'application/json',
                                'Authorization': 'Bearer ' + self.config.token})
        process = None
        complete = False
        result = None
        total = 0
        settings = self.config['streaming']
        maximum = settings['sample_rate'] * 2 * settings['max_output_seconds']
        deadline = None
        selector = None
        from .speech_clock import SpeechClock
        clock = SpeechClock(settings['sample_rate'], settings['playback_latency_seconds'])
        full_pcm = bytearray()
        all_cues = []
        cursor = None
        from .replay import ReplayResponse
        try:
            if (self._capture_enabled() and self.microphone.enabled and self.listening.is_set()
                    ):
                # Spoken visual child has returned before it calls voice('/say').
                self._capture_suspended = False
                capture_source = self._capture_get()
                # Independent experimental opt-in; ordinary A0 mask stays intact.
                if self._barge_candidate_enabled() and allow_barge_in and replay is None:
                    from .barge_candidate import BargeCandidate
                    monitor=BargeCandidate(self,capture_source)
                    capture_source.candidate=self._capture_control=monitor
                    monitor.thread.start()
            if cancelled():
                return cancelled_result()
            self._stream_timing_mark(timing,'response_open_begin')
            response_context = measured(latency,'worker_request',self.http.open,item,timeout=self.config['timeouts']['client']) if replay is None else ReplayResponse(replay, settings)
            self._stream_timing_mark(timing,'response_open_end')
            with response_context as response:
                self.voice_response = response
                if response.headers.get_content_type() != 'application/x-ndjson':
                    raise RuntimeError('Expected an audio event stream')
                while True:
                    if cancelled():
                        return cancelled_result()
                    line = response.readline(settings['max_event_bytes'] + 1)
                    if not line:
                        break
                    if len(line) > settings['max_event_bytes'] or not line.endswith(b'\n'):
                        raise ValueError('Invalid stream event size')
                    event = json.loads(line)
                    if cancelled():return cancelled_result()
                    if event['type'] == 'reply':
                        self.observe_normal_input(event,path,epoch,motor_policy_epoch,capture_source,process is None and total==0)
                        self._stream_timing_mark(timing,'first_reply_received')
                        self._stream_timing_bind(timing,event.get('content_attempt_id'))
                        premask_attempt = event.get('content_attempt_id')
                        result = event
                        spoken=event.get('spoken_text')
                        if type(spoken) is not str or not spoken.strip() or len(spoken)>self.config['limits']['max_speech_chars']:
                            spoken=event.get('reply','')
                        if self._capture_enabled() and not pump_reply_seen:
                            self.current_reply_text = ''
                            pump_reply_seen = True
                        self.current_reply_text += ' ' + spoken
                    elif event['type'] == 'motion':
                        if len(all_cues) + len(event['cues']) > self.config['conversation']['expressions']['speech_sync']['max_cues']:
                            raise ValueError('Too many speech motion cues')
                        all_cues.extend(event['cues'])
                        if not interrupted():
                            self.expressions.timeline(event['cues'], clock)
                            self._stream_timing_mark(timing,'first_motion_enqueued')
                    elif event['type'] == 'audio':
                        self._stream_timing_mark(timing,'first_audio_line_received')
                        if cancelled():
                            return cancelled_result()
                        if event.get('sample_rate') != settings['sample_rate'] or event.get('format') != 'S16_LE' or event.get('channels') != 1:
                            raise ValueError('Unsupported stream audio format')
                        pcm = base64.b64decode(event['pcm_base64'], validate=True)
                        total += len(pcm)
                        if len(pcm) % 2 or total > maximum:
                            raise ValueError('Invalid stream audio length')
                        full_pcm.extend(pcm)
                        if interrupted():
                            if cursor is None:
                                cursor = clock.resume_cursor()
                            continue
                        if process is None:
                            if all_cues:
                                self._stream_timing_mark(timing,'timeline_wait_begin')
                                self.expressions.wait_timeline(clock)
                                self._stream_timing_mark(timing,'timeline_wait_end')
                            if cancelled(): return cancelled_result()
                            self.phase = 'speaking'
                            if not all_cues:
                                self.expressions.set('speaking', (result or {}).get('emotion', 'neutral'))
                            self._stream_timing_mark(timing,'aplay_popen_begin')
                            if capture_source is not None:
                                capture_source.output(True)
                            process = subprocess.Popen(['aplay', '-q', '-D', self.audio['playback_device'],
                                '--buffer-time='+str(settings['playback_buffer_us']), '--period-time='+str(settings['playback_period_us']),
                                '-t', 'raw', '-f', 'S16_LE', '-r', str(settings['sample_rate']), '-c', '1'],
                                stdin=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                            self._stream_timing_mark(timing,'aplay_popen_end')
                            self.playback_process = process
                            if not self._capture_enabled() and allow_barge_in and self.microphone.enabled and self.config['conversation'].get('barge_in', {}).get('enabled', False):
                                from .barge_in import BargeInMonitor
                                monitor = BargeInMonitor(self)
                                monitor.start()
                                self._stream_timing_mark(timing,'monitor_start_return')
                            if cancelled():
                                return cancelled_result()
                            os.set_blocking(process.stdin.fileno(), False)
                            selector = selectors.DefaultSelector()
                            selector.register(process.stdin, selectors.EVENT_WRITE)
                            deadline = time.monotonic() + settings['max_output_seconds'] + self.config['timeouts']['playback_margin']
                        if latency is not None:latency.pcm(len(pcm))
                        remaining = memoryview(pcm)
                        while remaining:
                            if interrupted():
                                if cursor is None:
                                    cursor = clock.resume_cursor()
                                break
                            if cancelled():
                                return cancelled_result()
                            if time.monotonic() > deadline:
                                raise TimeoutError('Streaming playback stopped or timed out')
                            if process.poll() is not None:
                                raise RuntimeError('Streaming playback failed')
                            if selector.select(timeout=0.2):
                                try:
                                    written = os.write(process.stdin.fileno(), remaining)
                                    if latency is not None and written>0:
                                        latency.mark('first_write');latency.pcm(written,written=True)
                                    if written>0:
                                        self._stream_timing_mark(timing,'first_positive_write',written)
                                        if capture_source is not None and capture_source.candidate is not None:
                                            capture_source.candidate.written(bytes(remaining[:written]),process.pid,
                                                premask_attempt,premask_written,settings['sample_rate'])
                                            trial=getattr(self,'barge_trial',None)
                                            if trial is not None:trial.observe(capture_source.candidate)
                                        self._premask_written(capture_source, process, premask_attempt,
                                                              premask_written, written, settings['sample_rate'])
                                        premask_written += written
                                    clock.feed(written)
                                    remaining = remaining[written:]
                                except BrokenPipeError:
                                    if not interrupted():
                                        raise
                                except BlockingIOError:
                                    pass
                    elif event['type'] == 'done':
                        if latency is not None:latency.mark('stream_done')
                        if result is None or not event.get('ok'):
                            raise RuntimeError('Invalid stream completion')
                        result = event
                        complete = True
                        break
                    elif event['type'] == 'error':
                        raise RuntimeError('Compute worker failed during audio stream')
                    else:
                        raise ValueError('Unknown stream event')
                if not complete:
                    raise RuntimeError('Audio stream ended without completion')
            if process is not None:
                process.stdin.close()
                measured(latency,'aplay_wait',process.wait,timeout=max(1, deadline - time.monotonic()))
                if cancelled():
                    return cancelled_result()
                if process.returncode and not interrupted():
                    raise RuntimeError('Streaming playback failed')
                if not interrupted():
                    time.sleep(self.audio['echo_tail_seconds'])
            if interrupted():
                if cursor is None:
                    cursor = clock.resume_cursor()
                if cursor is None:
                    self.resume_audio=None
                    self.resume_blocked_reason='unverified_pcm_cursor'
                    return {**{key:value for key,value in result.items() if key!='type'},
                            **cancelled_result(),'resume_blocked_reason':self.resume_blocked_reason}
                self.resume_audio = {'pcm': bytes(full_pcm), 'cursor': min(cursor, len(full_pcm)),
                                     'cursor_verified': True,
                                     'conversation_mode': mode['mode'],
                                     'result': {key: value for key, value in result.items() if key not in ('type','latency')},
                                     'cues': all_cues, 'epoch': epoch, 'spoken_text': self.current_reply_text,
                                     'deadline': (self.last_voice_at or time.monotonic()) + self.config['conversation']['interaction']['resume_after_empty_seconds']}
                return {**self.resume_audio['result'], **cancelled_result()}
            self.resume_audio = None
            return {key: value for key, value in result.items() if key != 'type'}
        except Exception:
            if cancelled() or interrupted():
                self.resume_audio = None
                return cancelled_result()
            raise
        finally:
            self.voice_response = None
            if selector is not None:
                selector.close()
            if process is not None and process.poll() is None:
                def cancel_play():
                    process.terminate()
                    try:
                        process.wait(timeout=self.config['timeouts']['process_stop'])
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                measured(latency,'aplay_cancel',cancel_play)
            if process is not None:
                if not process.stdin.closed:
                    process.stdin.close()
                process.stderr.close()
            self.playback_process = None
            if capture_source is not None:
                trial=getattr(self,'barge_trial',None)
                if trial is not None:trial.observe(monitor)
                capture_source.output(False)
            try:
                if (epoch != self.microphone_epoch or not self.microphone.enabled
                        or (capture_source is not None and not capture_source.permitted())):
                    self.resume_audio = None
                if monitor is not None:
                    pcm = monitor.finish()
                    if pcm and self._capture_enabled():
                        with self.microphone_lock:
                            pump = getattr(self, '_capture_pump', None)
                            if pump is not None and epoch == self.microphone_epoch and pump.fresh(pcm):
                                self.pending_pcm = (epoch, pcm)
                    elif pcm:
                        self.pending_pcm = (epoch, pcm)
                    if self.resume_audio is not None:
                        self.resume_audio['deadline'] = (self.last_voice_at or time.monotonic()) + self.config['conversation']['interaction']['resume_after_empty_seconds']
            finally:
                self.expressions.hold()
                if not cancelled() and not interrupted():
                    self.expressions.set('neutral')

    def run(self):
        greeted = False
        while not self.stopping.is_set():
            if not self.listening.wait(timeout=1):
                if not self.audio_lock.locked():
                    self.phase = 'paused'
                    if self.microphone.enabled:
                        self.expressions.set('neutral')
                    else:
                        self.expressions.hold(maintenance=True)
                continue
            try:
                with self.audio_lock:
                    epoch = self.microphone_epoch
                    if not self.listening.is_set():
                        continue
                    health = self.request(self.config['network']['voice_url'], '/health', timeout=self.config['timeouts']['http'])
                    if not health.get('ok'):
                        raise RuntimeError('Voice server is not ready')
                    status = self.request(self.config['network']['hub_url'], '/status', timeout=self.config['timeouts']['http'])
                    if status['ownership']['state'] != 'free':
                        raise RuntimeError('Robot is controlled by another application')
                    if not self.listening.is_set() or epoch != self.microphone_epoch:
                        continue
                    self.last_error = None
                    if not self.playback_configured:
                        self.configure_playback()
                        self.playback_configured = True
                    if not greeted:
                        if self.config['conversation']['wake_on_start'] and self.motor_permitted():
                            self.request(self.config['network']['hub_url'], '/actions/wake', {}, timeout=self.config['timeouts']['wake'])
                        if self.config['conversation']['greet_on_start']:
                            self.voice('/say', {'text': self.config['conversation']['greeting']}, expected_epoch=epoch)
                        greeted = True
                    if not self.listening.is_set() or epoch != self.microphone_epoch:
                        continue
                    if self.barge_trial.consume():continue
                    interrupted_input = False
                    snapshot_turn = False
                    from .spoken_vision import binding
                    captured_operator = binding(self.operator_status())
                    pending, self.pending_pcm = self.pending_pcm, None
                    if pending is not None and pending[0] == epoch:
                        pcm = self._capture_pending(pending[1]) if self._capture_enabled() else pending[1]
                        interrupted_input = True
                    else:
                        from .barge_trial import EitherEvent
                        pcm = self.capture(stop_event=EitherEvent(self.initiative.wake,self.barge_trial.wake),
                            idle_deadline=self.initiative.idle_deadline())
                        if not pcm and self.barge_trial.consume():continue
                        if not pcm and self.initiative.maybe_run():continue
                    if pcm:
                        self.barge_trial.cancel()  # Real input wins over a queued diagnostic.
                        if hasattr(self,'sensory'):self._sensory_withdraw(preserve_visual=True)
                        self.initiative.input_activity()
                    if not pcm or not self.listening.is_set() or epoch != self.microphone_epoch:
                        continue
                    self._vision_route = (captured_operator, dict(
                        stt_nonempty=False, normalized_exact_visual=False, own_echo_match=False,
                        action_allowlisted=False, route_attempted=False,
                        stage='capture', result='pending', child_phase=None, child_error_class=None))
                    if interrupted_input:
                        self.vision_route_update(stage='interrupted', result='existing_interruption_path')
                    self.phase = 'processing'
                    LOG.info('phrase captured seconds=%.2f', len(pcm) / 32000)
                    if interrupted_input:
                        recognized = self.request(self.config['network']['voice_url'], '/transcribe',
                                                  {'pcm_base64': base64.b64encode(pcm).decode()})
                        if self._capture_enabled() and not self._capture_fresh():
                            continue
                        text = recognized['transcript']
                        if not text and self.resume_audio is not None:
                            saved = self.resume_audio
                            if saved.get('cursor_verified') is not True:
                                self.resume_audio=None
                                self.resume_blocked_reason='unverified_pcm_cursor'
                                continue
                            self.phase = 'waiting_to_resume'
                            if time.monotonic() < saved['deadline']:
                                more = self.capture(idle_deadline=saved['deadline'], skip_expression=True)
                                if more:
                                    self.pending_pcm = (epoch, more)
                                    continue
                            if self.sounds.music:
                                self.resume_audio = None
                                continue
                            if self.microphone.enabled and self.listening.is_set() and epoch == self.microphone_epoch:
                                LOG.info('empty_interruption_resume')
                                self.voice('/say', {}, expected_epoch=epoch, replay=saved)
                            continue
                        self.resume_audio = None
                        if not text:
                            continue
                        if recognized['decision']['action'] == 'stop':
                            self.last_transcript = text
                            LOG.info('spoken_stop')
                            self.set_microphone(False)
                            continue
                        response = self.voice('/text', {'text': text, 'session': self.config['conversation']['session'],
                                                       'previous_reply_interrupted': True}, expected_epoch=epoch)
                        response['transcript'] = text
                    else:
                        from .spoken_vision import matches, dispatch
                        self.vision_route_update(stage='stt', result='pending')
                        recognized = self.request(self.config['network']['voice_url'], '/transcribe',
                                                  {'pcm_base64': base64.b64encode(pcm).decode()})
                        if self._capture_enabled() and not self._capture_fresh():
                            continue
                        text = recognized['transcript']
                        if (recognized.get('ok') is not True or type(text) is not str
                                or len(text) > self.config['limits']['max_text_chars']):
                            raise ValueError('Invalid transcription result')
                        if not self.listening.is_set() or epoch != self.microphone_epoch:
                            continue
                        exact_visual = matches(text)
                        visual_allowed = matches(text, self.current_reply_text)
                        self.vision_route_update(stt_nonempty=bool(text),
                            normalized_exact_visual=exact_visual,
                            own_echo_match=exact_visual and not visual_allowed,
                            stage='action', result='pending')
                        action = recognized['decision']['action']
                        self.vision_route_update(action_allowlisted=action in ('answer', 'stop', 'pause', 'reset'),
                            stage='route', result=('action_rejected' if action != 'answer' else
                                'empty_stt' if not text else 'nonmatching_stt' if not exact_visual else
                                'echo_rejected' if not visual_allowed else 'eligible'))
                        if action in ('stop', 'pause'):
                            response = {'transcript': text, 'command': action}
                        elif action == 'reset':
                            self.resume_audio = None
                            self.request(self.config['network']['voice_url'], '/reset',
                                         {'session': self.config['conversation']['session']})
                            response = self.voice('/say', {'text': self.config['conversation']['reset_reply'],
                                                          'session': self.config['conversation']['session']}, expected_epoch=epoch)
                            response['transcript'] = text
                        elif action == 'answer' and visual_allowed:
                            snapshot_turn = True
                            self.vision_route_update(route_attempted=True, stage='dispatch', result='pending')
                            try:
                                response = self._capture_visual(dispatch, text, epoch, captured_operator)
                            except Exception as exc:
                                self.vision_route_failure(exc)
                                raise
                            self.vision_route_update(stage='dispatch', result='returned')
                        elif text:
                            response = self.voice('/text', {'text': text,
                                                           'session': self.config['conversation']['session'],
                                                           'previous_reply_interrupted': False}, expected_epoch=epoch)
                            response['transcript'] = text
                        else:
                            continue
                    if self._capture_enabled() and (response.get('cancelled')
                            or not self.microphone.enabled or not self.listening.is_set()
                            or epoch != self.microphone_epoch or self.stopping.is_set()
                            or captured_operator['policy_epoch'] != self.motion_policy.snapshot()['epoch']):
                        continue
                    self.last_transcript = response.get('transcript', '')
                    if self.last_transcript:
                        self.turns += 1
                        if self.config['logging']['log_transcripts'] and not snapshot_turn:
                            LOG.info('turn transcript=%r reply=%r', self.last_transcript, response.get('reply'))
                    if response.get('command') == 'stop':
                        self.resume_audio = None
                    if response.get('command') in ('pause', 'stop'):
                        self.set_microphone(False)
                    self.last_error = None
            except Exception as exc:
                try:
                    self.durable_intent.audio_error(self,'audio_loop_error')
                except Exception:
                    LOG.exception('schedule_cleanup_failed')
                self.last_error = str(exc)
                self.phase = 'error'
                LOG.exception('conversation_error')
                self.stopping.wait(self.config['conversation']['retry_seconds'])
        pump = self._capture_retire() if self._capture_enabled() else None
        if pump is not None:
            pump.close()
        self.phase = 'stopped'

    def set_listening(self, enabled, payload, *, require_paused=False, durable=False, manual_admission=None):
        """Bind automated pause/resume to existing authority at event mutation."""
        if type(enabled) is not bool or type(payload) is not dict:
            raise ValueError('Listening control object required')
        binding = None
        if payload:
            if set(payload) != {'operator_binding'} or type(payload['operator_binding']) is not dict:
                raise ValueError('Exact listening operator binding required')
            binding = dict(payload['operator_binding'])
            if (set(binding) != {'agent_boot_id', 'microphone_epoch', 'policy_epoch', 'owner_id', 'expires_at_monotonic'}
                    or type(binding['agent_boot_id']) is not str or not 1 <= len(binding['agent_boot_id']) <= 256
                    or (binding['owner_id'] is not None and (type(binding['owner_id']) is not str or not 1 <= len(binding['owner_id']) <= 128))
                    or any(type(binding[k]) is not int or not 0 <= binding[k] < 2**63 for k in ('microphone_epoch', 'policy_epoch'))
                    or type(binding['expires_at_monotonic']) not in (int, float)
                    or not 0 <= binding['expires_at_monotonic'] <= 1e15
                    or not math.isfinite(binding['expires_at_monotonic'])):
                raise ValueError('Exact listening operator binding required')
        # Same lock order as operator snapshots. Check and mutate atomically
        # with microphone OFF/new owner and MotionPolicy.save, without I/O.
        retired_capture = None
        withdrawn_initiative = False
        with self.microphone_lock, self.motion_policy.lock, (self.durable_intent.lock if manual_admission is not None else nullcontext()):
            if manual_admission is not None:manual_admission()
            if binding is not None:
                policy = self.motion_policy.snapshot()
                if (self.agent_boot_id != binding['agent_boot_id']
                        or self.microphone_epoch != binding['microphone_epoch']
                        or policy['epoch'] != binding['policy_epoch']
                        or self.microphone_owner_id != binding['owner_id']
                        or self.motion_policy.owner_id != binding['owner_id']
                        or not self.microphone.enabled or self.microphone.error is not None
                        or policy['motor_enabled'] is not True or policy['quiet'] is not False
                        or policy['privacy_all'] is not False or self.stopping.is_set()
                        or not 0 < binding['expires_at_monotonic'] - time.monotonic() <= 60
                        or ((enabled or require_paused) and (self.phase != 'paused' or self.capture_active))
                        or (require_paused and self.listening.is_set())):
                    raise RuntimeError('Listening operator or snapshot changed')
            if enabled:
                if not self.microphone.enabled:
                    raise RuntimeError('Microphone is muted; enable it with the microphone switch')
                if durable:
                    policy=self.motion_policy.snapshot()
                    if self.microphone_owner_id is not None or self.motion_policy.owner_id is not None or policy['quiet'] or policy['privacy_all'] or self.microphone.error is not None:
                        raise RuntimeError('Unowned safe listening intent required')
                    self.durable_update(listening=True)
                if hasattr(self,'initiative'):
                    withdrawn_initiative = self.initiative.cancel(stop_audio=False)
                self.listening.set()
            else:
                if hasattr(self,'sensory'):self._sensory_withdraw()
                if durable:self.durable_update(listening=False,automatic=False)
                if hasattr(self,'initiative'):
                    withdrawn_initiative = self.initiative.cancel(stop_audio=False)
                self.listening.clear()
                retired_capture = getattr(self, '_capture_pump', None)
                if retired_capture is not None:
                    # Only set the Event while holding policy.lock: the reader
                    # may hold its condition while taking a policy snapshot.
                    retired_capture.retired.set()
                    self._capture_packet = self.pending_pcm = None
            result = {'ok': True, 'listening': enabled}
        if withdrawn_initiative or (durable and not enabled):self.stop_speaker()
        if retired_capture is not None:
            retired_capture.close()
        return result

    @staticmethod
    def panel_binding(binding):
        keys={'agent_boot_id','microphone_epoch','policy_epoch','intent_generation','schedule_generation','owner_id'}
        if (type(binding) is not dict or set(binding)!=keys or type(binding['agent_boot_id']) is not str
            or not 1<=len(binding['agent_boot_id'])<=256 or binding['owner_id'] is not None
            or any(type(binding[k]) is not int or not 0<=binding[k]<2**63 for k in keys-{'agent_boot_id','owner_id'})):
            raise ValueError('Exact panel binding required')
        return dict(binding)

    def panel_state(self):
        with self.microphone_lock,self.motion_policy.lock,self.initiative.lock,self.durable_intent.lock:
            policy=self.motion_policy.snapshot();intent=self.durable_intent.snapshot();i=self.initiative
            pump=getattr(self,'_capture_pump',None);thread=getattr(pump,'thread',None);process=getattr(pump,'process',None)
            reader=bool(thread is not None and thread.is_alive());alive=bool(process is not None and process.poll() is None)
            closed=(not self.microphone.enabled and not self.listening.is_set() and not self.capture_active and not reader and process is None)
            now=time.monotonic()
            state=('OFF' if not i.schedule_enabled else 'RUNNING' if i.state=='running' else 'COOLDOWN' if now<i.schedule_next_due else 'WAITING_FOR_IDLE')
            return dict(version=1,binding=dict(agent_boot_id=self.agent_boot_id,microphone_epoch=self.microphone_epoch,policy_epoch=policy['epoch'],intent_generation=intent['generation'],schedule_generation=i.schedule_generation,owner_id=None),
                microphone=dict(enabled=self.microphone.enabled,listening=self.listening.is_set(),capture_active=self.capture_active,reader_alive=reader,process_alive=alive,error=bool(self.microphone.error),closed=closed),
                automatic=dict(enabled=i.schedule_enabled,state=state,requested=intent['automatic_questions_requested'],interval_seconds=300,generation=i.schedule_generation),
                policy=dict(policy,microphone_owner_id=self.microphone_owner_id,motion_policy_owner_id=self.motion_policy.owner_id),
                volume=dict(percent=self.volume.percent,enabled=self.audio.get('playback_mixer',{}).get('enabled',False)),
                conversation_mode=self.conversation_mode.snapshot(),
                capabilities=dict(microphone=True,automatic=True,stop=True,camera_control=False,motion_off=True,conversation_mode=True),phase=self.phase)

    def panel_match(self,binding):
        # Called by the existing MIC mutation under MIC/policy/initiative/intent locks.
        p=self.motion_policy.snapshot();v=self.durable_intent.snapshot()
        generation=self.initiative.schedule_generation
        if (self.agent_boot_id!=binding['agent_boot_id'] or self.microphone_epoch!=binding['microphone_epoch']
            or p['epoch']!=binding['policy_epoch'] or v['generation']!=binding['intent_generation'] or generation!=binding['schedule_generation']
            or self.microphone_owner_id is not None or self.motion_policy.owner_id is not None
            or p['quiet'] or p['privacy_all'] or self.microphone.error is not None or self.durable_intent.error or self.stopping.is_set()):
            raise RuntimeError('Panel authority unavailable or changed')

    def panel_control(self,payload):
        if type(payload) is not dict or type(payload.get('action')) is not str:raise ValueError('Panel action required')
        action=payload['action'];positive=action in ('microphone_on','automatic_on')
        mode_action=action in ('mode_normal','mode_alice_test')
        if action not in ('microphone_on','microphone_off','automatic_on','automatic_off','stop','mode_normal','mode_alice_test'):raise ValueError('Panel action unavailable')
        fields={'action','binding','mode_generation'} if mode_action else {'action','binding'} if positive else {'action'}
        if set(payload)!=fields:raise ValueError('Exact panel action fields required')
        if positive or mode_action:binding=self.panel_binding(payload['binding'])
        motion_withdrawn=None
        if mode_action:
            with self.microphone_lock,self.motion_policy.lock,self.initiative.lock,self.durable_intent.lock:
                self.panel_match(binding)
                self.conversation_mode.save(action.removeprefix('mode_'),payload['mode_generation'])
                if hasattr(self,'sensory'):self._sensory_withdraw()
        elif action=='microphone_on':
            self.set_microphone(True,listen=True,expected_boot_id=binding['agent_boot_id'],expected_epoch=binding['microphone_epoch'],admission=lambda:self.panel_match(binding))
        elif action=='automatic_on':
            self.initiative.schedule_control(dict(enabled=True,expected_generation=binding['schedule_generation'],operator_binding=dict(agent_boot_id=binding['agent_boot_id'],microphone_epoch=binding['microphone_epoch'],policy_epoch=binding['policy_epoch'],owner_id=None,expires_at_monotonic=time.monotonic()+59)),panel_intent_generation=binding['intent_generation'])
        elif action=='automatic_off':
            i=self.initiative
            with self.microphone_lock,self.motion_policy.lock,i.lock,self.durable_intent.lock:
                was_enabled=i.schedule_enabled
                self.durable_update(automatic=False)
                running=i._cancel_locked('explicit_off')
                if not was_enabled:i.schedule_generation+=1
            i.wake.set()
            if running:self.stop_speaker()
        else:
            self.set_microphone(False,listen=False,preserve_owner=True)
            if action=='stop':
                p=self.motion_policy.snapshot();owner=self.motion_policy.owner_id
                value=dict(motor_enabled=False,quiet=p['quiet'],privacy_all=p['privacy_all'],expected_boot_id=self.agent_boot_id,expected_epoch=p['epoch'])
                if owner is not None:value.update(owner_id=owner,expected_owner_id=owner)
                try:motion_withdrawn=self.set_motion_policy(value)['motor_enabled'] is False
                except (ValueError,RuntimeError,OSError):motion_withdrawn=False
        return dict(accepted=True,action=action,state=self.panel_state(),scope=['conversation_mode'] if mode_action else ['questions'] if action.startswith('automatic_') else ['audio','questions'],motion_permission_withdrawn=motion_withdrawn,camera_controlled=False)

    def manual(self, path, payload):
        binding = payload.get('operator_binding')
        voice_binding=payload.get('voice_operator_binding')
        if 'voice_operator_binding' in payload:
            if (path!='/say' or set(payload)!={'text','voice_operator_binding'} or type(voice_binding) is not dict
                or set(voice_binding)!={'agent_boot_id','microphone_epoch','policy_epoch','owner_id','expires_at_monotonic','intent_generation'}
                or type(voice_binding['agent_boot_id']) is not str or not 1<=len(voice_binding['agent_boot_id'])<=256
                or voice_binding['owner_id'] is not None
                or any(type(voice_binding[k]) is not int or not 0<=voice_binding[k]<2**63 for k in ('microphone_epoch','policy_epoch','intent_generation'))
                or type(voice_binding['expires_at_monotonic']) not in (int,float) or not math.isfinite(voice_binding['expires_at_monotonic'])):
                raise ValueError('Exact fresh voice-only binding required')
        stamp=None
        was_listening=False
        def capture_voice_authority():
            nonlocal stamp,was_listening
            policy=self.motion_policy.snapshot();intent=self.durable_intent.snapshot()
            if voice_binding is not None:
                if (self.agent_boot_id!=voice_binding['agent_boot_id'] or self.microphone_epoch!=voice_binding['microphone_epoch']
                    or policy['epoch']!=voice_binding['policy_epoch'] or intent['generation']!=voice_binding['intent_generation']
                    or self.microphone_owner_id is not None or self.motion_policy.owner_id is not None
                    or not self.microphone.enabled or self.microphone.error is not None or not self.listening.is_set()
                    or not self.capture_active or self.phase!='listening' or self.pending_pcm is not None or self.resume_audio is not None
                    or self.playback_process is not None or self.voice_response is not None
                    or policy['quiet'] or policy['privacy_all'] or self.durable_intent.error or not intent['listening_requested']
                    or self.stopping.is_set() or not 0<voice_binding['expires_at_monotonic']-time.monotonic()<=60):
                    raise RuntimeError('Voice-only authority changed')
            was_listening=self.listening.is_set()
            stamp=(self.agent_boot_id,self.microphone_epoch,dict(policy),self.microphone_owner_id,self.motion_policy.owner_id,intent['generation'],intent['listening_requested'])
        def voice_authorized():
            try:
                with self.microphone_lock,self.motion_policy.lock,self.durable_intent.lock:
                    intent=self.durable_intent.snapshot();policy=self.motion_policy.snapshot()
                    return (stamp is not None and self.agent_boot_id==stamp[0] and self.microphone_epoch==stamp[1]
                        and policy==stamp[2] and self.microphone_owner_id==stamp[3] and self.motion_policy.owner_id==stamp[4]
                        and intent['generation']==stamp[5] and intent['listening_requested']==stamp[6]
                        and not self.durable_intent.error and self.microphone.enabled and self.microphone.error is None
                        and not self.stopping.is_set() and not policy['quiet'] and not policy['privacy_all']
                        and (voice_binding is None or 0<voice_binding['expires_at_monotonic']-time.monotonic()<=60))
            except Exception:return False

        if 'operator_binding' in payload:
            if (path != '/say' or set(payload) != {'text', 'operator_binding'} or type(binding) is not dict
                    or set(binding) != {'agent_boot_id', 'microphone_epoch', 'policy_epoch', 'owner_id', 'expires_at_monotonic'}
                    or type(binding['agent_boot_id']) is not str or not 1 <= len(binding['agent_boot_id']) <= 256
                    or (binding['owner_id'] is not None and (type(binding['owner_id']) is not str or not 1 <= len(binding['owner_id']) <= 128))
                    or any(type(binding[k]) is not int or not 0 <= binding[k] < 2**63 for k in ('microphone_epoch', 'policy_epoch'))
                    or type(binding['expires_at_monotonic']) not in (int, float)
                    or not math.isfinite(binding['expires_at_monotonic'])):
                raise ValueError('Exact bounded speech operator binding required')
        def same_owner():
            value = self.operator_status()
            return (value['agent_boot_id'] == binding['agent_boot_id']
                and value['microphone_epoch'] == binding['microphone_epoch']
                and value['motion_policy']['epoch'] == binding['policy_epoch']
                and value['microphone_owner_id'] == binding['owner_id']
                and value['motion_policy_owner_id'] == binding['owner_id']
                and value['microphone_enabled'] and not value['capture_active'] and not value['listening']
                and value['phase'] == 'paused' and value['motion_policy']['motor_enabled']
                and not value['motion_policy']['quiet'] and not value['motion_policy']['privacy_all']
                and 0 < binding['expires_at_monotonic'] - time.monotonic() <= 60)
        if binding is not None and not same_owner():
            raise RuntimeError('Speech operator or snapshot changed')
        if binding is not None:
            was_listening = False
            self.set_listening(False, {'operator_binding': binding}, require_paused=True)
        else:
            self.set_listening(False, {}, manual_admission=capture_voice_authority)
        def restore_listening():
            if was_listening:
                with self.microphone_lock,self.motion_policy.lock,self.durable_intent.lock:
                    policy=self.motion_policy.snapshot();intent=self.durable_intent.snapshot()
                    if (stamp is not None and self.agent_boot_id==stamp[0] and self.microphone_epoch==stamp[1]
                        and policy==stamp[2] and self.microphone_owner_id==stamp[3] and self.motion_policy.owner_id==stamp[4]
                        and intent['generation']==stamp[5] and intent['listening_requested'] and not self.durable_intent.error
                        and self.microphone.enabled and self.microphone.error is None and not self.stopping.is_set()
                        and not policy['quiet'] and not policy['privacy_all']):self.listening.set()
        acquired = self.audio_lock.acquire(timeout=self.config['timeouts']['manual_audio_lock'])
        if not acquired:
            restore_listening()
            raise RuntimeError('Robot is processing a voice turn; try again when idle')
        try:
            options = dict(allow_barge_in=was_listening)
            if binding is None:
                if not voice_authorized():raise RuntimeError('Manual voice authority withdrawn before output')
                options.update(expected_epoch=stamp[1],expected_policy_epoch=stamp[2]['epoch'],manual_authority=voice_authorized)
                if voice_binding is not None:options['valid_until']=voice_binding['expires_at_monotonic']
            if binding is not None:
                if not same_owner():raise RuntimeError('Speech operator or snapshot changed')
                options.update(expected_epoch=binding['microphone_epoch'], expected_policy_epoch=binding['policy_epoch'],
                               valid_until=binding['expires_at_monotonic'])
            response = self.voice('/text' if path == '/ask' else '/say',
                                    {'text': payload['text'], 'session': self.config['conversation']['session']}, **options)
            result={k:v for k,v in response.items() if k!='audio_base64'}
            if voice_binding is not None:
                completed=(response.get('ok') is True and not response.get('cancelled') and not response.get('interrupted')
                    and self.playback_process is None and self.voice_response is None and voice_authorized())
                result['voice_control_receipt']=dict(agent_boot_id=stamp[0],microphone_epoch=stamp[1],policy_epoch=stamp[2]['epoch'],intent_generation=stamp[5],
                    playback_completed=bool(completed),playback_reaped_monotonic=time.monotonic() if completed else None)
            return result
        finally:
            self.phase = 'paused'
            self.audio_lock.release()
            restore_listening()


def main(config, test_speaker=False):
    logging.basicConfig(level=config['logging']['level'], format='%(asctime)s %(levelname)s %(message)s')
    agent = Agent(config)
    try:
        agent.configure_playback()
        agent.playback_configured = True
    except Exception:
        LOG.exception('initial_playback_configuration_failed')
    if test_speaker:
        response = agent.request(config['network']['voice_url'], '/text',
                                 {'text': 'Поздоровайся и скажи, что разговор через локальную модель работает.',
                                  'session': 'setup-test'})
        agent.play(response['audio_base64'])
        print(json.dumps({k: v for k, v in response.items() if k != 'audio_base64'}, ensure_ascii=False))
        return

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, value):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def auth(self):
            if not hmac.compare_digest(self.headers.get('Authorization', '').encode(),
                                       ('Bearer ' + config.token).encode()):
                self.reply(401, {'error': 'Bearer token required'})
                return False
            return True

        def do_GET(self):
            if not self.auth():
                return
            if self.path == '/initiative/schedule':
                self.reply(200,agent.initiative.schedule_status())
                return
            if self.path == '/initiative':
                if agent.initiative.status()['state'] not in ('armed','running'):
                    self.reply(200,{'initiative':agent.initiative.status()})
                    return
                try:self.reply(200,agent.initiative.inspect())
                except Exception:self.reply(409,{'error':'Initiative unavailable','initiative':agent.initiative.status()})
                return
            if self.path == '/diagnostics/premask':
                self.reply(200, agent.premask_status())
                return
            if self.path == '/vision-capabilities':
                self.reply(200, {'bound_snapshot_say':1,'agent_boot_id':agent.agent_boot_id})
                return
            if self.path=='/panel-state':
                self.reply(200,agent.panel_state());return
            if self.path not in ('/status','/operator'):
                self.reply(404, {'error': 'Not found'})
                return
            self.reply(200, agent.operator_status() if self.path=='/operator' else agent.status())

        def do_POST(self):
            if not self.auth():
                return
            if self.path == '/actors/motion/native':
                self.close_connection = True
                try:
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<=4096: raise ValueError('Native request size')
                    from .autonomous.contracts import decode
                    value=agent.motion_proxy.handle(decode(self.rfile.read(size)))
                    self.reply(200 if value.get('accepted') is True else 409,value)
                except Exception as exc:
                    self.reply(409, {'accepted':False,'error':type(exc).__name__})
                return
            try:
                if self.path=='/panel-control':
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<=4096:raise ValueError('Panel request bound')
                    from .autonomous.contracts import decode
                    value=agent.panel_control(decode(self.rfile.read(size)))
                elif self.path == '/diagnostics/barge-trial':
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<=4096:raise ValueError('Trial request bound')
                    from .autonomous.contracts import decode
                    value=agent.barge_trial.submit(decode(self.rfile.read(size)))
                elif self.path == '/diagnostics/premask':
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= 4096: raise ValueError('Diagnostic request bound')
                    from .autonomous.contracts import decode
                    value = agent.set_premask(decode(self.rfile.read(size)))
                elif self.path == '/initiative/schedule':
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<=4096:raise ValueError('Schedule request bound')
                    from .autonomous.contracts import decode
                    value=agent.initiative.schedule_control(decode(self.rfile.read(size)))
                elif self.path == '/initiative':
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<=4096:raise ValueError('Initiative request bound')
                    from .autonomous.contracts import decode
                    value=agent.initiative.arm(decode(self.rfile.read(size)))
                elif self.path in ('/pause', '/resume'):
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 <= size <= 4096:
                        raise ValueError('Listening request bound')
                    from .autonomous.contracts import decode
                    payload = decode(self.rfile.read(size)) if size else {}
                    value = agent.set_listening(self.path == '/resume', payload, durable=True)
                elif self.path == '/volume':
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= config['limits']['max_agent_request_bytes']:
                        raise ValueError('Invalid request size')
                    value = agent.set_volume(json.loads(self.rfile.read(size))['volume_percent'])
                elif self.path == '/motion-policy':
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<=4096:raise ValueError('Policy request bound')
                    from .autonomous.contracts import decode
                    value=agent.set_motion_policy(decode(self.rfile.read(size)))
                elif self.path == '/microphone':
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= config['limits']['max_agent_request_bytes']:
                        raise ValueError('Invalid request size')
                    payload=json.loads(self.rfile.read(size))
                    if not isinstance(payload,dict):raise ValueError('Microphone control fields')
                    fields=set(payload)
                    authority={'expected_boot_id','expected_epoch'}
                    if fields & authority and not authority<=fields:raise ValueError('Complete microphone authority required')
                    if fields & authority and (not isinstance(payload['expected_boot_id'],str) or not payload['expected_boot_id'] or type(payload['expected_epoch']) is not int):
                        raise ValueError('Complete microphone authority required')
                    owners={'owner_id','expected_owner_id'}
                    if fields & owners and (not authority<=fields or any(not isinstance(payload[key],str) or not 1<=len(payload[key])<=128 for key in fields & owners)):
                        raise ValueError('Bounded microphone owner requires authority')
                    if fields-authority-owners not in ({'enabled'},{'enabled','listen'}):raise ValueError('Microphone control fields')
                    value = agent.set_microphone(payload['enabled'],payload.get('listen',True),
                        expected_boot_id=payload.get('expected_boot_id'),expected_epoch=payload.get('expected_epoch'),
                        owner_id=payload.get('owner_id'),expected_owner_id=payload.get('expected_owner_id'))
                elif self.path in ('/ask', '/say'):
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= config['limits']['max_agent_request_bytes']:
                        raise ValueError('Invalid request size')
                    value = agent.manual(self.path, json.loads(self.rfile.read(size)))
                else:
                    self.reply(404, {'error': 'Not found'})
                    return
                self.reply(200, value)
            except Exception as exc:
                LOG.exception('control_failed')
                self.reply(409, {'error': str(exc)})

        def log_message(self, fmt, *args):
            LOG.info('http %s', fmt % args)

    server = ThreadingHTTPServer((config['servers']['agent']['listen'], config['servers']['agent']['port']), Handler)
    server.daemon_threads = True
    threading.Thread(target=agent.run, daemon=True).start()

    def stop(signum, frame):
        agent.listening.clear()
        agent.stopping.set()
        if hasattr(agent,'sensory'):agent._sensory_withdraw()
        agent._premask_off('shutdown')
        # Exit from the main signal handler; systemd kills any remaining children.
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.serve_forever()
