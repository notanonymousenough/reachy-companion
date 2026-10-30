"""One Agent entrypoint and the same config for initiative controls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from reachy_companion import __main__ as cli
from reachy_companion.config import Config
from reachy_companion.deployment import service_unit
from reachy_companion.code_identity import MODULES, source_manifest

ROOT = Path(__file__).resolve().parents[1]


class AgentRuntimeTests(unittest.TestCase):
    def config(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'config.json'
        value = json.loads((ROOT / 'config.example.json').read_text())
        value['runtime']['profile'] = ''
        path.write_text(json.dumps(value))
        return Config(path, require_token=False)

    def test_initial_listening_setting_and_persisted_off_have_one_startup_path(self):
        config = self.config()
        config.data['conversation']['listen_on_start'] = True
        config.data['conversation']['expressions']['enabled'] = False
        with patch.dict('sys.modules', {'webrtcvad': Mock()}):
            from reachy_companion.agent import Agent
        first = Agent(config)
        self.addCleanup(first.stopping.set)
        self.assertTrue(first.listening.is_set())
        first.set_microphone(False)
        restarted = Agent(config)
        self.addCleanup(restarted.stopping.set)
        self.assertFalse(restarted.microphone.enabled)
        self.assertFalse(restarted.listening.is_set())

    def test_invalid_intent_cannot_use_initial_listening_default(self):
        from reachy_companion.durable_intent import DurableIntent
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'intent.json'
            path.write_text('{invalid')
            intent = DurableIntent(path, default_listening=True)
            self.assertTrue(intent.error)
            self.assertFalse(intent.snapshot()['listening_requested'])

    def test_service_has_one_agent_command_even_with_legacy_config(self):
        config = self.config()
        for legacy in (None, 'default', 'r42'):
            config.data['deployment']['robot']['agent_runtime_profile'] = legacy
            unit = service_unit(config, 'robot', 'agent')
            self.assertIn(' agent serve\n', unit)
            self.assertNotIn('--runtime-profile', unit)

    def test_cli_uses_the_canonical_agent(self):
        config = self.config()
        agent = Mock()
        with patch('reachy_companion.config.Config', return_value=config), \
                patch.dict('sys.modules', {'reachy_companion.agent': agent}):
            for action in ('serve', 'test-speaker'):
                with patch('sys.argv', ['companion', 'agent', action]):
                    self.assertEqual(cli.main(), 0)
                agent.main.assert_called_with(config, test_speaker=action == 'test-speaker')

    def test_initiative_cli_passes_explicit_config_without_environment_mutation(self):
        config = self.config()
        with patch('reachy_companion.config.Config', return_value=config), \
                patch('reachy_companion.initiative.control') as control:
            for action, enabled, schedule in (('auto-on', True, True), ('off', False, False),
                                               ('status', None, False)):
                with patch('sys.argv', ['companion', '--config', str(config.filename), 'initiative', action]):
                    self.assertEqual(cli.main(), 0)
                control.assert_called_with(enabled, schedule=schedule, config=config)

    def test_source_manifest_covers_promoted_helpers_without_a_duplicate_package(self):
        package = ROOT / 'src/reachy_companion'
        manifest = source_manifest(package, '/reviewed/site-packages/reachy_companion')
        self.assertEqual(set(manifest['modules']), MODULES)
        for name in ('agent', 'initiative', 'sensory_bridge', 'conversation_mode', 'snapshot_vision'):
            self.assertIn('reachy_companion.' + name, manifest['modules'])
        self.assertFalse((package / 'r42').exists())
