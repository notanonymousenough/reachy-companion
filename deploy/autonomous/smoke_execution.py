"""Account-local cooperative cross-process model ownership for finite probes.

No stale-owner reclaim, TTL, reset, implicit bootstrap or unknown recovery.
All runs require a frozen persistent root/ancestor anchor. Permanent journals
are append-only under kernel locks; release never deletes a path.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit
import uuid
import re
from smoke_fs import PinnedTree


def guard_root():
    # Do not derive the namespace from HOME/USERPROFILE environment overrides.
    if os.name=='nt':
        import ctypes
        buffer=ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None,40,None,0,buffer)!=0 or not buffer.value:
            raise RuntimeError('OS account profile identity unavailable')
        home=Path(buffer.value)
    else:
        import pwd
        home=Path(pwd.getpwuid(os.getuid()).pw_dir)
    return home/'.reachy-companion-execution'


def execution_scopes(cfg,binding):
    result=[]
    for role in ('main','fast'):
        weight=cfg['models'][role]['audit']['weight_sha256']
        parsed=urlsplit(cfg['models'][role]['base_url'])
        if (parsed.scheme!='http' or parsed.hostname not in ('localhost','127.0.0.1','::1')
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or type(weight) is not str or not re.fullmatch('[0-9a-f]{64}',weight)):
            raise ValueError('Audited loopback endpoint/model weight identity required')
        # The SDK sends to netloc, not /v1; aliases for the same local endpoint
        # and file/model key must not allocate new ownership namespaces.
        scope=dict(endpoint='http://loopback:'+str(parsed.port or 80),weight_sha256=weight)
        result.append(scope)
    return sorted(result,key=lambda value:json.dumps(value,sort_keys=True))


def _bytes(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()+b'\n'
def _key(scope):return hashlib.sha256(_bytes(scope)).hexdigest()
def anchor_path(root=None):
    root=guard_root() if root is None else root
    return root.with_name(root.name+'.anchor.json')
MAX_JOURNAL=65536


def _read(fd,limit):
    os.lseek(fd,0,os.SEEK_SET);data=os.read(fd,limit+1)
    if len(data)>limit:raise RuntimeError('Execution journal/anchor capacity exhausted')
    return data


def _append(fd,event):
    data=_bytes(event)
    if os.lseek(fd,0,os.SEEK_END)+len(data)>MAX_JOURNAL:raise RuntimeError('Execution journal capacity exhausted')
    if os.write(fd,data)!=len(data):raise RuntimeError('Incomplete persistent execution record')
    os.fsync(fd)


def provision_namespace(scopes):
    """Explicit ONE-TIME offline provisioning after independent quiescence audit.

    Never invoked by acquire/main. Existing root OR sibling anchor rejects;
    failures preserve partial state and cannot be retried as recovery.
    """
    root=guard_root();tree=PinnedTree(root)
    try:
        tree.pin_directory(root.parent)
        # Sibling sentinel is created first and never automatically removed.
        anchor_fd=tree.open_file(anchor_path(root),write=True,create=True)
        tree.mkdir(root)
        records=[];namespace=uuid.uuid4().hex
        for scope in scopes:
            key=_key(scope);directory=root/(key+'.held');directory_handle=tree.mkdir(directory)
            fd=tree.open_file(directory/'owner.jsonl',write=True,create=True)
            header=dict(kind='execution-journal-1',scope=scope,namespace=namespace)
            _append(fd,header);_append(fd,dict(state='RELEASED'))
            records.append(dict(key=key,scope=scope,directory_id=tree.identity(directory_handle),
                file_id=tree.file_identity(fd),header_sha256=hashlib.sha256(_bytes(header)).hexdigest()))
        tree.check_directories()
        directories=[dict(path=str(path),identity=tree.identity(handle)) for path,handle in tree.directories.items()
            if path==root or root.is_relative_to(path)]
        body=dict(kind='execution-anchor-1',platform=os.name,root=str(root),namespace=namespace,
            directories=directories,records=records)
        raw=_bytes(body)
        if os.write(anchor_fd,raw)!=len(raw):raise RuntimeError('Incomplete execution anchor')
        os.fsync(anchor_fd)
        return dict(path=str(anchor_path(root)),file_id=tree.file_identity(anchor_fd),sha256=hashlib.sha256(raw).hexdigest())
    finally:tree.close()


class ExecutionLease:
    def __init__(self,scopes,*,anchor):
        self.scopes=scopes;self.anchor=anchor;self.slots=[];self.tree=None
        self.closed=False;self.unknown=False;self.released=False;self.producer_started=False

    def _check_namespace(self):
        if guard_root()!=self.root:raise RuntimeError('OS account profile path changed')
        self.tree.check_directories()
        for record in self.body['directories']:
            handle=self.tree.directories[Path(record['path'])]
            if self.tree.identity(handle)!=record['identity']:raise RuntimeError('Persistent ancestor/root anchor mismatch')
        self.tree.check_file(self.anchor_fd,self.anchor['file_id'])
        if hashlib.sha256(_read(self.anchor_fd,MAX_JOURNAL)).hexdigest()!=self.anchor['sha256']:
            raise RuntimeError('Persistent anchor content changed')
        # A prior filesystem conflict is permanent until external owned recovery.
        root_handle=self.tree.directories[self.root]
        if self.tree.api:
            try:os.lstat(self.root/'NAMESPACE-UNKNOWN')
            except FileNotFoundError:pass
            else:raise RuntimeError('Namespace quarantined')
        else:
            try:os.stat('NAMESPACE-UNKNOWN',dir_fd=root_handle,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise RuntimeError('Namespace quarantined')
        for record in self.body['records']:
            directory=self.root/(record['key']+'.held')
            if self.tree.identity(self.tree.directories[directory])!=record['directory_id']:
                raise RuntimeError('Persistent scope directory anchor mismatch')

    def _quarantine(self):
        if self.tree is None:return
        try:
            fd=self.tree.open_file(self.root/'NAMESPACE-UNKNOWN',write=True,create=True)
            _append(fd,dict(state='UNKNOWN',reason='namespace_integrity_unknown'))
            self.tree.close_file(fd)
        except Exception:pass # never replace or remove a foreign/existing marker

    def acquire(self):
        if self.slots or self.closed:raise RuntimeError('Execution lease is single-use')
        root=guard_root();self.root=root;self.tree=PinnedTree(root)
        try:
            if (type(self.anchor) is not dict or set(self.anchor)!={'path','file_id','sha256'}
                    or self.anchor['path']!=str(anchor_path(root))):raise RuntimeError('Frozen persistent account anchor required')
            self.anchor_fd=self.tree.open_file(anchor_path(root))
            self.tree.check_file(self.anchor_fd,self.anchor['file_id'])
            raw=_read(self.anchor_fd,MAX_JOURNAL)
            if hashlib.sha256(raw).hexdigest()!=self.anchor['sha256']:raise RuntimeError('Frozen persistent anchor hash mismatch')
            self.body=json.loads(raw)
            if (self.body.get('kind')!='execution-anchor-1' or self.body.get('platform')!=os.name
                    or self.body.get('root')!=str(root)):raise RuntimeError('Persistent account namespace mismatch')
            self.tree.pin_directory(root)
            info=os.fstat(self.tree.directories[root]) if not self.tree.api else None
            if info and (stat.S_IMODE(info.st_mode)&0o077 or info.st_uid!=os.getuid()):
                raise RuntimeError('Private owned execution root required')
            records={record['key']:record for record in self.body['records']}
            if len(records)!=len(self.body['records']):raise RuntimeError('Duplicate anchored scope')
            for record in self.body['records']:self.tree.pin_directory(root/(record['key']+'.held'))
            self._check_namespace()
            for scope in self.scopes:
                key=_key(scope);record=records.get(key)
                if record is None or record['scope']!=scope:raise RuntimeError('Scope not independently provisioned')
                path=root/(key+'.held')/'owner.jsonl';fd=self.tree.open_file(path,write=True)
                self.tree.lock(fd);self.tree.check_file(fd,record['file_id'])
                content=_read(fd,MAX_JOURNAL);lines=content.splitlines(keepends=True)
                if (len(lines)<2 or hashlib.sha256(lines[0]).hexdigest()!=record['header_sha256']
                        or json.loads(lines[-1]).get('state')!='RELEASED'):
                    raise RuntimeError('Endpoint/model held or persistently unknown')
                self.slots.append(dict(key=key,path=path,fd=fd,file_id=record['file_id'],content=content,
                    nonce=uuid.uuid4().hex,directory=path.parent))
            self._check_namespace()
            for slot in self.slots:
                held=dict(state='HELD',nonce=slot['nonce'],pid=os.getpid())
                terminal=dict(state='RELEASED',nonce=slot['nonce'])
                if len(slot['content'])+len(_bytes(held))+len(_bytes(terminal))>MAX_JOURNAL:
                    raise RuntimeError('Execution journal capacity exhausted before admission')
            for slot in self.slots:
                _append(slot['fd'],dict(state='HELD',nonce=slot['nonce'],pid=os.getpid()))
                slot['content']=_read(slot['fd'],MAX_JOURNAL)
            return self
        except BaseException as exc:
            self.closed=True;self.unknown=True;self.tree.close()
            raise RuntimeError('Anchored endpoint/model ownership unavailable') from exc

    def _owned(self,slot):
        self.tree.check_file(slot['fd'],slot['file_id'])
        return _read(slot['fd'],MAX_JOURNAL)==slot['content']

    def finish(self,*,known):
        if self.closed:return
        self.closed=True;self.unknown=not known
        try:
            self._check_namespace()
            if any(not self._owned(slot) for slot in self.slots):
                raise RuntimeError('Execution ownership changed; preserve all state')
            for slot in self.slots:
                _append(slot['fd'],dict(state='RELEASED' if known else 'UNKNOWN',nonce=slot['nonce']))
            self._check_namespace()
            # Keep pinned ancestors/directories until after journal fd close.
            # No unlink/rmdir/path delete exists anywhere in this release path.
            for slot in self.slots:self.tree.close_file(slot['fd'])
            self._check_namespace()
            self.released=known
        except BaseException:
            self.unknown=True;self._quarantine();raise
        finally:
            try:self.tree.close()
            except BaseException:self.released=False;self.unknown=True;raise

    def status(self):
        return dict(namespace_keys=[slot['key'] for slot in self.slots],released=self.released,
            unknown=self.closed and self.unknown)
