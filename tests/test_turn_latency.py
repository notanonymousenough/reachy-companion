"""Bounded optional latency records; synthetic stages, no model/device requests."""
import base64
import copy
import json
import sys
import threading
import types
import unittest
from unittest.mock import Mock, patch

from reachy_companion.logging_utils import TurnLatency, checked_latency, measured_chunks
import test_alice_speech_address as alice_fixture

ID = 'a'*32


class Clock:
    def __init__(self):self.now=1000.0
    def __call__(self):return self.now
    def advance(self, seconds):self.now+=seconds


class LatencyRecordTests(unittest.TestCase):
    def test_generator_active_time_excludes_consumer_backpressure_and_close_does_not_advance(self):
        clock=Clock();closed=[]
        def chunks():
            try:
                clock.advance(2);yield object()
                clock.advance(3);yield object()
            finally:closed.append(True)
        with patch('reachy_companion.logging_utils.time.monotonic',clock):
            trace=TurnLatency(ID,'worker');iterator=measured_chunks(trace,chunks())
            next(iterator);clock.advance(10);next(iterator);list(iterator)
            report=trace.report('complete')
            self.assertEqual(report['elapsed_seconds'],15)
            self.assertEqual(report['stages']['tts']['active_seconds'],5)
            self.assertEqual(report['stages']['tts']['end_seconds'],15)
            self.assertIsNone(report['marks']['first_raw_pcm'])
            second=TurnLatency(ID,'worker');iterator=measured_chunks(second,chunks())
            next(iterator);clock.advance(20);iterator.close()
            self.assertEqual(second.report('cancelled')['stages']['tts']['active_seconds'],2)
        self.assertEqual(closed,[True,True])

    def test_fixed_schema_counts_and_validation_reject_content_mismatch_nonfinite_and_wrong_types(self):
        trace=TurnLatency(ID,'worker');trace.pcm(320);value=trace.report('complete')
        self.assertEqual(value['pcm_seconds'],.01)
        self.assertEqual(checked_latency(value,ID),value)
        self.assertIsNone(checked_latency(value,'b'*32))
        for path,bad in ((('elapsed_seconds',),True),(('elapsed_seconds',),float('nan')),
                         (('elapsed_seconds',),10**1000),(('pcm_frames',),False),
                         (('stages','tts','calls'),1.0),(('marks','first_raw_pcm'),'private text'),
                         (('main_first_token_seconds',),.1)):
            changed=copy.deepcopy(value);target=changed
            for key in path[:-1]:target=target[key]
            target[path[-1]]=bad
            self.assertIsNone(checked_latency(changed,ID))
        changed=dict(value,raw_transcript='private');self.assertIsNone(checked_latency(changed,ID))
        owned=checked_latency(value,ID);owned['stages']['tts']['calls']=22
        self.assertEqual(value['stages']['tts']['calls'],0)
        for _ in range(100):trace.mark('first_raw_pcm');trace.pcm(4)
        self.assertEqual(set(trace.report('complete')),set(value))
        self.assertLess(len(json.dumps(trace.report('complete'))),2000)


