"""Protocol evidence with substituted IO. No device or infrastructure acceptance."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.contracts import validate
from reachy_companion.autonomous.durable import DurableStore
from reachy_companion.autonomous.runtime import Scheduler

ROOT=Path(__file__).resolve().parents[1]


class Models:
    boot_id='test-mac'
    def __init__(self):self.views=[];self.prompts=[];self.choose=lambda view:dict(a='wait',why='quiet observation')
    def fast(self,request_id,view):
        self.views.append(view)
        return dict(request_id=request_id,compute_boot_id=self.boot_id,output=self.choose(view))
    def main(self,task):
        self.prompts.append(task.prompt)
        return dict(request_id=task.attempt_id,compute_boot_id=self.boot_id,output='model inference')


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.cfg=load(ROOT/'config.autonomous.normal.example.json')
        self.cfg.update(period_s=.005,fast_deadline_s=1)
        self.cfg['context']['enabled']=False
        self.model=Models();self.scheduler=Scheduler(self.cfg,self.model)
        self.store=DurableStore(Path(self.temp.name)/'state.sqlite3')
        self.scheduler.enable_production(self.store)
    def tearDown(self):
        self.scheduler.close();self.temp.cleanup()
    def pump(self,predicate,timeout=1):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.scheduler.advance()
            if predicate():return
            time.sleep(.002)
        self.fail('Protocol did not reach expected state')

    def test_silence_and_mic_off_keep_calling_model_and_unknown_is_explicit(self):
        self.scheduler.ingest(dict(type='operator',muted=True))
        self.pump(lambda:len(self.model.views)>=4)
        view=self.model.views[-1]
        self.assertFalse(view['op']['microphone_enabled'])
        self.assertEqual({s['id'] for s in view['sensors'] if s['state']=='unknown'},
            {'camera','battery','power','servo.load','network','lidar'})
        self.assertEqual(view['dialogue'],'')
        validate('FastView',view)

    def test_cache_updates_during_blocked_main_and_expires_with_source(self):
        gate=threading.Event();started=threading.Event()
        def main(task):
            started.set();gate.wait(1)
            return dict(output='done',request_id=task.attempt_id,compute_boot_id=self.model.boot_id)
        self.model.main=main
        self.model.choose=lambda view:dict(a='think',why='reflection',start=dict(type='main',input_ref=view['candidates'][0]['alias'])) if view['candidates'] and not view['pending'] else dict(a='wait',why='processing')
        self.scheduler.services.sensors['battery']=(lambda:dict(summary='62%',ttl_ms=20),.01,'robot-power')
        try:
            self.pump(lambda:started.is_set() and self.scheduler.state.sensors['battery'].summary=='62%')
            self.assertFalse(self.scheduler.main_job.future.done())
            sensor=self.scheduler.state.sensors['battery'];now=time.monotonic()
            self.assertEqual(sensor.view(now,False)['source_id'],'robot-power')
            self.assertEqual(sensor.view(now+.1,False)['summary'],'')
            self.assertEqual(sensor.view(now+.1,False)['state'],'stale')
        finally:gate.set()

    def test_goal_cas_timestamp_restart_and_rollback(self):
        state=self.scheduler.state
        revision=state.durable_revision
        choice=dict(a='think',why='new aim',update=dict(expected_revision=revision,reason='changed priorities',patch=dict(goal='Watch the room')))
        now=time.monotonic();state.apply(choice,state.bind(now,1),now)
        goal=state.snapshot(now)['goal']
        self.assertEqual(goal['reason'],'changed priorities');self.assertTrue(goal['changed_at'].endswith('Z'))
        self.assertEqual(goal['origin'],'agent')
        with self.assertRaises(ValueError):self.store.update(dict(memory='stale'),revision,'stale update')
        self.assertEqual(self.store.current()[1]['goal'],goal)
        self.store.rollback(0,revision+1,'operator rollback');self.scheduler.services.reload()
        self.assertIsNone(state.snapshot(now)['goal'])
        other=DurableStore(Path(self.temp.name)/'state.sqlite3')
        try:self.assertEqual(other.current()[0],revision+2)
        finally:other.close()

    def test_outbox_retry_exact_ack_and_reopen(self):
        self.scheduler.config['export_enabled']=True
        self.scheduler.state.record('decision_accepted',request_id='r',activity='wait',text='private')
        event_id,body=self.store.pending('s3')
        self.assertNotIn('private',json.dumps(body))
        calls=[]
        def fail(identity,event):calls.append(identity);raise OSError('offline')
        service=self.scheduler.services;service.deliveries['s3']=fail
        self.pump(lambda:'s3' in service.errors)
        self.assertEqual(self.store.pending('s3')[0],event_id)
        service.deliveries['s3']=lambda identity,event:identity
        service.next_export['s3']=0
        self.pump(lambda:self.store.db.execute('SELECT s3 FROM outbox WHERE id=?',(event_id,)).fetchone()==(1,))
        self.assertIsNotNone(self.store.pending('vps'))
        other=DurableStore(Path(self.temp.name)/'state.sqlite3')
        try:self.assertEqual(other.pending('vps')[0],event_id)
        finally:other.close()

    def test_local_only_log_is_bounded_without_discarding_pending_exports(self):
        self.store.cap=2
        for _ in range(4):self.store.append({'kind':'local'},destinations=())
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0],2)
        self.assertIsNone(self.store.pending('s3'))
        self.store.append({'kind':'export'})
        self.store.append({'kind':'export'})
        with self.assertRaises(BufferError):self.store.append({'kind':'export'})

    def test_privacy_revokes_inflight_sensor_tool_and_updates(self):
        gate=threading.Event();service=self.scheduler.services
        service.sensors['camera']=(lambda:(gate.wait(1) or True) and dict(summary='secret',ttl_ms=2000),.5,'camera-one')
        service.tools['web']=lambda value:(gate.wait(1) or True) and dict(secret='result')
        now=time.monotonic();service.start_tool('web','query',self.scheduler.state.bind(now,1),now)
        self.scheduler.advance();self.scheduler.ingest(dict(type='operator',muted=True,privacy_all=True))
        gate.set()
        self.pump(lambda:not service.polls and not service.tool_jobs)
        self.assertFalse(self.scheduler.state.tool_results)
        self.assertNotIn('secret',json.dumps(self.scheduler.state.snapshot(time.monotonic())))
        with self.assertRaises(ValueError):service.update(dict(goal='secret'),self.scheduler.state.durable_revision,'reason',time.monotonic())

    def test_overload_drains_real_execution_once_then_consolidates(self):
        gate=threading.Event();started=threading.Event()
        self.cfg['production']['overload_latency_s']=.03
        def slow(request_id,view):
            started.set();gate.wait(1)
            return dict(output=dict(a='wait',why='done'),request_id=request_id,compute_boot_id=self.model.boot_id)
        self.model.fast=slow
        self.scheduler.advance()
        try:
            self.pump(lambda:self.scheduler.state.overload=='DRAINING')
            self.assertFalse(self.scheduler.fast_job.future.done())
            self.assertEqual(self.scheduler.state.counts['overload_entered'],1)
            self.scheduler.advance();self.assertEqual(self.scheduler.state.counts['overload_entered'],1)
        finally:gate.set()
        self.model.fast=Models.fast.__get__(self.model)
        self.pump(lambda:self.scheduler.state.counts['consolidation_completed']==1)
        self.assertEqual(self.scheduler.state.overload,'ACTIVE')
        self.assertGreaterEqual(self.scheduler.state.counts['decision_stale'],1)

    def test_stop_rejects_late_outputs_and_preserves_clock_withdrawal(self):
        self.scheduler.advance();self.scheduler.ingest(dict(type='stop'))
        self.pump(lambda:self.scheduler.fast_job is None)
        calls=len(self.model.views)
        for _ in range(10):self.scheduler.advance()
        self.assertEqual(len(self.model.views),calls)
        self.assertEqual(self.scheduler.state.counts['decision_accepted'],0)
        self.assertEqual(self.scheduler.state.snapshot(time.monotonic())['mode'],'WITHDRAWN')

    def test_main_receives_personality_goal_sensors_and_memory_inference(self):
        self.scheduler.ingest(dict(type='sensor',id='battery',summary='62%',source_id='fixture-power',ttl_ms=5000))
        self.model.choose=lambda view:dict(a='think',why='reflection',start=dict(type='main',input_ref=view['candidates'][0]['alias'])) if view['candidates'] and not view['pending'] else dict(a='wait',why='processing')
        self.pump(lambda:bool(self.model.prompts))
        prompt=self.model.prompts[0]
        self.assertEqual(prompt['schema_version'],'companion-1')
        self.assertIn('personality',prompt['state']['character'])
        self.assertTrue(prompt['observations'])
        self.assertTrue(all(sensor['state'] in ('ready','fresh') for sensor in prompt['observations']))

    def test_private_reflection_silence_does_not_become_a_spoken_answer(self):
        self.model.choose=lambda view:dict(a='think',why='request',start=dict(type='main',input_ref=view['candidates'][0]['alias'])) if view['candidates'] and not view['pending'] else dict(a='wait',why='quiet')
        self.model.main=lambda task:dict(output='[SILENT]',request_id=task.attempt_id,compute_boot_id=self.model.boot_id)
        self.pump(lambda:self.scheduler.state.counts.get('private_reflection_completed',0)==1)
        self.assertFalse(self.scheduler.state.speech_proposals)
        self.assertFalse(any(t.status=='ready' for t in self.scheduler.state.tasks.values()))
        self.scheduler.ingest(dict(type='utterance',text='Explain the literal token [SILENT]'))
        self.pump(lambda:self.scheduler.state.counts.get('proposal_ready',0)==1)
        self.assertTrue(any(t.status=='ready' for t in self.scheduler.state.tasks.values()))

    def test_tool_registry_and_late_authority(self):
        service=self.scheduler.services;now=time.monotonic()
        service.start_tool('shell','rm anything',self.scheduler.state.bind(now,1),now)
        self.assertFalse(service.tool_jobs)
        service.tools['search']=lambda argument:dict(answer='a')
        service.start_tool('search','q',self.scheduler.state.bind(now,1),now)
        self.pump(lambda:'search' in self.scheduler.state.tool_results)
        self.assertIn('answer',self.scheduler.state.tool_results['search'])

    def test_vps_update_uses_same_cas_and_periodic_memory_is_versioned(self):
        service=self.scheduler.services;state=self.scheduler.state
        service.update_reader=lambda:dict(expected_revision=state.durable_revision,reason='VPS analysis',patch=dict(goal='Observe quietly'))
        self.pump(lambda:state.character['goal'] is not None)
        self.assertEqual(state.character['goal']['reason'],'VPS analysis')
        self.model.main=lambda task:dict(output='{"memory":"inference: calm room"}',request_id=task.attempt_id,compute_boot_id=self.model.boot_id)
        service.next_memory=0
        self.pump(lambda:state.character.get('memory')=='inference: calm room')
        self.assertGreater(state.durable_revision,1)

    def test_same_state_path_refuses_second_runtime_owner(self):
        other=DurableStore(Path(self.temp.name)/'state.sqlite3')
        try:
            with self.assertRaises(RuntimeError):other.claim()
        finally:other.close()

    def test_constrained_mac_protocol_and_main_provenance_without_sockets(self):
        from reachy_companion.autonomous.gateway import ModelBackend, fast_schema, fast_projection, PRODUCTION_SYSTEM
        from jsonschema import Draft202012Validator
        class Backend(ModelBackend):
            def count(self,model,text):return len(text.split())
            def post(inner,url,payload,*args):
                inner.payload=payload
                text='{"a":"wait","why":"quiet"}' if 'json_schema' in payload else 'actual substituted completion'
                return dict(content=text,stop_type='eos')
        for role in ('fast','main'):
            model=self.cfg['models'][role]
            model.update(base_url='http://127.0.0.1:1',completion_backend='llama_native')
            model['audit'].update(verified=True,device='metal_mac',runtime_build='fixture',weight_sha256='x',
                template_sha256='x',tokenizer_sha256='x',runtime_context_tokens=4096)
        backend=Backend(self.cfg)
        view=self.scheduler.state.snapshot(time.monotonic())
        result=backend.generate('fast',view)
        self.assertEqual(result['output']['a'],'wait')
        self.assertIn(PRODUCTION_SYSTEM,backend.payload['prompt'])
        projected,_=fast_projection(view)
        schema=fast_schema(projected)
        Draft202012Validator(schema).validate(dict(a='think',why='goal',update=dict(expected_revision=0,reason='curiosity',patch=dict(goal='look'))))
        ready_schema=fast_schema({**projected,'ready':[dict(alias='r0')],
            'candidates':[dict(alias='c0',kind='main')]})
        Draft202012Validator(ready_schema).validate(dict(a='converse',why='answer ready',commit='r0'))
        with self.assertRaises(Exception):
            Draft202012Validator(ready_schema).validate(dict(a='think',why='answer starvation',
                start=dict(type='main',input_ref='c0'),commit='r0'))
        with self.assertRaises(Exception):Draft202012Validator(schema).validate(dict(a='explore',why='no grant',motion='attentive'))
        result=backend.generate('main',dict(schema_version='companion-1',utterance='think',memory=[],observations=view['sensors'],state=dict(character=self.scheduler.state.character)))
        self.assertEqual(result['completion_provenance']['kind'],'model-final-1')
        with patch.object(backend,'post',return_value=dict(content='{"speak":false,"text":""}',stop_type='eos')):
            private=backend.generate('main',dict(schema_version='companion-1',utterance='private reflection',
                memory=[],observations=[],state=dict(self_directed=True)))
        self.assertEqual(private['output'],'[SILENT]')

    def test_short_speech_and_motion_share_binding_and_keep_guards(self):
        state=self.scheduler.state;now=time.monotonic()
        state.speech_attached=True;state.motion_allowed=True;state.actor_deadline=now+1;state.actor_binding={'owner':'fixture'}
        binding=state.bind(now,1)
        state.apply(dict(a='explore',why='observed sound',say='Хмм',motion='attentive'),binding,now)
        self.assertEqual(state.motion_proposals[0]['request_id'],state.speech_proposals[0]['request_id'])
        self.assertTrue(state.snapshot(now)['runtime']['working']['last_speech_proposal'].endswith('Хмм'))
        state.motion_proposals.clear();state.speech_proposals.clear();state.privacy=True
        state.apply(dict(a='explore',why='ignore privacy',motion='attentive'),state.bind(now,1),now)
        self.assertFalse(state.motion_proposals)
        self.assertEqual(state.counts['motion_capability_rejected'],1)

    def test_router_only_model_cannot_send_direct_speech(self):
        state=self.scheduler.state;state.speech_attached=True
        self.cfg['models']['fast']['direct_speech']=False
        now=time.monotonic()
        state.apply(dict(a='wait',why='untrusted shortcut',say='internal status'),state.bind(now,1),now)
        self.assertFalse(state.speech_proposals)
        self.assertEqual(state.counts['capability_rejected'],1)

    def test_quiet_level_measurement_reaches_cache_without_an_utterance(self):
        import struct
        from reachy_companion.autonomous.audio_adapter import AudioAdapter
        from reachy_companion.autonomous.audio_peer import AudioPeer
        peer=object.__new__(AudioPeer);peer.lock=threading.RLock();peer.clock=time.monotonic
        peer.permitted=lambda:True
        samples=struct.pack('<'+'h'*320,*([12]*320))
        self.assertTrue(peer.publish_level(samples,time.monotonic()))
        self.assertGreater(peer.audio_level['rms'],0)
        self.assertTrue(peer.publish_level(bytes(640),time.monotonic()))
        self.assertLess(peer.audio_level['delta'],0)
        adapter=AudioAdapter(None);adapter.bind_source('capture',0)
        now=time.monotonic();authority=self.scheduler.state.authority
        op=dict(binding=('agent',0,0),microphone_enabled=True,quiet=False,privacy_all=False,valid_until=now+1)
        self.assertIsNone(adapter.advance(authority,op))
        self.assertTrue(adapter.observe_level(dict(rms=peer.audio_level['rms'],delta=peer.audio_level['delta'],capture_age_s=0),
            started=now,source_boot='capture',authority=authority,operator_binding=op['binding']))
        event=adapter.drain_level(authority);self.scheduler.ingest(event)
        sensor=self.scheduler.state.snapshot(time.monotonic())['sensors'][0]
        self.assertEqual(sensor['id'],'audio.level');self.assertEqual(sensor['source_id'],'capture')
        adapter.advance(authority,dict(op,microphone_enabled=False))
        self.assertIsNone(adapter.drain_level(authority))
        adapter.close()

    def test_unknown_tool_completion_remains_durable_and_blocks_drain(self):
        service=self.scheduler.services
        def lost(request):raise TimeoutError('remote terminal unknown')
        service.tools['shell']=lost
        now=time.monotonic();service.start_tool('shell','approved task',self.scheduler.state.bind(now,1),now)
        self.pump(lambda:self.scheduler.state.overload=='DRAINING')
        self.assertIn('shell',service.unresolved)
        self.assertIn('shell',self.store.tool_pending())
        self.assertNotIn('shell',self.scheduler.state.snapshot(time.monotonic())['runtime']['tools'])
        for _ in range(5):self.scheduler.advance()
        self.assertEqual(self.scheduler.state.overload,'DRAINING')

    def test_joined_production_keeps_clock_after_microphone_peer_withdrawal(self):
        from types import SimpleNamespace
        from reachy_companion.autonomous.companion_session import run_session
        stop=threading.Event();renewals=[]
        def speech_status():return dict(execution_busy=False,tts_execution_busy=False,cancellation_execution_busy=False,stop_known=True)
        backend=SimpleNamespace(close_transport=lambda:None,reservation_attempts=0)
        playback=SimpleNamespace(backend=backend,status=lambda:dict(execution_busy=False))
        receipt=lambda:dict(binding=('agent',1,1),microphone_enabled=False,quiet=False,privacy_all=False,valid_until=time.monotonic()+1)
        self.scheduler.speech_adapter=SimpleNamespace(advance=lambda a:None,operator_view=receipt,status=speech_status,close=lambda:None,playback=playback,lock=threading.RLock(),operator_receipt=receipt())
        self.scheduler.audio_adapter=SimpleNamespace(status=lambda:dict(execution_busy=False,source_boot=None),advance=lambda a,r:None,close=lambda:None,allowed=False)
        self.model.call=lambda path:dict(compute_boot_id=self.model.boot_id,quarantined=[])
        poller=SimpleNamespace(status=lambda:dict(execution_busy=False),close=lambda:None)
        lease=SimpleNamespace(source_boot='source',authority=dict(agent_boot_id='agent',microphone_epoch=0,policy_epoch=0),
            last_accepted=None,armed=True,datagram=None,status=lambda:dict(execution_busy=False,withdrawn=True),
            close=lambda:None,tick=lambda *a:renewals.append(a))
        def peer_call(path,**kw):
            if path=='/stop':return dict(stop_known=True,execution_busy=False)
            return dict(source_boot='source',closed=True,permitted=False,operator_ready=False,lifetime='lease',lease_binding=lease.authority)
        client=SimpleNamespace(call=peer_call)
        # Binding check rejects this withdrawn peer; the independent clock still runs.
        timer=threading.Timer(.06,stop.set);timer.start()
        try:report=run_session(self.scheduler,poller,lease,client,client,'source',stop,None,lambda value:None,lifetime='lease')
        finally:timer.join()
        self.assertEqual(report['errors'],[],report)
        self.assertGreaterEqual(len(self.model.views),3)
        self.assertEqual(report['reason'],'controller_stop')
        self.assertFalse(renewals)
        self.assertFalse(report['accepted']) # no device acceptance from substitute IO

    def test_deployment_hook_renders_only_existing_production_session(self):
        import importlib.util
        from types import SimpleNamespace
        spec=importlib.util.spec_from_file_location('production_deploy',ROOT/'deploy/autonomous/observer_service.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        args=SimpleNamespace(config='normal.json',token_file='token',companion_config='hub.json',output='report.json')
        argv=module.production_arguments(args,dict(peer_url='https://device.invalid',peer_stop_port=9001,source_boot='known',controller='owner',status_port=9002))
        self.assertIn('--lifetime',argv);self.assertIn('lease',argv)
        self.assertEqual(argv[0],'companion-autonomous')
        self.assertNotIn('--allow-native-observation',argv)

    def test_character_changes_are_rate_limited_and_mic_off_does_not_poll_audio(self):
        service=self.scheduler.services;state=self.scheduler.state
        service.update(dict(personality='curious'),state.durable_revision,'reflection',time.monotonic())
        with self.assertRaises(ValueError):service.update(dict(personality='different'),state.durable_revision,'too soon',time.monotonic())
        calls=[]
        service.sensors['audio.extra']=(lambda:calls.append(1),.01,'capture')
        self.scheduler.ingest(dict(type='operator',muted=True))
        self.pump(lambda:len(self.model.views)>=3)
        self.assertFalse(calls)

    def test_s3_sigv4_real_request_shape_and_missing_credentials(self):
        import hashlib
        from unittest.mock import patch
        from reachy_companion.autonomous.durable import Delivery
        sink=Delivery('s3',dict(bucket='reachy-logs',region='eu-central-1',prefix='sessions'))
        with patch.dict('os.environ',{'AWS_ACCESS_KEY_ID':'fixture-access','AWS_SECRET_ACCESS_KEY':'fixture-secret','AWS_SESSION_TOKEN':'fixture-session'},clear=True):
            request=sink.s3_request('event-123',dict(id='event-123',metadata=dict(kind='decision')))
            self.assertEqual(request.get_method(),'PUT')
            self.assertTrue(request.full_url.endswith('/sessions/event-123.json'))
            self.assertEqual(request.get_header('X-amz-content-sha256'),hashlib.sha256(request.data).hexdigest())
            self.assertEqual(request.get_header('X-amz-security-token'),'fixture-session')
            self.assertIn('/eu-central-1/s3/aws4_request',request.get_header('Authorization'))
            self.assertIn('Signature=',request.get_header('Authorization'))
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(ValueError):sink.s3_request('event-123',dict(id='event-123'))

    def test_unavailable_motion_owner_does_not_stop_temporal_decisions(self):
        from types import SimpleNamespace
        self.scheduler.motion_adapter=SimpleNamespace(refresh=lambda:(_ for _ in ()).throw(OSError('offline')),close=lambda:True)
        self.pump(lambda:len(self.model.views)>=3)
        self.assertFalse(self.model.views[-1]['op']['motion_allowed'])

    def test_model_client_timeout_waits_exact_remote_terminal_without_repost(self):
        from reachy_companion.autonomous.runtime import RemoteGateway,Job
        gateway=object.__new__(RemoteGateway);gateway.config=self.cfg;gateway.boot_id='test-mac'
        terminal=threading.Event();queried=threading.Event();calls=[]
        def call(path,payload=None):
            calls.append(path)
            if path=='/decision':raise TimeoutError('response lost')
            queried.set()
            return dict(compute_boot_id='test-mac',executions=dict(fast=dict(request_id='request',status='terminal' if terminal.is_set() else 'running')))
        gateway.call=call
        job=Job(gateway.fast,'request',{})
        self.assertTrue(queried.wait(.5));self.assertFalse(job.future.done())
        terminal.set()
        deadline=time.monotonic()+.5
        while not job.future.done() and time.monotonic()<deadline:time.sleep(.002)
        with self.assertRaises(RuntimeError):job.future.result(timeout=.1)
        self.assertEqual(calls.count('/decision'),1)

    def test_gateway_health_tracks_request_execution_not_transport_deadlines(self):
        from reachy_companion.autonomous.gateway import Gateway
        gate=threading.Event();started=threading.Event()
        class Backend:
            def generate(self,role,data):
                started.set();gate.wait(1)
                return dict(output=dict(a='wait',why='finished'))
        gateway=Gateway(Backend())
        from reachy_companion.autonomous.runtime import Job
        job=Job(gateway.generate,'fast',{},'exact-request')
        try:
            self.assertTrue(started.wait(.5))
            self.assertEqual(gateway.health()['executions']['fast'],dict(request_id='exact-request',status='running'))
        finally:gate.set()
        job.future.result(timeout=.5)
        self.assertEqual(gateway.health()['executions']['fast'],dict(request_id='exact-request',status='terminal'))


if __name__=='__main__':unittest.main()
