"""Local sequenced protocol/real workers with synthetic PCM; no device acceptance."""
import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from reachy_companion.autonomous.audio_peer import AudioPeer,PeerClient,PeerLease,RemotePCM,create_server,owner_binding,stream_identity
from reachy_companion.autonomous.playback import Playback,ReplayPCM
from urllib.error import HTTPError


class FixturePCM(ReplayPCM):
    @property
    def stream(self):return self.current
    def progress(self,stream):
        self.advance(stream,16000);return super().progress(stream)


def wait(predicate,timeout=2):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:time.sleep(.002)
    if not predicate():raise AssertionError('Finite local fixture wait')


class LeaseProtocolTests(unittest.TestCase):
    def setUp(self,start_lease=True):
        self.operator=dict(agent_boot_id='fixture-agent',microphone_epoch=1,microphone_enabled=True,
            microphone_owner_id='fixture-owner',microphone_state_error=None,listening=False,capture_active=False,phase='paused',
            motion_policy=dict(epoch=1,quiet=False,privacy_all=False,motor_enabled=False))
        self.owner=dict(agent_boot_id='fixture-agent',initial_microphone_epoch=0,owned_microphone_epoch=1,owner_id='fixture-owner',policy_epoch=1)
        self.backend=FixturePCM();self.device=Playback(self.backend,allow_simulated=True,chunk_frames=4096)
        self.peer=AudioPeer(self.device,lambda:copy.deepcopy(self.operator),self.owner,controller='fixture-controller',lifetime='lease')
        self.server=create_server(self.peer,'t'*32,bind='127.0.0.1',port=0,stop_port=0)
        self.listener=threading.Thread(target=self.server.serve_forever,daemon=True);self.listener.start()
        self.client=PeerClient('http://127.0.0.1:'+str(self.server.server_address[1]),'t'*32,'fixture-controller')
        self.authority=owner_binding(self.owner);self.lease=PeerLease(self.client,source_boot=self.peer.boot_id,authority=self.authority)
        self.ticking=threading.Event();self.ticking.set()
        def ticks():
            while self.ticking.is_set():self.lease.tick(self.authority);time.sleep(.01)
        self.ticker=threading.Thread(target=ticks,daemon=True)
        if start_lease:self.ticker.start();wait(lambda:self.peer.permitted())
        self.remote=RemotePCM(self.client,stop_port=self.server.stop_address[1],source_boot=self.peer.boot_id,lifetime='lease')
        self.local=Playback(self.remote,allow_simulated=True,chunk_frames=4096)
    def tearDown(self):
        self.ticking.clear()
        if self.ticker.ident is not None:self.ticker.join(1)
        self.lease.close();self.local.close();self.peer.close()
        wait(lambda:not self.local.status()['execution_busy'])
        self.remote.close_transport()
        self.lease.worker.join(1);self.peer.watch.join(1);self.server.shutdown();self.server.server_close();self.listener.join(1)
    def complete(self,request='fixture-request'):
        self.local.operator('fixture-hub',microphone_enabled=True,valid_until=time.monotonic()+2)
        stream=self.local.begin('fixture-hub',request,deadline=time.monotonic()+2)
        self.local.push(stream,b'\x00\x00'*160);self.local.finish(stream)
        wait(lambda:self.local.terminal_receipt() is not None)
        return self.local.terminal_receipt()
    def retire(self,terminal):
        deadline=time.monotonic()+1
        while not self.remote.retire(terminal):
            if time.monotonic()>deadline:raise AssertionError('Terminal refs did not drain')
            time.sleep(.005)
        self.assertFalse(self.remote.admission_ready()) # ACK alone does not release local refs
        self.assertTrue(self.local.retire_terminal(terminal['stream_id'],terminal['generation']))
        self.assertTrue(self.remote.admission_ready())
    def test_forty_real_worker_completions_retire_bounded_maps_and_cannot_replay_first(self):
        for index in range(40):
            terminal=self.complete('fixture-'+str(index));self.retire(terminal)
            self.assertEqual(self.remote.stream_map,{});self.assertEqual(self.peer.streams,{})
            self.assertEqual(self.peer.stream_records,{});self.assertEqual(self.local.audio_stops,{})
            self.assertEqual(self.device.audio_stops,{});self.assertIsNone(self.local.worker);self.assertIsNone(self.device.worker)
        self.assertEqual(self.peer.stream_high_water,40);self.assertEqual(self.remote.reservation_attempts,40)
        for sequence in (1,40,42,2**63):
            stream=stream_identity(self.peer.boot_id,sequence) if sequence<2**63 else self.peer.boot_id+':'+str(sequence)
            with self.assertRaises(HTTPError):self.client.call('/reserve',source_boot=self.peer.boot_id,stream_sequence=sequence,stream_id=stream)
        self.assertEqual(self.peer.stream_high_water,40);self.assertEqual(self.peer.streams,{})
    def test_retire_waits_actual_progress_handler_reference_and_blocks_new_output(self):
        terminal=self.complete();scope=self.remote._scope(terminal['stream_id'])
        entered=threading.Event();release=threading.Event();results=[];original=self.backend.progress
        def progress(stream):entered.set();release.wait(2);return original(stream)
        with patch.object(self.backend,'progress',side_effect=progress):
            worker=threading.Thread(target=lambda:results.append(self.client.call('/progress',**scope)));worker.start()
            try:
                self.assertTrue(entered.wait(1));self.assertFalse(self.remote.retire(terminal))
                self.assertEqual(len(self.peer.stream_records),1);self.assertFalse(self.remote.admission_ready())
                with self.assertRaises(RuntimeError):self.remote.reserve('new-local')
                self.assertEqual(self.peer.stream_high_water,1)
            finally:release.set();worker.join(1)
        self.assertTrue(results);self.retire(terminal)
    def test_cancelled_input_has_exact_measured_stop_and_can_retire_without_pcm_resume(self):
        self.local.operator('fixture-hub',microphone_enabled=True,valid_until=time.monotonic()+2)
        stream=self.local.begin('fixture-hub','cancelled',deadline=time.monotonic()+2)
        self.local.push(stream,b'\x00\x00'*160)
        wait(lambda:any(event['kind']=='speech_progress' for event in self.local.status()['timeline']))
        self.local.interrupt('human_utterance',preserve=False)
        wait(lambda:self.local.terminal_receipt() is not None)
        terminal=self.local.terminal_receipt();self.assertFalse(terminal['complete']);self.retire(terminal)
        self.assertFalse(self.local.status()['resumable'])
    def test_unknown_reserve_spends_device_highwater_and_prevents_any_next_admission(self):
        def unknown(stream):raise RuntimeError('fixture unknown backend reservation')
        with patch.object(self.backend,'reserve',side_effect=unknown):
            with self.assertRaises(RuntimeError):self.remote.reserve('first-local')
        self.assertEqual(self.peer.stream_high_water,1);self.assertEqual(len(self.peer.stream_records),1)
        self.assertTrue(self.remote.withdrawn);self.assertFalse(self.remote.admission_ready())
        with self.assertRaises(RuntimeError):self.remote.reserve('second-local')
        with self.assertRaises(HTTPError):self.client.call('/reserve',source_boot=self.peer.boot_id,stream_sequence=2,stream_id=stream_identity(self.peer.boot_id,2))
        self.assertEqual(self.peer.stream_high_water,1)
    def test_foreign_generation_boot_and_noncanonical_wire_identity_never_retire(self):
        terminal=self.complete();scope=self.remote._scope(terminal['stream_id'])
        body=dict(scope,generation=self.remote.pending_stream['generation'],completion='complete')
        for changes in (dict(generation=body['generation']+1),dict(source_boot='foreign'),dict(stream_id='old-uuid'),dict(stream_sequence=True)):
            with self.assertRaises(HTTPError):self.client.call('/retire',**{**body,**changes})
        self.assertEqual(len(self.peer.stream_records),1);self.retire(terminal)
    def test_held_backend_stop_and_reservation_remain_occupied_not_retirable(self):
        entered=threading.Event();release=threading.Event();original=self.backend.stop
        def stop(stream):entered.set();release.wait(2);return original(stream)
        with patch.object(self.backend,'stop',side_effect=stop):
            self.local.operator('fixture-hub',microphone_enabled=True,valid_until=time.monotonic()+2)
            stream=self.local.begin('fixture-hub','held-stop',deadline=time.monotonic()+2)
            self.local.push(stream,b'\x00\x00'*160);self.local.finish(stream)
            try:
                self.assertTrue(entered.wait(1));scope=self.remote._scope(stream)
                body=dict(scope,generation=self.remote.pending_stream['generation'],completion='complete')
                answer=self.client.call('/retire',**body)
                self.assertFalse(answer['retired']);self.assertTrue(answer['execution_busy'])
                self.assertEqual(len(self.peer.stream_records),1);self.assertIsNone(self.device.terminal_receipt())
                self.assertTrue(self.device.status()['execution_busy'])
                with self.assertRaises(RuntimeError):self.remote.reserve('different')
            finally:release.set()
        wait(lambda:not self.local.status()['execution_busy'])
    def test_unknown_stop_cursor_cannot_retire_or_release_admission(self):
        original=self.backend.stop
        def unknown(stream):
            value=original(stream);return {**value,'verified':False,'consumed_frames':None}
        with patch.object(self.backend,'stop',side_effect=unknown):
            self.local.operator('fixture-hub',microphone_enabled=True,valid_until=time.monotonic()+2)
            stream=self.local.begin('fixture-hub','unknown-cursor',deadline=time.monotonic()+2)
            self.local.push(stream,b'\x00\x00'*160);self.local.finish(stream)
            wait(lambda:self.local.worker is not None and not self.local.worker.is_alive())
            self.assertIsNone(self.local.terminal_receipt());self.assertTrue(self.local.status()['terminal_unknown'])
            scope=self.remote._scope(stream)
            with self.assertRaises(HTTPError):self.client.call('/retire',**scope,generation=self.remote.pending_stream['generation'],completion='complete')
            self.assertEqual(len(self.peer.stream_records),1);self.assertFalse(self.remote.admission_ready())
    def test_missing_or_wrong_source_authority_cannot_renew_or_change_deadline(self):
        self.ticking.clear();self.ticker.join(1);self.lease.close();self.lease.worker.join(1)
        deadline=self.peer.lease_deadline
        for body in (dict(authority=self.authority),dict(source_boot='old-source',authority=self.authority),
                     dict(source_boot=self.peer.boot_id,authority={**self.authority,'policy_epoch':True})):
            with self.assertRaises(HTTPError):self.client.call('/lease',**body)
            self.assertEqual(self.peer.lease_deadline,deadline)
    def test_wire_sequence_never_wraps_and_old_backend_calls_are_denied_after_retirement(self):
        terminal=self.complete();wire=self.remote._scope(terminal['stream_id']);self.retire(terminal)
        with patch.object(self.backend,'progress') as progress,patch.object(self.backend,'write') as write:
            with self.assertRaises(HTTPError):self.client.call('/progress',**wire)
            with self.assertRaises(HTTPError):self.client.call('/write',**wire,pcm_base64='AAA=')
            progress.assert_not_called();write.assert_not_called()
        self.remote.reservation_attempts=2**63-1
        with patch.object(self.remote.transport,'call') as transport:
            with self.assertRaises(ValueError):self.remote.reserve('overflow')
            transport.assert_not_called()
        self.assertEqual(self.remote.reservation_attempts,2**63-1);self.assertTrue(self.remote.withdrawn)
    def test_udp_lease_is_bound_to_same_owner_and_unknown_exchange_is_sticky(self):
        from reachy_companion.autonomous.lease_datagram import LeaseDatagramServer,DatagramRenewal
        server=LeaseDatagramServer(self.peer,'t'*32,'127.0.0.1',0)
        client=DatagramRenewal(self.client,self.peer.boot_id,server.socket.getsockname()[1],authority=self.authority)
        try:
            client.renew();self.assertEqual(client.ack_sequence,1)
            client.authority={**self.authority,'owner_sha256':'0'*64}
            with self.assertRaises(Exception):client.renew()
            attempts=client.attempts
            with self.assertRaises(RuntimeError):client.renew()
            self.assertEqual(client.attempts,attempts);self.assertTrue(client.withdrawn)
        finally:client.close();server.close();server.worker.join(1)
    def test_current_epoch_change_is_sticky_no_late_tick_or_ack_can_rearm(self):
        self.lease.tick({**self.authority,'microphone_epoch':2});wait(lambda:self.lease.closed)
        acknowledged=self.lease.last_accepted
        self.assertFalse(self.lease.tick(self.authority));self.assertEqual(self.lease.last_accepted,acknowledged)
        wait(lambda:self.peer.closed);self.assertFalse(self.peer.permitted())
        with self.assertRaises(HTTPError):self.client.call('/lease',source_boot=self.peer.boot_id,authority=self.authority)


