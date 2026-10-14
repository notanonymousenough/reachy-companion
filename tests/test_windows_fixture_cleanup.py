"""Local synthetic algorithms plus opt-in-by-platform actual Win32 SQLite tests.

POSIX handle emulator is not a Windows filesystem/sharing/delete proof. Native
cases run only on Windows and use neutral synthetic voice receipts, no devices.
"""
import ctypes as C
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock,patch
from reachy_companion.autonomous import voice_memory_fixture as fixture
from reachy_companion.autonomous.windows_fixture_cleanup import (
    WindowsKernel,WindowsOwnedCleanup,FileId,FileInformation,Disposition,FileStandardInformation)

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('windows_cleanup_synthetic_receipts',ROOT/'tests/test_voice_memory_acceptance.py')
receipts_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(receipts_module)


class PosixHandleEmulator:
    """Exercise cleanup sequencing/identity on POSIX, not Windows API semantics."""
    def __init__(self):self.handles={};self.pending={};self.deleted=[];self.identities_seen=[]
    def validate_volume(self,path):pass
    def open(self,path,*,directory=False,delete=False):
        path=Path(path);value=os.lstat(path)
        if stat.S_ISLNK(value.st_mode) or stat.S_ISDIR(value.st_mode)!=directory or not directory and value.st_nlink!=1:
            raise ValueError('Unsupported object')
        fd=os.open(path,os.O_RDONLY);self.handles[fd]=path;return fd
    def identity(self,handle):
        value=os.fstat(handle);identity=(value.st_dev,value.st_ino);self.identities_seen.append(identity);return identity
    def delete(self,handle):
        identity=self.identity(handle);self.pending[identity]=self.handles[handle]
    def delete_pending(self,handle):return self.identity(handle) in self.pending
    def close(self,handle):
        identity=self.identity(handle);os.close(handle);del self.handles[handle]
        if identity in self.pending and not any(self.identity(fd)==identity for fd in self.handles):
            path=self.pending.pop(identity)
            current=os.lstat(path)
            if (current.st_dev,current.st_ino)!=identity:raise ValueError('Emulated deletion identity changed')
            if path.is_dir():path.rmdir()
            else:path.unlink()
            self.deleted.append(path)


