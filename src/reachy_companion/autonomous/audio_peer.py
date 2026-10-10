"""Authenticated finite audio peer: device ownership on Reachy, scheduler on Hub.

PCM writes queue bytes on the device owner; progress still reports measured
device consumption. No elapsed-time cursor, model-selected endpoint or resume.
"""
import base64
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler
from urllib.parse import urlsplit
from .contracts import decode, uid


class AudioPeer:
    def __init__(self, playback, operator, expected_owner, *, controller, clock=time.monotonic):
        self.playback, self.operator, self.expected_owner = playback, operator, dict(expected_owner)
        self.controller, self.clock, self.boot_id = controller, clock, uid()
        self.lock = threading.RLock()
        self.cached_operator = None
        self.operator_deadline = 0
        self.lease_deadline = clock()+10
        self.started_lease = False
        self.closed = False
        self.close_reason = None
        self.watch_error=None;self.watch_exited=False;self.operator_job=None;self.first_close=None
        self.operator_requests = 0
        self.max_operator_ms = 0
        self.lease_requests=0;self.max_lease_gap_ms=0;self.last_lease=None
        self.streams = {}
        self.observation = None
        self.sequence = 0
        self.last_output_end = 0
        self.last_output = None
        self.reserving = False
        self.watch = threading.Thread(target=self._watch, daemon=True)
        self.watch.start()

    def _watch(self):
        try:self._watch_loop()
        except BaseException as exc:
            self.watch_error=type(exc).__name__;self.close('watch_failed')
        finally:self.watch_exited=True

    def _watch_loop(self):
        job = result = None
        next_poll = 0
        while not self.closed:
            now = self.clock()
            if job and not job.is_alive():
                receipt = result.get('value')
                began = result['began']
                job = None
                with self.lock:
                    self.max_operator_ms=max(self.max_operator_ms,(now-began)*1000)
                    if result.get('error') or receipt is None:
                        self.watch_error=result.get('error','MissingReceipt');self.close('operator_unknown')
                    else:
                        try:owned=self._owned(receipt)
                        except (ValueError,TypeError,KeyError):
                            self.watch_error='InvalidReceipt';self.close('operator_invalid');return
                        if not owned:self.close('owner_changed')
                        elif now>=began+.3:self.close('operator_expired')
                        else:self.cached_operator=receipt;self.operator_deadline=began+.3
            if not job and now >= next_poll:
                if self.closed:return
                result = dict(began=now)
                def refresh(mailbox=result):
                    try:mailbox['value'] = self.operator()
                    except Exception as exc:mailbox['error']=type(exc).__name__
                job = threading.Thread(target=refresh, daemon=True)
                self.operator_requests+=1
                self.operator_job=job
                job.start();next_poll = now+.1
            with self.lock:
                valid = self.started_lease and self.operator_ready()
                initial = not self.started_lease and now < self.lease_deadline and (self.cached_operator is None or now < self.operator_deadline)
                if valid:
                    self.playback.operator(self.controller, microphone_enabled=True,
                        valid_until=min(self.operator_deadline, self.lease_deadline), wait=False)
                elif not initial:
                    self.close('operator_expired' if now>=self.operator_deadline else 'controller_expired')
            time.sleep(.005)

    def _owned(self, actual):
        if not isinstance(actual,dict) or not isinstance(actual.get('motion_policy'),dict):raise ValueError('Operator receipt')
        policy = actual['motion_policy']
        if (not isinstance(actual.get('agent_boot_id'),str) or not 1<=len(actual['agent_boot_id'])<=256
                or type(actual.get('microphone_epoch')) is not int or actual['microphone_epoch']<0
                or type(actual.get('microphone_enabled')) is not bool or type(actual.get('listening')) is not bool
                or not isinstance(actual.get('microphone_owner_id'),str)
                or actual.get('phase') not in ('paused','listening','thinking','speaking','error')
                or type(policy.get('epoch')) is not int or policy['epoch']<0
                or type(policy.get('quiet')) is not bool or type(policy.get('privacy_all')) is not bool):
            raise ValueError('Operator receipt schema')
        return (actual['agent_boot_id'] == self.expected_owner['agent_boot_id']
                and actual['microphone_epoch'] == self.expected_owner['owned_microphone_epoch']
                and actual.get('microphone_owner_id') == self.expected_owner['owner_id']
                and actual['microphone_enabled'] is True and not actual.get('microphone_state_error')
                and actual.get('phase') == 'paused' and actual.get('listening') is False
                and policy['epoch'] == self.expected_owner['policy_epoch']
                and policy['quiet'] is False and policy['privacy_all'] is False)

    def operator_ready(self):
        with self.lock:
            return (not self.closed and self.cached_operator is not None
                    and self.clock() < min(self.operator_deadline, self.lease_deadline))

    def permitted(self):
        with self.lock:return self.started_lease and self.operator_ready()

    def publish(self, pcm, captured_end, echo_reference):
        if not isinstance(pcm, bytes) or not pcm or len(pcm)%2 or len(pcm)>256000:
            raise ValueError('Bounded mono16k observation')
        with self.lock:
            if not self.permitted():return False
            self.sequence += 1
            self.observation = dict(pcm=pcm, captured_end=captured_end,
                source_boot=self.boot_id, sequence=self.sequence, echo_reference=echo_reference)
            return True

    def dispatch(self, path, body):
        if body.pop('controller', None) != self.controller:
            raise ValueError('Controller owner mismatch')
        if path == '/status':
            return dict(source_boot=self.boot_id, closed=self.closed, permitted=self.permitted(), operator_ready=self.operator_ready(),
                operator=self.cached_operator, playback=self.playback.status(), observation_sequence=self.sequence,
                close_reason=self.close_reason,first_close=self.first_close,watch_error=self.watch_error,
                watch_execution_busy=self.watch.is_alive(),operator_execution_busy=bool(self.operator_job and self.operator_job.is_alive()),max_operator_ms=self.max_operator_ms,operator_requests=self.operator_requests)
        if path == '/stop':
            self.close('controller_stop');deadline=self.clock()+.3
            while self.clock()<deadline:
                status=self.playback.status()
                if status['stop_known'] and not status['execution_busy']:return status
                time.sleep(.005)
            return self.playback.status()
        if path == '/lease':
            with self.lock:
                if (self.closed or self.cached_operator is None or self.clock() >= self.operator_deadline
                        or self.clock() >= self.lease_deadline):
                    raise RuntimeError('Controller lease withdrawn')
                self.started_lease=True;self.lease_deadline=self.clock()+.3
                now=self.clock()
                if self.last_lease is not None:self.max_lease_gap_ms=max(self.max_lease_gap_ms,(now-self.last_lease)*1000)
                self.last_lease=now;self.lease_requests+=1
                self.playback.operator(self.controller,microphone_enabled=True,valid_until=min(self.operator_deadline,self.lease_deadline),wait=False)
            return dict(source_boot=self.boot_id)
        if path not in ('/stream-stop','/progress') and not self.permitted():raise RuntimeError('Actual owner/operator unavailable')
        if path == '/observation':
            with self.lock:
                value=self.observation;self.observation=None
                if not value:return dict(observation=None,source_boot=self.boot_id)
                value=dict(value)
                value['capture_age_s']=self.clock()-value.pop('captured_end')
                value['pcm_base64']=base64.b64encode(value.pop('pcm')).decode()
                return dict(observation=value,source_boot=self.boot_id)
        stream=body.get('stream_id')
        if not isinstance(stream,str) or not 1<=len(stream)<=128:raise ValueError('Stream identity required')
        with self.lock:
            actual=self.streams.get(stream)
        if path == '/reserve':
            with self.lock:
                if self.reserving or stream in self.streams or len(self.streams)>=32:raise RuntimeError('Fresh bounded stream identity required')
                self.reserving=True
            try:
                actual=self.playback.begin(self.controller,stream,deadline=self.clock()+30)
                with self.lock:self.streams[stream]=actual;self.last_output=actual
                if not self.permitted():
                    self.playback.interrupt('late_reservation',preserve=False,wait=False)
                    raise RuntimeError('Reservation withdrawn')
            finally:
                with self.lock:self.reserving=False
            return dict(reserved=True,device_stream_id=actual)
        if not actual:raise RuntimeError('Unknown owned stream')
        if path == '/start':
            if body.get('rate')!=16000:raise ValueError('Mono16k peer required')
            return True  # local owned Playback starts ALSA, without submitting PCM
        if path == '/write':
            pcm=base64.b64decode(body['pcm_base64'],validate=True)
            if not self.playback.push(actual,pcm):raise RuntimeError('PCM queue withdrawn')
            return len(pcm)//2
        if path == '/finish':return self.playback.finish(actual)
        if path == '/progress':
            with self.playback.lock:
                active=self.playback.active
                if active and active['stream_id']==actual and not active['started']:
                    return dict(stream_id=stream,consumed_frames=0,verified=True,provenance='device_consumed_pcm')
            receipt=dict(self.playback.backend.progress(actual));receipt['stream_id']=stream
            return receipt
        if path == '/stream-stop':
            # Never turn a delayed stop for an old stream into stop of a new one.
            with self.playback.lock:
                if self.playback.backend.stream!=actual:raise RuntimeError('Retired stream stop')
                self.playback.interrupt('remote_stop',preserve=False,wait=False)
            receipt=dict(self.playback.backend.stop(actual));receipt['stream_id']=stream
            self.last_output_end=self.clock()
            return receipt
        raise ValueError('Typed peer path')

    def close(self,reason='shutdown'):
        with self.lock:
            if self.close_reason is None:
                self.close_reason=reason
                now=self.clock()
                self.first_close=dict(reason=reason,source_boot=self.boot_id,
                    last_accepted_age_ms=None if self.last_lease is None else max(0,(now-self.last_lease)*1000),
                    operator_age_remaining_ms=max(0,(self.operator_deadline-now)*1000),lease_requests=self.lease_requests)
            self.closed=True;self.observation=None
        with self.playback.lock:self.playback.closed=True
        return self.playback.interrupt('peer_withdrawal',preserve=False,wait=False)


