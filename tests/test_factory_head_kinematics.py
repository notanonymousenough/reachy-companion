"""Bound every analytical callsite without replacing the actual mutable model."""
import math
import threading
import unittest
from unittest.mock import Mock
try:import numpy as np
except ImportError:np=None
from reachy_companion.autonomous.factory_head_kinematics import install_bounded_kinematics


@unittest.skipIf(np is None,'NumPy required')
class KinematicsTests(unittest.TestCase):
    def model(self,*,matrix=None,residual=0.,delay=0.):
        clock=[10.];calls=[]
        class Analytical:
            def __init__(self,automatic_body_yaw=True):
                self.automatic_body_yaw=automatic_body_yaw;self.head_z_offset=.1
                self.kin=Mock()
                def forward(joints,body):
                    calls.append((tuple(joints),body));clock[0]+=delay
                    return (np.eye(4) if matrix is None else matrix).tolist()
                self.kin.forward_kinematics.side_effect=forward
                self.kin.inverse_kinematics.return_value=[residual]*6
            def fk(self,*args,**kwargs):raise AssertionError('Unbounded outer FK loop called')
            def ik(self,pose,body_yaw=0.,**kwargs):
                self.last_ik_body=body_yaw
                return np.array([body_yaw]+[0.]*6)
        lock=threading.RLock()
        prepared=install_bounded_kinematics(Analytical,np,lock,clock=lambda:clock[0])
        return Analytical(),clock,calls,lock,prepared

    def test_existing_model_instance_prevents_patch_and_second_model_cannot_construct(self):
        class Existing:
            def __init__(self,automatic_body_yaw=True):self.automatic_body_yaw=automatic_body_yaw
            def fk(self,*args,**kwargs):return 'original'
            def ik(self,*args,**kwargs):return 'original'
        existing=Existing();original=Existing.fk
        with self.assertRaises(ValueError):install_bounded_kinematics(Existing,np,threading.RLock())
        self.assertIs(Existing.fk,original);self.assertTrue(existing.automatic_body_yaw)
        model,clock,calls,lock,_=self.model()
        with self.assertRaises(RuntimeError):type(model)()
        self.assertEqual(calls,[])

    def test_startup_then_default_update_and_sampler_calls_all_use_same_bounded_model(self):
        model,clock,calls,lock,prepared=self.model();joints=np.array([.37]+[0.]*6)
        actual_native=model.kin
        model.fk(joints,no_iterations=20) # RobotBackend.run BEFORE _update
        self.assertEqual(model.ik(np.eye(4),no_iterations=20)[0],.37)
        self.assertEqual(model.last_ik_body,.37) # no implicit neutral body for warmup
        with lock:model.fk(joints) # update_head_kinematics_model default call
        model.fk(joints,no_iterations=20) # measured sampler/stop path
        self.assertEqual(len(calls),43);self.assertIs(model.kin,actual_native)
        self.assertTrue(all(values==(tuple([0.]*6),.37) for values in calls))
        self.assertFalse(model.automatic_body_yaw);model.kin.reset_forward_kinematics.assert_not_called()
        self.assertIs(type(model).fk,prepared['bounded_fk'])

    def test_permanently_upside_down_exhausts_fixed_inner_budget_once_without_perturbation(self):
        flipped=np.diag([1.,-1.,-1.,1.])
        model,clock,calls,lock,_=self.model(matrix=flipped)
        with self.assertRaises(ValueError):model.fk([.2]+[0.]*6,no_iterations=20)
        self.assertEqual(len(calls),20);self.assertEqual(set(calls),{(tuple([0.]*6),.2)})
        model.kin.inverse_kinematics.assert_not_called();model.kin.reset_forward_kinematics.assert_not_called()
        with self.assertRaises(RuntimeError):model.fk([.2]+[0.]*6)
        self.assertEqual(len(calls),20)

    def test_nonconvergence_nonfinite_and_slow_native_return_quarantine_no_retry(self):
        model,clock,calls,lock,_=self.model(residual=.02)
        with self.assertRaises(ValueError):model.fk([0.]*7,no_iterations=3)
        self.assertEqual(len(calls),3)
        with self.assertRaises(RuntimeError):model.ik(np.eye(4),body_yaw=0.)
        model,clock,calls,lock,_=self.model(matrix=np.full((4,4),float('nan')))
        with self.assertRaises(ValueError):model.fk([0.]*7,no_iterations=20)
        self.assertEqual(len(calls),1)
        model,clock,calls,lock,_=self.model(delay=.101)
        with self.assertRaises(ValueError):model.fk([0.]*7,no_iterations=20)
        self.assertEqual(len(calls),1) # elapsed guard does not pretend to preempt this call

    def test_shared_lock_contention_rejects_before_native_and_does_not_poison_model(self):
        model,clock,calls,lock,_=self.model();held=threading.Event();release=threading.Event()
        def other():
            with lock:held.set();release.wait(1)
        worker=threading.Thread(target=other);worker.start();self.assertTrue(held.wait(1))
        try:
            with self.assertRaises(RuntimeError):model.fk([0.]*7)
            self.assertEqual(calls,[]);self.assertFalse(model._finite_kinematics_failed)
        finally:release.set();worker.join(1)
        model.fk([0.]*7)

    def test_missing_or_stale_measured_body_and_invalid_iteration_budget_never_call_native(self):
        model,clock,calls,lock,_=self.model()
        with self.assertRaises(ValueError):model.ik(np.eye(4))
        for count in (0,True,21,-1):
            with self.assertRaises(ValueError):model.fk([0.]*7,no_iterations=count)
        self.assertEqual(calls,[])
        model.fk([.4]+[0.]*6);clock[0]+=.101
        with self.assertRaises(ValueError):model.ik(np.eye(4))
        self.assertEqual(len(calls),3)


