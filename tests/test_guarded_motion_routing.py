"""The production hub boundary must never fall back around an opted-in actor."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from reachy_companion.config import Config, initialize
from reachy_companion.hub import Hub


class GuardedMotionRoutingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = Path(__file__).resolve().parents[1]
        shutil.copy(source/'config.example.json', root)
        shutil.copytree(source/'profiles', root/'profiles')
        initialize(root)
        self.config = Config(root/'config.local.json')
        self.config.data['guarded_motion']['enabled'] = True
        self.hub = Hub(self.config)
        self.hub.http = Mock()

    def test_all_mutations_use_actor_and_correlate_receipts(self):
        envelopes = []
        def actor(path, envelope):
            self.assertEqual(path, '/actors/motion/native')
            envelopes.append(envelope)
            return dict(command_id=envelope['command_id'], hub_boot_id=envelope['hub_boot_id'],
                        accepted=True, result={'uuid': 'move'})
        self.hub.agent = actor
        for path in ('/api/move/goto', '/api/move/stop', '/api/motors/set_mode/enabled',
                     '/api/move/play/wake_up', '/api/move/play/goto_sleep', '/api/unknown'):
            self.assertEqual(self.hub.robot(path, {}), {'uuid': 'move'})
        self.assertEqual(len({entry['command_id'] for entry in envelopes}), len(envelopes))
        self.assertTrue(all(entry['hub_boot_id'] == self.hub.boot_id for entry in envelopes))
        self.assertNotEqual(Hub(self.config).boot_id, self.hub.boot_id)
        self.hub.http.open.assert_not_called()

    def test_unavailable_rejected_stale_and_malformed_actor_never_fall_back(self):
        for response in (None, {}, {'accepted': True},
                         {'accepted': True, 'command_id': 'old', 'hub_boot_id': self.hub.boot_id, 'result': {}}):
            self.hub.agent = Mock(return_value=response)
            with self.assertRaises(RuntimeError): self.hub.robot('/api/move/goto', {})
        self.hub.agent = Mock(side_effect=TimeoutError('actor unavailable'))
        with self.assertRaises(TimeoutError): self.hub.robot('/api/motors/set_mode/enabled', {})
        self.hub.http.open.assert_not_called()

    def test_missing_flag_defaults_off_and_invalid_flags_fail_validation(self):
        data = json.loads(self.config.filename.read_text())
        del data['guarded_motion']
        self.config.filename.write_text(json.dumps(data))
        self.assertFalse(Config(self.config.filename)['guarded_motion']['enabled'])
        for value in ({'enabled': 1}, {'enabled': 'false'}, {'enabled': True, 'fallback': True}, None):
            data['guarded_motion'] = value
            self.config.filename.write_text(json.dumps(data))
            with self.assertRaises(ValueError): Config(self.config.filename)


if __name__ == '__main__': unittest.main()
