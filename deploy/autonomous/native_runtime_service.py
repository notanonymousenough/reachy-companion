"""Finite deployment harness for the reusable Agent proxy/native IPC service."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import signal
import subprocess
import threading
import time


def serve(args):
    import native_actor_probe as probe
    from reachy_companion.autonomous.native_motion import Driver
    from reachy_companion.autonomous.motion_runtime import MotionRuntime,RuntimeServer
    from reachy_companion.motion_proxy import MotionProxy
    from reachy_companion.autonomous.contracts import decode
    # Actual runtime condition, factory withdrawal and kernel fence supplement
    # the parent root's audit of every prior serial handle.
    if (not probe.MARKER.exists() or probe.MARKER.stat().st_uid!=0
            or not probe.DROPIN.exists() or probe.DROPIN.read_text()!=probe.CONDITION
            or subprocess.run(['systemctl','is-active',probe.FACTORY],capture_output=True,text=True).stdout.strip()=='active'):
        raise RuntimeError('Native deployment fence missing')
    config=json.loads((args.production_root/'config.local.json').read_text())
    token=Path(config['paths']['token_file'])
    if not token.is_absolute():token=args.production_root/token
    token=token.read_text().strip()
    # An enabled production proxy must use the independent operator route;
    # querying /status from its writer would recursively enter this IPC server.
    operator_endpoint='/operator' if config.get('guarded_motion',{}).get('enabled') is True else '/status'
    def operator():return probe.operator(args.production_root,operator_endpoint)
    profile=None
    if getattr(args,'service_config',None):
        from reachy_companion.autonomous.native_config import load
        profile=load(args.service_config)
        if not profile['enabled']:raise RuntimeError('Managed native owner disabled')
        args.camera_policy=Path(profile['camera_policy_path'])
    socket_path=Path(profile['socket_path']) if profile else args.output.with_suffix('.sock')
    directory=Path(profile['guard_directory']) if profile else args.output.parent/'native-runtime-guard'
    duration=profile['duration_s'] if profile else 9
    policy_state=None
    if profile:
        from reachy_companion.motion_policy import MotionPolicy
        policy_state=MotionPolicy(profile['policy_path'])
    driver=Driver()
    def local_policy():
        # The root-selected finite role grants only antenna17. Privacy-all is
        # independently authoritative and cannot be overridden by HTTP fields.
        private=json.loads(args.camera_policy.read_text())['privacy_all'] if args.camera_policy else False
        value=policy_state.snapshot() if policy_state else dict(motor_enabled=True,quiet=False,privacy_all=False,epoch=0)
        if private is not False:value=dict(value,privacy_all=True)
        return value
    runtime=MotionRuntime(driver,directory,operator,
                          args.output.with_suffix('.intent.json'),owner_verified=True,
                          recovery_audited=args.acknowledge_recovered_stop,policy=local_policy)
    ipc=RuntimeServer(runtime,socket_path)
    emergency=RuntimeServer(runtime,Path(str(socket_path)+'.stop'),emergency=True)
    proxy=MotionProxy(True,socket_path,operator)
    done=threading.Event()
    for kind in (signal.SIGTERM,signal.SIGINT): signal.signal(kind,lambda *_:done.set())
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,code,value):
            body=json.dumps(value,allow_nan=False).encode();self.send_response(code)
            self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except OSError:pass
        def auth(self):return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
        def do_GET(self):
            if not self.auth():self.reply(401,{});return
            if self.path=='/operator':self.reply(200,dict(**operator(),motion_policy=local_policy()))
            elif self.path=='/status':self.reply(200,dict(motion_actor=proxy.status(),motion_policy=local_policy(),**operator()))
            else:self.reply(404,{})
        def do_POST(self):
            if not self.auth():self.reply(401,{});return
            self.close_connection=True
            if self.path not in ('/actors/motion/native','/motion-policy'):self.reply(404,{});return
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=4096:raise ValueError('Native request size')
                payload=decode(self.rfile.read(size))
                if self.path=='/motion-policy':
                    if not policy_state:raise RuntimeError('Finite policy adapter has no operator writer')
                    self.reply(200,policy_state.save(payload));return
                value=proxy.handle(payload)
                self.reply(200 if value['accepted'] else 409,value)
            except Exception as exc:self.reply(409,dict(accepted=False,error=type(exc).__name__))
    class Server(ThreadingHTTPServer):
        daemon_threads=True
        def get_request(self):
            connection,address=super().get_request();connection.settimeout(1);return connection,address
    relay=None
    report=dict(mode='finite_integrated_native_runtime',accepted=False,production_flag_changed=False,
                audio_commands=0,head_commands=0)
    with Server((profile['listen'] if profile else '0.0.0.0',profile['port'] if profile else 8775),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        started=time.monotonic()
        try:
            if args.camera_policy:
                policy=json.loads(args.camera_policy.read_text())
                if (set(policy)!={'camera_enabled','privacy_all'} or policy['camera_enabled'] is not True
                        or policy['privacy_all'] is not False or local_policy()['privacy_all'] is not False):raise RuntimeError('Explicit camera-only policy required')
                from reachy_companion.autonomous.camera_relay import CameraRelay
                relay=CameraRelay()
            thread.start()
            while not done.wait(.1) and (duration==0 or time.monotonic()-started<duration):
                if relay:
                    policy=json.loads(args.camera_policy.read_text())
                    if policy.get('camera_enabled') is not True or local_policy()['privacy_all'] is not False:
                        relay.close();relay=None
                if runtime.operator_invalid:done.set()
            report['final_runtime']=runtime.status()
            report['accepted']=(not runtime.operator_invalid and not runtime.guard.quarantined
                and runtime.actor is not None and runtime.actor.receipt is not None
                and runtime.actor.receipt['verified'] is True)
        finally:
            runtime.closing=True
            args.output.with_suffix('.closing.json').write_text(json.dumps(dict(writer_pid=__import__('os').getpid())))
            report['shutdown_hold_verified']=runtime.guard.emergency_output_stop()
            report['accepted']=report['accepted'] and report['shutdown_hold_verified']
            if thread.is_alive():server.shutdown();thread.join(1)
            try:
                if relay:relay.close()
            finally:
                try:
                    emergency.close();ipc.close()
                finally:runtime.close()
    report['lifecycle_closed']=True
    report['operator_after']=operator()
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    return 0 if report['accepted'] else 2
