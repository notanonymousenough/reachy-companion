"""Exact code-only OperationSlot closure. No namespace bootstrap or private state.
Caller must use separately enrolled canonical namespace; never create a second protocol.
"""
import os,stat,json,uuid
from pathlib import Path

def _identity(stat):return (stat.st_dev,stat.st_ino)

def _plain_directory(path):
 s=path.lstat()
 if path.is_symlink() or not stat.S_ISDIR(s.st_mode):raise ValueError('Operational directory type')
 if os.name=='nt' and (not hasattr(s,'st_file_attributes') or s.st_file_attributes&0x400):raise ValueError('Directory reparse state unknown/unsafe')
 return _identity(s)

class OperationSlot:
 def __init__(self,directory):
  self.directory=Path(directory);self.fd=None;self.dirfd=None;self.parentfd=None;self.anchorfd=None;self.windows_handles=[];self.anchor_name=self.directory.name+'.anchor.json';self.state_name='operation-state.json';self.anchor_bytes=None
 def _windows_fence(self):
  import ctypes
  from ctypes import wintypes
  class Info(ctypes.Structure):
   _fields_=[('attributes',wintypes.DWORD),('creation',wintypes.FILETIME),('access',wintypes.FILETIME),('write',wintypes.FILETIME),('volume',wintypes.DWORD),('size_hi',wintypes.DWORD),('size_lo',wintypes.DWORD),('links',wintypes.DWORD),('index_hi',wintypes.DWORD),('index_lo',wintypes.DWORD)]
  api=ctypes.WinDLL('kernel32',use_last_error=True);create=api.CreateFileW;create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];create.restype=wintypes.HANDLE
  info=api.GetFileInformationByHandle;info.argtypes=[wintypes.HANDLE,ctypes.POINTER(Info)];info.restype=wintypes.BOOL
  # No FILE_SHARE_DELETE: ordinary directory/ancestor rename/rebind is fenced.
  for path in list(reversed(self.directory.parents))+[self.directory]:
   _plain_directory(path);handle=create(str(path),0x80,3,None,3,0x02000000|0x00200000,None)
   if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
   self.windows_handles.append(handle);value=Info()
   if not info(handle,ctypes.byref(value)) or value.attributes&0x400:raise ValueError('Directory handle/reparse fence unavailable')
 def __enter__(self):
  try:
   self.parent_identity=_plain_directory(self.directory.parent);self.directory_identity=_plain_directory(self.directory)
   anchor_path=self.directory.parent/self.anchor_name;anchor_stat=anchor_path.lstat()
   if anchor_path.is_symlink() or not stat.S_ISREG(anchor_stat.st_mode) or anchor_stat.st_size>4096 or (os.name=='nt' and (not hasattr(anchor_stat,'st_file_attributes') or anchor_stat.st_file_attributes&0x400)):raise ValueError('Operation anchor type/reparse unsafe')
   if os.name=='nt':
    self._windows_fence();anchor=self.directory.parent/self.anchor_name
    self.anchorfd=os.open(anchor,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
   else:
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    self.parentfd=os.open(self.directory.parent,flags);self.dirfd=os.open(self.directory.name,flags,dir_fd=self.parentfd)
    self.anchorfd=os.open(self.anchor_name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.parentfd)
   self.anchor_identity=_identity(os.fstat(self.anchorfd));self.anchor_bytes=os.read(self.anchorfd,4097)
   if len(self.anchor_bytes)>4096:raise ValueError('Anchor size bound')
   anchor=json.loads(self.anchor_bytes)
   if anchor.get('schema')!=1 or tuple(anchor['directory_identity'])!=self.directory_identity or tuple(anchor['parent_identity'])!=self.parent_identity:raise ValueError('Operation directory rebound; existing anchor denies new generation')
   lock_path=self.directory/'operation.lock'
   if lock_path.exists() or lock_path.is_symlink():
    lock_stat=lock_path.lstat()
    if lock_path.is_symlink() or not stat.S_ISREG(lock_stat.st_mode) or (os.name=='nt' and (not hasattr(lock_stat,'st_file_attributes') or lock_stat.st_file_attributes&0x400)):raise ValueError('Lock reparse/type unsafe')
   self.fd=os.open(lock_path,os.O_RDWR|os.O_CREAT,0o600) if self.dirfd is None else os.open('operation.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=self.dirfd)
   if os.name=='nt':
    import msvcrt
    os.lseek(self.fd,0,os.SEEK_SET);msvcrt.locking(self.fd,msvcrt.LK_NBLCK,1)
   else:
    import fcntl
    fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   self.verify_namespace()
   if os.fstat(self.fd).st_size==0:os.write(self.fd,b'0');os.fsync(self.fd)
   return self
  except BaseException:self._close();raise
 def _close(self):
  for name in ('fd','anchorfd','dirfd','parentfd'):
   fd=getattr(self,name)
   if fd is not None:os.close(fd);setattr(self,name,None)
  if self.windows_handles:
   import ctypes
   from ctypes import wintypes
   close=ctypes.WinDLL('kernel32',use_last_error=True).CloseHandle;close.argtypes=[wintypes.HANDLE];close.restype=wintypes.BOOL
   for handle in reversed(self.windows_handles):close(handle)
   self.windows_handles=[]
 def __exit__(self,*args):self._close()
 def verify_namespace(self):
  if _plain_directory(self.directory.parent)!=self.parent_identity or _plain_directory(self.directory)!=self.directory_identity:raise ValueError('Operational namespace renamed/rebound')
  if self.dirfd is not None and (_identity(os.fstat(self.dirfd))!=self.directory_identity or _identity(os.fstat(self.parentfd))!=self.parent_identity):raise ValueError('Directory handle identity drift')
  anchor=self.directory.parent/self.anchor_name
  if anchor.is_symlink() or _identity(anchor.lstat())!=self.anchor_identity:raise ValueError('Operation anchor replaced')
  os.lseek(self.anchorfd,0,os.SEEK_SET)
  if os.read(self.anchorfd,4097)!=self.anchor_bytes:raise ValueError('Operation anchor modified')
  p=self.directory/'operation.lock'
  if p.is_symlink() or _identity(p.lstat())!=_identity(os.fstat(self.fd)):raise ValueError('Operational lock identity drift')
 def pending(self):
  self.verify_namespace()
  try:
   if self.dirfd is None:
    p=self.directory/self.state_name
    entry=p.lstat()
    if p.is_symlink() or entry.st_file_attributes&0x400:raise ValueError('Operational marker reparse/symlink')
    fd=os.open(p,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
   else:fd=os.open(self.state_name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.dirfd)
  except FileNotFoundError:self.verify_namespace();return None
  try:
   if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('Operational marker type')
   raw=os.read(fd,65537)
  finally:os.close(fd)
  self.verify_namespace()
  if len(raw)>65536:raise ValueError('Operational marker size')
  d=json.loads(raw)
  if d.get('schema')!=1:raise ValueError('Unknown operational marker')
  return d.get('inflight')
 def save(self,inflight):
  self.verify_namespace();name='state-'+uuid.uuid4().hex+'.tmp';flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
  fd=os.open(self.directory/name,flags,0o600) if self.dirfd is None else os.open(name,flags,0o600,dir_fd=self.dirfd)
  try:
   with os.fdopen(fd,'w') as f:json.dump({'schema':1,'inflight':inflight},f);f.flush();os.fsync(f.fileno())
   self.verify_namespace()
   if self.dirfd is None:os.replace(self.directory/name,self.directory/self.state_name)
   else:os.replace(name,self.state_name,src_dir_fd=self.dirfd,dst_dir_fd=self.dirfd);os.fsync(self.dirfd)
   self.verify_namespace()
  except BaseException:
   # Preserve the anchored temporary intent on unknown outcomes; never path-delete a rebound directory.
   raise
