"""Finite video-only producer: latest frame in RAM, loopback authenticated stream."""
import argparse
from collections import deque
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import struct
import sys
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from uuid import uuid4


class Producer:
    def __init__(self,args):
        self.args=args;self.lock=threading.Lock();self.latest=None;self.latest_at=None;self.scope=None;self.generation=0
        self.privacy_all=True;self.policy_seq=-1;self.policy_deadline=0;self.admission_id=None
        self.retired=deque(maxlen=128);self.boot_id=str(uuid4());self.seq=0;self.gaps=0;self.frames=0
        self.retired_admissions=set()
        # Frames from one producer run are correlated evidence. Reopening the
        # reader/privacy transitions cannot manufacture independent episodes.
        self.capture_lineage_id=str(uuid4())
        self.done=threading.Event()
        config=json.loads((args.production_root/'config.local.json').read_text())
        token_path=Path(config['paths']['token_file'])
        if not token_path.is_absolute():token_path=args.production_root/token_path
        self.operator_token=token_path.read_text().strip();self.port=urlsplit(config['network']['agent_url']).port
        self.opener=build_opener(ProxyHandler({}));self.last_operator=None
    def local_allowed(self):
        try:
            policy=json.loads(self.args.policy_file.read_text())
            return policy.get('camera_enabled') is True and policy.get('privacy_all') is False
        except Exception:return False
    def operator(self):
        request=Request('http://127.0.0.1:'+str(self.port)+'/status',headers={'Authorization':'Bearer '+self.operator_token})
        with self.opener.open(request,timeout=1) as response:value=json.load(response)
        self.last_operator={key:value.get(key) for key in ('microphone_enabled','capture_active','phase')}
        return value.get('microphone_enabled') is False and value.get('capture_active') is False
    def set_policy(self,value):
        if set(value) not in ({'scope','privacy_all','seq'},{'scope','privacy_all','seq','admission_id'}) or type(value['privacy_all']) is not bool or type(value['seq']) is not int or not 0<=value['seq']<=2**63-1:raise ValueError('Policy envelope')
        admission=value.get('admission_id')
        if admission is not None and (not isinstance(admission,str) or not 1<=len(admission)<=128):raise ValueError('Video admission bound')
        scope=value['scope']
        if set(scope)!= {'hub_boot_id','compute_boot_id','operator_epoch'} or type(scope['operator_epoch']) is not int or scope['operator_epoch']<0:
            raise ValueError('Policy scope')
        if any(not isinstance(scope[key],str) or not 1<=len(scope[key])<=128 for key in ('hub_boot_id','compute_boot_id')):raise ValueError('Boot scope')
        with self.lock:
            if self.done.is_set():raise ValueError('Terminal video producer')
            if admission in self.retired_admissions:raise ValueError('Retired video admission')
            owner=(scope['hub_boot_id'],scope['compute_boot_id'])
            if owner in self.retired:raise ValueError('Retired producer owner')
            if self.scope:
                old=(self.scope['hub_boot_id'],self.scope['compute_boot_id'])
                if owner==old:
                    if scope['operator_epoch']<self.scope['operator_epoch'] or value['seq']<=self.policy_seq:raise ValueError('Old epoch/sequence')
                else:
                    if len(self.retired)>=128:self.done.set();self.latest=None;raise RuntimeError('Producer fence capacity exhausted')
                    self.retired.append(old);self.policy_seq=-1
            if admission!=self.admission_id and self.admission_id is not None:
                if len(self.retired_admissions)>=128:self.done.set();self.latest=None;raise RuntimeError('Video admission fence capacity exhausted')
                self.retired_admissions.add(self.admission_id)
            if scope!=self.scope or value['privacy_all'] or self.privacy_all!=value['privacy_all'] or admission!=self.admission_id:
                self.latest=None;self.latest_at=None;self.generation+=1
            self.admission_id=admission
            self.scope=dict(scope);self.policy_seq=value['seq'];self.privacy_all=value['privacy_all']
            self.policy_deadline=time.monotonic()+1.5
    def allowed(self):
        return not self.done.is_set() and self.scope is not None and not self.privacy_all and time.monotonic()<self.policy_deadline and self.local_allowed()
    def packet(self):
        with self.lock:
            if not self.allowed():self.latest=None;self.latest_at=None;return None
            if self.latest is None:return None
            metadata,payload=self.latest
            if self.latest_at is not None:
                elapsed=time.monotonic()-self.latest_at
                if not 0<=elapsed<=2:self.latest=None;self.latest_at=None;return None
                metadata={**metadata,'source_age_lower_ms':int(elapsed*1000)}
            raw=json.dumps(metadata).encode()
            return struct.pack('!I',len(raw))+raw+payload
    def publish_frame(self,metadata,payload,scope,generation,dequeued):
        with self.lock:
            if not self.allowed() or self.scope!=scope or self.generation!=generation:return False
            self.latest=(metadata,payload);self.latest_at=dequeued;self.frames+=1;return True
    def source_ids(self):
        return dict(frame_id=str(uuid4()),lineage_id=self.capture_lineage_id,
                    lineage_scope='producer_capture_session',independent_episode_verified=False)
    def capture(self):
        from importlib.metadata import version
        import numpy as np
        from reachy_mini.media.camera_gstreamer import GStreamerCamera, Gst
        from reachy_mini.media.camera_constants import get_camera_specs_by_name
        if 'reachy_mini.media.audio_gstreamer' in sys.modules:raise RuntimeError('Camera-only import gate failed')
        camera=None;misses=0;reader_boot=None;reader_generation=None
        try:
            while not self.done.is_set():
                with self.lock:allowed=self.allowed();scope=dict(self.scope) if self.scope else None;generation=self.generation;admission=self.admission_id
                try:allowed=allowed and self.operator()
                except Exception:allowed=False
                if not allowed:
                    with self.lock:self.latest=None
                    data=frame=sample=ppm=buffer=segment=clock=None
                    if camera is not None:camera.close();camera=None
                    self.done.wait(.1);continue
                try:
                    if camera is not None and reader_generation!=generation:camera.close();camera=None
                    if camera is None:
                        camera=GStreamerCamera(camera_specs=get_camera_specs_by_name('wireless'));camera.open();reader_boot=str(uuid4())
                        reader_generation=generation
                    sample=camera._appsink_video.emit('try-pull-sample',100_000_000)
                    dequeued=time.monotonic() # receipt of buffer, never physical exposure time
                    if sample is None:
                        self.gaps+=1;misses+=1
                        with self.lock:self.latest=None
                        # Factory -> camera-only relay -> factory replaces the
                        # unixfd sender. Reopen after bounded misses; preserve
                        # the producer's existing capture lineage and policy.
                        if misses>=3:camera.close();camera=None;misses=0
                        self.done.wait(.1);continue
                    misses=0
                    buffer=sample.get_buffer();data=buffer.extract_dup(0,buffer.get_size())
                    if len(data)!=720*1280*3:raise ValueError('Native BGR frame size')
                    frame=np.frombuffer(data,dtype=np.uint8).reshape((720,1280,3))
                    # PTS is presentation time in this pipeline, not a verified
                    # physical exposure timestamp. Preserve both clock readings.
                    pts=None if buffer.pts==Gst.CLOCK_TIME_NONE else int(buffer.pts)
                    segment=sample.get_segment()
                    running=None if pts is None else int(segment.to_running_time(Gst.Format.TIME,pts))
                    if running==Gst.CLOCK_TIME_NONE:running=None
                    clock=camera.pipeline.get_clock();clock_now=int(clock.get_time());base=int(camera.pipeline.get_base_time())
                    ppm=b'P6\n320 180\n255\n'+frame[::4,::4,::-1].copy().tobytes()
                    metadata=dict(producer_boot_id=self.boot_id,seq=self.seq,**self.source_ids(),
                                  scope=scope,admission_id=admission,video_protocol=2,frame_sha256=hashlib.sha256(ppm).hexdigest(),sdk_version=version('reachy-mini'),
                                  audio_initialised=False,pts_ns=pts,buffer_running_time_ns=running,
                                  consumer_clock_ns=clock_now,consumer_base_time_ns=base,
                                  presentation_age_ms=None if running is None or clock_now<base+running else (clock_now-base-running)/1e6,
                                  source_capture_time_verified=False,source_age_lower_ms=0,source_age_upper_ms=None,
                                  reader_boot_id=reader_boot,presentation_clock_only=True,
                                  robot_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
                    self.seq+=1
                    self.publish_frame(metadata,ppm,scope,generation,dequeued)
                except Exception:
                    self.gaps+=1
                    with self.lock:self.latest=None
                    if camera is not None:camera.close();camera=None
                finally:
                    data=frame=sample=ppm=buffer=segment=clock=None
                self.done.wait(.5)
        finally:
            if camera is not None:camera.close()
            with self.lock:self.latest=None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('production-root','policy-file','token-file','output'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--port',type=int,default=8772);parser.add_argument('--duration',type=float,default=45)
    args=parser.parse_args()
    if not 1<=args.port<=65535 or not 5<=args.duration<=60:parser.error('Finite producer bounds')
    token=args.token_file.read_text().strip()
    if len(token)<32:raise ValueError('Separate video token required')
    producer=Producer(args)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def authorized(self):return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
        def reply(self,status,body):
            self.send_response(status);self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except OSError:pass
        def do_GET(self):
            if not self.authorized():self.reply(401,b'');return
            if self.path!='/latest':self.reply(404,b'');return
            packet=producer.packet();self.reply(200 if packet else 503,packet or b'')
        def do_POST(self):
            if not self.authorized():self.reply(401,b'');return
            try:
                if self.path!='/policy':self.reply(404,b'');return
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=2048:raise ValueError('Policy size')
                producer.set_policy(json.loads(self.rfile.read(size)));self.reply(200,b'{}')
            except Exception:self.reply(409,b'')
    class Server(ThreadingHTTPServer):
        daemon_threads=True
        def __init__(self,*args):self.clients=threading.BoundedSemaphore(2);super().__init__(*args)
        def process_request(self,request,address):
            request.settimeout(1)
            if not self.clients.acquire(False):self.shutdown_request(request);return
            try:super().process_request(request,address)
            except BaseException:self.clients.release();raise
        def process_request_thread(self,request,address):
            try:super().process_request_thread(request,address)
            finally:self.clients.release()
    capture=threading.Thread(target=producer.capture,daemon=True)
    with Server(('127.0.0.1',args.port),Handler) as server:
        serve=threading.Thread(target=server.serve_forever,daemon=True);serve.start();capture.start()
        try:producer.done.wait(args.duration)
        finally:
            producer.done.set();server.shutdown();serve.join(timeout=2);capture.join(timeout=4)
    report=dict(mode='finite_video_only_ram_producer',frames=producer.frames,gaps=producer.gaps,
                capture_thread_reaped=not capture.is_alive(),operator_last=producer.last_operator,
                raw_files_created=0,audio_or_motor_commands=0)
    with args.output.open('x') as out:json.dump(report,out,indent=2)
    print(json.dumps(report))
    if capture.is_alive():raise SystemExit(2)


if __name__=='__main__':main()
