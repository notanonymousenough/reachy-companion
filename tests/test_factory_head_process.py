"""Fresh-process wiring traces with fake factory modules; no native loading/UART."""
import hashlib
import inspect
from pathlib import Path
import sys
import tempfile
import threading
from types import ModuleType,SimpleNamespace,FunctionType
import unittest
from unittest.mock import Mock,patch
from reachy_companion.autonomous import factory_head_process as process
from reachy_companion.autonomous.factory_head_adapter import NATIVE_METHODS

class Native:
    pass
for method in (*NATIVE_METHODS,*process.STARTUP_METHODS):setattr(Native,method,lambda *args:None)
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
        module=ModuleType('fake_factory_main');module.__file__=__file__;module.startup_app_config=SimpleNamespace(get_startup_app=lambda:'saved-config')
        calls=[]
        module.ip_probe=lambda:None;module.imu_probe=lambda:None
        def construct(self,**kwargs):
            if kwargs:
                calls.append('backend_ctor');self.c=Native();calls.append('native_ctor')
                if kwargs['wireless_version']:module.imu_probe() # exact public Robot constructor branch, no BMI import
                self.head_kinematics=module.fake_analytical_class();calls.append('model_ctor')
        Robot.__init__=construct
        tools=ModuleType('reachy_mini.tools.reflash_motors');tools.calls=calls
        exec("def reflash_motors_if_needed(*args,**kwargs):calls.append('UNSAFE_reflash')",vars(tools))
        vendor=ModuleType('fixture_factory_daemon');vendor.__file__=str(Path(__file__).parent/'fixtures/factory_daemon_setup.py')
        vendor.RobotBackend=Robot;vendor.reflash_motors_if_needed=tools.reflash_motors_if_needed
        vendor.find_serial_port=lambda **kw:calls.append('UNSAFE_serial_discovery')
        exec(compile(Path(vendor.__file__).read_bytes(),vendor.__file__,'exec'),vars(vendor));Daemon=vendor.Daemon
        modules=patch.dict(sys.modules,{vendor.__name__:vendor,tools.__name__:tools});modules.start();self.addCleanup(modules.stop)
        def create(args):
            if args.hardware_config_filepath is not None:raise AssertionError('PID write path reachable before arm')
            if args.wireless_version:module.ip_probe() # model of pre-backend Daemon.start branch
            calls.append('create_app_only');return SimpleNamespace(args=args)
        class Analytical:
            def __init__(self,automatic_body_yaw=True):self.automatic_body_yaw=automatic_body_yaw
            def fk(self,*args,**kwargs):raise AssertionError('Unbounded FK must be replaced')
            def ik(self,*args,**kwargs):return [0]*7
        module.fake_analytical_class=Analytical
        Native.finite_prepare_readonly_startup=staticmethod(lambda:calls.append('native_readonly_prepare'))
        Native.finite_startup_status=staticmethod(lambda:(True,True,63,[0]*9,[False]*9,1.))
        module.create_app=create
        args=SimpleNamespace(autostart=False,no_media=False,wake_up_on_start=True,goto_sleep_on_stop=True,
            preload_datasets=True,dataset_update_interval_hours=24,fastapi_host='0.0.0.0',sim=True,mockup_sim=True,hardware_config_filepath='private-pid-config',kinematics_engine='NN',check_collision=True,serialport='/dev/fixture-uart',wireless_version=True)
        commands={n:type(n,(),{}) for n in ('GetStateCmd','GetMotorModeCmd','GetVersionCmd')}
        return module,Abstract,Robot,Daemon,args,commands,calls
    def pins(self,parts):
        return {key:hashlib.sha256(Path(inspect.getsourcefile(value)).read_bytes()).hexdigest()
            for key,value in zip(('main','abstract','robot','daemon'),parts[:4])}
    def backend_args(self):
        return dict(wireless_version=False,sim=False,mockup_sim=False,serialport='/dev/fixture-uart',scene='fixture',
            check_collision=False,kinematics_engine='AnalyticalKinematics',headless=True,use_audio=False,hardware_config_filepath=None)
    def daemon(self,parts):
        daemon=parts[3]();daemon.logger=SimpleNamespace(info=lambda *args:None);daemon.log_level='INFO';return daemon
    def prepare(self,parts,path,pins):
        main,abstract,robot,daemon,args,commands,calls=parts
        native=ModuleType('fake_native');native.__file__=str(path);native.ReachyMiniPyControlLoop=Native
        with patch.dict(process.SOURCE_PINS,pins,clear=True),patch.object(process,'verify_kinematics'):
            return process.prepare_factory_app(main,abstract,robot,daemon,commands,native_module=native,
                native_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),args=args,numpy=SimpleNamespace(asarray=lambda value:value),
                analytical_class=main.fake_analytical_class,kinematics_module=SimpleNamespace(),kinematics_sha256='a'*64)
    def test_source_mismatch_fails_before_class_patch_or_factory_creation(self):
        parts=self.setup_factory()
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
            with self.assertRaises(ValueError):self.prepare(parts,artifact,dict(process.SOURCE_PINS))
        self.assertEqual(parts[-1],[]);self.assertFalse(hasattr(parts[1],'_finite_head_transport_sealed'))
        self.assertTrue(parts[4].wake_up_on_start)
    def test_existing_backend_instance_prevents_native_prepare_or_live_class_patch(self):
        parts=self.setup_factory();existing=parts[2]();original=type(existing)._update
        digest=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
            with self.assertRaises(ValueError):self.prepare(parts,artifact,self.pins(parts))
        self.assertEqual(parts[-1],[]);self.assertIs(type(existing)._update,original)
        self.assertFalse(hasattr(parts[1],'_finite_head_transport_sealed'))

    def test_legacy_startup_abi_or_prior_native_owner_rejects_before_any_class_patch(self):
        parts=self.setup_factory();digest=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
            with patch.object(Native,'finite_prepare_readonly_startup',None):
                with self.assertRaises(ValueError):self.prepare(parts,artifact,self.pins(parts))
            with patch.object(Native,'finite_prepare_readonly_startup',side_effect=RuntimeError('native owner already existed')):
                with self.assertRaises(RuntimeError):self.prepare(parts,artifact,self.pins(parts))
        self.assertEqual(parts[-1],[]);self.assertFalse(hasattr(parts[1],'_finite_head_transport_sealed'))
        self.assertFalse(hasattr(parts[0].fake_analytical_class,'_finite_kinematics_prepared'))
        self.assertEqual(parts[4].hardware_config_filepath,'private-pid-config')

    def test_preparation_suppresses_producers_before_app_creation_and_cached_fk_is_not_proof(self):
        parts=self.setup_factory();digest=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
            result=self.prepare(parts,artifact,self.pins(parts))
        main,abstract,robot,daemon,args,commands,calls=parts
        self.assertEqual(calls,['native_readonly_prepare','create_app_only']);self.assertTrue(args.no_media);self.assertFalse(args.wake_up_on_start)
        self.assertIsNone(args.hardware_config_filepath);self.assertEqual(args.kinematics_engine,'AnalyticalKinematics');self.assertFalse(args.check_collision)
        self.assertFalse(args.goto_sleep_on_stop);self.assertEqual(args.fastapi_host,'127.0.0.1')
        self.assertIs(args.wireless_version,False)
        self.assertIsNone(main.startup_app_config.get_startup_app());self.assertTrue(abstract._finite_head_transport_sealed)
        instance=robot();updates=[]
        instance.get_all_joint_positions=lambda:([0]*7,[0]*2)
        instance.update_head_kinematics_model=lambda *values:updates.append(values)
        instance.ready=SimpleNamespace(set=lambda:updates.append('ready'))
        instance._update();self.assertEqual(updates[-1],'ready')
        self.assertFalse(result['all_mutation_paths_fenced']);self.assertFalse(result['head_hardware_acceptance'])
        instance.c=Native();instance.ready=threading.Event();instance.ready.set();instance.should_stop=threading.Event()
        instance._media_server=None;instance._tracking_aim=None;instance._tracking_weight=0.;instance._speech_offsets=(0,)*6
        instance.gravity_compensation_mode=False
        instance.head_kinematics=main.fake_analytical_class()
        instance._tracking_enabled=False;instance._tracking_target_pose=None;instance._tracker=None;instance._idle_reset_task=None
        instance._active_move_depth=0;instance._active_move_token=None;instance._active_audio_upload_id=None;instance.ik_required=False
        result['app'].state=SimpleNamespace(daemon=SimpleNamespace(backend=instance),startup_app_antenna_watcher_task=None)
        self.assertTrue(process.ready_factory_backend(result))
        for key,value in (('_media_server',object()),('_tracking_aim',object()),('_speech_offsets',(1,0,0,0,0,0)),('_active_move_depth',1),('_idle_reset_task',object()),('_tracking_enabled',True)):
            previous=getattr(instance,key);setattr(instance,key,value)
            self.assertFalse(process.ready_factory_backend(result));setattr(instance,key,previous)
        for target,key in ((result['startup_daemon_class'],'_setup_backend'),(result['startup_module'],'reflash_motors_if_needed'),
                (result['startup_tools_module'],'reflash_motors_if_needed'),(result['startup_module'],'RobotBackend')):
            previous=getattr(target,key);setattr(target,key,object())
            self.assertFalse(process.ready_factory_backend(result));setattr(target,key,previous)
        instance.should_stop.set();self.assertFalse(process.ready_factory_backend(result))

    def test_exact_public_vendor_default_reflashes_before_ctor_but_fenced_lifespan_never_does(self):
        previous=self.setup_factory();self.daemon(previous)._setup_backend(**self.backend_args())
        self.assertEqual(previous[-1],['UNSAFE_reflash','backend_ctor','native_ctor','model_ctor'])
        for mode in ('default','keyword_true','positional_true'):
            parts=self.setup_factory();original=parts[3]._setup_backend
            with tempfile.TemporaryDirectory() as directory:
                artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
                prepared=self.prepare(parts,artifact,self.pins(parts))
            self.assertEqual(parts[-1],['native_readonly_prepare','create_app_only'])
            instance=self.daemon(parts);values=self.backend_args()
            if mode=='default':instance._setup_backend(**values)
            elif mode=='keyword_true':instance._setup_backend(**values,reflash_motors_on_start=True)
            else:instance._setup_backend(*values.values(),True)
            self.assertEqual(parts[-1],['native_readonly_prepare','create_app_only','backend_ctor','native_ctor','model_ctor'])
            before=list(parts[-1])
            with self.assertRaises(ValueError):instance._setup_backend(**values)
            self.assertEqual(parts[-1],before) # never a second controller before model singleton rejects
            self.assertTrue(process.startup_fence_intact(prepared));self.assertFalse(prepared['all_mutation_paths_fenced'])
            for raw in (prepared['startup_module'].reflash_motors_if_needed,prepared['startup_tools_module'].reflash_motors_if_needed):
                with self.assertRaises(ValueError):raw('/dev/fixture-uart',dont_light_up=True)
            with self.assertRaises(ValueError):original(instance,**values) # original default still hits trap

    def test_missing_auto_or_changed_serial_and_nonreadonly_profiles_never_discover_or_construct(self):
        for port in (None,'','auto','/dev/../fixture','relative','/dev//fixture'):
            parts=self.setup_factory();parts[4].serialport=port
            with tempfile.TemporaryDirectory() as directory:
                artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
                with self.assertRaises(ValueError):self.prepare(parts,artifact,self.pins(parts))
            self.assertEqual(parts[-1],[])
        parts=self.setup_factory()
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded');self.prepare(parts,artifact,self.pins(parts))
        instance=self.daemon(parts);before=list(parts[-1])
        for key,value in (('serialport','auto'),('serialport','/dev/foreign-uart'),('wireless_version',True),('wireless_version',0),('sim',True),('mockup_sim',True),
                ('use_audio',True),('check_collision',True),('hardware_config_filepath','/fixture/pid.yaml'),('kinematics_engine','NN')):
            values=self.backend_args();values[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):instance._setup_backend(**values)
        self.assertEqual(parts[-1],before)

    def test_nooutput_profile_closes_ip_and_imu_constructor_branches_before_lifespan(self):
        # Causal model of the exact public branches reviewed in daemon/robot:
        # wireless=True reaches both probes even with media disabled.
        old=self.setup_factory();old[4].hardware_config_filepath=None;old[4].no_media=True
        old[0].ip_probe=Mock();old[0].imu_probe=Mock()
        old[0].create_app(old[4]);values=self.backend_args();values['wireless_version']=True
        self.daemon(old)._setup_backend(**values)
        old[0].ip_probe.assert_called_once();old[0].imu_probe.assert_called_once()
        parts=self.setup_factory();parts[0].ip_probe=Mock(side_effect=AssertionError('IP getter reached'))
        parts[0].imu_probe=Mock(side_effect=AssertionError('BMI constructor reached'))
        original_serial=parts[4].serialport
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
            prepared=self.prepare(parts,artifact,self.pins(parts))
        self.assertIs(parts[4].wireless_version,False);self.assertEqual(parts[4].serialport,original_serial)
        instance=self.daemon(parts);before=list(parts[-1])
        with self.assertRaises(ValueError):instance._setup_backend(**values)
        self.assertEqual(parts[-1],before) # True denied BEFORE original/controller/IMU
        instance._setup_backend(**self.backend_args())
        parts[0].ip_probe.assert_not_called();parts[0].imu_probe.assert_not_called()
        self.assertEqual(parts[-1],['native_readonly_prepare','create_app_only','backend_ctor','native_ctor','model_ctor'])
        self.assertFalse(prepared['all_mutation_paths_fenced']);self.assertFalse(prepared['head_hardware_acceptance'])

    def test_unknown_vendor_runtime_function_defaults_or_globals_deny_before_native_prepare(self):
        for mode in ('code','defaults','bool_confusion','backend','raw'):
            parts=self.setup_factory();daemon=parts[3];module=inspect.getmodule(daemon);original=daemon._setup_backend
            if mode=='code':
                daemon._setup_backend=FunctionType(original.__code__.replace(co_name='foreign_startup'),vars(module),
                    original.__name__,original.__defaults__)
            elif mode=='defaults':original.__defaults__=(None,False)
            elif mode=='bool_confusion':original.__defaults__=(None,1)
            elif mode=='backend':module.RobotBackend=object
            else:module.reflash_motors_if_needed=lambda *args,**kwargs:None
            with tempfile.TemporaryDirectory() as directory:
                artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
                with self.assertRaises(ValueError):self.prepare(parts,artifact,self.pins(parts))
            self.assertEqual(parts[-1],[]);self.assertFalse(hasattr(parts[2],'_finite_factory_prepared'))

    def test_unknown_method_shape_with_new_whole_file_hash_still_denies(self):
        parts=self.setup_factory();old=inspect.getmodule(parts[3])
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'drifted_daemon.py'
            source.write_text(Path(old.__file__).read_text().replace('reflash_motors_on_start: bool = True','reflash_motors_on_start: bool = False'))
            vendor=ModuleType('fixture_drifted_daemon');vendor.__dict__.update(vars(old));vendor.__name__='fixture_drifted_daemon';vendor.__file__=str(source)
            exec(compile(source.read_bytes(),str(source),'exec'),vars(vendor))
            changed=(*parts[:3],vendor.Daemon,*parts[4:])
            with patch.dict(sys.modules,{vendor.__name__:vendor}):
                artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded')
                with self.assertRaises(ValueError):self.prepare(changed,artifact,self.pins(changed))
        self.assertEqual(parts[-1],[])

    def test_unknown_backend_construction_remains_single_use_without_retry(self):
        parts=self.setup_factory()
        with tempfile.TemporaryDirectory() as directory:
            artifact=Path(directory)/'native.so';artifact.write_bytes(b'not-loaded');self.prepare(parts,artifact,self.pins(parts))
        instance=self.daemon(parts)
        with patch.object(parts[2],'__init__',side_effect=RuntimeError('unknown constructor completion')) as constructor:
            with self.assertRaisesRegex(RuntimeError,'unknown constructor'):instance._setup_backend(**self.backend_args())
            with self.assertRaises(ValueError):instance._setup_backend(**self.backend_args())
            self.assertEqual(constructor.call_count,1)

if __name__=='__main__':unittest.main()
