"""Explicit, pinned R42 runtime; never selected as an implicit fallback."""
import hashlib
import json
import os
from pathlib import Path


def verify():
    """Verify the installed profile without importing drivers or opening devices."""
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('R42 package file mismatch: ' + name)
    return manifest


def serve(config, *, test_speaker=False):
    verify()
    if config['conversation'].get('capture_pump_enabled') is not True:
        raise ValueError('R42 requires explicit conversation.capture_pump_enabled=true')
    from .agent import main
    return main(config, test_speaker=test_speaker)


def control(config, action):
    verify()
    from .initiative import control as run
    enabled = {'auto-on': True, 'auto-off': False, 'auto-status': None,
               'arm': True, 'off': False, 'status': None}[action]
    # The frozen thin client resolves Config from this environment variable.
    # Restore it for callers embedding the CLI in an existing Python process.
    previous = os.environ.get('REACHY_COMPANION_CONFIG')
    try:
        os.environ['REACHY_COMPANION_CONFIG'] = str(config.filename)
        return run(enabled, schedule=action.startswith('auto-'))
    finally:
        if previous is None:
            os.environ.pop('REACHY_COMPANION_CONFIG', None)
        else:
            os.environ['REACHY_COMPANION_CONFIG'] = previous
