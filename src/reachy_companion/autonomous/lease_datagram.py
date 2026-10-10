"""Finite authenticated challenge/renewal datagrams for the device audio lease.

Challenges expire on the device clock after 100 ms and are consumed once.
Neither hello nor a delayed renewal can revive a withdrawn device owner.
"""
import hashlib
from collections import Counter,deque
import hmac
import json
import secrets
import socket
import threading
import time
from urllib.parse import urlsplit
from .contracts import decode


def key(token,boot):return hmac.new(token.encode(),('audio-lease:'+boot).encode(),hashlib.sha256).digest()


def signed(secret,body):
    payload=json.dumps(body,separators=(',',':'),sort_keys=True).encode()
    return json.dumps(dict(body=body,mac=hmac.new(secret,payload,hashlib.sha256).hexdigest()),separators=(',',':')).encode()


def verified(secret,raw):
    if len(raw)>8192:raise ValueError('Datagram cap')
    envelope=decode(raw)
    if set(envelope)!={'body','mac'} or not isinstance(envelope['body'],dict) or not isinstance(envelope['mac'],str):
        raise ValueError('Datagram envelope')
    payload=json.dumps(envelope['body'],separators=(',',':'),sort_keys=True).encode()
    if not hmac.compare_digest(envelope['mac'],hmac.new(secret,payload,hashlib.sha256).hexdigest()):
        raise ValueError('Datagram authentication')
    return envelope['body']


