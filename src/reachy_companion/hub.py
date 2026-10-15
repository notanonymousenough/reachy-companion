#!/usr/bin/env python3
"""Small Reachy Mini scenario router; Python standard library only."""
import hmac
import json
import logging
import math
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

LOG = logging.getLogger("reachy-hub")


def reconciliation_error_class(exc):
    """Fixed wire diagnostics; never serialize exception messages or types."""
    if isinstance(exc,ImportError):return 'module_missing'
    if isinstance(exc,HTTPError):return 'http_error'
    if isinstance(exc,TimeoutError):return 'timeout'
    if isinstance(exc,(ValueError,KeyError,TypeError)):return 'validation'
    return 'state_denied'


def decode_reconciliation_json(data):
    """Strict stdlib-only JSON for the independently deployed production Hub."""
    def reject(value):raise ValueError('Non-finite reconciliation JSON')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate reconciliation JSON key')
            result[key]=value
        return result
    return json.loads(data,parse_constant=reject,object_pairs_hook=unique)


class Hub:
    def __init__(self, config):
        self.config = config
        self.http = build_opener(ProxyHandler({}))
        self.lock = threading.Lock()
        self.boot_id = str(uuid.uuid4())
        self.stock_scope=threading.local();self.stock_unknown=False;self.stock_owned=None;self.stock_stop_observed=None
        self.stock_stop_request=None

    def stock_selected(self):
        return self.config['guarded_motion'].get('transport','native')=='stock'

    def stock_operator(self):
        if not self.config['guarded_motion']['enabled'] or self.stock_unknown:raise RuntimeError('Stock motion disabled or completion unknown')
        began=time.monotonic();value=self.agent('/operator')
        if type(value) is not dict or time.monotonic()-began>.3:raise RuntimeError('Fresh stock operator required')
        policy=value.get('motion_policy')
        if (type(policy) is not dict or type(value.get('agent_boot_id')) is not str or not 1<=len(value['agent_boot_id'])<=256
                or any(type(epoch) is not int or not 0<=epoch<2**63 for epoch in (value.get('microphone_epoch'),policy.get('epoch')))
                or type(value.get('microphone_enabled')) is not bool
                or 'microphone_state_error' not in value or value['microphone_state_error'] is not None
                or policy.get('motor_enabled') is not True or policy.get('quiet') is not False or policy.get('privacy_all') is not False):
            raise RuntimeError('Current typed operator motor permission required')
        expression_version=getattr(self.stock_scope,'expression_version',None)
        if expression_version is not None and (type(value.get('expression_version')) is not int
                or value['expression_version']!=expression_version):
            raise RuntimeError('Stock command binding changed: expression_version')
        return value['agent_boot_id'],value['microphone_epoch'],policy['epoch'],value['microphone_enabled']

    def stock_begin(self):
        if self.stock_selected():
            self.stock_scope.expression_version=None
            self.stock_scope.binding=self.stock_operator()
            self.stock_scope.observed=0

    def stock_end(self):
        self.stock_scope.binding=None
        self.stock_scope.expression_version=None

    def stock_check(self):
        binding=getattr(self.stock_scope,'binding',None)
        if binding is None:raise RuntimeError('Stock command binding changed: missing_binding')
        self.stock_compare(binding,self.stock_operator())

    @staticmethod
    def stock_compare(expected,current):
        fields=('boot','mic_epoch','policy_epoch','mic_enabled')
        changed=[name for name,old,new in zip(fields,expected,current) if old!=new]
        if changed:raise RuntimeError('Stock command binding changed: '+','.join(changed))

    @staticmethod
    def move_uuid(value):
        if type(value) is not str or str(uuid.UUID(value))!=value:raise ValueError('Canonical factory move UUID required')
        return value

    def stock_dependencies(self):
        daemon=self.factory('/api/daemon/status');owner=self.factory('/api/daemon/robot-app-lock-status')
        active=self.factory('/api/move/running')
        if (type(daemon) is not dict or daemon.get('state')!='running' or daemon.get('error')
                or type(daemon.get('backend_status')) is not dict or daemon['backend_status'].get('ready') is not True
                or daemon['backend_status'].get('error') or type(owner) is not dict or owner.get('state')!='free'
                or type(active) is not list):raise RuntimeError('Stock factory readiness/ownership unknown')
        ids=[self.move_uuid(item['uuid']) for item in active]
        if any(value!=self.stock_owned for value in ids):raise RuntimeError('Foreign factory movement active')
        return ids

    def stock_stop_owned(self,task_id):
        self.move_uuid(task_id)
        if task_id!=self.stock_owned:raise RuntimeError('Only this lane owned UUID may be stopped')
        request_failed=False
        self.stock_stop_observed=False
        self.stock_stop_request=None
        # The stock daemon's stop is non-idempotent for completed UUIDs.
        # Only a fresh ready/free/empty observation may avoid that POST.
        began=time.monotonic()
        try:absent=not self.stock_dependencies() and time.monotonic()-began<=.3
        except Exception:absent=False
        if absent:
            self.stock_stop_observed=True
            if self.stock_unknown:raise RuntimeError('UUID absence observed; explicit reconciliation required')
            self.stock_owned=None;return
        self.stock_stop_request=dict(endpoint='/api/move/stop',error_class=None,http_status=None)
        try:
            self.factory('/api/move/stop',{'uuid':task_id}) # independent of withdrawn operator permission
        except BaseException as exc:
            request_failed=True;self.stock_unknown=True
            error_class=('HTTPError' if isinstance(exc,HTTPError) else 'TimeoutError' if isinstance(exc,TimeoutError)
                         else 'TransportError' if isinstance(exc,OSError) else 'ResponseError')
            status=exc.code if isinstance(exc,HTTPError) and type(exc.code) is int and 100<=exc.code<=599 else None
            self.stock_stop_request.update(error_class=error_class,http_status=status)
        try:
            deadline=time.monotonic()+min(2,self.config['timeouts']['move'])
            while time.monotonic()<deadline:
                active=self.factory('/api/move/running')
                if type(active) is not list:raise RuntimeError('Stock running observation unknown')
                ids=[self.move_uuid(item['uuid']) for item in active]
                if task_id not in ids:
                    self.stock_stop_observed=True
                    if request_failed:
                        # Observation is useful but cannot silently recover an
                        # unknown request. Retain exact UUID for explicit audit.
                        raise RuntimeError('Stock stop request failed; UUID absence observed; explicit reconciliation required')
                    self.stock_owned=None;return
                time.sleep(self.config['motion']['move_poll_seconds'])
            raise TimeoutError('Owned stock stop not observed')
        except BaseException:
            self.stock_unknown=True
            if not request_failed or self.stock_stop_observed is not True:self.stock_stop_observed=False
            raise

    def stock_reconcile(self,payload,*,diagnostic=None):
        """Explicit read-only reconciliation; never acquires permission or retries output."""
        def phase(value):
            if diagnostic is not None:diagnostic['phase']=value
        phase('admission')
        if (type(payload) is not dict or set(payload)!={'expected_hub_boot_id','owned_uuid','operator_binding'}
                or type(payload['expected_hub_boot_id']) is not str or payload['expected_hub_boot_id']!=self.boot_id):
            raise ValueError('Current Hub reconciliation binding required')
        task_id=self.move_uuid(payload['owned_uuid'])
        expected=payload['operator_binding']
        if (type(expected) is not dict or set(expected)!={'agent_boot_id','microphone_epoch','policy_epoch','microphone_enabled'}
                or type(expected.get('agent_boot_id')) is not str or not 1<=len(expected['agent_boot_id'])<=256
                or any(type(expected.get(k)) is not int or not 0<=expected[k]<2**63 for k in ('microphone_epoch','policy_epoch'))
                or type(expected.get('microphone_enabled')) is not bool):
            raise ValueError('Typed original reconciliation operator required')
        expected_tuple=(expected['agent_boot_id'],expected['microphone_epoch'],expected['policy_epoch'],expected['microphone_enabled'])
        if not self.lock.acquire(False):raise RuntimeError('Hub is busy')
        try:
            if not self.stock_selected() or not self.stock_unknown or self.stock_owned!=task_id:
                raise RuntimeError('Exact known owned unknown movement required')
            def operator():
                began=time.monotonic();value=self.agent('/operator')
                policy=value.get('motion_policy') if type(value) is dict else None
                if (time.monotonic()-began>.3 or type(policy) is not dict
                        or type(value.get('agent_boot_id')) is not str
                        or any(type(v) is not int or not 0<=v<2**63 for v in (value.get('microphone_epoch'),policy.get('epoch')))
                        or type(value.get('microphone_enabled')) is not bool
                        or 'microphone_state_error' not in value or value['microphone_state_error'] is not None
                        or policy.get('motor_enabled') is not False
                        or any(type(policy.get(k)) is not bool for k in ('quiet','privacy_all'))):
                    raise RuntimeError('Fresh operator with motors denied required for reconciliation')
                return value['agent_boot_id'],value['microphone_epoch'],policy['epoch'],value['microphone_enabled']
            began=time.monotonic()
            phase('operator_before')
            self.stock_compare(expected_tuple,operator())
            phase('factory_deps')
            if self.stock_dependencies():raise RuntimeError('Factory movement still active')
            phase('state')
            state=self.factory('/api/state/full')
            if type(state) is not dict or state.get('control_mode') not in ('enabled','disabled'):
                raise RuntimeError('Factory actual state unknown')
            phase('operator_after')
            self.stock_compare(expected_tuple,operator())
            phase('window')
            if time.monotonic()-began>.3:raise RuntimeError('Reconciliation observation window expired')
            self.stock_owned=None;self.stock_unknown=False;self.stock_stop_observed=True
            return dict(reconciled=True,uuid_absence_observed=True,factory_ready=True,
                operator_motor_enabled=False,pose_verified=False,hard_stop_certified=False)
        finally:self.lock.release()

    def factory(self,path,payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(self.config['network']['robot_url'] + path, data=data,
                          headers={'Content-Type': 'application/json'})
        with self.http.open(request, timeout=self.config['timeouts']['robot']) as response:
            return json.load(response)

    def robot(self, path, payload=None):
        if payload is not None and self.stock_selected():
            if path not in ('/api/move/goto','/api/move/play/wake_up','/api/move/play/goto_sleep','/api/motors/set_mode/enabled'):
                raise ValueError('Stock mutation is not in the explicit motion route')
            self.stock_check();self.stock_dependencies();self.stock_check()
            if path=='/api/move/goto':
                # The REST schema's null means leave an axis unchanged. Never
                # inherit an SDK default body yaw of zero for an antenna gesture.
                payload=dict(payload,body_yaw=None)
                payload.setdefault('head_pose',None)
            try:return self.factory(path,payload)
            except BaseException:self.stock_unknown=True;raise
        if payload is not None and self.config['guarded_motion']['enabled']:
            # Includes legacy expressions, wake/sleep and timeout stop calls.
            # No REST fallback: an absent/unready robot-local actor withdraws.
            command_id = str(uuid.uuid4())
            envelope = {'command_id': command_id, 'hub_boot_id': self.boot_id,
                        'path': path, 'payload': payload}
            result = self.agent('/actors/motion/native', envelope)
            if (not isinstance(result, dict) or result.get('command_id') != command_id
                    or result.get('hub_boot_id') != self.boot_id or result.get('accepted') is not True
                    or not isinstance(result.get('result'), dict)):
                raise RuntimeError('Guarded motion actor did not acknowledge this command')
            return result['result']
        return self.factory(path,payload)

    def native_motion(self, payload, *, command_id=None):
        """Explicit typed motor API; caller retains the acquired boot/epoch binding."""
        if not self.config['guarded_motion']['enabled'] or self.stock_selected(): raise RuntimeError('Explicit native motion transport required')
        command_id=command_id or str(uuid.uuid4())
        envelope=dict(command_id=command_id,hub_boot_id=self.boot_id,path='/native/antenna',payload=payload)
        value=self.agent('/actors/motion/native',envelope)
        if (value.get('accepted') is not True or value.get('command_id')!=command_id
                or value.get('hub_boot_id')!=self.boot_id or not isinstance(value.get('result'),dict)):
            raise RuntimeError('Native motion receipt unknown or rejected')
        return value['result']

    def status(self):
        return {'daemon': self.robot('/api/daemon/status'),
                'ownership': self.robot('/api/daemon/robot-app-lock-status'),
                'robot': self.robot('/api/state/full'),
                'action_running': self.lock.locked() or self.stock_unknown,
                'stock_motion':dict(selected=self.stock_selected(),unknown=self.stock_unknown,
                    hub_boot_id=self.boot_id,owned_uuid=self.stock_owned,stop_observed=self.stock_stop_observed,
                    stop_request=self.stock_stop_request,hard_stop_certified=False)}

    def move(self, path, payload):
        if self.stock_selected():
            if getattr(self.stock_scope,'binding',None) is None:
                if not self.lock.acquire(False):raise RuntimeError('Hub is busy')
                try:self.stock_begin();return self.move(path,payload)
                finally:self.stock_end();self.lock.release()
            task_id=None
            try:
                task=self.robot(path,payload)
                try:task_id=self.move_uuid(task['uuid'])
                except Exception:self.stock_unknown=True;raise
                self.stock_owned=task_id;self.stock_stop_observed=None
                deadline=time.monotonic()+self.config['timeouts']['move']
                while time.monotonic()<deadline:
                    time.sleep(self.config['motion']['move_poll_seconds']);self.stock_check()
                    if task_id not in self.stock_dependencies():
                        self.stock_owned=None
                        self.stock_check()
                        self.stock_scope.observed+=1
                        return dict(task,completion_observed=True,pose_verified=False,hard_stop_certified=False)
                raise TimeoutError('Stock movement completion not observed')
            except BaseException as exc:
                if task_id is not None and task_id==self.stock_owned:
                    try:self.stock_stop_owned(task_id)
                    except BaseException as stop_error:exc.add_note('Owned stock stop unknown: '+type(stop_error).__name__)
                raise
        task = self.robot(path, payload)
        task_id = task['uuid']
        deadline = time.monotonic() + self.config['timeouts']['move']
        while time.monotonic() < deadline:
            time.sleep(self.config['motion']['move_poll_seconds'])
            active = self.robot('/api/move/running')
            if not any(item['uuid'] == task_id for item in active):
                state = self.robot('/api/daemon/status')
                if state.get('error') or state.get('backend_status', {}).get('error'):
                    raise RuntimeError('Robot reported a movement error')
                return task
        self.robot('/api/move/stop', task)
        raise RuntimeError('Movement timed out; stop requested')

    def agent(self, path, payload=None):
        request = Request(self.config['network']['agent_url'] + path,
                          data=None if payload is None else json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json',
                                   'Authorization': 'Bearer ' + self.config.token})
        with self.http.open(request, timeout=self.config['timeouts']['http']) as response:
            return json.load(response)

    def expression(self, payload):
        from .motion_limits import validate_steps
        settings = self.config['conversation'].get('expressions', {})
        if not settings.get('enabled', False):
            return {'ok': True, 'skipped': 'expressions_disabled'}
        steps = validate_steps(payload['steps'], settings)
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('Hub is busy')
        try:
            self.stock_begin()
            if self.stock_selected() and 'operator_binding' in payload:
                binding=payload['operator_binding']
                if (type(binding) is not dict or set(binding)!={'agent_boot_id','microphone_epoch',
                        'microphone_enabled','policy_epoch','expression_version'}
                        or type(binding.get('microphone_epoch')) is not int
                        or type(binding.get('policy_epoch')) is not int
                        or type(binding.get('microphone_enabled')) is not bool
                        or type(binding.get('expression_version')) is not int or not 0<=binding['expression_version']<2**63):
                    raise RuntimeError('Stock command binding changed: missing_binding')
                self.stock_compare((binding.get('agent_boot_id'),binding['microphone_epoch'],binding['policy_epoch'],
                    binding['microphone_enabled']),self.stock_scope.binding)
                self.stock_scope.expression_version=binding['expression_version']
                self.stock_check()
            for step in steps:
                state = self.status()
                daemon = state['daemon']
                if daemon['state'] != 'running' or not (daemon.get('backend_status') or {}).get('ready'):
                    raise RuntimeError('Robot is not ready')
                if state['ownership']['state'] != 'free' or self.robot('/api/move/running'):
                    raise RuntimeError('Robot is controlled by another app or movement')
                if state['robot']['control_mode'] != 'enabled':
                    raise RuntimeError('Expressions require enabled motors')
                self.move('/api/move/goto', step)
            if self.stock_selected():
                return dict(ok=True,steps_observed=len(steps),pose_verified=False,hard_stop_certified=False)
            return {'ok': True, 'steps_completed': len(steps)}
        finally:
            self.stock_end()
            self.lock.release()

    def action(self, name):
        if name not in ('hello', 'wake', 'sleep'):
            raise ValueError('Unknown action')
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('Hub is busy')
        LOG.info('action_start name=%s', name)
        woke = False
        try:
            self.stock_begin()
            state = self.status()
            daemon = state['daemon']
            if daemon['state'] != 'running' or not (daemon.get('backend_status') or {}).get('ready'):
                raise RuntimeError('Robot is not ready')
            if state['ownership']['state'] != 'free' or self.robot('/api/move/running'):
                raise RuntimeError('Robot is controlled by another app or movement')
            mode = state['robot']['control_mode']
            if mode == 'gravity_compensation':
                raise RuntimeError('Robot is in gravity compensation mode')
            if name == 'sleep':
                if mode != 'disabled':
                    self.move('/api/move/play/goto_sleep', {})
            elif name == 'wake':
                if mode == 'disabled':
                    woke = True
                    self.robot('/api/motors/set_mode/enabled', {})
                    self.move('/api/move/play/wake_up', {})
                    if self.robot('/api/motors/status')['mode'] != 'enabled':
                        raise RuntimeError('Motors are not enabled after wake')
                    woke = False
            else:
                scenario = json.loads((self.config.path(self.config['paths']['scenarios_dir']) / 'hello.json').read_text())
                for step in scenario['steps']:
                    if not self.config['motion']['min_step_seconds'] <= step['duration'] <= self.config['motion']['max_step_seconds'] or len(step['offset']) != 2:
                        raise ValueError('Invalid scenario step')
                    if not all(math.isfinite(x) and abs(x) <= self.config['motion']['max_antenna_offset'] for x in step['offset']):
                        raise ValueError('Antenna offset exceeds scenario limits')
                if mode == 'disabled':
                    woke = True
                    self.robot('/api/motors/set_mode/enabled', {})
                    self.move('/api/move/play/wake_up', {})
                if self.robot('/api/motors/status')['mode'] != 'enabled':
                    raise RuntimeError('Motors are not enabled after wake')
                original = self.robot('/api/state/present_antenna_joint_positions')
                if self.stock_selected():self.stock_antenna_positions(original)
                for step in scenario['steps']:
                    antennas = [max(-math.pi, min(math.pi, pos + offset))
                                for pos, offset in zip(original, step['offset'])]
                    self.move('/api/move/goto', {'antennas': antennas,
                              'duration': step['duration'], 'interpolation': 'minjerk'})
                    actual = self.robot('/api/state/present_antenna_joint_positions')
                    if self.stock_selected():self.stock_antenna_positions(actual)
                    if any(abs(a-b) > self.config['motion']['antenna_tolerance'] for a,b in zip(actual, antennas)):
                        raise RuntimeError('Antennas did not reach the requested position')
                    LOG.info('antenna_step target=%s actual=%s', antennas, actual)
                actual = self.robot('/api/state/present_antenna_joint_positions')
                if self.stock_selected():self.stock_antenna_positions(actual)
                if any(abs(a-b) > self.config['motion']['antenna_tolerance'] for a,b in zip(actual, original)):
                    raise RuntimeError('Antennas did not return to their starting position')
            LOG.info('action_completed name=%s', name)
            if self.stock_selected():
                return dict(ok=True,action=name,completion_observed=bool(self.stock_scope.observed),
                    moves_observed=self.stock_scope.observed,
                    antenna_pose_verified=name=='hello',pose_verified=False,hard_stop_certified=False)
            return {'ok': True, 'action': name}
        except Exception:
            LOG.exception('action_failed name=%s', name)
            raise
        finally:
            try:
                if woke and not self.stock_selected():
                    self.move('/api/move/play/goto_sleep', {})
                    LOG.info('restored_sleep')
            finally:
                self.stock_end()
                self.lock.release()

    @staticmethod
    def stock_antenna_positions(value):
        if (type(value) is not list or len(value)!=2
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in value)):
            raise RuntimeError('Actual antenna positions unknown')

    def monitor(self):
        previous = None
        while True:
            try:
                status = self.robot('/api/daemon/status')
                current = (status['state'], status.get('error'),
                           (status.get('backend_status') or {}).get('ready'))
            except Exception as exc:
                current = ('offline', str(exc))
            if current != previous:
                LOG.info('robot_status %s', json.dumps(current))
                previous = current
            time.sleep(self.config['motion']['poll_seconds'])


