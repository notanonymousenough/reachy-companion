"""Authenticated audio peer: finite by default, with an opt-in sequenced lease.

PCM writes queue bytes on the device owner; progress still reports measured
device consumption. No elapsed-time cursor, model-selected endpoint or resume.
"""
import base64
import hmac
import http.client
import hashlib
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler
from urllib.parse import urlsplit
from .contracts import decode, uid


def stream_identity(boot,sequence):
    if (not isinstance(boot,str) or not 1<=len(boot)<=96 or type(sequence) is not int
            or not 1<=sequence<2**63):raise ValueError('Bounded sequenced stream identity')
    return boot+':'+str(sequence)


def owner_binding(owner):
    return dict(agent_boot_id=owner['agent_boot_id'],microphone_epoch=owner['owned_microphone_epoch'],
        policy_epoch=owner['policy_epoch'],owner_sha256=hashlib.sha256(owner['owner_id'].encode()).hexdigest())


def lease_authority(value):
    if (type(value) is not dict or set(value)!={'agent_boot_id','microphone_epoch','policy_epoch','owner_sha256'}
            or not isinstance(value['agent_boot_id'],str) or not 1<=len(value['agent_boot_id'])<=256
            or any(type(value[key]) is not int or not 0<=value[key]<2**63 for key in ('microphone_epoch','policy_epoch'))
            or not isinstance(value['owner_sha256'],str) or len(value['owner_sha256'])!=64
            or any(char not in '0123456789abcdef' for char in value['owner_sha256'])):
        raise ValueError('Typed lease authority required')
    return dict(value)


