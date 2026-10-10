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
        self.addCleanup(peer.close);wait(peer.operator_ready)
        return peer,backend

    def call(self,peer,path,**body):
        result=peer.dispatch(path,dict(controller='controller',**body))
        if path=='/lease':wait(lambda:not peer.playback.status()['execution_busy'])
        return result

    def test_rpc_queues_but_cursor_is_only_measured_backend_consumption(self):
        peer,backend=self.setup_peer();server=create_server(peer,'t'*32,port=0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        client=PeerClient('http://127.0.0.1:'+str(server.server_address[1]),'t'*32,'controller')
        client.call('/lease');wait(lambda:not peer.playback.status()['execution_busy']);remote=RemotePCM(client);remote.reserve('stream');remote.start('stream',16000)
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
        peer,backend=self.setup_peer();self.call(peer,'/lease')
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

    def test_startup_only_allows_control_until_first_controller_lease(self):
        peer,backend=self.setup_peer()
        self.assertFalse(peer.permitted())
        self.assertFalse(peer.publish(b'\0\0',time.monotonic(),None))
        with self.assertRaises(RuntimeError):self.call(peer,'/reserve',stream_id='early')
        time.sleep(.35)
        self.assertTrue(peer.operator_ready());self.assertFalse(peer.closed)
        self.assertFalse(backend.streams);self.assertEqual(peer.lease_requests,0)
        self.call(peer,'/lease');wait(peer.permitted)
        self.call(peer,'/reserve',stream_id='fresh')
        self.assertTrue(backend.streams)

    def test_malformed_or_failed_operator_closes_watch_and_output(self):
        valid=dict(agent_boot_id='agent',microphone_epoch=2,microphone_owner_id='owner',microphone_enabled=True,
            microphone_state_error=None,phase='paused',listening=False,motion_policy=dict(epoch=1,quiet=False,privacy_all=False))
        invalids=[{'motion_policy':{}},None,{'microphone_enabled':1},'unknown',
            {**valid,'microphone_enabled':1},{**valid,'microphone_epoch':True},{**valid,'listening':0}]
        invalids.extend({**valid,'motion_policy':{**valid['motion_policy'],name:value}}
                       for name,value in (('epoch',True),('quiet',0),('privacy_all',0)))
        for invalid in invalids:
            with self.subTest(invalid=invalid):
                peer,backend=self.setup_peer();self.call(peer,'/lease')
                self.actual=invalid;wait(lambda:peer.closed)
                wait(lambda:peer.watch_exited)
                wait(lambda:peer.playback.status()['stop_known'])
                self.assertFalse(peer.permitted());self.assertFalse(peer.publish(b'\0\0',time.monotonic(),None))
                self.assertIn(peer.close_reason,('operator_invalid','operator_unknown'))
                self.assertIsNotNone(peer.watch_error)
        peer,_=self.setup_peer();self.call(peer,'/lease')
        def failed():raise OSError('fixture')
        peer.operator=failed;wait(lambda:peer.closed)
        self.assertEqual(peer.close_reason,'operator_unknown')

    def test_private_lan_requires_explicit_owner_opt_in(self):
        with self.assertRaises(ValueError):PeerClient('http://192.168.2.158:8780','t'*32,'owner')
        peer=PeerClient('http://192.168.2.158:8780','t'*32,'owner',trusted_private_lan=True)
        self.assertEqual(peer.url,'http://192.168.2.158:8780')
        for url in ('http://8.8.8.8:8780','http://user@192.168.2.158:8780','http://192.168.2.158:8780/arbitrary'):
            with self.assertRaises(ValueError):PeerClient(url,'t'*32,'owner',trusted_private_lan=True)


if __name__=='__main__':unittest.main()
