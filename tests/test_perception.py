import hashlib
import unittest
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
from urllib.error import URLError
from unittest.mock import patch
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

    def test_camera_outer_cleanup_on_status_and_output_failures(self):
        source=Path(__file__).resolve().parents[1]/'deploy/autonomous/camera_probe.py'
        spec=importlib.util.spec_from_file_location('camera_probe_cleanup',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            frame=Path(directory)/'private.ppm';args=SimpleNamespace(frame=frame)
            for failure in (URLError('operator status unavailable'),OSError('output open failed')):
                def operation(args):
                    args.frame.write_bytes(b'private fixture pixels')
                    raise failure
                with self.assertRaises(type(failure)):module.owned_frame(args,operation)
                self.assertFalse(frame.exists())
            frame.write_bytes(b'preexisting user artifact')
            with self.assertRaises(FileExistsError):module.owned_frame(args,lambda _:None)
            self.assertEqual(frame.read_bytes(),b'preexisting user artifact')

    def test_stream_policy_clears_raw_and_fences_old_owner_epoch_and_sequence(self):
        source=Path(__file__).resolve().parents[1]/'deploy/autonomous/video_server.py'
        spec=importlib.util.spec_from_file_location('video_policy',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'token').write_text('x'*32)
            (root/'config.local.json').write_text('{"paths":{"token_file":"token"},"network":{"agent_url":"http://127.0.0.1:8770"}}')
            policy=root/'policy.json';policy.write_text('{"camera_enabled":true,"privacy_all":false}')
            producer=module.Producer(SimpleNamespace(production_root=root,policy_file=policy))
            identities=[producer.source_ids() for _ in range(3)]
            self.assertEqual(len({x['frame_id'] for x in identities}),3)
            self.assertEqual(len({x['lineage_id'] for x in identities}),1)
            self.assertTrue(all(x['independent_episode_verified'] is False for x in identities))
            scope=dict(hub_boot_id='hub',compute_boot_id='pc',operator_epoch=0)
            message=dict(scope=scope,privacy_all=False,seq=0)
            self.assertIsNone(producer.packet())
            with patch.object(module.time,'monotonic',return_value=10):
                producer.set_policy(message)
                producer.latest=({},b'fixture pixels')
                self.assertIsNotNone(producer.packet())
                with self.assertRaises(ValueError):producer.set_policy(message)
                producer.set_policy({**message,'scope':{**scope,'operator_epoch':1},'privacy_all':True,'seq':1})
                self.assertIsNone(producer.latest);self.assertIsNone(producer.packet())
                with self.assertRaises(ValueError):producer.set_policy({**message,'seq':2})
                producer.set_policy({**message,'scope':{**scope,'hub_boot_id':'new'},'seq':0})
                self.assertEqual(producer.source_ids()['lineage_id'],identities[0]['lineage_id'])
                with self.assertRaises(ValueError):producer.set_policy({**message,'seq':99})
            with patch.object(module.time,'monotonic',return_value=12):self.assertIsNone(producer.packet())


if __name__=='__main__':unittest.main()
