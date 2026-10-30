"""Bounded source-only bridge; owns no device, model, transport or permissions.

Call advance() from an existing clock. Callbacks run in two independent daemon
lanes; publication never waits for them. Executors MUST check the permit at each
output and atomically check the proposal's authority in the existing actuator.
Cancellation is cooperative: a lane stays busy until its callback really exits.
"""
from collections import deque
from concurrent.futures import Future
from copy import deepcopy
import json
import math
import threading
import time


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _text(value, limit):
    return type(value) is str and 0 < len(value) <= limit


class _Job:
    def __init__(self, callback, *args, cancel=None, deadline=None, proposal=None):
        self.cancel = cancel if cancel is not None else threading.Event()
        self.deadline, self.proposal = deadline, proposal
        self.future = Future()
        def run():
            try:
                self.future.set_result(callback(*args))
            except BaseException as exc:
                self.future.set_exception(exc)
        self.thread = threading.Thread(target=run, daemon=True, name='sensory-callback')


class ExecutionPermit:
    """Cooperative fence; never substitutes for actuator-side atomic admission."""
    def __init__(self, loop, proposal, cancelled):
        self._loop, self._proposal = loop, proposal
        self.cancelled = cancelled

    def __call__(self):
        with self._loop._lock:
            valid = not self.cancelled.is_set() and self._loop._valid(self._proposal)
            if not valid:
                self.cancelled.set()
            return valid


