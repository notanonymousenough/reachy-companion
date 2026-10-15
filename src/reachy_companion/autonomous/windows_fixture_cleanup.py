"""Finite local NTFS cleanup under exclusive source/parent/quarantine authority.

Win32 attribute handles pin identity without requesting DELETE during SQLite
use. No import opens handles. No path-only unlink, OS fallback or ACL mutation.
"""
import ctypes as C
import os
from pathlib import Path
from .contracts import uid
from .voice_memory_fixture import FILES,CleanupOwnershipConflict


def close_after_error(primary,closer):
    try:closer()
    except BaseException as secondary:
        primary.add_note('Windows lock finalization: '+type(secondary).__name__+': '+str(secondary))


class FileId(C.Structure):
    _fields_=[('volume',C.c_uint64),('identifier',C.c_ubyte*16)]


class FileTime(C.Structure):
    _fields_=[('low',C.c_uint32),('high',C.c_uint32)]


class FileInformation(C.Structure):
    _fields_=[('attributes',C.c_uint32),('creation',FileTime),('access',FileTime),('write',FileTime),
        ('volume',C.c_uint32),('size_high',C.c_uint32),('size_low',C.c_uint32),('links',C.c_uint32),
        ('index_high',C.c_uint32),('index_low',C.c_uint32)]


class Disposition(C.Structure):
    _fields_=[('delete',C.c_ubyte)]


class FileStandardInformation(C.Structure):
    _fields_=[('allocation',C.c_int64),('end',C.c_int64),('links',C.c_uint32),
        ('delete_pending',C.c_ubyte),('directory',C.c_ubyte)]


class WindowsKernel:
    """Documented kernel32 API only; unsupported IDs/volumes fail closed."""
    def __init__(self):
        if os.name!='nt' or not hasattr(C,'WinDLL'):raise ValueError('Native Windows cleanup unavailable')
        self.lib=C.WinDLL('kernel32',use_last_error=True)
        handle=C.c_void_p;dword=C.c_uint32;boolean=C.c_int32
        signatures=dict(
            CreateFileW=(handle,[C.c_wchar_p,dword,dword,handle,dword,dword,handle]),
            CloseHandle=(boolean,[handle]),
            GetFileInformationByHandleEx=(boolean,[handle,C.c_int32,handle,dword]),
            GetFileInformationByHandle=(boolean,[handle,C.POINTER(FileInformation)]),
            SetFileInformationByHandle=(boolean,[handle,C.c_int32,handle,dword]),
            GetDriveTypeW=(dword,[C.c_wchar_p]),
            GetVolumeInformationW=(boolean,[C.c_wchar_p,C.c_wchar_p,dword,C.POINTER(dword),C.POINTER(dword),
                C.POINTER(dword),C.c_wchar_p,dword]))
        for name,(result,args) in signatures.items():
            fn=getattr(self.lib,name);fn.restype=result;fn.argtypes=args
    @staticmethod
    def failed():raise C.WinError(C.get_last_error())
    def validate_volume(self,path):
        # Restrict plain local drive paths, excluding UNC/device/ADS syntax.
        path=Path(path).absolute();drive=path.drive
        if len(drive)!=2 or drive[1]!=':' or not drive[0].isalpha() or ':' in str(path)[2:]:
            raise ValueError('Plain local drive path required')
        root=drive+'\\'
        if self.lib.GetDriveTypeW(root)!=3:raise ValueError('Local fixed NTFS required')
        filesystem=C.create_unicode_buffer(32)
        if not self.lib.GetVolumeInformationW(root,None,0,None,None,None,filesystem,len(filesystem)):self.failed()
        if filesystem.value.upper()!='NTFS':raise ValueError('NTFS cleanup only')
    def open(self,path,*,directory=False,delete=False,share=7):
        # Attribute-only access permits SQLite READ/WRITE handles which do not
        # share DELETE. All our pins share deletion so journals can close/remove.
        access=0x80|(0x10000 if delete else 0) # FILE_READ_ATTRIBUTES | DELETE
        flags=0x00200000|(0x02000000 if directory else 0) # OPEN_REPARSE_POINT | BACKUP_SEMANTICS
        value=self.lib.CreateFileW(str(path),access,share,None,3,flags,None)
        if value is None or value==C.c_void_p(-1).value:self.failed()
        try:
            identity,attributes,links=self.info(value)
            if attributes&0x400 or bool(attributes&0x10)!=directory or not directory and links!=1:
                raise ValueError('Non-reparse directory or single-link file required')
            return value
        except BaseException as primary:
            close_after_error(primary,lambda:self.close(value));raise
    def info(self,handle):
        value=FileId();ordinary=FileInformation()
        if not self.lib.GetFileInformationByHandleEx(handle,18,C.byref(value),C.sizeof(value)):self.failed()
        if not self.lib.GetFileInformationByHandle(handle,C.byref(ordinary)):self.failed()
        identifier=bytes(value.identifier)
        if not any(identifier):raise ValueError('Nonzero native file identity required')
        return (value.volume,identifier),ordinary.attributes,ordinary.links
    def identity(self,handle):return self.info(handle)[0]
    def delete_pending(self,handle):
        value=FileStandardInformation()
        if not self.lib.GetFileInformationByHandleEx(handle,1,C.byref(value),C.sizeof(value)):self.failed()
        return bool(value.delete_pending)
    def delete(self,handle):
        value=Disposition(1)
        if not self.lib.SetFileInformationByHandle(handle,4,C.byref(value),C.sizeof(value)):self.failed()
    def close(self,handle):
        if not self.lib.CloseHandle(handle):self.failed()

    def create_operation_lock(self,path):
        # CREATE_NEW, DELETE authority on the ORIGINAL handle, and no sharing.
        # No close/reopen, pathname unlink or delete-on-close at acquisition:
        # a crashed/unknown operation deliberately leaves its marker behind.
        value=self.lib.CreateFileW(str(path),0x40010080,0,None,1,0x00200000,None)
        if value is None or value==C.c_void_p(-1).value:self.failed()
        try:
            _,attributes,links=self.info(value)
            if attributes&(0x400|0x10) or links!=1:raise ValueError('Single-link regular operation lock required')
            return value
        except BaseException as primary:
            close_after_error(primary,lambda:self.close(value));raise


