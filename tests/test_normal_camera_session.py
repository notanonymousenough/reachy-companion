"""In-process transport fixtures: no HTTP, model, device or live acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from reachy_companion.autonomous.audio_adapter import AudioAdapter
from reachy_companion.autonomous.audio_peer import AudioPeer,AudioPolling,RemotePCM
from reachy_companion.autonomous.companion_session import run_session,session_context
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.context import ContextProvider
from reachy_companion.autonomous.playback import Playback,ReplayPCM
from reachy_companion.autonomous.runtime import Scheduler
from reachy_companion.autonomous.speech_adapter import SpeechAdapter
from reachy_companion.autonomous.video_adapter import decode_packet,LatestFrameProcessor

ROOT=Path(__file__).resolve().parents[1]


class SelectionTests(unittest.TestCase):
    def test_cli_requires_camera_opt_in_before_constructing_any_runtime_resource(self):
        from reachy_companion.autonomous import companion_session as module
        with tempfile.TemporaryDirectory() as directory:
            token=Path(directory)/'token';token.write_text('fixture-'*4)
            argv=['normal','--mode','normal','--config',str(ROOT/'config.autonomous.normal.example.json'),
                '--companion-config',str(Path(directory)/'companion.json'),'--token-file',str(token),
                '--output',str(Path(directory)/'report.json'),'--peer-url','http://127.0.0.1:1',
                '--peer-stop-port','2','--controller','fixture','--source-boot','fixture','--allow-capture-output']
            with patch('reachy_companion.config.Config'),patch('reachy_companion.hub.Hub') as hub,patch.object(
                    module,'ContextGateway',side_effect=RuntimeError('offline construction boundary')) as gateway:
                with patch('sys.argv',argv),self.assertRaises(ValueError):module.main()
                hub.assert_not_called();gateway.assert_not_called()
                with patch.dict('os.environ',{}),patch('sys.argv',argv+['--allow-camera-context']),self.assertRaisesRegex(
                        RuntimeError,'offline construction boundary'):module.main()
                hub.assert_called_once();gateway.assert_called_once()
                self.assertIsNone(gateway.call_args.args[1])

    def test_candidate_selects_existing_camera_provider_without_memory_readback(self):
        cfg=load(ROOT/'config.autonomous.normal.example.json')
        self.assertEqual(cfg['period_s'],2)
        self.assertEqual(cfg['context']['namespaces'],['normal'])
        self.assertFalse(cfg['models']['fast']['audit']['verified'])
        self.assertIsNone(session_context(cfg,allow_camera=True))
        with self.assertRaises(ValueError):session_context(cfg)

    def test_camera_opt_in_rejects_disabled_missing_producer_and_memory_only(self):
        base=load(ROOT/'config.autonomous.normal.example.json')
        for change in (dict(enabled=False),dict(video_url=None),dict(mode='memory_only')):
            cfg=copy.deepcopy(base);cfg['context'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):session_context(cfg,allow_camera=True)
        for kwargs in (dict(readback=Path('absent')),dict(readback_sha256='a'*64)):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):session_context(base,allow_camera=True,**kwargs)

    def test_memory_only_whitelist_still_checks_exact_readback_and_hash(self):
        cfg=load(ROOT/'config.autonomous.example.json');cfg['context'].update(enabled=True,mode='memory_only')
        artifact=dict(action='readback',accepted=True,live_source_chain_validated=True,model_inference=False,
            state_projection_verified=True,content_whitelist_verified=True,versions=[1],revision=0,
            store_id='fixture-store',memory_projection_sha256='a'*64,memory_descriptor_sha256='b'*64)
        with patch('reachy_companion.autonomous.voice_memory_fixture.read_json',return_value=(artifact,'c'*64)):
            binding=session_context(cfg,readback=Path('fixture'),readback_sha256='c'*64)
            self.assertEqual(binding['store_id'],'fixture-store')
            with self.assertRaises(ValueError):session_context(cfg,readback=Path('fixture'),readback_sha256='d'*64)
        self.assertIsNone(session_context(load(ROOT/'config.autonomous.example.json')))


class ConsumedPCM(ReplayPCM):
    @property
    def stream(self):return self.current
    def progress(self,stream):
        self.advance(stream,16000)
        return super().progress(stream)


class FixtureTTS:
    def __init__(self):self.calls=[]
    def stream(self,text,cancel):
        self.calls.append(text);yield b'\0\0'*160
    def cancel(self):pass


class InProcessClient:
    """Dispatch the real peer protocol without creating a socket."""
    def __init__(self,peer):self.peer=peer
    def call(self,path,**body):
        return self.peer.dispatch(path,dict(body,controller=self.peer.controller))
    def at_port(self,port):return self
    def close(self):pass


class FixtureLease:
    def __init__(self,client):
        self.client=client;self.last_accepted=None;self.datagram=None;self.closed=False
    def tick(self):
        if not self.closed and self.client.peer.cached_operator is not None:
            self.client.call('/lease');self.last_accepted=time.monotonic()
    def status(self):return dict(execution_busy=False)
    def close(self):self.closed=True


class FixtureGateway:
    boot_id='fixture-compute'
    def __init__(self,provider):
        self.provider=provider;self.views=[];self.fast_ids=[];self.main_entered=threading.Event()
        self.main_release=threading.Event();self.hold_fast=False;self.fast_entered=threading.Event()
        self.fast_release=threading.Event();self.literal='Алиса, сколько будет два плюс два?'
    def call(self,path):
        if path!='/health':raise AssertionError(path)
        return dict(compute_boot_id=self.boot_id,quarantined=[])
    def context(self,request_id,query,privacy,authority):
        output=self.provider.snapshot(query,privacy,authority.hub_boot_id,authority.operator_epoch)
        return dict(output=output,request_id=request_id,compute_boot_id=self.boot_id)
    def revoke_context(self,authority,terminal=False):
        output=self.provider.revoke(authority.hub_boot_id,authority.operator_epoch,terminal)
        return dict(output=output,request_id='fixture-revoke',compute_boot_id=self.boot_id)
    def fast(self,request_id,view):
        self.views.append(copy.deepcopy(view));self.fast_ids.append(request_id)
        if self.hold_fast:
            self.fast_entered.set();self.fast_release.wait(3)
        choice=dict(a='wait',why='Synthetic idle decision')
        if view['ready']:choice=dict(a='converse',why='Synthetic commit',commit=view['ready'][0]['alias'])
        elif view['candidates'] and not view['pending']:
            choice=dict(a='think',why='Synthetic start',start=dict(type='main',input_ref=view['candidates'][0]['alias']))
        return dict(output=choice,request_id=request_id,compute_boot_id=self.boot_id)
    def main(self,task):
        self.main_entered.set();self.main_release.wait(3)
        return dict(output=self.literal,request_id=task.attempt_id,compute_boot_id=self.boot_id)


class NormalCameraTests(unittest.TestCase):
    def setUp(self):
        # Enforce the offline boundary even if a fixture accidentally regresses.
        self.no_socket=patch('socket.socket',side_effect=AssertionError('No HTTP/device transport in N0 tests'))
        self.no_socket.start();self.addCleanup(self.no_socket.stop)
        self.no_process=patch('subprocess.Popen',side_effect=AssertionError('No second physical owner'))
        self.no_process.start();self.addCleanup(self.no_process.stop)
        self.operator=dict(agent_boot_id='fixture-agent',microphone_epoch=1,microphone_enabled=True,
            microphone_owner_id='fixture-owner',microphone_state_error=None,listening=False,phase='paused',
            motion_policy=dict(epoch=1,quiet=False,privacy_all=False,motor_enabled=False))
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.provider=ContextProvider(dict(memory_path=str(Path(self.tmp.name)/'context.sqlite'),namespaces=['normal']),'fixture-compute')
        self.addCleanup(self.provider.close)
        self.provider.video_worker=LatestFrameProcessor(self.provider.video_completed)
        self.gateway=FixtureGateway(self.provider)
        self.peer=AudioPeer(Playback(ConsumedPCM(),allow_simulated=True,chunk_frames=4096),
            lambda:copy.deepcopy(self.operator),
            dict(agent_boot_id='fixture-agent',owned_microphone_epoch=1,owner_id='fixture-owner',policy_epoch=1),
            controller='fixture-controller')
        self.client=InProcessClient(self.peer)
        self.transport=patch('reachy_companion.autonomous.audio_peer.PersistentPeer',return_value=self.client)
        self.transport.start();self.addCleanup(self.transport.stop)
        self.playback=Playback(RemotePCM(self.client,source_boot=self.peer.boot_id,stop_port=2,max_streams=32),
            allow_simulated=True,chunk_frames=4096)
        self.tts=FixtureTTS();self.speech=SpeechAdapter(self.playback,self.tts,lambda:copy.deepcopy(self.operator))
        class NoSTT:
            def transcribe(self,pcm):raise AssertionError('No utterance was supplied')
        self.audio=AudioAdapter(NoSTT());self.poller=AudioPolling(self.client,self.audio,self.peer.boot_id)
        self.lease=FixtureLease(self.client)
        cfg=load(ROOT/'config.autonomous.normal.example.json')
        cfg.update(period_s=.015,fast_deadline_s=1);cfg['context']['refresh_s']=.02
        self.scheduler=Scheduler(cfg,self.gateway,speech_adapter=self.speech,audio_adapter=self.audio)
        self.stop=threading.Event();self.producer_stop=threading.Event();self.reports=[];self.latest=[]
        self.input_event=None
        self.produced=0;self.producer_errors=[]
        self.producer=threading.Thread(target=self.produce,daemon=True);self.producer.start()
        self.runner=None

    def produce(self):
        while not self.producer_stop.wait(.005):
            try:
                with self.provider.policy_lock:
                    if self.provider.scope is None or self.provider.privacy_all:continue
                    ticket=(dict(self.provider.scope),self.provider.video_generation,self.provider.video_admission)
                self.produced+=1
                raw=b'P6\n1 1\n255\n'+bytes([self.produced%256,0,0])
                meta=dict(video_protocol=2,audio_initialised=False,scope=ticket[0],admission_id=ticket[2],
                    producer_boot_id='fixture-camera',seq=self.produced,frame_id='fixture-frame-'+str(self.produced),
                    lineage_id='fixture-camera',frame_sha256=hashlib.sha256(raw).hexdigest(),
                    pts_ns=0,buffer_running_time_ns=0)
                encoded=json.dumps(meta).encode()
                metadata,pixels=decode_packet(struct.pack('!I',len(encoded))+encoded+raw)
                self.provider.admit_video(metadata,pixels,time.monotonic(),ticket)
            except Exception as exc:self.producer_errors.append(type(exc).__name__)

    def start(self):
        def publish(value):
            self.latest.append(value)
            # Trusted fixture input enters on the existing reducer thread.
            event,self.input_event=self.input_event,None
            if event is not None:self.scheduler.ingest(event)
        self.runner=threading.Thread(target=lambda:self.reports.append(run_session(
            self.scheduler,self.poller,self.lease,self.client,self.client,self.peer.boot_id,self.stop,3,publish)))
        self.runner.start()

    def wait(self,predicate):
        deadline=time.monotonic()+2
        while not predicate() and time.monotonic()<deadline:time.sleep(.005)
        self.assertTrue(predicate(),self.reports)

    def tearDown(self):
        self.gateway.main_release.set();self.gateway.fast_release.set();self.stop.set();self.producer_stop.set()
        if self.runner:self.runner.join(3)
        self.producer.join(1);self.scheduler.close();self.peer.close();self.peer.watch.join(1)
        for name in ('fast_job','main_job','context_job','context_terminal_job'):
            job=getattr(self.scheduler,name)
            if job:job.thread.join(1)
        self.provider.close()

    def test_silent_decisions_pending_main_camera_progress_and_exact_literal_speech(self):
        self.start()
        self.wait(lambda:self.scheduler.state.counts['decision_accepted']>=12)
        silent=list(self.gateway.fast_ids)
        self.assertGreaterEqual(len(set(silent)),12)
        self.assertTrue(all(view['dialogue']=='' for view in self.gateway.views))
        self.assertEqual(self.scheduler.state.counts['new_turn'],0)
        # The busy-main phase starts only after the independent silent phase.
        self.input_event=dict(type='utterance',text='Synthetic main request')
        self.assertTrue(self.gateway.main_entered.wait(1))
        before=(len(self.gateway.fast_ids),self.produced,self.poller.calls)
        accepted_before=self.scheduler.state.counts['decision_accepted']
        self.wait(lambda:len([v for v in self.gateway.views if v['pending']])>=5)
        pending=[v for v in self.gateway.views if v['pending']]
        frames={s['source_id'] for v in pending for s in v['sensors'] if s.get('source_id')}
        self.assertGreaterEqual(len(frames),2)
        self.assertGreater(len(self.gateway.fast_ids),before[0]+2)
        completed=self.scheduler.state.counts['decision_accepted']-accepted_before
        self.assertGreaterEqual(completed,2)
        self.assertGreater(self.produced,before[1]);self.assertGreater(self.poller.calls,before[2])
        self.offline_metrics=dict(silent_unique_request_ids=len(set(silent)),pending_fast_snapshots=len(pending),
            fast_completions_during_main=completed,pending_distinct_frame_ids=len(frames),synthetic_frames_during_main=self.produced-before[1],
            audio_polls_during_main=self.poller.calls-before[2],actual_model_inference=False,hardware=False)
        for view in self.gateway.views:
            self.assertLessEqual(len(view['sensors']),12);self.assertLessEqual(len(view['pending']),8)
            for sensor in view['sensors']:
                self.assertIn(sensor['state'],('unknown','no_data','stale'))
                self.assertIsNone(sensor['age_bounds_ms']['upper']);self.assertEqual(sensor['summary'],'')
        self.assertLessEqual(self.provider.video_worker.status()['pending_raw_frames'],1)
        self.assertFalse(self.producer_errors)
        self.gateway.main_release.set();self.wait(lambda:bool(self.tts.calls))
        self.assertEqual(self.tts.calls,[self.gateway.literal])
        self.wait(lambda:bool(self.speech.status()['receipts']) and not self.speech.status()['execution_busy'])
        self.stop.set();self.runner.join(2);self.assertFalse(self.runner.is_alive())
        report=self.reports[0]
        self.assertTrue(report['cleanup_verified']);self.assertTrue(report['accepted'])
        self.assertGreaterEqual(len(report['decisions']),12)
        self.assertEqual(len({d['request_id'] for d in report['decisions']}),len(report['decisions']))
        self.assertLessEqual(len(report['decisions']),self.scheduler.config['ledger_cap'])
        self.assertFalse(report['continuous_acceptance']);self.assertFalse(report['execution_busy']['main'])

    def test_authority_revoke_during_main_suppresses_late_speech_and_old_camera_admission(self):
        self.start();self.wait(lambda:self.scheduler.state.counts['context_updated']>0)
        self.input_event=dict(type='utterance',text='Synthetic pending request')
        self.assertTrue(self.gateway.main_entered.wait(1))
        with self.provider.policy_lock:
            old=(dict(self.provider.scope),self.provider.video_generation,self.provider.video_admission)
        self.operator['microphone_enabled']=False;self.operator['microphone_epoch']=2
        self.operator['microphone_owner_id']=None
        self.wait(lambda:self.stop.is_set())
        self.gateway.main_release.set();self.runner.join(2)
        self.scheduler.main_job.thread.join(1);self.scheduler.advance()
        self.assertTrue(self.scheduler.closed);self.assertFalse(self.tts.calls)
        self.assertFalse(self.provider.video_current(old));self.assertIsNone(self.provider.video.current)
        with self.assertRaises(ValueError):self.provider.snapshot('',False,old[0]['hub_boot_id'],old[0]['operator_epoch'])
        self.assertFalse(self.reports[0]['accepted'])

    def test_occupied_fast_does_not_pause_camera_or_audio_poll_and_late_result_cannot_act(self):
        self.gateway.hold_fast=True;self.start()
        self.assertTrue(self.gateway.fast_entered.wait(1))
        self.wait(lambda:self.provider.video.current is not None)
        before=(self.produced,self.poller.calls)
        self.wait(lambda:self.produced>=before[0]+10 and self.poller.calls>=before[1]+2)
        self.assertEqual(len(self.gateway.fast_ids),1)
        self.stop.set();self.gateway.fast_release.set();self.runner.join(2)
        self.scheduler.fast_job.thread.join(1);self.scheduler.advance()
        self.assertFalse(self.tts.calls);self.assertEqual(self.scheduler.state.counts['decision_accepted'],0)
        self.assertFalse(self.scheduler.state.speech_proposals)


if __name__=='__main__':unittest.main()