def create_server(peer, token, bind='127.0.0.1', port=8780):
    if len(token)<32:raise ValueError('Audio peer auth required')
    slots=threading.BoundedSemaphore(4)
    class Server(ThreadingHTTPServer):
        def process_request(self, request, address):
            if not slots.acquire(False):
                self.shutdown_request(request)
                return
            try:super().process_request(request,address)
            except BaseException:
                slots.release()
                raise
        def process_request_thread(self, request, address):
            try:super().process_request_thread(request,address)
            finally:slots.release()
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def setup(self):
            super().setup();self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            self.connection.settimeout(.5)
        def log_message(self,*args):pass
        def do_POST(self):
            if not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token):
                self.send_error(401);return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384:raise ValueError('Peer request cap')
                body=decode(self.rfile.read(size))
                result=peer.dispatch(self.path,body)
                payload=json.dumps(result).encode()
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            except Exception:self.send_error(409)
    server=Server((bind,port),Handler);server.daemon_threads=True
    return server


class PeerClient:
    def __init__(self,url,token,controller,timeout=.25,*,trusted_private_lan=False):
        if type(trusted_private_lan) is not bool:raise ValueError('Explicit peer transport opt-in')
        endpoint=urlsplit(url);allowed=endpoint.hostname in ('127.0.0.1','localhost','::1')
        if trusted_private_lan:
            import ipaddress
            address=ipaddress.ip_address(endpoint.hostname)
            allowed=any(address in ipaddress.ip_network(network) for network in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
        if (endpoint.scheme!='http' or not allowed or endpoint.username or endpoint.password
                or endpoint.query or endpoint.fragment or endpoint.path not in ('','/')):
            raise ValueError('Owned loopback or explicit RFC1918 peer transport required')
        self.url,self.token,self.controller,self.timeout=url.rstrip('/'),token,controller,timeout
        self.opener=build_opener(ProxyHandler({}))
    def call(self,path,**body):
        body['controller']=self.controller
        request=Request(self.url+path,data=json.dumps(body).encode(),headers={
            'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with self.opener.open(request,timeout=self.timeout) as response:raw=response.read(350001)
        if len(raw)>350000:raise ValueError('Bounded peer response')
        return decode(raw)


class PersistentPeer:
    """One serial actual network slot; callers never use it on the reducer."""
    def __init__(self,client):
        self.client=client;self.lock=threading.Lock();self.connection=None
    def close(self):
        with self.lock:
            if self.connection:self.connection.close()
            self.connection=None
    def call(self,path,**body):
        with self.lock:
            if self.connection is None:
                endpoint=urlsplit(self.client.url)
                self.connection=http.client.HTTPConnection(endpoint.hostname,endpoint.port,timeout=self.client.timeout)
                self.connection.connect();self.connection.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            try:
                self.connection.request('POST',path,json.dumps(dict(body,controller=self.client.controller)),
                    headers={'Authorization':'Bearer '+self.client.token,'Content-Type':'application/json'})
                response=self.connection.getresponse();raw=response.read(350001)
                if response.status!=200 or len(raw)>350000:raise RuntimeError('Peer response rejected')
                return decode(raw)
            except BaseException:
                self.connection.close();self.connection=None;raise


class RemotePCM:
    def __init__(self,client):self.client=client;self.transport=PersistentPeer(client);self.stream_map={}
    def reserve(self,stream):
        self.transport.close()
        result=self.transport.call('/reserve',stream_id=stream)
        actual=result.get('device_stream_id')
        if result.get('reserved') is not True or not isinstance(actual,str) or not 1<=len(actual)<=128:
            raise ValueError('Device reservation lineage')
        self.stream_map[stream]=actual
    def start(self,stream,rate):self.transport.call('/start',stream_id=stream,rate=rate)
    def write(self,stream,pcm):return self.transport.call('/write',stream_id=stream,pcm_base64=base64.b64encode(pcm).decode())
    def progress(self,stream):return self.transport.call('/progress',stream_id=stream)
    def finish(self,stream):return self.transport.call('/finish',stream_id=stream)
    def stop(self,stream):
        try:return self.client.call('/stream-stop',stream_id=stream)
        finally:self.transport.close()


class AudioPolling:
    """One actual peer poll slot; scheduler only consumes its latest receipt."""
    def __init__(self, client, adapter, source_boot):
        self.client,self.adapter,self.source_boot=client,adapter,source_boot
        self.adapter.bind_source(source_boot,0)
        self.lock=threading.Lock();self.job=None;self.result=None;self.next_poll=0
        self.closed=False;self.calls=self.errors=self.rejected=0

    def advance(self, authority, operator):
        with self.lock:
            now=time.monotonic()
            if self.closed:return
            if self.job and not self.job.is_alive():
                self.job=None;result,self.result=self.result,None
                if result:
                    scope,binding,started,packet=result
                    if (scope!=authority or not operator or tuple(operator['binding'])!=binding
                            or now-started>=.25 or packet.get('source_boot')!=self.source_boot):
                        self.rejected+=1
                    elif packet.get('observation'):
                        observation=packet['observation']
                        age=observation['capture_age_s']
                        if type(age) not in (int,float) or not 0<=age<=.25:self.rejected+=1
                        else:
                            pcm=base64.b64decode(observation['pcm_base64'],validate=True)
                            # Request start minus producer age is conservative:
                            # transport latency increases age, never freshness.
                            self.adapter.submit(pcm,source_boot=self.source_boot,
                                sequence=observation['sequence'],captured_end=started-age,
                                authority=scope,operator_binding=binding,
                                echo_reference=observation.get('echo_reference'))
            if not self.job and now>=self.next_poll and operator:
                binding=tuple(operator['binding']);self.calls+=1;self.next_poll=now+.05
                def work():
                    try:
                        packet=self.client.call('/observation')
                        with self.lock:
                            if not self.closed:self.result=authority,binding,now,packet
                    except Exception:
                        with self.lock:self.errors+=1
                self.job=threading.Thread(target=work,daemon=True);self.job.start()

    def close(self):
        with self.lock:self.closed=True;self.result=None

    def status(self):
        with self.lock:return dict(execution_busy=bool(self.job and self.job.is_alive()),
            calls=self.calls,errors=self.errors,rejected=self.rejected)


class PeerLease:
    """Independent renewal slot, gated by actual scheduler progress, not HTTP reads."""
    def __init__(self,client,*,datagram=None):
        self.client=client;self.lock=threading.Lock();self.closed=False
        self.datagram=datagram
        self.last_tick=time.monotonic();self.calls=self.errors=0;self.busy=False
        self.max_call_ms=0
        self.max_tick_gap_ms=0;self.error_types={}
        endpoint=urlsplit(client.url)
        # A lost TCP segment must not occupy the renewal slot for almost the
        # whole 300 ms device lease. Other peer operations retain their limits.
        self.connection=http.client.HTTPConnection(endpoint.hostname,endpoint.port,timeout=min(client.timeout,.05))
        self.worker=threading.Thread(target=self._run,daemon=True);self.worker.start()
    def tick(self):
        with self.lock:
            now=time.monotonic();self.max_tick_gap_ms=max(self.max_tick_gap_ms,(now-self.last_tick)*1000);self.last_tick=now
    def _run(self):
        while True:
            with self.lock:
                if self.closed:
                    self.connection.close()
                    if self.datagram:self.datagram.close()
                    return
                valid=time.monotonic()-self.last_tick<.1
                self.busy=valid
            if valid:
                started=time.monotonic()
                try:
                    if self.datagram:
                        self.datagram.renew()
                        with self.lock:
                            self.calls+=1;self.busy=False
                            self.max_call_ms=max(self.max_call_ms,(time.monotonic()-started)*1000)
                        time.sleep(.02)
                        continue
                    if self.connection.sock is None:
                        self.connection.connect()
                        self.connection.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    self.connection.request('POST','/lease',json.dumps(dict(controller=self.client.controller)),
                        headers={'Authorization':'Bearer '+self.client.token,'Content-Type':'application/json'})
                    response=self.connection.getresponse();raw=response.read(8193)
                    if response.status!=200 or len(raw)>8192:raise RuntimeError('Lease response rejected')
                    decode(raw)
                except Exception as exc:
                    self.connection.close()
                    with self.lock:
                        self.errors+=1;kind=type(exc).__name__
                        self.error_types[kind]=self.error_types.get(kind,0)+1
                with self.lock:
                    self.calls+=1;self.busy=False
                    self.max_call_ms=max(self.max_call_ms,(time.monotonic()-started)*1000)
            time.sleep(.02)
    def close(self):
        with self.lock:self.closed=True
    def status(self):
        with self.lock:return dict(execution_busy=self.worker.is_alive() if self.closed else self.busy,
            calls=self.calls,errors=self.errors,max_call_ms=self.max_call_ms,
            max_tick_gap_ms=self.max_tick_gap_ms,error_types=dict(self.error_types),
            progress_age_ms=(time.monotonic()-self.last_tick)*1000)
