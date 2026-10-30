"""Signal delivery during an Event operation must not deadlock cleanup."""
import signal
import subprocess
import sys
import threading
import unittest

from reachy_companion.autonomous.signal_stop import SignalStop


class SignalStopTests(unittest.TestCase):
    def test_real_signal_while_event_condition_is_held_does_not_reenter_lock(self):
        # Isolate the failure mode: Event.set as a handler would hang this child.
        program = '''
import signal
from reachy_companion.autonomous.signal_stop import SignalStop
stop = SignalStop()
signal.signal(signal.SIGTERM, stop.request_signal)
with stop._cond:
    signal.raise_signal(signal.SIGTERM)
    assert stop.is_set()
assert stop.wait(0)
'''
        result = subprocess.run([sys.executable, '-c', program], capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_signal_releases_indefinite_waiter_without_condition_notification(self):
        stop = SignalStop()
        result = []
        waiter = threading.Thread(target=lambda: result.append(stop.wait()), daemon=True)
        waiter.start()
        stop.request_signal()
        waiter.join(1)
        self.assertFalse(waiter.is_alive())
        self.assertEqual(result, [True])

    def test_ordinary_control_set_and_bounded_timeout_still_work(self):
        stop = SignalStop()
        self.assertFalse(stop.wait(.001))
        stop.set()
        self.assertTrue(stop.is_set())
        self.assertTrue(stop.wait(0))
