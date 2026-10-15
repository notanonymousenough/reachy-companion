"""Exact old failures and anchored journal regressions; temporary filesystem only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import test_live_smoke_contract as fixture
import smoke_execution as execution
from smoke_fs import PinnedTree


def scopes():return [dict(endpoint='http://loopback:1234',weight_sha256='a'*64)]


def old_module():
    raw=subprocess.check_output(['git','show','31f6ba4938d82a0142844fcc766f6c8376223cfc:deploy/autonomous/smoke_execution.py'],cwd=fixture.ROOT)
    assert hashlib.sha256(raw).hexdigest()=='5bdd9cfb4ad956713fed749c847b053bbd14c8acf4e9d986fcd08c76c84c7614'
    old=ModuleType('old_path_execution');exec(compile(raw,'old_execution.py','exec'),old.__dict__)
    return old


class NamespaceRebindTests(unittest.TestCase):
    def test_old_root_rename_admits_new_owner_new_anchor_refuses_without_bootstrap(self):
        old=old_module()
        with tempfile.TemporaryDirectory() as td:
            parent=Path(td).resolve();root=parent/'old-account-root'
            with patch.object(old,'guard_root',return_value=root):
                lease=old.ExecutionLease(scopes()).acquire();lease.finish(known=False)
                root.rename(parent/'retired-old-root')
                admitted=old.ExecutionLease(scopes()).acquire();admitted.finish(known=True)
            root=parent/'anchored-account-root'
            with patch.object(execution,'guard_root',return_value=root):
                anchor=execution.provision_namespace(scopes())
                lease=execution.ExecutionLease(scopes(),anchor=anchor).acquire();lease.finish(known=False)
                retired=parent/'retired-anchored-root';root.rename(retired)
                with self.assertRaises(RuntimeError):execution.ExecutionLease(scopes(),anchor=anchor).acquire()
                self.assertFalse(root.exists()) # no implicit replacement root
                self.assertIn(b'UNKNOWN',next(retired.glob('*/owner.jsonl')).read_bytes())
                with self.assertRaises(FileExistsError):execution.provision_namespace(scopes())
                root.mkdir();(root/'foreign').write_bytes(b'preserve replacement')
                with self.assertRaises(RuntimeError):execution.ExecutionLease(scopes(),anchor=anchor).acquire()
                self.assertEqual((root/'foreign').read_bytes(),b'preserve replacement')

    def test_frozen_ancestor_and_anchor_identity_cannot_rebind(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td).resolve();account=base/'account';account.mkdir();root=account/'execution'
            with patch.object(execution,'guard_root',return_value=root):
                anchor=execution.provision_namespace(scopes())
                lease=execution.ExecutionLease(scopes(),anchor=anchor).acquire();lease.finish(known=False)
                account.rename(base/'retired-account');account.mkdir()
                with self.assertRaises(RuntimeError):execution.ExecutionLease(scopes(),anchor=anchor).acquire()
                self.assertEqual(list(account.iterdir()),[])
                self.assertIn(b'UNKNOWN',next((base/'retired-account'/'execution').glob('*/owner.jsonl')).read_bytes())

    @unittest.skipIf(os.name=='nt','POSIX rename race; Windows denial tested natively below')
    def test_old_close_rebind_deletes_foreign_new_release_has_no_path_delete(self):
        old=old_module()
        with tempfile.TemporaryDirectory() as td:
            parent=Path(td).resolve();root=parent/'old-root'
            with patch.object(old,'guard_root',return_value=root):lease=old.ExecutionLease(scopes()).acquire()
            slot=lease.slots[0];real_close=os.close;swapped=[False]
            def old_close(fd):
                real_close(fd)
                if fd==slot['fd'] and not swapped[0]:
                    swapped[0]=True;slot['directory'].rename(parent/'retired-old-slot');slot['directory'].mkdir()
                    slot['path'].write_bytes(b'FOREIGN PRESERVE')
            with patch.object(old.os,'close',side_effect=old_close):lease.finish(known=True)
            self.assertFalse(slot['path'].exists());self.assertTrue(lease.released)
            root=parent/'new-root'
            with patch.object(execution,'guard_root',return_value=root):
                anchor=execution.provision_namespace(scopes());lease=execution.ExecutionLease(scopes(),anchor=anchor).acquire()
                slot=lease.slots[0];fd_to_swap=slot['fd'];swapped=[False]
                def new_close(fd):
                    real_close(fd)
                    if fd==fd_to_swap and not swapped[0]:
                        swapped[0]=True;slot['directory'].rename(parent/'retired-new-slot');slot['directory'].mkdir()
                        slot['path'].write_bytes(b'FOREIGN PRESERVE')
                with patch.object(os,'close',side_effect=new_close):
                    with self.assertRaises(RuntimeError):lease.finish(known=True)
                self.assertEqual(slot['path'].read_bytes(),b'FOREIGN PRESERVE')
                self.assertFalse(lease.status()['released']);self.assertTrue(lease.status()['unknown'])
                self.assertTrue((root/'NAMESPACE-UNKNOWN').exists())
                with self.assertRaises(RuntimeError):execution.ExecutionLease(scopes(),anchor=anchor).acquire()

    def test_acquire_requires_preprovisioned_immutable_anchor_and_no_creates(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve()/'never-provisioned'
            with patch.object(execution,'guard_root',return_value=root):
                with self.assertRaises(RuntimeError):execution.ExecutionLease(scopes(),anchor={}).acquire()
                self.assertFalse(root.exists());self.assertFalse(execution.anchor_path().exists())
                anchor=execution.provision_namespace(scopes())
                wrong={**anchor,'sha256':'f'*64}
                with self.assertRaises(RuntimeError):execution.ExecutionLease(scopes(),anchor=wrong).acquire()
                lease=execution.ExecutionLease(scopes(),anchor=anchor).acquire();lease.finish(known=True)
                again=execution.ExecutionLease(scopes(),anchor=anchor).acquire();again.finish(known=True)
                path=next(root.glob('*/owner.jsonl'))
                self.assertEqual([json.loads(line)['state'] for line in path.read_text().splitlines()[1:]],
                    ['RELEASED','HELD','RELEASED','HELD','RELEASED'])

    def test_native_open_policy_no_share_delete_reparse_flags_and_write_exclusion(self):
        tree=PinnedTree.__new__(PinnedTree)
        library=SimpleNamespace(CreateFileW=Mock(return_value=123))
        api=SimpleNamespace(lib=library,info=lambda handle:([1,b'id'],0x10,1),close=Mock())
        tree.api=api
        tree._win_open(Path('fixture'),directory=True)
        args=library.CreateFileW.call_args.args
        self.assertEqual(args[2],3);self.assertFalse(args[2]&4);self.assertTrue(args[5]&0x00200000)
        api.info=lambda handle:([1,b'id'],0,1)
        tree._win_open(Path('fixture'),write=True);args=library.CreateFileW.call_args.args
        self.assertEqual(args[2],1);self.assertTrue(args[1]&0x40000000);self.assertFalse(args[2]&6)
        tree._win_open(Path('new-fixture'),write=True,create=True)
        self.assertEqual(library.CreateFileW.call_args.args[4],1) # atomic CREATE_NEW, no close/reopen gap
        api.info=lambda handle:([1,b'id'],0x400,1)
        with self.assertRaises(ValueError):tree._win_open(Path('reparse'))
        api.close.assert_called_with(123)


@unittest.skipUnless(os.name=='nt','Native local fixed NTFS proof requires Windows')
class NativeWindowsNamespaceTests(unittest.TestCase):
    def test_held_directory_cannot_rename_and_journal_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve()/'namespace'
            with patch.object(execution,'guard_root',return_value=root):
                anchor=execution.provision_namespace(scopes());lease=execution.ExecutionLease(scopes(),anchor=anchor).acquire()
                try:
                    with self.assertRaises(OSError):lease.slots[0]['directory'].rename(root/'rebound')
                    with self.assertRaises(OSError):root.rename(root.parent/'rebound-root')
                    with self.assertRaises(OSError):lease.slots[0]['path'].write_bytes(b'foreign')
                finally:lease.finish(known=True)
                self.assertTrue(lease.status()['released'])

    def test_unknown_root_rename_does_not_reinitialize_account_namespace(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve()/'namespace'
            with patch.object(execution,'guard_root',return_value=root):
                anchor=execution.provision_namespace(scopes());lease=execution.ExecutionLease(scopes(),anchor=anchor).acquire()
                lease.finish(known=False);root.rename(root.parent/'retired')
                with self.assertRaises(RuntimeError):execution.ExecutionLease(scopes(),anchor=anchor).acquire()
                self.assertFalse(root.exists())


if __name__=='__main__':unittest.main()
