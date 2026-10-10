"""Finite local watchdog timing probe using a simulated stop sink only."""
import argparse
import json
from pathlib import Path
import tempfile
import threading
import time
from reachy_companion.autonomous.actuator_guard import ActuatorGuard, GuardRejected
from reachy_companion.autonomous.contracts import Authority


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inject-stop-delay', type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.inject_stop_delay <= 1:
        parser.error('Synthetic stop delay must be between0 and1 seconds')
    stopped = threading.Event()
    stamps = {}
    def stop():
        stamps['simulated_stop_started_s'] = time.monotonic()
        time.sleep(args.inject_stop_delay)
        stamps['simulated_stop_verified_s'] = time.monotonic()
        stopped.set()
        return True
    with tempfile.TemporaryDirectory(prefix='reachy-guard-probe-') as directory:
        guard = ActuatorGuard(directory, stop, ttl=.5, poll=.02)
        try:
            lease = guard.arm(Authority('fixture-hub', 'fixture-pc', robot_boot_id=guard.robot_boot_id),
                              microphone_enabled=True, quiet=False, privacy_all=False, fence_attested=True)
            for sequence in range(3):
                guard.heartbeat(lease, sequence)
                stamps['last_heartbeat_s'] = time.monotonic()
                time.sleep(.1)
            # No scheduler/main/heartbeat progress after this point.
            if not stopped.wait(2): raise TimeoutError('Local watchdog did not stop')
            elapsed = stamps['simulated_stop_verified_s']-stamps['last_heartbeat_s']
            try:
                guard.admit(lease, 'late')
                raise RuntimeError('Expired lease accepted')
            except GuardRejected:
                pass
            report = dict(mode='real_local_watchdog_simulated_sink', physical_commands=0,
                          injected_stop_delay_s=args.inject_stop_delay,
                          last_heartbeat_to_simulated_stop_started_s=stamps['simulated_stop_started_s']-stamps['last_heartbeat_s'],
                          last_heartbeat_to_simulated_stop_verified_s=elapsed, status=guard.status(),
                          accepted=.5 <= elapsed <= .65)
        finally: guard.close()
    with args.output.open('x', encoding='utf-8') as output: json.dump(report, output, indent=2)
    print(json.dumps(report))
    if not report['accepted']: raise SystemExit(2)


if __name__ == '__main__': main()
