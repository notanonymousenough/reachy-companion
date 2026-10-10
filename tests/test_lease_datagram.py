import threading
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

    def test_actual_udp_exchange_does_not_renew_after_scheduler_stall(self):
        actual=dict(agent_boot_id='agent',microphone_epoch=2,microphone_owner_id='owner',microphone_enabled=True,
            phase='paused',listening=False,motion_policy=dict(epoch=1,quiet=False,privacy_all=False))
        peer=AudioPeer(Playback(ReplayPCM(),allow_simulated=True),lambda:actual,
            dict(agent_boot_id='agent',owned_microphone_epoch=2,owner_id='owner',policy_epoch=1),controller='controller')
        self.addCleanup(peer.close)
        end=time.monotonic()+1
        while not peer.permitted() and time.monotonic()<end:time.sleep(.002)
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
        lease.tick();time.sleep(.05);self.assertEqual(peer.lease_requests,requests)
        lease.close();lease.worker.join(timeout=.2);self.assertFalse(lease.status()['execution_busy'])


if __name__=='__main__':unittest.main()
