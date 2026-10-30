"""Observe the existing normal Agent; never acquire audio or conversation work."""
import copy
from collections import deque
import errno
import http.client
from dataclasses import dataclass, replace
import json
import math
import socket
import time
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

from ..client import control_authority, compare_control_operator, _demo_read
from .contracts import Binding, decode, uid, validate
from .runtime import Job, Scheduler
from .state import State


def endpoint(url, configured_url=None):
    parts = urlsplit(url)
    if (parts.scheme != 'http' or not parts.hostname
            or (parts.hostname not in ('127.0.0.1', 'localhost', '::1') and url != configured_url)
            or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/')):
        raise ValueError('Native endpoint requires loopback or the exact configured Agent URL')
    return url.rstrip('/')


class NativeClient:
    def __init__(self, url, token, *, configured_url=None, quick_ack=False):
        self.url = endpoint(url, configured_url)
        if len(token) < 32: raise ValueError('Native authentication required')
        if quick_ack and not hasattr(socket, 'TCP_QUICKACK'):
            raise ValueError('Immediate status ACK requires Linux TCP_QUICKACK')
        self.quick_ack = quick_ack
        self.token = token
        self.opener = build_opener(ProxyHandler({}))

    def get(self, path, *, setup_hardware=False):
        if setup_hardware and path != '/status':
            raise ValueError('Setup-only hardware read')
        request = Request(self.url + path, headers={'Authorization': 'Bearer ' + self.token})
        with self.opener.open(request, timeout=2 if setup_hardware else .3) as response:
            if self.quick_ack:
                # CPython's HTTPResponse still owns this socket while its body
                # is open, including Connection: close. ACK the headers before
                # reading the small body: delayed ACK + server Nagle otherwise
                # consumes the authority window. This does not alter timestamps.
                response.fp.raw._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)
            raw = response.read(65537)
        if len(raw) > 65536: raise ValueError('Bounded native receipt')
        return decode(raw)


def identity(operator):
    # Phase/capture/listening are observations, not persistent authority.
    return control_authority(operator)


def motor_identity(operator):
    # Validate the ENTIRE typed response. Durable mic state remains a conservative
    # STOP/ABA fence; listening, capture and phase never grant motor authority.
    return control_authority(operator)


def transient_read(exc):
    # Only transport failures of read-only status calls. HTTP/protocol/schema
    # errors and arbitrary OSErrors must never become a reconnect policy.
    if isinstance(exc, HTTPError): return False
    if isinstance(exc, URLError): return transient_read(exc.reason)
    return isinstance(exc, (TimeoutError, ConnectionError)) or (
        isinstance(exc, OSError) and exc.errno in {
            errno.ETIMEDOUT, errno.ECONNREFUSED, errno.ECONNRESET,
            errno.ECONNABORTED, errno.EHOSTUNREACH, errno.ENETUNREACH})


class StockNotSent(Exception):
    pass


class NativeReadExpired(TimeoutError):
    pass


def guarded_control(config, base, path, payload, expected, *, deadline, response_timeout, admission,
                    motor_only=False, operator_check=None):
    """Native-only stock send barrier; no process-wide transport monkeypatch."""
    endpoint = urlsplit(base)
    if endpoint.scheme != 'http' or endpoint.path or endpoint.query or endpoint.fragment or endpoint.username:
        raise ValueError('Direct native Hub endpoint required')
    class Connection(http.client.HTTPConnection):
        auto_open = 0
        sent = False
        def send(self, data):
            data = memoryview(data)
            while data:
                # Repeat for headers/body/partial sends, immediately at the
                # existing socket boundary. No I/O or waiting in admission.
                if not admission() or time.monotonic() >= self.deadline:
                    raise StockNotSent('Native admission closed')
                if self.sock is None: raise ConnectionError('Prepared stock connection lost')
                self.sock.settimeout(min(2, self.deadline-time.monotonic()))
                self.sent = True  # even a failed send can have an unknown outcome
                count = self.sock.send(data)
                if count <= 0: raise ConnectionError('Stock send failed')
                data = data[count:]
    connection = Connection(endpoint.hostname, endpoint.port, timeout=2)
    try:
        body = json.dumps(payload).encode()
        connection.connect()
        current, began = _demo_read(config, base+'/control/operator', deadline=deadline)
        if operator_check: operator_check(current)
        compare_control_operator(current, expected)
        if (current['expression_version'] != expected['expression_version']
                or (not motor_only and current != expected)):
            raise StockNotSent('Stock observation changed')
        connection.deadline = min(began+.3, deadline)
        connection.request('POST', path, body=body,
            headers={'Authorization': 'Bearer '+config.token, 'Content-Type': 'application/json'})
        connection.sock.settimeout(response_timeout)
        response = connection.getresponse(); raw = response.read(8193)
        if response.status != 200 or len(raw) > 8192: raise ValueError('Stock response UNKNOWN')
        return decode(raw)
    except StockNotSent as exc:
        if connection.sent: raise RuntimeError('Partial stock send UNKNOWN') from exc
        raise
    except Exception as exc:
        if motor_only and not connection.sent:
            raise StockNotSent('Motor pre-send check unavailable/closed') from exc
        raise
    finally:
        connection.close()


