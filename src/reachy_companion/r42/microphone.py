"""Persistent operator microphone switch, independent of temporary test pause."""
import json
import os
from pathlib import Path
import tempfile


def validate_control(payload):
    """Validate the existing Agent microphone API without importing audio code."""
    allowed = {'enabled', 'listen', 'expected_boot_id', 'expected_epoch', 'owner_id', 'expected_owner_id'}
    if type(payload) is not dict or set(payload) - allowed or type(payload.get('enabled')) is not bool:
        raise ValueError('Expected enabled boolean and supported microphone fields')
    if 'listen' in payload and type(payload['listen']) is not bool:
        raise ValueError('listen must be boolean')
    authority = 'expected_boot_id' in payload or 'expected_epoch' in payload
    if authority and (type(payload.get('expected_boot_id')) is not str
            or not 1 <= len(payload['expected_boot_id']) <= 256
            or type(payload.get('expected_epoch')) is not int
            or not 0 <= payload['expected_epoch'] < 2**63):
        raise ValueError('Complete microphone authority required')
    for key in ('owner_id', 'expected_owner_id'):
        if key in payload and (not authority or type(payload[key]) is not str or not 1 <= len(payload[key]) <= 128):
            raise ValueError('Bounded microphone owner requires authority')


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
