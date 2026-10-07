"""Persistent operator microphone switch, independent of temporary test pause."""
import json
import os
from pathlib import Path


class MicrophoneState:
    def __init__(self, path, default=True):
        self.path = Path(path)
        self.enabled = default
        self.error = None
        if self.path.exists():
            try:
                value = json.loads(self.path.read_text())['enabled']
                if not isinstance(value, bool):
                    raise ValueError('Microphone state must be boolean')
                self.enabled = value
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.enabled = False
                self.error = str(exc)

    def save(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be boolean')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump({'enabled': enabled}, out)
        temporary.replace(self.path)
        self.enabled = enabled
        self.error = None
