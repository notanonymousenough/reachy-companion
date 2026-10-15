"""Finite local NTFS cleanup under exclusive source/parent/quarantine authority.

Win32 attribute handles pin identity without requesting DELETE during SQLite
use. No import opens handles. No path-only unlink, OS fallback or ACL mutation.
"""
import ctypes as C
import os
from pathlib import Path,PureWindowsPath
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


class RenameInformation(C.Structure):
    # WCHAR is always UTF-16 on Windows, including tests hosted on POSIX.
    _fields_=[('replace',C.c_uint32),('root',C.c_void_p),('length',C.c_uint32),('name',C.c_uint16*1)]


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
    def open(self,path,*,directory=False,delete=False,share=7,traverse=False):
        # Attribute-only access permits SQLite READ/WRITE handles which do not
        # share DELETE. All our pins share deletion so journals can close/remove.
        if traverse and not directory:raise ValueError('Rename target root must be a directory')
        access=0x80|(0x10000 if delete else 0)|(0x20 if traverse else 0) # attributes | DELETE | FILE_TRAVERSE
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
    def rename(self,handle,directory,name,*,directory_path):
        if (type(name) is not str or not name or len(name)>128 or name in ('.','..')
                or any(c in name for c in '/\\:\x00')):raise ValueError('Simple quarantine component required')
        raw=str(directory_path).replace('/','\\');root=PureWindowsPath(raw)
        if (not root.is_absolute() or len(root.drive)!=2 or root.drive[1]!=':' or not root.drive[0].isalpha()
                or ':' in raw[2:] or '\x00' in raw or '..' in root.parts or raw!=str(root)):
            raise ValueError('Canonical local absolute rename target root required')
        self.validate_volume(str(root))
        source_id=self.identity(handle);root_id=self.identity(directory)
        if source_id[0]!=root_id[0]:raise CleanupOwnershipConflict('Cross-volume rename denied')
        target=self.open(str(root),directory=True,traverse=True)
        try:
            if self.identity(target)!=root_id:raise CleanupOwnershipConflict('Rename target root replaced')
        finally:self.close(target)
        # Actual Win32 class3 rejects non-NULL RootDirectory on the target OS.
        # Keep the verified source handle; resolve ONLY the absolute destination
        # under the existing exclusive parent/quarantine namespace contract.
        encoded=str(root/name).encode('utf-16-le')
        size=max(C.sizeof(RenameInformation),RenameInformation.name.offset+len(encoded)+2)
        buffer=C.create_string_buffer(size);value=RenameInformation.from_buffer(buffer)
        value.replace=0;value.root=None;value.length=len(encoded)
        C.memmove(C.addressof(buffer)+RenameInformation.name.offset,encoded,len(encoded))
        if not self.lib.SetFileInformationByHandle(handle,3,buffer,size):self.failed()
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
            self.original_directory_id=self.api.identity(self.directory)
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
    def verify_transfer(self,remaining,tokens,*,detached=False):
        for parent,handle in self.ancestors:self.check(parent,handle,directory=True)
        self.check(self.location,self.directory,directory=True)
        self.check(self.quarantine,self.quarantine_handle,directory=True)
        if set(os.listdir(self.location))!=set(remaining):raise CleanupOwnershipConflict('Source remaining set changed')
        expected={token.name for _,token in tokens}|({'fixture'} if detached else set())
        if set(os.listdir(self.quarantine))!=expected:raise CleanupOwnershipConflict('Quarantine entries changed')
        for name in remaining:self.check(self.location/name,self.files[name])
        for name,token in tokens:self.check(token,self.files[name])
    def original_reused(self):
        # Only a confirmed detached original plus a DISTINCT FileID is reuse.
        # Unknown lookup is an error, never absence; no Path.exists suppression.
        try:handle=self.api.open(self.path,directory=True)
        except FileNotFoundError:return False
        try:
            if self.api.identity(handle)==self.api.identity(self.directory):
                raise CleanupOwnershipConflict('Original directory still bound at source')
            return True
        finally:self.api.close(handle)
    def remove(self):
        names=self.verify(source_name=True)
        if set(names)!=set(self.files):raise CleanupOwnershipConflict('Unresolved closed-SQLite journal pins')
        self.quarantine=self.path.parent/('.voice-cleanup-'+uid());self.quarantine.mkdir(mode=0o700)
        handles=[];tokens=[];remaining=set(names);primary=None
        try:
            self.quarantine_handle=self.api.open(self.quarantine,directory=True,traverse=True)
            self.verify_transfer(remaining,tokens)
            # Windows denies ancestor-directory rename with open child handles.
            # Retain ALL pins: move each original file by its checked handle first.
            for name in sorted(names):
                self.verify_transfer(remaining,tokens)
                handle=self.checked_handle(self.location/name,self.files[name],delete=True);handles.append(handle)
                token=self.quarantine/('owned-'+uid())
                self.api.rename(handle,self.quarantine_handle,token.name,directory_path=self.quarantine)
                remaining.remove(name);tokens.append((name,token))
                self.verify_transfer(remaining,tokens)
            # Empty source only; original directory FileID remains authoritative.
            directory_delete=self.checked_handle(self.location,self.directory,directory=True,delete=True)
            handles.append(directory_delete);self.verify_transfer(remaining,tokens)
            self.api.rename(directory_delete,self.quarantine_handle,'fixture',directory_path=self.quarantine)
            self.location=self.quarantine/'fixture'
            self.verify_transfer(set(),tokens,detached=True)
            self.original_reused() # deny unknown/new source lookup BEFORE any deletion
            # Full final delete set, including both directories, BEFORE first delete.
            final=[]
            for name,token in tokens:
                handle=self.checked_handle(token,self.files[name],delete=True);handles.append(handle)
                final.append((name,token,handle))
            quarantine_delete=self.checked_handle(self.quarantine,self.quarantine_handle,directory=True,delete=True)
            handles.append(quarantine_delete)
            self.verify_transfer(set(),tokens,detached=True)
            for name,token,handle in final:
                if self.api.identity(handle)!=self.api.identity(self.files[name]):raise CleanupOwnershipConflict('Delete set changed')
            if (self.api.identity(directory_delete)!=self.api.identity(self.directory)
                    or self.api.identity(quarantine_delete)!=self.api.identity(self.quarantine_handle)):
                raise CleanupOwnershipConflict('Delete directory set changed')
            # Commit deletion only after complete transfer and final set verification.
            for name,token,handle in final:self.api.delete(handle)
            # Close all file DELETE/rename handles and pins before empty dirs delete.
            file_handles=[h for h in handles if h not in (directory_delete,quarantine_delete)]
            for handle in file_handles:self.api.close(handle);handles.remove(handle)
            for name in list(self.files):self.api.close(self.files.pop(name))
            if os.listdir(self.location):raise CleanupOwnershipConflict('Detached directory no longer empty')
            self.api.delete(directory_delete);self.api.close(self.directory);self.directory=None
            self.api.close(directory_delete);handles.remove(directory_delete)
            if os.listdir(self.quarantine):raise CleanupOwnershipConflict('Quarantine not empty after owned deletion')
            self.api.delete(quarantine_delete);self.api.close(self.quarantine_handle);self.quarantine_handle=None
            self.api.close(quarantine_delete);handles.remove(quarantine_delete)
            # Keep original FileID as metadata after its last handle is closed.
            reused=self.original_reused_after_close()
        except BaseException as exc:
            primary=exc
            raise CleanupOwnershipConflict('Windows cleanup preserved remaining locations',str(self.quarantine)) from exc
        finally:
            errors=[]
            while handles:
                handle=handles.pop()
                if primary is not None:close_after_error(primary,lambda:self.api.close(handle))
                else:
                    try:self.api.close(handle)
                    except BaseException as exc:errors.append(exc)
            if errors:raise errors[0]
        return dict(owned_files_removed=True,cleanup_contract='exclusive_private_quarantine',
            cleanup_backend='win32_local_ntfs_file_id_delete_handle',adversarial_same_uid_race_safe=False,
            original_path_reused=reused)
    def original_reused_after_close(self):
        try:handle=self.api.open(self.path,directory=True)
        except FileNotFoundError:return False
        try:
            if self.api.identity(handle)==self.original_directory_id:raise CleanupOwnershipConflict('Original source identity reappeared')
            return True
        finally:self.api.close(handle)
    def release_lock(self,lock_fd):return # failure preserves original lock/quarantine
    def close(self):
        errors=[]
        def attempt(handle):
            try:self.api.close(handle)
            except BaseException as exc:errors.append(exc)
        while self.files:
            _,handle=self.files.popitem();attempt(handle)
        for attribute in ('directory','quarantine_handle'):
            handle=getattr(self,attribute,None)
            if handle is not None:setattr(self,attribute,None);attempt(handle)
        while self.ancestors:
            _,handle=self.ancestors.pop();attempt(handle)
        if errors:
            for error in errors[1:]:errors[0].add_note('Additional owned handle close: '+str(error))
            raise errors[0]