class AudioPeer:
    def __init__(self, playback, operator, expected_owner, *, controller, clock=time.monotonic, mute_owner=None,lifetime='finite',source_boot=None):
        if type(lifetime) is not str or lifetime not in ('finite','lease'):raise ValueError('Explicit audio lifetime')
        self.lifetime=lifetime;self.stream_high_water=0;self.stream_records={};self.reservation_handlers=0
        self.playback, self.operator, self.expected_owner = playback, operator, dict(expected_owner)
        if source_boot is not None and lifetime!='lease':raise ValueError('Explicit source claim only for lease lifetime')
        if source_boot is not None:stream_identity(source_boot,1)
        self.controller, self.clock, self.boot_id = controller, clock, source_boot or uid()
        self.mute_owner=mute_owner;self.operator_control_busy=False;self.operator_control_receipt=None
        self.lock = threading.RLock()
        self.cached_operator = None
        self.operator_deadline = 0
        self.lease_deadline = clock()+10
        self.started_lease = False
        self.closed = False
        self.close_reason = None
        self.watch_error=None;self.watch_exited=False;self.operator_job=None;self.first_close=None;self.closed_at=None;self.close_observers=[]
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
                or 'microphone_owner_id' not in actual or (actual['microphone_owner_id'] is not None and not isinstance(actual['microphone_owner_id'],str))
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
            if self.lifetime=='lease' and self.sequence>=2**63-1:self.close('observation_sequence_exhausted');return False
            self.sequence += 1
            self.observation = dict(pcm=pcm, captured_end=captured_end,
                source_boot=self.boot_id, sequence=self.sequence, echo_reference=echo_reference)
            return True

    def operator_status(self):
        with self.lock:
            return diagnostic_operator(self.cached_operator)

    @contextmanager
    def stream_reference(self,path,body):
        record=None;reservation=self.lifetime=='lease' and path=='/reserve'
        if reservation:
            with self.lock:self.reservation_handlers+=1
        if self.lifetime=='lease' and path in ('/start','/write','/finish','/progress','/stream-stop'):
            with self.lock:
                stream=body.get('stream_id');sequence=body.get('stream_sequence')
                if (body.get('source_boot')!=self.boot_id or stream!=stream_identity(self.boot_id,sequence)):
                    raise ValueError('Exact sequenced stream scope')
                record=self.stream_records.get(stream)
                if record is None or record['retiring'] or record['actual'] is None:
                    raise RuntimeError('Retired or unknown stream')
                record['refs']+=1
        try:yield
        finally:
            if reservation:
                with self.lock:self.reservation_handlers-=1
            if record is not None:
                with self.lock:record['refs']-=1

    def dispatch(self,path,body):
        with self.stream_reference(path,body):return self._dispatch(path,body)

    def _dispatch(self, path, body):
        if body.pop('controller', None) != self.controller:
            raise ValueError('Controller owner mismatch')
        if path == '/status':
            return dict(source_boot=self.boot_id,lifetime=self.lifetime,
                lease_binding=owner_binding(self.expected_owner) if self.lifetime=='lease' else None,
                stream_high_water=self.stream_high_water,stream_records=len(self.stream_records),
                closed=self.closed, permitted=self.permitted(), operator_ready=self.operator_ready(),
                agent_mute_supported=self.mute_owner is not None,operator_control_execution_busy=self.operator_control_busy,
                agent_mute_receipt=None if self.operator_control_receipt is None else dict(self.operator_control_receipt),operator=self.operator_status(), playback=self.playback.status(), observation_sequence=self.sequence,
                close_reason=self.close_reason,first_close=self.first_close,watch_error=self.watch_error,
                watch_execution_busy=self.watch.is_alive(),operator_execution_busy=bool(self.operator_job and self.operator_job.is_alive()),max_operator_ms=self.max_operator_ms,operator_requests=self.operator_requests)
        if path == '/stop':
            self.close('controller_stop');deadline=self.clock()+.3
            while self.clock()<deadline:
                status=self.playback.status()
                if status['stop_known'] and not status['execution_busy']:return status
                time.sleep(.005)
            return self.playback.status()
        if path == '/operator-mute':
            with self.lock:
                if (set(body)!={'source_boot'} or body['source_boot']!=self.boot_id or self.mute_owner is None
                        or self.operator_control_busy or not self.permitted()):raise RuntimeError('Owned operator mute unavailable')
                self.operator_control_busy=True
            try:
                receipt=self.mute_owner()
                if (not isinstance(receipt,dict) or receipt.get('agent_boot_id')!=self.expected_owner['agent_boot_id']
                        or type(receipt.get('microphone_epoch')) is not int or not 0<=receipt['microphone_epoch']<2**63
                        or receipt['microphone_epoch']!=self.expected_owner['owned_microphone_epoch']+1
                        or receipt.get('microphone_enabled') is not False or receipt.get('microphone_owner_present') is not False
                        or receipt.get('listening') is not False or receipt.get('capture_active') is not False
                        or 'microphone_state_error' not in receipt or receipt['microphone_state_error'] is not None):
                    raise RuntimeError('Actual Agent mute acknowledgement unknown')
                public={name:receipt[name] for name in ('agent_boot_id','microphone_epoch','microphone_enabled',
                    'microphone_owner_present','listening','capture_active','microphone_state_error')}
                with self.lock:self.operator_control_receipt=public
                return dict(source_boot=self.boot_id,agent_mute_verified=True,operator=dict(public))
            finally:
                self.close('owner_operator_mute')
                with self.lock:self.operator_control_busy=False
        if path == '/lease':
            with self.lock:
                if self.lifetime=='lease':lease_authority(body.get('authority'))
                if self.lifetime=='lease' and (body!={'source_boot':self.boot_id,'authority':owner_binding(self.expected_owner)}
                        or self.cached_operator is None or not self._owned(self.cached_operator)):
                    raise RuntimeError('Exact current lease authority required')
                if (self.closed or self.cached_operator is None or self.clock() >= self.operator_deadline
                        or self.clock() >= self.lease_deadline):
                    raise RuntimeError('Controller lease withdrawn')
                self.started_lease=True;self.lease_deadline=self.clock()+.3
                now=self.clock()
                if self.last_lease is not None:self.max_lease_gap_ms=max(self.max_lease_gap_ms,(now-self.last_lease)*1000)
                self.last_lease=now;self.lease_requests+=1
                self.playback.operator(self.controller,microphone_enabled=True,valid_until=min(self.operator_deadline,self.lease_deadline),wait=False)
            return dict(source_boot=self.boot_id,**({'authority':owner_binding(self.expected_owner)} if self.lifetime=='lease' else {}))
        if path not in ('/stream-stop','/progress') and not self.permitted():raise RuntimeError('Actual owner/operator unavailable')
        if path == '/observation':
            with self.lock:
                value=self.observation;self.observation=None
                if not value:return dict(observation=None,source_boot=self.boot_id)
                value=dict(value)
                value['capture_age_s']=self.clock()-value.pop('captured_end')
                value['pcm_base64']=base64.b64encode(value.pop('pcm')).decode()
                return dict(observation=value,source_boot=self.boot_id)
        if self.lifetime=='lease' and path=='/retire':return self.retire(body)
        stream=body.get('stream_id')
        if not isinstance(stream,str) or not 1<=len(stream)<=128:raise ValueError('Stream identity required')
        with self.lock:
            actual=self.streams.get(stream)
        if path == '/reserve':
            with self.lock:
                if self.reserving or stream in self.streams or len(self.streams)>=32:raise RuntimeError('Fresh bounded stream identity required')
                if self.lifetime=='lease':
                    sequence=body.get('stream_sequence')
                    if (body.get('source_boot')!=self.boot_id or stream!=stream_identity(self.boot_id,sequence)
                            or sequence!=self.stream_high_water+1 or self.stream_records):
                        raise RuntimeError('Next sequenced reservation requires terminal retirement')
                    self.stream_high_water=sequence # spent BEFORE potentially unknown backend operation
                    self.stream_records[stream]=dict(actual=None,generation=None,refs=0,retiring=False)
                self.reserving=True
            try:
                actual=self.playback.begin(self.controller,stream,deadline=self.clock()+30)
                with self.lock:self.streams[stream]=actual;self.last_output=actual
                if self.lifetime=='lease':
                    with self.lock,self.playback.lock:
                        self.stream_records[stream].update(actual=actual,generation=self.playback.generation)
                if not self.permitted():
                    self.playback.interrupt('late_reservation',preserve=False,wait=False)
                    raise RuntimeError('Reservation withdrawn')
            finally:
                with self.lock:self.reserving=False
            return dict(reserved=True,device_stream_id=actual,**(
                {'generation':self.stream_records[stream]['generation']} if self.lifetime=='lease' else {}))
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
            job,result=self.playback.request_stop(actual) # deduplicate actual backend operation
            job.join(self.playback.stop_timeout)
            if job.is_alive():
                return dict(stream_id=stream,verified_stopped=False,verified=False,consumed_frames=None,execution_busy=True)
            receipt=dict(result.get('receipt',{}));receipt['stream_id']=stream
            receipt['execution_busy']=self.playback.status()['execution_busy']
            self.last_output_end=self.clock()
            return receipt
        raise ValueError('Typed peer path')

    def retire(self,body):
        stream=body.get('stream_id');sequence=body.get('stream_sequence');generation=body.get('generation')
        if (set(body)!={'source_boot','stream_id','stream_sequence','generation','completion'}
                or body['source_boot']!=self.boot_id or stream!=stream_identity(self.boot_id,sequence)
                or type(generation) is not int or body['completion'] not in ('complete','cancelled')):
            raise ValueError('Exact terminal retirement scope')
        reply=dict(source_boot=self.boot_id,stream_id=stream,stream_sequence=sequence,generation=generation)
        with self.lock:
            record=self.stream_records.get(stream)
            if record is None or record['generation']!=generation or record['actual'] is None:
                raise RuntimeError('Retirement owner/generation unknown')
            if record['refs'] or self.reserving or self.reservation_handlers or self.playback.status()['execution_busy']:
                return dict(reply,retired=False,execution_busy=True)
            terminal=self.playback.terminal_receipt(record['actual'],generation)
            if terminal is None:raise RuntimeError('Terminal backend stop/cursor unknown')
            if body['completion']=='complete' and (not terminal['complete']
                    or terminal['consumed_frames']!=terminal['submitted_frames']):
                raise RuntimeError('Normal completion requires measured full consumption')
            record['retiring']=True
            if not self.playback.retire_terminal(record['actual'],generation):
                raise RuntimeError('Terminal references changed during retirement')
            del self.streams[stream];del self.stream_records[stream]
            return dict(reply,retired=True,execution_busy=False)

    def dispatch_stop(self,path,body):
        """Dedicated listener: exact owned revocation, independent of permission."""
        keys={'controller','source_boot'}|({'stream_id'} if path=='/stream-stop' else set())
        if self.lifetime=='lease' and path=='/stream-stop':keys.add('stream_sequence')
        if (path not in ('/stop','/stream-stop') or not isinstance(body,dict) or set(body)!=keys
                or body.get('controller')!=self.controller or body.get('source_boot')!=self.boot_id):
            raise ValueError('Exact current peer stop binding required')
        return self.dispatch(path,{key:value for key,value in body.items() if self.lifetime=='lease' or key!='source_boot'})

    def on_close(self,observer):
        with self.lock:
            if self.first_close is not None:self.first_close.update(observer(self.closed_at))
            else:self.close_observers.append(observer)

    def close(self,reason='shutdown'):
        observers=[]
        with self.lock:
            if self.close_reason is None:
                self.close_reason=reason
                now=self.clock();self.closed_at=now
                self.first_close=dict(reason=reason,source_boot=self.boot_id,
                    last_accepted_age_ms=None if self.last_lease is None else max(0,(now-self.last_lease)*1000),
                    operator_age_remaining_ms=max(0,(self.operator_deadline-now)*1000),controller_lease_remaining_ms=max(0,(self.lease_deadline-now)*1000),lease_requests=self.lease_requests)
                observers=self.close_observers;self.close_observers=[]
            self.closed=True;self.observation=None
        with self.playback.lock:self.playback.closed=True
        result=self.playback.interrupt('peer_withdrawal',preserve=False,wait=False)
        for observer in observers:
            try:observed=observer(self.closed_at)
            except Exception:observed={'observer_error':True}
            with self.lock:self.first_close.update(observed)
        return result


