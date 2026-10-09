"""Standalone optional VPS broker. One allowlisted synthetic workflow; no controls."""
import hashlib
import hmac
import json
import os
import queue
import re
import sqlite3
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler


def decode(raw):
    def reject(x): raise ValueError('nonfinite JSON')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError('duplicate JSON key')
            value[key] = item
        return value
    return json.loads(raw, parse_constant=reject, object_pairs_hook=unique)


class Store:
    def __init__(self, path, invoke, capacity=1024, pending_cap=8):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.invoke, self.capacity, self.pending_cap = invoke, capacity, pending_cap
        self.permit = threading.Semaphore(1)
        self.queue = queue.Queue(maxsize=pending_cap)
        self.closed = False
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks (key TEXT PRIMARY KEY, digest TEXT, body TEXT, deadline REAL, status TEXT, result TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)')
        unknown = self.db.execute("SELECT COUNT(*) FROM tasks WHERE status='running'").fetchone()[0]
        if unknown:
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES('quarantined','true')")
        self.quarantined = bool(self.db.execute("SELECT 1 FROM metadata WHERE key='quarantined'").fetchone())
        # Unknown dispatch after crash is never automatically rerun.
        self.db.execute("UPDATE tasks SET status='execution_unknown' WHERE status IN ('queued','running')")
        self.db.commit()
        self.worker = threading.Thread(target=self.consume, daemon=True)
        self.worker.start()

    def consume(self):
        while True:
            key = self.queue.get()
            try:
                if key is None: return
                self.work(key)
            finally:
                self.queue.task_done()

    def close(self):
        if self.closed: return
        self.queue.put(None, timeout=2)
        self.worker.join(timeout=2)
        if self.worker.is_alive(): raise RuntimeError('Execution still busy; database not closed')
        self.db.close()
        self.closed = True

    def _row(self, key):
        row = self.db.execute('SELECT * FROM tasks WHERE key=?', (key,)).fetchone()
        if row is None: raise KeyError(key)
        return row

    def public(self, row):
        body = decode(row['body'])
        return dict(task_id=body['task_id'], attempt_id=body['attempt_id'], status=row['status'],
                    result=decode(row['result']) if row['result'] is not None and row['status']=='succeeded' else None)

    def status(self, key):
        with self.lock:
            row = self._row(key)
            if time.time() > row['deadline'] and row['status'] in ('queued','running','succeeded'):
                self.db.execute("UPDATE tasks SET status='expired', result=NULL WHERE key=?", (key,)); self.db.commit()
                row = self._row(key)
            return self.public(row)

    def submit(self, body):
        if not isinstance(body, dict) or set(body) != {'capability','task_id','attempt_id','deadline_at','arguments'}:
            raise ValueError('Invalid task envelope')
        if body['capability'] != 'workflow.synthetic_echo': raise ValueError('Unknown capability')
        for field in ('task_id','attempt_id'):
            if not isinstance(body[field], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', body[field]): raise ValueError('Invalid identity')
        args = body['arguments']
        if not isinstance(args, dict) or set(args) != {'value'} or not isinstance(args['value'], str) or len(args['value']) > 256:
            raise ValueError('Invalid arguments')
        if not isinstance(body['deadline_at'], str) or not body['deadline_at'].endswith('Z'): raise ValueError('UTC deadline required')
        deadline = datetime.fromisoformat(body['deadline_at'].replace('Z','+00:00')).timestamp()
        raw = json.dumps(body, sort_keys=True, separators=(',',':'))
        digest = hashlib.sha256(raw.encode()).hexdigest()
        key = body['task_id'] + '/' + body['attempt_id']
        with self.lock:
            existing = self.db.execute('SELECT * FROM tasks WHERE key=?', (key,)).fetchone()
            if existing:
                if existing['digest'] != digest: raise FileExistsError('Idempotency conflict')
                return self.status(key)
            if self.quarantined: raise BlockingIOError('Execution unknown: operator audit required')
            if not time.time() < deadline <= time.time()+60: raise ValueError('Deadline must be within60s')
            # Retain tombstones24h; cap rejects instead of losing dedupe guarantees.
            self.db.execute("DELETE FROM tasks WHERE deadline<? AND status NOT IN ('queued','running')", (time.time()-86400,))
            if self.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] >= self.capacity: raise BlockingIOError('Retention full')
            pending = self.db.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('queued','running')").fetchone()[0]
            if pending >= self.pending_cap or self.queue.full(): raise BlockingIOError('Queue full')
            self.db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?)', (key,digest,raw,deadline,'queued',None))
            self.db.commit()
            self.queue.put_nowait(key)
            return self.status(key)

    def cancel(self, key):
        with self.lock:
            row = self._row(key)
            if row['status'] in ('queued','running'):
                self.db.execute("UPDATE tasks SET status='cancelled', result=NULL WHERE key=?", (key,)); self.db.commit()
            return self.status(key)

    def work(self, key):
        # Permit is held until invoke actually returns, even after cancel/deadline.
        with self.permit:
            with self.lock:
                if self.status(key)['status'] != 'queued': return
                if self.quarantined:
                    self.db.execute("UPDATE tasks SET status='execution_unknown' WHERE key=?", (key,)); self.db.commit()
                    return
                row = self._row(key); body = decode(row['body'])
                self.db.execute("UPDATE tasks SET status='running' WHERE key=?", (key,)); self.db.commit()
            try:
                result = self.invoke(body)
                expected = dict(task_id=body['task_id'], attempt_id=body['attempt_id'], value=body['arguments']['value'])
                if result != expected: raise ValueError('Workflow output identity/shape mismatch')
                status = 'succeeded'
            except Exception:
                result, status = None, 'execution_unknown'
                with self.lock:
                    self.quarantined = True
                    self.db.execute("INSERT OR REPLACE INTO metadata VALUES('quarantined','true')"); self.db.commit()
            with self.lock:
                if self.status(key)['status'] != 'running': return
                self.db.execute('UPDATE tasks SET status=?, result=? WHERE key=?', (status,json.dumps(result) if result else None,key))
                self.db.commit()


