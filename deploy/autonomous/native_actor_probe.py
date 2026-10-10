"""Finite single-writer transition; private receipt, muted Agent, factory rollback.

Run supervisor as root; the hardware child runs as pollen and uses kernel
exclusive serial ownership. Default is read-only. --motor-test admits exactly
one bounded antenna move after native baseline/hold gates, never audio/head.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
from urllib.request import Request, build_opener, ProxyHandler

FACTORY = 'reachy-mini-daemon.service'
PORT = Path('/dev/ttyAMA3')
MARKER = Path('/run/reachy-native-finite-owner.flag')
DROPIN = Path('/run/systemd/system/reachy-mini-daemon.service.d/90-reachy-native-finite-fence.conf')
CONDITION = '[Unit]\nConditionPathExists=!/run/reachy-native-finite-owner.flag\n'


def operator(root, endpoint='/status'):
    if endpoint not in ('/status','/operator'): raise ValueError('Operator endpoint')
    config = json.loads((root/'config.local.json').read_text())
    token = Path(config['paths']['token_file'])
    if not token.is_absolute(): token = root/token
    from urllib.parse import urlsplit
    port = urlsplit(config['network']['agent_url']).port
    request = Request(f'http://127.0.0.1:{port}{endpoint}', headers={'Authorization': 'Bearer '+token.read_text().strip()})
    with build_opener(ProxyHandler({})).open(request, timeout=.3) as response:
        raw = response.read(65537)
    if len(raw) > 65536: raise RuntimeError('Operator receipt bound')
    value = json.loads(raw)
    if (value.get('microphone_enabled') is not False or value.get('capture_active') is not False
            or value.get('phase') != 'paused' or value.get('microphone_state_error')):
        raise RuntimeError('Actual operator mute not verified')
    return {key: value.get(key) for key in ('agent_boot_id', 'microphone_epoch', 'microphone_enabled', 'capture_active', 'phase')}


def serial_owners():
    device = PORT.stat().st_rdev
    owners = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        for path in (proc/'fd').glob('*'):
            try:
                if path.stat().st_rdev == device: owners.append(int(proc.name))
            except (FileNotFoundError, ProcessLookupError): pass
    return sorted(set(owners))


def child(args):
    if getattr(args,'runtime_service',False):
        from native_runtime_service import serve
        return serve(args)
    from reachy_companion.autonomous.native_motion import Driver, HoldActor, TICK
    from reachy_companion.autonomous.actuator_guard import ActuatorGuard
    from reachy_companion.autonomous.contracts import Authority
    import math
    report = dict(mode='finite_native_antenna_hold', audio_commands=0, head_commands=0,
                  accepted=False, motor_test_requested=args.motor_test)
    before = operator(args.production_root)
    driver = actor = guard = None
    try:
        driver = Driver()
        if args.motor_test:
            actor = HoldActor(driver)
            origin = actor.origin
        else:
            _, origin = driver.prepare(for_motion=False)
        report.update(kernel_exclusive=driver.exclusive, models=driver.models,
                      initial_torque=driver.torque, initial_pose=origin,
                      hardware_error_status=driver.health, voltage_decivolts=driver.voltage_decivolts,
                      antenna_voltage_limits=driver.antenna_voltage_limits,
                      antenna_shutdown=driver.antenna_shutdown,
                      antenna_controls=driver.antenna_controls,
                      vendor_profile_verified=driver.vendor_profile_verified)
        if args.motor_test:
            # Durable recovery permission precedes the only possible torque-on.
            # No intent means recovery must not alter preexisting motor state.
            with args.output.with_suffix('.intent.json').open('x') as output:
                json.dump({'baseline_torque': driver.torque, 'enabled_ids': [17]}, output)
                output.flush()
                os.fsync(output.fileno())
            guard = ActuatorGuard(args.output.with_suffix('.guard'), actor.stop, ttl=.15, poll=.005)
            lease = guard.arm(Authority('finite-local-owner', 'no-model', robot_boot_id=guard.robot_boot_id,
                                       operator_epoch=before['microphone_epoch']),
                              microphone_enabled=False, motor_enabled=True, channel='motion',
                              quiet=False, privacy_all=False, fence_attested=True)
            if operator(args.production_root) != before: raise RuntimeError('Operator changed before dispatch')
            guard.dispatch(lease, 'single-antenna-fixture',
                           lambda: actor.enqueue(math.radians(2), 1, guard.deadline), channel='motion')
            start = time.monotonic()
            sequence = 0
            while time.monotonic()-start < .65:
                if operator(args.production_root) != before:
                    guard.revoke()
                    raise RuntimeError('Operator changed during motion')
                sequence += 1
                guard.heartbeat(lease, sequence)
                actor.heartbeat(guard.deadline)
                report['last_heartbeat'] = time.monotonic()
                time.sleep(.05)
            if not actor.stopped.wait(.55): raise RuntimeError('Verified hold deadline exceeded')
            report['hold'] = actor.receipt
            report['stop_reason'] = actor.stop_reason
            report['heartbeat_to_verified_s'] = actor.receipt['completed']-report['last_heartbeat'] if actor.receipt else None
            report['target_writes'] = actor.target_writes
            report['control_samples'] = list(driver.control_samples)
            samples = list(actor.samples)
            report['max_antenna_displacement_radians'] = max(abs(pose[7]-actor.origin[7]) for _, pose in samples)
            report['accepted'] = (actor.receipt is not None and actor.receipt['verified'] is True
                and report['heartbeat_to_verified_s'] <= .5 and not actor.error
                and 3*TICK <= report['max_antenna_displacement_radians'] <= math.radians(2.3))
        else:
            report['mode'] = 'native_register_readiness_only'
            report['accepted'] = True
            report['motor_writes'] = 0
    except Exception as exc:
        report['error'] = type(exc).__name__+': '+str(exc)[:256]
        if driver:
            report['readiness_before_error'] = {'models': getattr(driver, 'models', None),
                                               'torque': getattr(driver, 'torque', None),
                                               'health': getattr(driver, 'health', None),
                                               'voltage_decivolts': getattr(driver, 'voltage_decivolts', None),
                                               'kernel_exclusive': getattr(driver, 'exclusive', False)}
    finally:
        try:
            if guard: guard.close()
            if actor:
                report['writer_reaped_and_hold_known'] = actor.close()
                # Driver fd is closed; a separate recovery handles release auditing.
            elif driver: driver.close()
        except Exception as exc:
            report['cleanup_error'] = type(exc).__name__
            report['accepted'] = False
        report['operator_after'] = operator(args.production_root)
        report['operator_unchanged'] = report['operator_after'] == before
        report['accepted'] = report['accepted'] and report['operator_unchanged']
        with args.output.open('x') as output: json.dump(report, output, indent=2)
    return 0 if report['accepted'] else 2


def recover(args):
    if args.intent is None: raise RuntimeError('Explicit recovery intent path required')
    if not args.intent.exists():
        print(json.dumps({'hardware_never_admitted': True}))
        return
    intent = json.loads(args.intent.read_text())
    if intent != {'baseline_torque': [0]*9, 'enabled_ids': [17]}:
        raise RuntimeError('Recovery intent does not attest a torque-off baseline')
    # Recovery is independent of editable-package import resolution.
    import importlib.util
    path = Path(__file__).resolve().parent/'src/reachy_companion/autonomous/native_motion.py'
    spec = importlib.util.spec_from_file_location('recovery_driver', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    Driver = module.Driver
    driver = Driver()
    try:
        driver.release()
        values = [driver.register(i, 64, allow_alert=True) for i in range(10, 19)]
        if any(values): raise RuntimeError('Native release rollback did not restore torque-off baseline')
        print(json.dumps({'release_verified': True, 'torque': values}))
    finally: driver.close()


def supervisor(args):
    if os.geteuid() != 0: raise RuntimeError('Root supervisor required to audit all serial owners')
    before = operator(args.production_root)
    config_hash = hashlib.sha256((args.production_root/'config.local.json').read_bytes()).hexdigest()
    def run(*command, timeout=8):
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    status = run('systemctl', 'is-active', FACTORY).stdout.strip()
    if status != 'active': raise RuntimeError('Factory must initially be active')
    if 'masked' in run('systemctl', 'show', FACTORY, '--property=UnitFileState', '--value').stdout:
        raise RuntimeError('Preexisting factory mask must be preserved')
    def native(path):
        with build_opener(ProxyHandler({})).open('http://127.0.0.1:8000/api/'+path, timeout=1) as response:
            return json.loads(response.read(65536))
    daemon = native('daemon/status')
    if (native('motors/status').get('mode') != 'disabled' or native('move/running')
            or native('daemon/robot-app-lock-status').get('state') != 'free'
            or daemon.get('state') != 'running' or not (daemon.get('backend_status') or {}).get('ready')):
        raise RuntimeError('Factory disabled/idle/readiness gate failed')
    # Refuse unknown existing serial writers. The launcher MainPID is a shell;
    # serial PID must belong to exactly this systemd control group.
    owners = serial_owners()
    if len(owners) != 1 or FACTORY not in Path(f'/proc/{owners[0]}/cgroup').read_text():
        raise RuntimeError('Initial native serial ownership not factory-exclusive')
    if args.output.exists(): raise FileExistsError(args.output)
    report = dict(mode='finite_single_writer_transition', operator_before=before, initial_owners=owners,
                  accepted=False, factory_restored=False)
    leaf = args.output.with_suffix('.child.json')
    intent = leaf.with_suffix('.intent.json')
    if intent.exists(): raise FileExistsError(intent)
    package_root = Path(__file__).resolve().parent/'src'
    base = ['runuser', '-u', 'pollen', '--', 'env', 'PYTHONPATH='+str(package_root),
            '/venvs/mini_daemon/bin/python', str(Path(__file__).resolve()),
            '--production-root', str(args.production_root), '--output', str(leaf)]
    if getattr(args,'runtime_service',False):
        base[5:5]=['GST_PLUGIN_PATH=/opt/gst-plugins-rs/lib/aarch64-linux-gnu/:/usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/',
                   'LD_LIBRARY_PATH=/usr/local/lib/aarch64-linux-gnu/',
                   'LIBCAMERA_IPA_MODULE_PATH=/usr/local/lib/aarch64-linux-gnu/libcamera/ipa',
                   'LIBCAMERA_IPA_CONFIG_PATH=/usr/local/share/libcamera/ipa','MALLOC_ARENA_MAX=2']
        base+=['--runtime-service']
    if getattr(args,'acknowledge_recovered_stop',False):base+=['--acknowledge-recovered-stop']
    if getattr(args,'camera_policy',None):base+=['--camera-policy',str(args.camera_policy)]
    # Independent systemd recovery handles supervisor loss. It kills only the
    # isolated child unit before opening serial, verifies release, then restores.
    rollback = Path(__file__).with_name('native_actor_rollback.sh')
    if not rollback.is_file(): raise RuntimeError('Independent rollback script required')
    expected = package_root/'reachy_companion/autonomous/native_motion.py'
    # No constructor/device access. Verify actual child imports before stop.
    code = ('from pathlib import Path; import reachy_companion.autonomous.native_motion as m; '
            f'assert Path(m.__file__).resolve()==Path({str(expected)!r}); print("isolated_import_verified")')
    run('runuser', '-u', 'pollen', '--', 'env', 'PYTHONPATH='+str(package_root),
        '/venvs/mini_daemon/bin/python', '-c', code)
    run('systemd-run', '--unit=reachy-native-import-preflight', '--collect', '--wait',
        '--property=RuntimeMaxSec=5s', *base, '--import-check')
    if MARKER.exists() or DROPIN.exists(): raise RuntimeError('Another native transition already owns the fence')
    import uuid
    owner = str(uuid.uuid4())
    with MARKER.open('x') as output: output.write(owner)
    failure_done=threading.Event();failure_thread=None
    try:
        # Schedule recovery before the condition/reload/stop transition. If
        # drop-in creation fails, the no-intent recovery only restores service.
        run('systemd-run', '--unit=reachy-native-fence-rollback', '--collect', '--on-active=30s',
            '/bin/bash', str(rollback), str(Path(__file__).resolve()), str(args.production_root), owner, str(intent))
        DROPIN.parent.mkdir(parents=True, exist_ok=True)
        with DROPIN.open('x') as output: output.write(CONDITION)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'stop', FACTORY, timeout=12)
        if serial_owners(): raise RuntimeError('Serial port did not become owner-free')
        run('systemctl', 'start', FACTORY)
        if run('systemctl', 'show', FACTORY, '--property=ConditionResult', '--value').stdout.strip() != 'no':
            raise RuntimeError('Factory restart fence was not enforced')
        if serial_owners(): raise RuntimeError('Factory condition fence admitted another writer')
        if operator(args.production_root) != before: raise RuntimeError('Operator changed during transition')
        command = base + ['--child'] + (['--motor-test'] if args.motor_test else [])
        if getattr(args,'inject_owner_failure',False):
            def inject():
                config=json.loads((args.production_root/'config.local.json').read_text())
                token=Path(config['paths']['token_file'])
                if not token.is_absolute():token=args.production_root/token
                deadline=time.monotonic()+10
                while not failure_done.wait(.05) and time.monotonic()<deadline:
                    try:
                        request=Request('http://127.0.0.1:8775/status',headers={'Authorization':'Bearer '+token.read_text().strip()})
                        with build_opener(ProxyHandler({})).open(request,timeout=.3) as response:
                            state=json.loads(response.read(16384))['motion_actor']
                        pid=state['writer_pid']
                        if (state['leased'] and state['max_displacement_radians']>=3*2*3.141592653589793/4096
                                and MARKER.read_text()==owner
                                and 'reachy-native-finite-actor.service' in Path(f'/proc/{pid}/cgroup').read_text()):
                            run('systemctl','kill','--signal=SIGKILL','reachy-native-finite-actor.service',timeout=2)
                            report['injected_owner_failure']=dict(writer_pid=pid,displacement_radians=state['max_displacement_radians'])
                            return
                    except Exception:pass
            failure_thread=threading.Thread(target=inject,daemon=True);failure_thread.start()
        # Unit has a separate hard lifetime; no per-task Arc mount or second writer.
        run('systemd-run', '--unit=reachy-native-finite-actor', '--collect', '--wait',
            '--property=RuntimeMaxSec=12s', '--property=TimeoutStopSec=1s',
            *command, timeout=15)
        report['child'] = json.loads(leaf.read_text())
        report['accepted'] = report['child']['accepted']
    except Exception as exc:
        report['error'] = type(exc).__name__
        if leaf.exists(): report['child'] = json.loads(leaf.read_text())
    finally:
        failure_done.set()
        if failure_thread:failure_thread.join(1)
        try:
            # Rollback performs stop/release/unmask/start in that order.
            recovery = run('/bin/bash', str(rollback), str(Path(__file__).resolve()),
                           str(args.production_root), owner, str(intent), timeout=15)
            report['rollback'] = recovery.stdout.strip()
            report['factory_restored'] = run('systemctl', 'is-active', FACTORY).stdout.strip() == 'active'
            run('systemctl', 'stop', 'reachy-native-fence-rollback.timer')
            deadline = time.monotonic()+15
            while time.monotonic() < deadline:
                try:
                    state = native('daemon/status')
                    if ((state.get('backend_status') or {}).get('ready')
                            and native('motors/status').get('mode') == 'disabled'
                            and not native('move/running')):
                        report['native_ready_after'] = True
                        break
                except Exception: pass
                time.sleep(.25)
            if not report.get('native_ready_after'): raise RuntimeError('Factory readiness did not return')
            report['operator_after'] = operator(args.production_root)
            report['operator_unchanged'] = report['operator_after'] == before
            report['config_unchanged'] = hashlib.sha256((args.production_root/'config.local.json').read_bytes()).hexdigest() == config_hash
        except Exception as exc:
            report['recovery_error'] = type(exc).__name__
            report['accepted'] = False
        report['accepted'] = (report['accepted'] and report['factory_restored']
                             and report.get('operator_unchanged') and report.get('config_unchanged'))
        with args.output.open('x') as output: json.dump(report, output, indent=2)
        print(json.dumps(report))
    return 0 if report['accepted'] else 2


def main():
    # A previous flat shadow package beside this script precedes PYTHONPATH.
    # Pin the source root explicitly in the actual script process as well.
    sys.path.insert(0, str(Path(__file__).resolve().parent/'src'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--motor-test', action='store_true')
    parser.add_argument('--runtime-service',action='store_true')
    parser.add_argument('--inject-owner-failure',action='store_true')
    parser.add_argument('--acknowledge-recovered-stop',action='store_true')
    parser.add_argument('--camera-policy',type=Path)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--intent', type=Path)
    parser.add_argument('--import-check', action='store_true')
    args = parser.parse_args()
    if args.import_check:
        import reachy_companion.autonomous.native_motion as module
        if args.runtime_service:
            from reachy_companion.autonomous import motion_runtime,camera_relay
            import native_runtime_service
        expected = Path(__file__).resolve().parent/'src/reachy_companion/autonomous/native_motion.py'
        if Path(module.__file__).resolve() != expected: raise RuntimeError('Unit imported a different actor')
        print(json.dumps({'unit_import_verified': True, 'hardware_initializations': 0}))
        return
    if args.recover: recover(args); return
    raise SystemExit(child(args) if args.child else supervisor(args))


if __name__ == '__main__': main()
