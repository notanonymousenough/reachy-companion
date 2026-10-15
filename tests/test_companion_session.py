"""Real local reducers/transports with synthetic STT/TTS/PCM; no hardware proof."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import signal
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from reachy_companion.autonomous.audio_adapter import AudioAdapter,HttpSTT
from reachy_companion.autonomous.audio_peer import AudioPeer,AudioPolling,PeerClient,PeerLease,RemotePCM,create_server
from reachy_companion.autonomous.companion_session import run_session
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.playback import Playback,ReplayPCM
from reachy_companion.autonomous.runtime import ReplayGateway,Scheduler
from reachy_companion.autonomous.motion_adapter import MotionAdapter
from reachy_companion.autonomous.speech_adapter import SpeechAdapter


class ConsumedFixturePCM(ReplayPCM):
    @property
    def stream(self):return self.current
    def progress(self,stream):
        self.advance(stream,16000)
        return super().progress(stream)


class FixtureTTS:
    def __init__(self):self.calls=[]
    def stream(self,text,cancel):
        self.calls.append(text)
        yield b'\x00\x00'*160
    def cancel(self):pass


class FixtureGateway(ReplayGateway):
    def __init__(self):super().__init__(.01);self.health_entered=threading.Event();self.health_release=None;self.changed=False
    def call(self,path):
        if path!='/health':raise AssertionError(path)
        self.health_entered.set()
        if self.health_release is not None:self.health_release.wait(3)
        return dict(compute_boot_id='foreign-compute' if self.changed else self.boot_id,quarantined=[])


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.operator=dict(agent_boot_id='fixture-agent',microphone_epoch=1,microphone_enabled=True,
            microphone_owner_id='fixture-owner',microphone_state_error=None,listening=False,phase='paused',
            motion_policy=dict(epoch=1,quiet=False,privacy_all=False,motor_enabled=False))
        owner=dict(agent_boot_id='fixture-agent',owned_microphone_epoch=1,owner_id='fixture-owner',policy_epoch=1)
        self.device=Playback(ConsumedFixturePCM(),allow_simulated=True,chunk_frames=4096)
        self.peer=AudioPeer(self.device,lambda:copy.deepcopy(self.operator),owner,controller='fixture-controller')
        self.server=create_server(self.peer,'t'*32,bind='127.0.0.1',port=0,stop_port=0)
        self.server_thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.server_thread.start()
        self.client=PeerClient('http://127.0.0.1:'+str(self.server.server_address[1]),'t'*32,'fixture-controller')
        self.stop_client=self.client.at_port(self.server.stop_address[1])
        self.stt=HttpSTT('http://127.0.0.1:1','t'*32);self.audio=AudioAdapter(self.stt)
        self.tts=FixtureTTS();self.playback=Playback(RemotePCM(self.client,stop_port=self.server.stop_address[1],source_boot=self.peer.boot_id,max_streams=32),allow_simulated=True,chunk_frames=4096)
        self.speech=SpeechAdapter(self.playback,self.tts,lambda:copy.deepcopy(self.operator))
        cfg=load(Path(__file__).resolve().parents[1]/'config.autonomous.example.json');cfg['period_s']=.02
        self.gateway=FixtureGateway();self.scheduler=Scheduler(cfg,self.gateway,speech_adapter=self.speech,audio_adapter=self.audio)
        self.poller=AudioPolling(self.client,self.audio,self.peer.boot_id);self.lease=PeerLease(self.client)
        self.stop=threading.Event();self.latest=[]
    def tearDown(self):
        if self.gateway.health_release is not None:self.gateway.health_release.set()
        self.stop.set();self.lease.close();self.poller.close();self.scheduler.close();self.peer.close()
        self.lease.worker.join(1);self.peer.watch.join(1)
        self.server.shutdown();self.server.server_close();self.server_thread.join(1)
    def run_normal(self,duration=1):
        return run_session(self.scheduler,self.poller,self.lease,self.client,self.stop_client,self.peer.boot_id,self.stop,duration,self.latest.append)
    def wait(self,predicate,timeout=2):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:time.sleep(.005)
        self.assertTrue(predicate())
    def test_actual_normal_ingest_without_practice_or_echo_reference_reaches_main_and_playback(self):
        result=[]
        with patch.object(self.stt,'transcribe',return_value='A neutral normal question') as transcribe:
            runner=threading.Thread(target=lambda:result.append(self.run_normal(2)));runner.start()
            try:
                self.wait(lambda:any(item.get('listening_ready') is True for item in self.latest))
                self.assertTrue(self.peer.publish(b'\x00\x00'*320,time.monotonic(),None))
                self.wait(lambda:bool(self.tts.calls))
                self.wait(lambda:self.speech.status()['receipts'] and not self.speech.status()['execution_busy'])
                self.stop.set();runner.join(2);self.assertFalse(runner.is_alive())
            finally:self.stop.set();runner.join(3)
        report=result[0]
        self.assertEqual(report['counts']['new_turn'],1);self.assertEqual(report['counts']['task_started'],1)
        self.assertEqual(len(self.tts.calls),1);transcribe.assert_called_once()
        self.assertTrue(report['cleanup_verified']);self.assertFalse(any(report['execution_busy'].values()))
        self.assertFalse(report['continuous']);self.assertEqual(report['device_lifetime_cap_s'],180)
        self.assertEqual(self.audio.status()['counts']['completed'],1);self.assertFalse(report['transcripts_retained'])
    def test_changed_compute_boot_withdraws_instead_of_reconnect(self):
        self.gateway.changed=True
        report=self.run_normal()
        self.assertEqual(report['reason'],'runtime_error');self.assertFalse(report['accepted'])
        self.assertEqual(self.scheduler.state.authority.compute_boot_id,self.gateway.boot_id)
        self.assertTrue(self.peer.closed);self.assertTrue(self.scheduler.closed)
    def test_expired_health_keeps_real_occupied_job_and_stops_renewal(self):
        self.gateway.health_release=threading.Event()
        report=self.run_normal(2)
        self.assertEqual(report['reason'],'runtime_error');self.assertTrue(report['execution_busy']['health'])
        self.assertFalse(report['cleanup_verified']);self.assertTrue(self.peer.closed)
        self.assertTrue(self.lease.closed);self.assertTrue(self.scheduler.closed)
    def test_mute_revokes_current_source_and_never_reacquires_microphone(self):
        def mute():
            self.wait(lambda:self.peer.permitted());self.operator['microphone_enabled']=False
            self.operator['microphone_epoch']=2;self.operator['microphone_owner_id']=None
        worker=threading.Thread(target=mute);worker.start()
        report=self.run_normal(2);worker.join(1)
        self.assertNotEqual(report['reason'],'duration');self.assertTrue(self.peer.closed)
        self.assertFalse(self.operator['microphone_enabled']);self.assertEqual(self.operator['microphone_epoch'],2)
        self.assertFalse(report['automatic_microphone_activation']);self.assertFalse(self.tts.calls)
    def test_actual_scheduler_exception_closes_all_owners(self):
        with patch.object(self.scheduler,'advance',side_effect=RuntimeError('fixture reducer failure')):
            report=self.run_normal()
        self.assertEqual(report['reason'],'runtime_error');self.assertEqual(report['errors'],['RuntimeError'])
        self.assertTrue(self.scheduler.closed);self.assertTrue(self.audio.closed);self.assertTrue(self.speech.closed)
        self.assertTrue(self.peer.closed);self.assertTrue(self.lease.closed)

    def test_refresh_preserves_only_new_current_proposal_with_same_permitted_physical_binding(self):
        for mode in ('same','foreign_epoch','quiet','privacy','muted','expired','old_authority'):
            with self.subTest(mode=mode),self.speech.lock:
                old=self.scheduler.state.authority;current=replace(old,interaction_epoch=1,speech_epoch=1)
                self.speech.current_authority=current;binding=('fixture-agent',1,1)
                self.speech.binding=binding;self.speech.authority=(old,binding)
                self.speech.pending=dict(authority=old if mode=='old_authority' else current,
                    deadline=time.monotonic()+(-1 if mode=='expired' else 2),request_id='fixture-proposal',text='Neutral fixture reply')
                actual=copy.deepcopy(self.operator)
                if mode=='foreign_epoch':actual['microphone_epoch']=2
                if mode=='quiet':actual['motion_policy']['quiet']=True
                if mode=='privacy':actual['motion_policy']['privacy_all']=True
                if mode=='muted':actual['microphone_enabled']=False
                job=threading.Thread(target=lambda:None);job.start();job.join(1)
                self.speech.refresh_job=job
                self.speech.refresh_result=(current,self.speech.generation,time.monotonic(),dict(actual=actual))
                self.speech._accept_refresh()
                self.assertEqual(self.speech.pending is not None,mode=='same')
                self.speech.pending=None

    def test_stop_during_occupied_stt_retains_slot_and_discards_late_text(self):
        entered=threading.Event();release=threading.Event();reports=[]
        def transcribe(pcm):entered.set();release.wait(3);return 'Late fixture text'
        with patch.object(self.stt,'transcribe',side_effect=transcribe):
            runner=threading.Thread(target=lambda:reports.append(self.run_normal(2)));runner.start()
            try:
                self.wait(lambda:self.peer.permitted() and self.audio.allowed)
                self.peer.publish(b'\x00\x00'*320,time.monotonic(),None);self.assertTrue(entered.wait(1))
                self.stop.set();runner.join(2);self.assertFalse(runner.is_alive())
                self.assertTrue(reports[0]['execution_busy']['audio']);self.assertFalse(reports[0]['cleanup_verified'])
                self.assertTrue(self.audio.closed);self.assertFalse(self.tts.calls)
            finally:release.set();runner.join(3)
        self.audio.job.join(1);self.assertIsNone(self.audio.result)

    def test_new_turn_during_held_main_keeps_slot_and_fast_ticks_without_old_speech(self):
        entered=threading.Event();release=threading.Event();reports=[]
        def main(task):
            entered.set();release.wait(4)
            return dict(output='Late old fixture reply',request_id=task.attempt_id,compute_boot_id=self.gateway.boot_id)
        with patch.object(self.gateway,'main',side_effect=main) as calls,patch.object(self.stt,'transcribe',side_effect=['First normal fixture','Second normal fixture']):
            runner=threading.Thread(target=lambda:reports.append(self.run_normal(3)));runner.start()
            try:
                self.wait(lambda:any(item.get('listening_ready') for item in self.latest))
                self.peer.publish(b'\x00\x00'*320,time.monotonic(),None);self.assertTrue(entered.wait(1))
                self.wait(lambda:self.audio.allowed)
                self.peer.publish(b'\x00\x00'*320,time.monotonic(),None)
                self.wait(lambda:self.scheduler.state.counts['new_turn']==2)
                self.wait(lambda:self.scheduler.state.counts['main_execution_busy']>0)
                self.assertEqual(calls.call_count,1);self.assertFalse(self.tts.calls)
                self.stop.set();runner.join(2);self.assertFalse(runner.is_alive())
                self.assertTrue(reports[0]['execution_busy']['main']);self.assertFalse(reports[0]['cleanup_verified'])
                self.assertGreater(reports[0]['counts']['fast_requested'],3)
            finally:release.set();runner.join(4)
        self.scheduler.main_job.thread.join(1)
        self.scheduler.advance();self.assertFalse(self.tts.calls)

    def test_stale_capture_never_submits_to_stt_or_main(self):
        reports=[]
        with patch.object(self.stt,'transcribe') as transcribe:
            runner=threading.Thread(target=lambda:reports.append(self.run_normal()));runner.start()
            try:
                self.wait(lambda:any(item.get('listening_ready') for item in self.latest))
                self.peer.publish(b'\x00\x00'*320,time.monotonic()-1,None)
                self.wait(lambda:self.poller.status()['rejected']>0)
                self.stop.set();runner.join(2)
                transcribe.assert_not_called();self.assertFalse(self.tts.calls)
            finally:self.stop.set();runner.join(2)

    def test_existing_typed_motion_adapter_dispatches_and_stops_inside_normal_owner_loop(self):
        commands=[];operator=self.operator
        class Hub:
            boot_id=None
            def agent(self,path):
                if path=='/operator':return copy.deepcopy(operator)
                if path!='/status':raise AssertionError(path)
                policy={**operator['motion_policy'],'motor_enabled':True}
                actor=dict(actor_boot_id='fixture-actor',session_id='fixture-session',policy=policy,
                    operator=copy.deepcopy(operator),binding=None,ready=True,owner_verified=True,kernel_exclusive=True,
                    command_high_watermark=len(commands),heartbeat_to_verified_s=.1,max_displacement_radians=.01,
                    target_writes=1,hold=dict(verified=True,trajectory_updates_after_hold=0))
                return dict(agent_boot_id=operator['agent_boot_id'],microphone_epoch=1,microphone_enabled=True,motion_actor=actor)
            def native_motion(self,payload,command_id=None):
                commands.append(payload)
                return dict(lease_id='fixture-lease',verified_stopped=True)
        motion=MotionAdapter(Hub(),cooldown_s=3);motion.refresh();self.playback.motion=motion
        self.scheduler=Scheduler(self.scheduler.config,self.gateway,motion,self.speech,self.audio)
        self.scheduler.ingest(dict(type='sensor',id='fixture.motion',summary='Synthetic bounded movement invitation'))
        original=self.gateway.fast;selected=[]
        def fast(request_id,view):
            if not selected and view['op']['motion_allowed']:
                selected.append(True)
                return dict(output=dict(a='explore',why='fixture',motion='attentive'),request_id=request_id,compute_boot_id=self.gateway.boot_id)
            return original(request_id,view)
        reports=[]
        with patch.object(self.gateway,'fast',side_effect=fast):
            runner=threading.Thread(target=lambda:reports.append(self.run_normal(3)));runner.start()
            try:
                self.wait(lambda:bool(motion.receipts),timeout=2.5)
                self.stop.set();runner.join(2)
            finally:self.stop.set();runner.join(4)
        self.assertTrue(motion.receipts[0]['accepted']);self.assertTrue(any(value['kind']=='trajectory' for value in commands))
        self.assertTrue(reports[0]['cleanup_verified']);self.assertFalse(reports[0]['execution_busy']['motion'])

    def test_startup_failure_closes_constructed_real_audio_and_exact_owned_peer(self):
        from reachy_companion.autonomous import companion_session as module
        from reachy_companion.autonomous.audio_session_control import create_server as control_server
        root=Path(__file__).resolve().parents[1];created=[]
        def audio(stt):
            adapter=AudioAdapter(stt);created.append(adapter);return adapter
        def control(*args,**kwargs):return control_server(*args,**{**kwargs,'port':0})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'token').write_text('t'*32)
            data=json.loads((root/'config.example.json').read_text());data['paths']['token_file']='token'
            data['runtime']['profile']='';data['guarded_motion']=dict(enabled=False,socket_path='s',policy_path='p')
            (path/'companion.json').write_text(json.dumps(data));output=path/'report.json'
            argv=['normal','--mode','normal','--config',str(root/'config.autonomous.example.json'),
                '--companion-config',str(path/'companion.json'),'--token-file',str(path/'token'),
                '--output',str(output),'--peer-url',self.client.url,'--peer-stop-port',str(self.server.stop_address[1]),
                '--controller','fixture-controller','--source-boot',self.peer.boot_id,'--allow-capture-output']
            with patch('sys.argv',argv),patch.object(module,'ContextGateway',return_value=self.gateway),patch.object(module,'AudioAdapter',side_effect=audio),patch.object(module,'SpeechAdapter',side_effect=RuntimeError('fixture startup error')),patch.object(module,'create_server',side_effect=control),patch('builtins.print'):
                self.assertEqual(module.main(),2)
            report=json.loads(output.read_text())
            self.assertEqual(report['reason'],'startup_error');self.assertEqual(len(created),1)
            self.assertTrue(created[0].closed);self.assertTrue(self.peer.closed)
            self.assertFalse(any(report['startup_execution_busy'].values()));self.assertFalse(report['accepted'])

    def test_main_sigterm_uses_owned_stop_and_restores_prior_signal_handler(self):
        from reachy_companion.autonomous import companion_session as module
        from reachy_companion.autonomous.audio_session_control import create_server as control_server
        root=Path(__file__).resolve().parents[1];run=module.run_session;sent=[]
        before=signal.getsignal(signal.SIGTERM)
        def control(*args,**kwargs):return control_server(*args,**{**kwargs,'port':0})
        def session(*args):
            publish=args[-1]
            def stop_when_ready(value):
                publish(value)
                if value.get('listening_ready') and not sent:
                    sent.append(True);signal.raise_signal(signal.SIGTERM)
            return run(*args[:-1],stop_when_ready)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'token').write_text('t'*32)
            data=json.loads((root/'config.example.json').read_text());data['paths']['token_file']='token'
            data['runtime']['profile']='';data['guarded_motion']=dict(enabled=False,socket_path='s',policy_path='p')
            (path/'companion.json').write_text(json.dumps(data));output=path/'report.json'
            argv=['normal','--mode','normal','--config',str(root/'config.autonomous.example.json'),
                '--companion-config',str(path/'companion.json'),'--token-file',str(path/'token'),
                '--output',str(output),'--peer-url',self.client.url,'--peer-stop-port',str(self.server.stop_address[1]),
                '--controller','fixture-controller','--source-boot',self.peer.boot_id,'--allow-capture-output']
            self.lease.close();self.lease.worker.join(1)
            with patch('sys.argv',argv),patch.object(module,'ContextGateway',return_value=self.gateway),patch.object(module,'create_server',side_effect=control),patch.object(module,'run_session',side_effect=session),patch('reachy_companion.hub.Hub.agent',return_value=copy.deepcopy(self.operator)),patch('builtins.print'):
                self.assertEqual(module.main(),0)
            report=json.loads(output.read_text())
            self.assertEqual(report['reason'],'controller_stop');self.assertTrue(sent)
            self.assertTrue(report['cleanup_verified']);self.assertTrue(self.peer.closed)
            self.assertEqual(signal.getsignal(signal.SIGTERM),before)

    def test_cumulative_remote_budget_crosses_eight_and_denies_thirty_third_before_transport(self):
        remote=RemotePCM(self.client,max_streams=32)
        def reserve(path,stream_id):return dict(reserved=True,device_stream_id='device-'+stream_id)
        with patch.object(remote.transport,'call',side_effect=reserve) as calls,patch.object(remote.transport,'close'):
            for index in range(32):remote.reserve('fixture-'+str(index))
            self.assertEqual(calls.call_count,32);self.assertEqual(remote.reservation_attempts,32)
            self.assertEqual(len(remote.stream_map),32)
            with self.assertRaisesRegex(RuntimeError,'before reservation'):remote.reserve('fixture-33')
            self.assertEqual(calls.call_count,32);self.assertEqual(remote.reservation_attempts,32)

    def test_unknown_reservation_attempt_spends_budget_and_cannot_be_reclaimed(self):
        remote=RemotePCM(self.client,max_streams=2)
        with patch.object(remote.transport,'call',side_effect=TimeoutError('fixture unknown')) as calls,patch.object(remote.transport,'close'):
            for index in range(2):
                with self.assertRaises(TimeoutError):remote.reserve('fixture-'+str(index))
            with self.assertRaisesRegex(RuntimeError,'before reservation'):remote.reserve('fixture-new')
            self.assertEqual(calls.call_count,2);self.assertEqual(remote.reservation_attempts,2)
            self.assertEqual(remote.stream_map,{})


if __name__=='__main__':unittest.main()