def create_server(peer, token, bind='127.0.0.1', port=8780, *, stop_port=None):
    if len(token)<32:raise ValueError('Audio peer auth required')
    if stop_port is not None and (type(stop_port) is not int or not 0<=stop_port<=65535):
        raise ValueError('Explicit valid stop listener port required')
    def listener(selected_port,control_only,capacity):
        slots=threading.BoundedSemaphore(capacity)
        class Server(ThreadingHTTPServer):
            daemon_threads=True
            def __init__(self,*args):
                self.stop_server=self.stop_worker=None
                self.lifecycle_lock=threading.Lock();self.before_start_stop=threading.Event();self.entered=threading.Event()
                self.handlers_lock=threading.Lock();self.handlers=0
                super().__init__(*args)
            def process_request(self,request,address):
                if not slots.acquire(False):self.shutdown_request(request);return
                with self.handlers_lock:self.handlers+=1
                try:super().process_request(request,address)
                except BaseException:
                    with self.handlers_lock:self.handlers-=1
                    slots.release();raise
            def process_request_thread(self,request,address):
                try:super().process_request_thread(request,address)
                finally:
                    with self.handlers_lock:self.handlers-=1
                    slots.release() # only actual connection handler return releases capacity
            def serve_forever(self,poll_interval=.5):
                try:
                    with self.lifecycle_lock:
                        if self.before_start_stop.is_set():return
                        if self.stop_server is not None:
                            self.stop_worker=threading.Thread(target=self.stop_server.serve_forever,kwargs={'poll_interval':.02},daemon=True)
                            self.stop_worker.start()
                        self.entered.set()
                    super().serve_forever(poll_interval)
                except BaseException:
                    self.server_close();raise
                finally:self._stop_control()
            def _stop_control(self):
                with self.lifecycle_lock:
                    if self.stop_server is not None:
                        self.stop_server.shutdown()
                        if self.stop_worker and self.stop_worker.ident is not None and self.stop_worker is not threading.current_thread():self.stop_worker.join(.5)
            def shutdown(self):
                with self.lifecycle_lock:
                    self.before_start_stop.set();entered=self.entered.is_set()
                if entered:super().shutdown()
                self._stop_control()
            def server_close(self):
                self._stop_control();super().server_close()
                if self.stop_server is not None:self.stop_server.server_close()
            def transport_status(self):
                with self.handlers_lock:media=self.handlers
                stop=self.stop_server
                if stop:
                    with stop.handlers_lock:control=stop.handlers
                else:control=0
                return dict(media_handlers=media,stop_handlers=control,
                    stop_listener_busy=bool(self.stop_worker and self.stop_worker.is_alive()))
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def setup(self):
                super().setup();self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                self.connection.settimeout(.5)
            def log_message(self,*args):pass
            def do_POST(self):
                if control_only:self.close_connection=True
                if not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token):
                    self.send_error(401);return
                if control_only and self.path not in ('/stop','/stream-stop'):
                    self.send_error(404);return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=(1024 if control_only else 16384):raise ValueError('Peer request cap')
                    body=decode(self.rfile.read(size))
                    with peer.stream_reference(self.path,body):
                        result=peer.dispatch_stop(self.path,body) if control_only else peer.dispatch(self.path,body)
                        payload=json.dumps(result).encode()
                        self.send_response(200);self.send_header('Content-Type','application/json')
                        if control_only:self.send_header('Connection','close')
                        self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
                except OSError:self.close_connection=True
                except Exception:
                    try:self.send_error(409)
                    except OSError:self.close_connection=True
        return Server((bind,selected_port),Handler)
    server=listener(port,False,4)
    try:server.stop_server=listener(stop_port,True,2) if stop_port is not None else None
    except BaseException:server.server_close();raise
    server.stop_address=server.stop_server.server_address if server.stop_server else None
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
        self.trusted_private_lan=trusted_private_lan
        self.opener=build_opener(ProxyHandler({}))
    def at_port(self,port):
        if type(port) is not int or not 1<=port<=65535:raise ValueError('Bound stop port required')
        endpoint=urlsplit(self.url)
        if port==(endpoint.port or 80):raise ValueError('Separate stop listener must not use the media port')
        host=endpoint.hostname
        return PeerClient('http://'+('['+host+']' if ':' in host else host)+':'+str(port),
            self.token,self.controller,self.timeout,trusted_private_lan=self.trusted_private_lan)
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
    def __init__(self,client,*,stop_port=None,source_boot=None,max_streams=None,lifetime='finite'):
        if lifetime not in ('finite','lease') or type(lifetime) is not str:raise ValueError('Explicit remote lifetime')
        if lifetime=='lease' and (stop_port is None or max_streams is not None):raise ValueError('Lease protocol requires dedicated stop and retirement')
        if max_streams is not None and (type(max_streams) is not int or not 1<=max_streams<=32):
            raise ValueError('Explicit finite remote stream budget1..32 required')
        if lifetime=='lease':stream_identity(source_boot,1)
        self.lifetime=lifetime;self.pending_stream=None;self.withdrawn=False
        self.max_streams=max_streams;self.reservation_attempts=0;self.budget_lock=threading.RLock()
        if stop_port is not None and (not isinstance(source_boot,str) or not 1<=len(source_boot)<=128):
            raise ValueError('Current peer boot required for separate stop transport')
        self.client=client;self.transport=PersistentPeer(client);self.stream_map={}
        self.stop_client=client.at_port(stop_port) if stop_port is not None else None
        self.source_boot=source_boot
    def reserve(self,stream):
        with self.budget_lock:
            if self.lifetime=='lease' and (self.withdrawn or self.pending_stream is not None):
                raise RuntimeError('Prior terminal retirement or unknown reservation blocks admission')
            if self.max_streams is not None and self.reservation_attempts>=self.max_streams:
                raise RuntimeError('Finite remote stream budget exhausted before reservation')
            if self.lifetime=='lease' and self.reservation_attempts>=2**63-1:
                self.withdrawn=True;raise ValueError('Sequenced reservation exhausted without wrap')
            self.reservation_attempts+=1 # spent BEFORE transport, including unknown completion
            if self.lifetime=='lease':
                wire=stream_identity(self.source_boot,self.reservation_attempts)
                self.pending_stream=dict(local=stream,wire=wire,sequence=self.reservation_attempts,generation=None,phase='RESERVING')
        self.transport.close()
        if self.lifetime=='lease':
            try:result=self.transport.call('/reserve',**self._scope(stream,reserving=True))
            except BaseException:
                with self.budget_lock:self.withdrawn=True
                raise
        else:result=self.transport.call('/reserve',stream_id=stream)
        actual=result.get('device_stream_id')
        if result.get('reserved') is not True or not isinstance(actual,str) or not 1<=len(actual)<=128:
            raise ValueError('Device reservation lineage')
        with self.budget_lock:
            self.stream_map[stream]=actual
            if self.lifetime=='lease':
                generation=result.get('generation')
                if type(generation) is not int or generation<1:self.withdrawn=True;raise ValueError('Device stream generation')
                self.pending_stream.update(generation=generation,phase='LIVE')
    def admission_ready(self):
        with self.budget_lock:return self.lifetime=='finite' or not self.withdrawn and self.pending_stream is None
    def _scope(self,stream,reserving=False):
        if self.lifetime=='finite':return dict(stream_id=stream)
        with self.budget_lock:
            value=self.pending_stream
            if (self.withdrawn or value is None or value['local']!=stream
                    or value['phase']!=('RESERVING' if reserving else 'LIVE')):raise RuntimeError('Exact current wire stream required')
            return dict(source_boot=self.source_boot,stream_id=value['wire'],stream_sequence=value['sequence'])
    def _receipt(self,stream,result):
        if self.lifetime=='lease':
            expected=self._scope(stream)['stream_id']
            if result.get('stream_id')!=expected:raise ValueError('Wire cursor stream mismatch')
            return dict(result,stream_id=stream)
        return result
    def start(self,stream,rate):self.transport.call('/start',**self._scope(stream),rate=rate)
    def write(self,stream,pcm):return self.transport.call('/write',**self._scope(stream),pcm_base64=base64.b64encode(pcm).decode())
    def progress(self,stream):return self._receipt(stream,self.transport.call('/progress',**self._scope(stream)))
    def finish(self,stream):return self.transport.call('/finish',**self._scope(stream))
    def stop(self,stream):
        if self.stop_client is not None:
            # Never acquire/close the media lock, or retry on the media listener.
            scope=self._scope(stream)
            scope['source_boot']=self.source_boot
            return self._receipt(stream,self.stop_client.call('/stream-stop',**scope))
        try:return self.client.call('/stream-stop',stream_id=stream)
        finally:self.transport.close()

    def retire(self,terminal):
        stream=terminal['stream_id']
        with self.budget_lock:
            scope=self._scope(stream);value=self.pending_stream
            scope.update(generation=value['generation'],completion='complete' if terminal['complete'] else 'cancelled')
            value['phase']='RETIRING'
        try:
            result=self.client.call('/retire',**scope)
            expected={key:scope[key] for key in ('source_boot','stream_id','stream_sequence','generation')}
            if result==dict(expected,retired=False,execution_busy=True):
                with self.budget_lock:value['phase']='LIVE'
                return False
            if result!=dict(expected,retired=True,execution_busy=False):raise ValueError('Exact terminal retirement acknowledgement')
            self.transport.close() # retirement worker, after all stream callers returned
            with self.budget_lock:value['phase']='ACK'
            return True
        except BaseException:
            with self.budget_lock:self.withdrawn=True
            raise

    def commit_retirement(self,stream):
        if self.lifetime=='finite':return
        with self.budget_lock:
            value=self.pending_stream
            if self.withdrawn or value is None or value['local']!=stream or value['phase']!='ACK':
                raise RuntimeError('Retirement acknowledgement is not committed')
            self.stream_map.pop(stream);self.pending_stream=None

    def close_transport(self):
        with self.budget_lock:
            if self.lifetime=='lease':self.withdrawn=True
        self.transport.close() # lifecycle worker only; never the independent stop handler


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
    def __init__(self,client,*,datagram=None,source_boot=None,authority=None):
        if source_boot is not None:stream_identity(source_boot,1)
        if (source_boot is None)!=(authority is None):raise ValueError('Lease source and authority must be paired')
        self.source_boot=source_boot;self.authority=lease_authority(authority) if authority is not None else None
        self.armed=source_boot is None;self.withdrawal_reason=None
        self.client=client;self.lock=threading.Lock();self.closed=False
        self.datagram=datagram
        self.last_tick=time.monotonic();self.calls=self.errors=0;self.busy=False
        self.max_call_ms=0
        self.max_tick_gap_ms=0;self.error_types={}
        self.last_worker_tick=None;self.max_worker_gap_ms=0;self.last_send=None;self.last_accepted=None
        self.worker_exit=None;self.worker_exception=None;self.first_close=None
        endpoint=urlsplit(client.url)
        # A lost TCP segment must not occupy the renewal slot for almost the
        # whole 300 ms device lease. Other peer operations retain their limits.
        self.connection=http.client.HTTPConnection(endpoint.hostname,endpoint.port,timeout=min(client.timeout,.05))
        self.worker=threading.Thread(target=self._run,daemon=True);self.worker.start()
    def tick(self,authority=None):
        with self.lock:
            now=time.monotonic()
            if self.source_boot is not None:
                if self.closed:return False
                try:valid=lease_authority(authority)==self.authority
                except ValueError:valid=False
                if not valid or self.armed and now-self.last_tick>=.1:
                    self._withdraw('authority_changed' if not valid else 'reducer_expired');return False
                self.armed=True
            self.max_tick_gap_ms=max(self.max_tick_gap_ms,(now-self.last_tick)*1000);self.last_tick=now
            return True
    def _run(self):
        try:self._run_loop()
        except BaseException as exc:
            with self.lock:
                self.worker_exception=type(exc).__name__
                if self.source_boot is not None:self._withdraw('renewal_worker_failed')
        finally:
            self.connection.close()
            if self.datagram:self.datagram.close()
            with self.lock:self.worker_exit='closed' if self.closed else 'unexpected_exit'

    def _run_loop(self):
        while True:
            with self.lock:
                now=time.monotonic()
                if self.last_worker_tick is not None:self.max_worker_gap_ms=max(self.max_worker_gap_ms,(now-self.last_worker_tick)*1000)
                self.last_worker_tick=now
                if self.closed:return
                if self.source_boot is not None:
                    if not self.armed:
                        if now-self.last_tick>=2:self._withdraw('initial_authority_timeout');return
                        self.busy=False
                        continue_wait=True
                    else:
                        continue_wait=False
                        if now-self.last_tick>=.1:self._withdraw('reducer_expired');return
                else:continue_wait=False
                valid=not continue_wait and time.monotonic()-self.last_tick<.1
                self.busy=valid
            if continue_wait:time.sleep(.005);continue
            if valid:
                started=time.monotonic()
                with self.lock:
                    if self.source_boot is not None:self.calls+=1
                try:
                    if self.datagram:
                        self.datagram.renew()
                        with self.lock:
                            if self.source_boot is None:self.calls+=1
                            self.busy=False
                            if self.source_boot is not None and (self.closed or time.monotonic()-self.last_tick>=.1):
                                self._withdraw('late_renewal_ack');return
                            self.last_accepted=time.monotonic()
                            self.max_call_ms=max(self.max_call_ms,(time.monotonic()-started)*1000)
                        time.sleep(.02)
                        continue
                    if self.connection.sock is None:
                        self.connection.connect()
                        self.connection.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    with self.lock:self.last_send=time.monotonic()
                    body=dict(controller=self.client.controller)
                    if self.source_boot is not None:body.update(source_boot=self.source_boot,authority=self.authority)
                    self.connection.request('POST','/lease',json.dumps(body),
                        headers={'Authorization':'Bearer '+self.client.token,'Content-Type':'application/json'})
                    response=self.connection.getresponse();raw=response.read(8193)
                    if response.status!=200 or len(raw)>8192:raise RuntimeError('Lease response rejected')
                    answer=decode(raw)
                    with self.lock:
                        if self.source_boot is not None:
                            if answer!=dict(source_boot=self.source_boot,authority=self.authority):raise ValueError('Lease acknowledgement scope')
                            if self.closed or time.monotonic()-self.last_tick>=.1:self._withdraw('late_renewal_ack');return
                        self.last_accepted=time.monotonic()
                except Exception as exc:
                    self.connection.close()
                    with self.lock:
                        self.errors+=1;kind=type(exc).__name__
                        self.error_types[kind]=self.error_types.get(kind,0)+1
                        if self.source_boot is not None:self._withdraw('renewal_unknown');return
                with self.lock:
                    if self.source_boot is None:self.calls+=1
                    self.busy=False
                    self.max_call_ms=max(self.max_call_ms,(time.monotonic()-started)*1000)
            time.sleep(.02)
    def _withdraw(self,reason):
        if self.withdrawal_reason is None:self.withdrawal_reason=reason
        if self.first_close is None:self.first_close=self._timing(time.monotonic())
        self.closed=True
    def close(self):
        with self.lock:
            self._withdraw('controller_stop')
    def _timing(self,now):
        sent=self.datagram.last_send if self.datagram else self.last_send
        return dict(last_send_age_ms=None if sent is None else max(0,(now-sent)*1000),
            last_accepted_age_ms=None if self.last_accepted is None else max(0,(now-self.last_accepted)*1000),
            reducer_progress_age_ms=max(0,(now-self.last_tick)*1000),
            worker_scheduling_age_ms=None if self.last_worker_tick is None else max(0,(now-self.last_worker_tick)*1000))
    def status(self):
        with self.lock:return dict(execution_busy=self.worker.is_alive() if self.closed else self.busy,
            withdrawn=self.closed,withdrawal_reason=self.withdrawal_reason,
            calls=self.calls,errors=self.errors,max_call_ms=self.max_call_ms,
            max_tick_gap_ms=self.max_tick_gap_ms,error_types=dict(self.error_types),
            progress_age_ms=(time.monotonic()-self.last_tick)*1000,
            max_worker_scheduling_gap_ms=self.max_worker_gap_ms,worker_exit=self.worker_exit,worker_exception=self.worker_exception,
            first_close=self.first_close,timing=self._timing(time.monotonic()),
            datagram=self.datagram.status() if self.datagram else None)


