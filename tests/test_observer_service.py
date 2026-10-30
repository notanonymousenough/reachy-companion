"""Single-use offline service authorization; no network or installed units."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('observer_service', ROOT/'deploy/autonomous/observer_service.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class ObserverLaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.arm = Path(self.tmp.name)/'arm.local.json'
        self.value = dict(agent_url='http://127.0.0.1:8090', hub_url='http://127.0.0.1:8080',
            agent_boot='fixture', microphone_epoch=1, policy_epoch=2, controller='fixture-owner')
        self.arm.write_text(json.dumps(self.value))

    def test_single_use_arm_does_not_resume_even_if_replaced_with_same_values(self):
        self.assertEqual(launcher.consume_arm(self.arm), self.value)
        self.assertFalse(self.arm.exists())
        self.arm.write_text(json.dumps(self.value))
        with self.assertRaisesRegex(ValueError, 'fresh coordinator preflight'):
            launcher.consume_arm(self.arm)

    def test_malformed_arm_is_consumed_on_failure_without_retry(self):
        self.value['token'] = 'must-never-be-an-arm-field'
        self.arm.write_text(json.dumps(self.value))
        with self.assertRaisesRegex(ValueError, 'credentials forbidden'): launcher.consume_arm(self.arm)
        self.assertFalse(self.arm.exists())
        with self.assertRaisesRegex(ValueError, 'fresh coordinator preflight'): launcher.consume_arm(self.arm)

    def test_session_uses_file_references_and_existing_native_entrypoint_once(self):
        from reachy_companion.autonomous.config import load
        cfg = load(ROOT/'config.autonomous.native-agent.example.json'); cfg['context']['enabled'] = False
        root = Path(self.tmp.name)
        argv = ['observer_service', 'session', '--config', str(root/'config.json'),
            '--token-file', str(root/'token.local'), '--companion-config', str(root/'private.json'),
            '--arm-file', str(self.arm), '--output', str(root/'report.json'), '--metadata', str(root/'meta.json')]
        captured = []
        with patch.object(sys, 'argv', argv), \
                patch('reachy_companion.autonomous.config.load', return_value=cfg), \
                patch('reachy_companion.autonomous.native_agent_session.main',
                      side_effect=lambda: captured.append(list(sys.argv)) or 0):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(len(captured), 1)
        self.assertIn('--service', captured[0]); self.assertIn('--token-file', captured[0])
        self.assertNotIn('--duration', captured[0]); self.assertNotIn('--allow-stock-settle', captured[0])
        self.assertEqual(captured[0][captured[0].index('--token-file')+1], str(root/'token.local'))
        self.assertFalse(self.arm.exists())


if __name__ == '__main__': unittest.main()
