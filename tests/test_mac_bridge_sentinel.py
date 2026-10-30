"""Offline transport-health lifecycle traces; no network/devices."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1]/'deploy/autonomous/mac_bridge_sentinel.py'
spec = importlib.util.spec_from_file_location('mac_bridge_sentinel', path)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SentinelTests(unittest.TestCase):
    def make(self, results):
        self.now = 0.
        self.saved, self.ready = [], []
        self.alive, self.same = True, True
        def identity():
            if not self.alive: raise s.LinkLost()
            if not self.same: raise s.IdentityMismatch()
        values = iter(results)
        return s.Monitor(identity, lambda: next(values), self.saved.append,
                         lambda: self.ready.append(True), clock=lambda: self.now)

    def test_timeout_then_fresh_same_identity_is_recovery(self):
        m = self.make([{'ok': True}, {'ok': False, 'error': 'TimeoutError'}, {'ok': True}])
        self.assertTrue(m.step()); self.now = .2
        self.assertTrue(m.step()); self.assertEqual(m.state, 'HEALTH_UNAVAILABLE')
        self.assertIsNone(m.terminal); self.now = .8
        self.assertTrue(m.step()); self.assertEqual(m.counts['recoveries'], 1)
        self.assertEqual(len(self.ready), 1)

    def test_actual_dead_reverse_listener_closes(self):
        m = self.make([{'ok': True}]); m.step(); self.alive = False
        self.assertFalse(m.step()); self.assertEqual(m.terminal, 'LinkLost')

    def test_identity_replaced_closes_without_rebind(self):
        m = self.make([{'ok': True}]); m.step(); self.same = False
        self.assertFalse(m.step()); self.assertEqual(m.terminal, 'IdentityMismatch')
        self.assertEqual(len(self.ready), 1)

    def test_identity_changes_during_response_cannot_recover(self):
        m = self.make([])
        def probe():
            self.same = False
            return {'ok': True}
        m.probe = probe
        self.assertFalse(m.step()); self.assertFalse(self.ready)

    def test_permanent_health_unavailable_bounded_shutdown(self):
        m = self.make([{'ok': False, 'error': 'TimeoutError'}]*8)
        for t in [0., .6, 1.2, 1.8, 2.4]:
            self.now = t; self.assertTrue(m.step())
        self.now = 3.; self.assertFalse(m.step())
        self.assertEqual(m.terminal, 'health_unavailable_budget')
        self.assertFalse(self.ready)

    def test_late_success_cannot_extend_outage_budget(self):
        m = self.make([{'ok': False, 'error': 'TimeoutError'}, {'ok': True}])
        self.assertTrue(m.step()); self.now = 3.1
        self.assertFalse(m.step()); self.assertFalse(self.ready)
        self.assertEqual(m.counts['reads'], 2)
        self.assertEqual(m.counts['recoveries'], 0)

    def test_kernel_reverse_listener_identity_loss_and_replacement(self):
        def proc(inode):
            def read(p):
                if str(p).endswith('boot_id'): return 'boot-a\n'
                return ('header\n' + ('0: 0100007F:46B1 00000000:0000 0A 0 0 0 1000 0 '+inode+'\n' if inode else ''))
            return read
        with patch.object(Path, 'read_text', proc('123')):
            expected = s.listener_identity()
            s.check_identity(expected)
        with patch.object(Path, 'read_text', proc(None)):
            with self.assertRaises(s.LinkLost): s.check_identity(expected)
        with patch.object(Path, 'read_text', proc('124')):
            with self.assertRaises(s.IdentityMismatch): s.check_identity(expected)

    def test_metadata_suffix_and_atomic_cleanup_are_bounded(self):
        m = self.make([{'ok': True}]*2000)
        for i in range(2000): self.now = i*.2; m.step()
        self.assertEqual(m.counts['reads'], 2000)
        self.assertEqual(len(m.recent), 16)
        self.assertLess(len(self.saved), 90)
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'status.json'
            s.atomic_save(p, m.snapshot()); s.atomic_save(p, m.snapshot())
            self.assertEqual(list(Path(directory).iterdir()), [p])
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertLess(p.stat().st_size, 16384)
            self.assertEqual(json.loads(p.read_text())['counts']['reads'], 2000)

    def test_http_error_is_secret_free(self):
        class Opener:
            def open(self, *a, **kw):
                raise s.URLError(TimeoutError('sensitive content'))
        result = s.health_read(Opener())
        self.assertEqual(result['cause'], 'TimeoutError')
        self.assertNotIn('sensitive', json.dumps(result))

    def test_failed_read_never_proves_link_loss(self):
        m = self.make([{'ok': False, 'error': 'URLError', 'cause': 'ConnectionRefusedError'}])
        self.assertTrue(m.step()); self.assertIsNone(m.terminal)
        self.assertEqual(m.state, 'HEALTH_UNAVAILABLE')


if __name__ == '__main__': unittest.main()
