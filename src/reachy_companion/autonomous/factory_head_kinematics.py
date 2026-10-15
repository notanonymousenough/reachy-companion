"""Process-local bounded analytical FK/IK over the factory's exact mutable model.

Bounds attempts and rejects elapsed budgets AFTER native calls return. It cannot
interrupt a hung Rust call or certify target I/O/solver capability by itself.
"""
import hashlib
import gc
import inspect
import math
from pathlib import Path
import time

ANALYTICAL_SHA256='602b522febefa6c465be6cd92ba7934e0d4837cc6b7052bfbb3c6229eacbc942'
ASSETS_SHA256='b07324cfe46515d7b3bd5be416f5f2ed87811ac1fcdb0e6ad841119e4ed9ab3b'


def reject_existing_instances(classes):
    # Fresh exclusive preparation only; never patch a live factory/model class.
    if any(issubclass(type(value),klass) for value in gc.get_objects() for klass in classes):
        raise ValueError('Existing factory/kinematics instances cannot be adopted')


def verify_kinematics(analytical_class,native_module,native_sha256):
    source=inspect.getsourcefile(analytical_class)
    if not source or hashlib.sha256(Path(source).read_bytes()).hexdigest()!=ANALYTICAL_SHA256:
        raise ValueError('Pinned factory analytical source required')
    assets=Path(source).parents[1]/'assets'/'kinematics_data.json'
    if hashlib.sha256(assets.read_bytes()).hexdigest()!=ASSETS_SHA256:raise ValueError('Pinned factory kinematics geometry required')
    artifact=Path(getattr(native_module,'__file__',''))
    if (artifact.suffix not in ('.so','.pyd','.dylib') or not isinstance(native_sha256,str) or len(native_sha256)!=64
            or hashlib.sha256(artifact.read_bytes()).hexdigest()!=native_sha256
            or getattr(inspect.getmodule(analytical_class),'ReachyMiniRustKinematics',None) is not getattr(native_module,'ReachyMiniRustKinematics',None)
            or getattr(native_module,'ReachyMiniRustKinematics',None) is None):
        raise ValueError('Exact reviewed native kinematics class/artifact required')
    if getattr(analytical_class,'_finite_kinematics_prepared',False):raise ValueError('Fresh kinematics class required')
    if any(not callable(getattr(analytical_class,name,None)) for name in ('__init__','fk','ik')):
        raise ValueError('Pinned analytical kinematics ABI required')


def install_bounded_kinematics(klass,np,lock,*,clock=time.monotonic):
    """Install before every constructor, covering startup and cached-update FK."""
    if getattr(klass,'_finite_kinematics_prepared',False):raise ValueError('Fresh kinematics class required')
    reject_existing_instances((klass,))
    original_init=klass.__init__;original_ik=klass.ik
    allocated=[False]
    def rigid(value):
        matrix=np.asarray(value,dtype=float)
        if (matrix.shape!=(4,4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3],[0,0,0,1],atol=1e-6)
                or not np.allclose(matrix[:3,:3].T@matrix[:3,:3],np.eye(3),atol=1e-6)
                or not math.isclose(float(np.linalg.det(matrix[:3,:3])),1,abs_tol=1e-6)):
            raise ValueError('Finite rigid kinematics result required')
        return matrix
    def fresh(began):
        if not 0<=clock()-began<=.1:raise ValueError('Actual kinematics call exceeded elapsed budget')
    def init(self,automatic_body_yaw=True):
        if not lock.acquire(blocking=False):raise RuntimeError('Actual shared model slot occupied at construction')
        try:
            if allocated[0]:raise RuntimeError('Finite factory may construct only one kinematics model')
            allocated[0]=True # failed/unknown construction cannot be retried
            self._finite_kinematics_failed=True
            self._finite_measured_body=None;self._finite_measured_at=None
            original_init(self,automatic_body_yaw=False) # never auto-turn measured body
            self._finite_kinematics_failed=False
        finally:lock.release()
    def fk(self,joint_angles,check_collision=False,no_iterations=3):
        if type(no_iterations) is not int or not 1<=no_iterations<=20 or check_collision is not False:
            raise ValueError('Finite analytical iteration budget required')
        joints=np.asarray(joint_angles,dtype=float)
        if joints.shape!=(7,) or not np.isfinite(joints).all():raise ValueError('Seven measured finite joints required')
        if getattr(self,'_finite_kinematics_failed',True):raise RuntimeError('Kinematics outcome quarantined')
        if not lock.acquire(blocking=False):raise RuntimeError('Actual shared kinematics slot occupied')
        began=clock()
        try:
            body=float(joints[0]);stewart=joints[1:].tolist()
            matrix=None
            for _ in range(no_iterations):
                fresh(began);matrix=rigid(self.kin.forward_kinematics(list(stewart),body));fresh(began)
            # One attempt only. Never perturb measured joints/body or reset the
            # solver to manufacture an upright/converged result.
            horizontal=math.hypot(float(matrix[0,0]),float(matrix[1,0]))
            roll=math.atan2(float(matrix[2,1]),float(matrix[2,2]))
            if horizontal<1e-6 or abs(roll)>math.pi/2:raise ValueError('Analytical FK not upright')
            inverse=np.asarray(self.kin.inverse_kinematics(matrix.tolist(),body),dtype=float)
            if inverse.shape!=(6,) or not np.isfinite(inverse).all():raise ValueError('FK inverse residual unavailable')
            errors=np.arctan2(np.sin(inverse-joints[1:]),np.cos(inverse-joints[1:]))
            if np.max(np.abs(errors))>2e-3:raise ValueError('Analytical FK did not converge to measured joints')
            fresh(began);result=matrix.copy();result[2,3]-=self.head_z_offset
            result=rigid(result);self._finite_measured_body=body;self._finite_measured_at=began
            return result
        except BaseException:self._finite_kinematics_failed=True;raise
        finally:lock.release()
    def ik(self,pose,body_yaw=None,check_collision=False,no_iterations=0):
        matrix=rigid(pose)
        if body_yaw is None:
            body_yaw=self._finite_measured_body
            if self._finite_measured_at is None:raise ValueError('Fresh measured body required for implicit startup IK')
            fresh(self._finite_measured_at)
        if (type(no_iterations) is not int or not 0<=no_iterations<=20 or check_collision is not False
                or type(body_yaw) not in (int,float) or not math.isfinite(body_yaw)):
            raise ValueError('Finite preserved-body analytical IK required')
        if getattr(self,'_finite_kinematics_failed',True) or self.automatic_body_yaw is not False:
            raise RuntimeError('Kinematics scope changed/quarantined')
        if not lock.acquire(blocking=False):raise RuntimeError('Actual shared kinematics slot occupied')
        began=clock()
        try:
            fresh(began);result=np.asarray(original_ik(self,matrix,body_yaw=body_yaw,check_collision=False,no_iterations=no_iterations),dtype=float)
            fresh(began)
            if result.shape!=(7,) or not np.isfinite(result).all() or abs(float(result[0])-body_yaw)>1e-4:
                raise ValueError('Analytical IK changed preserved body or returned invalid joints')
            return result
        except BaseException:self._finite_kinematics_failed=True;raise
        finally:lock.release()
    klass.__init__=init;klass.fk=fk;klass.ik=ik;klass._finite_kinematics_prepared=True
    return dict(kinematics_class=klass,bounded_fk=fk,bounded_ik=ik)
