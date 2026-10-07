"""Time-based charge reminder; never presents a fictitious battery measurement."""
import json
import math
import os
import threading
import time
from pathlib import Path


class ChargeReminder:
    def __init__(self, path, settings):
        self.path = Path(path)
        self.settings = settings
        self.lock = threading.Lock()
        self.seconds = 0.0
        self.since = None
        self.online = False
        self.updated = time.monotonic()
        self.saved = self.updated
        self.error = None
        try:
            if self.path.exists():
                state = json.loads(self.path.read_text())
                seconds = float(state['active_seconds'])
                if not math.isfinite(seconds) or seconds < 0:
                    raise ValueError('Invalid reminder state')
                self.seconds = seconds
                self.since = state.get('charged_at')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.error = str(exc)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'active_seconds': self.seconds, 'charged_at': self.since}))
        temporary.chmod(0o600)
        os.replace(temporary, self.path)
        self.saved = time.monotonic()

    def observe(self, online):
        with self.lock:
            now = time.monotonic()
            if self.online and online:
                self.seconds += max(0, now-self.updated)
            self.online, self.updated = bool(online), now
            if now-self.saved >= 30:
                self._save()

    def reset(self):
        with self.lock:
            self.seconds = 0.0
            self.since = time.time()
            self.updated = time.monotonic()
            self._save()
        return self.status()

    def status(self):
        with self.lock:
            enabled = self.settings['reminder_enabled']
            return {'source': 'usage_timer', 'battery_percent': None, 'battery_sensor_available': False,
                    'reminder_enabled': enabled, 'active_minutes': round(self.seconds/60),
                    'remind_after_minutes': self.settings['remind_after_minutes'],
                    'charge_reminder_due': enabled and self.seconds >= self.settings['remind_after_minutes']*60,
                    'charged_at': self.since, 'robot_online': self.online, 'state_error': self.error}
