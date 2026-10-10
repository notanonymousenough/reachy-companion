"""Persistent operator microphone switch, independent of temporary test pause."""
import json
import os
from pathlib import Path
import tempfile


class MicrophoneState:
    def __init__(self, path, default=True):
        self.path = Path(path)
        self.enabled = default
        self.epoch = 0
        self.error = None
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text())
                value = saved['enabled']
                if not isinstance(value, bool):
                    raise ValueError('Microphone state must be boolean')
                epoch = saved.get('epoch', 0)  # Existing operator switch files.
                if type(epoch) is not int or not 0 <= epoch < 2**63:
                    raise ValueError('Invalid microphone epoch')
                self.enabled = value
                self.epoch = epoch
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.enabled = False
                self.error = str(exc)

    def save(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be boolean')
        if self.epoch >= 2**63-1:
            self.enabled = False
            self.error = 'Microphone epoch exhausted'
            raise ValueError(self.error)
        self.epoch += 1
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=self.path.name+'.',suffix='.tmp',dir=self.path.parent)
            temporary = Path(name)
            with os.fdopen(fd, 'w') as out:
                json.dump({'enabled': enabled, 'epoch': self.epoch}, out)
                out.flush()
                os.fsync(out.fileno())
            temporary.replace(self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:os.fsync(directory_fd)
            finally:os.close(directory_fd)
            self.enabled = enabled
            self.error = None
        except (OSError, ValueError) as exc:
            self.enabled = False
            self.error = str(exc)
            raise
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
