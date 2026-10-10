import math
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

from reachy_companion.autonomous.actuator_guard import ActuatorGuard, GuardRejected
from reachy_companion.autonomous.contracts import Authority
from reachy_companion.autonomous.native_motion import Driver, HoldActor, crc16, read_packet, status_value


class FixtureDriver:
    def __init__(self, drifting=False):
        self.pose = [0.] * 9
        self.enabled = False
        self.closed = False
        self.drifting = drifting
    def prepare(self): return self.positions()
    def positions(self):
        if self.drifting: self.pose[7] += .002
        return time.monotonic(), list(self.pose)
    def pin_enable(self, pose): self.enabled = True
    def target(self, antennas): self.pose[-2:] = antennas
    def release(self): self.enabled = False
    def close(self): self.closed = True


class NativeMotionTests(unittest.TestCase):
    def test_wireless_profile_rejects_unknown_models_alerts_voltage_and_existing_torque(self):
        def fixture(model=1190, health=1, voltage=74, temperature=30, torque=0,
                    shutdown=52, vendor_verified=True):
            driver = Driver.__new__(Driver)
            driver.vendor_profile_verified = vendor_verified
            def register(motor_id, address, length=1, **kwargs):
                return {0: 1200 if motor_id < 17 else model, 70: health, 144: voltage,
                        146: temperature, 64: torque, 11: 3, 34: 35, 32: 70, 63: shutdown}.get(address,0)
            driver.register = register
            driver.positions = lambda: (time.monotonic(), [0.]*9)
            return driver
        with patch('reachy_companion.autonomous.native_motion.time.sleep'):
            self.assertEqual(fixture().prepare()[1], [0.]*9)
            for options in ({'model': 999}, {'health': 2}, {'health': 3}, {'health': 4}, {'voltage': 67},
                            {'voltage': 77}, {'temperature': 45}, {'torque': 1},
                            {'shutdown':53}, {'vendor_verified':False}):
                with self.assertRaises(RuntimeError): fixture(**options).prepare()
            diagnostic = fixture(health=4, voltage=77)
            diagnostic.prepare(for_motion=False)
            self.assertFalse(diagnostic.motion_profile_admitted)

    def test_read_only_packets_and_status_validation(self):
        self.assertEqual(crc16(bytes.fromhex('fffffd0001030001')), 0x4e19)
        packet = read_packet(17, 64, 1)
        self.assertEqual(packet[7], 2)
        for args in ((17, 116, 1), (17, 64, 4), (254, 64, 1)):
            with self.assertRaises(ValueError): read_packet(*args)
        response = bytes.fromhex('fffffd00') + bytes([17]) + struct.pack('<H', 5) + b'\x55\x00\x01'
        response += struct.pack('<H', crc16(response))
        self.assertEqual(status_value(response, 17, 1), 1)
        for broken in (response[:-1], response[:-1]+bytes([response[-1]^1]), response[:8]+b'\x01'+response[9:]):
            with self.assertRaises(RuntimeError): status_value(broken, 17, 1)
        with self.assertRaises(RuntimeError): status_value(response, 18, 1)
        alert = response[:8] + b'\x80' + response[9:-2]
        alert += struct.pack('<H', crc16(alert))
        with self.assertRaises(RuntimeError): status_value(alert, 17, 1)
        self.assertEqual(status_value(alert, 17, 1, allow_alert=True), 1)
        error = response[:8] + b'\x81' + response[9:-2]
        error += struct.pack('<H', crc16(error))
        with self.assertRaises(RuntimeError): status_value(error, 17, 1, allow_alert=True)

    def test_expired_lease_holds_without_target_replay_and_preserves_quarantine_rules(self):
        driver = FixtureDriver()
        actor = HoldActor(driver)
        with tempfile.TemporaryDirectory() as directory:
            guard = ActuatorGuard(directory, actor.stop, ttl=.1, poll=.005)
            lease = guard.arm(Authority('hub', 'pc', robot_boot_id=guard.robot_boot_id),
                              microphone_enabled=False, quiet=False, privacy_all=False,
                              fence_attested=True, channel='motion', motor_enabled=True)
            try:
                self.assertTrue(guard.dispatch(lease, 'fixture', lambda: actor.enqueue(math.radians(2), 1, guard.deadline), channel='motion'))
                self.assertTrue(actor.stopped.wait(.6))
                self.assertTrue(actor.receipt['verified'])
                self.assertEqual(actor.receipt['profile'], 'hold_current_pose')
                self.assertGreater(actor.receipt['samples'], 5)
                self.assertLess(actor.receipt['completed']-actor.receipt['started'], .3)
                count = actor.target_writes
                time.sleep(.05)
                self.assertEqual(actor.target_writes, count)
                self.assertFalse(actor.enqueue(.001, 1, time.monotonic()+1))
                with self.assertRaises(RuntimeError): actor.heartbeat(time.monotonic()+1)
                with self.assertRaises(GuardRejected): guard.dispatch(lease, 'late', lambda: True, channel='motion')
            finally:
                guard.close()
                self.assertTrue(actor.close())
        self.assertFalse(driver.enabled)
        self.assertTrue(driver.closed)

    def test_drifting_feedback_never_becomes_verified_stop(self):
        actor = HoldActor(FixtureDriver(drifting=True))
        try:
            self.assertFalse(actor.stop())
            self.assertTrue(actor.stopped.wait(.2))
            self.assertFalse(actor.receipt['verified'])
        finally: self.assertFalse(actor.close())

    def test_duration_ends_even_with_a_long_live_lease(self):
        actor = HoldActor(FixtureDriver())
        try:
            self.assertTrue(actor.enqueue(.001, .4, time.monotonic()+5))
            self.assertTrue(actor.stopped.wait(.8))
            self.assertTrue(actor.receipt['verified'])
            count = actor.target_writes
            time.sleep(.05)
            self.assertEqual(actor.target_writes, count)
        finally: actor.close()


if __name__ == '__main__': unittest.main()
