"""Profile selection, packaging closure and fail-closed startup without hardware."""
import ast
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from reachy_companion import __main__ as cli, r42
from reachy_companion.config import Config
from reachy_companion.deployment import service_unit

ROOT = Path(__file__).resolve().parents[1]


class ProfileTests(unittest.TestCase):
    def config(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'config.json'
        value = json.loads((ROOT / 'config.example.json').read_text())
        value['runtime']['profile'] = ''
        path.write_text(json.dumps(value))
        return Config(path, require_token=False)

    def test_all_profile_relative_imports_and_assets_are_pinned(self):
        manifest = r42.verify()
        package = Path(r42.__file__).parent
        for name in manifest['files']:
            if not name.endswith('.py'):
                continue
            parent = Path(name).parent.parts
            for node in ast.walk(ast.parse((package / name).read_text())):
                if isinstance(node, ast.ImportFrom) and node.level and node.module:
                    parts = parent[:len(parent) - node.level + 1] + tuple(node.module.split('.'))
                    dependency = '/'.join(parts) + '.py'
                    self.assertIn(dependency, manifest['files'], (name, dependency))
        self.assertIn('assets/autonomous-contracts.json', manifest['files'])
        self.assertIn('assets/pollen-emotions-v1.json', manifest['files'])

    def test_default_service_unchanged_and_explicit_profile_persists(self):
        config = self.config()
        self.assertNotIn('--runtime-profile', service_unit(config, 'robot', 'agent'))
        config.data['deployment']['robot']['agent_runtime_profile'] = 'r42'
        self.assertIn('agent serve --runtime-profile r42', service_unit(config, 'robot', 'agent'))
        self.assertNotIn('--runtime-profile', service_unit(config, 'hub', 'hub'))
        config.data['deployment']['robot']['agent_runtime_profile'] = 'unknown'
        with self.assertRaises(ValueError):
            config.validate()
        with self.assertRaises(ValueError):
            service_unit(config, 'robot', 'agent')

    def test_profile_requires_explicit_continuous_capture_before_driver_import(self):
        config = self.config()
        config.data['conversation']['capture_pump_enabled'] = False
        with patch.dict('sys.modules', {'reachy_companion.r42.agent': None}):
            with self.assertRaisesRegex(ValueError, 'capture_pump_enabled'):
                r42.serve(config)

    def test_configured_cli_routes_profile_and_explicit_default_overrides(self):
        config = self.config()
        config.data['deployment']['robot']['agent_runtime_profile'] = 'r42'
        with patch('reachy_companion.config.Config', return_value=config), patch.object(r42, 'serve') as serve:
            with patch('sys.argv', ['companion', 'agent', 'serve']):
                cli.main()
            serve.assert_called_once_with(config, test_speaker=False)
        default = Mock()
        with patch('reachy_companion.config.Config', return_value=config), patch.dict('sys.modules', {'reachy_companion.agent': default}):
            with patch('sys.argv', ['companion', 'agent', 'serve', '--runtime-profile', 'default']):
                cli.main()
            default.main.assert_called_once_with(config, test_speaker=False)

    def test_explicit_config_reaches_frozen_control_client_and_environment_restored(self):
        config = self.config()
        with patch('reachy_companion.r42.initiative.control') as control:
            control.side_effect = lambda *a, **k: self.assertEqual(os.environ['REACHY_COMPANION_CONFIG'], str(config.filename))
            with patch.dict(os.environ, {'REACHY_COMPANION_CONFIG': 'previous.json'}):
                r42.control(config, 'auto-on')
                self.assertEqual(os.environ['REACHY_COMPANION_CONFIG'], 'previous.json')
            control.assert_called_once_with(True, schedule=True)

    def test_package_tamper_stops_before_driver_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'manifest.json').write_text(json.dumps({'files': {'agent.py': '0' * 64}}))
            (root / 'agent.py').write_text('raise AssertionError("must not import")')
            with patch.object(r42, '__file__', str(root / '__init__.py')):
                with self.assertRaisesRegex(ValueError, 'agent.py'):
                    r42.verify()
