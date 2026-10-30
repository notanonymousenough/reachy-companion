"""Saved speaker level; microphone capture controls are never involved."""
import json
import os
from pathlib import Path


def validate_percent(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ValueError('volume_percent must be an integer between 0 and 100')
    return value


class PlaybackVolume:
    def __init__(self, path, default):
        self.path = Path(path)
        self.percent = validate_percent(default)
        if self.path.exists():
            try:
                self.percent = validate_percent(json.loads(self.path.read_text())['volume_percent'])
            except (OSError, ValueError, KeyError, TypeError):
                pass

    def save(self, percent):
        validate_percent(percent)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump({'volume_percent': percent}, out)
        temporary.replace(self.path)
        self.percent = percent
