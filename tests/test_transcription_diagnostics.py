"""Request-local STT stage instrumentation; synthetic RAM PCM/fake models only."""
import base64
import importlib
import json
import sys
import threading
import types
import unittest
from unittest.mock import patch
from reachy_companion.recognition import Recognizer

class Segment:
    def __init__(self,text,logprob=-.5,no_speech=.1):self.text=text;self.avg_logprob=logprob;self.no_speech_prob=no_speech
class Whisper:
    def __init__(self,segments):self.segments=segments;self.calls=[];self.iterations=0
    def transcribe(self,samples,**kwargs):
        self.calls.append((samples.copy(),kwargs.copy()))
        def stream():
            for item in self.segments:self.iterations+=1;yield item
        return stream(),None
class Sounds:
    def __init__(self,kind):self.kind=kind;self.calls=[]
    def classify(self,pcm):
        self.calls.append(pcm)
        return dict(kind=self.kind,speech=.12,music=.73,raw_audio='must-not-copy',steps=[dict(text='must-not-copy')])

class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        try:import numpy
        except ImportError:
            # Dependency-free runs test stage control/counting with a frame-count
            # stand-in; the worker/target NumPy conversion is checked separately.
            class Frames:
                def __init__(self,pcm):self.size=len(pcm)//2
                def astype(self,*args):return self
                def __truediv__(self,*args):return self
                def copy(self):return self
            substitute=types.SimpleNamespace(float32=object(),frombuffer=lambda pcm,**kw:Frames(pcm))
            change=patch.dict(sys.modules,numpy=substitute);change.start();self.addCleanup(change.stop)
    @classmethod
    def setUpClass(cls):
        piper=types.ModuleType('piper');piper.PiperVoice=piper.SynthesisConfig=object
        vosk=types.ModuleType('vosk');vosk.Model=vosk.KaldiRecognizer=vosk.SetLogLevel=object
        with patch.dict(sys.modules,piper=piper,vosk=vosk):cls.voice=importlib.import_module('reachy_companion.voice')
    def pipeline(self,kind='speech',segments=(),enabled=True):
        config={'audio':dict(max_input_seconds=8,sample_rate=16000),'conversation':dict(
            recognition={'diagnostics_enabled':enabled},sound_reactions={'window_seconds':3})}
        stt=Recognizer.__new__(Recognizer);stt.config=config;stt.lock=threading.Lock()
        stt.settings=dict(backend='faster_whisper',language='ru',beam_size=3,initial_prompt='fixture',vad_filter=True,
            no_speech_threshold=.6,log_prob_threshold=-.9)
        stt.model=Whisper(segments)
        pipeline=self.voice.Pipeline.__new__(self.voice.Pipeline);pipeline.config=config;pipeline.stt=stt;pipeline.sounds=Sounds(kind)
        pipeline.last_turn={'existing':'unchanged'};pipeline.phase='idle';pipeline.sessions={}
        pipeline.classify=lambda text:dict(action='answer' if text else 'empty')
        return pipeline
    def payload(self,diagnostics=True):
        # Four seconds synthetic mono PCM; prefilter must see only the last 3s.
        return dict(pcm_base64=base64.b64encode(b'\x01\x00'*64000).decode(),diagnostics=diagnostics)
    def test_music_skip_and_whisper_empty_are_distinct_on_same_admitted_pcm(self):
        payload=self.payload();music=self.pipeline(kind='music');empty=self.pipeline()
        skip=music.transcribe_response(payload);result=empty.transcribe_response(payload)
        self.assertEqual(skip['transcript'],result['transcript']);self.assertEqual(skip['decision'],result['decision'])
        self.assertEqual(skip['diagnostics']['outcome'],'music_prefilter_skipped_whisper')
        self.assertTrue(skip['diagnostics']['prefilter_skip']);self.assertFalse(skip['diagnostics']['whisper_invoked'])
        self.assertEqual(music.stt.model.calls,[]);self.assertEqual(len(music.sounds.calls),1)
        self.assertEqual(result['diagnostics']['outcome'],'whisper_empty');self.assertTrue(result['diagnostics']['whisper_invoked'])
        self.assertEqual(len(empty.stt.model.calls),1);self.assertEqual(len(empty.sounds.calls),1)
        self.assertEqual(music.sounds.calls,empty.sounds.calls);self.assertEqual(len(empty.sounds.calls[0]),96000)
        self.assertEqual(empty.stt.model.calls[0][0].size,64000)
    def test_filter_edge_counts_single_consumption_and_default_text_equivalence(self):
        segments=[Segment(' kept ',logprob=-.9),Segment('discard',logprob=-.9001),
            Segment('discard',no_speech=.6),Segment('discard',logprob=-1,no_speech=.9),Segment('   ')]
        normal=self.pipeline(segments=segments);diagnostic=self.pipeline(segments=segments)
        before=normal.transcribe_response(self.payload(False));after=diagnostic.transcribe_response(self.payload())
        self.assertEqual(before,{k:v for k,v in after.items() if k!='diagnostics'});self.assertEqual(after['transcript'],'kept')
        counts=after['diagnostics'];self.assertEqual([counts[k] for k in ('segments_seen','segments_accepted','segments_rejected','rejected_logprob','rejected_no_speech','accepted_empty_text')],[5,2,3,2,2,1])
        self.assertEqual(diagnostic.stt.model.iterations,5);self.assertEqual(len(diagnostic.stt.model.calls),1)
        self.assertEqual(normal.stt.model.calls[0][1],diagnostic.stt.model.calls[0][1])
        self.assertEqual(normal.sounds.calls,diagnostic.sounds.calls)
    def test_double_gate_and_default_response_are_unchanged_without_diagnostic_request(self):
        pipeline=self.pipeline(enabled=False)
        with self.assertRaises(ValueError):pipeline.transcribe_response(self.payload())
        self.assertFalse(pipeline.stt.model.calls);self.assertFalse(pipeline.sounds.calls)
        result=pipeline.transcribe_response(self.payload(False));self.assertEqual(set(result),{'ok','transcript','decision'})
        for bad in (1,'true',None):
            body=self.payload();body['diagnostics']=bad
            with self.assertRaises(ValueError):pipeline.transcribe_response(body)
        body=self.payload(False);del body['diagnostics']
        self.assertEqual(set(pipeline.transcribe_response(body)),{'ok','transcript','decision'})
        with self.assertRaises(ValueError):pipeline.transcribe_response([])
    def test_only_selected_numeric_categories_and_counts_leave_request_scope(self):
        pipeline=self.pipeline(segments=[Segment('fixture-private-text')]);result=pipeline.transcribe_response(self.payload())
        diag=result['diagnostics'];self.assertNotIn('fixture-private-text',json.dumps(diag));self.assertNotIn('must-not-copy',json.dumps(diag))
        self.assertNotIn('pcm_base64',diag);self.assertNotIn('steps',diag)
        self.assertEqual(pipeline.last_turn,{'existing':'unchanged'});self.assertEqual(pipeline.phase,'idle');self.assertEqual(pipeline.sessions,{})
        self.assertFalse(hasattr(pipeline,'last_diagnostics'))
    def test_nonfinite_or_extra_sound_values_are_not_reflected(self):
        pipeline=self.pipeline(kind='music')
        pipeline.sounds.classify=lambda pcm:dict(kind='music',speech=float('nan'),music=float('inf'),secret='fixture')
        result=pipeline.transcribe_response(self.payload())
        self.assertEqual(result['diagnostics']['scores'],{});json.dumps(result,allow_nan=False)
    def test_default_rejection_retains_original_short_circuit(self):
        class Rejected:
            avg_logprob=-1
            @property
            def no_speech_prob(self):raise AssertionError('default rejected segment must short circuit')
            @property
            def text(self):raise AssertionError('rejected text must not be accessed')
        pipeline=self.pipeline(segments=[Rejected()])
        self.assertEqual(pipeline.transcribe_response(self.payload(False))['transcript'],'')

if __name__=='__main__':unittest.main()
