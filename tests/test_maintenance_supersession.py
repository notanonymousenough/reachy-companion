"""Synthetic failure boundaries; never loads an operational marker/provider."""
import base64
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('maintenance_supersession',
    ROOT/'deploy/autonomous/maintenance_supersession.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
OLD = b'{"schema":1, "inflight":{"mutation_pending":true,"fixture":"unknown"}}'
IDLE = b'{"schema":1,"inflight":null}'


class Fixture:
    def __init__(self, fault=None):
        self.raw = OLD
        self.records = {}
        self.events = []
        self.locked = False
        self.fault = fault
        self.saves = 0

    def __enter__(self):
        assert not self.locked
        self.locked = True
        self.events.append('lock')
        return self

    def __exit__(self, *args):
        self.locked = False
        self.events.append('unlock')

    def verify_namespace(self):
        assert self.locked
        if self.fault == 'namespace':
            raise RuntimeError('namespace drift')

    def read_marker(self):
        self.verify_namespace()
        return self.raw

    def validate_approval(self, approval, raw):
        self.verify_namespace()
        return approval == {'fixture_plan': 'approved'} and raw == OLD

    def is_unknown(self, raw):
        return raw == OLD

    def is_known_idle(self, raw):
        return raw == IDLE

    def durable_record(self, kind, raw):
        self.verify_namespace()
        self.events.append(kind)
        if self.fault == kind:
            raise OSError('write/fsync outcome unavailable')
        if kind in self.records:
            raise FileExistsError(kind)
        self.records[kind] = raw

    def read_record(self, kind):
        self.verify_namespace()
        if self.fault == kind + '-read':
            return b'changed'
        return self.records[kind]

    def save(self, value):
        self.verify_namespace()
        assert value is None
        self.saves += 1
        self.events.append('save')
        if self.fault == 'save-before':
            raise OSError('before rename')
        self.raw = IDLE
        if self.fault == 'save-after':
            raise OSError('after rename/fsync/verify unknown')
        if self.fault == 'save-drift':
            self.raw = b'{"schema":1,"inflight":{"fixture":"new-owner"}}'

    def effect(self, phase, keys):
        self.verify_namespace()
        self.events.append(phase)
        if self.fault == phase:
            raise RuntimeError('boundary unavailable')
        if self.fault == phase + '-drift':
            self.raw = b'new-owner-marker'
        result = dict.fromkeys(keys, True)
        result['evidence_sha256'] = 'a' * 64
        if self.fault == phase + '-false':
            result[keys[0]] = False
        if self.fault == phase + '-truthy':
            result[keys[0]] = 1
        return result

    def hold(self):
        return self.effect('hold', M.HOLD)

    def terminate(self):
        return self.effect('terminate', M.BOUNDARY)

    def reconcile(self):
        return self.effect('reconcile', M.RECONCILE)

    def restore(self):
        return self.effect('restore', M.RESTORE)


class MaintenanceTests(unittest.TestCase):
    def run_once(self, f, approval=None):
        return M.supersede(f, f, approval=(
            {'fixture_plan': 'approved'} if approval is None else approval))

    def test_order_same_mutex_and_exact_history_before_clear(self):
        f = Fixture()
        result = self.run_once(f)
        self.assertEqual(f.events, ['lock', 'intent', 'hold', 'terminate',
            'reconcile', 'supersession', 'save', 'restore', 'unlock'])
        journal = json.loads(f.records['intent'])
        receipt = json.loads(f.records['supersession'])
        self.assertEqual(base64.b64decode(journal['original_marker_base64']), OLD)
        self.assertEqual(journal['historical_outcome'], 'UNKNOWN')
        self.assertEqual(receipt['historical_outcome'], 'UNKNOWN')
        self.assertEqual(result['historical_outcome'], 'UNKNOWN')
        self.assertEqual(result['disposition'], 'superseded-by-explicit-maintenance')
        self.assertEqual(f.saves, 1)
        self.assertFalse(f.locked)

    def test_every_precommit_fault_preserves_original_no_restore_no_retry(self):
        faults = ['namespace', 'intent', 'intent-read', 'hold', 'terminate',
            'reconcile', 'supersession', 'supersession-read']
        faults += [phase + suffix for phase in ('hold', 'terminate', 'reconcile')
                   for suffix in ('-false', '-truthy')]
        for fault in faults:
            with self.subTest(fault=fault):
                f = Fixture(fault)
                with self.assertRaises((RuntimeError, OSError)):
                    self.run_once(f)
                self.assertEqual(f.raw, OLD)
                self.assertEqual(f.saves, 0)
                self.assertNotIn('restore', f.events)
                self.assertFalse(f.locked)

    def test_new_marker_is_never_overwritten(self):
        for phase in ('hold', 'terminate', 'reconcile'):
            f = Fixture(phase + '-drift')
            with self.assertRaises(M.MaintenanceDenied):
                self.run_once(f)
            self.assertEqual(f.raw, b'new-owner-marker')
            self.assertEqual(f.saves, 0)
            self.assertNotIn('restore', f.events)
            if phase == 'terminate':
                self.assertNotIn('reconcile', f.events)

    def test_final_write_failure_can_have_completed_no_restore_or_rewrite(self):
        for fault, expected in (('save-before', OLD), ('save-after', IDLE)):
            f = Fixture(fault)
            with self.assertRaises(OSError):
                self.run_once(f)
            self.assertEqual(f.raw, expected)
            self.assertEqual(f.saves, 1)
            self.assertIn('intent', f.records)
            self.assertIn('supersession', f.records)
            self.assertNotIn('restore', f.events)

    def test_new_owner_after_write_blocks_restore(self):
        f = Fixture('save-drift')
        with self.assertRaises(M.MaintenanceDenied):
            self.run_once(f)
        self.assertIn(b'new-owner', f.raw)
        self.assertEqual(f.saves, 1)
        self.assertNotIn('restore', f.events)

    def test_unapproved_plan_denied_before_journal_or_effects(self):
        f = Fixture()
        with self.assertRaises(M.MaintenanceDenied):
            self.run_once(f, {'fixture_plan': 'different'})
        self.assertEqual(f.events, ['lock', 'unlock'])

    def test_no_retry_over_existing_intent(self):
        f = Fixture()
        f.records['intent'] = b'previous unknown intent'
        with self.assertRaises(FileExistsError):
            self.run_once(f)
        self.assertNotIn('hold', f.events)
        self.assertEqual(f.saves, 0)

    def test_restore_failure_keeps_durable_history_no_second_save(self):
        f = Fixture('restore')
        with self.assertRaises(RuntimeError):
            self.run_once(f)
        self.assertEqual(f.raw, IDLE)
        self.assertEqual(f.saves, 1)
        self.assertIn('supersession', f.records)


if __name__ == '__main__':
    unittest.main()
