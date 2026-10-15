"""Runner entry for one fresh, source-pinned existing factory/private head IPC.

Constructs only the existing factory lifespan backend. Never instantiate the SDK
or another controller. Target native build/finite stop capability proof is a
runner input, not a result inferred from a Mac build or cached HTTP state.
"""
import argparse
import importlib
import json
import math
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler
from .factory_head_process import prepare_factory_app,ready_factory_backend
from .factory_head_runtime import FactoryHeadRuntime,PrivateFactoryHeadIPC
from .factory_head_sample import ExistingFactorySampler
from .factory_head_adapter import verify_native_clock


def pose_matrix(value,np):
    from .factory_head_guard import pose
    x,y,z,roll,pitch,yaw=pose(value)
    cr,sr=math.cos(roll),math.sin(roll);cp,sp=math.cos(pitch),math.sin(pitch);cy,sy=math.cos(yaw),math.sin(yaw)
    matrix=np.eye(4)
    matrix[:3,:3]=[[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
        [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]]
    matrix[:3,3]=[x,y,z];return matrix


def measured_pose(matrix,np):
    from .factory_head_guard import AXES
    matrix=np.asarray(matrix,dtype=float)
    if (matrix.shape!=(4,4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3],[0,0,0,1],atol=1e-6)
            or not np.allclose(matrix[:3,:3].T@matrix[:3,:3],np.eye(3),atol=1e-6)
            or not math.isclose(float(np.linalg.det(matrix[:3,:3])),1,abs_tol=1e-6)):
        raise ValueError('Measured rigid factory pose required')
    r=matrix[:3,:3];horizontal=math.hypot(float(r[0,0]),float(r[1,0]))
    if horizontal<1e-6:raise ValueError('Finite Euler scope cannot cross gimbal lock')
    return dict(zip(AXES,(*[float(v) for v in matrix[:3,3]],math.atan2(float(r[2,1]),float(r[2,2])),
        math.atan2(-float(r[2,0]),horizontal),math.atan2(float(r[1,0]),float(r[0,0])))))


def operator_reader(url,token_env):
    parsed=urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Configured actual Agent operator URL required')
    token=os.environ.get(token_env,'')
    if len(token)<32:raise ValueError('Actual Agent bearer environment required')
    http=build_opener(ProxyHandler({}))
    def read():
        request=Request(url,headers={'Authorization':'Bearer '+token})
        with http.open(request,timeout=.1) as response:
            data=response.read(16385)
            if len(data)>16384:raise ValueError('Operator response bound')
            return json.loads(data)
    return read


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--factory-args',type=Path,required=True)
    parser.add_argument('--native-sha256',required=True)
    parser.add_argument('--capability-proof',type=Path,required=True)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--operator-url',required=True)
    parser.add_argument('--token-env',default='REACHY_COMPANION_TOKEN')
    args=parser.parse_args()
    proof=json.loads(args.capability_proof.read_text())
    if (proof.get('native_artifact_sha256')!=args.native_sha256 or proof.get('target_bounded_io_verified') is not True
            or not isinstance(proof.get('capabilities'),dict)):
        raise ValueError('Reviewed TARGET native measured-capability proof required')
    required=('all_mutation_paths_fenced','native_sample_clock','native_all_torque_read','owner_scoped_stop',
        'enable_pins_present_before_torque','independent_watchdog')
    if any(proof['capabilities'].get(key) is not True for key in required):raise ValueError('Every measured native/factory capability required')
    kin_sha=proof.get('kinematics_artifact_sha256')
    if not isinstance(kin_sha,str) or len(kin_sha)!=64:raise ValueError('Reviewed TARGET native kinematics artifact proof required')
    operator=operator_reader(args.operator_url,args.token_env)
    np=importlib.import_module('numpy');uvicorn=importlib.import_module('uvicorn')
    factory=importlib.import_module('reachy_mini.daemon.app.main')
    abstract=importlib.import_module('reachy_mini.daemon.backend.abstract')
    robot=importlib.import_module('reachy_mini.daemon.backend.robot')
    daemon=importlib.import_module('reachy_mini.daemon.daemon')
    native=importlib.import_module('reachy_mini_motor_controller.reachy_mini_motor_controller')
    analytical=importlib.import_module('reachy_mini.kinematics.analytical_kinematics')
    kin_native=importlib.import_module('reachy_mini_rust_kinematics.reachy_mini_rust_kinematics')
    factory_args=factory.Args(**json.loads(args.factory_args.read_text()))
    commands={key:getattr(abstract,key) for key in ('GetStateCmd','GetMotorModeCmd','GetVersionCmd')}
    prepared=prepare_factory_app(factory,abstract.Backend,robot.RobotBackend,daemon.Daemon,commands,
        native_module=native,native_sha256=args.native_sha256,args=factory_args,numpy=np,
        analytical_class=analytical.AnalyticalKinematics,kinematics_module=kin_native,kinematics_sha256=kin_sha)
    verify_native_clock(native.ReachyMiniPyControlLoop) # after source/binary hash check, before lifespan/UART construction
    state={};stopping=threading.Event()
    def attach_ready():
        deadline=time.monotonic()+10
        while not stopping.wait(.01):
            if time.monotonic()>=deadline:state['error']='factory_readiness_timeout';return
            try:ready=ready_factory_backend(prepared)
            except (AttributeError,RuntimeError):ready=False
            if not ready:continue
            backend=prepared['app'].state.daemon.backend;controller=backend.c
            def fk(joints):return measured_pose(backend.head_kinematics.fk(np.asarray(joints),no_iterations=20),np)
            def ik(value,body):
                result=backend.head_kinematics.ik(pose_matrix(value,np),body_yaw=body)
                if result is None:raise ValueError('Factory IK has no solution')
                values=np.asarray(result,dtype=float)
                if values.shape!=(7,) or not np.isfinite(values).all():raise ValueError('Finite seven-joint IK required')
                return tuple(float(value) for value in values)
            # Runtime identity includes this process and an unreused private boot.
            from .contracts import uid
            identity=f'factory:{os.getpid()}:{uid()}'
            sampler=ExistingFactorySampler(controller,identity,fk,prepared['kinematics_lock'])
            runtime=FactoryHeadRuntime(controller,sampler,operator,fk,ik,prepared['kinematics_lock'],proof['capabilities'],identity,
                readiness=lambda:(ready_factory_backend(prepared) and prepared['app'].state.daemon.backend is backend
                    and backend.c is controller))
            ipc=PrivateFactoryHeadIPC(runtime,args.directory);state.update(runtime=runtime,ipc=ipc)
            ipc.serve();return
    thread=threading.Thread(target=attach_ready,daemon=True);thread.start()
    try:uvicorn.run(prepared['sealed_app'],host='127.0.0.1',port=factory_args.fastapi_port)
    finally:
        stopping.set()
        if 'ipc' in state:state['ipc'].close()
        thread.join(.5)
    # Runner must inspect measured cleanup before replacing this UART owner.
    if state.get('error'):raise RuntimeError(state['error'])

if __name__=='__main__':main()