class SensoryLoop:
    """decision(snapshot, cancel_event) -> choice; execute(proposal, permit).

    Choice is {action, why, evidence: [observation_id], payload?: JSON object}.
    Non-wait choices require at least one current fresh observation. Callback
    results contain no grants: set_authority() is a trusted integration hook.
    Times are from this instance's monotonic clock, not remote wall clocks.
    """
    def __init__(self, decision, execute, *, clock=time.monotonic, sensor_cap=12,
                 history_cap=8, decision_timeout_s=5, proposal_ttl_s=3):
        if not callable(decision) or not callable(execute) or not callable(clock):
            raise ValueError('Callbacks and monotonic clock required')
        if (type(sensor_cap) is not int or not 1 <= sensor_cap <= 32
                or type(history_cap) is not int or not 1 <= history_cap <= 32
                or not _number(decision_timeout_s, .01, 120)
                or not _number(proposal_ttl_s, .01, 120)):
            raise ValueError('Bounded loop configuration required')
        self._decision, self._execute, self._clock = decision, execute, clock
        self._lock = threading.RLock()
        self._sensor_cap, self._timeout, self._ttl = sensor_cap, decision_timeout_s, proposal_ttl_s
        self._sensors = {}
        self._previous = deque(maxlen=history_cap)
        self._authority, self._revision, self._state_revision = {}, 0, 0
        self._enabled = self._private = self._closed = False
        self._counter = 0
        self._dirty = False
        self._decision_job = self._execution_job = None
        self._pending_decision = self._pending_proposal = None
        self._counts = dict(published=0, evicted=0, pending_replaced=0,
                            decision_started=0, decision_failed=0, discarded=0,
                            execution_started=0, execution_failed=0, completed=0)

    def _withdraw(self):
        self._revision += 1
        self._pending_decision = self._pending_proposal = None
        self._dirty = False
        for job in (self._decision_job, self._execution_job):
            if job is not None:
                job.cancel.set()

    def set_authority(self, binding, *, enabled, privacy=False):
        """Bind boot/epochs from trusted controls; never call with model output."""
        if (type(binding) is not dict or type(enabled) is not bool
                or type(privacy) is not bool):
            raise ValueError('Exact trusted authority and booleans required')
        raw = json.dumps(binding, allow_nan=False)
        if len(raw.encode()) > 2048:
            raise ValueError('Authority bound')
        binding = json.loads(raw)
        with self._lock:
            if self._closed:
                raise RuntimeError('Loop closed')
            if (binding, enabled, privacy) != (self._authority, self._enabled, self._private):
                self._withdraw()
                # Old boot/MIC/policy observations must not be re-admitted by
                # a later ON. A producer publishes again under the new grant.
                self._sensors.clear()
                self._authority, self._enabled, self._private = binding, enabled, privacy
                if privacy:
                    self._previous.clear()
                self._dirty = enabled and not privacy
            return self._revision

    def invalidate(self):
        """Withdraw outputs on foreground activity or other trusted supersession."""
        with self._lock:
            self._withdraw()
            return self._revision

    def stop(self):
        with self._lock:
            self._withdraw()
            self._enabled = False
            self._sensors.clear()

    def close(self):
        """Withdraw admission without claiming callbacks/devices have stopped."""
        with self._lock:
            self.stop()
            self._closed = True

    def publish(self, observation):
        """Publish one actual observation; no capture/inference happens here.

        Required: kind, source, observed_monotonic, summary. Optional: ttl_s
        (default 2), source_event_id. Newest value per (kind,source) wins.
        Returns local provenance id, or None for private/out-of-order data.
        """
        required = {'kind', 'source', 'observed_monotonic', 'summary'}
        if type(observation) is not dict or not required <= observation.keys() or observation.keys() - required - {'ttl_s', 'source_event_id'}:
            raise ValueError('Observation envelope')
        item = deepcopy(observation)
        now = self._clock()
        ttl = item.get('ttl_s', 2)
        if (not _text(item['kind'], 64) or not _text(item['source'], 128)
                or not _text(item['summary'], 512)
                or not _number(item['observed_monotonic'], 0, now)
                or not _number(ttl, .01, 120)
                or ('source_event_id' in item and not _text(item['source_event_id'], 128))):
            raise ValueError('Bounded local-clock observation required')
        key = (item['kind'], item['source'])
        with self._lock:
            if self._closed:
                raise RuntimeError('Loop closed')
            if self._private:
                return None
            old = self._sensors.get(key)
            if old and item['observed_monotonic'] <= old['observed_monotonic']:
                return None
            self._counter += 1
            item.update(id='obs-' + str(self._counter), expires_monotonic=item['observed_monotonic'] + ttl)
            if key not in self._sensors and len(self._sensors) >= self._sensor_cap:
                del self._sensors[next(iter(self._sensors))]
                self._counts['evicted'] += 1
            self._sensors.pop(key, None)
            self._sensors[key] = item
            self._state_revision += 1
            self._counts['published'] += 1
            self._dirty = True
            self._fence_outputs()
            return item['id']

    def _snapshot(self):
        now = self._clock()
        return dict(authority=deepcopy(self._authority), authority_revision=self._revision,
                    state_revision=self._state_revision, at_monotonic=now,
                    enabled=self._enabled, privacy=self._private,
                    observations=[dict(deepcopy(s), state='fresh' if now < s['expires_monotonic'] else 'expired',
                                       age_s=max(0, now-s['observed_monotonic'])) for s in self._sensors.values()],
                    busy=dict(decision=self._decision_job is not None,
                              execution=self._execution_job is not None),
                    pending=dict(decision=self._pending_decision is not None,
                                 execution=self._pending_proposal is not None),
                    previous_actions=deepcopy(list(self._previous)), counts=dict(self._counts))

    def snapshot(self):
        with self._lock:
            return self._snapshot()

    def request_decision(self):
        """Optional bounded idle clock trigger; does not fabricate an event."""
        with self._lock:
            self._dirty = True

    def _valid(self, proposal):
        now = self._clock()
        if (self._closed or not self._enabled or self._private
                or proposal['authority_revision'] != self._revision
                or now >= proposal['expires_monotonic']):
            return False
        current = {s['id']: s for s in self._sensors.values()}
        return all(ref in current and now < current[ref]['expires_monotonic'] for ref in proposal['evidence'])

    def _fence_outputs(self):
        if self._pending_proposal and not self._valid(self._pending_proposal):
            self._pending_proposal = None
            self._counts['discarded'] += 1
        job = self._execution_job
        if job and not self._valid(job.proposal):
            job.cancel.set()

    def _proposal(self, choice, view, job):
        if (job.cancel.is_set() or self._clock() >= job.deadline
                or type(choice) is not dict or not {'action', 'why', 'evidence'} <= choice.keys()
                or choice.keys() - {'action', 'why', 'evidence', 'payload'}
                or not _text(choice['action'], 64) or not _text(choice['why'], 256)
                or type(choice['evidence']) is not list or len(choice['evidence']) > self._sensor_cap
                or any(not _text(ref, 128) for ref in choice['evidence'])
                or type(choice.get('payload', {})) is not dict):
            return None
        if len(json.dumps(choice, allow_nan=False).encode()) > 2048:
            return None
        evidence = list(dict.fromkeys(choice['evidence']))
        if choice['action'] == 'wait':
            return None
        observed = {s['id']: s for s in view['observations'] if s['state'] == 'fresh'}
        if not evidence or any(ref not in observed for ref in evidence):
            return None
        now = self._clock()
        proposal = dict(action=choice['action'], why=choice['why'], evidence=evidence,
                        payload=deepcopy(choice.get('payload', {})),
                        provenance=[deepcopy(observed[ref]) for ref in evidence],
                        authority=deepcopy(view['authority']), authority_revision=view['authority_revision'],
                        state_revision=view['state_revision'], decided_monotonic=now,
                        expires_monotonic=min(now+self._ttl, *(observed[ref]['expires_monotonic'] for ref in evidence)))
        return proposal if self._valid(proposal) else None

    def advance(self):
        """Non-blocking harvest/admission. Caller supplies the ongoing clock."""
        with self._lock:
            self._fence_outputs()
            job = self._execution_job
            if job and job.future.done():
                try:
                    result = job.future.result()
                    outcome = 'completed' if result is True and not job.cancel.is_set() and self._valid(job.proposal) else 'withdrawn'
                    if outcome == 'completed':
                        self._counts['completed'] += 1
                except BaseException:
                    outcome = 'failed'
                    self._counts['execution_failed'] += 1
                if not self._private:
                    self._previous.append(dict(action=job.proposal['action'], evidence=list(job.proposal['evidence']),
                                               authority_revision=job.proposal['authority_revision'],
                                               at_monotonic=self._clock(), outcome=outcome))
                self._execution_job = None
            job = self._decision_job
            if job and self._clock() >= job.deadline:
                job.cancel.set()
            if job and job.future.done():
                try:
                    proposal = self._proposal(job.future.result(), job.view, job)
                    if proposal:
                        self._pending_proposal = proposal
                    else:
                        self._counts['discarded'] += 1
                except BaseException:
                    self._counts['decision_failed'] += 1
                self._decision_job = None
            if self._enabled and not self._private and not self._closed:
                if self._dirty:
                    if self._pending_decision is not None:
                        self._counts['pending_replaced'] += 1
                    self._pending_decision = self._snapshot()
                    self._dirty = False
                if self._decision_job is None and self._pending_decision is not None:
                    self._pending_decision = None
                    # Rebuild at actual admission; pending never freezes stale ages/busy.
                    view = self._snapshot()
                    cancel = threading.Event()
                    job = _Job(self._decision, deepcopy(view), cancel, cancel=cancel,
                               deadline=self._clock()+self._timeout)
                    job.view = view
                    self._decision_job = job
                    self._counts['decision_started'] += 1
                    job.thread.start()
                if self._execution_job is None and self._pending_proposal is not None:
                    proposal, self._pending_proposal = self._pending_proposal, None
                    if self._valid(proposal):
                        cancel = threading.Event()
                        permit = ExecutionPermit(self, proposal, cancel)
                        def execute(p=deepcopy(proposal), gate=permit):
                            return self._execute(p, gate) if gate() else False
                        job = _Job(execute, cancel=cancel, proposal=proposal)
                        self._execution_job = job
                        self._counts['execution_started'] += 1
                        job.thread.start()
                    else:
                        self._counts['discarded'] += 1
            return self._snapshot()
