"""Bounded PCM playback clock, including gaps between streamed sentences."""
import threading
import time


class SpeechClock:
    def __init__(self, sample_rate, latency_seconds=0.08):
        self.bytes_per_second = sample_rate * 2
        self.latency = latency_seconds
        self.lock = threading.Lock()
        self.end = self.base = 0
        self.started = None

    def _position(self):
        if self.started is None:
            return 0
        elapsed = max(0, time.monotonic() - self.started - self.latency)
        return min(self.end, self.base + int(elapsed * self.bytes_per_second))

    def feed(self, count):
        with self.lock:
            position = self._position()
            if self.started is None or position >= self.end:
                self.base = self.end
                self.started = time.monotonic()
            self.end += count

    def position(self):
        with self.lock:
            return self._position() // 2 * 2

    def seconds(self):
        return self.position() / self.bytes_per_second
