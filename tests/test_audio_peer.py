import threading
import time
import unittest
from reachy_companion.autonomous.audio_peer import AudioPeer, PeerClient, PeerLease, RemotePCM, create_server
from reachy_companion.autonomous.playback import Playback, ReplayPCM


def wait(predicate):
    end=time.monotonic()+1
    while not predicate():
        if time.monotonic()>=end:raise AssertionError('Finite condition timeout')
        time.sleep(.002)


class Backend(ReplayPCM):
    @property
    def stream(self):return self.current


class PeerTests(unittest.TestCase):
    def setup_peer(self):
        self.actual=dict(agent_boot_id='agent',microphone_epoch=2,microphone_owner_id='owner',
            microphone_enabled=True,microphone_state_error=None,phase='paused',listening=False,
            motion_policy=dict(epoch=1,quiet=False,privacy_all=False,motor_enabled=False))
        backend=Backend();playback=Playback(backend,allow_simulated=True)
        peer=AudioPeer(playback,lambda:self.actual,
            dict(agent_boot_id='agent',owned_microphone_epoch=2,owner_id='owner',policy_epoch=1),controller='controller')
        self.addCleanup(peer.close);wait(peer.permitted)
        return peer,backend

    def call(self,peer,path,**body):return peer.dispatch(path,dict(controller='controller',**body))

    def test_rpc_queues_but_cursor_is_only_measured_backend_consumption(self):
        peer,backend=self.setup_peer();server=create_server(peer,'t'*32,port=0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        client=PeerClient('http://127.0.0.1:'+str(server.server_address[1]),'t'*32,'controller')
        client.call('/lease');remote=RemotePCM(client);remote.reserve('stream');remote.start('stream',16000)
        self.assertEqual(remote.write('stream',b'\0\0'*100),100)
        wait(lambda:backend.streams[backend.current]['written']==100)
        self.assertEqual(remote.progress('stream')['consumed_frames'],0)
        backend.advance(backend.current,30)
        self.assertEqual(remote.progress('stream')['consumed_frames'],30)
        stop=remote.stop('stream');self.assertTrue(stop['verified_stopped'])
        self.assertEqual(stop['consumed_frames'],30)
        self.assertFalse(peer.playback.status()['resumable'])

    def test_operator_withdrawal_closes_owner_and_rejects_delayed_pcm(self):
        peer,backend=self.setup_peer();self.call(peer,'/lease');self.call(peer,'/reserve',stream_id='stream')
        self.actual={**self.actual,'microphone_epoch':3,'microphone_owner_id':None,'microphone_enabled':False}
        wait(lambda:peer.closed)
        with self.assertRaises(RuntimeError):self.call(peer,'/write',stream_id='stream',pcm_base64='AAA=')
        wait(lambda:not peer.playback.status()['execution_busy'])
        self.assertTrue(peer.playback.status()['stop_known'])

    def test_controller_expiry_is_independent_of_hub_and_closes_capture_mailbox(self):
        peer,backend=self.setup_peer();self.call(peer,'/lease')
        self.assertTrue(peer.publish(b'\0\0',time.monotonic(),None))
        wait(lambda:peer.closed)
        self.assertIsNone(peer.observation)
        with self.assertRaises(RuntimeError):self.call(peer,'/lease')

    def test_latest_only_observation_and_fixed_controller(self):
        peer,backend=self.setup_peer()
        peer.publish(b'\1\0',time.monotonic(),None);peer.publish(b'\2\0',time.monotonic(),'playback')
        packet=self.call(peer,'/observation')['observation']
        self.assertEqual(packet['sequence'],2);self.assertEqual(packet['echo_reference'],'playback')
        self.assertIsNone(self.call(peer,'/observation')['observation'])
        with self.assertRaises(ValueError):peer.dispatch('/status',dict(controller='foreign'))

    def test_persistent_heartbeat_reuses_socket_and_scheduler_stall_expires(self):
        peer,_=self.setup_peer();server=create_server(peer,'t'*32,port=0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        client=PeerClient('http://127.0.0.1:'+str(server.server_address[1]),'t'*32,'controller')
        lease=PeerLease(client);self.addCleanup(lease.close)
        wait(lambda:peer.lease_requests>=2)
        socket=lease.connection.sock
        end=time.monotonic()+.45
        while time.monotonic()<end:
            lease.tick();time.sleep(.005)
        self.assertIs(lease.connection.sock,socket)
        self.assertGreater(peer.lease_requests,10)
        self.assertFalse(peer.closed)
        wait(lambda:peer.closed)
        self.assertEqual(peer.close_reason,'controller_expired')
        requests=peer.lease_requests
        lease.tick();time.sleep(.05)
        self.assertEqual(peer.lease_requests,requests)
        lease.close();wait(lambda:not lease.status()['execution_busy'])

    def test_private_lan_requires_explicit_owner_opt_in(self):
        with self.assertRaises(ValueError):PeerClient('http://192.168.2.158:8780','t'*32,'owner')
        peer=PeerClient('http://192.168.2.158:8780','t'*32,'owner',trusted_private_lan=True)
        self.assertEqual(peer.url,'http://192.168.2.158:8780')
        for url in ('http://8.8.8.8:8780','http://user@192.168.2.158:8780','http://192.168.2.158:8780/arbitrary'):
            with self.assertRaises(ValueError):PeerClient(url,'t'*32,'owner',trusted_private_lan=True)


if __name__=='__main__':unittest.main()
