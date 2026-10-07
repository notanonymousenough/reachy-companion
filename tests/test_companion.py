import copy
import json
import shutil
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from reachy_companion.config import Config, initialize
from reachy_companion.firewall import render, unit
from reachy_companion.deployment import ssh_args
from reachy_companion.client import control

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = json.loads((ROOT / 'config.example.json').read_text())
        self.data['security']['robot']['hub_source_ipv4'] = '192.0.2.10'
        (self.root / 'config.example.json').write_text(json.dumps(self.data))
        shutil.copytree(ROOT / "profiles", self.root / "profiles")
        initialize(self.root)
        self.config = Config(self.root / 'config.local.json')

    def test_profile_changes_voice_without_overwriting_local_network_or_token(self):
        token = self.config.token
        profile = self.root / 'profiles/friend.json'
        data = json.loads(profile.read_text())
        data['tts']['pitch_cents'] = 175
        profile.write_text(json.dumps(data))
        configured = Config(self.config.filename)
        self.assertEqual(configured['tts']['pitch_cents'], 175)
        self.assertEqual(configured['security']['robot']['hub_source_ipv4'], '192.0.2.10')
        self.assertEqual(configured.token, token)
        data['network'] = {'hub_url': 'http://wrong-host:1'}
        profile.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            Config(self.config.filename)

    def test_update_preserves_firewall_and_skips_unchanged_dependencies(self):
        from reachy_companion.deployment import update
        import hashlib
        self.config.data['deployment']['robot']['root'] = str(self.root)
        venv = self.root / self.config['deployment']['robot']['venv_dir'] / 'bin'
        venv.mkdir(parents=True)
        (venv / 'python').touch()
        locks = self.root / 'requirements'
        locks.mkdir()
        (locks / 'robot.lock').write_text('webrtcvad-wheels==2.0.14.post1\n')
        with patch('reachy_companion.deployment.os.geteuid', return_value=0), \
             patch('reachy_companion.deployment.subprocess.run') as run, \
             patch('pathlib.Path.write_text'):
            update(self.config, 'robot')
        commands = [call.args[0] for call in run.call_args_list]
        self.assertFalse(any('apt-get' in c or 'nft' in c for c in commands))
        self.assertIn(['systemctl', 'restart', 'reachy-voice-agent'], commands)
        data = self.config.path(self.config['paths']['data_dir'])
        marker = data / 'robot-dependencies.sha256'
        marker.write_text(hashlib.sha256((locks / 'robot.lock').read_bytes()).hexdigest())
        with patch('reachy_companion.deployment.os.geteuid', return_value=0), \
             patch('reachy_companion.deployment.subprocess.run') as run, \
             patch('pathlib.Path.write_text'):
            update(self.config, 'robot')
        self.assertFalse(any('pip' in ' '.join(call.args[0]) for call in run.call_args_list))

    def test_secret_and_config_are_private_and_not_overwritten(self):
        token = self.config.token
        self.assertGreaterEqual(len(token), 32)
        self.assertEqual((self.root / 'secrets/token').stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            initialize(self.root)
        self.assertEqual(Config(self.config.filename).token, token)
        self.assertNotIn(token, self.config.filename.read_text())

    def test_firewall_blocks_ipv6_application_bypass_and_preserves_other_tables(self):
        rules = render(self.config)
        self.assertIn('ip saddr 192.0.2.10 accept', rules)
        self.assertIn('policy drop', rules)
        self.assertNotIn('flush ruleset', rules)
        self.assertNotIn('tcp dport', rules)
        self.assertNotIn('ip6 saddr', rules)
        self.assertIn('Before=network-pre.target', unit(self.config))
        self.config.data['security']['robot']['hub_source_ipv4'] = '192.0.2.10; accept'
        with self.assertRaises(ValueError):
            render(self.config)

    def test_robot_ssh_always_uses_hub(self):
        args = ssh_args(self.config, 'robot')
        self.assertIn('-J', args)
        self.assertEqual(args[args.index('-J') + 1], 'deploy@reachy-hub.lan')

    def test_operator_speech_routes_via_hub(self):
        with patch('reachy_companion.client.request', return_value={'ok': True}) as request:
            control(self.config, 'voice', 'ask', 'привет')
        self.assertEqual(request.call_args.args[1], self.config['network']['voice_url'] + '/robot/ask')

    def test_invalid_audio_protocol_is_rejected(self):
        self.config.data['audio']['sample_rate'] = 48000
        with self.assertRaises(ValueError):
            self.config.validate()

    def test_failed_answer_does_not_update_history(self):
        piper = types.ModuleType('piper')
        piper.PiperVoice = piper.SynthesisConfig = object
        vosk = types.ModuleType('vosk')
        vosk.Model = vosk.KaldiRecognizer = vosk.SetLogLevel = object
        with patch.dict(sys.modules, {'piper': piper, 'vosk': vosk}):
            from reachy_companion.voice import Pipeline
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.config = self.config
        pipeline.sessions = {}
        pipeline.agent_sessions = {}
        with patch('reachy_companion.brains.answer', return_value='Привет!'):
            reply, pending = pipeline.answer('Привет', 'test')
        self.assertEqual(reply, 'Привет!')
        self.assertEqual(pipeline.sessions, {})
        self.assertEqual(len(pending['messages']), 2)
        with patch('reachy_companion.brains.answer', side_effect=RuntimeError('unfinished')):
            with self.assertRaises(RuntimeError):
                pipeline.answer('Привет', 'test')
        self.assertEqual(pipeline.sessions, {})
        pipeline.agent_sessions['test'] = 'previous'
        pipeline.reset('test')
        self.assertNotIn('test', pipeline.agent_sessions)


if __name__ == '__main__':
    unittest.main()
