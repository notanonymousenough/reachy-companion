import unittest

from reachy_companion.alsa_role_observer import observe_roles


class AlsaRoleObserverTests(unittest.TestCase):
    def setUp(self):
        self.parent = dict(pid=10, ppid=1, cgroup='agent', exe='/python', start=1)
        self.child = dict(pid=11, ppid=10, cgroup='agent', exe='/usr/bin/aplay', start=2)

    def observe(self, raw, proc=None):
        return observe_roles(proc or (lambda pid: self.parent if pid == 10 else self.child),
                             [self.child], lambda pid: raw, self.parent)

    def test_empty_does_not_admit_or_prove_absence_valid_later_poll_does_admit(self):
        empty = self.observe(b'')
        self.assertEqual(empty['playbacks'], [])
        self.assertEqual(empty['counts']['empty'], 1)
        self.assertFalse(empty['absence_verified'])
        self.assertEqual(self.observe(b'/usr/bin/aplay\0-q\0')['playbacks'], [self.child])

    def test_unknown_oversize_and_malformed_never_admitted_or_prove_absence(self):
        for raw in (b'private-name\0', b'aplay', b'x' * 8193, None):
            with self.subTest(raw_type=type(raw)):
                result = self.observe(raw)
                self.assertFalse(result['absence_verified'])
                self.assertEqual(result['playbacks'], [])
                self.assertEqual(result['counts']['unknown'], 1)

    def test_capture_alias_and_capture_options_rejected(self):
        for raw in (b'arecord\0', b'aplay\0-C\0', b'aplay\0-qC\0', b'aplay\0--capture\0'):
            result = self.observe(raw)
            self.assertEqual(result['counts']['capture'], 1)
            self.assertTrue(result['absence_verified'])
            self.assertEqual(result['playbacks'], [])

    def test_child_disappearance_and_reuse_are_races(self):
        calls = []
        def proc(pid):
            if pid == 10: return self.parent
            calls.append(pid)
            return self.child if len(calls) == 1 else dict(self.child, start=3)
        result = self.observe(b'aplay\0', proc)
        self.assertEqual(result['counts']['raced'], 1)
        self.assertFalse(result['absence_verified'])
        def missing(pid):
            if pid == 10: return self.parent
            raise FileNotFoundError()
        self.assertEqual(self.observe(b'aplay\0', missing)['counts']['raced'], 1)

    def test_parent_drift_after_scan_always_aborts_even_empty_child(self):
        calls = []
        def proc(pid):
            if pid == 11: return self.child
            calls.append(pid)
            return self.parent if len(calls) == 1 else dict(self.parent, start=9)
        with self.assertRaisesRegex(ValueError, 'agent_identity_changed'):
            self.observe(b'', proc)

    def test_foreign_parent_or_cgroup_never_admitted(self):
        for changed in (dict(self.child, ppid=99), dict(self.child, cgroup='foreign')):
            result = observe_roles(lambda pid: self.parent if pid == 10 else changed,
                                   [changed], lambda pid: b'aplay\0', self.parent)
            self.assertEqual(result['playbacks'], [])
            self.assertFalse(result['absence_verified'])
            self.assertEqual(result['counts']['raced'], 1)

    def test_permission_failure_propagates_and_empty_candidates_prove_absence(self):
        def denied(pid): raise PermissionError()
        with self.assertRaises(PermissionError):
            observe_roles(lambda pid: self.parent if pid == 10 else self.child,
                          [self.child], denied, self.parent)
        self.assertTrue(observe_roles(lambda pid: self.parent, [], denied,
                                     self.parent)['absence_verified'])
