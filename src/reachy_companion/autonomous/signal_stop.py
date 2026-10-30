"""Event-compatible stop flag whose signal handler never acquires a lock."""
import threading


class SignalStop(threading.Event):
    """Signals set a plain flag; ordinary control threads retain Event.set().

    Calling Event.set() from a Python signal handler can re-enter the Event's
    non-reentrant condition lock while the main thread is inside wait/set.
    Session loops already poll with bounded waits. Indefinite waiters poll at
    50 ms so a signal also releases them without notifying a condition.
    """
    def __init__(self):
        super().__init__()
        self._signal_requested = False

    def request_signal(self, *_):
        self._signal_requested = True

    def is_set(self):
        return self._signal_requested or super().is_set()

    def wait(self, timeout=None):
        if timeout is None:
            while not self.is_set():
                super().wait(.05)
        elif not self.is_set():
            super().wait(timeout)
        return self.is_set()
