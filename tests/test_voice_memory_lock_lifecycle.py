"""Causal lock/finalization faults; emulated handles are not native Win32 proof."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from reachy_companion.autonomous import voice_memory_fixture as fixture
from reachy_companion.autonomous.windows_fixture_cleanup import WindowsOperationLock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('memory_lock_receipts',ROOT/'tests/test_voice_memory_acceptance.py')
receipts=importlib.util.module_from_spec(spec);spec.loader.exec_module(receipts)


class HandleSequenceModel:
    """Real POSIX FDs, modeled disposition; not Windows sharing semantics."""
    def __init__(self):self.pins=[];self.events=[];self.lock=None;self.lock_path=None
    def validate_volume(self,path):pass
    def open(self,path,*,directory=False,share=7):
        assert directory and share==3
        fd=os.open(path,os.O_RDONLY);self.pins.append(fd);self.events.append(('pin',fd));return fd
    def create_operation_lock(self,path):
        self.lock=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);self.lock_path=Path(path)
        self.events.append(('create',self.lock));return self.lock
    def delete(self,handle):
        assert handle==self.lock and self.pins
        identity=os.fstat(handle);current=os.stat(self.lock_path)
        assert (identity.st_dev,identity.st_ino)==(current.st_dev,current.st_ino)
        self.events.append(('disposition',handle));os.unlink(self.lock_path)
    def identity(self,handle):
        value=os.fstat(handle);return value.st_dev,value.st_ino
    def info(self,handle):return self.identity(handle),0,os.fstat(handle).st_nlink
    def close(self,handle):
        if handle==self.lock:os.close(handle);return
        # Parent pins outlive CRT close on every completed operation.
        if self.lock is not None:
            try:os.fstat(self.lock)
            except OSError:pass
            else:raise AssertionError('Ancestor released before CRT descriptor')
        self.events.append(('unpin',handle));os.close(handle);self.pins.remove(handle)


@unittest.skipUnless(os.name=='posix','POSIX descriptor fault model only')
class LockLifecycleTests(unittest.TestCase):
    def setUp(self):
        binary=patch.object(os,'O_BINARY',0,create=True);binary.start();self.addCleanup(binary.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.directory=self.root/'fixture';hub,device=receipts.receipts()
        hp=self.root/'hub.json';dp=self.root/'device.json';hp.write_text(json.dumps(hub));dp.write_text(json.dumps(device))
        self.store=fixture.prepare(self.directory,hp,dp,dict(controller='controller',session_boot='session',source_boot='source'))['store_id']
    def owner_model(self):
        api=HandleSequenceModel()
        class Owner(WindowsOperationLock):
            def __init__(self,directory):super().__init__(directory,kernel=api)
        return api,Owner
    def test_old_normal_finally_unlink_failure_leaks_fd_and_new_forget_has_no_path_unlink(self):
        # Exact pre-fix noncleanup finally ordering: unlink exception prevents close.
        fd=os.open(self.directory/'operator.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with patch.object(Path,'unlink',side_effect=PermissionError('Windows open CRT lock')):
            with self.assertRaises(PermissionError):
                (self.directory/'operator.lock').unlink()
                os.close(fd)
        os.fstat(fd) # old fd is still live after an otherwise normal operation
        os.close(fd);(self.directory/'operator.lock').unlink()
        api,owner=self.owner_model()
        crt=SimpleNamespace(open_osfhandle=lambda handle,flags:handle,get_osfhandle=lambda fd:fd)
        with patch.dict(sys.modules,msvcrt=crt),patch.object(fixture,'operation_lock_class',return_value=owner):
            with patch.object(Path,'unlink',side_effect=AssertionError('Path unlink forbidden')):
                result=fixture.operate('forget',self.directory,self.store,0)
        self.assertTrue(result['forgotten_replay_rejected']);self.assertFalse(api.pins)
        self.assertEqual([x[0] for x in api.events].count('disposition'),1)
        with self.assertRaises(OSError):os.fstat(api.lock)
        self.assertFalse((self.directory/'operator.lock').exists())
    def test_release_failure_always_closes_fd_keeps_marker_and_primary_exception(self):
        for primary in (None,ValueError('first body failure')):
            with self.subTest(primary=primary):
                fd=os.open(self.root/('lock-'+str(primary is None)),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                store=Mock();owner=Mock();owner.release_lock.side_effect=PermissionError('release denied')
                if primary is None:
                    with self.assertRaisesRegex(PermissionError,'release denied'):fixture.finish_fixture(self.directory,store,fd,owner)
                else:
                    fixture.finish_fixture(self.directory,store,fd,owner,primary)
                    self.assertIn('PermissionError',primary.__notes__[0])
                with self.assertRaises(OSError):os.fstat(fd)
                store.close.assert_called_once();owner.close.assert_called_once()
                self.assertTrue((self.root/('lock-'+str(primary is None))).exists())
    def test_open_failure_preserves_primary_even_if_release_and_store_close_fail(self):
        api,owner=self.owner_model();crt=SimpleNamespace(open_osfhandle=lambda h,f:h,get_osfhandle=lambda fd:fd)
        store=Mock();store.meta.side_effect=ValueError('initializer original');store.close.side_effect=OSError('store close failed')
        with patch.dict(sys.modules,msvcrt=crt),patch.object(fixture,'operation_lock_class',return_value=owner),patch.object(fixture,'MemoryStore',return_value=store):
            with self.assertRaisesRegex(ValueError,'initializer original') as error:fixture.open_fixture(self.directory,self.store)
        self.assertIn('store close failed',error.exception.__notes__[0]);self.assertFalse(api.pins)
        with self.assertRaises(OSError):os.fstat(api.lock)
        self.assertTrue((self.directory/'operator.lock').exists()) # unknown store close: no disposition
        self.assertNotIn('disposition',[event[0] for event in api.events])
    def test_handle_disposition_failure_preserves_marker_and_foreign_files_without_fd_leak(self):
        api,owner=self.owner_model();crt=SimpleNamespace(open_osfhandle=lambda h,f:h,get_osfhandle=lambda fd:fd)
        with patch.dict(sys.modules,msvcrt=crt),patch.object(fixture,'operation_lock_class',return_value=owner):
            with patch.object(api,'delete',side_effect=PermissionError('disposition denied')):
                with self.assertRaisesRegex(PermissionError,'disposition denied'):fixture.operate('readback',self.directory,self.store,0)
        self.assertFalse(api.pins)
        with self.assertRaises(OSError):os.fstat(api.lock)
        self.assertTrue((self.directory/'operator.lock').exists())
        with self.assertRaises(FileExistsError):fixture.operate('readback',self.directory,self.store,0)
        self.assertTrue((self.directory/'memory.sqlite').exists())

    def test_handle_transfer_and_marker_write_failures_close_original_once_without_deletion(self):
        for stage in ('transfer','marker'):
            with self.subTest(stage=stage):
                api,owner=self.owner_model()
                transfer=Mock(side_effect=ValueError('original transfer')) if stage=='transfer' else lambda h,f:h
                crt=SimpleNamespace(open_osfhandle=transfer,get_osfhandle=lambda fd:fd)
                with patch.dict(sys.modules,msvcrt=crt),patch.object(fixture,'operation_lock_class',return_value=owner):
                    if stage=='transfer':
                        with self.assertRaisesRegex(ValueError,'original transfer'):fixture.open_fixture(self.directory,self.store)
                    else:
                        with patch.object(os,'fsync',side_effect=OSError('original marker')):
                            with self.assertRaisesRegex(OSError,'original marker'):fixture.open_fixture(self.directory,self.store)
                self.assertFalse(api.pins)
                with self.assertRaises(OSError):os.fstat(api.lock)
                self.assertTrue((self.directory/'operator.lock').exists())
                self.assertNotIn('disposition',[event[0] for event in api.events])
                (self.directory/'operator.lock').unlink() # only this neutral test root, known fd closed

    def test_callers_handled_exception_does_not_hide_normal_operation_release_failure(self):
        api,owner=self.owner_model();crt=SimpleNamespace(open_osfhandle=lambda h,f:h,get_osfhandle=lambda fd:fd)
        try:raise ValueError('unrelated caller exception')
        except ValueError:
            with patch.dict(sys.modules,msvcrt=crt),patch.object(fixture,'operation_lock_class',return_value=owner):
                with patch.object(api,'delete',side_effect=PermissionError('actual release failure')):
                    with self.assertRaisesRegex(PermissionError,'actual release failure'):
                        fixture.operate('readback',self.directory,self.store,0)
        self.assertFalse(api.pins)
        with self.assertRaises(OSError):os.fstat(api.lock)


if __name__=='__main__':unittest.main()
