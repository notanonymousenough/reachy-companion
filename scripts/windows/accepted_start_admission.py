"""Strict admission over the unchanged existing OperationSlot, not a new slot.

Bindings must come from separately reviewed enrollment, never current discovery.
There is no provisioning/recovery API, automatic clear or lifecycle action.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from operation_slot import OperationSlot,_identity,_plain_directory


class AdmissionDenied(ValueError):pass


@dataclass(frozen=True)
class NamespaceBinding:
    directory: Path
    parent_identity: tuple
    directory_identity: tuple
    anchor_identity: tuple
    lock_identity: tuple
    anchor_sha256: str

    def validate(self):
        path=Path(self.directory)
        if not path.is_absolute() or '..' in path.parts:
            raise AdmissionDenied('Canonical enrolled directory required')
        for value in (self.parent_identity,self.directory_identity,self.anchor_identity,self.lock_identity):
            if type(value) is not tuple or len(value)!=2 or any(type(item) is not int or item<0 for item in value):
                raise AdmissionDenied('Enrolled native identity required')
        if type(self.anchor_sha256) is not str or re.fullmatch('[0-9a-f]{64}',self.anchor_sha256) is None:
            raise AdmissionDenied('Enrolled anchor SHA256 required')
        return path


def regular_existing(path,limit):
    try:value=path.lstat()
    except OSError:raise AdmissionDenied('Existing operation file unavailable') from None
    if (stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode) or value.st_nlink!=1
            or not 0<value.st_size<=limit
            or os.name=='nt' and (not hasattr(value,'st_file_attributes') or value.st_file_attributes is None
                                 or value.st_file_attributes&0x400)):
        raise AdmissionDenied('Existing single-link non-reparse operation file required')
    return value


def preexisting(binding):
    directory=binding.validate()
    if (_plain_directory(directory.parent)!=binding.parent_identity
            or _plain_directory(directory)!=binding.directory_identity):
        raise AdmissionDenied('Enrolled operation namespace changed')
    anchor=regular_existing(directory.parent/(directory.name+'.anchor.json'),4096)
    lock=regular_existing(directory/'operation.lock',4096)
    if _identity(anchor)!=binding.anchor_identity or _identity(lock)!=binding.lock_identity:
        raise AdmissionDenied('Enrolled operation anchor or lock changed')
    # Metadata only before acquiring the mutex. Opening state here could block
    # an active Windows owner's legitimate atomic save/replace.
    regular_existing(directory/'operation-state.json',65536)


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise AdmissionDenied('Duplicate operation state key')
        result[key]=value
    return result


def reject_constant(value):raise AdmissionDenied('Nonfinite operation state')


def verify_known_idle(slot,binding):
    slot.verify_namespace()
    preexisting(binding)
    if (slot.parent_identity!=binding.parent_identity or slot.directory_identity!=binding.directory_identity
            or slot.anchor_identity!=binding.anchor_identity or _identity(os.fstat(slot.fd))!=binding.lock_identity
            or hashlib.sha256(slot.anchor_bytes).hexdigest()!=binding.anchor_sha256):
        raise AdmissionDenied('Frozen operation enrollment mismatch')
    path=slot.directory/'operation-state.json'
    before=regular_existing(path,65536)
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)
    fd=(os.open(path,flags) if slot.dirfd is None else os.open('operation-state.json',flags,dir_fd=slot.dirfd))
    try:
        opened=os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink!=1 or _identity(opened)!=_identity(before):
            raise AdmissionDenied('Operation state identity changed')
        raw=os.read(fd,65537)
    finally:os.close(fd)
    slot.verify_namespace()
    if _identity(regular_existing(path,65536))!=_identity(before) or len(raw)>65536:
        raise AdmissionDenied('Operation state replaced or oversized')
    try:value=json.loads(raw,object_pairs_hook=unique,parse_constant=reject_constant)
    except (ValueError,UnicodeError):raise AdmissionDenied('Typed known operation state required') from None
    if (type(value) is not dict or set(value)!={'schema','inflight'} or type(value['schema']) is not int
            or value['schema']!=1 or value['inflight'] is not None):
        raise AdmissionDenied('Operation is not explicitly known idle')


@contextmanager
def accepted_start_admission(binding):
    preexisting(binding) # No OperationSlot entry/lock creation on missing enrollment.
    with OperationSlot(binding.directory) as slot:
        verify_known_idle(slot,binding)
        # Caller retains the original save(inflight)/save(None) protocol and
        # must journal any actual operation before submission. Never auto-clear.
        yield slot
        verify_known_idle(slot,binding)
