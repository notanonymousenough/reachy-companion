"""Frozen original/public protocol on synthetic POSIX files, not Win32 proof."""
import ast
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
HELPERS=ROOT/'scripts/windows'
sys.path.insert(0,str(HELPERS))
try:
    import operation_slot
    import accepted_start_admission as admission
finally:sys.path.pop(0)

SOURCE_SHA='de663d943ff9b999d315d9cbd1ef4858c76eb318fe5a02b6eb91b34e845965a4'
AST_SHA='5c47c5dc471fc06721aafb1402c48f2156b79746a26e815eae53e213c9702cd2'


class SourceIdentityTests(unittest.TestCase):
    def test_exact_sanitized_original_bytes_and_three_node_ast_are_unchanged(self):
        source=(HELPERS/'operation_slot.py').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),SOURCE_SHA)
        nodes=[node for node in ast.parse(source).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))]
        self.assertEqual([node.name for node in nodes],['_identity','_plain_directory','OperationSlot'])
        normalized=ast.dump(ast.Module(body=nodes,type_ignores=[]),include_attributes=False).encode()
        self.assertEqual(hashlib.sha256(normalized).hexdigest(),AST_SHA)


@unittest.skipUnless(os.name=='posix','Independent POSIX flock/source proof only; native Windows is a separate gate')
class StrictAdmissionTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.directory=self.root/'enrolled';self.directory.mkdir()
        self.anchor=self.root/'enrolled.anchor.json';self.lock=self.directory/'operation.lock'
        self.state=self.directory/'operation-state.json';self.lock.write_bytes(b'0')
        self.anchor.write_text(json.dumps(dict(schema=1,directory_identity=self.identity(self.directory),parent_identity=self.identity(self.root))))
        self.state.write_text(json.dumps(dict(schema=1,inflight=None)))
        self.binding=admission.NamespaceBinding(self.directory,self.identity(self.root),self.identity(self.directory),
            self.identity(self.anchor),self.identity(self.lock),hashlib.sha256(self.anchor.read_bytes()).hexdigest())
        # Independent module/process executes exact frozen sanitized source,
        # authenticated by the source/AST constants, without any private artifact.
        self.reference=self.root/'reference_slot.py';self.reference.write_bytes((HELPERS/'operation_slot.py').read_bytes())
        spec=importlib.util.spec_from_file_location('frozen_reference_slot',self.reference)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.original=module.OperationSlot

    @staticmethod
    def identity(path):
        value=path.lstat();return value.st_dev,value.st_ino

    def snapshot(self):return {str(path.relative_to(self.root)):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}

    def child(self,kind,action='observe'):
        binding=dict(directory=str(self.directory),parent_identity=self.binding.parent_identity,
            directory_identity=self.binding.directory_identity,anchor_identity=self.binding.anchor_identity,
            lock_identity=self.binding.lock_identity,anchor_sha256=self.binding.anchor_sha256)
        code='''import importlib.util,json,sys
from pathlib import Path
kind,action,reference,helpers,raw=sys.argv[1:]
binding=json.loads(raw)
try:
    if kind=='original':
        spec=importlib.util.spec_from_file_location('frozen_reference',reference)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        context=module.OperationSlot(binding['directory'])
    else:
        sys.path.insert(0,helpers)
        from accepted_start_admission import NamespaceBinding,accepted_start_admission
        for key in ('parent_identity','directory_identity','anchor_identity','lock_identity'):binding[key]=tuple(binding[key])
        context=accepted_start_admission(NamespaceBinding(**binding))
    with context as slot:
        if action=='leave_pending':slot.save({'kind':'UNKNOWN','owner':'synthetic-child'})
        result={'admitted':True,'pending':slot.pending()}
    print(json.dumps(result))
except BaseException as error:
    print(json.dumps({'admitted':False,'error_kind':type(error).__name__}))
'''
        process=subprocess.run([sys.executable,'-I','-B','-c',code,kind,action,str(self.reference),str(HELPERS),json.dumps(binding)],
                               capture_output=True,text=True,timeout=5)
        self.assertEqual(process.returncode,0,process.stderr)
        return json.loads(process.stdout)

    def test_independent_original_and_strict_processes_contend_on_same_existing_lock_both_directions(self):
        with admission.accepted_start_admission(self.binding):
            blocked=self.child('original');self.assertFalse(blocked['admitted'])
            self.assertEqual(blocked['error_kind'],'BlockingIOError')
        with self.original(self.directory):
            blocked=self.child('strict');self.assertFalse(blocked['admitted'])
            self.assertEqual(blocked['error_kind'],'BlockingIOError')
        self.assertTrue(self.child('original')['admitted'])
        self.assertTrue(self.child('strict')['admitted'])
        self.assertEqual(json.loads(self.state.read_text()),dict(schema=1,inflight=None))

    def test_busy_admission_does_not_open_state_before_obtaining_existing_mutex(self):
        opened=os.open
        def guarded(path,*args,**kwargs):
            if str(path).endswith('operation-state.json'):raise AssertionError('State must not be opened while another owner holds mutex')
            return opened(path,*args,**kwargs)
        with self.original(self.directory),patch.object(admission.os,'open',side_effect=guarded):
            with self.assertRaises((BlockingIOError,OSError)):
                with admission.accepted_start_admission(self.binding):self.fail('Busy owner admitted')

    def test_original_missing_pending_semantics_unchanged_but_strict_admission_denies_without_bootstrap(self):
        self.state.unlink()
        with self.original(self.directory) as slot:self.assertIsNone(slot.pending())
        before=self.snapshot()
        with self.assertRaises(admission.AdmissionDenied):
            with admission.accepted_start_admission(self.binding):self.fail('Missing state admitted')
        self.assertEqual(self.snapshot(),before);self.assertFalse(self.state.exists())

    def test_missing_or_empty_enrollment_files_cannot_initialize_slot(self):
        for path in (self.anchor,self.lock,self.state):
            raw=path.read_bytes();path.unlink();before=self.snapshot()
            with self.subTest(path=path.name),self.assertRaises((ValueError,OSError)):
                with admission.accepted_start_admission(self.binding):self.fail('Missing enrollment admitted')
            self.assertEqual(self.snapshot(),before);self.assertFalse(path.exists())
            path.write_bytes(raw)
            # Explicit synthetic fixture recovery freezes its new file identity.
            self.binding=replace(self.binding,anchor_identity=self.identity(self.anchor),lock_identity=self.identity(self.lock))
        self.lock.write_bytes(b'');before=self.snapshot()
        with self.assertRaises(admission.AdmissionDenied):
            with admission.accepted_start_admission(self.binding):self.fail('Empty lock admitted')
        self.assertEqual(self.snapshot(),before)

    def test_malformed_duplicate_unknown_false_or_missing_inflight_is_not_known_idle(self):
        for raw in (b'{}',b'{"schema":1}',b'{"schema":true,"inflight":null}',b'{"schema":1,"inflight":false}',
                    b'{"schema":1,"inflight":{}}',b'{"schema":1,"inflight":{"kind":"UNKNOWN"}}',
                    b'{"schema":1,"inflight":null,"inflight":null}',b'{"schema":1,"inflight":NaN}',b'x'*65537):
            self.state.write_bytes(raw);before=self.snapshot()
            with self.subTest(raw=raw[:64]),self.assertRaises((ValueError,OSError)):
                with admission.accepted_start_admission(self.binding):self.fail('Unknown state admitted')
            self.assertEqual(self.snapshot(),before)

    def test_independent_original_unknown_is_preserved_and_strict_child_cannot_clear_it(self):
        self.assertTrue(self.child('original','leave_pending')['admitted'])
        before=self.state.read_bytes()
        blocked=self.child('strict');self.assertFalse(blocked['admitted'])
        self.assertEqual(blocked['error_kind'],'AdmissionDenied')
        self.assertEqual(self.state.read_bytes(),before)
        with self.original(self.directory) as slot:self.assertEqual(slot.pending(),dict(kind='UNKNOWN',owner='synthetic-child'))

    def test_body_pending_then_exception_or_normal_return_keeps_exact_marker_and_closes_only_owned_handles(self):
        marker=dict(kind='UNKNOWN',owner='synthetic-parent')
        with self.assertRaisesRegex(RuntimeError,'body failed'):
            with admission.accepted_start_admission(self.binding) as slot:
                slot.save(marker);before=self.state.read_bytes();raise RuntimeError('body failed')
        self.assertEqual(self.state.read_bytes(),before)
        with self.original(self.directory) as slot:
            self.assertEqual(slot.pending(),marker);slot.save(None) # explicit test-owner recovery, never admission recovery
        with self.assertRaises(admission.AdmissionDenied):
            with admission.accepted_start_admission(self.binding) as slot:
                slot.save(marker);before=self.state.read_bytes()
        self.assertEqual(self.state.read_bytes(),before)
        self.assertFalse(self.child('strict')['admitted'])

    def test_legitimate_previous_atomic_save_does_not_freeze_an_obsolete_state_inode(self):
        original=operation_slot.OperationSlot.__enter__;old=self.identity(self.state)
        def enter(slot):
            with self.original(self.directory) as previous:previous.save(None)
            return original(slot)
        with patch.object(operation_slot.OperationSlot,'__enter__',enter):
            with admission.accepted_start_admission(self.binding):pass
        self.assertNotEqual(self.identity(self.state),old)

    def test_lock_removed_after_precheck_cannot_admit_or_hide_original_create_behavior(self):
        original=operation_slot.OperationSlot.__enter__;saved=self.root/'saved-lock'
        def enter(slot):
            self.lock.rename(saved) # outside the cooperative protocol
            return original(slot)
        with patch.object(operation_slot.OperationSlot,'__enter__',enter):
            with self.assertRaises(admission.AdmissionDenied):
                with admission.accepted_start_admission(self.binding):self.fail('Recreated lock admitted')
        self.assertEqual(saved.read_bytes(),b'0')
        self.assertEqual(self.lock.read_bytes(),b'0') # original O_CREAT behavior is deliberately unchanged
        self.assertNotEqual(self.identity(self.lock),self.binding.lock_identity)
        self.assertEqual(json.loads(self.state.read_text()),dict(schema=1,inflight=None))

    def test_state_symlink_hardlink_and_anchor_or_lock_replacement_preserve_foreign_objects(self):
        target=self.root/'foreign-state';target.write_bytes(self.state.read_bytes());self.state.unlink();self.state.symlink_to(target)
        before=self.snapshot()
        with self.assertRaises(admission.AdmissionDenied):
            with admission.accepted_start_admission(self.binding):self.fail('Reparse state admitted')
        self.assertEqual(self.snapshot(),before);self.assertTrue(self.state.is_symlink())
        self.state.unlink();self.state.write_bytes(target.read_bytes());alias=self.root/'state-alias';os.link(self.state,alias)
        with self.assertRaises(admission.AdmissionDenied):
            with admission.accepted_start_admission(self.binding):self.fail('Hardlink state admitted')
        self.assertEqual(target.read_bytes(),alias.read_bytes());alias.unlink()
        for path in (self.anchor,self.lock):
            foreign=path.with_name(path.name+'.foreign');foreign.write_bytes(path.read_bytes());foreign.replace(path)
            before=self.snapshot()
            with self.assertRaises(admission.AdmissionDenied):
                with admission.accepted_start_admission(self.binding):self.fail('Replaced enrolled object admitted')
            self.assertEqual(self.snapshot(),before)
            self.binding=replace(self.binding,anchor_identity=self.identity(self.anchor),lock_identity=self.identity(self.lock))

    def test_rebinding_directory_during_body_preserves_old_pending_and_new_foreign_tree(self):
        saved=self.root/'saved';marker=dict(kind='UNKNOWN',owner='synthetic')
        with self.assertRaises((ValueError,OSError)):
            with admission.accepted_start_admission(self.binding) as slot:
                slot.save(marker);before=self.state.read_bytes()
                self.directory.rename(saved);self.directory.mkdir();(self.directory/'sentinel').write_bytes(b'FOREIGN')
        self.assertEqual((saved/'operation-state.json').read_bytes(),before)
        self.assertEqual((self.directory/'sentinel').read_bytes(),b'FOREIGN')
        with self.assertRaises((ValueError,OSError)):
            with admission.accepted_start_admission(self.binding):self.fail('Rebound namespace admitted')
        self.assertFalse((self.directory/'operation.lock').exists())

    def test_independently_pinned_hash_and_identity_are_not_derived_from_current_observation(self):
        for binding in (replace(self.binding,anchor_sha256='0'*64),replace(self.binding,lock_identity=(0,0)),
                        replace(self.binding,anchor_sha256=''),replace(self.binding,parent_identity=(True,0))):
            before=self.snapshot()
            with self.assertRaises((ValueError,OSError)):
                with admission.accepted_start_admission(binding):self.fail('Invalid enrollment admitted')
            self.assertEqual(self.snapshot(),before)


if __name__=='__main__':unittest.main()
