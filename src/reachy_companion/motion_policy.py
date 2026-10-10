"""Durable operator motor/quiet/privacy policy, independent of microphone state."""
import os
from pathlib import Path
import tempfile
import threading
from .autonomous.contracts import decode


class MotionPolicy:
    def __init__(self,path):
        self.path=Path(path)
        self.lock=threading.RLock()
        self.failed=False
        self.owner_id=None

    def owned_snapshot(self):
        with self.lock:return self.snapshot(),self.owner_id

    def snapshot(self):
        with self.lock:
            try:
                if self.failed:raise RuntimeError('Policy persistence failed')
                if not self.path.exists():return dict(motor_enabled=False,quiet=False,privacy_all=False,epoch=0)
                raw=self.path.read_bytes()
                if len(raw)>4096:raise ValueError('Policy bound')
                value=decode(raw)
                if (not isinstance(value,dict) or set(value)!={'motor_enabled','quiet','privacy_all','epoch'}
                        or any(type(value[key]) is not bool for key in ('motor_enabled','quiet','privacy_all'))
                        or type(value['epoch']) is not int or not 0<=value['epoch']<2**63):
                    raise ValueError('Operator policy unknown')
                return value
            except Exception:
                return dict(motor_enabled=False,quiet=True,privacy_all=True,epoch=None)

    def save(self,value,*,expected_epoch=None,owner_id=None,expected_owner_id=None):
        if (not isinstance(value,dict) or set(value)!={'motor_enabled','quiet','privacy_all'}
                or any(type(item) is not bool for item in value.values())):
            raise ValueError('Expected boolean motor_enabled/quiet/privacy_all')
        if expected_epoch is not None and (type(expected_epoch) is not int or not 0<=expected_epoch<2**63):
            raise ValueError('Exact expected policy epoch required')
        for owner in (owner_id,expected_owner_id):
            if owner is not None and (not isinstance(owner,str) or not 1<=len(owner)<=128 or expected_epoch is None):
                raise ValueError('Bounded policy owner requires epoch CAS')
        with self.lock:
            before=self.snapshot()
            if before['epoch'] is None or before['epoch']>=2**63-1:raise RuntimeError('Policy epoch unavailable')
            if ((expected_epoch is not None and expected_epoch!=before['epoch'])
                    or (expected_owner_id is not None and expected_owner_id!=self.owner_id)):
                raise RuntimeError('Policy authority changed')
            after=dict(value,epoch=before['epoch']+1)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            fd,name=tempfile.mkstemp(prefix=self.path.name+'.',dir=self.path.parent)
            temporary=Path(name)
            try:
                import json
                with os.fdopen(fd,'w') as output:
                    json.dump(after,output);output.flush();os.fsync(output.fileno())
                temporary.replace(self.path)
                directory=os.open(self.path.parent,os.O_RDONLY)
                try:os.fsync(directory)
                finally:os.close(directory)
            except BaseException:
                self.failed=True;self.owner_id=None
                raise
            finally:temporary.unlink(missing_ok=True)
            self.owner_id=owner_id
            return after
