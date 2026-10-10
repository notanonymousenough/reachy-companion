import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reachy_companion.microphone import MicrophoneState


class MicrophonePersistenceTests(unittest.TestCase):
    def test_legacy_mute_and_monotonic_epoch_survive_restart(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'microphone.json';path.write_text('{"enabled":false}')
            state=MicrophoneState(path,True)
            self.assertFalse(state.enabled);self.assertEqual(state.epoch,0)
            state.save(False)
            restarted=MicrophoneState(path,True)
            self.assertFalse(restarted.enabled);self.assertEqual(restarted.epoch,1)
            restarted.save(False)
            self.assertEqual(MicrophoneState(path).epoch,2)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(list(Path(root).glob('*.tmp')),[])

    def test_file_and_directory_synced_before_success(self):
        with tempfile.TemporaryDirectory() as root:
            state=MicrophoneState(Path(root)/'microphone.json',False)
            with patch('reachy_companion.microphone.os.fsync',wraps=__import__('os').fsync) as sync:
                state.save(False)
            self.assertEqual(sync.call_count,2)

    def test_failed_persistence_disables_current_process_and_reports_unknown_durability(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'microphone.json';path.write_text('{"enabled":true,"epoch":3}')
            state=MicrophoneState(path)
            with patch('reachy_companion.microphone.os.fsync',side_effect=OSError('fixture disk failure')):
                with self.assertRaises(OSError):state.save(False)
            self.assertFalse(state.enabled);self.assertEqual(state.epoch,4)
            self.assertIn('disk failure',state.error)
            self.assertEqual(list(Path(root).glob('*.tmp')),[])
            # Failure cannot promise durable mute: last durable file is explicit.
            self.assertTrue(MicrophoneState(path).enabled)

    def test_corrupt_epoch_or_boolean_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'microphone.json'
            for epoch in (-1,True,'1',2**63):
                path.write_text(json.dumps(dict(enabled=True,epoch=epoch)))
                state=MicrophoneState(path)
                self.assertFalse(state.enabled);self.assertIsNotNone(state.error)
            state.epoch=2**63-1
            with self.assertRaises(ValueError):state.save(True)
            self.assertFalse(state.enabled)


if __name__=='__main__':unittest.main()
