"""Offline producer/SDK boundary checks; no sockets, devices or audio backend."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from reachy_companion.autonomous.video_adapter import decode_packet

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('camera_coexist_producer',ROOT/'deploy/autonomous/video_server.py')
video=importlib.util.module_from_spec(spec);spec.loader.exec_module(video)


def operator():
    return dict(agent_boot_id='agent',microphone_epoch=213,microphone_owner_id=None,
        motion_policy_owner_id=None,microphone_enabled=True,capture_active=True,listening=True,
        microphone_state_error=None,phase='listening',
        motion_policy=dict(epoch=116,privacy_all=False,quiet=False,motor_enabled=False))


class CameraCoexistTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        root=Path(self.directory.name);(root/'token').write_text('x'*32)
        (root/'config.local.json').write_text(json.dumps(dict(paths=dict(token_file='token'),
            network=dict(agent_url='http://127.0.0.1:8090'))))
        self.policy=root/'policy';self.policy.write_text('{"camera_enabled":true,"privacy_all":false}')
        self.p=video.Producer(types.SimpleNamespace(production_root=root,policy_file=self.policy))
        self.scope=dict(hub_boot_id='hub',compute_boot_id='pc',operator_epoch=0)
        self.value=operator();self.requests=[]
        def read(request,timeout):
            self.requests.append((request.get_method(),request.selector))
            return io.BytesIO(json.dumps(self.value).encode())
        self.p.opener=types.SimpleNamespace(open=read)
        self.admit(0,'a')

    def admit(self,seq,admission,privacy=False):
        self.p.set_policy(dict(scope=self.scope,seq=seq,admission_id=admission,privacy_all=privacy))

    def sdk(self,on_sample,on_open=lambda:None):
        # Pixel transformation is covered separately. This fixture exercises the
        # real producer loop and supplies only the SDK interfaces it actually uses.
        sampled=types.SimpleNamespace(copy=lambda:types.SimpleNamespace(tobytes=lambda:b'\1\2\3'*(320*180)))
        class Frame:
            def reshape(self,*args):return self
            def __getitem__(self,key):return sampled
        camera=Mock()
        buffer=types.SimpleNamespace(pts=123,get_size=lambda:1280*720*3,
            extract_dup=lambda offset,size:b'\0'*size)
        sample=types.SimpleNamespace(get_buffer=lambda:buffer,
            get_segment=lambda:types.SimpleNamespace(to_running_time=lambda fmt,pts:456))
        def emit(*args):on_sample();return sample
        camera._appsink_video.emit.side_effect=emit
        camera.open.side_effect=on_open
        camera.pipeline.get_clock.return_value.get_time.return_value=1000
        camera.pipeline.get_base_time.return_value=100
        camera.pipeline.get_state.return_value.state='NULL'
        factory=Mock(return_value=camera)
        modules={'numpy':types.SimpleNamespace(frombuffer=lambda *args,**kw:Frame(),uint8=object()),
            'reachy_mini':types.ModuleType('reachy_mini'),
            'reachy_mini.media':types.ModuleType('reachy_mini.media'),
            'reachy_mini.media.camera_gstreamer':types.SimpleNamespace(GStreamerCamera=factory,
                Gst=types.SimpleNamespace(CLOCK_TIME_NONE=2**64-1,Format=types.SimpleNamespace(TIME='TIME'),
                    State=types.SimpleNamespace(NULL='NULL'))),
            'reachy_mini.media.camera_constants':types.SimpleNamespace(get_camera_specs_by_name=lambda name:'wireless')}
        return camera,factory,modules

    def run_capture(self,on_sample,on_open=lambda:None):
        camera,factory,modules=self.sdk(on_sample,on_open)
        waits=0
        def wait(timeout):
            nonlocal waits
            waits+=1
            if waits>=8:self.p.done.set()
        def path(value):
            return types.SimpleNamespace(read_text=lambda:'robot') if value=='/proc/sys/kernel/random/boot_id' else Path(value)
        with patch.dict(sys.modules,modules),patch('importlib.metadata.version',return_value='1.11.0'), \
                patch.object(video,'Path',side_effect=path),patch.object(self.p.done,'wait',side_effect=wait):
            self.p.capture()
        camera.close.assert_called_once()
        factory.assert_called_once_with(camera_specs='wireless')
        self.assertFalse(self.p.capture_lock.locked())
        self.assertIsNone(self.p.latest)
        return camera

    def test_mic_on_real_producer_loop_keeps_audio_state_and_single_reader_latest_only(self):
        original=copy.deepcopy(self.value);packets=[];actual=self.p.publish_frame
        def publish(*args):
            accepted=actual(*args);packets.append(self.p.packet())
            if len(packets)==3:self.p.done.set()
            return accepted
        def second_reader():
            with self.assertRaisesRegex(RuntimeError,'already active'):self.p.capture()
        with patch.object(self.p,'publish_frame',side_effect=publish):
            self.run_capture(lambda:None,second_reader)
        self.assertEqual(self.value,original)
        self.assertEqual(set(self.requests),{('GET','/operator')})
        decoded=[decode_packet(packet) for packet in packets]
        self.assertEqual([m['seq'] for m,_ in decoded],[0,1,2])
        self.assertEqual(len({m['frame_id'] for m,_ in decoded}),3)
        self.assertEqual(len({m['lineage_id'] for m,_ in decoded}),1)
        for metadata,raw in decoded:
            self.assertEqual(metadata['pts_ns'],123)
            self.assertEqual(metadata['buffer_running_time_ns'],456)
            self.assertFalse(metadata['source_capture_time_verified'])
            self.assertIsNone(metadata['source_age_upper_ms'])
            self.assertLessEqual(len(raw),1048576)
        self.assertNotIn('reachy_mini.media.audio_gstreamer',sys.modules)

    def test_privacy_remote_revoke_stop_epoch_or_local_opt_out_closes_and_drops_inflight(self):
        changes=(lambda:self.value['motion_policy'].update(privacy_all=True),
            lambda:self.admit(1,'b',privacy=True),
            lambda:self.value.update(microphone_epoch=214,microphone_enabled=False,listening=False,capture_active=False),
            lambda:self.policy.write_text('{"camera_enabled":false,"privacy_all":false}'),
            lambda:setattr(self.p,'policy_deadline',0))
        for change in changes:
            with self.subTest(change=change):
                self.value=operator();self.policy.write_text('{"camera_enabled":true,"privacy_all":false}')
                self.p.done.clear();self.admit(self.p.policy_seq+1,str(self.p.policy_seq+1))
                before=self.p.frames;calls=0
                def sample():
                    nonlocal calls
                    calls+=1;change()
                camera,factory,modules=self.sdk(sample)
                camera.close.side_effect=self.p.done.set
                with patch.dict(sys.modules,modules),patch('importlib.metadata.version',return_value='1.11.0'):
                    self.p.capture()
                camera.close.assert_called_once();factory.assert_called_once()
                self.assertEqual(calls,1);self.assertEqual(self.p.frames,before)
                self.assertIsNone(self.p.packet());self.assertIsNone(self.p.latest)

    def test_authority_change_is_fenced_until_new_admission_and_slow_reads_fail_closed(self):
        self.assertTrue(self.p.operator())
        self.value['microphone_epoch']+=1
        self.assertFalse(self.p.operator())
        self.value['microphone_epoch']-=1
        self.assertFalse(self.p.operator())  # Local ABA cannot resume old admission.
        self.admit(1,'b');self.assertTrue(self.p.operator())
        with patch.object(video.time,'monotonic',side_effect=[10,10.31]):
            self.assertFalse(self.p.operator())
        self.assertIsNone(self.p.packet())

    def test_remote_privacy_needs_new_admission_after_false_again(self):
        self.assertTrue(self.p.operator())
        self.admit(1,'a',privacy=True);self.admit(2,'a',privacy=False)
        self.assertFalse(self.p.operator())
        self.admit(3,'b');self.assertTrue(self.p.operator())
        with self.assertRaises(ValueError):self.admit(4,'a')

    def test_latest_slot_expires_and_receipt_does_not_certify_capture_time(self):
        with patch.object(video.time,'monotonic',return_value=10):
            self.admit(1,'b');self.assertTrue(self.p.operator())
            for seq in (1,2):
                self.assertTrue(self.p.publish_frame(dict(seq=seq),b'pixels',self.scope,self.p.generation,9.9))
            packet=self.p.packet();length=struct.unpack('!I',packet[:4])[0]
            metadata=json.loads(packet[4:4+length]);self.assertEqual(metadata['seq'],2)
            self.assertGreaterEqual(metadata['source_age_lower_ms'],99)
        with patch.object(video.time,'monotonic',return_value=10.31):
            self.assertIsNone(self.p.packet());self.assertIsNone(self.p.latest)
        with patch.object(video.time,'monotonic',return_value=11):
            self.assertTrue(self.p.operator())
            self.assertTrue(self.p.publish_frame({},b'old pixels',self.scope,self.p.generation,8))
            self.assertIsNone(self.p.packet());self.assertIsNone(self.p.latest)

    def test_unknown_reader_shutdown_is_terminal_and_does_not_reopen(self):
        camera,factory,modules=self.sdk(self.p.done.set)
        camera.pipeline.get_state.return_value.state='PLAYING'
        with patch.dict(sys.modules,modules),patch('importlib.metadata.version',return_value='1.11.0'), \
                self.assertRaisesRegex(RuntimeError,'shutdown unknown'):
            self.p.capture()
        self.assertTrue(self.p.reader_shutdown_unknown);self.assertTrue(self.p.done.is_set())
        self.assertFalse(self.p.capture_lock.locked());self.assertIsNone(self.p.latest)
        camera.close.assert_called_once();factory.assert_called_once()


if __name__=='__main__':unittest.main()
