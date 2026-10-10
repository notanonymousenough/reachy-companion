"""Prepare a fresh existing-factory ASGI process without starting its lifespan.

Never execute the installed console main (wireless startup/audio config hooks).
The hardware runner owns replacement/start/restore and private IPC. Preparation
is not native hardware capability proof or permission to move.
"""
import hashlib
import inspect
import threading
import time
from pathlib import Path
from .factory_head_fence import FactoryReadOnlyASGI,install_backend_read_fence
from .factory_head_adapter import NATIVE_METHODS

SOURCE_PINS={'main':'7bf043a1300b1eda7f2c6593a27fd70b8f953c4b2b08832310edd102a2cbc30c',
    'abstract':'0aea04d0cc08c8325f54cd39a4b6dfca36935b828635f2a2ca23b9f05c38803b',
    'robot':'16d3dae8add1f30eb608de8aa9ae04d1afd31924fc7d5729bf515823f4bcdd57',
    'daemon':'794fecf0dcbbe003cb09672fc821ca186a10ba07391a695ecb4c7fb28429b007'}


def verify_source(objects,native_path,native_sha256):
    if set(objects)!=set(SOURCE_PINS):raise ValueError('Exact installed factory source objects required')
    for name,obj in objects.items():
        source=inspect.getsourcefile(obj)
        if source is None or hashlib.sha256(Path(source).read_bytes()).hexdigest()!=SOURCE_PINS[name]:
            raise ValueError('Installed factory source pin mismatch: '+name)
    native_path=Path(native_path)
    if (not isinstance(native_sha256,str) or len(native_sha256)!=64
            or hashlib.sha256(native_path.read_bytes()).hexdigest()!=native_sha256):raise ValueError('Reviewed target native artifact pin required')


def prepare_factory_app(main_module,abstract_class,robot_class,daemon_class,commands,*,native_module,native_sha256,args,numpy):
    """Explicit preparation before constructors/listeners in a fresh process.

    Caller imports the exact installed modules, supplies the reviewed TARGET
    artifact hash and starts only the returned ASGI wrapper. No vendor files or
    saved startup-app/mixer/config are modified. Never call this on live objects.
    """
    native_path=getattr(native_module,'__file__',None)
    native_class=getattr(native_module,'ReachyMiniPyControlLoop',None)
    if (not native_path or Path(native_path).suffix not in ('.so','.pyd','.dylib')
            or getattr(inspect.getmodule(robot_class),'ReachyMiniPyControlLoop',None) is not native_class
            or native_class is None or any(not callable(getattr(native_class,n,None)) for n in NATIVE_METHODS)):
        raise ValueError('Actual factory native class/artifact .2 ABI binding required')
    verify_source(dict(main=main_module,abstract=abstract_class,robot=robot_class,daemon=daemon_class),native_path,native_sha256)
    if getattr(robot_class,'_finite_factory_prepared',False):raise ValueError('Fresh factory process required')
    if not issubclass(robot_class,abstract_class):raise ValueError('Pinned factory class inheritance required')
    if not callable(getattr(robot_class,'_update',None)):raise ValueError('Pinned robot update ABI required')
    for key,value in dict(autostart=True,no_media=True,wake_up_on_start=False,goto_sleep_on_stop=False,
        preload_datasets=False,dataset_update_interval_hours=0,fastapi_host='127.0.0.1',sim=False,mockup_sim=False).items():
        if not hasattr(args,key):raise ValueError('Pinned factory argument ABI required')
    lock=threading.RLock()
    # Validate every preflight above before class/startup patches.
    fence=install_backend_read_fence(abstract_class,commands)
    main_module.startup_app_config.get_startup_app=lambda:None # process-local; no saved-config write
    for key,value in dict(autostart=True,no_media=True,wake_up_on_start=False,goto_sleep_on_stop=False,
        preload_datasets=False,dataset_update_interval_hours=0,fastapi_host='127.0.0.1',sim=False,mockup_sim=False).items():setattr(args,key,value)
    def update_read_only(self):
        # Replace the existing update's target/IK/tracking/gravity writers.
        # Cached publication is allowed; it NEVER supplies a guard sample.
        with lock:
            head,antennas=self.get_all_joint_positions()
            self.update_head_kinematics_model(numpy.asarray(head),numpy.asarray(antennas))
            self.last_alive=time.time();self.ready.set()
    robot_class._update=update_read_only;robot_class._finite_factory_prepared=True
    app=main_module.create_app(args)
    return dict(app=app,sealed_app=FactoryReadOnlyASGI(app),kinematics_lock=lock,
        source_pinned=True,transport_fence=fence,native_artifact_sha256=native_sha256,
        all_mutation_paths_fenced=False,head_hardware_acceptance=False,
        remaining=['verify_actual_ready_backend/no_media/no_startup_producers','verify_target_native_ABI_and_all9_disabled',
                   'native_owner_arm/private_IPC','bounded_FK_IK_and_finite_scheduler','runner_measured_stop_capability'])
