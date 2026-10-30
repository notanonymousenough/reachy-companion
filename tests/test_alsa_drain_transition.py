from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from reachy_companion.autonomous.alsa_pcm import AlsaPCM


class DrainTransitionTests(unittest.TestCase):
    def backend(self,draining):
        backend=object.__new__(AlsaPCM)
        backend.lib=SimpleNamespace(snd_pcm_state=Mock(side_effect=[5,1]),snd_pcm_delay=Mock(return_value=-77))
        backend.handle=object();backend.draining=draining;backend.drained=False
        backend.written=100;backend.cursor=0
        return backend

    def test_nonblocking_drain_finishes_between_state_and_delay(self):
        backend=self.backend(True)
        self.assertEqual(backend.measured(),100)
        self.assertTrue(backend.drained)

    def test_setup_without_requested_drain_is_not_completion(self):
        backend=self.backend(False)
        with self.assertRaises(RuntimeError):backend.measured()
        self.assertFalse(backend.drained)
