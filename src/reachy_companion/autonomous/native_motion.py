"""Single serial writer and finite antenna trajectories with measured hold stop.

No SDK, audio or device initialization on import. The owner must withdraw the
factory daemon and audit existing serial handles before constructing Driver.
Only the pinned synchronous controller is used, never its queued control loop.
"""
from collections import deque
import errno
import fcntl
import hashlib
import math
import os
from pathlib import Path
import select
import struct
import termios
import threading
import time

NATIVE_SHA256 = '799457a35b52171ae53ef5504c3c9b014ca699384ef1c767aa6af5e2194b7983'
FACTORY_BACKEND_SHA256 = '16d3dae8add1f30eb608de8aa9ae04d1afd31924fc7d5729bf515823f4bcdd57'
TICK = 2 * math.pi / 4096
READ_WIDTHS = {0:2, 10:1, 11:1, 20:4, 32:2, 34:2, 36:2, 38:2, 48:4, 52:4,
               63:1, 64:1, 70:1, 80:2, 82:2, 84:2, 100:2, 102:2, 104:4,
               108:4, 112:4, 116:4, 124:2, 126:2, 128:4, 132:4, 144:2, 146:1}


def crc16(data):
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x8005 if crc & 0x8000 else 0)) & 0xffff
    return crc


def read_packet(motor_id, address, length):
    if motor_id not in range(10, 19) or READ_WIDTHS.get(address) != length:
        raise ValueError('Read-only motor register allowlist')
    body = bytes([motor_id]) + struct.pack('<H', 7) + b'\x02' + struct.pack('<HH', address, length)
    packet = b'\xff\xff\xfd\x00' + body
    return packet + struct.pack('<H', crc16(packet))


def status_value(packet, motor_id, length, *, allow_alert=False):
    if (len(packet) != length + 11 or packet[:4] != b'\xff\xff\xfd\x00'
            or packet[4] != motor_id or struct.unpack('<H', packet[5:7])[0] != length + 4
            or packet[7] != 0x55 or packet[8] not in ((0, 0x80) if allow_alert else (0,))
            or crc16(packet[:-2]) != int.from_bytes(packet[-2:], 'little')):
        raise RuntimeError('Motor status unknown, error or malformed: '+packet[:32].hex())
    return int.from_bytes(packet[9:-2], 'little')


