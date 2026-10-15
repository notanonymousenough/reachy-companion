"""Synthetic protocol DTOs and real local State/SQLite; never actual voice proof."""
import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
from reachy_companion.autonomous import voice_chain as chain
from reachy_companion.autonomous import voice_memory_fixture as memory
from reachy_companion.autonomous.state import State
from reachy_companion.autonomous.runtime import ReplayGateway,Scheduler,RemoteGateway
from reachy_companion.autonomous.gateway import ModelBackend
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.playback import Playback,ReplayPCM
from reachy_companion.autonomous.speech_adapter import SpeechAdapter

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('chain_fixture_receipts',ROOT/'tests/test_voice_memory_acceptance.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def receipts(items=None,*,store_id=None,revision=-1):
    hub,device=fixture.receipts();hub['working_memory_receipt_schema']='voice-working-2'
    hub['receipt_overflow']=dict(turns=False,main=False)
    hub['transcripts_retained']=False
    hub['context_enabled']=items is not None
    if items is not None:hub['context_terminal_revoke']={'output':dict(revoked=True,terminal=True,hub_boot_id=hub['hub_boot_id'])}
    for index,turn in enumerate(hub['turns']):
        text='Synthetic neutral practice response';data=text if items is None else dict(schema_version='context-1',utterance=text,memory=items,observations=[])
        final=chain.model_final(data,'Neutral fixture reply','llama_native','fixture-model')
        begin=1.+index*10
        turn.update(received_at=begin,stt_provenance='pc_http_stt',ttl_ms=2000,stt_text_sha256=chain.digest(text),
            main_final=dict(task_id='task-'+str(index),attempt_id='attempt-'+str(index),input_ref=turn['working_input_ref'],
                authority=copy.deepcopy(turn['working_authority']),created_at=begin+.1,completed_at=begin+1,
                deadline=begin+5,committed_at=begin+1.1,proposal_expires=begin+5,final=final),
            reply_playback=dict(stream_id='stream-'+str(index),authority=copy.deepcopy(turn['working_authority']),
                operator_binding=turn['working_operator_binding'][:],output_sha256=final['output_sha256'],tts_complete=True,cancelled=False,
                verified_stopped=True,provenance='device_consumed_pcm',tts_frames=3200,max_measured_consumed=3200,
                producer_started_at=begin+1.2,first_consumed_at=begin+1.3,deadline=begin+5))
        turn['main_final'].update(memory_store_id=store_id,memory_revision=revision)
    return hub,device


class ChainTests(unittest.TestCase):
    def test_actual_audited_gateway_rejects_extra_fast_sensor_before_transport_or_model(self):
        state=State();meta=dict(item_id='fixture-note',namespace='fixture-space',created_at='2020-01-01T00:00:00Z',
            voice=dict(lineage_id='fixture-source'),operator_root='fixture-owner')
        item=memory.item(meta,2)
        state.update_context(dict(memory=dict(store_id='store',revision=3,items=[item]),sensors=[]),0)
        clean=state.snapshot(0)
        report=dict(action='readback',accepted=True,live_source_chain_validated=True,model_inference=False,
            state_projection_verified=True,content_whitelist_verified=True,versions=[2],store_id='store',revision=3,
            memory_projection_sha256=chain.digest([item]),memory_descriptor_sha256=chain.digest(clean['memory']))
        binding=chain.context_binding(report);cfg=load(ROOT/'config.autonomous.example.json')
        cfg['gateway'].update(client_url='http://127.0.0.1:1',token_env='CHAIN_FIXTURE_TOKEN')
        cfg['models']['fast'].update(completion_backend='llama_native',base_url='http://127.0.0.1:1',id='fixture-fast',decision_format='object')
        backend=ModelBackend(cfg);backend.count=lambda *args:1;transport_calls=[];model_calls=[]
        def model(url,payload,*args):
            model_calls.append(payload)
            return dict(content=json.dumps(dict(a='wait',why='fixture')),stop_type='word',tokens_predicted=3)
        backend.post=model
        def transport(owner,path,payload=None):
            if path=='/health':return dict(compute_boot_id='fixture-compute')
            transport_calls.append(path)
            return {**backend.generate_loaded('fast',payload['data']), 'request_id':payload['request_id']}
        with patch.dict(os.environ,CHAIN_FIXTURE_TOKEN='fixture-token'*4),patch.object(RemoteGateway,'call',transport):
            gateway=fixture.runtime.AuditedGateway(cfg,memory_scope=binding)
            gateway.fast('clean',clean);self.assertEqual(len(transport_calls),1);self.assertEqual(len(model_calls),1)
            transport_calls.clear();model_calls.clear()
            state.ingest(dict(type='sensor',id='camera.extra',summary='Unexpected camera fixture summary',availability='available'),0)
            injected=state.snapshot(0) # real schema-validated State/FastView
            self.assertEqual(injected['memory'],clean['memory']);self.assertTrue(injected['sensors'])
            with self.assertRaises(ValueError):gateway.fast('extra-camera',injected)
            extra=copy.deepcopy(clean);extra['observations']=[dict(summary='Unexpected observation fixture')]
            with self.assertRaises(ValueError):gateway.fast('extra-observation',extra)
            unknown=copy.deepcopy(clean);unknown.pop('sensors')
            with self.assertRaises(ValueError):gateway.fast('unknown-sensors',unknown)
            self.assertFalse(transport_calls);self.assertFalse(model_calls)
            # Ordinary profile keeps its existing sensor path; no global camera disable.
            ordinary=fixture.runtime.AuditedGateway(cfg)
            ordinary.fast('ordinary-camera',injected)
            self.assertEqual(len(transport_calls),1);self.assertEqual(len(model_calls),1)

    def test_legacy_working_one_is_not_strict_live_source_and_mutated_chain_is_rejected(self):
        hub,device=fixture.receipts();binding=dict(controller='controller',session_boot='session',source_boot='source')
        memory.voice_provenance(hub,device,binding) # existing neutral workflow remains supported
        with self.assertRaises(ValueError):memory.voice_provenance(hub,device,binding,require_live=True)
        hub,device=receipts();memory.voice_provenance(hub,device,binding,require_live=True)
        changes=[lambda t:t.update(stt_provenance='fixture_or_unverified_stt'),lambda t:t.update(capture_age_ms=2000),
            lambda t:t['main_final']['final'].update(backend='replay'),lambda t:t['main_final']['final'].update(kind='scripted'),
            lambda t:t['main_final']['final'].update(utterance_sha256='a'*64),lambda t:t['main_final'].update(input_ref='foreign'),
            lambda t:t['main_final']['authority'].update(microphone_epoch=999),lambda t:t['main_final'].update(completed_at=100),
            lambda t:t['main_final'].update(committed_at=100),lambda t:t['reply_playback'].update(provenance='simulated_consumed_pcm'),
            lambda t:t['reply_playback'].update(max_measured_consumed=3199),lambda t:t['reply_playback'].update(max_measured_consumed=True),
            lambda t:t['reply_playback'].update(output_sha256='b'*64),lambda t:t['reply_playback'].update(cancelled=True),
            lambda t:t['reply_playback'].update(operator_binding=['new-agent',1,0]),lambda t:t['reply_playback'].update(first_consumed_at=100)]
        for index,change in enumerate(changes):
            bad=copy.deepcopy(hub);change(bad['turns'][0])
            with self.subTest(index=index),self.assertRaises(ValueError):memory.voice_provenance(bad,device,binding,require_live=True)
        bad=copy.deepcopy(hub);bad['turns'][1]['main_final']['attempt_id']=bad['turns'][0]['main_final']['attempt_id']
        with self.assertRaises(ValueError):memory.voice_provenance(bad,device,binding,require_live=True)

    def test_canonical_state_binds_actual_final_and_does_not_upgrade_replay_or_stale_result(self):
        state=State();state.speech_attached=True;state.ingest(dict(type='utterance',text='Neutral fixture input'),0)
        ref=next(iter(state.candidates));task=state.apply(dict(a='think',why='fixture',start=dict(type='main',input_ref=ref)),state.bind(0,5),0)
        output='Neutral fixture output';proof=chain.model_final(task.prompt,output,'completion_http','fixture-model')
        state.complete(task.task_id,task.attempt_id,task.authority,output,.1,provenance=proof)
        state.apply(dict(a='converse',why='fixture',commit=task.task_id),state.bind(.2,5),.2)
        proposal=state.speech_proposals.pop();self.assertEqual(proposal['main_receipt']['input_ref'],ref)
        self.assertEqual(proposal['main_receipt']['final'],proof)
        self.assertNotIn(output,json.dumps(proposal['main_receipt']))
        replay=ReplayGateway(0).main(task);self.assertNotIn('completion_provenance',replay)
        for kind in ('bad_hash','late'):
            other=State();other.ingest(dict(type='utterance',text='Other neutral input'),0);ref=next(iter(other.candidates))
            pending=other.apply(dict(a='think',why='fixture',start=dict(type='main',input_ref=ref)),other.bind(0,5),0)
            bad=chain.model_final(pending.prompt,output,'completion_http','fixture-model')
            if kind=='bad_hash':bad['output_sha256']='a'*64
            other.complete(pending.task_id,pending.attempt_id,pending.authority,output,
                pending.deadline+1 if kind=='late' else .1,provenance=bad)
            self.assertNotEqual(pending.status,'ready');self.assertFalse(other.speech_proposals)

    def test_turn_to_speech_is_identity_correlated_not_positional_or_ambiguous(self):
        hub,_=receipts();turns=copy.deepcopy(hub['turns']);calls=[];speeches=[];consumed=[]
        for turn in turns:
            main=turn.pop('main_final');play=turn.pop('reply_playback')
            calls.append(dict(task_id=main['task_id'],attempt_id=main['attempt_id'],input_ref=main['input_ref'],final=main['final']))
            speeches.insert(0,dict(main_receipt=main,**play));consumed.append(play)
        chain.attach_turns(turns,calls,speeches,consumed)
        self.assertEqual(turns[0]['main_final']['input_ref'],turns[0]['working_input_ref'])
        with self.assertRaises(ValueError):chain.attach_turns(turns,calls,speeches+speeches[:1],consumed)

    def test_strict_prepare_owner_cas_new_session_context_and_forget_use_existing_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owned=root/'owned';hp=root/'hub.json';dp=root/'device.json'
            hub,device=receipts();hp.write_text(json.dumps(hub));dp.write_text(json.dumps(device))
            binding=dict(controller='controller',session_boot='session',source_boot='source')
            result=memory.prepare(owned,hp,dp,binding,require_live=True);store=result['store_id']
            with self.assertRaises(memory.MemoryConflict):memory.operate('confirm',owned,store,0)
            memory.operate('confirm',owned,store,0,True);memory.operate('correct',owned,store,1,True)
            meta=json.loads((owned/'binding.json').read_text())
            next_hub,next_device=receipts([memory.item(meta,2)],store_id=store,
                revision=memory.operate('readback',owned,store,2)['revision'])
            readback=dict(**memory.operate('readback',owned,store,2),action='readback',accepted=True,model_inference=False)
            next_hub['memory_context_binding']=chain.context_binding(readback);next_hub['memory_readback_sha256']='c'*64
            next_binding={**binding,'session_boot':'next-session'};next_hub['session_boot']='next-session'
            next_device['operator_after']['microphone_epoch']=4
            for turn in next_hub['turns']:
                turn['sequence']+=100;turn['lineage_id']='source:'+str(turn['sequence'])
                for authority in (turn['working_authority'],turn['main_final']['authority'],turn['reply_playback']['authority']):authority['microphone_epoch']=3
                turn['working_operator_binding'][1]=turn['reply_playback']['operator_binding'][1]=3
            hp.write_text(json.dumps(next_hub));dp.write_text(json.dumps(next_device))
            verified=memory.operate('verify-live-context',owned,store,2,live_receipts=(hp,dp,next_binding))
            self.assertTrue(verified['next_main_context_validated']);self.assertEqual(verified['versions'],[2])
            output=root/'verify.json'
            process=subprocess.run([sys.executable,str(ROOT/'deploy/autonomous/voice_memory_acceptance.py'),'verify-live-context',
                '--directory',str(owned),'--output',str(output),'--allow-disposable-voice-fixture','--expected-store-id',store,
                '--expected-version','2','--hub-receipt',str(hp),'--device-receipt',str(dp),'--controller','controller',
                '--session-boot','next-session','--source-boot','source'],cwd=ROOT,capture_output=True,text=True,timeout=5)
            self.assertEqual(process.returncode,0,process.stderr);report=json.loads(output.read_text())
            self.assertTrue(report['next_main_context_validated']);self.assertFalse(report['live_voice_verified'])
            for mode in ('old_hub','old_session','old_lineage','old_mic','context_off','foreign_store','old_revision'):
                bad=copy.deepcopy(next_hub);bad_device=copy.deepcopy(next_device);bad_binding=dict(next_binding)
                if mode=='old_hub':
                    bad['hub_boot_id']=hub['hub_boot_id'];bad['context_terminal_revoke']['output']['hub_boot_id']=bad['hub_boot_id']
                    for t in bad['turns']:
                        for authority in (t['working_authority'],t['main_final']['authority'],t['reply_playback']['authority']):authority['hub_boot_id']=bad['hub_boot_id']
                elif mode=='old_session':bad['session_boot']=bad_binding['session_boot']='session'
                elif mode=='old_lineage':bad['turns'][0].update(sequence=2,lineage_id='source:2')
                elif mode=='old_mic':
                    for t in bad['turns']:
                        for authority in (t['working_authority'],t['main_final']['authority'],t['reply_playback']['authority']):authority['microphone_epoch']=1
                        t['working_operator_binding'][1]=t['reply_playback']['operator_binding'][1]=1
                    bad_device['operator_after']['microphone_epoch']=2
                elif mode=='context_off':bad['context_enabled']=False
                elif mode=='foreign_store':bad['turns'][0]['main_final']['memory_store_id']='another-store'
                else:bad['turns'][0]['main_final']['memory_revision']-=1
                hp.write_text(json.dumps(bad));dp.write_text(json.dumps(bad_device))
                with self.subTest(mode=mode),self.assertRaises(ValueError):
                    memory.operate('verify-live-context',owned,store,2,live_receipts=(hp,dp,bad_binding))
            dp.write_text(json.dumps(next_device))
            next_hub['turns'][0]['main_final']['final']['memory_projection_sha256']=chain.digest([]);hp.write_text(json.dumps(next_hub))
            with self.assertRaises(ValueError):memory.operate('verify-live-context',owned,store,2,live_receipts=(hp,dp,next_binding))
            self.assertEqual(memory.operate('readback',owned,store,2)['versions'],[2])
            memory.operate('forget',owned,store,2)
            with self.assertRaises(memory.MemoryConflict):memory.operate('verify-live-context',owned,store,-1,live_receipts=(hp,dp,binding))
            memory.operate('cleanup',owned,store,-1,exclusive_filesystem_cleanup=True)
            self.assertFalse(owned.exists())

    def test_audit_retention_is_bounded_and_overflow_cannot_pass_strict_source(self):
        audit=[];overflow=False
        for index in range(1000):overflow=chain.retain_main_audit(audit,dict(task_id=str(index))) or overflow
        self.assertEqual(len(audit),8);self.assertEqual(audit[0]['task_id'],'992');self.assertTrue(overflow)
        hub,device=receipts();hub['receipt_overflow']['main']=True
        with self.assertRaises(ValueError):memory.voice_provenance(hub,device,
            dict(controller='controller',session_boot='session',source_boot='source'),require_live=True)

    def test_real_speech_adapter_preserves_task_chain_but_replay_cursor_is_not_live_evidence(self):
        state=State();state.speech_attached=True
        state.set_speech_operator(dict(binding=('agent',1,0),microphone_enabled=True,quiet=False,privacy_all=False))
        now=time.monotonic();state.ingest(dict(type='utterance',text='Neutral fixture input'),now)
        ref=next(iter(state.candidates));task=state.apply(dict(a='think',why='fixture',start=dict(type='main',input_ref=ref)),state.bind(now,5),now)
        output='Neutral fixture reply';proof=chain.model_final(task.prompt,output,'completion_http','fixture-model')
        state.complete(task.task_id,task.attempt_id,task.authority,output,now+.001,provenance=proof)
        state.apply(dict(a='converse',why='fixture',commit=task.task_id),state.bind(now+.002,5),now+.002)
        proposal=state.speech_proposals.pop()
        class PCM(ReplayPCM):
            def write(self,stream,pcm):
                frames=super().write(stream,pcm);self.advance(stream,frames);return frames
        class TTS:
            def stream(self,text,cancel):yield b'\0\0'*320
            def cancel(self):pass
        backend=PCM();playback=Playback(backend,allow_simulated=True)
        speech=SpeechAdapter(playback,TTS(),lambda:dict(agent_boot_id='agent',microphone_epoch=1,microphone_enabled=True,
            motion_policy=dict(epoch=0,quiet=False,privacy_all=False)))
        try:
            speech.advance(state.authority);end=time.monotonic()+1
            while not speech.operator_view() and time.monotonic()<end:time.sleep(.002)
            self.assertIsNotNone(speech.operator_view());speech.execute(proposal)
            while not speech.status()['receipts'] and time.monotonic()<end:time.sleep(.002)
            receipt=speech.status()['receipts'][0]
            self.assertEqual(receipt['main_receipt'],proposal['main_receipt']);self.assertEqual(receipt['authority'],state.authority.wire())
            self.assertEqual(receipt['output_sha256'],chain.digest(output));self.assertNotIn(output,json.dumps(receipt))
            progress=[event for event in speech.status()['timeline'] if event['kind']=='speech_progress']
            self.assertTrue(progress);self.assertTrue(all(event['provenance']=='simulated_consumed_pcm' for event in progress))
        finally:
            speech.close();speech.control.join(1)
            if speech.worker:speech.worker.join(1)

    def test_model_backend_only_marks_successful_final_and_binds_full_context(self):
        cfg=load(ROOT/'config.autonomous.example.json');cfg['models']['main'].update(completion_backend='llama_native',base_url='http://127.0.0.1:1',id='fixture-model')
        backend=ModelBackend(cfg);backend.count=lambda *args:1
        backend.post=lambda *args:dict(content='Neutral FINAL',stop_type='eos',tokens_predicted=2)
        data=dict(schema_version='context-1',utterance='Neutral query',memory=[],observations=[])
        result=backend.generate_loaded('main',json.dumps(data),context_input=True)
        self.assertEqual(result['completion_provenance'],chain.model_final(data,'Neutral FINAL','llama_native',cfg['models']['main']['id']))
        backend.post=lambda *args:dict(content='partial',stop_type='limit',tokens_predicted=2)
        with self.assertRaises(ValueError):backend.generate_loaded('main','Neutral query')

    def test_whitelist_binding_rejects_foreign_fast_and_main_context_before_transport(self):
        items=[dict(id='fixture-note',version=2,content='Neutral six')]
        descriptors=[dict(alias='fixture-note:2',type='fact',summary='Neutral six')]
        report=dict(action='readback',accepted=True,live_source_chain_validated=True,model_inference=False,
            state_projection_verified=True,content_whitelist_verified=True,versions=[2],store_id='store',revision=3,
            memory_projection_sha256=chain.digest(items),memory_descriptor_sha256=chain.digest(descriptors))
        binding=chain.context_binding(report);calls=[]
        task=SimpleNamespace(kind='main',memory_store_id='store',memory_revision=3,
            prompt=dict(schema_version='context-1',utterance='Neutral query',memory=items,observations=[]))
        chain.check_context_view(dict(memory=descriptors,sensors=[]),binding);chain.check_context_task(task,binding)
        for change in ({'memory_store_id':'foreign'},{'memory_revision':2},{'memory_revision':True},
                {'prompt':{**task.prompt,'memory':[dict(content='Unexpected fixture content')]}},
                {'prompt':{**task.prompt,'observations':[dict(summary='Unexpected observation')]}}):
            bad=copy.deepcopy(task)
            for key,value in change.items():setattr(bad,key,value)
            with self.assertRaises(ValueError):
                chain.check_context_task(bad,binding);calls.append('main transport')
        for memory_value in ([],[dict(summary='Unexpected fixture content')]):
            with self.assertRaises(ValueError):
                chain.check_context_view(dict(memory=memory_value,sensors=[]),binding);calls.append('fast transport')
        self.assertFalse(calls)
        report['live_source_chain_validated']=False
        with self.assertRaises(ValueError):chain.context_binding(report) # old neutral14 cannot bootstrap live gate

    def test_late_final_does_not_free_an_occupied_job_or_create_ready_speech(self):
        cfg=load(ROOT/'config.autonomous.example.json');cfg.update(period_s=.001,fast_deadline_s=.1,task_timeout_s=.02)
        entered=threading.Event();release=threading.Event()
        class Held(ReplayGateway):
            def main(self,task):
                entered.set();release.wait(2);output='Late neutral FINAL'
                return dict(output=output,compute_boot_id=task.authority.compute_boot_id,request_id=task.attempt_id,
                    completion_provenance=chain.model_final(task.prompt,output,'completion_http','fixture-model'))
        scheduler=Scheduler(cfg,Held());scheduler.ingest(dict(type='utterance',text='Neutral query'))
        end=time.monotonic()+1
        while not entered.is_set() and time.monotonic()<end:scheduler.advance();time.sleep(.002)
        self.assertTrue(entered.is_set());job=scheduler.main_job;time.sleep(.03);scheduler.advance()
        self.assertIs(scheduler.main_job,job);self.assertFalse(job.future.done())
        release.set();job.future.result(timeout=1);scheduler.advance()
        self.assertFalse(any(t.status=='ready' for t in scheduler.state.tasks.values()));self.assertFalse(scheduler.state.speech_proposals)
        scheduler.close()


if __name__=='__main__':unittest.main()