class LeaseDatagramServer:
    def __init__(self,peer,token,bind,port):
        self.peer=peer;self.secret=key(token,peer.boot_id);self.nonces={};self.last_sequence=-1
        self.diagnostics_lock=threading.Lock();self.rejection_tail=deque(maxlen=8);self.first_withdrawal=None;self.last_accepted=None
        self.handling_tail=deque(maxlen=16);self.last_worker_step=None;self.max_worker_loop_gap_ms=0;self.max_handle_ms=0
        self.received=0;self.accepted=0;self.rejections=Counter();self.last_received=None;self.max_packet_gap_ms=0
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.socket.bind((bind,port));self.socket.settimeout(.05)
        self.stop=threading.Event()
        if hasattr(peer,'on_close'):peer.on_close(self.withdrawal)
        self.worker=threading.Thread(target=self.run,daemon=True);self.worker.start()
    def handle(self,body):
        now=self.peer.clock()
        if body.get('source_boot')!=self.peer.boot_id or body.get('controller')!=self.peer.controller:
            raise ValueError('Datagram source/controller')
        if not self.peer.operator_ready():raise RuntimeError('Device permission withdrawn')
        self.nonces={nonce:deadline for nonce,deadline in self.nonces.items() if now<deadline}
        if body.get('kind')=='hello':
            if set(body)!={'kind','source_boot','controller','echo'} or not isinstance(body['echo'],str) or len(body['echo'])!=32:
                raise ValueError('Challenge request')
            if len(self.nonces)>=4:raise RuntimeError('Bounded challenge slots')
            nonce=secrets.token_hex(16);self.nonces[nonce]=now+.1
            return dict(kind='challenge',source_boot=self.peer.boot_id,nonce=nonce,echo=body['echo'])
        if body.get('kind')!='renew' or set(body)!={'kind','source_boot','controller','nonce','sequence'}:
            raise ValueError('Typed renewal')
        sequence=body['sequence'];nonce=body['nonce']
        if (type(sequence) is not int or not 0<=sequence<2**63 or sequence<=self.last_sequence
                or not isinstance(nonce,str) or nonce not in self.nonces):raise ValueError('Fresh renewal required')
        deadline=self.nonces.pop(nonce)
        with self.peer.lock:
            if self.peer.clock()>=deadline:raise ValueError('Challenge expired')
            self.peer.dispatch('/lease',dict(controller=self.peer.controller))
            with self.diagnostics_lock:
                self.last_sequence=sequence;self.last_accepted=self.peer.clock();self.accepted+=1
        return dict(kind='accepted',source_boot=self.peer.boot_id,sequence=sequence)
    def run(self):
        while not self.stop.is_set():
            step=self.peer.clock()
            with self.diagnostics_lock:
                if self.last_worker_step is not None:self.max_worker_loop_gap_ms=max(self.max_worker_loop_gap_ms,(step-self.last_worker_step)*1000)
                self.last_worker_step=step
            phase='receive';sequence=None;began=None
            try:
                raw,address=self.socket.recvfrom(8193)
                now=self.peer.clock()
                with self.diagnostics_lock:
                    if self.last_received is not None:self.max_packet_gap_ms=max(self.max_packet_gap_ms,(now-self.last_received)*1000)
                    self.last_received=now;self.received+=1
                began=now;body=verified(self.secret,raw)
                phase='verified_'+body.get('kind') if body.get('kind') in ('hello','renew') else 'verified_invalid'
                value=body.get('sequence');sequence=value if type(value) is int and 0<=value<2**63 else None
                self.record_handling(phase,sequence)
                answer=self.handle(body);handled=self.peer.clock()
                with self.diagnostics_lock:self.max_handle_ms=max(self.max_handle_ms,(handled-began)*1000)
                phase='challenge_send' if answer['kind']=='challenge' else 'ack_send'
                self.record_handling(phase,sequence,handle_ms=(handled-began)*1000)
                self.socket.sendto(signed(self.secret,answer),address)
                self.record_handling('challenge_sent' if answer['kind']=='challenge' else 'ack_sent',sequence,
                    handle_ms=(handled-began)*1000,response_send_ms=(self.peer.clock()-handled)*1000)
            except socket.timeout:pass
            except (ValueError,RuntimeError) as exc:
                known=('Datagram cap','Datagram envelope','Datagram authentication','Datagram source/controller',
                    'Device permission withdrawn','Challenge request','Bounded challenge slots','Typed renewal',
                    'Fresh renewal required','Challenge expired','Controller lease withdrawn')
                reason=str(exc) if str(exc) in known else type(exc).__name__
                self.reject(reason);self.record_handling('failed:'+phase,sequence,error_kind=reason)
            except (OSError,TypeError,KeyError) as exc:
                self.reject(type(exc).__name__);self.record_handling('failed:'+phase,sequence,error_kind=type(exc).__name__)
    def record_handling(self,phase,sequence,**metadata):
        with self.diagnostics_lock:self.handling_tail.append(dict(at=self.peer.clock(),phase=phase,sequence=sequence,**metadata))
    def reject(self,reason):
        with self.diagnostics_lock:
            self.rejections[reason]+=1;self.rejection_tail.append((self.peer.clock(),reason))
    def timing(self,now):
        return dict(source_boot=self.peer.boot_id,ack_sequence=self.last_sequence,
            last_receive_age_ms=None if self.last_received is None else max(0,(now-self.last_received)*1000),
            last_accepted_age_ms=None if self.last_accepted is None else max(0,(now-self.last_accepted)*1000),
            rejection_tail=[dict(age_ms=max(0,(now-at)*1000),reason=reason) for at,reason in self.rejection_tail],
            handling_tail=[dict(age_ms=max(0,(now-item['at'])*1000),**{name:value for name,value in item.items() if name!='at'}) for item in self.handling_tail],
            max_handle_ms=self.max_handle_ms,max_worker_loop_gap_ms=self.max_worker_loop_gap_ms)
    def withdrawal(self,now):
        with self.diagnostics_lock:
            if self.first_withdrawal is None:self.first_withdrawal=self.timing(now)
            return dict(datagram=self.first_withdrawal)
    def status(self):
        with self.diagnostics_lock:return dict(received=self.received,accepted=self.accepted,rejections=dict(self.rejections),
            max_packet_gap_ms=self.max_packet_gap_ms,last_sequence=self.last_sequence,execution_busy=self.worker.is_alive(),
            timing=self.timing(self.peer.clock()),first_withdrawal=self.first_withdrawal)
    def close(self):
        self.stop.set();self.worker.join(timeout=.1);self.socket.close();self.nonces.clear()


