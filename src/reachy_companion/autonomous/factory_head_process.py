"""Prepare a fresh existing-factory ASGI process without starting its lifespan.

Never execute the installed console main (wireless startup/audio config hooks).
The hardware runner owns replacement/start/restore and private IPC. Preparation
is not native hardware capability proof or permission to move.
"""
import hashlib
import inspect
import math
import threading
import time
from pathlib import Path
from .factory_head_fence import FactoryReadOnlyASGI,install_backend_read_fence
from .factory_head_adapter import NATIVE_METHODS
from .factory_head_kinematics import verify_kinematics,install_bounded_kinematics,reject_existing_instances

STARTUP_METHODS=('finite_prepare_readonly_startup','finite_startup_status')

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


def prepare_factory_app(main_module,abstract_class,robot_class,daemon_class,commands,*,native_module,native_sha256,args,numpy,
                        analytical_class,kinematics_module,kinematics_sha256):
    """Explicit preparation before constructors/listeners in a fresh process.

    Caller imports the exact installed modules, supplies the reviewed TARGET
    artifact hash and starts only the returned ASGI wrapper. No vendor files or
    saved startup-app/mixer/config are modified. Never call this on live objects.
    """
    native_path=getattr(native_module,'__file__',None)
    native_class=getattr(native_module,'ReachyMiniPyControlLoop',None)
    if (not native_path or Path(native_path).suffix not in ('.so','.pyd','.dylib')
            or getattr(inspect.getmodule(robot_class),'ReachyMiniPyControlLoop',None) is not native_class
            or native_class is None or any(not callable(getattr(native_class,n,None)) for n in (*NATIVE_METHODS,*STARTUP_METHODS))):
        raise ValueError('Actual factory native class/artifact .4 startup ABI binding required')
    verify_source(dict(main=main_module,abstract=abstract_class,robot=robot_class,daemon=daemon_class),native_path,native_sha256)
    verify_kinematics(analytical_class,kinematics_module,kinematics_sha256)
    if getattr(robot_class,'_finite_factory_prepared',False):raise ValueError('Fresh factory process required')
    if not issubclass(robot_class,abstract_class):raise ValueError('Pinned factory class inheritance required')
    if not callable(getattr(robot_class,'_update',None)):raise ValueError('Pinned robot update ABI required')
    for key,value in dict(autostart=True,no_media=True,wake_up_on_start=False,goto_sleep_on_stop=False,
        preload_datasets=False,dataset_update_interval_hours=0,fastapi_host='127.0.0.1',sim=False,mockup_sim=False,
        hardware_config_filepath=None,kinematics_engine='AnalyticalKinematics',check_collision=False).items():
        if not hasattr(args,key):raise ValueError('Pinned factory argument ABI required')
    reject_existing_instances((abstract_class,robot_class,daemon_class,analytical_class))
    lock=threading.RLock()
    # Validate every preflight above before class/startup patches.
    native_class.finite_prepare_readonly_startup() # irreversible, BEFORE controller/lifespan
    kinematics=install_bounded_kinematics(analytical_class,numpy,lock)
    fence=install_backend_read_fence(abstract_class,commands)
    main_module.startup_app_config.get_startup_app=lambda:None # process-local; no saved-config write
    for key,value in dict(autostart=True,no_media=True,wake_up_on_start=False,goto_sleep_on_stop=False,
        preload_datasets=False,dataset_update_interval_hours=0,fastapi_host='127.0.0.1',sim=False,mockup_sim=False,
        hardware_config_filepath=None,kinematics_engine='AnalyticalKinematics',check_collision=False).items():setattr(args,key,value)
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
        read_only_update=update_read_only,native_class=native_class,backend_class=robot_class,
        source_pinned=True,transport_fence=fence,native_artifact_sha256=native_sha256,
        **kinematics,kinematics_artifact_sha256=kinematics_sha256,
        all_mutation_paths_fenced=False,head_hardware_acceptance=False,
        remaining=['verify_actual_ready_backend/no_media/no_startup_producers','verify_target_native_ABI_and_all9_disabled',
                   'native_owner_arm/private_IPC','bounded_FK_IK_and_finite_scheduler','runner_measured_stop_capability'])


def ready_factory_backend(preparation):
    """Actual live producer/readiness check; no cached pose/torque attestation."""
    if preparation.get('source_pinned') is not True:return False
    app=preparation['app'];sealed=preparation['sealed_app']
    if not isinstance(sealed,FactoryReadOnlyASGI) or sealed.app is not app:return False
    backend=app.state.daemon.backend
    if type(backend) is not preparation['backend_class'] or type(backend)._update is not preparation['read_only_update']:return False
    if getattr(backend,'error',None) is not None:return False
    if (type(getattr(backend,'c',None)) is not preparation['native_class']
            or not backend.ready.is_set() or backend.should_stop.is_set()):return False
    native_start=backend.c.finite_startup_status()
    if (not isinstance(native_start,(tuple,list)) or len(native_start)!=6 or native_start[0] is not True
            or native_start[1] is not True or type(native_start[2]) is not int or native_start[2]!=63 or len(native_start[3])!=9
            or any(type(v) is not int or v not in (0,1) for v in native_start[3])
            or len(native_start[4])!=9 or any(v is not False for v in native_start[4])
            or type(native_start[5]) not in (int,float) or not math.isfinite(native_start[5]) or not 0<=native_start[5]<=1000):return False
    model=getattr(backend,'head_kinematics',None)
    if (type(model) is not preparation['kinematics_class'] or type(model).fk is not preparation['bounded_fk']
            or type(model).ik is not preparation['bounded_ik'] or getattr(model,'_finite_kinematics_failed',True)
            or model.automatic_body_yaw is not False):return False
    required=('_media_server','_tracking_aim','_tracking_weight','_speech_offsets','gravity_compensation_mode',
        '_tracking_enabled','_tracking_target_pose','_tracker','_idle_reset_task','_active_move_depth',
        '_active_move_token','_active_audio_upload_id','ik_required')
    if any(not hasattr(backend,key) for key in required):return False
    if (backend._media_server is not None or backend._tracking_aim is not None or backend._tracking_weight!=0
            or backend.gravity_compensation_mode is not False or backend._tracking_enabled is not False
            or backend._tracking_target_pose is not None or backend._tracker is not None or backend._idle_reset_task is not None
            or type(backend._active_move_depth) is not int or backend._active_move_depth!=0 or backend._active_move_token is not None
            or backend._active_audio_upload_id is not None or backend.ik_required is not False):return False
    offsets=backend._speech_offsets
    if not isinstance(offsets,(tuple,list)) or len(offsets)!=6 or any(value!=0 for value in offsets):return False
    if not hasattr(app.state,'startup_app_antenna_watcher_task') or app.state.startup_app_antenna_watcher_task is not None:return False
    return True
