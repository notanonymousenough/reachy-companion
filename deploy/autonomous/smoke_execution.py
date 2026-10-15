"""Account-local cooperative cross-process model ownership for finite probes.

No stale-owner reclaim, TTL, reset or automatic unknown recovery. All runs use
the same home-root namespace, independent of output paths and instance reloads.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit
import uuid
import re


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
def _identity(info):return info.st_dev,info.st_ino


class ExecutionLease:
    def __init__(self,scopes):
        self.scopes=scopes;self.slots=[];self.closed=False;self.unknown=False;self.released=False;self.producer_started=False

    def acquire(self):
        if self.slots or self.closed:raise RuntimeError('Execution lease is single-use')
        root=guard_root();root.mkdir(mode=0o700,exist_ok=True)
        info=root.lstat()
        if not stat.S_ISDIR(info.st_mode) or (os.name!='nt' and stat.S_IMODE(info.st_mode)&0o077):
            raise RuntimeError('Private stable execution root required')
        try:
            for scope in self.scopes:
                key=hashlib.sha256(_bytes(scope)).hexdigest();directory=root/(key+'.held')
                directory.mkdir(mode=0o700) # actual cross-process exclusion, not an existence-only check
                slot=dict(directory=directory,directory_id=_identity(directory.lstat()),key=key,fd=None)
                self.slots.append(slot)
                path=directory/'owner.jsonl';fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
                slot.update(fd=fd,path=path,file_id=_identity(os.fstat(fd)))
                content=_bytes(dict(scope=scope,nonce=uuid.uuid4().hex,pid=os.getpid(),state='HELD'))
                os.write(fd,content);os.fsync(fd);slot['content']=content
            return self
        except FileExistsError as exc:
            self.finish(known=True)
            raise RuntimeError('Endpoint/model execution held or persistently unknown') from exc
        except BaseException:
            self.finish(known=False);raise

    def _owned(self,slot):
        return (_identity(slot['directory'].lstat())==slot['directory_id']
            and _identity(slot['path'].lstat())==slot['file_id']
            and _identity(os.fstat(slot['fd']))==slot['file_id']
            and slot['path'].read_bytes()==slot['content'])

    def finish(self,*,known):
        if self.closed:return
        self.closed=True;self.unknown=not known
        try:
            if any(slot['fd'] is None or not self._owned(slot) for slot in self.slots):
                raise RuntimeError('Execution ownership changed; preserve all state')
            if not known:
                for slot in self.slots:
                    event=_bytes(dict(state='UNKNOWN'))
                    os.write(slot['fd'],event);os.fsync(slot['fd']);slot['content']+=event
            else:
                for slot in reversed(self.slots):
                    os.close(slot['fd']);slot['fd']=None
                    # Cooperative private-root contract; identities were checked
                    # before any unlink. No foreign-state recovery is attempted.
                    slot['path'].unlink();slot['directory'].rmdir()
                self.released=True
        except BaseException:
            self.unknown=True;raise
        finally:
            for slot in self.slots:
                if slot['fd'] is not None:os.close(slot['fd']);slot['fd']=None

    def status(self):
        return dict(namespace_keys=[slot['key'] for slot in self.slots],released=self.released,
            unknown=self.closed and self.unknown)