class CleanupScenarios:
    def make_fixture(self):
        hub,device=receipts_module.receipts();hp=self.root/'hub.json';dp=self.root/'device.json'
        hp.write_text(json.dumps(hub));dp.write_text(json.dumps(device))
        self.directory=self.root/'owned'
        result=fixture.prepare(self.directory,hp,dp,dict(controller='controller',session_boot='session',source_boot='source'))
        fixture.operate('forget',self.directory,result['store_id'],0)
        return result['store_id']
    def cleanup(self,store):return fixture.operate('cleanup',self.directory,store,-1,exclusive_filesystem_cleanup=True)
    def test_success_with_existing_sqlite_and_closed_crt_lock(self):
        store=self.make_fixture();result=self.cleanup(store)
        self.assertTrue(result['owned_files_removed']);self.assertFalse(self.directory.exists())
        self.assertEqual(result['cleanup_backend'],'win32_local_ntfs_file_id_delete_handle')
        self.assertFalse(result['adversarial_same_uid_race_safe']);self.assertFalse(list(self.root.glob('.voice-cleanup-*')))
        self.assertTrue((self.root/'hub.json').exists());self.assertTrue((self.root/'device.json').exists())
    def test_foreign_database_and_directory_rebinding_are_preserved(self):
        for mode in ('file','directory'):
            with self.subTest(mode=mode):
                # Separate parent, receipts and fixture for each scenario.
                self.root=self.root/mode;self.root.mkdir();store=self.make_fixture();original=WindowsOwnedCleanup.after_sqlite_close
                saved=self.root/'saved'
                def replace(owner):
                    original(owner) # SQLite and CRT lock are CLOSED: Win32 rename is now admissible.
                    if mode=='file':(self.directory/'memory.sqlite').rename(saved)
                    else:
                        self.directory.rename(saved);self.directory.mkdir();(self.directory/'operator.lock').write_bytes(b'FOREIGN_LOCK')
                    (self.directory/'memory.sqlite').write_bytes(b'FOREIGN_DB')
                with patch.object(WindowsOwnedCleanup,'after_sqlite_close',replace):
                    with self.assertRaises(fixture.CleanupOwnershipConflict):self.cleanup(store)
                self.assertEqual((self.directory/'memory.sqlite').read_bytes(),b'FOREIGN_DB');self.assertTrue(saved.exists())
                if mode=='directory':self.assertEqual((self.directory/'operator.lock').read_bytes(),b'FOREIGN_LOCK')
                else:self.assertTrue((self.directory/'operator.lock').exists())
    def test_replacement_after_detach_preserves_every_object_without_deletion(self):
        store=self.make_fixture();rename=os.rename;injected=[False]
        def race(source,target,*args,**kwargs):
            result=rename(source,target,*args,**kwargs)
            if Path(target).name=='fixture' and not injected[0]:
                injected[0]=True;target=Path(target)
                rename(target/'memory.sqlite',self.root/'saved.sqlite');(target/'memory.sqlite').write_bytes(b'FOREIGN_AFTER_DETACH')
            return result
        with patch('reachy_companion.autonomous.windows_fixture_cleanup.os.rename',side_effect=race):
            with self.assertRaises(fixture.CleanupOwnershipConflict) as error:self.cleanup(store)
        quarantine=Path(error.exception.preserved_path)
        self.assertEqual((quarantine/'fixture'/'memory.sqlite').read_bytes(),b'FOREIGN_AFTER_DETACH')
        self.assertTrue((quarantine/'fixture'/'operator.lock').exists());self.assertTrue((self.root/'saved.sqlite').exists())
    def test_identity_mismatch_in_delete_handle_preserves_all_tokens(self):
        store=self.make_fixture();checked=WindowsOwnedCleanup.checked_handle;injected=[False]
        def race(owner,path,pinned,**kwargs):
            if kwargs.get('delete') and not injected[0]:
                injected[0]=True;Path(path).rename(self.root/'saved-token');Path(path).write_bytes(b'FOREIGN_TOKEN')
            return checked(owner,path,pinned,**kwargs)
        with patch.object(WindowsOwnedCleanup,'checked_handle',race):
            with self.assertRaises(fixture.CleanupOwnershipConflict) as error:self.cleanup(store)
        quarantine=Path(error.exception.preserved_path)
        self.assertTrue(any(path.is_file() and path.read_bytes()==b'FOREIGN_TOKEN' for path in quarantine.rglob('*')))
        self.assertEqual(len(list(quarantine.glob('owned-*'))),3);self.assertTrue((self.root/'saved-token').exists())


