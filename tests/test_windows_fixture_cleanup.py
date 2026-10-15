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
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
from reachy_companion.autonomous import voice_memory_fixture as fixture
from reachy_companion.autonomous.windows_fixture_cleanup import (
    WindowsKernel,WindowsOwnedCleanup,FileId,FileInformation,Disposition,FileStandardInformation,RenameInformation)

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('windows_cleanup_synthetic_receipts',ROOT/'tests/test_voice_memory_acceptance.py')
receipts_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(receipts_module)


class PosixHandleEmulator:
    """Exercise cleanup sequencing/identity on POSIX, not Windows API semantics."""
    def __init__(self):self.handles={};self.pending={};self.deleted=[];self.identities_seen=[]
    def validate_volume(self,path):pass
    def open(self,path,*,directory=False,delete=False,traverse=False):
        path=Path(path);value=os.lstat(path)
        if stat.S_ISLNK(value.st_mode) or stat.S_ISDIR(value.st_mode)!=directory or not directory and value.st_nlink!=1:
            raise ValueError('Unsupported object')
        fd=os.open(path,os.O_RDONLY);self.handles[fd]=path;return fd
    def identity(self,handle):
        value=os.fstat(handle);identity=(value.st_dev,value.st_ino);self.identities_seen.append(identity);return identity
    def delete(self,handle):
        identity=self.identity(handle);self.pending[identity]=self.handles[handle]
    def delete_pending(self,handle):return self.identity(handle) in self.pending or os.fstat(handle).st_nlink==0
    def rename(self,handle,directory,name):
        source=self.handles[handle];target=self.handles[directory]/name
        identity=self.identity(handle)
        if source.is_dir() and any(source in path.parents for path in self.handles.values()):
            raise PermissionError('Modeled Windows ancestor rename with child pins')
        if target.exists():raise FileExistsError(target)
        os.rename(source,target)
        for fd in self.handles:
            if self.identity(fd)==identity:self.handles[fd]=target
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
    def cleanup(self,store):
        self.delete_calls=[];original=WindowsOwnedCleanup.remove
        def tracked(owner):
            delete=owner.api.delete
            def record(handle):self.delete_calls.append(owner.api.identity(handle));return delete(handle)
            with patch.object(owner.api,'delete',side_effect=record):return original(owner)
        with patch.object(WindowsOwnedCleanup,'remove',tracked):
            return fixture.operate('cleanup',self.directory,store,-1,exclusive_filesystem_cleanup=True)
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
                    original(owner)
                    if mode=='file':(self.directory/'memory.sqlite').rename(saved)
                    else:
                        # Directory replacement is injected only once EMPTY: child
                        # pins have followed their files to quarantine on Windows.
                        return
                    (self.directory/'memory.sqlite').write_bytes(b'FOREIGN_DB')
                transfer=WindowsOwnedCleanup.verify_transfer;injected=[False]
                def replace_empty(owner,remaining,tokens,**kwargs):
                    if mode=='directory' and not remaining and not kwargs.get('detached') and not injected[0]:
                        injected[0]=True;self.directory.rename(saved);self.directory.mkdir()
                        (self.directory/'operator.lock').write_bytes(b'FOREIGN_LOCK');(self.directory/'memory.sqlite').write_bytes(b'FOREIGN_DB')
                    return transfer(owner,remaining,tokens,**kwargs)
                with patch.object(WindowsOwnedCleanup,'after_sqlite_close',replace),patch.object(WindowsOwnedCleanup,'verify_transfer',replace_empty):
                    with self.assertRaises(fixture.CleanupOwnershipConflict):self.cleanup(store)
                self.assertEqual((self.directory/'memory.sqlite').read_bytes(),b'FOREIGN_DB');self.assertTrue(saved.exists())
                self.assertFalse(self.delete_calls)
                if mode=='directory':self.assertEqual((self.directory/'operator.lock').read_bytes(),b'FOREIGN_LOCK')
                else:self.assertTrue((self.directory/'operator.lock').exists())
    def test_replacement_after_detach_preserves_every_object_without_deletion(self):
        store=self.make_fixture();verify=WindowsOwnedCleanup.verify_transfer;injected=[False]
        original_binding=(self.directory/'binding.json').read_bytes()
        def race(owner,remaining,tokens,**kwargs):
            if kwargs.get('detached') and not injected[0]:
                injected[0]=True;owner.location.rename(self.root/'saved-empty')
                owner.location.mkdir();(owner.location/'memory.sqlite').write_bytes(b'FOREIGN_AFTER_DETACH')
                (owner.location/'operator.lock').write_bytes(b'FOREIGN_LOCK')
            return verify(owner,remaining,tokens,**kwargs)
        with patch.object(WindowsOwnedCleanup,'verify_transfer',race):
            with self.assertRaises(fixture.CleanupOwnershipConflict) as error:self.cleanup(store)
        quarantine=Path(error.exception.preserved_path)
        self.assertTrue(injected[0]);self.assertFalse(self.delete_calls)
        self.assertEqual((quarantine/'fixture'/'memory.sqlite').read_bytes(),b'FOREIGN_AFTER_DETACH')
        self.assertEqual((quarantine/'fixture'/'operator.lock').read_bytes(),b'FOREIGN_LOCK')
        self.assertTrue((self.root/'saved-empty').is_dir())
        owned=[p.read_bytes() for p in quarantine.glob('owned-*')]
        self.assertEqual(len(owned),3);self.assertIn(original_binding,owned)
        self.assertTrue(any(data.startswith(b'SQLite format 3') for data in owned));self.assertIn(b'',owned)
    def test_identity_mismatch_in_delete_handle_preserves_all_tokens(self):
        store=self.make_fixture();checked=WindowsOwnedCleanup.checked_handle;injected=[False]
        original_binding=(self.directory/'binding.json').read_bytes()
        def race(owner,path,pinned,**kwargs):
            if kwargs.get('delete') and Path(path).name.startswith('owned-') and not injected[0]:
                injected[0]=True;Path(path).rename(self.root/'saved-token');Path(path).write_bytes(b'FOREIGN_TOKEN')
            return checked(owner,path,pinned,**kwargs)
        with patch.object(WindowsOwnedCleanup,'checked_handle',race):
            with self.assertRaises(fixture.CleanupOwnershipConflict) as error:self.cleanup(store)
        quarantine=Path(error.exception.preserved_path)
        self.assertTrue(injected[0]);self.assertFalse(self.delete_calls)
        self.assertTrue(any(path.is_file() and path.read_bytes()==b'FOREIGN_TOKEN' for path in quarantine.rglob('*')))
        self.assertEqual(len(list(quarantine.glob('owned-*'))),3);self.assertTrue((self.root/'saved-token').exists())
        # Sorted first original is binding.json; save and preserve its exact bytes.
        self.assertEqual((self.root/'saved-token').read_bytes(),original_binding)

    def test_partial_transfer_failure_preserves_moved_and_remaining_original_bytes(self):
        store=self.make_fixture();verify=WindowsOwnedCleanup.verify_transfer;injected=[False];before={}
        def fail(owner,remaining,tokens,**kwargs):
            result=verify(owner,remaining,tokens,**kwargs)
            if not before:before.update({name:(owner.location/name).read_bytes() for name in remaining})
            if len(tokens)==1:
                injected[0]=True;raise PermissionError('injected after one verified move')
            return result
        with patch.object(WindowsOwnedCleanup,'verify_transfer',fail):
            with self.assertRaises(fixture.CleanupOwnershipConflict) as error:self.cleanup(store)
        quarantine=Path(error.exception.preserved_path)
        self.assertTrue(injected[0]);self.assertFalse(self.delete_calls)
        self.assertEqual((self.directory/'memory.sqlite').read_bytes(),before['memory.sqlite'])
        self.assertEqual((self.directory/'operator.lock').read_bytes(),before['operator.lock'])
        tokens=list(quarantine.glob('owned-*'));self.assertEqual(len(tokens),1)
        self.assertEqual(tokens[0].read_bytes(),before['binding.json'])

    def test_unknown_source_lookup_after_detach_denies_before_first_delete(self):
        store=self.make_fixture()
        with patch.object(WindowsOwnedCleanup,'original_reused',side_effect=PermissionError('unknown source lookup')):
            with self.assertRaises(fixture.CleanupOwnershipConflict) as error:self.cleanup(store)
        quarantine=Path(error.exception.preserved_path)
        self.assertFalse(self.delete_calls);self.assertEqual(len(list(quarantine.glob('owned-*'))),3)
        self.assertTrue((quarantine/'fixture').is_dir());self.assertFalse(list((quarantine/'fixture').iterdir()))

    def test_last_quarantine_delete_handle_denied_preserves_complete_transferred_set(self):
        store=self.make_fixture();checked=WindowsOwnedCleanup.checked_handle;injected=[False]
        def deny(owner,path,pinned,**kwargs):
            if kwargs.get('delete') and Path(path)==owner.quarantine:
                injected[0]=True;raise PermissionError('last final delete handle denied')
            return checked(owner,path,pinned,**kwargs)
        with patch.object(WindowsOwnedCleanup,'checked_handle',deny):
            with self.assertRaises(fixture.CleanupOwnershipConflict) as error:self.cleanup(store)
        quarantine=Path(error.exception.preserved_path)
        self.assertTrue(injected[0]);self.assertFalse(self.delete_calls)
        self.assertEqual(len(list(quarantine.glob('owned-*'))),3);self.assertTrue((quarantine/'fixture').is_dir())

    def test_every_move_rechecks_all_prior_token_ids_and_exact_remaining_names(self):
        for mode in ('token','remaining'):
            with self.subTest(mode=mode):
                self.root=self.root/mode;self.root.mkdir();store=self.make_fixture()
                verify=WindowsOwnedCleanup.verify_transfer;injected=[False]
                before=(self.directory/'binding.json').read_bytes()
                def replace(owner,remaining,tokens,**kwargs):
                    if len(tokens)==1 and not injected[0]:
                        injected[0]=True
                        if mode=='token':
                            tokens[0][1].rename(self.root/'saved-original');tokens[0][1].write_bytes(b'FOREIGN_MOVED_TOKEN')
                        else:(self.directory/'foreign.txt').write_bytes(b'FOREIGN_REMAINING')
                    return verify(owner,remaining,tokens,**kwargs)
                with patch.object(WindowsOwnedCleanup,'verify_transfer',replace):
                    with self.assertRaises(fixture.CleanupOwnershipConflict) as error:self.cleanup(store)
                quarantine=Path(error.exception.preserved_path)
                self.assertTrue(injected[0]);self.assertFalse(self.delete_calls)
                self.assertTrue((self.directory/'memory.sqlite').exists());self.assertTrue((self.directory/'operator.lock').exists())
                token=next(quarantine.glob('owned-*'))
                if mode=='token':
                    self.assertEqual(token.read_bytes(),b'FOREIGN_MOVED_TOKEN');self.assertEqual((self.root/'saved-original').read_bytes(),before)
                else:
                    self.assertEqual(token.read_bytes(),before);self.assertEqual((self.directory/'foreign.txt').read_bytes(),b'FOREIGN_REMAINING')

    def test_distinct_new_source_directory_is_reported_only_after_confirmed_detach(self):
        store=self.make_fixture();lookup=WindowsOwnedCleanup.original_reused;injected=[False]
        def new_source(owner):
            if not injected[0]:
                injected[0]=True;self.directory.mkdir();(self.directory/'foreign.txt').write_bytes(b'FOREIGN_SOURCE')
            return lookup(owner)
        with patch.object(WindowsOwnedCleanup,'original_reused',new_source):result=self.cleanup(store)
        self.assertTrue(result['original_path_reused']);self.assertTrue(result['owned_files_removed'])
        self.assertEqual((self.directory/'foreign.txt').read_bytes(),b'FOREIGN_SOURCE')


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
            if kwargs.get('delete') and Path(args[0]).name.startswith('owned-'):raise PermissionError('Sharing/capability denied')
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

    def test_noncleanup_mutex_blocks_other_process_and_namespace_rename_until_owned_close(self):
        store=self.make_fixture();meta,db,fd,owner=fixture.open_fixture(self.directory,store)
        saved=self.root/'renamed'
        try:
            with self.assertRaises(OSError):self.directory.rename(saved)
            with self.assertRaises(OSError):(self.directory/'operator.lock').rename(self.root/'moved-lock')
            command=[sys.executable,'-c',
                'import sys; from reachy_companion.autonomous.voice_memory_fixture import operate; '
                'operate("readback",sys.argv[1],sys.argv[2],-1)',str(self.directory),store]
            blocked=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(blocked.returncode,0,blocked.stdout)
            self.assertTrue((self.directory/'operator.lock').exists())
        finally:fixture.finish_fixture(self.directory,db,fd,owner)
        self.assertFalse((self.directory/'operator.lock').exists())
        admitted=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(admitted.returncode,0,admitted.stderr)
        # A later foreign marker is never deleted by the already-closed owner.
        marker=self.directory/'operator.lock';marker.write_bytes(b'FOREIGN_AFTER_CLOSE')
        owner.close();self.assertEqual(marker.read_bytes(),b'FOREIGN_AFTER_CLOSE')

    def test_noncleanup_disposition_failure_closes_fd_and_preserves_pending_marker(self):
        store=self.make_fixture();meta,db,fd,owner=fixture.open_fixture(self.directory,store)
        with patch.object(owner.api,'delete',side_effect=PermissionError('injected disposition failure')):
            with self.assertRaisesRegex(PermissionError,'disposition failure'):
                fixture.finish_fixture(self.directory,db,fd,owner)
        with self.assertRaises(OSError):os.fstat(fd)
        marker=self.directory/'operator.lock';before=marker.read_bytes()
        with self.assertRaises(OSError):fixture.operate('readback',self.directory,store,-1)
        self.assertEqual(marker.read_bytes(),before)
        self.assertTrue((self.directory/'memory.sqlite').exists())