class Driver:
    """One synchronous controller; raw register reads reuse its existing fd."""
    def __init__(self, port='/dev/ttyAMA3'):
        import reachy_mini_motor_controller as package
        import reachy_mini_motor_controller.reachy_mini_motor_controller as native
        if hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest() != NATIVE_SHA256:
            raise RuntimeError('Unaudited controller binary')
        backend = Path(native.__file__).parents[1]/'reachy_mini/daemon/backend/robot/backend.py'
        self.vendor_profile_verified = hashlib.sha256(backend.read_bytes()).hexdigest() == FACTORY_BACKEND_SHA256
        if not self.vendor_profile_verified: raise RuntimeError('Unaudited Reachy voltage profile')
        device = os.stat(port).st_rdev
        self.controller = package.ReachyMiniMotorController(port)
        descriptors = []
        for path in Path('/proc/self/fd').iterdir():
            try:
                if os.stat(path).st_rdev == device: descriptors.append(int(path.name))
            except FileNotFoundError: pass
        if len(descriptors) != 1: raise RuntimeError('Controller descriptor ownership unknown')
        self.fd = descriptors[0]
        fcntl.ioctl(self.fd, termios.TIOCEXCL)
        # Probe only open(), without constructing another controller or writer.
        try:
            other = os.open(port, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
        except OSError as exc:
            if exc.errno != errno.EBUSY: raise
        else:
            os.close(other)
            raise RuntimeError('Kernel serial fence not enforced')
        self.exclusive = True

    def register(self, motor_id, address, length=1, *, allow_alert=False):
        flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        try:
            os.set_blocking(self.fd, False)
            return self._register(motor_id, address, length, allow_alert)
        finally:
            fcntl.fcntl(self.fd, fcntl.F_SETFL, flags)

    def _register(self, motor_id, address, length, allow_alert):
        packet = read_packet(motor_id, address, length)
        if select.select([self.fd], [], [], 0)[0]:
            raise RuntimeError('Unexpected pending serial response')
        if os.write(self.fd, packet) != len(packet): raise RuntimeError('Partial serial request')
        end = time.monotonic() + .03
        response = bytearray()
        while len(response) < length + 11:
            remaining = end - time.monotonic()
            if remaining <= 0 or not select.select([self.fd], [], [], remaining)[0]:
                raise TimeoutError('Fresh motor register read timed out')
            response.extend(os.read(self.fd, length + 11 - len(response)))
        return status_value(bytes(response), motor_id, length, allow_alert=allow_alert)

    def prepare(self, *, for_motion=True):
        # Pinned wireless vendor profile: M288 head/body, M077 antennas.
        self.models = [self.register(i, 0, 2, allow_alert=True) for i in range(10, 19)]
        self.health = [self.register(i, 70, allow_alert=True) for i in range(10, 19)]
        self.voltage_decivolts = [self.register(i, 144, 2, allow_alert=True) for i in range(10, 19)]
        self.torque = [self.register(i, 64, allow_alert=True) for i in range(10, 19)]
        self.temperature = self.register(17, 146, allow_alert=True)
        self.antenna_voltage_limits = [self.register(17, address, 2, allow_alert=True) for address in (34, 32)]
        self.antenna_shutdown = self.register(17, 63, allow_alert=True)
        self.antenna_controls = {str(address): self.register(17, address, READ_WIDTHS[address], allow_alert=True)
                                for address in (10, 20, 36, 38, 48, 52, 80, 82, 84, 100, 102, 104, 108, 112, 116, 132)}
        expected_controls={10:0,20:0,36:885,38:1750,48:4095,52:0,80:0,82:0,84:200,
                           100:885,102:1750,104:1620,108:0,112:0}
        if self.models != [1200]*7+[1190]*2 or any(self.torque):
            raise RuntimeError('Finite fixture requires verified supported motors and torque off')
        # Installed SDK1.11.0 read_hardware_errors deliberately filters only
        # Input Voltage Error up to7.8V. Its exact file hash is pinned above;
        # this narrower finite wireless fixture requires the measured factory
        # shutdown52/limits35..70 and6.8..7.6V. This is not a generic XL330
        # exception, nor a reboot or change to protection registers.
        if for_motion and (not self.vendor_profile_verified
                           or self.antenna_shutdown != 52 or self.antenna_voltage_limits != [35, 70]
                           or any(self.antenna_controls[str(key)]!=value for key,value in expected_controls.items())
                           or any(value not in (0, 1) for value in self.health)
                           or any(not 68 <= value <= 76 for value in self.voltage_decivolts)
                           or not 0 <= self.temperature < 45):
            raise RuntimeError('Wireless vendor voltage/health/temperature envelope failed')
        self.motion_profile_admitted = for_motion
        self.control_samples = deque(maxlen=32)
        if self.register(17, 11, allow_alert=True) != 3: raise RuntimeError('Antenna is not in position mode')
        first_stamp, first = self.positions()
        time.sleep(.2)
        stamp, pose = self.positions()
        if max(abs(a-b) for a, b in zip(first, pose)) > TICK * 1.1:
            raise RuntimeError('Initial pose is not stationary')
        return stamp, pose

    def positions(self):
        started = time.monotonic()
        if getattr(self, 'motion_profile_admitted', False):
            if (self.register(17, 70, allow_alert=True) not in (0, 1)
                    or not 68 <= self.register(17, 144, 2, allow_alert=True) <= 76
                    or self.register(17, 146, allow_alert=True) >= 45):
                raise RuntimeError('Active motor left vendor health envelope')
        value = list(self.controller.read_all_positions())
        if getattr(self, 'motion_profile_admitted', False):
            self.control_samples.append(dict(stamp=time.monotonic(),
                goal_ticks=self.register(17,116,4,allow_alert=True),
                present_ticks=self.register(17,132,4,allow_alert=True),
                torque=self.register(17,64,allow_alert=True),
                pwm_raw=self.register(17,124,2,allow_alert=True),
                current_raw=self.register(17,126,2,allow_alert=True)))
        ended = time.monotonic()
        if ended-started > .1 or len(value) != 9 or any(not math.isfinite(v) for v in value):
            raise RuntimeError('Position feedback not fresh or complete')
        return ended, value

    def pin_enable(self, positions):
        self.controller.set_antennas_positions(positions[-2:])
        self.controller.enable_torque_on_ids([17])
        if self.register(17, 64, allow_alert=True) != 1: raise RuntimeError('Motor enable not acknowledged')

    def target(self, antennas): self.controller.set_antennas_positions(antennas)

    def release(self):
        self.controller.disable_torque_on_ids([17])
        if self.register(17, 64, allow_alert=True) != 0: raise RuntimeError('Antenna release unknown')

    def close(self):
        # Rust synchronous controller has no thread or queue; dropping releases fd.
        self.controller = None


class HoldActor:
    """Guard callbacks only touch RAM; worker owns every serial operation.

    Stop waits at most300ms for a measured hold receipt. Unknown completion is
    returned as False, never as an enqueue acknowledgement or torque-off flag.
    """
    def __init__(self, driver, *, period=.02):
        self.driver, self.period = driver, period
        self.mutex = threading.Lock()
        self.plan = None
        self.deadline = 0
        self.withdraw = threading.Event()
        self.stopped = threading.Event()
        self.done = threading.Event()
        self.receipt = None
        self.stop_reason = None
        self.error = None
        self.enabled = False
        self.samples = deque(maxlen=256)
        self.target_writes = 0
        self.origin_time, self.origin = driver.prepare()
        self.thread = threading.Thread(target=self.run, name='single-motor-writer', daemon=True)
        self.thread.start()

    def enqueue(self, offset, duration, deadline):
        if (type(offset) not in (float, int) or not math.isfinite(offset) or abs(offset) > math.radians(2)
                or type(duration) not in (float, int) or not .4 <= duration <= 2):
            raise ValueError('Finite antenna trajectory exceeds bounds')
        if not -math.pi <= self.origin[-2]+offset <= math.pi-TICK:
            raise ValueError('Absolute antenna goal exceeds verified position-mode limits')
        with self.mutex:
            if self.plan or self.withdraw.is_set() or self.error or time.monotonic() >= deadline:
                return False
            self.deadline = deadline
            self.plan = (time.monotonic(), offset, duration)
            return True

    def heartbeat(self, deadline):
        with self.mutex:
            if self.withdraw.is_set() or time.monotonic() >= self.deadline:
                raise RuntimeError('Actor deadline cannot be revived')
            self.deadline = deadline

    def stop(self):
        self.withdraw.set()
        return self.stopped.wait(.3) and self.receipt is not None and self.receipt['verified'] is True

    def hold(self):
        started = time.monotonic()
        stamp, pose = self.driver.positions()
        self.driver.target(pose[-2:])
        self.target_writes += 1
        hold_written = time.monotonic()
        window = deque()
        while time.monotonic()-started < .28:
            stamp, current = self.driver.positions()
            window.append((stamp, current))
            self.samples.append((stamp, current))
            if stamp-window[0][0] >= .2:
                ranges = [max(item[1][i] for item in window)-min(item[1][i] for item in window) for i in range(9)]
                velocity = max(abs(current[i]-window[0][1][i])/(stamp-window[0][0]) for i in range(9))
                verified = max(ranges) <= TICK * 1.1 and velocity <= .02
                if verified:
                    return dict(verified=True, profile='hold_current_pose', started=started,
                                hold_written=hold_written, completed=time.monotonic(),
                                max_range_radians=max(ranges), max_velocity_radians_s=velocity,
                                samples=len(window), trajectory_updates_after_hold=0)
                window.popleft()
            self.done.wait(self.period)
        return dict(verified=False, profile='hold_current_pose', started=started,
                    completed=time.monotonic(), reason='feedback_not_settled_before_deadline')

    def run(self):
        try:
            while not self.done.is_set():
                with self.mutex: plan, deadline = self.plan, self.deadline
                if self.withdraw.is_set() or (plan and (time.monotonic() >= deadline
                                                       or time.monotonic() >= plan[0] + plan[2])):
                    self.stop_reason = ('owner_revoke' if self.withdraw.is_set() else
                                        'lease_expired' if time.monotonic() >= deadline else 'trajectory_complete')
                    self.withdraw.set()
                    self.receipt = self.hold()
                    self.stopped.set()
                    return
                if plan:
                    if not self.enabled:
                        _, pose = self.driver.positions()
                        if self.withdraw.is_set() or time.monotonic() >= deadline: continue
                        self.enabled = True
                        self.driver.pin_enable(pose)
                    started, offset, duration = plan
                    # Same bounded400ms ramp for every fixture, then retain the
                    # final target only until the finite plan/lease ends.
                    fraction = min(1, max(0, (time.monotonic()-started)/min(duration,.4)))
                    antennas = [self.origin[-2] + offset*fraction, self.origin[-1]]
                    if self.withdraw.is_set() or time.monotonic() >= deadline: continue
                    self.driver.target(antennas)
                    self.target_writes += 1
                    self.samples.append(self.driver.positions())
                self.done.wait(self.period)
        except Exception as exc:
            self.error = type(exc).__name__
            self.withdraw.set()
            # Best effort hold, but an I/O exception remains execution unknown.
            try: self.hold()
            except Exception: pass
            self.stopped.set()

    def close(self, *, close_driver=True):
        known = self.stop()
        self.done.set()
        self.thread.join(.5)
        if self.thread.is_alive(): raise RuntimeError('Native writer not reaped')
        if self.enabled: self.driver.release()
        if close_driver: self.driver.close()
        return known