@unittest.skipUnless(os.name=='posix','POSIX emulator only; no native Windows proof')
class SyntheticWindowsCleanupTests(CleanupScenarios,unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.api=PosixHandleEmulator();api=self.api
        class Owner(WindowsOwnedCleanup):
            @staticmethod
            def platform_check():pass
            def __init__(self,directory):super().__init__(directory,kernel=api)
        patcher=patch.object(fixture,'cleanup_class',return_value=Owner);patcher.start();self.addCleanup(patcher.stop)
    def tearDown(self):self.assertFalse(self.api.handles)
    def test_unsupported_volume_fails_before_lock(self):
        store=self.make_fixture()
        with patch.object(self.api,'validate_volume',side_effect=ValueError('Unsupported volume')):
            with self.assertRaises(ValueError):self.cleanup(store)
        self.assertTrue((self.directory/'memory.sqlite').exists());self.assertFalse((self.directory/'operator.lock').exists())
    def test_delete_open_denied_preserves_all_tokens(self):
        store=self.make_fixture();opening=self.api.open
        def denied(*args,**kwargs):
            if kwargs.get('delete'):raise PermissionError('Sharing/capability denied')
            return opening(*args,**kwargs)
        with patch.object(self.api,'open',side_effect=denied):
            with self.assertRaises(fixture.CleanupOwnershipConflict) as error:self.cleanup(store)
        self.assertFalse(self.api.deleted);self.assertEqual(len(list(Path(error.exception.preserved_path).glob('owned-*'))),3)
    def test_sqlite_pending_journal_is_released_by_original_handle_before_reopening_path(self):
        directory=self.root/'journal-fixture';directory.mkdir();(directory/'memory.sqlite').write_bytes(b'owned')
        (directory/'memory.sqlite-wal').write_bytes(b'owned-journal')
        owner=WindowsOwnedCleanup(directory,kernel=self.api)
        try:
            handle=owner.files['memory.sqlite-wal'];self.api.delete(handle)
            owner.after_sqlite_close()
            self.assertNotIn('memory.sqlite-wal',owner.files);self.assertFalse((directory/'memory.sqlite-wal').exists())
            self.assertEqual((directory/'memory.sqlite').read_bytes(),b'owned')
        finally:owner.close()


@unittest.skipUnless(os.name=='nt','Requires actual Windows kernel/local fixed NTFS/operator-only parent ACL')
class NativeWindowsCleanupTests(CleanupScenarios,unittest.TestCase):
    def setUp(self):
        # Runner supplies an operator-only parent on actual local fixed NTFS.
        parent=os.environ.get('REACHY_WINDOWS_CLEANUP_TEST_PARENT')
        if not parent:raise RuntimeError('Native proof requires REACHY_WINDOWS_CLEANUP_TEST_PARENT')
        self.tmp=tempfile.TemporaryDirectory(dir=parent,prefix='reachy-neutral-cleanup-')
        self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        WindowsKernel().validate_volume(self.root)


class Win32AdapterTests(unittest.TestCase):
    def test_pending_delete_is_queried_on_original_handle_without_reopen(self):
        kernel=WindowsKernel.__new__(WindowsKernel);kernel.lib=Mock()
        def standard(handle,kind,value,size):
            self.assertEqual((handle,kind,size),(321,1,24))
            C.cast(value,C.POINTER(FileStandardInformation)).contents.delete_pending=1;return 1
        kernel.lib.GetFileInformationByHandleEx.side_effect=standard
        self.assertTrue(kernel.delete_pending(321));kernel.lib.CreateFileW.assert_not_called()
    def test_native_fixed_width_layout_access_sharing_flags_and_handle_deletion(self):
        self.assertEqual(C.sizeof(FileId),24);self.assertEqual(FileId.identifier.offset,8)
        self.assertEqual(C.sizeof(FileInformation),52);self.assertEqual(C.sizeof(Disposition),1)
        self.assertEqual(C.sizeof(FileStandardInformation),24);self.assertEqual(FileStandardInformation.delete_pending.offset,20)
        kernel=WindowsKernel.__new__(WindowsKernel);kernel.lib=Mock()
        kernel.lib.CreateFileW.return_value=123
        def fileid(handle,kind,value,size):
            self.assertEqual(kind,18);identity=C.cast(value,C.POINTER(FileId));identity.contents.volume=77
            identity.contents.identifier[0]=5;return 1
        def ordinary(handle,value):
            info=C.cast(value,C.POINTER(FileInformation));info.contents.attributes=0;info.contents.links=1;return 1
        kernel.lib.GetFileInformationByHandleEx.side_effect=fileid;kernel.lib.GetFileInformationByHandle.side_effect=ordinary
        handle=kernel.open('fixture');args=kernel.lib.CreateFileW.call_args.args
        self.assertEqual(args[1:3],(0x80,7));self.assertEqual(args[4:6],(3,0x00200000))
        kernel.close(handle);kernel.open('fixture',delete=True)
        self.assertEqual(kernel.lib.CreateFileW.call_args.args[1],0x10080)
        kernel.delete(handle);args=kernel.lib.SetFileInformationByHandle.call_args.args
        self.assertEqual(args[:2],(123,4));self.assertEqual(args[3],1)
        self.assertEqual(C.cast(args[2],C.POINTER(Disposition)).contents.delete,1)
    def test_reparse_and_multiple_links_fail_closed(self):
        for attributes,links in ((0x400,1),(0,2)):
            kernel=WindowsKernel.__new__(WindowsKernel);kernel.lib=Mock();kernel.lib.CreateFileW.return_value=123
            with patch.object(kernel,'info',return_value=((77,b'x'*16),attributes,links)):
                with self.assertRaises(ValueError):kernel.open('fixture')
            kernel.lib.CloseHandle.assert_called_once_with(123)


if __name__=='__main__':unittest.main()
