"""PC-owned bounded provenance store. APIs are trusted-owner operations, not tools."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import threading
from .contracts import uid, validate


class MemoryConflict(ValueError): pass


def stamp(value): return datetime.fromisoformat(value.replace('Z','+00:00'))


class MemoryStore:
    def __init__(self, path, namespaces):
        if not 1 <= len(namespaces) <= 4 or any(not isinstance(x,str) or not 1<=len(x)<=64 for x in namespaces):
            raise ValueError('Bounded owner namespaces required')
        self.namespaces=set(namespaces);self.lock=threading.RLock()
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(path,check_same_thread=False,timeout=1)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA secure_delete=ON');self.db.execute('PRAGMA max_page_count=2048')
        self.db.execute('PRAGMA wal_autocheckpoint=16');self.db.execute('PRAGMA journal_size_limit=1048576')
        for sql in ('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS versions (id TEXT,version INTEGER,body TEXT,PRIMARY KEY(id,version))',
                    'CREATE TABLE IF NOT EXISTS active (id TEXT PRIMARY KEY,version INTEGER)',
                    'CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY,digest TEXT,lineage TEXT,namespace TEXT,kind TEXT)',
                    'CREATE TABLE IF NOT EXISTS deleted (id TEXT PRIMARY KEY)',
                    'CREATE TABLE IF NOT EXISTS revoked_lineages (id TEXT PRIMARY KEY)'):
            self.db.execute(sql)
        with self.db:
            for key,value in [('store_id',uid()),('revision','0'),('writes_frozen','0')]:
                self.db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',(key,value))
        path.chmod(0o600)

    def meta(self,key):return self.db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()[0]
    def bump(self):self.db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
    def count(self,table):return self.db.execute('SELECT count(*) FROM '+table).fetchone()[0]

    def evidence(self,evidence_id,digest,lineage,namespace,kind):
        if (namespace not in self.namespaces or kind not in ('sensor','human','model','fixture')
                or not re.fullmatch('[0-9a-f]{64}',digest) or not 1<=len(evidence_id)<=128 or not 1<=len(lineage)<=128
                or (kind=='fixture' and not namespace.startswith('fixture'))):raise ValueError('Invalid provenance')
        values=(evidence_id,digest,lineage,namespace,kind)
        with self.lock,self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.meta('writes_frozen')=='1' or self.db.execute('SELECT 1 FROM revoked_lineages WHERE id=?',(lineage,)).fetchone():
                raise MemoryConflict('Revoked lineage or frozen writes')
            old=self.db.execute('SELECT * FROM evidence WHERE id=?',(evidence_id,)).fetchone()
            if old and old!=values:raise MemoryConflict('Evidence identity changed')
            if not old:
                if self.count('evidence')>=512:raise MemoryConflict('Evidence capacity')
                self.db.execute('INSERT INTO evidence VALUES (?,?,?,?,?)',values)

    def commit(self,item,expected_version,*,confirmed=False):
        item=json.loads(json.dumps(item,allow_nan=False));validate('MemoryItem',item)
        if item['namespace'] not in self.namespaces or len(item['id'])>128 or len(item['content'])>256 or len(json.dumps(item,ensure_ascii=False).encode())>4096:
            raise ValueError('Memory projection bound/namespace; no silent truncation')
        if item['valid_until'] is not None and stamp(item['valid_until'])<=stamp(item['valid_from']):raise ValueError('Invalid validity interval')
        if item['status']=='active' and item['epistemic_type'] in ('fact','preference') and confirmed is not True:
            raise MemoryConflict('Trusted confirmation required; model proposals cannot promote facts')
        if item['epistemic_type']=='hypothesis' and item['valid_until'] is None:raise ValueError('Hypothesis must expire')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                if self.meta('writes_frozen')=='1' or self.db.execute('SELECT 1 FROM deleted WHERE id=?',(item['id'],)).fetchone():
                    raise MemoryConflict('Forgotten item or frozen writes')
                old=self.db.execute('SELECT version FROM active WHERE id=?',(item['id'],)).fetchone()
                actual=old[0] if old else None
                if actual!=expected_version or item['version']!=(0 if actual is None else actual+1):raise MemoryConflict('Memory CAS conflict')
                rows=[self.db.execute('SELECT lineage,namespace FROM evidence WHERE id=?',(eid,)).fetchone()
                      for eid in item['evidence_ids']+item['counterevidence_ids']]
                if any(row is None or row[1]!=item['namespace'] for row in rows):raise MemoryConflict('Missing/cross-namespace evidence')
                roots={row[0] for row in rows}
                if roots!=set(item['lineage_ids']) or any(self.db.execute('SELECT 1 FROM revoked_lineages WHERE id=?',(root,)).fetchone() for root in roots):
                    raise MemoryConflict('Lineage mismatch/revocation')
                if item['epistemic_type']!='fiction' and not item['evidence_ids']:raise MemoryConflict('Unsupported memory')
                if self.count('versions')>=512 or (old is None and self.count('active')>=128):raise MemoryConflict('Memory capacity')
                if old:
                    previous=json.loads(self.db.execute('SELECT body FROM versions WHERE id=? AND version=?',(item['id'],actual)).fetchone()[0])
                    if previous['namespace']!=item['namespace']:raise MemoryConflict('Namespace immutable')
                self.db.execute('INSERT INTO versions VALUES (?,?,?)',(item['id'],item['version'],json.dumps(item,ensure_ascii=False)))
                self.db.execute('INSERT OR REPLACE INTO active VALUES (?,?)',(item['id'],item['version']))
                self.bump();self.db.commit()
                return int(self.meta('revision'))
            except BaseException:self.db.rollback();raise

    def recall(self,query='',*,now=None):
        if not isinstance(query,str) or len(query)>1024:raise ValueError('Query cap')
        now=now or datetime.now(timezone.utc)
        with self.lock:
            self.db.execute('BEGIN')
            try:
                rows=self.db.execute('SELECT body FROM versions JOIN active USING(id,version)').fetchall()
                items=[json.loads(row[0]) for row in rows]
                items=[item for item in items if item['namespace'] in self.namespaces and item['status']=='active'
                       and stamp(item['valid_from'])<=now and (item['valid_until'] is None or now<stamp(item['valid_until']))]
                terms=set(query.lower().split())
                items.sort(key=lambda x:(-len(terms & set(x['content'].lower().split())),x['id']))
                result=dict(store_id=self.meta('store_id'),revision=int(self.meta('revision')),items=items[:8])
                self.db.commit();return result
            except BaseException:self.db.rollback();raise

    def supports(self,descriptors):
        """Relevant-version fence; unrelated store revisions do not reject work."""
        if len(descriptors)>8:return False
        with self.lock:
            now=datetime.now(timezone.utc)
            for descriptor in descriptors:
                row=self.db.execute('SELECT body FROM versions JOIN active USING(id,version) WHERE id=?',
                                    (descriptor['alias'].rsplit(':',1)[0],)).fetchone()
                if row is None:return False
                item=json.loads(row[0])
                if (descriptor!=dict(alias=item['id']+':'+str(item['version']),type=item['epistemic_type'],summary=item['content'])
                        or item['status']!='active' or item['namespace'] not in self.namespaces or stamp(item['valid_from'])>now
                        or (item['valid_until'] is not None and now>=stamp(item['valid_until']))):return False
            return True

    def forget_lineage(self,lineage):
        """Delete all versions dependent on the root; forbid reimport/corrections."""
        if not isinstance(lineage,str) or not 1<=len(lineage)<=128:raise ValueError('Lineage cap')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                rows=self.db.execute('SELECT id,body FROM versions').fetchall()
                ids={row[0] for row in rows if lineage in json.loads(row[1])['lineage_ids']}
                if self.count('revoked_lineages')>=256 or self.count('deleted')+len(ids)>1024:
                    # Deletion still proceeds; no tombstone eviction permits resurrection.
                    self.db.execute("UPDATE meta SET value='1' WHERE key='writes_frozen'")
                else:
                    self.db.execute('INSERT OR IGNORE INTO revoked_lineages VALUES (?)',(lineage,))
                    self.db.executemany('INSERT OR IGNORE INTO deleted VALUES (?)',[(x,) for x in ids])
                for item_id in ids:
                    self.db.execute('DELETE FROM active WHERE id=?',(item_id,));self.db.execute('DELETE FROM versions WHERE id=?',(item_id,))
                self.db.execute('DELETE FROM evidence WHERE lineage=?',(lineage,))
                self.bump();self.db.commit()
                if self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:raise MemoryConflict('Deletion checkpoint incomplete')
                return len(ids)
            except BaseException:self.db.rollback();raise

    def close(self):
        with self.lock:self.db.close()
