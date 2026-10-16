"""Exact first-content opt-in and shared finite metadata consumer; no devices/models."""
import ast
import base64
import copy
import io
import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from reachy_companion import token_stream as stream
from test_token_stream import ROOT,overlay
import test_token_stream as legacy_tests
from test_stream_cleanup_overlay import load


def reader_fixture():
    r=stream.TimelyReader.__new__(stream.TimelyReader)
    r.__dict__.update(condition=threading.Lock(),attempt_id='0'*32,seconds=40,started=100.,started_unix=1792150000.,
        token_chunks=2,max_read_gap=.1,first_token=100.1,last_token=100.2,terminal_time=100.3,
        first_semantic=100.15,first_pcm=100.18,queue_peak=2,queue_bytes_peak=12,overflow=False,discarded=1,
        terminal=True,failed=False,post_attempted=True,fast_grace_exceeded=False,close_elapsed=.01,
        first_segment_chars=20,first_segment_boundary='period',
        first_audio_durations={key:None for key in stream.FIRST_AUDIO_DURATIONS},thread=SimpleNamespace(is_alive=lambda:False))
    return r


class FirstContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=subprocess.check_output(['git','show','2865db30e92fcb069c241c34bae4419ad65ed594:src/reachy_companion/voice.py'],cwd=ROOT).decode()
        cls.new=overlay(cls.old,ROOT/'deploy/patches/reachy-worker-92cf-content-stream.patch');cls.module=load(cls.new)

    def pipeline(self):
        p=self.module.Pipeline.__new__(self.module.Pipeline)
        p.config=json.loads((ROOT/'config.example.json').read_text())
        p.tts_settings=object()
        chunks=[SimpleNamespace(sample_channels=1,sample_rate=22050,audio_int16_bytes=b'original'),
                SimpleNamespace(sample_channels=1,sample_rate=22050,audio_int16_bytes=b'next')]
        p.tts=SimpleNamespace(synthesize=Mock(return_value=iter(chunks)))
        return p

    def test_exact_audio_bytes_cues_settings_and_commands_unchanged_with_observer(self):
        original=load(self.old);outputs=[];commands=[];observations=[]
        for module,observe in ((original,None),(self.module,None),(self.module,observations.append)):
            p=self.pipeline()
            def run(command,**kwargs):commands.append((command,kwargs));return SimpleNamespace(stdout=b'\0\0'*320)
            with patch.object(module.subprocess,'run',side_effect=run),patch('reachy_companion.speech_motion.cues',return_value=[dict(at=0)]):
                args={} if observe is None else dict(first_segment_observer=observe)
                outputs.append(list(module.Pipeline.audio_events(p,[dict(text='Короткий ответ.',emotion='neutral',gesture='auto')],speech_address_prefix='',**args)))
            p.tts.synthesize.assert_called_once()
        self.assertEqual(outputs[0],outputs[1]);self.assertEqual(outputs[1],outputs[2])
        self.assertEqual(commands[:2],commands[2:4]);self.assertEqual(commands[:2],commands[4:])
        self.assertEqual(len(observations),1);self.assertEqual(set(observations[0]),stream.FIRST_AUDIO_DURATIONS)
        self.assertTrue(all(v>=0 for v in observations[0].values()))

    def test_first_chunk_stage_durations_are_actual_disjoint_same_clock_measurements(self):
        p=self.pipeline();observed=[];clock=iter((100.,100.2,100.21,100.24,100.25,100.26,100.3))
        with patch.object(self.module.time,'monotonic',side_effect=lambda:next(clock)), \
                patch.object(self.module.subprocess,'run',return_value=SimpleNamespace(stdout=b'\0\0'*320)), \
                patch('reachy_companion.speech_motion.cues',return_value=[]):
            list(p.audio_events([dict(text='Содержательно.',emotion='neutral',gesture='auto')],first_segment_observer=observed.append))
        self.assertEqual(len(observed),1)
        for key,value in dict(first_piper_wait_seconds=.2,first_sox_seconds=.03,first_cues_seconds=.01,first_segment_prepare_seconds=.3).items():
            self.assertAlmostEqual(observed[0][key],value)

    def test_empty_first_pcm_does_not_relabel_later_chunk_as_first_piper_measurement(self):
        p=self.pipeline();observed=[];clock=iter((100.,100.2,100.21,100.24,100.25,100.26,100.5))
        with patch.object(self.module.time,'monotonic',side_effect=lambda:next(clock)), \
                patch.object(self.module.subprocess,'run',side_effect=[SimpleNamespace(stdout=b''),SimpleNamespace(stdout=b'\0\0')]), \
                patch('reachy_companion.speech_motion.cues',return_value=[]):
            list(p.audio_events([dict(text='Ответ.',emotion='neutral',gesture='auto')],first_segment_observer=observed.append))
        self.assertEqual(len(observed),1)
        self.assertAlmostEqual(observed[0]['first_piper_wait_seconds'],.2)
        self.assertAlmostEqual(observed[0]['first_segment_prepare_seconds'],.5)

    def test_only_first_segment_receives_observer_and_style_prefix_and_filters_survive(self):
        seen=[];observer=Mock()
        p=SimpleNamespace(config=dict(limits=dict(max_speech_chars=5000),conversation=dict(expressions=dict(speech_sync=dict(max_cues=2)))),
            address_speech=lambda text,prefix:prefix+text,speech_address_metadata=lambda *a:{})
        def audio(segments,total,**kwargs):
            seen.append(kwargs);yield dict(type='audio',pcm_base64='AAA=')
        p.audio_events=audio
        raw='<think>PRIVATE</think><emotion=curious>Первое. Второе.'
        list(stream.incremental_audio(p,stream.semantic_segments(iter(raw),5000),'Алиса, ',first_segment_observer=observer))
        self.assertIs(seen[0]['first_segment_observer'],observer);self.assertEqual(seen[0]['speech_address_prefix'],'Алиса, ')
        self.assertNotIn('first_segment_observer',seen[1]);self.assertEqual(seen[1]['speech_address_prefix'],'')

    def test_instruction_is_only_appended_to_stream_system_message_and_request_history_remain_intact(self):
        case=legacy_tests.ExactWorkerOverlayTests();case.module=self.module
        case.addCleanup=self.addCleanup
        p=case.pipeline()
        original=copy.deepcopy(p.config['llm']);captured=[]
        def tokens(config,messages,**kwargs):
            captured.extend(messages);kwargs['execution'].submitted();yield 'Ответ. ';kwargs['execution'].terminal()
        with patch.object(stream,'completion_tokens',side_effect=tokens):list(p.stream(dict(text='Объясни в восьми предложениях',session='existing'),'/text'))
        self.assertEqual(p.config['llm'],original)
        self.assertEqual(captured[0]['content'],original['system_prompt']+'\n'+stream.CONTENT_INSTRUCTION)
        self.assertEqual(captured[-1],dict(role='user',content='Объясни в восьми предложениях'))
        self.assertEqual(captured[1:3],[dict(role='user',content='Remember'),dict(role='assistant',content='Remembered')])
        self.assertNotIn('кружк',stream.CONTENT_INSTRUCTION)


