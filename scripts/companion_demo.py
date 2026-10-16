"""Mac launch path: existing SSH transport, independent device watch, Hub demo."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[1]


def need(value):
    if not value:
        raise RuntimeError('Companion demo launch check failed')


def robot_call(config, known_hosts, payload):
    """Reuse the reviewed foreground mux; no reconnect after losing its socket."""
    robot, hub = (config['deployment'][k] for k in ('robot', 'hub'))
    destination = robot['user'] + '@' + robot['host']
    source = (ROOT / 'deploy/autonomous/demo_watch.py').read_bytes()
    packed = base64.b64encode(zlib.compress(source)).decode()
    vision_source=(ROOT/'deploy/autonomous/demo_vision.py').read_bytes() if payload.get('action')=='vision' else b''
    vision_packed=base64.b64encode(zlib.compress(vision_source)).decode()
    bootstrap = ("import base64,zlib;raw=zlib.decompress(base64.b64decode(" + repr(packed) + "));"
        "vision=zlib.decompress(base64.b64decode("+repr(vision_packed)+"));"
        "exec(compile(raw,'<companion-demo-watch>','exec'),{'__name__':'__main__','__file__':'<companion-demo-watch>','SOURCE':raw,'VISION_SOURCE':vision})")
    remote = shlex.join(['sudo', '-n', '/venvs/mini_daemon/bin/python', '-I', '-B', '-c', bootstrap,
        '--production-root', robot['root']])
    need(len(remote.encode()) < 32768)
    transfer_seconds=50 if payload.get('action')=='vision' else 23
    until = time.monotonic() + (60 if payload.get('action')=='vision' else 35)
    with tempfile.TemporaryDirectory(prefix='reachy-demo-mux-') as directory:
        os.chmod(directory, 0o700)
        control = str(Path(directory) / 'mux')
        setup = [sys.executable, str(ROOT / 'scripts/factory_ssh.py'), 'ssh', '-M', '-N', '-S', control,
            '-oControlPersist=no', '-oForkAfterAuthentication=no', '-J', hub['user'] + '@' + hub['host'],
            '-oConnectTimeout=5', '-oConnectionAttempts=1', '-oServerAliveInterval=2', '-oServerAliveCountMax=2',
            '-oStrictHostKeyChecking=yes', '-oUserKnownHostsFile=' + str(known_hosts), destination]
        base = ['ssh', '-S', control, '-oControlMaster=no', '-oBatchMode=yes', '-oProxyCommand=false',
            '-oConnectTimeout=3', destination]
        master = subprocess.Popen(setup, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        close_known = False
        transfer_validated = False
        forced_reap = False
        try:
            while time.monotonic() < until:
                need(master.poll() is None)
                try:
                    info = Path(control).lstat()
                    need(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o022)
                    break
                except FileNotFoundError:
                    time.sleep(.05)
            else:
                raise TimeoutError('Owned SSH mux unavailable')
            check = subprocess.run(['ssh', '-S', control, '-O', 'check', destination], capture_output=True, timeout=3)
            need(check.returncode == 0 and master.poll() is None)
            value = subprocess.run(base + [remote], input=json.dumps(payload).encode(), capture_output=True,
                timeout=min(transfer_seconds, max(.1, until - time.monotonic())))
            need(value.returncode == 0 and len(value.stdout) <= 16384)
            answer = json.loads(value.stdout)
            need(type(answer) is dict)
            transfer_validated = True
            return answer
        finally:
            try:
                closed = subprocess.run(['ssh', '-S', control, '-O', 'exit', destination], capture_output=True, timeout=2)
                close_known = closed.returncode == 0
            except (OSError, subprocess.TimeoutExpired): pass
            try: master.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                forced_reap = True
                master.terminate()
                try: master.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    master.kill()
                    master.communicate(timeout=1)
            # The existing PTY helper can report SSH 255 after OUR successful
            # mux exit. Accept it only after validated transfer + explicit close
            # + natural helper EOF/reaping, never after a forced or lost close.
            need(transfer_validated and close_known and not forced_reap and master.returncode in (0, 255))


def validate_ready(value, owner):
    need(type(value) is dict and set(value) == {'kind', 'ready', 'run_id', 'plan_sha256', 'owner_sha256', 'operator_binding'})
    need(value['kind'] == 'companion-demo-watch' and value['ready'] is True
         and value['owner_sha256'] == hashlib.sha256(owner.encode()).hexdigest())
    for key, size in (('run_id', 32), ('plan_sha256', 64)):
        need(type(value[key]) is str and len(value[key]) == size and all(c in '0123456789abcdef' for c in value[key]))
    binding = value['operator_binding']
    need(type(binding) is dict and set(binding) == {'agent_boot_id', 'microphone_epoch', 'policy_epoch'})
    need(type(binding['agent_boot_id']) is str and 1 <= len(binding['agent_boot_id']) <= 256
         and all(type(binding[k]) is int and 0 <= binding[k] < 2**63 for k in ('microphone_epoch', 'policy_epoch')))
    return value


def hub_command(config):
    hub = config['deployment']['hub']
    pin = hashlib.sha256((ROOT / 'src/reachy_companion/client.py').read_bytes()).hexdigest()
    code = ("import hashlib,json,sys;from pathlib import Path;root=Path(sys.argv[1]);"
        "source=root/'src/reachy_companion/client.py';"
        "assert hashlib.sha256(source.read_bytes()).hexdigest()==sys.argv[2],'Client revision changed';"
        "sys.path.insert(0,str(root/'src'));from reachy_companion.config import Config;"
        "from reachy_companion.client import demo;raw=sys.stdin.buffer.read(16385);assert len(raw)<=16384;p=json.loads(raw);"
        "assert (set(p)-{'prime_paused'}) in ({'owner','operator_binding','turns','seconds'},{'owner','operator_binding','turns','seconds','vision_text','vision_deadline'});"
        "assert type(p.get('prime_paused',False)) is bool;"
        "sys.exit(demo(Config(root/'config.local.json'),owner_id=p['owner'],operator_binding=p['operator_binding'],"
        "turns=p['turns'],seconds=p['seconds'],vision_text=p.get('vision_text'),vision_deadline=p.get('vision_deadline'),prime_paused=p.get('prime_paused',False)))")
    remote = shlex.join(['/usr/bin/python3', '-I', '-B', '-c', code, hub['root'], pin])
    return ['ssh', '-oBatchMode=yes', '-oStrictHostKeyChecking=yes', '-oConnectTimeout=5',
        hub['user'] + '@' + hub['host'], remote]


def launch(config, known_hosts, *, turns, seconds, vision=None, prime_paused=False):
    need(type(turns) is int and 1 <= turns <= 3 and type(seconds) is int and 10 <= seconds <= 300)
    need(type(prime_paused) is bool)
    need(known_hosts.is_file())
    need(vision is None or (type(vision) is str and 1<=len(vision)<=256 and seconds>=60))
    started=time.monotonic()
    owner = str(uuid.uuid4())
    ready = None
    code = 1
    cleanup = None
    try:
        ready = validate_ready(robot_call(config, known_hosts, dict(action='arm', owner=owner, seconds=seconds)), owner)
        print('Independent device watch ready.' if vision is not None else 'Independent device watch ready. Starting live demo on Hub.', flush=True)
        packet = dict(owner=owner, operator_binding=ready['operator_binding'], turns=turns, seconds=seconds)
        if prime_paused:packet['prime_paused']=True
        if vision is not None:
            print('Taking one snapshot for a spoken reply. This command does not listen for an STT trigger.',flush=True)
            snapshot=robot_call(config,known_hosts,dict(action='vision',owner=owner,run_id=ready['run_id'],
                plan_sha256=ready['plan_sha256'],question=vision))
            need(type(snapshot) is dict and set(snapshot)=={'kind','final_text','expires_at_monotonic','frame'}
                 and snapshot['kind']=='companion-vision-snapshot')
            remaining=int(seconds-(time.monotonic()-started));need(remaining>=10)
            packet.update(vision_text=snapshot['final_text'],vision_deadline=snapshot['expires_at_monotonic'],seconds=remaining)
            snapshot=None
        child = subprocess.run(hub_command(config), input=json.dumps(packet).encode(), timeout=packet['seconds'] + 10)
        code = child.returncode
    except KeyboardInterrupt:
        code = 130
    except Exception:
        print('Demo launch failed; no automatic grant retry.', file=sys.stderr, flush=True)
    finally:
        if ready is not None:
            try:
                report = robot_call(config, known_hosts, dict(action='finish', owner=owner,
                    run_id=ready['run_id'], plan_sha256=ready['plan_sha256']))
                need(set(report) == {'kind', 'cleanup'} and report['kind'] == 'companion-demo-cleanup')
                cleanup = report['cleanup']
            except Exception:
                print('Watch cleanup UNKNOWN; independent device deadline remains active.', file=sys.stderr, flush=True)
    verified = (type(cleanup) is dict and cleanup.get('final_OFF') is True
        and cleanup.get('admission_retired') is True
        and cleanup.get('factory_running_empty') is True and cleanup.get('aplay_absent') is True
        and type(cleanup.get('volume_percent')) is int and 1 <= cleanup['volume_percent'] <= 100
        and cleanup.get('volume_preserved') is True and cleanup.get('stock_unknown') is False)
    print(json.dumps(dict(kind='companion-demo-terminal', child_returncode=code,
        cleanup_verified=verified, physical_motion_verified=False, context_verified=False)), flush=True)
    return code if verified else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'config.local.json'))
    parser.add_argument('--robot-known-hosts', type=Path, default=Path.home() / '.ssh/known_hosts')
    parser.add_argument('--turns', type=int, default=3)
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--vision',nargs='?',const='Что перед тобой?',help='One explicit snapshot reply; optional question (not an STT trigger)')
    parser.add_argument('--prime-paused',action='store_true',help='First owned microphone ON grant uses listen=false; guarded controller resumes')
    args = parser.parse_args()
    from reachy_companion.config import Config
    return launch(Config(args.config, require_token=False), args.robot_known_hosts.expanduser(), turns=args.turns, seconds=args.seconds,vision=args.vision,prime_paused=args.prime_paused)


if __name__ == '__main__':
    sys.exit(main())
