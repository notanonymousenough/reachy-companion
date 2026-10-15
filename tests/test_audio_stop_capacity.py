"""Real HTTP capacity/ownership tests; simulated backend, no device access."""
import concurrent.futures
import http.client
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch

from reachy_companion.autonomous.audio_peer import AudioPeer, PeerClient, RemotePCM, create_server
from reachy_companion.autonomous.playback import Playback, ReplayPCM


def wait(predicate):
    end=time.monotonic()+2
    while not predicate():
        if time.monotonic()>end:raise AssertionError('Condition did not complete')
        time.sleep(.002)


class Backend(ReplayPCM):
    @property
    def stream(self):return self.current


class StopCapacityTests(unittest.TestCase):
    def setup_peer(self,backend=None):
        backend=backend or Backend()
        operator=dict(agent_boot_id='agent',microphone_epoch=2,microphone_owner_id='owner',
            microphone_enabled=True,microphone_state_error=None,phase='paused',listening=False,
            motion_policy=dict(epoch=1,quiet=False,privacy_all=False))
        peer=AudioPeer(Playback(backend,allow_simulated=True,stop_timeout=.03),lambda:operator,
            dict(agent_boot_id='agent',owned_microphone_epoch=2,owner_id='owner',policy_epoch=1),controller='controller')
        self.addCleanup(peer.close)
        wait(peer.operator_ready)
        peer.dispatch('/lease',dict(controller='controller'))
        wait(lambda:not peer.playback.status()['execution_busy'])
        halted=threading.Event()
        def heartbeat():
            while not halted.wait(.02):
                try:peer.dispatch('/lease',dict(controller='controller'))
                except RuntimeError:return
        worker=threading.Thread(target=heartbeat);worker.start()
        def cleanup():
            halted.set();worker.join(1);peer.close();peer.watch.join(1)
            wait(lambda:not peer.playback.status()['execution_busy'])
            self.assertFalse(worker.is_alive());self.assertFalse(peer.watch.is_alive())
        self.addCleanup(cleanup)
        return peer,backend

    def serve(self,peer):
        server=create_server(peer,'t'*32,port=0,stop_port=0)
        worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});worker.start()
        wait(lambda:server.entered.is_set())
        def cleanup():
            server.shutdown();server.server_close();worker.join(1)
            wait(lambda:server.transport_status()['media_handlers']==server.transport_status()['stop_handlers']==0)
            self.assertFalse(worker.is_alive());self.assertFalse(server.transport_status()['stop_listener_busy'])
        self.addCleanup(cleanup)
        client=PeerClient('http://127.0.0.1:'+str(server.server_address[1]),'t'*32,'controller',timeout=.6)
        return server,client,client.at_port(server.stop_address[1])

    def post(self,port,path,body,token='t'*32,timeout=1):
        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
        try:
            connection.request('POST',path,json.dumps(body),{'Authorization':'Bearer '+token,'Connection':'close'})
            response=connection.getresponse();raw=response.read()
            return response.status,raw
        finally:connection.close()

    def test_four_held_media_handlers_do_not_block_stop_or_accept_late_writes(self):
        peer,backend=self.setup_peer();server,client,control=self.serve(peer)
        client.call('/reserve',stream_id='stream')
        release=threading.Event();self.addCleanup(release.set)
        original=peer.dispatch
        def held(path,body):
            if path=='/write':release.wait(2)
            return original(path,body)
        peer.dispatch=held
        pool=concurrent.futures.ThreadPoolExecutor(4)
        try:
            writes=[pool.submit(self.post,server.server_address[1],'/write',
                dict(controller='controller',stream_id='stream',pcm_base64='AAA=')) for _ in range(4)]
            wait(lambda:server.transport_status()['media_handlers']==4)
            # Architect's original failure: the fifth media connection is reset.
            with self.assertRaises((OSError,http.client.HTTPException)):
                self.post(server.server_address[1],'/stop',dict(controller='controller'))
            generation=peer.playback.generation
            receipt=control.call('/stop',source_boot=peer.boot_id)
            self.assertTrue(peer.closed);self.assertGreater(peer.playback.generation,generation)
            self.assertTrue(receipt['stop_known'])
            self.assertEqual(server.transport_status()['media_handlers'],4)
            release.set()
            self.assertEqual([future.result()[0] for future in writes],[409]*4)
            self.assertEqual(backend.streams[backend.current]['written'],0)
        finally:release.set();pool.shutdown(wait=True)

    def test_remote_stop_never_acquires_media_lock_and_has_no_media_fallback(self):
        peer,_=self.setup_peer();server,client,_=self.serve(peer)
        remote=RemotePCM(client,stop_port=server.stop_address[1],source_boot=peer.boot_id)
        remote.reserve('stream')
        with remote.transport.lock:
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                stopped=pool.submit(remote.stop,'stream')
                self.assertTrue(stopped.result(timeout=.5)['verified_stopped'])
        remote.transport.close()
        with patch.object(remote.stop_client,'call',side_effect=OSError('control unavailable')):
            with patch.object(client,'call',side_effect=AssertionError('media fallback')):
                with self.assertRaises(OSError):remote.stop('stream')

    def test_control_rejects_foreign_bindings_and_routes_but_stops_expired_owner(self):
        peer,_=self.setup_peer();server,client,control=self.serve(peer)
        client.call('/reserve',stream_id='stream');generation=peer.playback.generation
        valid=dict(controller='controller',source_boot=peer.boot_id,stream_id='stream')
        for change in ({'controller':'foreign'},{'source_boot':'old'},{'stream_id':'foreign'},{'extra':True}):
            self.assertEqual(self.post(server.stop_address[1],'/stream-stop',{**valid,**change})[0],409)
            self.assertEqual(peer.playback.generation,generation)
        for route in ('/write','/reserve','/lease','/status','/operator-mute'):
            self.assertEqual(self.post(server.stop_address[1],route,valid)[0],404)
        self.assertEqual(self.post(server.stop_address[1],'/stop',valid,token='foreign')[0],401)
        peer.close('expired')
        self.assertFalse(peer.permitted())
        self.assertTrue(control.call('/stream-stop',source_boot=peer.boot_id,stream_id='stream')['verified_stopped'])

    def test_unknown_backend_stop_keeps_actual_job_busy_and_deduplicated(self):
        release=threading.Event();entered=threading.Event();self.addCleanup(release.set)
        class Held(Backend):
            calls=0
            def stop(self,stream):
                self.calls+=1;entered.set();release.wait(2)
                return super().stop(stream)
        backend=Held();peer,_=self.setup_peer(backend);server,client,control=self.serve(peer)
        client.call('/reserve',stream_id='stream')
        result=control.call('/stream-stop',source_boot=peer.boot_id,stream_id='stream')
        self.assertTrue(entered.is_set());self.assertFalse(result['verified_stopped'])
        self.assertIsNone(result['consumed_frames']);self.assertTrue(result['execution_busy'])
        self.assertTrue(peer.playback.status()['execution_busy'])
        control.call('/stream-stop',source_boot=peer.boot_id,stream_id='stream')
        self.assertEqual(backend.calls,1)
        with self.assertRaises(Exception):client.call('/reserve',stream_id='new')
        release.set();wait(lambda:not peer.playback.status()['execution_busy'])

    def test_delayed_old_stream_stop_cannot_revoke_new_stream(self):
        peer,_=self.setup_peer();_,client,control=self.serve(peer)
        client.call('/reserve',stream_id='old')
        control.call('/stream-stop',source_boot=peer.boot_id,stream_id='old')
        wait(lambda:not peer.playback.status()['execution_busy'])
        client.call('/reserve',stream_id='new');generation=peer.playback.generation
        with self.assertRaises(Exception):control.call('/stream-stop',source_boot=peer.boot_id,stream_id='old')
        self.assertEqual(peer.playback.generation,generation)
        self.assertEqual(peer.playback.active['stream_id'],peer.streams['new'])

    def test_control_capacity_counts_handlers_after_client_timeout(self):
        peer,_=self.setup_peer();server,_,_=self.serve(peer)
        release=threading.Event();self.addCleanup(release.set)
        original=peer.dispatch_stop
        def held(path,body):release.wait(2);return original(path,body)
        peer.dispatch_stop=held
        pool=concurrent.futures.ThreadPoolExecutor(2)
        try:
            futures=[pool.submit(self.post,server.stop_address[1],'/stop',
                dict(controller='controller',source_boot=peer.boot_id),timeout=.05) for _ in range(2)]
            wait(lambda:server.transport_status()['stop_handlers']==2)
            for future in futures:
                with self.assertRaises(TimeoutError):future.result()
            self.assertEqual(server.transport_status()['stop_handlers'],2)
            with self.assertRaises((OSError,http.client.HTTPException)):
                self.post(server.stop_address[1],'/stop',dict(controller='controller',source_boot=peer.boot_id))
        finally:release.set();pool.shutdown(wait=True)

    def test_listener_lifecycle_default_ephemeral_and_partial_start_failure(self):
        peer,_=self.setup_peer()
        default=create_server(peer,'t'*32,port=0)
        self.assertIsNone(default.stop_address);default.shutdown();default.server_close()
        server=create_server(peer,'t'*32,port=0,stop_port=0)
        addresses=(server.server_address,server.stop_address)
        self.assertTrue(all(address[1]>0 for address in addresses))
        with patch('threading.Thread.start',side_effect=RuntimeError('start fixture')):
            with self.assertRaises(RuntimeError):server.serve_forever()
        server.shutdown();server.server_close()
        for address in addresses:
            with socket.socket() as connection:self.assertNotEqual(connection.connect_ex(address),0)
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1',0));occupied.listen()
            with socket.socket() as free:
                free.bind(('127.0.0.1',0));port=free.getsockname()[1]
            with self.assertRaises(OSError):create_server(peer,'t'*32,port=port,stop_port=occupied.getsockname()[1])
            with socket.socket() as reusable:reusable.bind(('127.0.0.1',port))


if __name__=='__main__':unittest.main()
