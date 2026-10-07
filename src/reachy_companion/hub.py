#!/usr/bin/env python3
"""Small Reachy Mini scenario router; Python standard library only."""
import hmac
import json
import logging
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler

LOG = logging.getLogger("reachy-hub")


class Hub:
    def __init__(self, config):
        self.config = config
        self.http = build_opener(ProxyHandler({}))
        self.lock = threading.Lock()

    def robot(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(self.config['network']['robot_url'] + path, data=data,
                          headers={'Content-Type': 'application/json'})
        with self.http.open(request, timeout=self.config['timeouts']['robot']) as response:
            return json.load(response)

    def status(self):
        return {'daemon': self.robot('/api/daemon/status'),
                'ownership': self.robot('/api/daemon/robot-app-lock-status'),
                'robot': self.robot('/api/state/full'),
                'action_running': self.lock.locked()}

    def move(self, path, payload):
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
            return {'ok': True, 'steps_completed': len(steps)}
        finally:
            self.lock.release()

    def action(self, name):
        if name not in ('hello', 'wake', 'sleep'):
            raise ValueError('Unknown action')
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('Hub is busy')
        LOG.info('action_start name=%s', name)
        woke = False
        try:
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
                for step in scenario['steps']:
                    antennas = [max(-math.pi, min(math.pi, pos + offset))
                                for pos, offset in zip(original, step['offset'])]
                    self.move('/api/move/goto', {'antennas': antennas,
                              'duration': step['duration'], 'interpolation': 'minjerk'})
                    actual = self.robot('/api/state/present_antenna_joint_positions')
                    if any(abs(a-b) > self.config['motion']['antenna_tolerance'] for a,b in zip(actual, antennas)):
                        raise RuntimeError('Antennas did not reach the requested position')
                    LOG.info('antenna_step target=%s actual=%s', antennas, actual)
                actual = self.robot('/api/state/present_antenna_joint_positions')
                if any(abs(a-b) > self.config['motion']['antenna_tolerance'] for a,b in zip(actual, original)):
                    raise RuntimeError('Antennas did not return to their starting position')
            LOG.info('action_completed name=%s', name)
            return {'ok': True, 'action': name}
        except Exception:
            LOG.exception('action_failed name=%s', name)
            raise
        finally:
            try:
                if woke:
                    self.move('/api/move/play/goto_sleep', {})
                    LOG.info('restored_sleep')
            finally:
                self.lock.release()

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
                    self.reply(200, {key: value.get(key) for key in ('microphone_enabled', 'capture_active', 'phase', 'expression', 'expression_error')})
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
            if self.path in ('/actions/expression', '/control/microphone'):
                try:
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= hub.config['limits']['max_agent_request_bytes']:
                        raise ValueError('Invalid request size')
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise ValueError('Expected JSON object')
                    if self.path == '/control/microphone':
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