class WindowsOperationLock:
    """Transient mutex deleted through its own handle BEFORE descriptor close.

    All ancestors remain pinned without share-delete through descriptor close.
    Failure leaves the exact marker; this grants no filesystem cleanup authority.
    """
    def __init__(self,directory,*,kernel=None):
        self.api=kernel or WindowsKernel();self.path=Path(directory).absolute();self.ancestors=[]
        self.handle=None;self.fd=None;self.api.validate_volume(self.path)
        if self.path!=self.path.resolve():raise ValueError('Canonical non-reparse operation directory required')
        try:
            for parent in [*reversed(self.path.parents),self.path]:
                self.ancestors.append(self.api.open(parent,directory=True,share=3))
        except BaseException as primary:
            close_after_error(primary,self.close);raise
    def create_lock(self):
        import msvcrt
        handle=self.api.create_operation_lock(self.path/'operator.lock')
        try:fd=msvcrt.open_osfhandle(handle,os.O_WRONLY|os.O_BINARY)
        except BaseException as primary:
            close_after_error(primary,lambda:self.api.close(handle));raise
        # open_osfhandle transfers ownership: os.close(fd) is the sole closer.
        try:
            self.identity=self.api.identity(handle);self.nonce=uid()
            marker=('voice-operation-1:'+self.nonce+'\n').encode()
            if os.write(fd,marker)!=len(marker):raise OSError('Incomplete operation lock marker')
            os.fsync(fd)
        except BaseException as primary:
            close_after_error(primary,lambda:os.close(fd));raise # preserve marker
        self.handle=handle;self.fd=fd
        return fd
    def release_lock(self,fd):
        import msvcrt
        if fd!=self.fd or msvcrt.get_osfhandle(fd)!=self.handle:
            raise CleanupOwnershipConflict('Operation lock descriptor changed')
        identity,attributes,links=self.api.info(self.handle)
        if identity!=self.identity or attributes&(0x400|0x10) or links!=1:
            raise CleanupOwnershipConflict('Operation lock identity/link changed')
        self.api.delete(self.handle)
    def close(self):
        # Called AFTER the CRT fd close, including failed deletion. Never unlink.
        errors=[]
        while self.ancestors:
            try:self.api.close(self.ancestors.pop())
            except BaseException as exc:errors.append(exc)
        if errors:raise errors[0]