class Win32AdapterTests(unittest.TestCase):
    def test_handle_rename_has_utf16_fixed_layout_no_replace_and_retained_target_root(self):
        self.assertEqual(RenameInformation.root.offset,C.sizeof(C.c_void_p))
        self.assertEqual(RenameInformation.name.offset,2*C.sizeof(C.c_void_p)+4)
        kernel=WindowsKernel.__new__(WindowsKernel);kernel.lib=Mock()
        def rename(handle,kind,buffer,size):
            header=RenameInformation.from_buffer(buffer)
            self.assertEqual((handle,kind,header.replace,header.root),(123,3,0,456))
            data=C.string_at(C.addressof(buffer)+RenameInformation.name.offset,header.length)
            self.assertEqual(data.decode('utf-16-le'),'owned-нейтральный')
            self.assertGreaterEqual(size,RenameInformation.name.offset+header.length+2);return 1
        kernel.lib.SetFileInformationByHandle.side_effect=rename
        kernel.rename(123,456,'owned-нейтральный');kernel.lib.CreateFileW.assert_not_called()
        for name in ('','..','a/b','a\\b','x:y','x\x00y'):
            with self.assertRaises(ValueError):kernel.rename(123,456,name)
    def test_operation_lock_is_create_new_delete_authority_no_sharing_no_auto_delete(self):
        kernel=WindowsKernel.__new__(WindowsKernel);kernel.lib=Mock();kernel.lib.CreateFileW.return_value=123
        with patch.object(kernel,'info',return_value=((77,b'file-id'),0,1)):
            self.assertEqual(kernel.create_operation_lock('fixture'),123)
        args=kernel.lib.CreateFileW.call_args.args
        self.assertEqual(args[1:3],(0x40010080,0));self.assertEqual(args[4:6],(1,0x00200000))
        # No delete-on-close at creation: crash must leave a recovery marker.
        self.assertFalse(args[5]&0x04000000);kernel.lib.SetFileInformationByHandle.assert_not_called()
        with patch.object(kernel,'info',return_value=((77,b'file-id'),0,2)):
            with self.assertRaises(ValueError):kernel.create_operation_lock('fixture')
        kernel.lib.CloseHandle.assert_called_once_with(123)
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
        with patch.object(kernel,'info',return_value=((77,b'x'*16),0x10,1)):
            kernel.open('quarantine',directory=True,traverse=True)
        self.assertEqual(kernel.lib.CreateFileW.call_args.args[1],0xa0)
    def test_reparse_and_multiple_links_fail_closed(self):
        for attributes,links in ((0x400,1),(0,2)):
            kernel=WindowsKernel.__new__(WindowsKernel);kernel.lib=Mock();kernel.lib.CreateFileW.return_value=123
            with patch.object(kernel,'info',return_value=((77,b'x'*16),attributes,links)):
                with self.assertRaises(ValueError):kernel.open('fixture')
            kernel.lib.CloseHandle.assert_called_once_with(123)


if __name__=='__main__':unittest.main()
