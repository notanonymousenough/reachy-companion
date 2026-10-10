from pathlib import Path
import tempfile
import unittest
from reachy_companion.motion_policy import MotionPolicy


class PolicyTests(unittest.TestCase):
    def test_default_denial_durable_epoch_and_corruption_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'policy.json';state=MotionPolicy(path)
            self.assertFalse(state.snapshot()['motor_enabled'])
            saved=state.save(dict(motor_enabled=True,quiet=False,privacy_all=False))
            self.assertEqual(saved['epoch'],1)
            self.assertEqual(MotionPolicy(path).snapshot(),saved)
            changed=state.save(dict(motor_enabled=True,quiet=True,privacy_all=False))
            self.assertEqual(changed['epoch'],2)
            path.write_text('{"motor_enabled":true,"motor_enabled":false}')
            self.assertIsNone(state.snapshot()['epoch'])
            self.assertTrue(state.snapshot()['privacy_all'])
            with self.assertRaises(RuntimeError):state.save(dict(motor_enabled=True,quiet=False,privacy_all=False))

    def test_numeric_grants_and_unknown_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state=MotionPolicy(Path(directory)/'policy.json')
            for value in (dict(motor_enabled=1,quiet=False,privacy_all=False),dict(motor_enabled=True,quiet=False,privacy_all=False,epoch=3)):
                with self.assertRaises(ValueError):state.save(value)
            self.assertFalse(state.path.exists())
