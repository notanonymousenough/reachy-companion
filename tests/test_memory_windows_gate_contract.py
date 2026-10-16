"""Source gate selection and mocked Windows fixture policy, not native proof."""
import ast
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_voice_memory_acceptance as memory_tests

ROOT=Path(__file__).resolve().parents[1]
REQUIRED_NATIVE={
    'test_success_with_existing_sqlite_and_closed_crt_lock',
    'test_foreign_database_and_directory_rebinding_are_preserved',
    'test_replacement_after_detach_preserves_every_object_without_deletion',
    'test_identity_mismatch_in_delete_handle_preserves_all_tokens',
    'test_partial_transfer_failure_preserves_moved_and_remaining_original_bytes',
    'test_unknown_source_lookup_after_detach_denies_before_first_delete',
    'test_last_quarantine_delete_handle_denied_preserves_complete_transferred_set',
    'test_every_move_rechecks_all_prior_token_ids_and_exact_remaining_names',
    'test_distinct_new_source_directory_is_reported_only_after_confirmed_detach',
    'test_native_empty_directory_detach_uses_original_handle_and_absolute_target',
    'test_native_occupied_sentinel_is_never_replaced_and_both_files_keep_ids_and_bytes',
    'test_noncleanup_mutex_blocks_other_process_and_namespace_rename_until_owned_close',
    'test_noncleanup_disposition_failure_closes_fd_and_preserves_pending_marker'}
REQUIRED_WORKFLOW={
    'test_separate_processes_confirmation_correction_restart_forget_and_owned_cleanup',
    'test_invalid_or_unfinished_provenance_never_creates_store',
    'test_foreign_store_files_locks_and_symlinks_are_preserved',
    'test_owner_correction_fences_ready_speech_and_new_store_rejects_old_uuid'}
POSIX_FAULTS={
    'test_cleanup_requires_exclusive_authority_and_supported_anchored_operations',
    'test_mid_cleanup_file_and_directory_replacements_are_preserved',
    'test_replacement_after_last_check_is_atomically_moved_and_preserved_not_unlinked'}


def classes(filename):
    return {node.name:node for node in ast.parse((ROOT/'tests'/filename).read_text()).body if isinstance(node,ast.ClassDef)}


def tests(node):
    return {method.name:method for method in node.body if isinstance(method,ast.FunctionDef) and method.name.startswith('test_')}


class WindowsMemoryGateContractTests(unittest.TestCase):
    def assert_platform_gate(self,node,platform):
        self.assertEqual(len(node.decorator_list),1)
        decorator=node.decorator_list[0]
        self.assertIsInstance(decorator,ast.Call)
        self.assertEqual(ast.unparse(decorator.func),'unittest.skipUnless')
        self.assertEqual(ast.unparse(decorator.args[0]),"os.name == '"+platform+"'")

    def test_exact_seventeen_windows_gates_cannot_disappear_or_acquire_skip_decorators(self):
        native=classes('test_windows_fixture_cleanup.py')
        self.assertEqual(native['CleanupScenarios'].decorator_list,[])
        self.assert_platform_gate(native['NativeWindowsCleanupTests'],'nt')
        self.assertEqual([ast.unparse(base) for base in native['NativeWindowsCleanupTests'].bases],
                         ['CleanupScenarios','unittest.TestCase'])
        methods={**tests(native['CleanupScenarios']),**tests(native['NativeWindowsCleanupTests'])}
        self.assertEqual(set(methods),REQUIRED_NATIVE);self.assertEqual(len(methods),13)
        for method in methods.values():self.assertEqual(method.decorator_list,[])
        workflow=classes('test_voice_memory_acceptance.py')['VoiceMemoryTests']
        self.assertEqual(workflow.decorator_list,[])
        self.assertEqual([ast.unparse(base) for base in workflow.bases],['unittest.TestCase'])
        methods=tests(workflow)
        self.assertEqual(set(methods),REQUIRED_WORKFLOW|POSIX_FAULTS)
        for name in REQUIRED_WORKFLOW:self.assertEqual(methods[name].decorator_list,[])
        for name in POSIX_FAULTS:self.assert_platform_gate(methods[name],'posix')
        for node in (native['CleanupScenarios'],native['NativeWindowsCleanupTests'],workflow):
            for call in ast.walk(node):
                if isinstance(call,ast.Call):
                    name=call.func.attr if isinstance(call.func,ast.Attribute) else call.func.id if isinstance(call.func,ast.Name) else None
                    self.assertNotIn(name,('skipTest','SkipTest'))
        runbook=(ROOT/'docs/autonomous-companion/windows-fixture-cleanup.md').read_text()
        self.assertIn('test_windows_fixture_cleanup.NativeWindowsCleanupTests',runbook)
        for name in REQUIRED_WORKFLOW:self.assertIn('test_voice_memory_acceptance.VoiceMemoryTests.'+name,runbook)
        self.assertEqual(len(REQUIRED_NATIVE)+len(REQUIRED_WORKFLOW),17)

    def test_windows_parent_is_required_existing_absolute_and_validated_before_use(self):
        with patch.dict(os.environ,{},clear=True),patch.object(memory_tests,'WindowsKernel') as kernel:
            with self.assertRaisesRegex(RuntimeError,'REACHY_WINDOWS_CLEANUP_TEST_PARENT'):memory_tests.fixture_parent('nt')
            kernel.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory).resolve()
            for value in ('relative-parent',str(parent/'absent')):
                with patch.dict(os.environ,REACHY_WINDOWS_CLEANUP_TEST_PARENT=value),patch.object(memory_tests,'WindowsKernel') as kernel:
                    with self.assertRaisesRegex(ValueError,'Existing absolute'):memory_tests.fixture_parent('nt')
                    kernel.assert_not_called()
            with patch.dict(os.environ,REACHY_WINDOWS_CLEANUP_TEST_PARENT=str(parent)),patch.object(memory_tests,'WindowsKernel') as kernel:
                self.assertEqual(memory_tests.fixture_parent('nt'),parent)
                kernel.return_value.validate_volume.assert_called_once_with(parent)
                self.assertEqual(list(parent.iterdir()),[])

    def test_unsupported_windows_volume_fails_without_fallback_or_directory_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory).resolve()
            with patch.dict(os.environ,REACHY_WINDOWS_CLEANUP_TEST_PARENT=str(parent)),patch.object(memory_tests,'WindowsKernel') as kernel:
                kernel.return_value.validate_volume.side_effect=ValueError('Unsupported NTFS capability')
                with self.assertRaisesRegex(ValueError,'Unsupported NTFS'):memory_tests.fixture_parent('nt')
                self.assertEqual(list(parent.iterdir()),[])
        with patch.object(memory_tests,'WindowsKernel') as kernel:
            self.assertIsNone(memory_tests.fixture_parent('posix'));kernel.assert_not_called()


if __name__=='__main__':unittest.main()
