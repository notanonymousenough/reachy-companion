"""Explicit Alice TTS formatting; model content stays unchanged, synthetic audio."""
import base64
import json
import shutil
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from reachy_companion.config import Config,initialize


class AliceSpeechAddressTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);source=Path(__file__).resolve().parents[1]
        shutil.copy(source/'config.example.json',root);shutil.copytree(source/'profiles',root/'profiles')
        initialize(root);self.config=Config(root/'config.local.json')
        self.config.data['conversation']['speech_address_prefix']='Алиса, '
        self.config.data['conversation']['interaction']['acknowledgements']['enabled']=False
        self.config.data['conversation']['expressions']['enabled']=False
        self.config.data['tts'].update(pitch_cents=0,playback_eq=dict(enabled=False))
        self.config.data['streaming']['pcm_chunk_bytes']=4
        piper=types.ModuleType('piper');piper.PiperVoice=piper.SynthesisConfig=object
        vosk=types.ModuleType('vosk');vosk.Model=vosk.KaldiRecognizer=vosk.SetLogLevel=object
        with patch.dict(sys.modules,{'piper':piper,'vosk':vosk}):
            from reachy_companion.voice import Pipeline
        p=self.pipeline=Pipeline.__new__(Pipeline)
        p.config=self.config;p.lock=threading.Lock();p.sessions={};p.agent_sessions={};p.last_turn=None
        p.phase='idle';p.check_robot=Mock();p.tts_settings=object();self.spoken=[]
        p.classify=lambda text:dict(action='answer',intent='other',emotion='neutral')
        p.transcribe=Mock(return_value='Actual captured question')
        def synthesize(text,**kwargs):
            self.spoken.append(text)
            for _ in range(2):yield types.SimpleNamespace(sample_channels=1,sample_rate=16000,audio_int16_bytes=b'\0\0'*16)
        def synthesize_wav(text,wav,**kwargs):
            self.spoken.append(text);wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*16)
        p.tts=types.SimpleNamespace(synthesize=synthesize,synthesize_wav=synthesize_wav)
        run=patch('reachy_companion.voice.subprocess.run',side_effect=lambda *args,**kw:types.SimpleNamespace(stdout=kw['input']))
        run.start();self.addCleanup(run.stop)

    def test_typed_default_and_profile_scope(self):
        data=json.loads(self.config.filename.read_text());data['conversation'].pop('speech_address_prefix',None)
        self.config.filename.write_text(json.dumps(data))
        self.assertEqual(Config(self.config.filename)['conversation']['speech_address_prefix'],'')
        for value in (None,False,1,[],{},'Алиса','alice, ','Алиса, extra'):
            data['conversation']['speech_address_prefix']=value
            self.config.filename.write_text(json.dumps(data))
            with self.assertRaises(ValueError):Config(self.config.filename)
        data['conversation']['speech_address_prefix']=''
        (self.config.root/'alice-profile.json').write_text(json.dumps(dict(conversation=dict(speech_address_prefix='Алиса, '))))
        data['runtime']['profile']='alice-profile.json';self.config.filename.write_text(json.dumps(data))
        self.assertEqual(Config(self.config.filename)['conversation']['speech_address_prefix'],'Алиса, ')

    def test_address_detection_case_unicode_boundary_and_body_preservation(self):
        for text in ('Алиса, да','АЛИСА, Да','аЛиСа\u00a0да','\u2003Алиса! Да','Алиса','Алиса… да'):
            self.assertEqual(self.pipeline.address_speech(text),text)
        for text in ('Да.','Алисам это не нужно.','Alice says hello'):
            self.assertEqual(self.pipeline.address_speech(text),'Алиса, '+text)
        self.assertEqual(self.pipeline.address_speech(''),'')
        self.config.data['conversation']['speech_address_prefix']=''
        self.assertEqual(self.pipeline.address_speech('Да.'),'Да.')
        self.assertEqual(self.pipeline.speech_address_metadata('Да.'),{})

    def test_nonstream_real_answer_content_history_and_tts_prefix_only(self):
        with patch('reachy_companion.brains.answer',return_value='Да, подходит.') as backend:
            result=self.pipeline.turn(dict(text='Вопрос',session='s'),'/text')
        backend.assert_called_once()
        self.assertEqual(self.spoken,['Алиса, Да, подходит.'])
        self.assertEqual(result['reply'],'Да, подходит.')
        self.assertEqual(result['spoken_text'],'Алиса, Да, подходит.')
        self.assertEqual(result['speech_address_scope'],'tts_utterance')
        self.assertEqual(self.pipeline.sessions['s']['messages'][-1]['content'],'Да, подходит.')
        self.assertNotIn('Алиса',backend.call_args.args[1][-1]['content'])

    def test_stream_prefix_once_across_segments_piper_and_pcm_chunks(self):
        with patch('reachy_companion.brains.answer',return_value='<emotion=neutral>Да. <emotion=joy>Это подходит.') as backend:
            events=list(self.pipeline.stream(dict(pcm_base64=base64.b64encode(b'pcm').decode(),session='s'),'/turn'))
        self.pipeline.transcribe.assert_called_once_with(b'pcm');backend.assert_called_once()
        self.assertEqual(self.spoken,['Алиса, Да.','Это подходит.'])
        self.assertGreater(len([event for event in events if event['type']=='audio']),2)
        reply=next(event for event in events if event['type']=='reply')
        self.assertEqual(reply['reply'],'Да. Это подходит.')
        self.assertEqual(reply['spoken_text'],'Алиса, Да. Это подходит.')
        self.assertEqual(self.pipeline.sessions['s']['messages'][-1]['content'],'Да. Это подходит.')

    def test_existing_alice_no_duplicate_and_default_human_voice_unchanged(self):
        list(self.pipeline.stream(dict(text='Алиса, что ты думаешь?'),'/say'))
        self.assertEqual(self.spoken,['Алиса, что ты думаешь?'])
        self.spoken.clear();self.config.data['conversation']['speech_address_prefix']=''
        events=list(self.pipeline.stream(dict(text='Привет.'),'/say'))
        self.assertEqual(self.spoken,['Привет.'])
        self.assertFalse(any('spoken_text' in event for event in events))

    def test_empty_stopped_cancelled_streams_never_synthesize_prefix(self):
        self.pipeline.classify=lambda text:dict(action='stop')
        events=list(self.pipeline.stream(dict(text='Стоп'),'/text'))
        self.assertFalse(any(event['type']=='audio' for event in events));self.assertEqual(self.spoken,[])
        self.pipeline.classify=lambda text:dict(action='answer',intent='other',emotion='neutral')
        self.pipeline.transcribe.return_value=''
        list(self.pipeline.stream(dict(pcm_base64=''),'/turn'))
        self.assertEqual(self.spoken,[])
        iterator=self.pipeline.stream(dict(text='Да.'),'/say')
        self.assertEqual(next(iterator)['type'],'reply');iterator.close()
        self.assertEqual(self.spoken,[]);self.assertFalse(self.pipeline.lock.locked())

    def test_prefix_counts_in_character_and_pcm_duration_limits(self):
        self.config.data['limits']['max_speech_chars']=3
        with self.assertRaises(ValueError):self.pipeline.synthesize('Да')
        with self.assertRaises(ValueError):list(self.pipeline.audio_events([dict(text='Да',emotion='neutral',gesture='auto')]))
        self.assertEqual(self.spoken,[])
        self.config.data['limits']['max_speech_chars']=100
        self.config.data['streaming']['max_output_seconds']=.00001
        with self.assertRaises(RuntimeError):list(self.pipeline.audio_events([dict(text='Да',emotion='neutral',gesture='auto')]))

    def test_stream_acknowledgement_and_final_are_separate_addressed_utterances(self):
        self.config.data['conversation']['interaction']['acknowledgements']=dict(
            enabled=True,delay_seconds=0,phrases=dict(other='Сейчас отвечу.'))
        released=threading.Event()
        def answer(*args):released.wait(2);return 'Да.',dict(messages=[dict(role='assistant',content='Да.')])
        with patch.object(self.pipeline,'answer',side_effect=answer):
            iterator=self.pipeline.stream(dict(text='Вопрос',session='s'),'/text')
            first=next(iterator);self.assertTrue(first['acknowledgement'])
            self.assertEqual(first['spoken_text'],'Алиса, Сейчас отвечу.')
            released.set();list(iterator)
        self.assertEqual(self.spoken,['Алиса, Сейчас отвечу.','Алиса, Да.'])


if __name__=='__main__':unittest.main()
