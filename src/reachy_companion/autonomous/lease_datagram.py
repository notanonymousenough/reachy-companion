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
            try:
                raw,address=self.socket.recvfrom(8193)
                now=self.peer.clock()
                with self.diagnostics_lock:
                    if self.last_received is not None:self.max_packet_gap_ms=max(self.max_packet_gap_ms,(now-self.last_received)*1000)
                    self.last_received=now;self.received+=1
                answer=self.handle(verified(self.secret,raw))
                self.socket.sendto(signed(self.secret,answer),address)
            except socket.timeout:pass
            except (ValueError,RuntimeError) as exc:
                known=('Datagram cap','Datagram envelope','Datagram authentication','Datagram source/controller',
                    'Device permission withdrawn','Challenge request','Bounded challenge slots','Typed renewal',
                    'Fresh renewal required','Challenge expired','Controller lease withdrawn')
                reason=str(exc) if str(exc) in known else type(exc).__name__
                self.reject(reason)
            except (OSError,TypeError,KeyError) as exc:self.reject(type(exc).__name__)
    def reject(self,reason):
        with self.diagnostics_lock:
            self.rejections[reason]+=1;self.rejection_tail.append((self.peer.clock(),reason))
    def timing(self,now):
        return dict(source_boot=self.peer.boot_id,ack_sequence=self.last_sequence,
            last_receive_age_ms=None if self.last_received is None else max(0,(now-self.last_received)*1000),
            last_accepted_age_ms=None if self.last_accepted is None else max(0,(now-self.last_accepted)*1000),
            rejection_tail=[dict(age_ms=max(0,(now-at)*1000),reason=reason) for at,reason in self.rejection_tail])
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
        self.source=source_boot;self.controller=client.controller;self.secret=key(client.token,source_boot);self.sequence=0
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.socket.connect((endpoint.hostname,port));self.socket.settimeout(.04)
    def receive(self):return verified(self.secret,self.socket.recv(8193))
    def renew(self):
        self.socket.setblocking(False)
        for _ in range(8):
            try:self.socket.recv(8193)
            except BlockingIOError:break
        self.socket.settimeout(.04)
        began=time.monotonic();echo=secrets.token_hex(16)
        self.last_send=time.monotonic()
        self.socket.send(signed(self.secret,dict(kind='hello',source_boot=self.source,controller=self.controller,echo=echo)))
        challenge=self.receive()
        if (challenge.get('kind')!='challenge' or challenge.get('source_boot')!=self.source
                or challenge.get('echo')!=echo or time.monotonic()-began>=.08):raise ValueError('Fresh challenge required')
        self.sequence+=1
        self.last_send=time.monotonic()
        self.socket.send(signed(self.secret,dict(kind='renew',source_boot=self.source,controller=self.controller,
            nonce=challenge['nonce'],sequence=self.sequence)))
        ack=self.receive()
        if ack!=dict(kind='accepted',source_boot=self.source,sequence=self.sequence):raise ValueError('Renewal acknowledgement')
        self.last_ack=time.monotonic();self.ack_sequence=self.sequence
    def status(self):
        now=time.monotonic()
        return dict(source_boot=self.source,sequence=self.sequence,ack_sequence=self.ack_sequence,
            last_send_age_ms=None if self.last_send is None else max(0,(now-self.last_send)*1000),
            last_ack_age_ms=None if self.last_ack is None else max(0,(now-self.last_ack)*1000))
    def close(self):self.socket.close()