class SharedMetadataContractTests(unittest.TestCase):
    def test_producer_record_and_exact_private_consumer_contract_have_same_31_fields(self):
        r=reader_fixture();r.observe_first_audio({key:.1 for key in stream.FIRST_AUDIO_DURATIONS})
        value=r.metadata();self.assertEqual(len(value),31);self.assertEqual(set(value),stream.METADATA_FIELDS)
        raw=b'unrelated log\ncontent_stream_metadata '+json.dumps(value).encode()+b'\n'
        self.assertEqual(stream.metadata_rows(raw),[value])
        self.assertNotIn('text',value);self.assertNotIn('model',value)
        r.observe_first_audio({key:8 for key in stream.FIRST_AUDIO_DURATIONS})
        self.assertEqual(r.metadata(),value)
        self.assertTrue(value['model_post_attempted'])

    def test_missing_unknown_and_strict_boolean_count_enum_numeric_types_reject(self):
        value=reader_fixture().metadata()
        bad=[dict(value,PRIVATE='do not expose'),{k:v for k,v in value.items() if k!='model_post_attempted'}]
        for key in stream.METADATA_BOOLEANS:
            for item in (0,1,None,'true'):bad.append(dict(value,**{key:item}))
        for key in stream.METADATA_COUNTS:
            for item in (True,-1,0.0):bad.append(dict(value,**{key:item}))
        for key in stream.METADATA_NUMBERS | stream.METADATA_OPTIONAL_NUMBERS:
            for item in (True,-1,float('nan'),float('inf'),'PRIVATE'):bad.append(dict(value,**{key:item}))
        for field,item in (('first_segment_chars',True),('first_segment_chars',601),('first_segment_chars',None),
                ('first_segment_boundary','PRIVATE'),('first_segment_boundary',None)):
            bad.append(dict(value,**{field:item}))
        for changed in bad:
            with self.assertRaises(ValueError) as caught:stream.validate_metadata(changed)
            self.assertNotIn('PRIVATE',str(caught.exception))

    def test_duplicate_nonfinite_and_unknown_metadata_logs_fail_in_shared_consumer(self):
        text=json.dumps(reader_fixture().metadata())
        for record in (text[:-1]+',"model_post_attempted":true}',text.replace('40','NaN',1),text[:-1]+',"PRIVATE":true}'):
            with self.assertRaises(ValueError):stream.metadata_rows(('content_stream_metadata '+record).encode())
        with self.assertRaises(ValueError):stream.metadata_rows(b'x'*1048577)
        empty=reader_fixture();empty.first_segment_chars=empty.first_segment_boundary=None
        self.assertEqual(stream.metadata_rows(b'content_stream_metadata '+json.dumps(empty.metadata()).encode()),[empty.metadata()])


if __name__=='__main__':unittest.main()
