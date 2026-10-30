"""Transactional local state and an at-least-once, privacy-safe delivery outbox.

Transport callbacks must return the exact event ID only after durable acceptance.
S3 delivery uses SigV4 and environment credentials, or an explicit HTTPS PUT proxy.
VPS uses authenticated HTTPS and an explicit {accepted: true, id: ...} receipt.
"""
import json
import os
from pathlib import Path
import sqlite3
import time
from urllib.request import Request, build_opener, ProxyHandler
from urllib.parse import urlsplit, quote
from datetime import datetime, timezone
import hashlib
import hmac
import re
from .contracts import decode, uid, validate
from .state import utc


class DurableStore:
    def __init__(self, path, cap=10000):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        path.chmod(0o600)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS versions(revision INTEGER PRIMARY KEY, body TEXT NOT NULL,
            reason TEXT NOT NULL, at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS changes(field TEXT PRIMARY KEY, changed REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS tool_admissions(name TEXT PRIMARY KEY, request_id TEXT NOT NULL,
            status TEXT NOT NULL, at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, body TEXT NOT NULL,
            s3 INTEGER NOT NULL DEFAULT 0, vps INTEGER NOT NULL DEFAULT 0);
        ''')
        self.cap = cap
        self.owner=None
        if self.db.execute('SELECT count(*) FROM versions').fetchone()[0] == 0:
            self.update(dict(personality='Ричи: краткий, прямой, любопытный.',
                principles='Не выдумывать восприятие. STOP, privacy, ownership и физические guards обязательны.',
                goal=None, memory=''), -1, 'initial state')

    def claim(self):
        """Local process fence; inspection is allowed, a second runtime is not."""
        import fcntl
        path=self.db.execute('PRAGMA database_list').fetchone()[2]+'.owner'
        owner=open(path,'a');os.chmod(path,0o600)
        try:fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:owner.close();raise RuntimeError('Production state already has a runtime owner')
        self.owner=owner

    def current(self):
        row = self.db.execute('SELECT revision,body FROM versions ORDER BY revision DESC LIMIT 1').fetchone()
        return row[0], decode(row[1])

    def last_changed(self,field):
        row=self.db.execute('SELECT changed FROM changes WHERE field=?',(field,)).fetchone()
        return row[0] if row else 0

    def update(self, patch, expected, reason):
        if type(expected) is not int or expected < -1:raise ValueError('Integer revision required')
        if (not isinstance(patch, dict) or not patch or set(patch)-{'personality','principles','goal','memory'}
                or not isinstance(reason,str) or not 1 <= len(reason) <= 240):
            raise ValueError('Bounded versioned update required')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT revision,body FROM versions ORDER BY revision DESC LIMIT 1').fetchone()
            revision, body = (row[0], decode(row[1])) if row else (-1, {})
            if revision != expected:raise ValueError('Version CAS conflict')
            for key, value in patch.items():
                if key == 'goal':
                    if value is not None:validate('Goal', value)
                elif not isinstance(value,str) or len(value) > (512 if key != 'memory' else 2048):
                    raise ValueError('State projection bound')
            body.update(patch)
            for field in patch:
                self.db.execute('INSERT OR REPLACE INTO changes VALUES (?,?)',(field,time.time() if revision>=0 else 0))
            self.db.execute('INSERT INTO versions VALUES (?,?,?,?)',
                (revision+1,json.dumps(body,ensure_ascii=False),reason,utc()))
        return revision+1

    def rollback(self, target, expected, reason):
        if type(target) is not int or target<0:raise ValueError('Integer target revision required')
        row = self.db.execute('SELECT body FROM versions WHERE revision=?',(target,)).fetchone()
        if row is None:raise ValueError('Unknown revision')
        return self.update(decode(row[0]),expected,reason)

    def append(self, event, destinations=('s3','vps')):
        # Content is deliberately excluded even outside privacy. No retrospective
        # export of dialogue, observations, goals or model reasoning on re-enable.
        safe = {key:event[key] for key in ('kind','at','request_id','activity','task_id') if key in event}
        event_id = uid()
        body = json.dumps(dict(id=event_id,metadata=safe),ensure_ascii=False)
        with self.db:
            if self.db.execute('SELECT count(*) FROM outbox').fetchone()[0] >= self.cap:
                self.db.execute('DELETE FROM outbox WHERE rowid IN '
                    '(SELECT rowid FROM outbox WHERE s3=1 AND vps=1 ORDER BY rowid LIMIT 1)')
                if self.db.execute('SELECT count(*) FROM outbox').fetchone()[0] >= self.cap:
                    raise BufferError('Durable outbox full; delivery required')
            self.db.execute('INSERT INTO outbox VALUES (?,?,?,?)',
                (event_id,body,int('s3' not in destinations),int('vps' not in destinations)))
        return event_id

    def tool_pending(self):
        return dict(self.db.execute("SELECT name,request_id FROM tool_admissions WHERE status!='terminal'").fetchall())

    def tool_begin(self,name,request_id):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if name in self.tool_pending():raise ValueError('Tool execution unresolved')
            self.db.execute('INSERT OR REPLACE INTO tool_admissions VALUES (?,?,?,?)',(name,request_id,'running',utc()))

    def tool_terminal(self,name,request_id):
        # Trusted hook only: model output cannot reconcile execution.
        with self.db:
            if self.db.execute("UPDATE tool_admissions SET status='terminal' WHERE name=? AND request_id=?",(name,request_id)).rowcount!=1:
                raise ValueError('Tool terminal identity mismatch')

    def pending(self, destination):
        if destination not in ('s3','vps'):raise ValueError('Unknown destination')
        row = self.db.execute('SELECT id,body FROM outbox WHERE '+destination+'=0 ORDER BY rowid LIMIT 1').fetchone()
        return None if row is None else (row[0],decode(row[1]))

    def ack(self, destination, event_id):
        if destination not in ('s3','vps'):raise ValueError('Unknown destination')
        with self.db:
            self.db.execute('UPDATE outbox SET '+destination+'=1 WHERE id=?',(event_id,))
            self.db.execute('DELETE FROM outbox WHERE s3=1 AND vps=1')

    def close(self):
        self.db.close()
        if self.owner:self.owner.close();self.owner=None


class Delivery:
    def __init__(self, destination, settings):
        self.destination,self.settings = destination,settings
        if destination=='s3' and settings.get('bucket'):
            if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]',settings['bucket']) or not re.fullmatch(r'[a-z0-9-]{1,32}',settings.get('region','')):
                raise ValueError('S3 bucket/region required')
            self.opener=build_opener(ProxyHandler({}));return
        url = settings['url']
        parts = urlsplit(url)
        if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password):
            raise ValueError('Export requires HTTPS')
        if destination=='s3' and '{id}' not in url:raise ValueError('S3 URL must contain stable {id} object key')
        self.opener=build_opener(ProxyHandler({}))

    def s3_request(self,event_id,body):
        access=os.environ.get(self.settings.get('access_key_env','AWS_ACCESS_KEY_ID'),'')
        secret=os.environ.get(self.settings.get('secret_key_env','AWS_SECRET_ACCESS_KEY'),'')
        session=os.environ.get(self.settings.get('session_token_env','AWS_SESSION_TOKEN'),'')
        if not access or not secret:raise ValueError('S3 credentials not configured')
        region=self.settings['region'];bucket=self.settings['bucket']
        host=f'{bucket}.s3.{region}.amazonaws.com'
        prefix=self.settings.get('prefix','reachy').strip('/')
        path='/'+quote((prefix+'/' if prefix else '')+event_id+'.json',safe='/~')
        payload=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
        digest=hashlib.sha256(payload).hexdigest()
        now=datetime.now(timezone.utc);stamp=now.strftime('%Y%m%dT%H%M%SZ');day=now.strftime('%Y%m%d')
        headers={'host':host,'x-amz-date':stamp,'x-amz-content-sha256':digest}
        if session:headers['x-amz-security-token']=session
        signed=';'.join(sorted(headers))
        canonical=''.join(key+':'+headers[key]+'\n' for key in sorted(headers))
        request_hash=hashlib.sha256(('PUT\n'+path+'\n\n'+canonical+'\n'+signed+'\n'+digest).encode()).hexdigest()
        scope=day+'/'+region+'/s3/aws4_request'
        string_to_sign='AWS4-HMAC-SHA256\n'+stamp+'\n'+scope+'\n'+request_hash
        def sign(key,value):return hmac.new(key,value.encode(),hashlib.sha256).digest()
        key=sign(sign(sign(sign(('AWS4'+secret).encode(),day),region),'s3'),'aws4_request')
        signature=hmac.new(key,string_to_sign.encode(),hashlib.sha256).hexdigest()
        headers['Authorization']='AWS4-HMAC-SHA256 Credential='+access+'/'+scope+', SignedHeaders='+signed+', Signature='+signature
        headers['Content-Type']='application/json'
        return Request('https://'+host+path,data=payload,headers=headers,method='PUT')

    def __call__(self, event_id, body):
        if self.destination=='s3' and self.settings.get('bucket'):
            with self.opener.open(self.s3_request(event_id,body),timeout=5) as response:
                if not 200<=response.status<300:raise OSError('S3 write rejected')
            return event_id
        token = os.environ.get(self.settings.get('token_env',''),'')
        headers={'Content-Type':'application/json'}
        if self.destination=='vps' and not token:raise ValueError('VPS credentials not configured')
        if token:headers['Authorization']='Bearer '+token
        url=self.settings['url'].replace('{id}',event_id)
        request=Request(url,data=json.dumps(body).encode(),headers=headers,
            method='PUT' if self.destination=='s3' else 'POST')
        with self.opener.open(request,timeout=5) as response:
            if not 200 <= response.status < 300:raise OSError('Delivery rejected')
            if self.destination=='vps':
                receipt=decode(response.read(4097))
                if receipt != dict(accepted=True,id=event_id):raise ValueError('Durable receipt required')
        return event_id
