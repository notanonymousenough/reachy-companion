"""Saved conversation selection. It grants no audio, initiative or motor authority."""
import json
import os
from pathlib import Path
import tempfile
import threading


MODES = ('normal', 'alice_test')


def validate_saved(value):
    if (type(value) is not dict or set(value) != {'version', 'mode', 'generation'}
            or type(value['version']) is not int or value['version'] != 1
            or type(value['mode']) is not str or value['mode'] not in MODES
            or type(value['generation']) is not int or not 0 <= value['generation'] < 2**63):
        raise ValueError('Invalid saved conversation mode')
    return dict(value)


class ConversationMode:
    def __init__(self, path, default='normal'):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.value = validate_saved(dict(version=1, mode=default, generation=0))
        self.error = None
        try:
            if self.path.exists():
                self.value = validate_saved(json.loads(self.path.read_text()))
            else:
                self._write(self.value)
        except (OSError, ValueError, KeyError, TypeError):
            # A damaged setting never silently re-enables Alice addressing.
            self.value = dict(version=1, mode='normal', generation=0)
            self.error = 'Conversation mode could not be loaded or saved'

    def snapshot(self):
        with self.lock:
            return dict(self.value, error=self.error)

    def save(self, mode, expected_generation):
        with self.lock:
            if type(mode) is not str or mode not in MODES:
                raise ValueError('Unknown conversation mode')
            if type(expected_generation) is not int or expected_generation != self.value['generation']:
                raise RuntimeError('Conversation mode changed')
            if self.value['generation'] >= 2**63 - 1:
                raise RuntimeError('Conversation mode generation exhausted')
            value = dict(version=1, mode=mode, generation=expected_generation + 1)
            try:
                self._write(value)
            except OSError:
                self.error = 'Conversation mode could not be saved'
                raise
            self.value = value
            self.error = None
            return self.snapshot()

    def _write(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=self.path.name + '.', suffix='.tmp', dir=self.path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, 'w') as out:
                json.dump(value, out)
                out.flush()
                os.fsync(out.fileno())
            temporary.replace(self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
