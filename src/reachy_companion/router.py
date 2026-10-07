"""Hub voice gateway. Standard library only: never imports speech/LLM runtimes."""
import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

LOG = logging.getLogger('reachy-router')


class Router:
    def __init__(self, config):
        self.config = config
        self.http = build_opener(ProxyHandler({}))

    def open(self, base, path, body=None, timeout=None):
        return self.http.open(Request(base.rstrip('/') + path, data=body,
                              headers={'Content-Type': 'application/json',
                                       'Authorization': 'Bearer ' + self.config.token}),
                              timeout=timeout or self.config['timeouts']['client'])


def handler_for(router):
    config = router.config

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def setup(self):
            super().setup()
            self.connection.settimeout(config['timeouts']['client'])

        def reply(self, code, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            if not hmac.compare_digest(self.headers.get('Authorization', '').encode(),
                                       ('Bearer ' + config.token).encode()):
                self.close_connection = True
                self.reply(401, {'error': 'Bearer token required'})
                return False
            return True

        def relay(self, base, path, body=None):
            sent = False
            try:
                with router.open(base, path, body) as upstream:
                    self.send_response(upstream.status)
                    sent = True
                    self.send_header('Content-Type', upstream.headers.get('Content-Type', 'application/json'))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.close_connection = True
                    # read1 returns AVAILABLE data, so it never waits for an entire
                    # reply or full buffer before forwarding the first audio event.
                    while chunk := upstream.read1(config['streaming']['relay_chunk_bytes']):
                        self.wfile.write(chunk)
                        self.wfile.flush()
            except HTTPError as exc:
                if not sent:
                    self.reply(exc.code, {'ok': False, 'error': 'Upstream request failed'})
            except (URLError, TimeoutError, OSError):
                if not sent:
                    self.reply(503, {'ok': False, 'error': 'Compute worker or robot is unavailable'})
                else:
                    self.close_connection = True
                LOG.warning('upstream_unavailable path=%s', path)

        def do_GET(self):
            if self.path == '/health':
                try:
                    with router.open(config['network']['compute_url'], '/health', timeout=config['timeouts']['http']) as response:
                        ready = json.load(response).get('ok', False)
                except (OSError, URLError, ValueError):
                    ready = False
                self.reply(200 if ready else 503, {'ok': ready, 'service': 'voice-router',
                                                 'mode': 'remote', 'inference_on_hub': False})
            elif self.path == '/status' and self.authorized():
                try:
                    with router.open(config['network']['agent_url'], '/status', timeout=config['timeouts']['http']) as response:
                        agent = json.load(response)
                except (OSError, URLError, ValueError):
                    agent = {'error': 'Robot agent unavailable'}
                try:
                    with router.open(config['network']['compute_url'], '/status', timeout=config['timeouts']['http']) as response:
                        worker = json.load(response)
                except (OSError, URLError, ValueError):
                    worker = {'ok': False, 'error': 'Compute worker unavailable'}
                self.reply(200, {'ok': worker.get('ok', False), 'mode': 'remote',
                                 'phase': worker.get('phase', 'offline'),
                                 'last_turn': worker.get('last_turn'), 'worker': worker, 'agent': agent})
            elif self.path != '/status':
                self.reply(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.authorized():
                return
            if self.path not in ('/turn', '/text', '/say', '/reset', '/pause', '/resume',
                                 '/robot/ask', '/robot/say', '/microphone', '/expression/plan', '/transcribe', '/stream/turn', '/stream/text', '/stream/say'):
                self.close_connection = True
                self.reply(404, {'error': 'Not found'})
                return
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= config['limits']['max_request_bytes']:
                    raise ValueError('Invalid request size')
                body = self.rfile.read(size)
                if len(body) != size:
                    raise ValueError('Incomplete request body')
                if not isinstance(json.loads(body), dict):
                    raise ValueError('Expected JSON object')
            except (ValueError, TimeoutError):
                self.close_connection = True
                self.reply(400, {'error': 'Invalid request body'})
                return
            if self.path in ('/pause', '/resume', '/microphone', '/robot/ask', '/robot/say'):
                self.relay(config['network']['agent_url'], self.path.removeprefix('/robot'), body)
            else:
                self.relay(config['network']['compute_url'], self.path, body)

        def log_message(self, fmt, *args):
            LOG.info('http client=%s %s', self.client_address[0], fmt % args)

    return Handler


def main(config):
    from .logging_utils import configure
    configure(config, 'router')
    address = config['servers']['voice']
    server = ThreadingHTTPServer((address['listen'], address['port']), handler_for(Router(config)))
    server.daemon_threads = True
    LOG.info('routing compute requests to %s; no inference loaded', config['network']['compute_url'])
    server.serve_forever()
