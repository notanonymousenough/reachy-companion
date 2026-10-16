"""Audio-only carrier checks; no device, HTTP or acoustic acceptance."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import reachy_companion.client as client
from test_demo import DemoTests

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audio_builder', ROOT/'deploy/autonomous/prepare_audio_only_demo.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class AudioOnlyTests(unittest.TestCase):
    def setUp(self):
        self.original = (ROOT/'src/reachy_companion/client.py').read_bytes()
        exec(compile(builder.candidate(self.original), '<audio-only>', 'exec'), client.__dict__)
        self.addCleanup(lambda: exec(compile(self.original, '<original>', 'exec'), client.__dict__))
        self.fixture = DemoTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def run_audio(self, read=None, clock=None):
        with patch.object(client, 'request', side_effect=read or self.fixture.request), \
             patch.object(client.time, 'sleep'), patch('builtins.print') as output:
            result = client.demo({'network': {'hub_url': 'http://fixture'}}, turns=1, seconds=180)
        return result, output

    def test_disabled_policy_claim_and_mic_cleanup_never_enable_motors(self):
        result, output = self.run_audio()
        self.assertEqual(result, 0)
        self.assertEqual([p for p,_ in self.fixture.posts], ['/control/motion-policy', '/control/microphone', '/control/microphone', '/control/motion-policy'])
        self.assertEqual(self.fixture.operator['motion_policy']['epoch'], 10)
        self.assertFalse(self.fixture.operator['motion_policy']['motor_enabled'])
        self.assertIsNone(self.fixture.operator['motion_policy_owner_id'])
        self.assertFalse(self.fixture.operator['microphone_enabled'])
        self.assertTrue(all(payload.get('motor_enabled') is not True for _,payload in self.fixture.posts))
        self.assertIn('AUDIO_ONLY_LISTENING', str(output.call_args_list))

    def test_motor_on_preflight_denied_without_grants(self):
        self.fixture.operator['motion_policy']['motor_enabled'] = True
        self.assertEqual(self.run_audio()[0], 1)
        self.assertEqual(self.fixture.posts, [])

    def test_changed_policy_after_mic_grant_cancels_and_only_cleans_own_mic(self):
        def read(config, url, payload=None, **kw):
            value = self.fixture.request(config, url, payload, **kw)
            if payload and payload.get('enabled') is True:
                self.fixture.operator['motion_policy']['epoch'] += 1
            return value
        result, output = self.run_audio(read)
        self.assertEqual(result, 1)
        self.assertNotIn('AUDIO_ONLY_LISTENING', str(output.call_args_list))
        self.assertEqual([p for p,_ in self.fixture.posts], ['/control/motion-policy', '/control/microphone', '/control/microphone'])

    def test_full_window_starts_at_capture_not_grant(self):
        now = [0.0]
        def read(config, url, payload=None, **kw):
            value = self.fixture.request(config, url, payload, **kw)
            if payload and payload.get('enabled') is True:
                self.fixture.operator.update(capture_active=False, listening=False)
            if url.endswith('/control/status') and self.fixture.operator['microphone_enabled']:
                now[0] += 10
                if now[0] >= 30:
                    self.fixture.operator.update(capture_active=True, listening=True)
            return value
        with patch.object(client.time, 'monotonic', side_effect=lambda: now[0]):
            result, output = self.run_audio(read)
        self.assertEqual(result, 0)
        self.assertIn('window_seconds=90', str(output.call_args_list))
        self.assertGreaterEqual(now[0], 30)

    def test_late_capture_never_announces_shortened_window(self):
        now = [0.0]
        def read(config, url, payload=None, **kw):
            value = self.fixture.request(config, url, payload, **kw)
            if payload and payload.get('enabled') is True: now[0] = 100
            return value
        with patch.object(client.time, 'monotonic', side_effect=lambda: now[0]):
            result, output = self.run_audio(read)
        self.assertEqual(result, 1)
        self.assertNotIn('AUDIO_ONLY_LISTENING', str(output.call_args_list))
        self.assertFalse(self.fixture.operator['microphone_enabled'])

    def test_wrong_preimage_rejected(self):
        with self.assertRaises(ValueError): builder.candidate(self.original+b'\n')

    def test_unsupported_modes_denied_before_io(self):
        for kw in ({'seconds':75}, {'turns':2}, {'prime_paused':True}):
            args = dict(seconds=180, turns=1); args.update(kw)
            with patch.object(client, 'request') as io, self.assertRaises(ValueError):
                client.demo({}, **args)
            io.assert_not_called()

    def test_lost_applied_mic_grant_still_cleans_both_claims(self):
        self.fixture.fail_after_microphone = True
        result, output = self.run_audio()
        self.assertEqual(result, 1)
        self.assertFalse(self.fixture.operator['microphone_enabled'])
        self.assertIsNone(self.fixture.operator['motion_policy_owner_id'])
        self.assertNotIn('AUDIO_ONLY_LISTENING', str(output.call_args_list))

    def test_foreign_owner_is_preserved_on_stop(self):
        self.fixture.foreign = True
        self.assertEqual(self.run_audio()[0], 1)
        self.assertEqual(self.fixture.operator['microphone_owner_id'], 'human')
        self.assertEqual(self.fixture.operator['motion_policy_owner_id'], 'human')


if __name__ == '__main__': unittest.main()