class PeerStartup:
    """Hub-side first-lease admission, independent of physical device permissions."""
    def __init__(self,source_boot,*,timeout=2,clock=time.monotonic):
        if not isinstance(source_boot,str) or not 1<=len(source_boot)<=128 or not .1<=timeout<=5:
            raise ValueError('Finite peer startup scope')
        self.source=source_boot;self.clock=clock;self.deadline=clock()+timeout
        self.phase='STARTING';self.reason=None;self.lock=threading.Lock()
        self.last_status=None;self.first_withdrawal=None
    def observe(self,receipt,acknowledged):
        with self.lock:
            if self.phase=='WITHDRAWN':return False
            if self.phase=='ACTIVE' and self.clock()-self.last_status>=.3:return self._withdraw('status_expired')
            if (not isinstance(receipt,dict) or receipt.get('source_boot')!=self.source
                    or any(type(receipt.get(name)) is not bool for name in ('closed','permitted','operator_ready'))):
                return self._withdraw('invalid_status')
            if receipt['closed']:return self._withdraw('device_closed')
            if self.phase=='STARTING':
                if self.clock()>=self.deadline:return self._withdraw('first_lease_timeout')
                if acknowledged is True and receipt['operator_ready'] and receipt['permitted']:self.phase='ACTIVE'
            elif not receipt['operator_ready'] or not receipt['permitted']:return self._withdraw('device_withdrawn')
            self.last_status=self.clock()
            return self.phase=='ACTIVE'
    def _withdraw(self,reason,error_kind=None):
        now=self.clock()
        self.first_withdrawal=dict(previous_phase=self.phase,reason=reason,error_kind=error_kind,
            last_status_age_ms=None if self.last_status is None else max(0,(now-self.last_status)*1000),
            status_remaining_ms=None if self.last_status is None else max(0,(self.last_status+.3-now)*1000))
        self.phase='WITHDRAWN';self.reason=reason;return False
    def failure(self,error_kind):
        with self.lock:
            if self.phase=='ACTIVE':self._withdraw('status_failed',error_kind[:64])
            return self.phase
    def advance(self):
        with self.lock:
            if self.phase=='STARTING' and self.clock()>=self.deadline:self._withdraw('first_lease_timeout')
            elif self.phase=='ACTIVE' and self.clock()-self.last_status>=.3:self._withdraw('status_expired')
            return self.phase
    def close(self):
        with self.lock:
            if self.phase!='WITHDRAWN':self._withdraw('controller_stop')
    def status(self):
        with self.lock:return dict(phase=self.phase,reason=self.reason,source_boot=self.source,first_withdrawal=self.first_withdrawal)


def diagnostic_operator(actual):
    """Bounded public metadata; ownership nonce stays in the private owner file."""
    if not isinstance(actual,dict):return None
    view={name:actual[name] for name in ('agent_boot_id','microphone_epoch','microphone_enabled','capture_active','phase','listening') if name in actual}
    view['microphone_owner_present']=actual.get('microphone_owner_id') is not None if 'microphone_owner_id' in actual else None
    view['microphone_state_error']=None if not actual.get('microphone_state_error') else 'operator_error'
    policy=actual.get('motion_policy')
    if isinstance(policy,dict):view['motion_policy']={name:policy[name] for name in ('epoch','quiet','privacy_all','motor_enabled') if name in policy}
    return view
