"""Inference-free hub scheduler. One actual request per available clock tick."""
from concurrent.futures import Future
import json
import os
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler
from .contracts import decode, uid, validator
from .state import State


class Job:
    """A daemon transport job; deadline expiry never implies execution completion."""
    def __init__(self, function, *args):
        self.future = Future()
        def work():
            try:
                self.future.set_result(function(*args))
            except BaseException as exc:
                self.future.set_exception(exc)
        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()


class RemoteGateway:
    def __init__(self, config):
        self.config = config
        self.url = config['gateway']['client_url']
        if not self.url:
            raise ValueError('Set separate PC gateway client_url')
        self.token = os.environ.get(config['gateway']['token_env'], '')
        if len(self.token) < 32:
            raise ValueError('Set gateway token environment variable')
        self.opener = build_opener(ProxyHandler({}))
        self.boot_id = self.call('/health')['compute_boot_id']

    def call(self, path, payload=None):
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}
        request = Request(self.url.rstrip('/') + path,
                          data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        with self.opener.open(request, timeout=self.config['http_timeout_s'] + 1) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError('Oversized gateway response')
        return decode(raw)

    def fast(self, request_id, view):
        result = self.call('/decision', dict(request_id=request_id, data=view))
        if result['request_id'] != request_id:
            raise ValueError('request identity mismatch')
        return result

    def main(self, task):
        if task.kind == 'research':
            from .workflows import WorkflowClient
            output = WorkflowClient(self.config['workflows']).run(task)
            return dict(output=output,compute_boot_id=task.authority.compute_boot_id,request_id=task.attempt_id)
        result = self.call('/main', dict(request_id=task.attempt_id, data=task.prompt))
        if result['request_id'] != task.attempt_id:
            raise ValueError('attempt identity mismatch')
        return result

    def context(self,request_id,query,privacy_all,authority):
        return self.call('/context',dict(request_id=request_id,data=dict(query=query,privacy_all=privacy_all,
                        hub_boot_id=authority.hub_boot_id,operator_epoch=authority.operator_epoch)))


class ReplayGateway:
    """Explicit deterministic fixture backend; never represented as model inference."""
    boot_id = 'replay-compute'
    def __init__(self, main_delay=0.1):
        self.main_delay = main_delay
        self.fast_calls = 0
    def fast(self, request_id, view):
        self.fast_calls += 1
        choice = dict(a='wait', why='Replay: no new task')
        if view['op']['microphone_enabled']:
            if view['ready']:
                choice = dict(a='converse', why='Replay: accept ready proposal', commit=view['ready'][0]['alias'])
            elif view['candidates']:
                choice = dict(a='think', why='Replay: start background task',
                              start=dict(type=view['candidates'][0]['kind'], input_ref=view['candidates'][0]['alias']))
        return dict(output=choice, compute_boot_id=self.boot_id, request_id=request_id)
    def main(self, task):
        time.sleep(self.main_delay)
        return dict(output=task.prompt if task.kind == 'research' else 'Replay fixture response.', compute_boot_id=self.boot_id, request_id=task.attempt_id)


class Scheduler:
    def __init__(self, config, gateway, motion_adapter=None, speech_adapter=None):
        # Compile/import schema machinery before admitting clock ticks.
        for name in ('FastView','FastChoice','MemoryItem'):validator(name)
        self.config, self.gateway = config, gateway
        self.state = State(gateway.boot_id, config)
        self.motion_adapter=motion_adapter
        self.speech_adapter=speech_adapter;self.state.speech_attached=speech_adapter is not None
        self.actor_job=self.motion_job=None;self.next_actor=0
        if motion_adapter:
            self.state.muted=True
            motion_adapter.hub.boot_id=self.state.authority.hub_boot_id
        self.fast_job = self.main_job = None
        self.binding = self.main_task = None
        self.next_tick = 0
        self.expiry_logged = False
        self.context_job=None
        self.context_binding=None
        self.next_context=0
        self.closed=False

    def ingest(self, event, now=None):
        if self.closed:return
        if self.speech_adapter and event.get('type') in ('operator','utterance'):
            self.speech_adapter.interrupt('human_utterance' if event['type']=='utterance' else 'operator',False)
        self.state.ingest(event, time.monotonic() if now is None else now)

    def speech_activity(self,origin):
        # Trusted classifier hook; echo cannot create a State human utterance.
        if origin not in ('human_activity','echo'):raise ValueError('Speech provenance')
        if self.speech_adapter:return self.speech_adapter.interrupt(origin)

    def confirm_no_user_utterance(self,since,until):
        return bool(self.speech_adapter and self.speech_adapter.confirm_no_utterance(since=since,until=until))

    def handshake_compute(self, boot, generation):
        """Single-owner authenticated health/reconnect callback, never a model result."""
        return self.state.set_compute_boot(boot, generation)

    def advance(self, now=None):
        if self.closed:return
        now = time.monotonic() if now is None else now
        if self.speech_adapter:
            receipt=self.speech_adapter.operator_view()
            if receipt:self.state.set_speech_operator(receipt)
        if self.motion_adapter:
            if self.actor_job and self.actor_job.future.done():
                try:self.state.set_actor(self.actor_job.future.result())
                except Exception:
                    self.state.motion_allowed=False;self.state.record('actor_authority_unavailable')
                self.actor_job=None
            if not self.actor_job and now>=self.next_actor:
                self.actor_job=Job(self.motion_adapter.refresh);self.next_actor=now+.1
            if self.motion_job and self.motion_job.future.done():
                try:
                    report=self.motion_job.future.result()
                    self.state.record('motion_completed' if report['accepted'] else 'motion_failed',request_id=report['request_id'])
                except Exception:self.state.record('motion_failed')
                self.motion_job=None
        if self.config.get('context',{}).get('enabled') and hasattr(self.gateway,'context'):
            if self.context_job and self.context_job.future.done():
                request_id,authority,started=self.context_binding
                try:
                    result=self.context_job.future.result()
                    if result['request_id']!=request_id or result['compute_boot_id']!=authority.compute_boot_id or authority!=self.state.authority:
                        raise ValueError('Stale context authority')
                    self.state.update_context(result['output'],now,now-started)
                except Exception:self.state.record('context_failed')
                self.context_job=self.context_binding=None
            if not self.context_job and now>=self.next_context:
                request_id=uid();self.context_binding=(request_id,self.state.authority,now)
                self.context_job=Job(self.gateway.context,request_id,self.state.current_utterance,self.state.privacy,self.state.authority)
                self.next_context=now+self.config['context'].get('refresh_s',.5)
        # Poll done futures without waiting; worker threads never mutate hub state.
        if self.main_job and self.main_job.future.done():
            task = self.main_task
            try:
                result = self.main_job.future.result()
                if result['compute_boot_id'] != task.authority.compute_boot_id or result['request_id'] != task.attempt_id:
                    self.state.complete(task.task_id, task.attempt_id, task.authority, None, now, error=True)
                else:
                    self.state.complete(task.task_id, task.attempt_id, task.authority, result['output'], now)
            except Exception:
                self.state.complete(task.task_id, task.attempt_id, task.authority, None, now, error=True)
            self.main_job = self.main_task = None
        if self.fast_job and self.fast_job.future.done():
            try:
                result = self.fast_job.future.result()
                if (result['compute_boot_id'] != self.binding.authority.compute_boot_id
                        or result['request_id'] != self.binding.request_id):
                    raise ValueError('Completion does not match request authority')
                choice = result['output']
                # Capacity rejection before reducer consumes the candidate.
                if choice.get('start') and self.main_job:
                    self.state.record('main_execution_busy')
                    task = None
                else:
                    task = self.state.apply(choice, self.binding, now)
                if self.state.motion_proposals:
                    proposal=self.state.motion_proposals.popleft()
                    if self.motion_adapter and not self.motion_job:
                        self.motion_job=Job(self.motion_adapter.execute,proposal)
                    else:self.state.record('motion_execution_busy')
                if task:
                    self.main_task = task
                    self.main_job = Job(self.gateway.main, task)
            except Exception:
                self.state.record('fast_failed')
            self.fast_job = self.binding = None
        if self.speech_adapter:
            self.speech_adapter.advance(self.state.authority)
            if self.state.speech_proposals:
                proposal=self.state.speech_proposals.popleft()
                try:self.speech_adapter.execute(proposal)
                except Exception:self.state.record('speech_admission_rejected')
        self.state.collect(now)
        if self.fast_job and now > self.binding.deadline and not self.expiry_logged:
            self.state.record('fast_deadline_expired')
            self.expiry_logged = True
        if self.motion_adapter and self.state.actor_binding is None:return
        if now < self.next_tick:
            return
        # No catch-up burst. Skipped busy ticks remain explicit gaps.
        self.next_tick = now + self.config['period_s']
        if self.fast_job:
            self.state.record('tick_busy_gap'); return
        view = self.state.snapshot(now)
        if self.main_job and not self.main_job.future.done() and self.main_task.status != 'running':
            # Revoking a result does not conceal still-busy physical execution.
            view['pending'] = view['pending'][:7] + [dict(alias=self.main_task.task_id,
                kind=self.main_task.kind, status='execution_busy_result_revoked',
                age_ms=max(0, int((now-self.main_task.created)*1000)))]
        self.binding = self.state.bind(now, self.config['fast_deadline_s'])
        self.fast_job = Job(self.gateway.fast, self.binding.request_id, view)
        self.expiry_logged = False
        self.state.record('fast_requested', request_id=self.binding.request_id)

    def run(self, duration_s, events=(), output=None):
        start = time.monotonic()
        pending = iter(events)
        event = next(pending, None)
        while time.monotonic() - start < duration_s:
            now = time.monotonic()
            while event is not None and event['at_s'] <= now-start:
                self.ingest({k:v for k,v in event.items() if k != 'at_s'}, now)
                event = next(pending, None)
            self.advance(now)
            time.sleep(min(0.01, self.config['period_s']/10))
        # Stop new admission, invalidate any pending action; no model cancellation claim.
        if self.speech_adapter:self.speech_adapter.close()
        self.closed=True
        motion_stopped=self.motion_adapter.close() if self.motion_adapter else True
        self.state.ingest(dict(type='operator', muted=True),time.monotonic())
        report = dict(mode='replay' if isinstance(self.gateway, ReplayGateway) else 'real_model_shadow',
                      actuators='bounded_native_antenna17' if self.motion_adapter else 'simulated', counts=dict(self.state.counts),
                      execution_busy=dict(fast=bool(self.fast_job and not self.fast_job.future.done()),
                                          main=bool(self.main_job and not self.main_job.future.done()),
                                          actor=bool(self.actor_job and not self.actor_job.future.done()),
                                          context=bool(self.context_job and not self.context_job.future.done()),
                                          motion=bool(self.motion_job and not self.motion_job.future.done()) or bool(self.motion_adapter and hasattr(self.motion_adapter,'status') and self.motion_adapter.status()['execution_busy'])),
                      ledger=list(self.state.ledger), authority=self.state.authority.wire())
        if self.motion_adapter:
            report['motion_receipts']=list(self.motion_adapter.receipts)
            report['motion_stop_known']=motion_stopped
        if self.speech_adapter:
            report['speech']=self.speech_adapter.status()
            report['execution_busy']['speech']=report['speech']['execution_busy'] or report['speech']['tts_execution_busy']
        if output:
            from pathlib import Path
            path = Path(output)
            # Avoid accidental overwriting; caller selects privacy-sensitive output destination.
            with path.open('x') as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
        return report