class DatagramRenewal:
    """One actual two-packet exchange slot; no retry of expired challenges."""
    def __init__(self,client,source_boot,port):
        endpoint=urlsplit(client.url)
        self.last_send=None;self.last_ack=None;self.ack_sequence=None
        self.diagnostics_lock=threading.Lock();self.exchange_phase='idle';self.exchange_tail=deque(maxlen=16)
        self.attempts=0;self.attempt_started=None;self.first_failed_attempt=None;self.last_receive=None
        self.source=source_boot;self.controller=client.controller;self.secret=key(client.token,source_boot);self.sequence=0
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.socket.connect((endpoint.hostname,port));self.socket.settimeout(.04)
    def receive(self):
        raw=self.socket.recv(8193);self.last_receive=time.monotonic()
        return verified(self.secret,raw)
    def record(self,phase,error_kind=None):
        with self.diagnostics_lock:
            self.exchange_phase=phase
            self.exchange_tail.append(dict(at=time.monotonic(),phase=phase,sequence=self.sequence,attempt=self.attempts,error_kind=error_kind))
    def renew(self):
        with self.diagnostics_lock:self.attempts+=1;self.attempt_started=time.monotonic()
        try:self.exchange()
        except Exception as exc:
            phase=self.exchange_phase;kind=type(exc).__name__
            self.record('failed:'+phase,kind)
            with self.diagnostics_lock:
                if self.first_failed_attempt is None:
                    now=time.monotonic()
                    self.first_failed_attempt=dict(source_boot=self.source,attempt=self.attempts,phase=phase,
                        sequence=self.sequence,ack_sequence=self.ack_sequence,error_kind=kind,
                        elapsed_ms=max(0,(now-self.attempt_started)*1000),
                        last_send_age_ms=None if self.last_send is None else max(0,(now-self.last_send)*1000),
                        last_receive_age_ms=None if self.last_receive is None else max(0,(now-self.last_receive)*1000),
                        last_ack_age_ms=None if self.last_ack is None else max(0,(now-self.last_ack)*1000))
            raise
    def exchange(self):
        self.record('drain')
        self.socket.setblocking(False)
        for _ in range(8):
            try:self.socket.recv(8193)
            except BlockingIOError:break
        self.socket.settimeout(.04)
        began=time.monotonic();echo=secrets.token_hex(16)
        self.record('hello_send');self.last_send=time.monotonic()
        self.socket.send(signed(self.secret,dict(kind='hello',source_boot=self.source,controller=self.controller,echo=echo)))
        self.record('challenge_wait');challenge=self.receive()
        if (challenge.get('kind')!='challenge' or challenge.get('source_boot')!=self.source
                or challenge.get('echo')!=echo or time.monotonic()-began>=.08):raise ValueError('Fresh challenge required')
        self.sequence+=1
        self.record('renew_send');self.last_send=time.monotonic()
        self.socket.send(signed(self.secret,dict(kind='renew',source_boot=self.source,controller=self.controller,
            nonce=challenge['nonce'],sequence=self.sequence)))
        self.record('ack_wait');ack=self.receive()
        if ack!=dict(kind='accepted',source_boot=self.source,sequence=self.sequence):raise ValueError('Renewal acknowledgement')
        self.last_ack=time.monotonic();self.ack_sequence=self.sequence;self.record('accepted')
    def status(self):
        now=time.monotonic()
        with self.diagnostics_lock:
            tail=[dict(age_ms=max(0,(now-item['at'])*1000),phase=item['phase'],sequence=item['sequence'],attempt=item['attempt'],error_kind=item['error_kind']) for item in self.exchange_tail]
            phase=self.exchange_phase
        return dict(source_boot=self.source,sequence=self.sequence,ack_sequence=self.ack_sequence,attempts=self.attempts,first_failed_attempt=self.first_failed_attempt,exchange_phase=phase,exchange_tail=tail,
            last_receive_age_ms=None if self.last_receive is None else max(0,(now-self.last_receive)*1000),
            last_send_age_ms=None if self.last_send is None else max(0,(now-self.last_send)*1000),
            last_ack_age_ms=None if self.last_ack is None else max(0,(now-self.last_ack)*1000))
    def close(self):self.socket.close()
