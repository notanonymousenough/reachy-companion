"""Fresh-process wiring traces with fake factory modules; no native loading/UART."""
import hashlib
from pathlib import Path
import sys
import tempfile
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import patch
from reachy_companion.autonomous import factory_head_process as process
from reachy_companion.autonomous.factory_head_adapter import NATIVE_METHODS

class Native:
    pass
for method in NATIVE_METHODS:setattr(Native,method,lambda *args:None)
# The actual Robot module must import this exact native class.
ReachyMiniPyControlLoop=Native

class ProcessTests(unittest.TestCase):
    def setup_factory(self):
        class Abstract:
            def process_command(self,*args,**kw):pass
            def _handle_webrtc_message(self,*args):pass
            def request_idle_reset(self,*args):pass
            def cancel_idle_reset(self,*args):pass
        class Robot(Abstract):
            def _update(self):raise AssertionError('legacy writer must be suppressed')
        class Daemon:pass
        module=ModuleType('fake_factory_main');module.__file__=__file__;module.startup_app_config=SimpleNamespace(get_startup_app=lambda:'saved-config')
        calls=[]
        def create(args):calls.append('create_app_only');return SimpleNamespace(args=args)
        module.create_app=create
        args=SimpleNamespace(autostart=False,no_media=False,wake_up_on_start=True,goto_sleep_on_stop=True,
            preload_datasets=True,dataset_update_interval_hours=24,fastapi_host='0.0.0.0',sim=True,mockup_sim=True)
        commands={n:type(n,(),{}) for n in ('GetStateCmd','GetMotorModeCmd','GetVersionCmd')}
        return module,Abstract,Robot,Daemon,args,commands,calls
    def prepare(self,parts,path,pins):
        main,abstract,robot,daemon,args,commands,calls=parts
        native=ModuleType('fake_native');native.__file__=str(path);native.ReachyMiniPyControlLoop=Native
        with patch.dict(process.SOURCE_PINS,pins,clear=True):
            return process.prepare_factory_app(main,abstract,robot,daemon,commands,native_module=native,
                native_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),args=args,numpy=SimpleNamespace(asarray=lambda value:value))
    def test_source_mismatch_fails_before_class_patch_or_factory_creation(self):
        parts=self.setup_factory()
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
            with self.assertRaises(ValueError):self.prepare(parts,artifact,dict(process.SOURCE_PINS))
        self.assertEqual(parts[-1],[]);self.assertFalse(hasattr(parts[1],'_finite_head_transport_sealed'))
        self.assertTrue(parts[4].wake_up_on_start)
    def test_preparation_suppresses_producers_before_app_creation_and_cached_fk_is_not_proof(self):
        parts=self.setup_factory();digest=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
            result=self.prepare(parts,artifact,dict.fromkeys(process.SOURCE_PINS,digest))
        main,abstract,robot,daemon,args,commands,calls=parts
        self.assertEqual(calls,['create_app_only']);self.assertTrue(args.no_media);self.assertFalse(args.wake_up_on_start)
        self.assertFalse(args.goto_sleep_on_stop);self.assertEqual(args.fastapi_host,'127.0.0.1')
        self.assertIsNone(main.startup_app_config.get_startup_app());self.assertTrue(abstract._finite_head_transport_sealed)
        instance=robot();updates=[]
        instance.get_all_joint_positions=lambda:([0]*7,[0]*2)
        instance.update_head_kinematics_model=lambda *values:updates.append(values)
        instance.ready=SimpleNamespace(set=lambda:updates.append('ready'))
        instance._update();self.assertEqual(updates[-1],'ready')
        self.assertFalse(result['all_mutation_paths_fenced']);self.assertFalse(result['head_hardware_acceptance'])

if __name__=='__main__':unittest.main()