class WindowsOwnedCleanup:
    """Same quarantine contract, native handles and delete-on-close on Windows.

    Path enumeration/moves require exclusive source and parent authority; this
    is not a hostile same-UID or privileged-filesystem race guarantee. The
    runner must prove operator-only inherited ACLs before asserting that scope.
    """
    requires_closed_lock=True
    @staticmethod
    def platform_check():WindowsKernel()
    def __init__(self,directory,*,kernel=None):
        self.api=kernel or WindowsKernel();self.path=Path(directory).absolute();self.location=self.path
        self.files={};self.ancestors=[];self.directory=None;self.quarantine=None;self.quarantine_handle=None
        self.api.validate_volume(self.path)
        try:
            # Reject existing junction/reparse components, including ancestors.
            # The exclusive parent contract keeps these paths stable thereafter.
            for parent in reversed(self.path.parents):self.ancestors.append((parent,self.api.open(parent,directory=True)))
            self.directory=self.api.open(self.path,directory=True)
            for name in os.listdir(self.path):
                if name not in FILES:raise CleanupOwnershipConflict('Unexpected cleanup entry')
                self.files[name]=self.api.open(self.path/name)
            self.verify(source_name=True)
        except BaseException:self.close();raise
    def checked_handle(self,path,pinned,*,directory=False,delete=False):
        current=self.api.open(path,directory=directory,delete=delete)
        try:
            if self.api.identity(current)!=self.api.identity(pinned):raise CleanupOwnershipConflict('Windows fixture identity changed')
            return current
        except BaseException:self.api.close(current);raise
    def check(self,path,pinned,*,directory=False):
        self.api.close(self.checked_handle(path,pinned,directory=directory))
    def verify(self,source_name=False,allow_journals=False):
        for parent,handle in self.ancestors:self.check(parent,handle,directory=True)
        if self.quarantine_handle is not None:self.check(self.quarantine,self.quarantine_handle,directory=True)
        self.check(self.location,self.directory,directory=True)
        names=set(os.listdir(self.location))
        required=set(self.files)-{'memory.sqlite-wal','memory.sqlite-shm'}
        allowed=set(self.files)|({'memory.sqlite-wal','memory.sqlite-shm'} if allow_journals else set())
        if not required<=names or not names<=allowed:raise CleanupOwnershipConflict('Fixture entries changed')
        for name in names&set(self.files):self.check(self.location/name,self.files[name])
        return names
    def create_lock(self):
        fd=os.open(self.path/'operator.lock',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            self.files['operator.lock']=self.api.open(self.path/'operator.lock');self.verify(source_name=True)
            return fd
        except BaseException:os.close(fd);raise # retain lock for owner recovery
    def pin_journals(self):
        names=self.verify(source_name=True,allow_journals=True)
        for name in names-set(self.files):self.files[name]=self.api.open(self.location/name)
        self.verify(source_name=True)
    def after_sqlite_close(self):
        # SQLite may have marked its journals delete-pending. Reopening that
        # pathname on Windows fails until the last attribute pin is closed.
        # Query the ORIGINAL handle, never infer identity from the current path.
        self.check(self.location,self.directory,directory=True)
        for name in ('memory.sqlite-wal','memory.sqlite-shm'):
            handle=self.files.get(name)
            if handle is not None and self.api.delete_pending(handle):
                self.api.close(handle);del self.files[name]
        self.verify(source_name=True)
    def remove(self):
        self.verify(source_name=True)
        self.quarantine=self.path.parent/('.voice-cleanup-'+uid());self.quarantine.mkdir(mode=0o700)
        delete_handles=[]
        try:
            self.quarantine_handle=self.api.open(self.quarantine,directory=True)
            destination=self.quarantine/'fixture';os.rename(self.path,destination);self.location=destination
            names=self.verify();tokens=[]
            for name in sorted(names):
                token=self.quarantine/('owned-'+uid());os.rename(self.location/name,token)
                self.check(token,self.files[name]);tokens.append((name,token))
            if os.listdir(self.location):raise CleanupOwnershipConflict('New entries after detachment')
            # Acquire every identity-matched DELETE handle before any deletion.
            for name,token in tokens:
                delete_handles.append((name,token,self.checked_handle(token,self.files[name],delete=True)))
            for name,token,handle in delete_handles:
                self.api.delete(handle);self.api.close(self.files.pop(name))
            while delete_handles:
                _,_,handle=delete_handles.pop();self.api.close(handle)
            # Close removed SQLite journal pins which disappeared on SQLite close.
            while self.files:
                _,handle=self.files.popitem();self.api.close(handle)
            self.remove_directory(self.location,'directory')
            self.remove_directory(self.quarantine,'quarantine_handle')
            if self.quarantine.exists():raise CleanupOwnershipConflict('Quarantine deletion not complete')
        except BaseException as exc:
            raise CleanupOwnershipConflict('Windows cleanup preserved remaining quarantine',str(self.quarantine)) from exc
        finally:
            while delete_handles:
                _,_,handle=delete_handles.pop();self.api.close(handle)
        return dict(owned_files_removed=True,cleanup_contract='exclusive_private_quarantine',
            cleanup_backend='win32_local_ntfs_file_id_delete_handle',adversarial_same_uid_race_safe=False,
            original_path_reused=self.path.exists())
    def remove_directory(self,path,attribute):
        if os.listdir(path):raise CleanupOwnershipConflict('Directory not empty')
        handle=self.checked_handle(path,getattr(self,attribute),directory=True,delete=True)
        try:
            self.api.delete(handle);self.api.close(getattr(self,attribute));setattr(self,attribute,None)
        finally:self.api.close(handle)
        if path.exists():raise CleanupOwnershipConflict('Directory deletion not complete')
    def release_lock(self,lock_fd):return # failure preserves original lock/quarantine
    def close(self):
        for handle in self.files.values():self.api.close(handle)
        self.files.clear()
        for attribute in ('directory','quarantine_handle'):
            handle=getattr(self,attribute,None)
            if handle is not None:self.api.close(handle);setattr(self,attribute,None)
        for _,handle in self.ancestors:self.api.close(handle)
        self.ancestors.clear()
