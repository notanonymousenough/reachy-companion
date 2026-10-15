"""Pinned filesystem primitives for execution journals; no path deletion."""
import os
from pathlib import Path
import stat


class PinnedTree:
    def __init__(self,root):
        self.root=Path(root);self.directories={};self.files={};self.api=None
        if not self.root.is_absolute():raise ValueError('Absolute execution root required')
        if os.name=='nt':
            from reachy_companion.autonomous.windows_fixture_cleanup import WindowsKernel
            self.api=WindowsKernel();self.api.validate_volume(self.root)
        elif not hasattr(os,'O_NOFOLLOW') or not os.supports_dir_fd:
            raise ValueError('Anchored filesystem operations unavailable')

    def _win_open(self,path,*,directory=False,write=False,attributes=False,create=False):
        import ctypes
        access=0x80 if directory or attributes else 0x80000000|(0x40000000 if write else 0)
        share=3 if directory or attributes else 1 # never SHARE_DELETE; journals also deny foreign WRITE
        flags=0x00200000|(0x02000000 if directory else 0)
        handle=self.api.lib.CreateFileW(str(path),access,share,None,1 if create else 3,flags,None)
        if handle is None or handle==ctypes.c_void_p(-1).value:self.api.failed()
        try:
            _,attributes,links=self.api.info(handle)
            if attributes&0x400 or bool(attributes&0x10)!=directory or not directory and links!=1:
                raise ValueError('Non-reparse directory or single-link file required')
            return handle
        except BaseException:self.api.close(handle);raise

    def identity(self,handle):
        if self.api:
            volume,identifier=self.api.identity(handle)
            return [volume,identifier.hex()]
        value=os.fstat(handle)
        return [value.st_dev,value.st_ino]

    def pin_directory(self,path):
        path=Path(path)
        if path in self.directories:return self.directories[path]
        parent=None
        if path.parent!=path:parent=self.pin_directory(path.parent)
        if self.api:handle=self._win_open(path,directory=True)
        else:
            flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
            handle=os.open(str(path) if parent is None else path.name,flags,
                **({} if parent is None else {'dir_fd':parent}))
        self.directories[path]=handle
        return handle

    def check_directories(self):
        for path,handle in self.directories.items():
            if self.api:
                probe=self._win_open(path,directory=True)
                try:current=self.identity(probe)
                finally:self.api.close(probe)
            else:
                parent=self.directories.get(path.parent)
                value=os.stat(str(path) if path.parent==path else path.name,follow_symlinks=False,
                    **({} if path.parent==path else {'dir_fd':parent}))
                if not stat.S_ISDIR(value.st_mode):raise RuntimeError('Directory rebound or symlinked')
                current=[value.st_dev,value.st_ino]
            if current!=self.identity(handle):raise RuntimeError('Directory namespace identity changed')

    def open_file(self,path,*,write=False,create=False):
        path=Path(path);parent=self.pin_directory(path.parent)
        if self.api:
            native=self._win_open(path,write=write,create=create)
            import msvcrt
            try:fd=msvcrt.open_osfhandle(native,(os.O_RDWR if write else os.O_RDONLY)|os.O_BINARY)
            except BaseException:self.api.close(native);raise
        else:
            flags=(os.O_RDWR if write else os.O_RDONLY)|os.O_NOFOLLOW
            if create:flags|=os.O_CREAT|os.O_EXCL
            fd=os.open(path.name,flags,0o600,dir_fd=parent)
        try:
            value=os.fstat(fd)
            if not stat.S_ISREG(value.st_mode) or value.st_nlink!=1:raise ValueError('Single-link journal/anchor required')
            self.files[fd]=path
            return fd
        except BaseException:os.close(fd);raise

    def file_identity(self,fd):
        if self.api:
            import msvcrt
            return self.identity(msvcrt.get_osfhandle(fd))
        return self.identity(fd)

    def check_file(self,fd,expected):
        path=self.files[fd]
        if self.file_identity(fd)!=expected:raise RuntimeError('Pinned file identity changed')
        if self.api:
            # Existing no-share-delete handle prevents name replacement.
            native=self._win_open(path,attributes=True)
            try:current=self.identity(native)
            finally:self.api.close(native)
        else:
            value=os.stat(path.name,dir_fd=self.directories[path.parent],follow_symlinks=False)
            if not stat.S_ISREG(value.st_mode) or value.st_nlink!=1:raise RuntimeError('Journal rebound or linked')
            current=[value.st_dev,value.st_ino]
        if current!=expected:raise RuntimeError('Journal namespace identity changed')

    def mkdir(self,path):
        path=Path(path);parent=self.pin_directory(path.parent)
        if self.api:os.mkdir(path,0o700) # ancestor handles forbid rebind during provision
        else:os.mkdir(path.name,0o700,dir_fd=parent)
        return self.pin_directory(path)

    def lock(self,fd):
        if not self.api:
            import fcntl
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Windows write handle is exclusive against every other writer, and
        # all directory/anchor/journal handles omit SHARE_DELETE.

    def close_file(self,fd):
        self.files.pop(fd,None);os.close(fd)

    def close(self):
        errors=[]
        for fd in list(self.files):
            try:self.close_file(fd)
            except BaseException as exc:errors.append(exc)
        for handle in reversed(list(self.directories.values())):
            try:
                if self.api:self.api.close(handle)
                else:os.close(handle)
            except BaseException as exc:errors.append(exc)
        self.directories.clear()
        if errors:raise RuntimeError('Pinned namespace handle cleanup unknown') from errors[0]
