import subprocess
import sys
import tempfile
import threading
import unittest
from reachy_companion.autonomous.actuator_guard import ActuatorGuard, GuardRejected
from reachy_companion.autonomous.contracts import Authority


def arm(guard, **override):
    options = dict(microphone_enabled=True, quiet=False, privacy_all=False, fence_attested=True)
    options.update(override)
    return guard.arm(Authority('hub-test', 'pc-test', robot_boot_id=guard.robot_boot_id), **options)


class GuardTests(unittest.TestCase):
    def test_operator_gates_no_dispatch_and_old_boot(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = ActuatorGuard(directory, lambda: True)
            try:
                for options in (dict(microphone_enabled=False), dict(quiet=True), dict(privacy_all=True),
                                dict(fence_attested=False), dict(microphone_enabled='yes')):
                    with self.assertRaises(GuardRejected): arm(guard, **options)
                with self.assertRaises(GuardRejected):
                    guard.arm(Authority('hub', 'pc'), microphone_enabled=True, quiet=False,
                              privacy_all=False, fence_attested=True)
                self.assertFalse(guard.status()['leased'])
            finally: guard.close()

    def test_duplicate_sequence_expiry_never_renews_old_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [0.]
            stops = []
            guard = ActuatorGuard(directory, lambda: stops.append(True) or True, clock=lambda: now[0])
            try:
                lease = arm(guard)
                guard.heartbeat(lease, 1)
                with self.assertRaises(GuardRejected): guard.heartbeat(lease, 1)
                self.assertTrue(guard.admit(lease, 'one'))
                self.assertFalse(guard.admit(lease, 'one'))
                now[0] = .5
                with self.assertRaises(GuardRejected): guard.heartbeat(lease, 2)
                self.assertEqual(stops, [True])
                replacement = arm(guard)
                with self.assertRaises(GuardRejected): guard.admit(lease, 'late')
                self.assertTrue(guard.admit(replacement, 'fresh'))
            finally: guard.close()

    def test_watchdog_stops_without_scheduler_or_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            stopped = threading.Event()
            guard = ActuatorGuard(directory, lambda: stopped.set() or True, ttl=.1, poll=.01)
            try:
                arm(guard)
                self.assertTrue(stopped.wait(1))
                self.assertFalse(guard.status()['leased'])
                self.assertFalse(guard.status()['quarantined'])
            finally: guard.close()

    def test_unknown_stop_persists_restart_and_requires_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = ActuatorGuard(directory, lambda: False)
            lease = arm(guard)
            guard.revoke()
            self.assertTrue(guard.status()['quarantined'])
            guard.close()
            replacement = ActuatorGuard(directory, lambda: True)
            try:
                with self.assertRaises(GuardRejected): arm(replacement)
                with self.assertRaises(GuardRejected): replacement.acknowledge_stopped(verified_stopped=False)
                replacement.acknowledge_stopped(verified_stopped=True)
                arm(replacement)
                with self.assertRaises(GuardRejected): replacement.admit(lease, 'late-after-restart')
            finally: replacement.close()

    def test_durability_failure_cannot_skip_stop(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            stopped = []
            guard = ActuatorGuard(directory, lambda: stopped.append(True) or True)
            arm(guard)
            def failed_write(status): raise sqlite3.OperationalError('storage unavailable')
            guard.write = failed_write
            guard.revoke()
            self.assertEqual(stopped, [True])
            self.assertTrue(guard.status()['quarantined'])
            guard.close()
            replacement = ActuatorGuard(directory, lambda: True)
            try: self.assertTrue(replacement.status()['quarantined'])
            finally: replacement.close()

    def test_capacity_withdraws_without_evicting_tombstones(self):
        with tempfile.TemporaryDirectory() as directory:
            guard = ActuatorGuard(directory, lambda: True, clock=lambda: 0)
            try:
                lease = arm(guard)
                for n in range(256): self.assertTrue(guard.admit(lease, str(n)))
                with self.assertRaises(GuardRejected): guard.admit(lease, 'overflow')
                self.assertFalse(guard.status()['leased'])
                with self.assertRaises(GuardRejected): guard.admit(lease, '0')
            finally: guard.close()

    def test_process_lock_and_crash_active_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            code = '''import sys
from reachy_companion.autonomous.actuator_guard import ActuatorGuard
from reachy_companion.autonomous.contracts import Authority
g=ActuatorGuard(sys.argv[1], lambda: True, clock=lambda: 0)
g.arm(Authority('hub', 'pc', robot_boot_id=g.robot_boot_id), microphone_enabled=True, quiet=False, privacy_all=False, fence_attested=True)
print('armed', flush=True)
sys.stdin.read()
'''
            child = subprocess.Popen([sys.executable, '-c', code, directory], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'armed')
                with self.assertRaises(GuardRejected): ActuatorGuard(directory, lambda: True)
                child.kill(); child.wait(timeout=3)
                replacement = ActuatorGuard(directory, lambda: True)
                try:
                    self.assertTrue(replacement.status()['quarantined'])
                    with self.assertRaises(GuardRejected): arm(replacement)
                finally: replacement.close()
            finally:
                if child.poll() is None: child.kill(); child.wait(timeout=3)
                for handle in (child.stdin, child.stdout, child.stderr): handle.close()


if __name__ == '__main__': unittest.main()