class NativeAgent:
    """One real poll slot and one single-use stock slot, independent of inference."""
    def __init__(self, agent, hub, companion_config, expected, hub_boot, *, allow_stock=False, clock=time.monotonic,
                 _motor_scope=False):
        self.agent, self.hub, self.companion_config = agent, hub, companion_config
        self.expected = identity(expected)
        if ((not _motor_scope and not expected['microphone_enabled']) or expected['microphone_owner_id'] is not None
                or expected['motion_policy_owner_id'] is not None
                or expected['motion_policy']['privacy_all'] or expected['motion_policy']['quiet']):
            raise ValueError('Existing unowned normal listening authority required')
        self.clock, self.allow_stock = clock, allow_stock
        self.poll_job = self.stock_job = None
        self.next_poll = 0
        self.latest = None
        self.closed = False
        self.withdrawn = None
        self.stock_used = False
        self.stock_unknown = False
        self.stock_receipt = None
        if not isinstance(hub_boot, str) or not 1 <= len(hub_boot) <= 256: raise ValueError('Current Hub boot required')
        self.hub_boot = hub_boot
        self.polls = 0
        self.voice_busy_since = None
        self.unavailable = False
        self.generation = 0
        self.gaps = deque(maxlen=256)
        self.gap_count = 0
        self.completed_unavailable_s = 0
        self.read_failures = self.late_receipts = self.recoveries = 0
        self.physical_closed_after_gap = False
        self.acoustic_watermark = None

    def read_acoustic(self, status, operator, pcm, began):
        """Read-receipt metadata only. Remote monotonic clocks are not ours."""
        if self.closed or self.withdrawn: return None
        value = status.get('capture_acoustic')
        keys = {'binding', 'source_generation', 'seq', 'mask_generation', 'mask',
                'read_begin', 'read_end', 'read_call', 'window_ms', 'rms', 'vad',
                'loud', 'delta', 'onset', 'clock', 'capture_age_upper_ms',
                'reaction_usable', 'read_age_s'}
        def number(v, low, high):
            return type(v) in (int, float) and math.isfinite(v) and low <= v <= high
        if (type(value) is not dict or set(value) != keys
                or type(value['binding']) is not list or len(value['binding']) != 3
                or type(value['binding'][0]) is not str or not 1 <= len(value['binding'][0]) <= 64
                or any(type(v) is not int for v in value['binding'][1:])
                or value['binding'] != [operator['agent_boot_id'], operator['microphone_epoch'],
                                        operator['motion_policy']['epoch']]
                or any(type(value[k]) is not int or not 0 <= value[k] < 2**63
                       for k in ('source_generation', 'seq', 'mask_generation', 'read_call', 'vad'))
                or value['seq'] == 0 or value['read_call'] == 0
                or value['source_generation'] != pcm['source_generation']
                or value['read_call'] > pcm['read_calls']
                or type(status['capture_pcm'].get('mask_generation')) is not int
                or value['mask_generation'] != status['capture_pcm'].get('mask_generation')
                or status['capture_pcm'].get('output_suppressed') is not False
                or pcm['gap_events'] or pcm['overflow_events']
                or value['mask'] != 'clear' or value['clock'] != 'monotonic_read_receipt'
                or value['capture_age_upper_ms'] is not None or value['reaction_usable'] is not False
                or not number(value['read_begin'], 0, 1e15)
                or not number(value['read_end'], 0, 1e15)
                or not 0 <= value['read_end']-value['read_begin'] <= 1
                or not number(value['read_age_s'], 0, .3) or value['read_age_s'] >= .3
                or not number(value['window_ms'], .001, 1000)
                or not number(value['rms'], 0, 32768) or type(value['loud']) is not bool
                or (value['delta'] is not None and not number(value['delta'], -32768, 32768))
                or (value['onset'] is not None and type(value['onset']) is not bool)
                or value['vad'] > 1000):
            return None
        clean = {k: copy.deepcopy(v) for k, v in value.items() if k != 'read_age_s'}
        # This deadline uses only local BEGIN + remote measured receipt age.
        # It is deliberately conservative and never describes acoustic age.
        expires = began + .3-value['read_age_s']
        old = self.acoustic_watermark
        if old:
            previous, previous_expires = old
            if (clean['binding'] != previous['binding']
                    or clean['source_generation'] != previous['source_generation']
                    or any(clean[k] < previous[k] for k in ('seq', 'mask_generation', 'read_end', 'read_call'))):
                return None
            if clean['seq'] == previous['seq']:
                if clean != previous: return None
                expires = min(expires, previous_expires)  # A poll cannot re-age a window.
        self.acoustic_watermark = (clean, expires)
        if self.closed or self.withdrawn:
            self.clear_acoustic()
            return None
        if self.clock() >= expires: return None
        return dict(clean, receipt_expires=expires)

    def revoke(self, reason):
        if self.withdrawn is None: self.withdrawn = reason
        self.clear_acoustic()

    def clear_acoustic(self):
        self.acoustic_watermark = None
        if self.latest is not None: self.latest.pop('acoustic', None)

    def unavailable_since(self, reason, now):
        if self.withdrawn or self.unavailable: return
        self.unavailable = True
        self.clear_acoustic()
        self.generation += 1
        self.physical_closed_after_gap = True
        self.gap_count += 1
        self.gaps.append(dict(start=now, end=None, reason=reason, generation=self.generation))

    def fresh(self, now):
        return bool(not self.closed and not self.withdrawn and not self.unavailable
                    and self.latest and now-self.latest['received'] < .3)

    def observation_report(self, now):
        gaps = [dict(gap, duration_s=max(0, (gap['end'] if gap['end'] is not None else now)-gap['start']))
                for gap in self.gaps]
        return dict(state='TERMINAL_REVOKED' if self.withdrawn else 'CLOSED' if self.closed else
                    'FRESH' if self.fresh(now) else 'OBSERVATION_UNAVAILABLE' if self.unavailable else 'OBSERVING',
                    generation=self.generation, gaps=gaps, gap_count=self.gap_count,
                    gap_history_cap=self.gaps.maxlen, gaps_omitted=self.gap_count-len(gaps),
                    unavailable_s=self.completed_unavailable_s + (
                        max(0, now-self.gaps[-1]['start']) if self.unavailable else 0),
                    recoveries=self.recoveries, read_failures=self.read_failures, late_receipts=self.late_receipts,
                    last_receipt_age_s=None if not self.latest else max(0, now-self.latest['received']),
                    unavailable=self.unavailable, current_phase=self.latest['phase'] if self.fresh(now) else 'UNKNOWN',
                    physical_closed_after_gap=self.physical_closed_after_gap)

    def check_operator(self, operator):
        if (identity(operator) != self.expected or not operator['listening']
                or not operator['capture_active'] or operator['phase'] in ('paused', 'stopped', 'error')):
            raise ValueError('Native authority/listening withdrawn; no reconnect')

    def check_counters(self, receipt):
        if self.latest:
            old, new = self.latest['pcm'], receipt['pcm']
            # A1 same-epoch pause/manual retires the pump and changes generation.
            # Never use a replacement source as continuity evidence.
            if (new['source_generation'] != old['source_generation']
                    or receipt['turns'] < self.latest['turns']
                    or any(new[k] < old[k] for k in old if k != 'source_generation')):
                raise ValueError('Native source changed/counter regression')

    def read(self):
        try:
            return self._read()
        except Exception as exc:
            # Worker may see revoke evidence before a later network failure;
            # publish it immediately, never mask it with a transient timeout.
            if not transient_read(exc): self.revoke(type(exc).__name__)
            raise

    def _read(self):
        began = self.clock()
        before = self.agent.get('/operator')
        self.check_operator(before)
        status = self.agent.get('/status')
        # /status has extra telemetry and omits some /operator fields. Validate
        # every authority field it does carry, including exact scalar types.
        self.check_operator({key: status.get(key, value) for key, value in before.items()})
        if (status.get('agent_boot_id') != before['agent_boot_id']
                or status.get('microphone_epoch') != before['microphone_epoch']
                or status.get('motion_policy') != before['motion_policy']
                or status.get('microphone_enabled') is not True
                or status.get('capture_active') is not True or status.get('listening') is not True
                or status.get('microphone_state_error', 'missing') is not None
                or status.get('phase') not in ('listening', 'recording', 'processing', 'speaking', 'waiting_to_resume')
                or type(status.get('turns')) is not int or not 0 <= status['turns'] < 2**63):
            raise ValueError('Typed native status required')
        pcm = status.get('capture_pcm')
        keys = ('source_generation', 'read_bytes', 'read_frames', 'read_calls', 'gap_events', 'overflow_events')
        if (type(pcm) is not dict or any(type(pcm.get(k)) is not int or not 0 <= pcm[k] < 2**63 for k in keys)
                or pcm.get('retired') is not False or pcm.get('clock') != 'monotonic_read_receipt'
                or pcm['read_frames'] != pcm['read_bytes'] // 2):
            raise ValueError('A1 actual PCM counters required')
        # Return a bounded metadata projection; never retain last_transcript.
        receipt = dict(operator=before, pcm={k: pcm[k] for k in keys}, phase=status['phase'],
                    capture_active=status['capture_active'], turns=status['turns'], received=began)
        receipt['acoustic'] = self.read_acoustic(status, before, receipt['pcm'], began)
        self.check_counters(receipt)
        after = self.hub.get('/control/operator')
        self.check_operator(after)
        receipt['operator'] = after
        if self.clock() - began >= .3: raise NativeReadExpired('Native status expired')
        return receipt

    def advance(self):
        now = self.clock()
        if self.closed: return
        if self.latest and now-self.latest['received'] >= .3:
            self.unavailable_since('native_status_expired', self.latest['received']+.3)
        if self.poll_job and self.poll_job.future.done():
            try:
                receipt = self.poll_job.future.result()
                self.check_operator(receipt['operator'])
                self.check_counters(receipt)
                if now - receipt['received'] >= .3: raise NativeReadExpired('Late native status')
                if self.withdrawn: return
                self.latest = receipt
                if self.unavailable:
                    self.gaps[-1]['end'] = now
                    self.completed_unavailable_s += max(0, now-self.gaps[-1]['start'])
                    self.unavailable = False
                    self.recoveries += 1
                if receipt['phase'] in ('processing', 'speaking', 'waiting_to_resume'):
                    if self.voice_busy_since is None: self.voice_busy_since = receipt['received']
                else: self.voice_busy_since = None
            except Exception as exc:
                if transient_read(exc):
                    if isinstance(exc, NativeReadExpired): self.late_receipts += 1
                    else: self.read_failures += 1
                    self.unavailable_since(type(exc).__name__, now)
                else: self.revoke(type(exc).__name__)
            self.poll_job = None
        if self.stock_job and self.stock_job.future.done():
            try:
                self.stock_receipt = self.stock_job.future.result()
            except Exception as exc:
                # A failed POST is never retried or called a completed effect.
                self.stock_unknown = True
                self.stock_receipt = dict(completion='UNKNOWN', error_class=type(exc).__name__)
                self.revoke('stock_outcome_UNKNOWN')
            self.stock_job = None
        if not self.withdrawn and not self.poll_job and now >= self.next_poll:
            self.poll_job = Job(self.read)
            self.polls += 1
            self.next_poll = now + .1

    def stock_allowed(self, now):
        return bool(self.allow_stock and self.fresh(now) and not self.stock_used
            and not self.physical_closed_after_gap
            and self.latest['operator']['motion_policy']['motor_enabled'])

    def dispatch(self, proposal):
        if not self.stock_allowed(self.clock()) or not self.admit_stock(proposal): return False
        self.stock_used = True  # reserve before starting; no lost-response retry
        self.stock_job = Job(self.execute_stock, proposal)
        return True

    def admit_stock(self, proposal):
        now = self.clock()
        return bool(self.allow_stock and self.fresh(now) and not self.physical_closed_after_gap
                    and proposal['generation'] == self.generation and now < proposal['deadline']
                    and proposal['operator'] == self.latest['operator']
                    and identity(self.latest['operator']) == self.expected)

    def execute_stock(self, proposal):
        hardware = self.hub.get('/status')
        stock = hardware.get('stock_motion', {})
        boot = stock.get('hub_boot_id')
        if (not isinstance(boot, str) or not boot or stock.get('selected') is not True
                or stock.get('unknown') is not False or stock.get('owned_uuid') is not None
                or hardware.get('action_running') is not False
                or hardware.get('ownership', {}).get('state') != 'free'):
            raise ValueError('Free existing Hub stock owner required')
        if self.hub_boot is not None and boot != self.hub_boot: raise ValueError('Hub restarted')
        current = self.hub.get('/control/operator')
        try: self.check_operator(current)
        except Exception as exc:
            self.revoke(type(exc).__name__)
            raise
        if current != proposal['operator'] or not self.admit_stock(proposal):
            return dict(completion='not_dispatched', reason='grant_revoked')
        return self.send_settle(proposal, current, boot)

    def send_settle(self, proposal, current, boot, *, motor_only=False):
        # Fixed stock settle: one degree roll, then neutral, two slow steps.
        # No actor daemon, factory client or motor owner is created here.
        steps = [dict(head_pose=dict(x=0, y=0, z=0, roll=roll, pitch=0, yaw=0),
                      antennas=[0, 0], duration=.5, interpolation='minjerk') for roll in (math.radians(1), 0)]
        binding = dict(agent_boot_id=current['agent_boot_id'], microphone_epoch=current['microphone_epoch'],
            microphone_enabled=current['microphone_enabled'], policy_epoch=current['motion_policy']['epoch'],
            expression_version=current['expression_version'])
        try:
            extra = dict(motor_only=True, operator_check=self.check_operator) if motor_only else {}
            result = guarded_control(self.companion_config, self.hub.url, '/actions/expression',
                dict(steps=steps, operator_binding=binding), current, deadline=proposal['deadline'], response_timeout=3,
                admission=lambda: self.admit_stock(proposal), **extra)
        except StockNotSent:
            return dict(completion='not_dispatched', reason='pre_send_closed')
        if (result.get('ok') is not True or result.get('steps_observed') != 2
                or result.get('pose_verified') is not False or result.get('hard_stop_certified') is not False):
            raise ValueError('Hub stock completion UNKNOWN')
        return dict(completion='observed', steps_observed=2, pose_verified=False, hard_stop_certified=False,
                    request_id=proposal['request_id'], hub_boot_id=boot)

    def close(self):
        self.closed = True  # only local admission; normal Agent keeps listening
        self.clear_acoustic()

    def busy(self):
        return dict(native_poll=bool(self.poll_job and not self.poll_job.future.done()),
                    stock=bool(self.stock_job and not self.stock_job.future.done()))


class GoalClockNativeAgent(NativeAgent):
    """Explicit finite R12 arm. PCM is an optional, discontinuous sensor only."""
    def __init__(self, agent, hub, companion_config, expected, hub_boot, *, allow_stock=False,
                 goal, goal_ttl_s, clock=time.monotonic):
        validate('Goal', goal)
        if (allow_stock is not True or goal['origin'] != 'operator' or not goal['text'].strip()
                or goal['evidence_ids'] or type(goal['version']) is not int or not 0 <= goal['version'] < 2**63
                or type(goal_ttl_s) not in (int, float)
                or not math.isfinite(goal_ttl_s) or not 1 <= goal_ttl_s <= 180):
            raise ValueError('Explicit finite stock arm and independent operator goal/expiry required')
        # Base observer requires Mic ON; this arm deliberately permits initial
        # Mic OFF, but pins that durable state exactly for its whole lifetime.
        super().__init__(agent, hub, companion_config, expected, hub_boot,
                         allow_stock=allow_stock, clock=clock, _motor_scope=True)
        self.expected = motor_identity(expected)
        self.check_operator(expected)
        self.arm_id = uid()
        self.goal = copy.deepcopy(goal)
        self.goal_source = lambda: goal
        self.goal_expires = clock() + goal_ttl_s
        self.stop_requested = lambda: False
        self.sensor_watermark = None
        self.sensor_present = None
        self.sensor_turns = None
        # This profile never establishes continuous PCM, even at initial arm.
        self.sensor_continuous = False
        self.motor_unavailable = True

    def check_operator(self, operator):
        try:
            if (motor_identity(operator) != self.expected
                    or operator['motion_policy']['motor_enabled'] is not True
                    or operator['microphone_epoch'] == 2**63-1
                    or operator['motion_policy']['epoch'] == 2**63-1
                    or operator['phase'] in ('error', 'stopped')):
                raise ValueError('Motor authority withdrawn; explicit new arm required')
        except Exception:
            self.revoke('motor_authority_withdrawn')
            raise

    def grant_current(self, now):
        if self.closed or self.withdrawn: return False
        if self.stop_requested(): self.revoke('explicit_disable')
        if self.goal_source() != self.goal: self.revoke('operator_goal_changed')
        return bool(not self.closed and not self.withdrawn and now < self.goal_expires)

    def fresh(self, now):
        return bool(self.grant_current(now) and not self.motor_unavailable and self.latest
                    and now < self.latest['received'] + .3)

    def read_motor_receipt(self, *, poll=False):
        began = self.clock()
        try:
            hardware = self.hub.get('/status')
            stock = hardware.get('stock_motion', {})
            # Check known negative evidence BEFORE any subsequent read can time out.
            if (stock.get('hub_boot_id') != self.hub_boot or stock.get('selected') is not True
                    or stock.get('unknown') is not False
                    or 'owned_uuid' not in stock
                    or (stock['owned_uuid'] is not None and
                        (type(stock['owned_uuid']) is not str or not 1 <= len(stock['owned_uuid']) <= 256))
                    or type(hardware.get('action_running')) is not bool
                    or hardware.get('ownership', {}).get('state') != 'free'
                    or hardware.get('daemon', {}).get('state') != 'running'
                    or hardware.get('daemon', {}).get('error')
                    or hardware.get('daemon', {}).get('backend_status', {}).get('ready') is not True
                    or hardware.get('daemon', {}).get('backend_status', {}).get('error')
                    or hardware.get('robot', {}).get('control_mode') != 'enabled'):
                raise ValueError('Known free existing Hub stock owner/readiness required')
            busy = stock['owned_uuid'] is not None or hardware['action_running']
            pending = poll and self.stock_job and not self.stock_job.future.done()
            if busy and not pending: raise ValueError('Free idle Hub required')
            current = self.hub.get('/control/operator')
            self.check_operator(current)
            if busy:
                # Our reserved effect may own this busy state. No fresh
                # receipt/admission is issued; retain its actual job until
                # completion/reconciliation rather than guessing ownership.
                raise NativeReadExpired('Reserved stock effect pending; motor admission unavailable')
            if self.clock() >= began + .3: raise NativeReadExpired('Motor receipt expired from BEGIN')
            return dict(operator=current, received=began, begin_monotonic=began, hub_boot_id=self.hub_boot,
                        phase='UNKNOWN', capture_active=None, turns=None, pcm=None)
        except Exception as exc:
            self.motor_unavailable = True
            if not transient_read(exc): self.revoke('motor_control_' + type(exc).__name__)
            raise

    def read(self):
        receipt = self.read_motor_receipt(poll=True)
        try:
            status = self.agent.get('/status')
            self.check_operator({k: status.get(k, v) for k, v in receipt['operator'].items()})
            if status.get('microphone_state_error', 'missing') is not None:
                raise ValueError('Native durable microphone state UNKNOWN')
            pcm = status.get('capture_pcm')
            keys = ('source_generation', 'read_bytes', 'read_frames', 'read_calls', 'gap_events', 'overflow_events')
            if (status.get('listening') is True and status.get('capture_active') is True
                    and status.get('phase') in ('listening', 'recording', 'processing', 'speaking', 'waiting_to_resume')
                    and type(status.get('turns')) is int and 0 <= status['turns'] < 2**63
                    and type(pcm) is dict and pcm.get('retired') is False
                    and pcm.get('clock') == 'monotonic_read_receipt'
                    and all(type(pcm.get(k)) is int and 0 <= pcm[k] < 2**63 for k in keys)
                    and pcm['read_frames'] == pcm['read_bytes'] // 2):
                receipt['pcm'] = {k: pcm[k] for k in keys}
                receipt['turns'] = status['turns']
        except Exception as exc:
            if not transient_read(exc):
                self.revoke('native_control_' + type(exc).__name__)
                raise
            # Sensor timeout does not revoke MOTOR; BEGIN age still bounds it.
        self.notice_sensor(receipt['pcm'], receipt['turns'], self.clock())
        try:
            # Final control check can cross a sensor retire/resume. Its motor
            # identity is valid; it is deliberately NOT PCM continuity proof.
            current = self.hub.get('/control/operator')
            self.check_operator(current)
            receipt['operator'] = current
        except Exception as exc:
            self.motor_unavailable = True
            if not transient_read(exc): self.revoke('motor_control_' + type(exc).__name__)
            raise
        return receipt

    def sensor_gap(self, reason, now, *, force=False):
        self.sensor_continuous = False
        if force and self.unavailable:
            self.generation += 1
            return
        self.unavailable_since(reason, now)

    def notice_sensor(self, pcm, turns, now):
        # The single poll worker publishes invalidation as soon as it sees a
        # discontinuity, including before a later control timeout/socket send.
        old = self.sensor_watermark or (self.latest and self.latest['pcm'])
        changed = bool(pcm and old and (pcm['source_generation'] != old['source_generation']
            or any(pcm[k] < old[k] for k in old if k != 'source_generation')
            or any(pcm[k] != old[k] for k in ('gap_events', 'overflow_events'))
            or (self.sensor_turns is not None and turns < self.sensor_turns)))
        if pcm is None or changed:
            lost = pcm is None and (self.sensor_present is True or (self.sensor_present is None and bool(old)))
            self.sensor_gap('audio_discontinuous_UNKNOWN', now, force=changed or lost)
        self.sensor_present = pcm is not None
        if pcm is not None: self.sensor_watermark = pcm
        if turns is not None: self.sensor_turns = turns

    def advance(self):
        now = self.clock()
        # A terminal arm never hides completion/UNKNOWN of its occupied effect.
        if self.stock_job and self.stock_job.future.done():
            try: self.stock_receipt = self.stock_job.future.result()
            except Exception as exc:
                self.stock_unknown = True
                self.stock_receipt = dict(completion='UNKNOWN', error_class=type(exc).__name__)
                self.revoke('stock_outcome_UNKNOWN')
            self.stock_job = None
        if not self.grant_current(now): return
        if self.latest and not self.motor_unavailable and now >= self.latest['received'] + .3:
            self.motor_unavailable = True
            self.sensor_gap('poll_receipt_expired', self.latest['received'] + .3)
        if self.poll_job and self.poll_job.future.done():
            try:
                receipt = self.poll_job.future.result()
                self.check_operator(receipt['operator'])
                if now >= receipt['received'] + .3: raise NativeReadExpired('Late motor receipt')
                # Never label a composite/replacement receipt continuous after a
                # gap. Its motor projection can still be current independently.
                self.latest = receipt
                self.motor_unavailable = False
            except Exception as exc:
                self.motor_unavailable = True
                if transient_read(exc):
                    if isinstance(exc, NativeReadExpired): self.late_receipts += 1
                    else: self.read_failures += 1
                    self.sensor_gap(type(exc).__name__, now)
                else: self.revoke('motor_control_' + type(exc).__name__)
            self.poll_job = None
        if self.grant_current(now) and not self.poll_job and now >= self.next_poll:
            self.poll_job = Job(self.read)
            self.polls += 1
            self.next_poll = now + .1

    def stock_allowed(self, now):
        return bool(self.allow_stock and self.fresh(now) and not self.stock_used)

    def admit_stock(self, proposal):
        now = self.clock()
        try:
            return bool(self.allow_stock and self.fresh(now)
                and proposal['basis'] == 'operator_goal_clock' and proposal['arm_id'] == self.arm_id
                and proposal['hub_boot_id'] == self.hub_boot == self.latest['hub_boot_id']
                and proposal['goal_version'] == (self.goal['id'], self.goal['version'])
                and proposal['generation'] == self.generation
                and now < proposal['deadline'] <= min(proposal['model_deadline'],
                    proposal['receipt_begin'] + .3, self.goal_expires)
                and motor_identity(proposal['operator']) == self.expected
                and motor_identity(self.latest['operator']) == self.expected
                and proposal['operator']['expression_version'] == self.latest['operator']['expression_version'])
        except (KeyError, TypeError, ValueError): return False

    def execute_stock(self, proposal):
        # This is an effect preflight in the reserved stock job, never a second
        # polling/replacement slot. It cannot extend the proposal's deadline.
        try: receipt = self.read_motor_receipt()
        except Exception:
            return dict(completion='not_dispatched', reason='motor_receipt_unavailable')
        current = receipt['operator']
        if (not self.admit_stock(proposal)
                or current['expression_version'] != proposal['operator']['expression_version']):
            return dict(completion='not_dispatched', reason='grant_revoked')
        return self.send_settle(proposal, current, receipt['hub_boot_id'], motor_only=True)

    def observation_report(self, now):
        report = super().observation_report(now)
        report.update(profile='finite_goal_clock', sensor_state='UNKNOWN',
                      pcm_continuity=self.sensor_continuous, motor_fresh=self.fresh(now),
                      goal_version=self.goal['version'], goal_expires_monotonic=self.goal_expires)
        if not self.closed and not self.withdrawn:
            report['state'] = 'MOTOR_FRESH_SENSOR_UNKNOWN' if self.fresh(now) else 'MOTOR_UNAVAILABLE_SENSOR_UNKNOWN'
        return report


@dataclass(frozen=True)
class GoalClockBinding(Binding):
    decision_generation: int
    motor_identity: tuple
    arm_id: str
    goal_version: tuple
    hub_boot_id: str


class NativeState(State):
    def __init__(self, compute_boot, config, native):
        super().__init__(compute_boot, config)
        self.native = native
        self.started = native.clock()
        self.native_signature = None
        self.stock_proposal = None
        self.request_generation = None

    def ingest(self, event, now):
        if event.get('type') in ('utterance', 'workflow'):
            raise ValueError('Normal Agent exclusively owns conversation/main')
        return super().ingest(event, now)

    def observe(self):
        if not self.native.fresh(self.native.clock()): return
        receipt = self.native.latest
        operator = receipt['operator']
        signature = (identity(operator), operator['expression_version'])
        if signature != self.native_signature:
            self.native_signature = signature
            self.authority = replace(self.authority, robot_boot_id=operator['agent_boot_id'],
                operator_epoch=self.authority.operator_epoch + 1, microphone_epoch=operator['microphone_epoch'])
            self.revision += 1
        self.muted = not operator['microphone_enabled']
        self.quiet = operator['motion_policy']['quiet']
        self.privacy = operator['motion_policy']['privacy_all']

    def snapshot(self, now):
        view = super().snapshot(now)
        receipt = self.native.latest
        if not receipt: raise ValueError('No native observation')
        view['scene'] = 'Existing normal Agent owns capture, STT, main and reply. Camera physical age remains unknown.'
        view['goal'] = copy.deepcopy(self.config.get('native_agent', {}).get('operator_goal'))
        view['principles'] = ('No scheduler main, speech or input candidates. motion=settle is one fixed Hub stock '
                              'profile (1 degree roll then neutral); only if motion_allowed. No attentive/native actor mapping.')
        # Physical capture age is UNKNOWN for the installed A1 reader. These
        # observations may inform passive choices, never invite a sensor effect.
        view['op']['motion_allowed'] = False
        view['dialogue'] = ''; view['candidates'] = []; view['ready'] = []
        fresh = self.native.fresh(now)
        busy = receipt['phase'] in ('processing', 'speaking', 'waiting_to_resume')
        if busy:
            view['pending'] = [dict(alias='native-voice', kind='native_voice',
                status='execution_busy_phase_observed_completion_UNKNOWN' if fresh else 'native_voice_current_UNKNOWN',
                age_ms=max(0, int((now-(self.native.voice_busy_since or receipt['received']))*1000)))]
        metadata = {'native.elapsed': dict(elapsed_ms=max(0, int((now-self.started)*1000))),
                    'native.pcm': receipt['pcm'],
                    'native.voice': dict(phase=receipt['phase'] if fresh else 'UNKNOWN', busy=busy if fresh else None,
                                         turns=receipt['turns'], capture_active=receipt['capture_active'] if fresh else None,
                                         main_stage='UNKNOWN')}
        view['sensors'] = view['sensors'][:6]
        for name, value in metadata.items():
            summary = json.dumps(value, separators=(',', ':'))
            if len(summary) > 256: raise ValueError('Native metadata cap')
            view['sensors'].append(dict(id=name, state='ready' if fresh or name == 'native.elapsed' else 'stale',
                age_ms=0 if name == 'native.elapsed' else max(0, int((now-receipt['received'])*1000)), summary=summary))
        acoustic = receipt.get('acoustic')
        if not fresh or not acoustic or now >= acoustic['receipt_expires']:
            view['sensors'].append(dict(id='native.acoustic', state='UNKNOWN', age_ms=None, summary=''))
        else:
            # Three bounded fields share seq. Age remains explicitly read-only;
            # no raw PCM, transcript, direction, identity or music inference.
            seq = acoustic['seq']
            groups = {
                'native.acoustic': {k: acoustic[k] for k in
                    ('seq', 'rms', 'delta', 'onset', 'vad', 'loud', 'window_ms')},
                'native.acoustic.binding': dict(seq=seq, boot=acoustic['binding'][0],
                    mic=acoustic['binding'][1], policy=acoustic['binding'][2],
                    source=acoustic['source_generation'], mask=acoustic['mask_generation'],
                    read_call=acoustic['read_call']),
                'native.acoustic.receipt': dict(seq=seq, read_begin=acoustic['read_begin'],
                    read_end=acoustic['read_end'], clock=acoustic['clock'],
                    read_age_upper_ms=math.ceil(max(0, .3-(acoustic['receipt_expires']-now))*1000),
                    mask=acoustic['mask'], capture_age_upper_ms=None, reaction='UNKNOWN')}
            encoded = {key: json.dumps(value, separators=(',', ':')) for key, value in groups.items()}
            if any(len(value) > 256 for value in encoded.values()):
                view['sensors'].append(dict(id='native.acoustic', state='UNKNOWN', age_ms=None, summary=''))
            else:
                view['sensors'].extend(dict(id=key, state='read_receipt_only', age_ms=None, summary=value)
                                       for key, value in encoded.items())
        return validate('FastView', view)

    def bind(self, now, timeout):
        binding = super().bind(now, timeout)
        self.request_generation = (binding.request_id, self.native.generation)
        return binding

    def apply(self, choice, binding, now):
        if (not self.native.fresh(now)
                or self.request_generation != (binding.request_id, self.native.generation)):
            self.record('native_decision_discarded', request_id=binding.request_id); return None
        validate('FastChoice', choice)
        if choice.get('start') or choice.get('commit') or choice.get('say'):
            self.record('native_conversation_owner_rejected'); return None
        motion = choice.get('motion')
        if motion and not isinstance(self.native, GoalClockNativeAgent):
            self.record('native_acoustic_reaction_UNKNOWN'); return None
        if motion and (motion != 'settle' or not self.native.stock_allowed(now)):
            self.record('native_stock_rejected'); return None
        before = self.counts['decision_accepted']
        super().apply({**choice, 'motion': None}, binding, now)
        if motion and self.counts['decision_accepted'] > before:
            self.stock_proposal = self.make_stock_proposal(binding)
        return None

    def make_stock_proposal(self, binding):
        receipt = self.native.latest
        return dict(request_id=binding.request_id,
            operator=copy.deepcopy(receipt['operator']), generation=self.native.generation,
            deadline=min(binding.deadline, receipt['received']+.3))


class GoalClockState(NativeState):
    def ingest(self, event, now):
        if event.get('type') == 'operator':
            # Every explicit disable/operator transition terminates this arm;
            # a later enable never binds it to a new grant.
            self.native.revoke('explicit_disable')
            self.stock_proposal = None
            return
        raise ValueError('Finite goal/clock profile accepts no sensor/content events')

    def snapshot(self, now):
        view = State.snapshot(self, now)
        view.update(scene='Finite initial stock settle from explicit operator goal and clock only. Sensors UNKNOWN.',
            goal=copy.deepcopy(self.native.goal), dialogue='', memory=[], prev=[], pending=[], ready=[],
            candidates=[], evidence_aliases=[],
            principles='Only operator goal/clock may select one fixed settle: roll 1 degree then neutral, '
                       '0.5s each. No audio, voice, context or camera evidence. Sensors UNKNOWN.')
        view['op']['motion_allowed'] = self.native.stock_allowed(now)
        view['sensors'] = [dict(id='native.clock', state='ready', age_ms=0, summary=json.dumps(dict(
            elapsed_ms=max(0, int((now-self.started)*1000)), goal_version=self.native.goal['version'],
            goal_remaining_ms=max(0, int((self.native.goal_expires-now)*1000))))),
            dict(id='native.audio', state='no_data', age_ms=None, summary='')]
        return validate('FastView', view)

    def bind(self, now, timeout):
        binding = super().bind(now, timeout)
        return GoalClockBinding(**vars(binding), decision_generation=self.native.generation,
            motor_identity=self.native.expected, arm_id=self.native.arm_id,
            goal_version=(self.native.goal['id'], self.native.goal['version']), hub_boot_id=self.native.hub_boot)

    def apply(self, choice, binding, now):
        self.stock_proposal = None
        if (not isinstance(binding, GoalClockBinding) or not self.native.fresh(now)
                or binding.arm_id != self.native.arm_id or binding.motor_identity != self.native.expected
                or binding.hub_boot_id != self.native.hub_boot
                or binding.goal_version != (self.native.goal['id'], self.native.goal['version'])
                or binding.decision_generation != self.native.generation):
            self.record('native_decision_discarded', request_id=binding.request_id)
            return None
        # A model-supplied basis is a schema error. Never copy a newer sensor
        # generation onto an older in-flight result during a concurrent poll.
        result = super().apply(choice, binding, now)
        if binding.decision_generation != self.native.generation:
            self.stock_proposal = None
            self.record('native_decision_discarded', request_id=binding.request_id)
        return result

    def make_stock_proposal(self, binding):
        receipt = self.native.latest
        return dict(request_id=binding.request_id, operator=copy.deepcopy(receipt['operator']),
            generation=binding.decision_generation, basis='operator_goal_clock', arm_id=binding.arm_id,
            hub_boot_id=binding.hub_boot_id,
            goal_version=binding.goal_version, model_deadline=binding.deadline, receipt_begin=receipt['received'],
            deadline=min(binding.deadline, receipt['received']+.3, self.native.goal_expires))


class NativeScheduler(Scheduler):
    def __init__(self, config, gateway, native):
        if config.get('native_agent', {}).get('enabled') is not True:
            raise ValueError('Matching native_agent gateway/session profile required')
        if config.get('speech', {}).get('enabled') or config.get('motion', {}).get('enabled') or config.get('workflows', {}).get('enabled'):
            raise ValueError('Native session forbids additional speech/motor/workflow owners')
        goal_clock = isinstance(native, GoalClockNativeAgent)
        if goal_clock != (config.get('native_agent', {}).get('stock_profile') == 'finite_goal_clock'):
            raise ValueError('Matching explicit finite goal/clock profile required')
        if goal_clock and config.get('context', {}).get('enabled'):
            raise ValueError('Finite goal/clock profile forbids context/camera')
        if goal_clock:
            native.goal_source = lambda: config['native_agent'].get('operator_goal')
        super().__init__(config, gateway)  # no AudioAdapter, SpeechAdapter or MotionAdapter
        self.native = native
        self.state = (GoalClockState if goal_clock else NativeState)(gateway.boot_id, config, native)
        self.observation_generation = native.generation
        self.context_closed_after_gap = False

    def advance(self, now=None):
        if self.closed: return
        now = self.native.clock() if now is None else now
        self.native.advance()
        if self.native.withdrawn:
            self.close(); return
        if self.observation_generation != self.native.generation:
            if self.fast_job and self.state.request_generation == (self.binding.request_id, self.observation_generation):
                self.state.record('native_decision_invalidated', request_id=self.binding.request_id)
            self.observation_generation = self.native.generation
            self.state.stock_proposal = None
            # Revoke the actual context scope; never mint a new epoch/grant to
            # bypass its floor. Privacy-sensitive context stays closed for this
            # session, even when metadata decisions recover.
            self.context_closed_after_gap = True
            self.next_context = math.inf
            self.state.context_sensors = []
            self.revoke_context(self.state.authority)
            self.state.record('native_observation_gap')
        if self.context_closed_after_gap and self.context_job and self.context_job.future.done():
            try: self.context_job.future.result()
            except Exception: pass
            self.state.record('native_context_discarded')
            self.context_job = self.context_binding = None
        if not self.native.fresh(now):
            if now >= self.next_tick:
                self.next_tick = now+self.config['period_s']
                self.state.record('native_tick_unavailable_gap')
            # Keep actual fast/context/poll slots, including their bindings.
            # No calls to the generic scheduler can create grants/requests here.
            return
        if not self.native.latest: return
        self.state.observe()
        super().advance(now)
        if self.main_job: raise RuntimeError('Native conversation ownership violation')
        if self.state.stock_proposal:
            proposal = self.state.stock_proposal
            self.state.stock_proposal = None
            if not self.native.dispatch(proposal): self.state.record('native_stock_rejected')

    def close(self):
        self.native.close()
        super().close()
