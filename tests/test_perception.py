import hashlib
import unittest
from reachy_companion.autonomous.perception import pixel_metrics, shadow_event
from reachy_companion.autonomous.state import State


class PixelTests(unittest.TestCase):
    def metrics(self,payload):return pixel_metrics(payload,hashlib.sha256(payload).hexdigest())

    def test_pixel_measurements_and_channel_order(self):
        result=self.metrics(b'P6\n2 1\n255\n'+bytes([255,0,0,0,255,0]))
        self.assertEqual(result['mean_rgb'],[127.5,127.5,0])
        self.assertEqual(result['mean_luminance'],round((255*54+255*183)/512,3))
        self.assertFalse(result['semantic_scene_inferred'])

    def test_provenance_and_size_rejections(self):
        with self.assertRaises(ValueError):pixel_metrics(b'P6\n1 1\n255\n\0\0\0','wrong')
        for payload in (b'P6\n1 1\n255\n\0',b'P6\n0 1\n255\n',b'P6\n641 1\n255\n',
                        b'P6\n1 1\n256\n\0\0\0',b'x'*1048577):
            with self.assertRaises(ValueError):self.metrics(payload)

    def test_capture_time_unknown_cannot_be_fresh_sensor_evidence(self):
        result=self.metrics(b'P6\n1 1\n255\n\0\0\0')
        state=State();state.ingest(shadow_event(result),0)
        sensor=state.snapshot(.1)['sensors'][0]
        self.assertEqual(sensor['state'],'unknown')
        self.assertIsNone(sensor['age_ms'])
        self.assertEqual(sensor['summary'],'')


if __name__=='__main__':unittest.main()
