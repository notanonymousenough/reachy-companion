import unittest

from reachy_companion.autonomous.response_endpoint import ResponseEndpoint


class MarkerVad:
    def is_speech(self, frame, rate):
        assert len(frame) == 640 and rate == 16000
        return frame[0] == 1


class ResponseEndpointTests(unittest.TestCase):
    def test_fragmented_utterance_stops_before_later_noise(self):
        endpoint = ResponseEndpoint(MarkerVad())
        audio = b'\0' * 640 * 10 + b'\1' * 640 * 20 + b'\0' * 640 * 30 + b'\1' * 640 * 20
        for offset in range(0, len(audio), 222):
            endpoint.feed(audio[offset:offset + 222])
        self.assertEqual(endpoint.reason, 'speech_then_silence')
        self.assertEqual(endpoint.frames, 60)
        self.assertEqual(len(endpoint.pcm), 60 * 640)
        self.assertFalse(endpoint.receipt()['trusted_resume_window'])
        endpoint.clear()
        self.assertFalse(endpoint.pcm)

    def test_short_noise_never_establishes_speech(self):
        endpoint = ResponseEndpoint(MarkerVad(), max_seconds=1)
        endpoint.feed(b'\1' * 640 * 4 + b'\0' * 640 * 46)
        self.assertEqual(endpoint.reason, 'response_deadline')
        self.assertFalse(endpoint.started)

    def test_continuous_speech_has_hard_bound(self):
        endpoint = ResponseEndpoint(MarkerVad(), max_seconds=1)
        endpoint.feed(b'\1' * 640 * 50)
        self.assertEqual(endpoint.reason, 'response_deadline')
        endpoint.feed(b'\1' * 640 * 50)
        self.assertEqual(endpoint.frames, 50)

    def test_invalid_input_does_not_enter_buffer(self):
        endpoint = ResponseEndpoint(MarkerVad())
        for data in (b'\1', b'\0' * (640 * 401)):
            with self.assertRaises(ValueError):
                endpoint.feed(data)
        self.assertFalse(endpoint.pending)


if __name__ == '__main__':
    unittest.main()
