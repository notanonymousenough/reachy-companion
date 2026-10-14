"""Pose conversion against actual NumPy; no imports of installed factory/native."""
import math
import unittest
try:import numpy as np
except ImportError:np=None
from reachy_companion.autonomous.factory_head_entry import pose_matrix,measured_pose

@unittest.skipIf(np is None,'NumPy required for actual rigid-pose conversion tests')
class PoseTests(unittest.TestCase):
    def test_nonneutral_pose_roundtrip_and_preserved_xyz_rpy_convention(self):
        pose=dict(x=-.0218,y=.0038,z=-.0476,roll=.0684,pitch=.5088,yaw=-.033)
        actual=measured_pose(pose_matrix(pose,np),np)
        for key in pose:self.assertAlmostEqual(actual[key],pose[key],places=12)
        turned=dict(pose,z=pose['z']+.005,yaw=pose['yaw']+math.radians(3))
        actual=measured_pose(pose_matrix(turned,np),np)
        for key in turned:self.assertAlmostEqual(actual[key],turned[key],places=12)
    def test_invalid_rotation_nonfinite_and_gimbal_lock_are_disarmed(self):
        for matrix in (np.eye(3),np.full((4,4),float('nan')),np.zeros((4,4))):
            with self.assertRaises(ValueError):measured_pose(matrix,np)
        with self.assertRaises(ValueError):measured_pose(pose_matrix(dict(x=0,y=0,z=0,roll=0,pitch=math.pi/2,yaw=0),np),np)

if __name__=='__main__':unittest.main()
