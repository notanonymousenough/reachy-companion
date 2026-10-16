"""Exact helper capture failure stages with stub camera; no device/model access."""
import ast
import hashlib
import builtins
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import types
import unittest
from unittest.mock import Mock, patch
from test_demo_vision import vision, ROOT
from reachy_companion import spoken_vision as spoken
try:
    import numpy
except ImportError:
    numpy=None


@unittest.skipIf(numpy is None, "Optional camera numpy runtime absent; no install")
class CapturePhaseTests(unittest.TestCase):
    def setUp(self):
        self.camera=Mock();self.camera.pipeline.get_state.return_value.state='NULL'
        self.sample=Mock();buffer=self.sample.get_buffer.return_value
        buffer.get_size.return_value=1280*720*3
        buffer.extract_dup.return_value=b'\1\2\3'*(1280*720)
        self.sample.get_caps.return_value.get_structure.return_value.get_value.side_effect=lambda key:{'width':1280,'height':720,'format':'BGR'}[key]
        self.camera._appsink_video.emit.return_value=self.sample
        self.constructor=Mock(return_value=self.camera);self.specs=Mock(return_value=object())
        self.modules={'reachy_mini':types.ModuleType('reachy_mini'),'reachy_mini.media':types.ModuleType('reachy_mini.media'),
            'reachy_mini.media.camera_gstreamer':SimpleNamespace(GStreamerCamera=self.constructor,Gst=SimpleNamespace(State=SimpleNamespace(NULL='NULL'))),
            'reachy_mini.media.camera_constants':SimpleNamespace(get_camera_specs_by_name=self.specs)}

    def capture(self, version='1.11.0'):
        with patch.dict(sys.modules,self.modules),patch.object(vision.importlib.metadata,'version',return_value=version):
            return vision.capture_png()

    def failure(self, phase, version='1.11.0', error=ValueError):
        with self.assertRaises(error):self.capture(version)
        self.assertEqual(vision.PHASE,phase)
        with patch.object(spoken,'PHASE','snapshot'),patch.object(spoken,'SNAPSHOT',vision):
            diagnostic=spoken.failure(error('PRIVATE text image token'))
        self.assertEqual(diagnostic,dict(kind='companion-spoken-vision-error',phase=phase,error_class=error.__name__))
        self.assertNotIn('PRIVATE',json.dumps(diagnostic))
        with self.assertRaisesRegex(RuntimeError,'^Spoken snapshot child failed phase='+phase+' error_class='+error.__name__+'$'):
            spoken.child_result(json.dumps(diagnostic).encode(),1)

    def test_import_value_error_has_fixed_import_stage_without_guessing_sdk_cause(self):
        original=builtins.__import__
        def importing(name,*args,**kwargs):
            if name=='reachy_mini.media.camera_gstreamer':raise ValueError('PRIVATE gi detail')
            return original(name,*args,**kwargs)
        with patch.object(builtins,'__import__',side_effect=importing):self.failure('capture_import')
        self.constructor.assert_not_called()

    def test_real_child_protocol_and_installed_agent_observer_accept_new_fixed_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'spoken_vision.py').write_bytes((ROOT/'src/reachy_companion/spoken_vision.py').read_bytes())
            (root/'snapshot_vision.py').write_text("PHASE='startup'\ndef bind_parent_lifetime():pass\n"
                "def caption_checked(*args):\n global PHASE\n PHASE='capture_caps'\n raise ValueError('PRIVATE')\n")
            packet=dict(config={},port=8090,token='x'*32,deadline=spoken.time.monotonic()+45,expected={},question='Что перед тобой?')
            result=subprocess.run([sys.executable,str(root/'spoken_vision.py'),'--snapshot-child'],
                input=json.dumps(packet).encode(),capture_output=True,timeout=5)
            self.assertEqual(result.returncode,1);self.assertEqual(result.stderr,b'')
            expected=dict(kind='companion-spoken-vision-error',phase='capture_caps',error_class='ValueError')
            self.assertEqual(json.loads(result.stdout),expected)
            with self.assertRaises(RuntimeError) as caught:spoken.child_result(result.stdout,1)
            from test_agent_vision_route_observation import candidate
            from test_agent_live_latency_patch import load
            module=load(candidate()[1]);agent=module.Agent.__new__(module.Agent)
            agent._vision_route=({},dict(route_attempted=True,child_phase=None,child_error_class=None))
            agent.vision_route_failure(caught.exception)
            self.assertEqual(agent._vision_route[1]['child_phase'],'capture_caps')
            self.assertEqual(agent._vision_route[1]['result'],'typed_child_failure')
            self.assertNotIn('PRIVATE',json.dumps(agent._vision_route[1]))

    def test_version_and_audio_import_guards_remain_distinct_and_construct_no_camera(self):
        self.failure('capture_sdk_version',version='1.10.0');self.constructor.assert_not_called()
        self.modules['reachy_mini.media.audio_gstreamer']=object()
        self.failure('capture_no_audio');self.constructor.assert_not_called()

    def test_sdk_value_errors_identify_specs_constructor_open_and_close(self):
        for source,phase in ((self.specs,'capture_specs'),(self.constructor,'capture_construct'),
                (self.camera.open,'capture_open'),(self.camera.close,'capture_close')):
            with self.subTest(phase=phase):
                source.side_effect=ValueError('PRIVATE SDK message')
                self.failure(phase)
                source.side_effect=None

    def test_missing_sample_does_not_extend_two_second_budget_and_closes(self):
        self.camera._appsink_video.emit.return_value=None
        with patch.object(vision.time,'monotonic',side_effect=[100,100,103]):self.failure('capture_sample')
        self.camera._appsink_video.emit.assert_called_once_with('try-pull-sample',100_000_000)
        self.camera.close.assert_called_once()

    def test_caps_buffer_extract_and_numpy_shape_are_distinct(self):
        caps=self.sample.get_caps.return_value.get_structure.return_value
        caps.get_value.side_effect=lambda key:{'width':640,'height':720,'format':'BGR'}[key]
        self.failure('capture_caps')
        caps.get_value.side_effect=lambda key:{'width':1280,'height':720,'format':'BGR'}[key]
        buffer=self.sample.get_buffer.return_value
        buffer.get_size.return_value=7;self.failure('capture_buffer')
        buffer.get_size.return_value=1280*720*3
        buffer.extract_dup.side_effect=ValueError('PRIVATE');self.failure('capture_extract')
        buffer.extract_dup.side_effect=None;buffer.extract_dup.return_value=b'short'
        self.failure('capture_pixels')

    def test_encode_png_bound_and_non_null_cleanup_are_distinct(self):
        with patch.object(vision.zlib,'compress',side_effect=ValueError('PRIVATE')):self.failure('capture_encode')
        with patch.object(vision.zlib,'compress',return_value=b'x'*1048577):self.failure('capture_png_bound')
        self.camera.pipeline.get_state.return_value.state='PLAYING';self.failure('capture_closed')
        self.camera.close.assert_called()

    def test_primary_capture_phase_and_class_survive_a_second_cleanup_failure(self):
        self.camera._appsink_video.emit.side_effect=ValueError('PRIVATE FIRST')
        self.camera.close.side_effect=RuntimeError('PRIVATE SECOND')
        self.failure('capture_sample')
        self.camera.close.assert_called_once()
        self.camera.pipeline.get_state.assert_not_called()

    def test_cleanup_only_error_keeps_its_own_phase_and_class(self):
        self.camera.close.side_effect=RuntimeError('PRIVATE')
        self.failure('capture_close',error=RuntimeError)

    def test_success_still_returns_png_and_original_phase_after_null_cleanup(self):
        png,when=self.capture()
        self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'));self.assertIsInstance(when,float)
        self.assertEqual(vision.PHASE,'capture');self.camera.close.assert_called_once()
        self.camera.pipeline.get_state.assert_called_once_with(1_000_000_000)

    def test_only_capture_function_and_parent_phase_allowlist_change_from_exact_installed_pins(self):
        for path,sha,skip in (
                ('deploy/autonomous/demo_vision.py','1bd06dec8f941a78f0519e090e3a54cbc5816f5485fbb83ddd348e1830d0ef3f','capture_png'),
                ('src/reachy_companion/spoken_vision.py','242ac03560af18c042ddef39fa2eb0eb343aa4c9dcb13e99a31e5eda3c134c69','ERROR_PHASES')):
            old=subprocess.check_output(['git','show','e86e54bd4d55f2cf4382e8ef5c5529e8d389d6e4:'+path],cwd=ROOT)
            self.assertEqual(hashlib.sha256(old).hexdigest(),sha)
            def outside(source):
                tree=ast.parse(source)
                tree.body=[n for n in tree.body if getattr(n,'name',None)!=skip and not
                    (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==skip for t in n.targets))]
                return ast.dump(tree,include_attributes=False)
            self.assertEqual(outside(old),outside((ROOT/path).read_bytes()))
        capture=next(n for n in ast.parse((ROOT/'deploy/autonomous/demo_vision.py').read_text()).body if getattr(n,'name',None)=='capture_png')
        phases={n.value for n in ast.walk(capture)
                if isinstance(n,ast.Constant) and type(n.value) is str and n.value.startswith('capture_')}
        self.assertTrue(phases<=spoken.ERROR_PHASES)
        for unknown in ('capture_PRIVATE','PRIVATE',None):
            with patch.object(spoken,'PHASE','snapshot'),patch.object(spoken,'SNAPSHOT',SimpleNamespace(PHASE=unknown)):
                self.assertEqual(spoken.failure(ValueError('PRIVATE'))['phase'],'startup')


if __name__=='__main__':unittest.main()
