"""Finite snapshot/native FINAL checks. No camera, model or device is accessed."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import sys
import types
import zlib
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('demo_vision_fixture',ROOT/'deploy/autonomous/demo_vision.py')
vision=importlib.util.module_from_spec(spec);spec.loader.exec_module(vision)


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.model=dict(key='configured-key',capabilities=dict(vision=True,reasoning=dict(allowed_options=[])),
            loaded_instances=[dict(id='existing-instance')])
        self.reply=dict(model_instance_id='existing-instance',stats=dict(model_load_time_seconds=0),
            output=[dict(type='reasoning',content='PRIVATE REASONING'),dict(type='message',content='Описание кадра.')])

    def test_native_exact_loaded_selection_and_message_only_final_no_reasoning_or_tools(self):
        model,instance=vision.select_model(dict(models=[self.model]),'configured-key')
        self.assertEqual(instance,'existing-instance')
        self.assertEqual(vision.final_message(self.reply,instance),'Описание кадра.')
        for change in (dict(output=[dict(type='reasoning',content='PRIVATE')]),
                dict(output=[dict(type='message',content='<think>PRIVATE')]),
                dict(output=[dict(type='message',content='safe'),dict(type='tool_call',name='private')]),
                dict(model_instance_id='changed'),dict(response_id=None),dict(stats=dict(model_load_time_seconds=1))):
            with self.subTest(change=change),self.assertRaises(ValueError):
                vision.final_message(dict(self.reply,**change),instance)
        for rows in ([],[self.model,self.model],[dict(self.model,loaded_instances=[])],
                [dict(self.model,capabilities=dict(vision=False))]):
            with self.assertRaises(ValueError):vision.select_model(dict(models=rows),'configured-key')

    def test_native_endpoint_is_local_and_configured_path_only(self):
        cfg=dict(network=dict(llm_base_url='http://local-pc:1234/v1'))
        with patch.object(vision.socket,'getaddrinfo',return_value=[(None,None,None,None,('192.168.1.2',1234))]):
            self.assertEqual(vision.native_address(cfg),('192.168.1.2',1234))
        with patch.object(vision.socket,'getaddrinfo',return_value=[(None,None,None,None,('8.8.8.8',1234))]):
            with self.assertRaises(ValueError):vision.native_address(cfg)

    def test_camera_child_cannot_outlive_its_parent_or_arm_after_reparenting(self):
        libc=SimpleNamespace(prctl=Mock(return_value=0))
        with patch.object(vision.ctypes,'CDLL',return_value=libc),patch.object(vision.os,'getppid',side_effect=[7,7]):
            vision.bind_parent_lifetime()
        libc.prctl.assert_called_once_with(1,vision.signal.SIGTERM,0,0,0)
        with patch.object(vision.ctypes,'CDLL',return_value=libc),patch.object(vision.os,'getppid',side_effect=[7,1]):
            with self.assertRaises(ValueError):vision.bind_parent_lifetime()

    def caption(self,*,stale=False,changed=False,timeout=False):
        clock=[100.0];self.sent=[];self.posts=0
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            plan=dict(run=str(run),boot='boot',mic_epoch=4,policy_epoch=8,deadline=300)
            value=dict(agent_boot_id='boot',microphone_epoch=4,microphone_owner_id=None,motion_policy_owner_id=None,
                microphone_enabled=False,capture_active=False,listening=False,phase='paused',
                motion_policy=dict(epoch=8,motor_enabled=False,quiet=False,privacy_all=False))
            io=Mock();io.operator_begin_by_thread={}
            io.req.return_value=dict(bound_snapshot_say=1,agent_boot_id='boot')
            def operator():
                io.operator_begin_by_thread[threading.get_ident()]=clock[0]
                current=copy.deepcopy(value)
                if changed and clock[0]>100:current['microphone_epoch']+=1
                return current
            io.op.side_effect=operator
            config=dict(network=dict(llm_base_url='http://local-pc:1234/v1'),llm=dict(model='configured-key'))
            def raw(path):
                return json.dumps(dict(pid=7,identity=dict(pid=7)) if path.name=='watch-ready.json' else config).encode()
            m=SimpleNamespace(ROOT=run,AGENT=('127.0.0.1',8090),raw=raw,state_unit=lambda _:dict(ActiveState='active',MainPID='7'),proc=lambda pid:dict(pid=pid))
            def connect(connection):
                def send(data):self.sent.append(bytes(data));return len(data)
                connection.sock=SimpleNamespace(send=send,settimeout=lambda _:None,close=lambda:None)
            def response(connection):
                self.posts+=1
                if timeout:raise TimeoutError('PRIVATE upstream body')
                clock[0]+=14
                return SimpleNamespace(status=200,read=lambda _:json.dumps(self.reply).encode())
            with patch.object(vision,'native_address',return_value=('127.0.0.1',1234)), \
                    patch.object(vision,'get_models',return_value=dict(models=[self.model])), \
                    patch.object(vision,'capture_png',return_value=(b'PRIVATE PIXELS',97 if stale else 100)), \
                    patch.object(vision.time,'monotonic',side_effect=lambda:clock[0]), \
                    patch('http.client.HTTPConnection.connect',connect),patch('http.client.HTTPConnection.getresponse',response):
                return vision.caption(m,io,plan,'Что перед тобой?')

    def test_exact_tested_native_input_privacy_flags_and_no_scene_export_in_metadata(self):
        result=self.caption()
        self.assertEqual(self.posts,1)
        raw=b''.join(self.sent);body=json.loads(raw.split(b'\r\n\r\n',1)[1])
        self.assertEqual(body['model'],'existing-instance');self.assertIs(body['store'],False)
        self.assertEqual(body['integrations'],[]);self.assertIs(body['stream'],False)
        self.assertEqual(body['max_output_tokens'],2048);self.assertNotIn('reasoning',body)
        self.assertEqual([item['type'] for item in body['input']],['text','image'])
        self.assertTrue(body['input'][1]['data_url'].startswith('data:image/png;base64,'))
        self.assertEqual(result['final_text'],'Описание кадра.')
        self.assertEqual(result['expires_at_monotonic'],160)
        self.assertNotIn('PRIVATE',json.dumps(result['frame']))
        self.assertFalse(result['frame']['source_capture_time_verified'])
        self.assertFalse(result['frame']['semantic_accuracy_verified'])

    def test_reasoning_off_is_sent_only_when_actually_allowed(self):
        self.model['capabilities']['reasoning']['allowed_options']=['off']
        self.caption()
        body=json.loads(b''.join(self.sent).split(b'\r\n\r\n',1)[1])
        self.assertEqual(body['reasoning'],'off')

    def test_camera_reader_closes_before_return_and_encodes_only_rgb_snapshot_ram(self):
        try:import numpy
        except ImportError:self.skipTest('Optional camera numpy runtime absent; no install')
        camera=Mock();camera.pipeline.get_state.return_value.state='NULL'
        sample=Mock();sample.get_buffer.return_value.get_size.return_value=1280*720*3
        sample.get_buffer.return_value.extract_dup.return_value=b'\1\2\3'*(1280*720)
        sample.get_caps.return_value.get_structure.return_value.get_value.side_effect=lambda key:{'width':1280,'height':720,'format':'BGR'}[key]
        camera._appsink_video.emit.return_value=sample
        modules={'reachy_mini':types.ModuleType('reachy_mini'),'reachy_mini.media':types.ModuleType('reachy_mini.media'),
            'reachy_mini.media.camera_gstreamer':SimpleNamespace(GStreamerCamera=Mock(return_value=camera),Gst=SimpleNamespace(State=SimpleNamespace(NULL='NULL'))),
            'reachy_mini.media.camera_constants':SimpleNamespace(get_camera_specs_by_name=lambda _:object())}
        with patch.dict(sys.modules,modules),patch.object(vision.importlib.metadata,'version',return_value='1.11.0'):
            png,_=vision.capture_png()
        camera.close.assert_called_once();self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
        offset=8;scan=b''
        while offset<len(png):
            length=int.from_bytes(png[offset:offset+4],'big');kind=png[offset+4:offset+8]
            if kind==b'IDAT':scan+=png[offset+8:offset+8+length]
            offset+=length+12
        self.assertEqual(zlib.decompress(scan)[:4],b'\0\3\2\1')

    def test_expired_frame_never_posts_changed_epoch_discards_final_and_timeout_never_retries(self):
        with self.assertRaises(ValueError):self.caption(stale=True)
        self.assertEqual(self.sent,[]);self.assertEqual(self.posts,0)
        with self.assertRaises(ValueError):self.caption(changed=True)
        self.assertEqual(self.posts,1)
        with self.assertRaises(TimeoutError):self.caption(timeout=True)
        self.assertEqual(self.posts,1)


if __name__=='__main__':unittest.main()
