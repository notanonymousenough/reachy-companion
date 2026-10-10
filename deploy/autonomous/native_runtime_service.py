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
    socket_path=args.output.with_suffix('.sock')
    directory=args.output.parent/'native-runtime-guard'
    driver=Driver()
    def local_policy():
        # The root-selected finite role grants only antenna17. Privacy-all is
        # independently authoritative and cannot be overridden by HTTP fields.
        private=json.loads(args.camera_policy.read_text())['privacy_all'] if args.camera_policy else False
        return dict(motor_enabled=True,quiet=False,privacy_all=private)
    runtime=MotionRuntime(driver,directory,operator,
                          args.output.with_suffix('.intent.json'),owner_verified=True,
                          recovery_audited=args.acknowledge_recovered_stop,policy=local_policy)
    ipc=RuntimeServer(runtime,socket_path)
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
            if self.path=='/status':self.reply(200,dict(motion_actor=proxy.status(),**operator()))
            else:self.reply(404,{})
        def do_POST(self):
            if not self.auth():self.reply(401,{});return
            self.close_connection=True
            if self.path!='/actors/motion/native':self.reply(404,{});return
            try:
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=4096:raise ValueError('Native request size')
                value=proxy.handle(decode(self.rfile.read(size)))
                self.reply(200 if value['accepted'] else 409,value)
            except Exception as exc:self.reply(409,dict(accepted=False,error=type(exc).__name__))
    class Server(ThreadingHTTPServer):
        daemon_threads=True
        def get_request(self):
            connection,address=super().get_request();connection.settimeout(1);return connection,address
    relay=None
    report=dict(mode='finite_integrated_native_runtime',accepted=False,production_flag_changed=False,
                audio_commands=0,head_commands=0)
    with Server(('0.0.0.0',8775),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        started=time.monotonic()
        try:
            if args.camera_policy:
                policy=json.loads(args.camera_policy.read_text())
                if (set(policy)!={'camera_enabled','privacy_all'} or policy['camera_enabled'] is not True
                        or policy['privacy_all'] is not False):raise RuntimeError('Explicit camera-only policy required')
                from reachy_companion.autonomous.camera_relay import CameraRelay
                relay=CameraRelay()
            thread.start()
            while not done.wait(.1) and time.monotonic()-started<9:
                if relay:
                    policy=json.loads(args.camera_policy.read_text())
                    if policy.get('camera_enabled') is not True or policy.get('privacy_all') is not False:
                        relay.close();relay=None
                if runtime.operator_invalid:done.set()
            report['final_runtime']=runtime.status()
            report['accepted']=(not runtime.operator_invalid and not runtime.guard.quarantined
                and runtime.actor is not None and runtime.actor.receipt is not None
                and runtime.actor.receipt['verified'] is True)
        finally:
            if thread.is_alive():server.shutdown();thread.join(1)
            try:
                if relay:relay.close()
            finally:
                try:ipc.close()
                finally:runtime.close()
    report['operator_after']=operator()
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    return 0 if report['accepted'] else 2
