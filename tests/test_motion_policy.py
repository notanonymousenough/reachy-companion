from pathlib import Path
import tempfile
import unittest
from reachy_companion.motion_policy import MotionPolicy


class PolicyTests(unittest.TestCase):
    def test_owned_grant_cleanup_cannot_overwrite_new_human_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            state=MotionPolicy(Path(directory)/'policy.json')
            grant=dict(motor_enabled=True,quiet=False,privacy_all=False)
            state.save(grant,expected_epoch=0,owner_id='runtime')
            self.assertEqual(state.owned_snapshot()[1],'runtime')
            state.save(dict(grant,quiet=True))
            before=state.path.read_bytes()
            with self.assertRaises(RuntimeError):state.save(dict(grant,motor_enabled=False),expected_epoch=1,expected_owner_id='runtime')
            self.assertEqual(state.path.read_bytes(),before)
            self.assertIsNone(state.owned_snapshot()[1])

    def test_failed_activation_human_same_epoch_and_restart_nonce_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state=MotionPolicy(Path(directory)/'policy.json');denial=dict(motor_enabled=False,quiet=True,privacy_all=False)
            state.save(denial)  # Human wins before delayed runtime CAS.
            with self.assertRaises(RuntimeError):state.save(dict(denial,motor_enabled=True),expected_epoch=0,owner_id='runtime')
            before=state.path.read_bytes()
            with self.assertRaises(RuntimeError):state.save(denial,expected_epoch=1,expected_owner_id='runtime')
            self.assertEqual(state.path.read_bytes(),before)
            state.save(denial,expected_epoch=1,owner_id='runtime')
            restarted=MotionPolicy(state.path)
            with self.assertRaises(RuntimeError):restarted.save(denial,expected_epoch=2,expected_owner_id='runtime')
            self.assertEqual(set(restarted.snapshot()),{'motor_enabled','quiet','privacy_all','epoch'})

    def test_cleanup_before_late_activation_invalidates_its_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            state=MotionPolicy(Path(directory)/'policy.json');denial=dict(motor_enabled=False,quiet=False,privacy_all=False)
            state.save(denial,expected_epoch=0)
            with self.assertRaises(RuntimeError):state.save(dict(denial,motor_enabled=True),expected_epoch=0,owner_id='late')
            self.assertFalse(state.snapshot()['motor_enabled'])
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