def serve(hub):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/control':
                from .control_page import PAGE
                body = PAGE.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == '/control/status':
                if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + hub.config.token):
                    self.reply(401, {'error': 'Bearer token required'})
                    return
                try:
                    value = hub.agent('/status')
                    self.reply(200, {key: value.get(key) for key in ('microphone_enabled', 'capture_active', 'phase', 'expression', 'expression_error', 'volume_percent', 'volume_control_enabled', 'resumable_reply', 'motion_actor', 'agent_boot_id', 'microphone_epoch', 'motion_policy')})
                except Exception:
                    self.reply(503, {'error': 'Robot agent unavailable'})
                return
            if self.path == '/health':
                self.reply(200, {'ok': True, 'service': 'reachy-hub'})
            elif self.path == '/status':
                try:
                    self.reply(200, hub.status())
                except Exception as exc:
                    self.reply(503, {'ok': False, 'error': str(exc)})
            else:
                self.reply(404, {'error': 'Not found'})

        def do_POST(self):
            token = self.headers.get('Authorization', '')
            if not hmac.compare_digest(token, 'Bearer ' + hub.config.token):
                self.reply(401, {'error': 'Bearer token required'})
                return
            if self.path=='/actions/stock-reconcile':
                diagnostic=dict(phase='decode')
                try:
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<=4096:raise ValueError('Reconciliation request size')
                    self.connection.settimeout(min(2,hub.config['timeouts']['http']))
                    payload=decode_reconciliation_json(self.rfile.read(size))
                    self.reply(200,hub.stock_reconcile(payload,diagnostic=diagnostic))
                except Exception as exc:
                    invalid=isinstance(exc,(ValueError,KeyError,TypeError))
                    self.reply(400 if invalid else 409,dict(
                        error='invalid_reconciliation_request' if invalid else 'reconciliation_denied',
                        phase=diagnostic['phase'],error_class=reconciliation_error_class(exc)))
                return
            if self.path in ('/actions/expression', '/control/microphone', '/control/volume', '/control/motion-policy'):
                try:
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= hub.config['limits']['max_agent_request_bytes']:
                        raise ValueError('Invalid request size')
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise ValueError('Expected JSON object')
                    if self.path == '/control/volume':
                        from .volume import validate_percent
                        if set(payload) != {'volume_percent'}:
                            raise ValueError('Expected volume_percent')
                        validate_percent(payload['volume_percent'])
                        value = hub.agent('/volume', payload)
                    elif self.path == '/control/motion-policy':
                        value=hub.agent('/motion-policy',payload)
                    elif self.path == '/control/microphone':
                        if set(payload) != {'enabled'} or not isinstance(payload['enabled'], bool):
                            raise ValueError('enabled must be boolean')
                        value = hub.agent('/microphone', payload)
                    else:
                        value = hub.expression(payload)
                    self.reply(200, value)
                except (ValueError, KeyError, TypeError) as exc:
                    self.reply(400, {'error': str(exc)})
                except Exception as exc:
                    self.reply(409, {'error': str(exc)})
                return
            actions = {'/actions/hello': 'hello', '/actions/wake': 'wake', '/actions/sleep': 'sleep'}
            if self.path not in actions:
                self.reply(404, {'error': 'Not found'})
                return
            try:
                self.reply(200, hub.action(actions[self.path]))
            except Exception as exc:
                self.reply(409, {'ok': False, 'error': str(exc)})

        def log_message(self, fmt, *args):
            LOG.info('http client=%s %s', self.client_address[0], fmt % args)

    threading.Thread(target=hub.monitor, daemon=True).start()
    server = ThreadingHTTPServer((hub.config['servers']['hub']['listen'], hub.config['servers']['hub']['port']), Handler)
    server.daemon_threads = True
    LOG.info('listening %s:%s', *server.server_address)
    server.serve_forever()


def main(config):
    from .logging_utils import configure
    configure(config, 'events')
    serve(Hub(config))
