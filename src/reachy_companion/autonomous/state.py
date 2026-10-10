"""Single-owner reducer. All actuations are entries in a bounded simulated ledger."""
from collections import Counter, deque
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import hashlib
import json
import time
from .contracts import Authority, Binding, Sensor, Task, uid, validate


def utc():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class State:
    def __init__(self, compute_boot='replay-compute', config=None):
        self.config = config or dict(ledger_cap=256, sensor_cap=12, task_cap=8,
                                    candidate_cap=8, task_timeout_s=30, proposal_ttl_s=15)
        self.authority = Authority(uid(), compute_boot)
        self.compute_generation = 0
        self.retired_compute_boots = deque(maxlen=128)
        self.revision = 0
        self.muted = False
        self.privacy = False
        self.sensors = {}
        self.candidates = {}
        self.candidate_kinds = {}
        self.current_utterance = ''
        self.memory_items = {}
        self.context_sensors = []
        self.memory_store_id = None
        self.memory_revision = -1
        self.context_received = None
        self.tasks = {}
        self.previous = deque(maxlen=3)
        self.ledger = deque(maxlen=self.config['ledger_cap'])
        self.counts = Counter()
        self.consumed = deque(maxlen=128)
        self.focus = None
        self.actor_binding=None;self.actor_signature=None;self.actor_deadline=0
        self.motion_allowed=False;self.quiet=False;self.motion_proposals=deque(maxlen=1)
        self.speech_attached=False;self.speech_proposals=deque(maxlen=1)

    def set_actor(self,receipt):
        # Trusted adapter receipt only, never a model/operator event payload.
        signature=(tuple(sorted(receipt['binding'].items())),tuple(sorted(receipt['policy'].items())),receipt['microphone_enabled'])
        if signature!=self.actor_signature:
            self.actor_signature=signature
            self.authority=replace(self.authority,operator_epoch=self.authority.operator_epoch+1,
                robot_boot_id=receipt['binding']['actor_boot_id'],microphone_epoch=receipt['binding']['operator_epoch'])
            self.revision+=1
        self.actor_binding=dict(receipt['binding']);self.actor_deadline=receipt['received']+.3
        self.muted=not receipt['microphone_enabled'];self.quiet=receipt['policy']['quiet'];self.privacy=receipt['policy']['privacy_all']
        self.motion_allowed=receipt['motion_allowed']

    def record(self, kind, **values):
        self.counts[kind] += 1
        self.ledger.append(dict(kind=kind, at=utc(), **values))

    def set_compute_boot(self, boot, generation):
        """Trusted owner handshake only; completions never call this method."""
        if not isinstance(boot, str) or not 1 <= len(boot) <= 256 or type(generation) is not int:
            raise ValueError('Invalid compute handshake')
        if generation <= self.compute_generation or boot in self.retired_compute_boots:
            self.record('compute_handshake_stale'); return False
        self.compute_generation = generation
        if boot != self.authority.compute_boot_id:
            self.retired_compute_boots.append(self.authority.compute_boot_id)
            self.authority = replace(self.authority, compute_boot_id=boot)
            self.revision += 1
            self.record('compute_restart')
        return True

    def ingest(self, event, now):
        kind = event.get('type')
        if kind == 'operator':
            # Even unmute increments epochs; old actions cannot regain authority.
            if not isinstance(event.get('muted'), bool):
                raise ValueError('operator muted must be boolean')
            self.muted = event['muted']
            if 'privacy_all' in event:
                if type(event['privacy_all']) is not bool:raise ValueError('Privacy flag must be boolean')
                self.privacy=event['privacy_all']
            self.current_utterance = ''
            self.candidates.clear()
            self.candidate_kinds.clear()
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
            self.current_utterance = text
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

    def update_context(self,value,now,roundtrip_s=0):
        memory=value['memory'];items=memory['items']
        if len(items)>8 or type(memory['revision']) is not int or memory['revision']<0:raise ValueError('Context memory bound')
        if not isinstance(memory['store_id'],str) or not 1<=len(memory['store_id'])<=128:raise ValueError('Memory store identity')
        if self.memory_store_id is not None and self.memory_store_id!=memory['store_id']:raise ValueError('Memory store changed without owner handshake')
        if self.memory_store_id==memory['store_id'] and memory['revision']<self.memory_revision:
            self.record('context_stale');return False
        next_items={}
        for item in items:
            validate('MemoryItem',item)
            if item['status']!='active' or len(item['content'])>256:raise ValueError('Context memory projection')
            alias=item['id']+':'+str(item['version'])
            if len(alias)>256 or alias in next_items:raise ValueError('Memory alias bound/duplicate')
            next_items[alias]=item
        if len(value['sensors'])>1:raise ValueError('Latest-only camera slot')
        for sensor in value['sensors']:
            validate('FastView',{**self.snapshot(now),'sensors':[sensor]})
            bounds=sensor.get('age_bounds_ms')
            if bounds and bounds['upper'] is not None:
                if bounds['upper']<bounds['lower']:raise ValueError('Invalid age interval')
                bounds['upper']+=max(0,int(roundtrip_s*1000))
        self.memory_items=next_items;self.memory_store_id=memory['store_id'];self.memory_revision=memory['revision']
        self.context_sensors=json.loads(json.dumps(value['sensors']));self.context_received=now
        for task in self.tasks.values():
            if task.status in ('running','ready','failed') and not self.memory_current(task):
                task.status='discarded';task.result=None
                self.record('task_memory_invalidated',task_id=task.task_id)
                if (task.authority==self.authority and task.kind=='main' and not self.muted and not self.privacy
                        and self.current_utterance and not self.candidates):
                    ref=uid();self.candidates[ref]=self.current_utterance;self.candidate_kinds[ref]='main'
                    self.record('memory_retry_candidate')
        self.record('context_updated',memory_revision=self.memory_revision)
        return True

    def memory_digest(self,alias):
        item=self.memory_items.get(alias)
        if item and not self.memory_valid(item):return None
        return hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest() if item else None

    @staticmethod
    def memory_valid(item):
        now=datetime.now(timezone.utc)
        start=datetime.fromisoformat(item['valid_from'].replace('Z','+00:00'))
        end=datetime.fromisoformat(item['valid_until'].replace('Z','+00:00')) if item['valid_until'] else None
        return start<=now and (end is None or now<end)

    def memory_current(self,task):
        return all(self.memory_digest(alias)==digest for alias,digest in task.memory_dependencies)

    def context_view(self,now):
        sensors=json.loads(json.dumps(self.context_sensors))
        elapsed=max(0,int((now-self.context_received)*1000)) if self.context_received is not None else 0
        for sensor in sensors:
            if self.privacy:
                sensor.update(state='disabled',summary='',age_ms=None)
                sensor.pop('lineage_id',None);sensor.pop('source_id',None)
            elif 'age_bounds_ms' in sensor:
                sensor['age_bounds_ms']['lower']+=elapsed
                if sensor['age_bounds_ms']['upper'] is not None:sensor['age_bounds_ms']['upper']+=elapsed
                if sensor['age_bounds_ms']['lower']>2000:sensor['state']='stale'
        return sensors

    def collect(self, now):
        for task in self.tasks.values():
            if task.status == 'running' and now > task.deadline:
                task.status = 'expired'
                self.record('task_expired', task_id=task.task_id)
            if task.status == 'ready' and (now > task.expires or task.authority != self.authority or not self.memory_current(task)):
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
            op=dict(microphone_enabled=not self.muted, privacy_all=self.privacy, quiet=self.quiet,
                    motion_allowed=self.motion_allowed and now<self.actor_deadline and not self.privacy and not self.quiet, operator_epoch=self.authority.operator_epoch,
                    microphone_epoch=self.authority.microphone_epoch, interaction_epoch=self.authority.interaction_epoch,
                    speech_epoch=self.authority.speech_epoch),
            sim=dict(origin='simulated', mood=0, arousal=0.2, fatigue=0, curiosity=0.5,
                     confidence=None, social_need=0, transition_reasons=[]),
            scene='Actual bounded antenna17 owner; any fixture sensors are synthetic. Camera semantics unavailable.' if self.actor_binding else 'Shadow actors; camera observations include age bounds and provenance.' if self.context_sensors else 'Shadow/replay. No physical sensor or actuator connected.',
            sensors=([s.view(now, self.muted) for s in list(self.sensors.values())[:12-len(self.context_sensors)]]+self.context_view(now)),
            prev=list(self.previous), dialogue='' if self.muted or self.privacy else self.current_utterance,
            memory=[] if self.privacy else [dict(alias=alias,type=item['epistemic_type'],summary=item['content']) for alias,item in self.memory_items.items() if self.memory_valid(item)], personality='Ричи: краткий, прямой, любопытный.',
            principles='No invented perception. Muted blocks speech. Motion attentive means only a finite antenna17 target <=2 degrees, never head/body; only when motion_allowed.' if self.actor_binding else 'No invented perception. Muted blocks speech. Simulated actions only.', goal=None,
            pending=pending[:8], ready=ready[:4],
            candidates=[dict(alias=k, kind=self.candidate_kinds[k], summary=v[:256]) for k,v in self.candidates.items()][:8],
            evidence_aliases=[])
        return validate('FastView', view)

    def dependency_digest(self, alias, now):
        if alias in self.candidates:
            value = ('candidate', self.candidate_kinds.get(alias), self.candidates[alias])
        else:
            task = self.tasks.get(alias)
            if not task or task.status != 'ready' or task.authority != self.authority or now > task.expires:
                return None
            value = ('proposal', task.attempt_id, task.result, task.expires)
        return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()

    def bind(self, now, timeout):
        candidates = tuple(self.candidates)
        ready = tuple(t.task_id for t in self.tasks.values() if t.status == 'ready')[:4]
        return Binding(uid(), self.authority, self.revision, now + timeout,
                       candidates, ready, (),
                       tuple((alias, self.dependency_digest(alias, now)) for alias in candidates + ready))

    def apply(self, value, binding, now):
        validate('FastChoice', value)
        if binding.authority != self.authority or now > binding.deadline:
            self.record('decision_stale', request_id=binding.request_id); return None
        if binding.request_id in self.consumed:
            self.record('decision_duplicate'); return None
        motion=value.get('motion')
        if motion and (motion!='attentive' or not self.motion_allowed or now>=self.actor_deadline or self.quiet or self.privacy
                or not self.actor_binding or value.get('start') or value.get('commit')):
            self.record('motion_capability_rejected');return None
        if value.get('say') or value.get('goal_review') or value.get('e'):
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
        if start and self.config.get('context',{}).get('enabled') and self.memory_store_id is None:
            self.record('context_not_ready');return None
        if commit and commit not in binding.ready:
            self.record('alias_rejected'); return None
        dependencies = dict(binding.dependencies)
        refs = [ref for ref in (focus, start['input_ref'] if start else None, commit) if ref is not None]
        if any(dependencies.get(ref) is None or dependencies[ref] != self.dependency_digest(ref, now) for ref in refs):
            self.record('dependency_changed'); return None
        self.consumed.append(binding.request_id)
        self.previous.append(value['a'] + ': ' + value['why'])
        self.focus = focus
        self.record('decision_accepted', request_id=binding.request_id, activity=value['a'])
        if motion:
            self.motion_proposals.append(dict(motion=motion,request_id=binding.request_id,authority=binding.authority,
                actual_binding=dict(self.actor_binding),deadline=min(binding.deadline,now+.5)))
            self.record('motion_proposed',request_id=binding.request_id)
        if commit:
            task = self.tasks.get(commit)
            if not task or task.status != 'ready' or task.authority != self.authority or now > task.expires:
                self.record('proposal_stale'); return None
            task.status = 'committed'
            if self.speech_attached:
                if isinstance(task.result,str) and 0<len(task.result)<=1024:
                    self.speech_proposals.append(dict(text=task.result,request_id=binding.request_id,authority=self.authority,deadline=min(task.expires,now+30)))
                    self.record('speech_proposed',task_id=task.task_id)
                else:self.record('speech_text_rejected',task_id=task.task_id)
            else:self.record('simulated_speech', task_id=task.task_id, text=task.result)
            task.result = None
        if start:
            ref = start['input_ref']
            if any(t.input_ref == ref for t in self.tasks.values()) or len(self.tasks) >= self.config['task_cap']:
                self.record('task_admission_rejected'); return None
            task = Task(uid(), uid(), ref, self.candidates.pop(ref), self.authority, now,
                        now+self.config['task_timeout_s'], kind=self.candidate_kinds.pop(ref))
            if task.kind=='main' and (self.memory_items or self.context_sensors):
                active_memory={alias:item for alias,item in self.memory_items.items() if self.memory_valid(item)}
                task.prompt=dict(schema_version='context-1',utterance=task.prompt,memory=list(active_memory.values()),observations=self.context_view(now))
                task.memory_dependencies=tuple((alias,hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest()) for alias,item in active_memory.items())
            self.tasks[task.task_id] = task
            self.record('task_started', task_id=task.task_id)
            return task
        return None

    def complete(self, task_id, attempt_id, authority, result, now, error=None):
        task = self.tasks.get(task_id)
        if not task or task.attempt_id != attempt_id or task.authority != authority or authority != self.authority or now > task.deadline or task.status != 'running' or not self.memory_current(task):
            if task and task.attempt_id == attempt_id and task.authority == authority and task.status == 'running':
                task.status = 'discarded'
            self.record('task_result_stale', task_id=task_id); return
        if error or not isinstance(result, str) or not result.strip() or len(result) > 8192:
            task.status = 'failed'; self.record('task_failed', task_id=task_id); return
        task.status, task.result = 'ready', result
        task.expires = now + self.config['proposal_ttl_s']
        self.record('proposal_ready', task_id=task_id)