class KinematicsPinTests(unittest.TestCase):
    def test_actual_source_geometry_and_native_class_artifact_all_required_before_patch(self):
        import hashlib,sys,tempfile,types
        from pathlib import Path
        from unittest.mock import patch
        from reachy_companion.autonomous import factory_head_kinematics as kin
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'pkg';(root/'kinematics').mkdir(parents=True);(root/'assets').mkdir()
            source=root/'kinematics'/'analytical.py'
            code='class Rust: pass\nclass Analytical:\n def __init__(self): raise AssertionError("constructor forbidden in verify")\n def fk(self): pass\n def ik(self): pass\n'
            source.write_text(code);assets=root/'assets'/'kinematics_data.json';assets.write_text('{}')
            module=types.ModuleType('finite_pin_fixture');module.__file__=str(source)
            with patch.dict(sys.modules,{'finite_pin_fixture':module}):
                exec(compile(code,str(source),'exec'),module.__dict__);module.ReachyMiniRustKinematics=module.Rust
                artifact=root/'native.so';artifact.write_bytes(b'fake-not-imported')
                native=types.SimpleNamespace(__file__=str(artifact),ReachyMiniRustKinematics=module.Rust)
                sha=hashlib.sha256(artifact.read_bytes()).hexdigest()
                with patch.object(kin,'ANALYTICAL_SHA256',hashlib.sha256(source.read_bytes()).hexdigest()),patch.object(kin,'ASSETS_SHA256',hashlib.sha256(assets.read_bytes()).hexdigest()):
                    kin.verify_kinematics(module.Analytical,native,sha)
                    with self.assertRaises(ValueError):kin.verify_kinematics(module.Analytical,native,'a'*64)
                    native.ReachyMiniRustKinematics=object()
                    with self.assertRaises(ValueError):kin.verify_kinematics(module.Analytical,native,sha)
                    native.ReachyMiniRustKinematics=module.Rust;assets.write_text('{"changed":true}')
                    with self.assertRaises(ValueError):kin.verify_kinematics(module.Analytical,native,sha)
                self.assertFalse(hasattr(module.Analytical,'_finite_kinematics_prepared'))


if __name__=='__main__':unittest.main()