class OwnerClaimTests(unittest.TestCase):
    @unittest.skipIf(os.name=='nt','Device owner file uses existing POSIX host')
    def test_source_claim_is_single_use_and_rejects_epoch_or_permission_change_before_writing(self):
        spec=importlib.util.spec_from_file_location('lease_device_owner',Path(__file__).resolve().parents[1]/'deploy/autonomous/device_audio_runtime.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        owner=dict(agent_boot_id='fixture-agent',initial_microphone_epoch=0,owned_microphone_epoch=1,owner_id='fixture-owner',policy_epoch=1)
        actual=dict(agent_boot_id='fixture-agent',microphone_epoch=1,microphone_owner_id='fixture-owner',microphone_enabled=True,
            capture_active=False,listening=False,phase='paused',microphone_state_error=None,motion_policy=dict(epoch=1,quiet=False,privacy_all=False))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owner.json';path.write_text(json.dumps(owner));path.chmod(0o600);raw=path.read_bytes()
            with self.assertRaises(ValueError):module.claim_lease_owner(path,{**actual,'microphone_epoch':2},'fixture-controller')
            self.assertEqual(path.read_bytes(),raw)
            fd,bound,source=module.claim_lease_owner(path,actual,'fixture-controller')
            try:
                self.assertEqual(bound['lease_source_claim']['source_boot'],source)
                with self.assertRaises((OSError,ValueError)):module.claim_lease_owner(path,actual,'fixture-controller')
            finally:os.close(fd)
            with self.assertRaises(ValueError):module.claim_lease_owner(path,actual,'fixture-controller')

    def test_lease_cleanup_uses_frozen_owner_and_never_mutates_replaced_or_old_epoch_owner(self):
        spec=importlib.util.spec_from_file_location('lease_cleanup_scope',Path(__file__).resolve().parents[1]/'deploy/autonomous/device_audio_runtime.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        expected=dict(agent_boot_id='fixture-agent',initial_microphone_epoch=0,owned_microphone_epoch=1,
            owner_id='fixture-original',policy_epoch=1,lease_source_claim=dict(source_boot='fixture-source'))
        for actual in (dict(agent_boot_id='fixture-agent',microphone_epoch=0,microphone_owner_id=None),
                       dict(agent_boot_id='fixture-agent',microphone_epoch=1,microphone_owner_id='fixture-replacement')):
            with patch.object(module,'agent',return_value=actual) as api:
                module.cleanup(None,Path('/does-not-exist'),expected_owner=expected)
                self.assertEqual(api.call_count,1);self.assertEqual(api.call_args.args[1],'/operator')

    @unittest.skipIf(os.name=='nt','Device owner file uses existing POSIX host')
    def test_lease_entry_never_activates_microphone_and_cleanup_only_mutes_owned_grant(self):
        spec=importlib.util.spec_from_file_location('lease_device_entry',Path(__file__).resolve().parents[1]/'deploy/autonomous/device_audio_runtime.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        root=Path(__file__).resolve().parents[1]
        owner=dict(agent_boot_id='fixture-agent',initial_microphone_epoch=0,owned_microphone_epoch=1,owner_id='fixture-owner',policy_epoch=1)
        actual=dict(agent_boot_id='fixture-agent',microphone_epoch=1,microphone_owner_id='fixture-owner',microphone_enabled=True,
            capture_active=False,listening=False,phase='paused',microphone_state_error=None,motion_policy=dict(epoch=1,quiet=False,privacy_all=False))
        writes=[];peer_class=module.AudioPeer;server_factory=module.create_server
        def api(cfg,path,payload=None):
            if payload is not None:
                writes.append((path,payload));actual.update(microphone_enabled=False,microphone_epoch=2,microphone_owner_id=None)
            return copy.deepcopy(actual)
        def peer(*args,**kwargs):
            value=peer_class(*args,**kwargs);value.close('controller_stop');return value
        def server(*args,**kwargs):return server_factory(*args,**{**kwargs,'port':0,'stop_port':0})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);owner_path=path/'owner.json';owner_path.write_text(json.dumps(owner));owner_path.chmod(0o600)
            data=json.loads((root/'config.example.json').read_text());data['paths']['token_file']='token';data['runtime']['profile']=''
            data['guarded_motion']=dict(enabled=False,socket_path='s',policy_path='p')
            (path/'config.json').write_text(json.dumps(data));(path/'token').write_text('t'*32)
            argv=['lease-device','--config',str(path/'config.json'),'--output',str(path/'report.json'),'--owner-file',str(owner_path),
                '--controller','fixture-controller','--lifetime','lease','--stop-port','8799','--allow-capture-output']
            with patch('sys.argv',argv),patch.object(module,'agent',side_effect=api),patch.object(module,'AudioPeer',side_effect=peer),patch.object(module,'create_server',side_effect=server),patch.object(module,'AlsaPCM',return_value=FixturePCM()),patch.object(module,'AlsaCapture') as capture,patch.dict('sys.modules',webrtcvad=SimpleNamespace(Vad=lambda _:None)),patch('builtins.print'):
                with self.assertRaises(SystemExit):module.main() # no capture occurred; never acceptance
                capture.assert_not_called()
            self.assertEqual(len(writes),1);self.assertEqual(writes[0][0],'/microphone')
            self.assertIs(writes[0][1]['enabled'],False);self.assertEqual(writes[0][1]['expected_owner_id'],'fixture-owner')

    @unittest.skipIf(os.name=='nt','Device owner file uses existing POSIX host')
    def test_claim_rejects_symlink_hardlink_and_wrong_actual_types_without_mutation(self):
        spec=importlib.util.spec_from_file_location('lease_owner_scope',Path(__file__).resolve().parents[1]/'deploy/autonomous/device_audio_runtime.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        owner=dict(agent_boot_id='fixture-agent',initial_microphone_epoch=0,owned_microphone_epoch=1,owner_id='fixture-owner',policy_epoch=1)
        actual=dict(agent_boot_id='fixture-agent',microphone_epoch=1,microphone_owner_id='fixture-owner',microphone_enabled=True,
            capture_active=False,listening=False,phase='paused',microphone_state_error=None,motion_policy=dict(epoch=1,quiet=False,privacy_all=False))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owner.json';path.write_text(json.dumps(owner));path.chmod(0o600);raw=path.read_bytes()
            link=Path(directory)/'alias';link.symlink_to(path)
            with self.assertRaises(OSError):module.claim_lease_owner(link,actual,'fixture-controller')
            link.unlink();os.link(path,link)
            with self.assertRaises(ValueError):module.claim_lease_owner(path,actual,'fixture-controller')
            link.unlink()
            for changes in (dict(microphone_epoch=True),dict(microphone_enabled=False),dict(microphone_owner_id='foreign'),dict(listening=True)):
                with self.assertRaises(ValueError):module.claim_lease_owner(path,{**actual,**changes},'fixture-controller')
            self.assertEqual(path.read_bytes(),raw)


class RenewalRaceTests(unittest.TestCase):
    def renewal(self,outcome):
        entered=threading.Event();release=threading.Event();requests=[]
        authority=owner_binding(dict(agent_boot_id='fixture-agent',owned_microphone_epoch=1,policy_epoch=0 if outcome=='false_policy' else 1,owner_id='fixture-owner'))
        client=SimpleNamespace(url='http://127.0.0.1:1',timeout=.25,token='t'*32,controller='fixture-controller')
        class Response:
            status=200
            def read(self,size):
                entered.set();release.wait(2)
                if outcome=='unknown':raise TimeoutError('fixture renewal unknown')
                reply=dict(authority)
                if outcome=='bool_epoch':reply['microphone_epoch']=True
                if outcome=='float_epoch':reply['microphone_epoch']=1.0
                if outcome=='false_policy':reply['policy_epoch']=False
                if outcome=='float_policy':reply['policy_epoch']=1.0
                return json.dumps(dict(source_boot='fixture-source',authority=reply)).encode()
        class Connection:
            sock=None
            def connect(self):self.sock=SimpleNamespace(setsockopt=lambda *args:None)
            def request(self,method,path,body,headers):requests.append(json.loads(body))
            def getresponse(self):return Response()
            def close(self):self.sock=None
        with patch('reachy_companion.autonomous.audio_peer.http.client.HTTPConnection',return_value=Connection()):
            lease=PeerLease(client,source_boot='fixture-source',authority=authority)
            try:
                self.assertTrue(lease.tick(authority));self.assertTrue(entered.wait(1))
                if outcome=='late':lease.close()
                if outcome=='expired':time.sleep(.11);self.assertFalse(lease.tick(authority))
                self.assertTrue(lease.worker.is_alive())
                if outcome!='unknown':self.assertTrue(lease.status()['execution_busy'])
                release.set();lease.worker.join(1);self.assertFalse(lease.worker.is_alive())
                self.assertTrue(lease.closed);self.assertIsNone(lease.last_accepted)
                self.assertFalse(lease.tick(authority));self.assertEqual(len(requests),1);self.assertEqual(lease.calls,1)
                self.assertEqual(requests[0]['source_boot'],'fixture-source');self.assertEqual(requests[0]['authority'],authority)
            finally:release.set();lease.close();lease.worker.join(1)
    def test_late_ack_after_close_never_rearms_and_retains_actual_worker_until_return(self):self.renewal('late')
    def test_unknown_renewal_is_one_attempt_without_reconnect_retry(self):self.renewal('unknown')
    def test_late_tick_after_expiry_cannot_make_held_renewal_fresh(self):self.renewal('expired')
    def test_malformed_epoch_ack_aliases_withdraw_before_any_acceptance(self):
        for outcome in ('bool_epoch','float_epoch','false_policy','float_policy'):
            with self.subTest(outcome=outcome):self.renewal(outcome)


class TypedAckTests(unittest.TestCase):
    def test_retirement_ack_boolean_and_integer_aliases_keep_record_and_deny_new_reserve(self):
        base=dict(source_boot='fixture-source',stream_id='fixture-source:1',stream_sequence=1,generation=1,retired=True,execution_busy=False)
        for changes in (dict(retired=1),dict(execution_busy=0),dict(retired=0,execution_busy=1),
                        dict(stream_sequence=True),dict(stream_sequence=1.0),dict(generation=True),dict(generation=1.0)):
            with self.subTest(changes=changes):
                client=PeerClient('http://127.0.0.1:1','t'*32,'fixture-controller')
                remote=RemotePCM(client,stop_port=2,source_boot='fixture-source',lifetime='lease')
                with patch.object(remote.transport,'call',return_value=dict(reserved=True,device_stream_id='fixture-device-stream',generation=1)) as reserve,patch.object(client,'call',return_value={**base,**changes}):
                    remote.reserve('first-local')
                    with self.assertRaises(ValueError):remote.retire(dict(stream_id='first-local',complete=True))
                    self.assertTrue(remote.withdrawn);self.assertFalse(remote.admission_ready());self.assertEqual(len(remote.stream_map),1)
                    with self.assertRaises(RuntimeError):remote.commit_retirement('first-local')
                    with self.assertRaises(RuntimeError):remote.reserve('new-local')
                    self.assertEqual(reserve.call_count,1)
                remote.close_transport()

    def test_udp_bool_and_float_sequences_latch_without_accepted_ack_or_retry(self):
        from reachy_companion.autonomous.lease_datagram import DatagramRenewal
        authority=owner_binding(dict(agent_boot_id='fixture-agent',owned_microphone_epoch=1,policy_epoch=1,owner_id='fixture-owner'))
        for sequence in (True,1.0):
            with self.subTest(sequence=sequence):
                peer=PeerClient('http://127.0.0.1:1','t'*32,'fixture-controller')
                renewal=DatagramRenewal(peer,'fixture-source',2,authority=authority);renewal.socket.close();sent=[]
                def empty(size):raise BlockingIOError
                renewal.socket=SimpleNamespace(setblocking=lambda _:None,settimeout=lambda _:None,recv=empty,
                    send=lambda body:sent.append(body),getsockname=lambda:('127.0.0.1',12345),getpeername=lambda:('127.0.0.1',23456),close=lambda:None)
                replies=[dict(kind='challenge',source_boot='fixture-source',echo='1'*32,nonce='2'*32),
                         dict(kind='accepted',source_boot='fixture-source',sequence=sequence)]
                with patch('reachy_companion.autonomous.lease_datagram.secrets.token_hex',return_value='1'*32),patch.object(renewal,'receive',side_effect=replies):
                    with self.assertRaises(ValueError):renewal.renew()
                    self.assertTrue(renewal.withdrawn);self.assertIsNone(renewal.last_ack);self.assertIsNone(renewal.ack_sequence)
                    with self.assertRaises(RuntimeError):renewal.renew()
                    self.assertEqual(len(sent),2);self.assertEqual(renewal.attempts,1)
                renewal.close()


class JoinedLeaseTests(unittest.TestCase):
    def test_first_renewal_attempt_without_ack_cannot_start_model_admission(self):
        self.first_renewal_ack(False)
    def test_malformed_first_ack_with_bool_epoch_has_zero_model_admission(self):
        self.first_renewal_ack(True)
    def first_renewal_ack(self,malformed):
        from reachy_companion.autonomous.audio_adapter import AudioAdapter,HttpSTT
        from reachy_companion.autonomous.audio_peer import AudioPolling
        from reachy_companion.autonomous.companion_session import run_session
        from reachy_companion.autonomous.config import load
        from reachy_companion.autonomous.runtime import ReplayGateway,Scheduler
        from reachy_companion.autonomous.speech_adapter import SpeechAdapter
        fixture=LeaseProtocolTests();fixture.setUp(start_lease=False);fixture.lease.close();fixture.lease.worker.join(1)
        entered=threading.Event();release=threading.Event()
        class Response:
            status=200
            def read(self,size):
                entered.set();release.wait(3)
                authority={**fixture.authority,'microphone_epoch':True} if malformed else fixture.authority
                return json.dumps(dict(source_boot=fixture.peer.boot_id,authority=authority)).encode()
        class Connection:
            sock=None
            def connect(self):self.sock=SimpleNamespace(setsockopt=lambda *args:None)
            def request(self,method,path,body,headers):fixture.client.call('/lease',**{key:value for key,value in json.loads(body).items() if key!='controller'})
            def getresponse(self):return Response()
            def close(self):self.sock=None
        class Gateway(ReplayGateway):
            def call(self,path):return dict(compute_boot_id=self.boot_id,quarantined=[])
        class TTS:
            def stream(self,text,cancel):yield b'\x00\x00'*160
            def cancel(self):pass
        audio=AudioAdapter(HttpSTT('http://127.0.0.1:1','t'*32));speech=SpeechAdapter(fixture.local,TTS(),lambda:copy.deepcopy(fixture.operator))
        cfg=load(Path(__file__).resolve().parents[1]/'config.autonomous.example.json');gateway=Gateway(.01)
        scheduler=Scheduler(cfg,gateway,speech_adapter=speech,audio_adapter=audio);poller=AudioPolling(fixture.client,audio,fixture.peer.boot_id)
        stop=threading.Event();reports=[];status=[]
        with patch('reachy_companion.autonomous.audio_peer.http.client.HTTPConnection',return_value=Connection()):
            fixture.lease=PeerLease(fixture.client,source_boot=fixture.peer.boot_id,authority=fixture.authority)
        def run():reports.append(run_session(scheduler,poller,fixture.lease,fixture.client,fixture.client.at_port(fixture.server.stop_address[1]),fixture.peer.boot_id,stop,None,status.append,lifetime='lease'))
        runner=threading.Thread(target=run);runner.start()
        try:
            if malformed:
                self.assertTrue(entered.wait(1));release.set();wait(lambda:fixture.lease.closed);runner.join(2)
                self.assertFalse(runner.is_alive());self.assertEqual(gateway.fast_calls,0)
                self.assertIsNone(fixture.lease.last_accepted);self.assertFalse(reports[0]['accepted'])
                return
            self.assertTrue(entered.wait(1));self.assertTrue(fixture.peer.permitted());time.sleep(.12)
            self.assertEqual(fixture.lease.calls,1);self.assertIsNone(fixture.lease.last_accepted)
            self.assertEqual(gateway.fast_calls,0);self.assertTrue(status);self.assertTrue(all(value.get('stage')=='STARTING' for value in status))
            stop.set();runner.join(2);self.assertFalse(runner.is_alive());self.assertTrue(reports[0]['execution_busy']['lease'])
        finally:
            release.set();stop.set();runner.join(3);audio.close();speech.close();fixture.tearDown()

    def test_stop_keeps_media_close_job_busy_while_real_remote_progress_is_held(self):
        from reachy_companion.autonomous.audio_adapter import AudioAdapter,HttpSTT
        from reachy_companion.autonomous.audio_peer import AudioPolling
        from reachy_companion.autonomous.companion_session import run_session
        from reachy_companion.autonomous.config import load
        from reachy_companion.autonomous.runtime import ReplayGateway,Scheduler
        from reachy_companion.autonomous.speech_adapter import SpeechAdapter
        fixture=LeaseProtocolTests();fixture.setUp(start_lease=False)
        slow=PeerClient(fixture.client.url,'t'*32,'fixture-controller',timeout=3)
        fixture.remote=RemotePCM(slow,stop_port=fixture.server.stop_address[1],source_boot=fixture.peer.boot_id,lifetime='lease')
        fixture.local=Playback(fixture.remote,allow_simulated=True,chunk_frames=4096)
        class Gateway(ReplayGateway):
            def call(self,path):return dict(compute_boot_id=self.boot_id,quarantined=[])
        class TTS:
            def stream(self,text,cancel):yield b'\x00\x00'*160
            def cancel(self):pass
        audio=AudioAdapter(HttpSTT('http://127.0.0.1:1','t'*32))
        speech=SpeechAdapter(fixture.local,TTS(),lambda:copy.deepcopy(fixture.operator))
        cfg=load(Path(__file__).resolve().parents[1]/'config.autonomous.example.json');cfg['period_s']=.02
        scheduler=Scheduler(cfg,Gateway(.01),speech_adapter=speech,audio_adapter=audio)
        poller=AudioPolling(fixture.client,audio,fixture.peer.boot_id);stop=threading.Event();reports=[]
        entered=threading.Event();release=threading.Event();original=fixture.backend.progress
        def progress(stream):entered.set();release.wait(3);return original(stream)
        def run():reports.append(run_session(scheduler,poller,fixture.lease,fixture.client,fixture.client.at_port(fixture.server.stop_address[1]),fixture.peer.boot_id,stop,None,lambda value:None,lifetime='lease'))
        with patch.object(audio.stt,'transcribe',return_value='Neutral held media fixture'),patch.object(fixture.backend,'progress',side_effect=progress):
            runner=threading.Thread(target=run);runner.start()
            try:
                wait(lambda:audio.allowed);fixture.peer.publish(b'\x00\x00'*320,time.monotonic(),None)
                self.assertTrue(entered.wait(1))
                wait(lambda:any(record['refs']>=2 for record in fixture.peer.stream_records.values()))
                stop.set();runner.join(2);self.assertFalse(runner.is_alive())
                self.assertTrue(reports[0]['execution_busy']['media_close']);self.assertFalse(reports[0]['cleanup_verified'])
                self.assertTrue(reports[0]['execution_busy']['speech'])
            finally:
                release.set();stop.set();runner.join(3);audio.close();speech.close()
                wait(lambda:not speech.status()['execution_busy']);wait(lambda:fixture.remote.transport.connection is None)
                fixture.tearDown()

    def test_actual_normal_loop_drives_fresh_authority_and_terminal_retirement(self):
        from reachy_companion.autonomous.audio_adapter import AudioAdapter,HttpSTT
        from reachy_companion.autonomous.audio_peer import AudioPolling
        from reachy_companion.autonomous.companion_session import run_session
        from reachy_companion.autonomous.config import load
        from reachy_companion.autonomous.runtime import ReplayGateway,Scheduler
        from reachy_companion.autonomous.speech_adapter import SpeechAdapter
        fixture=LeaseProtocolTests();fixture.setUp(start_lease=False)
        class Gateway(ReplayGateway):
            def call(self,path):return dict(compute_boot_id=self.boot_id,quarantined=[])
        class TTS:
            def stream(self,text,cancel):yield b'\x00\x00'*160
            def cancel(self):pass
        audio=AudioAdapter(HttpSTT('http://127.0.0.1:1','t'*32))
        speech=SpeechAdapter(fixture.local,TTS(),lambda:copy.deepcopy(fixture.operator))
        cfg=load(Path(__file__).resolve().parents[1]/'config.autonomous.example.json');cfg['period_s']=.02
        scheduler=Scheduler(cfg,Gateway(.01),speech_adapter=speech,audio_adapter=audio)
        poller=AudioPolling(fixture.client,audio,fixture.peer.boot_id);stop=threading.Event();reports=[];status=[]
        def run():reports.append(run_session(scheduler,poller,fixture.lease,fixture.client,fixture.client.at_port(fixture.server.stop_address[1]),fixture.peer.boot_id,stop,None,status.append,lifetime='lease'))
        with patch.object(audio.stt,'transcribe',return_value='Neutral lease fixture input'):
            runner=threading.Thread(target=run);runner.start()
            try:
                for index in range(3):
                    wait(lambda:audio.allowed and fixture.remote.admission_ready())
                    self.assertTrue(fixture.peer.publish(b'\x00\x00'*320,time.monotonic(),None))
                    wait(lambda:len(speech.receipts)>=index+1 and fixture.remote.admission_ready())
                self.assertEqual(fixture.peer.stream_high_water,3);self.assertEqual(fixture.peer.stream_records,{})
                stop.set();runner.join(2);self.assertFalse(runner.is_alive())
                self.assertTrue(reports[0]['cleanup_verified']);self.assertTrue(reports[0]['continuous'])
                self.assertFalse(reports[0]['continuous_acceptance']);self.assertEqual(reports[0]['reservation_attempts'],3)
            finally:stop.set();runner.join(3);audio.close();speech.close();fixture.tearDown()


if __name__=='__main__':unittest.main()
