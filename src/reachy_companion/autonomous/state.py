"""Single-owner reducer. All actuations are entries in a bounded simulated ledger."""
from collections import Counter, deque
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import time
from .contracts import Authority, Binding, Sensor, Task, uid, validate


def utc():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class State:
    def __init__(self, compute_boot='replay-compute', config=None):
        self.config = config or dict(ledger_cap=256, sensor_cap=12, task_cap=8,
                                    candidate_cap=8, task_timeout_s=30, proposal_ttl_s=15)
        self.authority = Authority(uid(), compute_boot)
        self.revision = 0
        self.muted = False
        self.privacy = False
        self.sensors = {}
        self.candidates = {}
        self.candidate_kinds = {}
        self.tasks = {}
        self.previous = deque(maxlen=3)
        self.ledger = deque(maxlen=self.config['ledger_cap'])
        self.counts = Counter()
        self.consumed = deque(maxlen=128)
        self.focus = None

    def record(self, kind, **values):
        self.counts[kind] += 1
        self.ledger.append(dict(kind=kind, at=utc(), **values))

    def set_compute_boot(self, boot):
        if boot != self.authority.compute_boot_id:
            self.authority = replace(self.authority, compute_boot_id=boot)
            self.revision += 1
            self.record('compute_restart')

    def ingest(self, event, now):
        kind = event.get('type')
        if kind == 'operator':
            # Even unmute increments epochs; old actions cannot regain authority.
            if not isinstance(event.get('muted'), bool):
                raise ValueError('operator muted must be boolean')
            self.muted = event['muted']
            self.authority = replace(self.authority,
                operator_epoch=self.authority.operator_epoch + 1,
                microphone_epoch=self.authority.microphone_epoch + 1,
                speech_epoch=self.authority.speech_epoch + 1)
            self.record('operator', muted=self.muted)
        elif kind == 'utterance':
            text = event.get('text')
            if not isinstance(text, str) or not text or len(text) > 1024:
                raise ValueError('utterance must fit mandatory input; no silent truncation')
            if self.muted or self.privacy:
                self.record('input_blocked'); return
            self.authority = replace(self.authority,
                interaction_epoch=self.authority.interaction_epoch + 1,
                speech_epoch=self.authority.speech_epoch + 1)
            # Old candidates are no longer current; active tasks remain accounted.
            self.candidates.clear()
            self.candidate_kinds.clear()
            ref = uid()
            self.candidates[ref] = text
            self.candidate_kinds[ref] = "main"
            self.record('new_turn')
        elif kind == 'workflow':
            value = event.get('value')
            if not isinstance(value, str) or len(value)>256:
                raise ValueError('workflow argument cap')
            if not self.config.get('workflows',{}).get('enabled'):
                self.record('workflow_disabled'); return
            if len(self.candidates)>=self.config['candidate_cap']:
                self.record('candidate_admission_rejected'); return
            ref=uid(); self.candidates[ref]=value; self.candidate_kinds[ref]='research'
        elif kind == 'sensor':
            name, summary = event.get('id'), event.get('summary', '')
            availability = event.get('availability', 'available')
            if not isinstance(name, str) or not 1 <= len(name) <= 128 or not isinstance(summary, str) or len(summary) > 256:
                raise ValueError('sensor bounds exceeded')
            if availability not in ('available', 'unknown', 'unsupported', 'disabled', 'offline'):
                raise ValueError('invalid sensor availability')
            if name not in self.sensors and len(self.sensors) >= self.config['sensor_cap']:
                self.record('sensor_admission_rejected'); return
            if self.privacy or (self.muted and name.startswith('audio')):
                self.record('input_blocked'); return
            age, ttl = event.get('age_ms', 0), event.get('ttl_ms', 5000)
            if type(age) is not int or age < 0 or type(ttl) is not int or not 1 <= ttl <= 60000:
                raise ValueError('invalid sensor times')
            captured = now - age / 1000 if availability == 'available' else None
            self.sensors[name] = Sensor(name, summary if captured is not None else '', captured, ttl / 1000, availability)
        else:
            raise ValueError('unknown replay event')
        self.revision += 1

    def collect(self, now):
        for task in self.tasks.values():
            if task.status == 'running' and now > task.deadline:
                task.status = 'expired'
                self.record('task_expired', task_id=task.task_id)
            if task.status == 'ready' and (now > task.expires or task.authority != self.authority):
                task.status = 'discarded'; task.result = None
                self.record('proposal_discarded', task_id=task.task_id)
        # Bounded terminal history; active execution accounted separately by scheduler.
        if len(self.tasks) >= self.config['task_cap']:
            terminal = [k for k, t in self.tasks.items() if t.status not in ('running', 'ready')]
            for key in terminal:
                del self.tasks[key]

    def snapshot(self, now):
        self.collect(now)
        pending, ready = [], []
        for task in self.tasks.values():
            if task.status == 'running':
                pending.append(dict(alias=task.task_id, kind=task.kind, status='running',
                                    age_ms=max(0, int((now-task.created)*1000))))
            elif task.status == 'ready':
                expires = datetime.now(timezone.utc) + timedelta(seconds=max(0, task.expires-now))
                ready.append(dict(alias=task.task_id, summary=task.result[:256],
                                  expires_at=expires.isoformat().replace('+00:00', 'Z')))
        view = dict(schema_version='1.1', at=utc(), mode='ACTIVE',
            op=dict(microphone_enabled=not self.muted, privacy_all=self.privacy, quiet=False,
                    motion_allowed=False, operator_epoch=self.authority.operator_epoch,
                    microphone_epoch=self.authority.microphone_epoch, interaction_epoch=self.authority.interaction_epoch,
                    speech_epoch=self.authority.speech_epoch),
            sim=dict(origin='simulated', mood=0, arousal=0.2, fatigue=0, curiosity=0.5,
                     confidence=None, social_need=0, transition_reasons=[]),
            scene='Shadow/replay. No physical sensor or actuator connected.',
            sensors=[s.view(now, self.muted) for s in self.sensors.values()],
            prev=list(self.previous), dialogue=next((v for k,v in self.candidates.items() if self.candidate_kinds[k]=='main'), ''),
            memory=[], personality='Ричи: краткий, прямой, любопытный.',
            principles='No invented perception. Muted blocks speech. Simulated actions only.', goal=None,
            pending=pending[:8], ready=ready[:4],
            candidates=[dict(alias=k, kind=self.candidate_kinds[k], summary=v[:256]) for k,v in self.candidates.items()][:8],
            evidence_aliases=[])
        return validate('FastView', view)

    def bind(self, now, timeout):
        return Binding(uid(), self.authority, self.revision, now + timeout,
                       tuple(self.candidates), tuple(t.task_id for t in self.tasks.values() if t.status=='ready'), ())

    def apply(self, value, binding, now):
        validate('FastChoice', value)
        if binding.authority != self.authority or now > binding.deadline or binding.revision != self.revision:
            self.record('decision_stale', request_id=binding.request_id); return None
        if binding.request_id in self.consumed:
            self.record('decision_duplicate'); return None
        # This slice has no tool broker, goal changes, motions, or direct short speech.
        if value.get('say') or value.get('motion') or value.get('goal_review') or value.get('e'):
            self.record('capability_rejected'); return None
        focus = value.get('focus')
        known = set(binding.candidates) | set(binding.ready)
        if focus is not None and focus not in known:
            self.record('alias_rejected'); return None
        start, commit = value.get('start'), value.get('commit')
        if start and commit:
            self.record('capability_rejected'); return None
        if (start or commit) and (self.muted or self.privacy):
            self.record('muted_action_rejected'); return None
        if start and (start['input_ref'] not in binding.candidates or start['type'] != self.candidate_kinds.get(start['input_ref'])):
            self.record('alias_rejected'); return None
        if commit and commit not in binding.ready:
            self.record('alias_rejected'); return None
        self.consumed.append(binding.request_id)
        self.previous.append(value['a'] + ': ' + value['why'])
        self.focus = focus
        self.record('decision_accepted', request_id=binding.request_id, activity=value['a'])
        if commit:
            task = self.tasks.get(commit)
            if not task or task.status != 'ready' or task.authority != self.authority or now > task.expires:
                self.record('proposal_stale'); return None
            task.status = 'committed'
            self.record('simulated_speech', task_id=task.task_id, text=task.result)
            task.result = None
        if start:
            ref = start['input_ref']
            if any(t.input_ref == ref for t in self.tasks.values()) or len(self.tasks) >= self.config['task_cap']:
                self.record('task_admission_rejected'); return None
            task = Task(uid(), uid(), ref, self.candidates.pop(ref), self.authority, now,
                        now+self.config['task_timeout_s'], kind=self.candidate_kinds.pop(ref))
            self.tasks[task.task_id] = task
            self.record('task_started', task_id=task.task_id)
            return task
        return None

    def complete(self, task_id, attempt_id, authority, result, now, error=None):
        task = self.tasks.get(task_id)
        if not task or task.attempt_id != attempt_id or task.authority != authority or authority != self.authority or now > task.deadline or task.status != 'running':
            if task and task.attempt_id == attempt_id and task.authority == authority and task.status == 'running':
                task.status = 'discarded'
            self.record('task_result_stale', task_id=task_id); return
        if error or not isinstance(result, str) or not result.strip() or len(result) > 8192:
            task.status = 'failed'; self.record('task_failed', task_id=task_id); return
        task.status, task.result = 'ready', result
        task.expires = now + self.config['proposal_ttl_s']
        self.record('proposal_ready', task_id=task_id)