class N8n:
    def __init__(self, url, token):
        self.url, self.token = url, token
        self.opener = build_opener(ProxyHandler({}))
    def __call__(self, body):
        payload = dict(task_id=body['task_id'], attempt_id=body['attempt_id'], value=body['arguments']['value'])
        request = Request(self.url, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json','X-Companion-Token':self.token})
        with self.opener.open(request, timeout=15) as response: raw = response.read(8193)
        if len(raw)>8192: raise ValueError('Oversized response')
        return decode(raw)


def create_server(store, token, bind='127.0.0.1', port=5679):
    if len(token) < 32: raise ValueError('Strong broker token required')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, code, value):
            raw = json.dumps(value).encode(); self.send_response(code)
            self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers()
            try: self.wfile.write(raw)
            except OSError: pass
        def authenticated(self):
            if hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token): return True
            self.reply(401, {'error':'unauthorized'}); return False
        def do_GET(self):
            if not self.authenticated(): return
            if self.path=='/health': self.reply(200, {'ok':not store.quarantined,'quarantined':store.quarantined,'capabilities':['workflow.synthetic_echo'],'controls':False}); return
            try:
                if not self.path.startswith('/tasks/'): raise KeyError()
                self.reply(200, store.status(self.path.removeprefix('/tasks/')))
            except KeyError: self.reply(404, {'error':'not_found'})
        def do_POST(self):
            if not self.authenticated(): return
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 <= size <= 4096: raise ValueError('Envelope cap')
                if self.path=='/tasks': result = store.submit(decode(self.rfile.read(size)))
                elif self.path.startswith('/tasks/') and self.path.endswith('/cancel'):
                    result = store.cancel(self.path.removeprefix('/tasks/').removesuffix('/cancel'))
                else: raise KeyError()
                self.reply(200, result)
            except KeyError: self.reply(404, {'error':'not_found'})
            except FileExistsError: self.reply(409, {'error':'idempotency_conflict'})
            except BlockingIOError: self.reply(429, {'error':'admission_full'})
            except Exception: self.reply(422, {'error':'invalid_envelope'})
    class Server(ThreadingHTTPServer):
        daemon_threads=True
        def __init__(self, *args):
            self.clients=threading.BoundedSemaphore(16); super().__init__(*args)
        def process_request(self, request, address):
            request.settimeout(5)
            if not self.clients.acquire(blocking=False): self.shutdown_request(request); return
            try: super().process_request(request,address)
            except BaseException: self.clients.release(); raise
        def process_request_thread(self, request,address):
            try: super().process_request_thread(request,address)
            finally: self.clients.release()
    return Server((bind,port),Handler)


if __name__=='__main__':
    store = Store(os.environ.get('WORKFLOW_DB','/data/tasks.sqlite'),
                  N8n(os.environ['WORKFLOW_URL'],os.environ['WORKFLOW_WEBHOOK_TOKEN']))
    with create_server(store,os.environ['WORKFLOW_BROKER_TOKEN'],bind='0.0.0.0',port=8080) as server: server.serve_forever()