class WorkerLatencyTests(unittest.TestCase):
    setUp=alice_fixture.AliceSpeechAddressTests.setUp

    def request(self):return dict(pcm_base64=base64.b64encode(b'\0\0').decode(),latency_diagnostics=True,latency_request_id=ID)

    def test_worker_stage_accounting_no_content_and_no_last_turn_retention(self):
        clock=Clock()
        def transcribe(pcm):clock.advance(2);return 'PRIVATE INPUT'
        def answer(*args):clock.advance(3);return 'PRIVATE REPLY',dict(used=0,messages=[dict(role='assistant',content='PRIVATE REPLY')])
        def tts(*args,**kwargs):
            for duration in (.5,.25):
                clock.advance(duration)
                yield types.SimpleNamespace(sample_channels=1,sample_rate=16000,audio_int16_bytes=b'\0\0'*16)
        def convert(*args,**kwargs):clock.advance(.1);return types.SimpleNamespace(stdout=kwargs['input'])
        payload=self.request();before=copy.deepcopy(payload)
        with patch('reachy_companion.logging_utils.time.monotonic',clock),patch.object(self.pipeline,'transcribe',side_effect=transcribe), \
                patch.object(self.pipeline,'answer',side_effect=answer) as backend,patch.object(self.pipeline.tts,'synthesize',side_effect=tts), \
                patch('reachy_companion.voice.subprocess.run',side_effect=convert):
            iterator=self.pipeline.stream(payload,'/turn');events=[next(iterator),next(iterator)]
            clock.advance(10);events+=list(iterator)
        value=events[-1]['latency'];self.assertEqual(events[-1]['type'],'done')
        self.assertEqual(value['request_id'],ID);self.assertEqual(value['elapsed_seconds'],15.95)
        self.assertEqual(value['stages']['stt']['active_seconds'],2)
        self.assertEqual(value['stages']['answer_call']['active_seconds'],3)
        self.assertEqual(value['stages']['tts']['active_seconds'],.75)
        self.assertEqual(value['stages']['audio_convert']['active_seconds'],.2)
        self.assertEqual(value['marks']['first_raw_pcm'],5.5)
        self.assertEqual(value['marks']['first_output_pcm'],5.6)
        self.assertEqual(value['pcm_frames'],32);self.assertIsNone(value['main_first_token_seconds'])
        self.assertNotIn('PRIVATE',json.dumps(value));self.assertNotIn('latency',self.pipeline.last_turn)
        self.assertEqual(payload,before);backend.assert_called_once()

    def test_disabled_and_unary_unavailable_first_pcm_markers(self):
        plain=self.pipeline.turn(dict(text='Reply'),'/say')
        self.assertNotIn('latency',plain)
        value=self.pipeline.turn(dict(text='Reply',latency_diagnostics=True,latency_request_id=ID),'/say')['latency']
        self.assertEqual(value['stages']['tts']['calls'],1)
        self.assertIsNone(value['marks']['first_raw_pcm']);self.assertIsNone(value['marks']['first_output_pcm'])
        self.assertIsNotNone(value['marks']['wav_ready']);self.assertIsNone(value['pcm_frames'])

    def test_invalid_request_metadata_denies_before_robot_stt_model_tts(self):
        cases=[dict(latency_diagnostics=value) for value in (None,1,'yes',[],{})]
        cases += [dict(latency_diagnostics=True,latency_request_id=value) for value in (None,False,'b'*31,'A'*32,{},[])]
        cases += [dict(latency_diagnostics=False,latency_request_id=ID)]
        with patch.object(self.pipeline,'answer') as answer:
            for case in cases:
                payload=dict(text='PRIVATE',pcm_base64='AAA=',**case);before=copy.deepcopy(payload)
                with self.assertRaises(ValueError):self.pipeline.turn(payload,'/turn')
                with self.assertRaises(ValueError):list(self.pipeline.stream(payload,'/turn'))
                self.assertEqual(payload,before)
            answer.assert_not_called()
        self.pipeline.check_robot.assert_not_called();self.pipeline.transcribe.assert_not_called()
        self.assertEqual(self.spoken,[]);self.assertFalse(self.pipeline.lock.locked())

    def test_close_before_tts_has_no_fabricated_pcm_or_tts_calls_and_releases_lock(self):
        trace=TurnLatency(ID,'worker')
        with patch('reachy_companion.voice.worker_latency',return_value=trace):
            iterator=self.pipeline.stream(dict(text='Reply'),'/say');next(iterator);iterator.close()
        report=trace.report('cancelled')
        self.assertEqual(report['stages']['tts']['calls'],0)
        self.assertIsNone(report['marks']['first_raw_pcm']);self.assertEqual(self.spoken,[])
        self.assertFalse(self.pipeline.lock.locked());self.assertEqual(self.pipeline.phase,'idle')

    def test_ack_and_final_share_one_identity_and_do_not_repeat_model_call(self):
        self.config.data['conversation']['interaction']['acknowledgements']=dict(
            enabled=True,delay_seconds=0,phrases=dict(other='Acknowledgement.'))
        released=threading.Event()
        def answer(*args):
            released.wait(2)
            return 'Answer.',dict(used=0,messages=[dict(role='assistant',content='Answer.')])
        with patch.object(self.pipeline,'answer',side_effect=answer) as backend:
            iterator=self.pipeline.stream(dict(text='Question',latency_diagnostics=True,latency_request_id=ID),'/text')
            try:first=next(iterator);self.assertTrue(first['acknowledgement'])
            finally:released.set()
            events=list(iterator)
        value=events[-1]['latency'];self.assertEqual(value['request_id'],ID)
        self.assertEqual(value['stages']['answer_call']['calls'],1)
        self.assertEqual(value['stages']['tts']['calls'],6)
        self.assertEqual(value['pcm_frames'],64);backend.assert_called_once()


class AgentLatencyTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(sys.modules,{'webrtcvad':types.SimpleNamespace(Vad=Mock())}):
            from reachy_companion.agent import Agent
        self.agent=Agent.__new__(Agent);self.agent.config={'logging':dict(latency_diagnostics=True)}

    def test_join_only_same_uuid_no_cross_host_subtraction_owned_copy_and_real_ttl(self):
        clock=Clock();payload=dict(text='PRIVATE')
        def voice(path,request,*args,latency=None):
            worker=TurnLatency(request['latency_request_id'],'worker').report('complete')
            worker['elapsed_seconds']=123
            clock.advance(3)
            return dict(ok=True,latency=worker)
        with patch('reachy_companion.logging_utils.time.monotonic',clock),patch.object(self.agent,'_voice',side_effect=voice):
            result=self.agent.voice('/turn',payload);report=result['latency']
            self.assertEqual(report['agent']['elapsed_seconds'],3)
            self.assertEqual(report['worker']['elapsed_seconds'],123)
            self.assertEqual(report['worker']['request_id'],report['agent']['request_id'])
            self.assertEqual(payload,dict(text='PRIVATE'))
            result['latency']['worker']['elapsed_seconds']=99
            self.assertEqual(self.agent.latency_status()['worker']['elapsed_seconds'],123)
            clock.advance(299.9);self.assertIsNotNone(self.agent.latency_status())
            clock.advance(.1);self.assertIsNone(self.agent.latency_status())
            self.assertIsNone(self.agent.last_voice_latency)

    def test_malformed_mismatched_and_replay_worker_reports_are_never_fresh_inference(self):
        for upstream in ({'raw':'PRIVATE'},TurnLatency('b'*32,'worker').report('complete')):
            with patch.object(self.agent,'_voice',return_value=dict(ok=True,latency=upstream)):
                result=self.agent.voice('/turn',{})
            self.assertIsNone(result['latency']['worker']);self.assertNotIn('PRIVATE',json.dumps(self.agent.latency_status()))
        def voice(path,payload,*args,latency=None):
            return dict(ok=True,latency=TurnLatency(payload['latency_request_id'],'worker').report('complete'))
        with patch.object(self.agent,'_voice',side_effect=voice):
            first=self.agent.voice('/turn',{},replay={})['latency']
            second=self.agent.voice('/turn',{},replay={})['latency']
        self.assertIsNone(first['worker']);self.assertEqual(first['agent']['source'],'replay')
        self.assertNotEqual(first['request_id'],second['request_id'])

    def test_disabled_no_new_identity_payload_metadata_or_probe_and_error_record_has_no_exception_text(self):
        self.agent.config['logging']['latency_diagnostics']=False
        payload=dict(text='PRIVATE');expected=dict(ok=True)
        with patch.object(self.agent,'_voice',return_value=expected) as voice,patch('reachy_companion.agent.uuid4') as uuid:
            self.assertIs(self.agent.voice('/turn',payload),expected)
            self.assertIs(voice.call_args.args[1],payload);uuid.assert_not_called()
        self.assertIsNone(self.agent.latency_status())
        self.agent.config['logging']['latency_diagnostics']=True
        with patch.object(self.agent,'_voice',side_effect=RuntimeError('PRIVATE ERROR')):
            with self.assertRaises(RuntimeError):self.agent.voice('/turn',{})
        report=self.agent.latency_status();self.assertEqual(report['agent']['outcome'],'error')
        self.assertNotIn('PRIVATE',json.dumps(report))


if __name__=='__main__':unittest.main()
