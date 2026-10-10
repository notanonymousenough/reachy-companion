import threading
import json
import socket
import time
import unittest
from reachy_companion.autonomous.audio_peer import AudioPeer,PeerClient,PeerLease
from reachy_companion.autonomous.lease_datagram import LeaseDatagramServer,DatagramRenewal,key,signed,verified
from reachy_companion.autonomous.playback import Playback,ReplayPCM


class Peer:
    boot_id='boot';controller='owner'
    def __init__(self):self.now=0;self.lock=threading.RLock();self.active=True;self.calls=0
    def clock(self):return self.now
    def permitted(self):return self.active
    def operator_ready(self):return self.active
    def dispatch(self,path,body):
        if not self.active:raise RuntimeError('Withdrawn')
        self.calls+=1


class DatagramTests(unittest.TestCase):
    def test_challenge_expiry_single_use_sequence_and_withdrawal(self):
        peer=Peer();server=LeaseDatagramServer(peer,'t'*32,'127.0.0.1',0);self.addCleanup(server.close)
        def hello():return server.handle(dict(kind='hello',source_boot='boot',controller='owner',echo='e'*32))
        challenge=hello();peer.now=.11
        with self.assertRaises(ValueError):server.handle(dict(kind='renew',source_boot='boot',controller='owner',nonce=challenge['nonce'],sequence=0))
        self.assertEqual(peer.calls,0)
        challenge=hello();renew=dict(kind='renew',source_boot='boot',controller='owner',nonce=challenge['nonce'],sequence=1)
        server.handle(renew)
        with self.assertRaises(ValueError):server.handle(renew)
        challenge=hello()
        with self.assertRaises(ValueError):server.handle(dict(renew,nonce=challenge['nonce']))
        peer.active=False
        with self.assertRaises(RuntimeError):server.handle(dict(renew,nonce=challenge['nonce'],sequence=2))
        self.assertEqual(peer.calls,1)

    def test_mac_scope_tampering_and_bounded_challenges(self):
        secret=key('t'*32,'boot');packet=signed(secret,dict(kind='hello'))
        self.assertEqual(verified(secret,packet),dict(kind='hello'))
        for other in (key('u'*32,'boot'),key('t'*32,'retired')):
            with self.assertRaises(ValueError):verified(other,packet)
        with self.assertRaises(ValueError):verified(secret,packet.replace(b'hello',b'renew'))
        peer=Peer();server=LeaseDatagramServer(peer,'t'*32,'127.0.0.1',0);self.addCleanup(server.close)
        body=dict(kind='hello',source_boot='boot',controller='owner',echo='e'*32)
        for _ in range(4):server.handle(body)
        with self.assertRaises(RuntimeError):server.handle(body)
        peer.now=.11;server.handle(body);self.assertEqual(len(server.nonces),1)

    def test_exchange_phase_failure_tail_is_bounded_and_contains_no_secrets(self):
        client=PeerClient('http://127.0.0.1:1','t'*32,'controller')
        transport=DatagramRenewal(client,'source',1);transport.socket.close()
        class NoReplies:
            def setblocking(self,value):self.blocking=value
            def settimeout(self,value):self.blocking=True
            def send(self,raw):return len(raw)
            def recv(self,size):
                if not self.blocking:raise BlockingIOError()
                raise socket.timeout()
            def close(self):pass
        transport.socket=NoReplies()
        first=None
        for _ in range(10):
            with self.assertRaises(socket.timeout):transport.renew()
            if first is None:first=transport.status()['first_failed_attempt']
            self.assertEqual(transport.status()['first_failed_attempt'],first)
        status=transport.status();self.assertEqual(len(status['exchange_tail']),16)
        self.assertEqual(status['exchange_phase'],'failed:challenge_wait')
        self.assertEqual(status['exchange_tail'][-1]['error_kind'],'TimeoutError')
        self.assertIsNone(status['ack_sequence']);self.assertIsNotNone(status['last_send_age_ms'])
        self.assertEqual(status['attempts'],10);self.assertEqual(first['attempt'],1)
        self.assertEqual(first['phase'],'challenge_wait');self.assertEqual(first['error_kind'],'TimeoutError')
        self.assertNotIn('t'*32,json.dumps(status))
        self.assertNotIn('nonce',json.dumps(status));self.assertNotIn('mac',json.dumps(status))

    def test_lost_ack_first_failure_is_preserved_and_fresh_next_exchange_succeeds(self):
        peer=Peer();server=LeaseDatagramServer(peer,'t'*32,'127.0.0.1',0);self.addCleanup(server.close)
        client=PeerClient('http://127.0.0.1:1','t'*32,'owner')
        transport=DatagramRenewal(client,'boot',1);transport.socket.close()
        class LocalExchange:
            def __init__(self):self.answer=None;self.drop_ack=True
            def setblocking(self,value):self.blocking=value
            def settimeout(self,value):self.blocking=True
            def send(self,raw):
                self.answer=server.handle(verified(transport.secret,raw));return len(raw)
            def recv(self,size):
                if not self.blocking or self.answer is None:raise BlockingIOError()
                answer,self.answer=self.answer,None
                if answer['kind']=='accepted' and self.drop_ack:
                    self.drop_ack=False;raise socket.timeout()
                return signed(transport.secret,answer)
            def close(self):pass
        transport.socket=LocalExchange()
        with self.assertRaises(socket.timeout):transport.renew()
        failed=transport.status()['first_failed_attempt']
        self.assertEqual(failed['phase'],'ack_wait');self.assertEqual(failed['sequence'],1)
        self.assertEqual(peer.calls,1);self.assertIsNone(transport.status()['ack_sequence'])
        transport.renew()
        self.assertEqual(peer.calls,2);self.assertEqual(transport.status()['ack_sequence'],2)
        self.assertEqual(transport.status()['first_failed_attempt'],failed)
        self.assertEqual(transport.status()['attempts'],2)
        self.assertNotIn('nonce',json.dumps(transport.status()))

    def test_late_previous_ack_is_rejected_during_current_challenge_without_renewal(self):
        client=PeerClient('http://127.0.0.1:1','t'*32,'owner')
        transport=DatagramRenewal(client,'boot',1);transport.socket.close();sent=[]
        class LateAck:
            def setblocking(self,value):self.blocking=value
            def settimeout(self,value):self.blocking=True
            def send(self,raw):sent.append(verified(transport.secret,raw)['kind']);return len(raw)
            def recv(self,size):
                if not self.blocking:raise BlockingIOError()
                return signed(transport.secret,dict(kind='accepted',source_boot='boot',sequence=0))
            def close(self):pass
        transport.socket=LateAck()
        with self.assertRaises(ValueError):transport.renew()
        self.assertEqual(sent,['hello']);self.assertEqual(transport.sequence,0)
        failed=transport.status()['first_failed_attempt']
        self.assertEqual(failed['phase'],'challenge_wait');self.assertEqual(failed['error_kind'],'ValueError')

    def test_actual_udp_exchange_does_not_renew_after_scheduler_stall(self):
        actual=dict(agent_boot_id='agent',microphone_epoch=2,microphone_owner_id='owner',microphone_enabled=True,
            phase='paused',listening=False,motion_policy=dict(epoch=1,quiet=False,privacy_all=False))
        peer=AudioPeer(Playback(ReplayPCM(),allow_simulated=True),lambda:actual,
            dict(agent_boot_id='agent',owned_microphone_epoch=2,owner_id='owner',policy_epoch=1),controller='controller')
        self.addCleanup(peer.close)
        end=time.monotonic()+1
        while not peer.operator_ready() and time.monotonic()<end:time.sleep(.002)
        server=LeaseDatagramServer(peer,'t'*32,'127.0.0.1',0);self.addCleanup(server.close)
        client=PeerClient('http://127.0.0.1:1','t'*32,'controller')
        transport=DatagramRenewal(client,peer.boot_id,server.socket.getsockname()[1])
        lease=PeerLease(client,datagram=transport);self.addCleanup(lease.close)
        end=time.monotonic()+.45
        while time.monotonic()<end:lease.tick();time.sleep(.005)
        self.assertGreater(peer.lease_requests,10);self.assertFalse(peer.closed)
        end=time.monotonic()+1
        while not peer.closed and time.monotonic()<end:time.sleep(.005)
        self.assertTrue(peer.closed);requests=peer.lease_requests
        frozen=server.status()['first_withdrawal']
        self.assertEqual(frozen['source_boot'],peer.boot_id)
        self.assertEqual(frozen['ack_sequence'],server.last_sequence)
        self.assertGreaterEqual(frozen['last_accepted_age_ms'],300)
        self.assertGreaterEqual(frozen['last_receive_age_ms'],0)
        phases=[item['phase'] for item in frozen['handling_tail']]
        self.assertIn('verified_renew',phases);self.assertIn('ack_sent',phases)
        self.assertLessEqual(len(phases),16);self.assertGreaterEqual(frozen['max_handle_ms'],0)
        self.assertNotIn('nonce',json.dumps(frozen));self.assertNotIn('t'*32,json.dumps(frozen))
        time.sleep(.02);self.assertEqual(server.status()['first_withdrawal'],frozen)
        lease.tick();time.sleep(.05);self.assertEqual(peer.lease_requests,requests)
        lease.close();lease.worker.join(timeout=.2);self.assertFalse(lease.status()['execution_busy'])
        status=lease.status();self.assertEqual(status['worker_exit'],'closed')
        self.assertIsNone(status['worker_exception']);self.assertIsNotNone(status['timing']['last_send_age_ms'])
        self.assertEqual(status['datagram']['ack_sequence'],frozen['ack_sequence'])
        for _ in range(20):server.reject('Datagram authentication')
        self.assertEqual(len(server.status()['timing']['rejection_tail']),8)


if __name__=='__main__':unittest.main()
