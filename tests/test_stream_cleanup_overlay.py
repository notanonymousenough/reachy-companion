"""Frozen DONE-only legacy overlay: actual old Pipeline and exact parity."""
import ast
import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock,patch

import test_voice_stream_cleanup as cleanup

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_stream_cleanup',ROOT/'deploy/autonomous/prepare_stream_cleanup.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)


def load(source):
    piper=types.ModuleType('piper');piper.PiperVoice=piper.SynthesisConfig=object
    vosk=types.ModuleType('vosk');vosk.Model=vosk.KaldiRecognizer=vosk.SetLogLevel=object
    module=types.ModuleType('reachy_companion.legacy_stream_fixture')
    module.__package__='reachy_companion'
    with patch.dict(sys.modules,{'piper':piper,'vosk':vosk}):
        exec(compile(source,'legacy_voice.py','exec'),module.__dict__)
    return module


class GeneratedLegacyCleanupTests(cleanup.StreamCleanupTests):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.directory.cleanup)
        target=Path(cls.directory.name)/'candidate';prepare.build(target)
        cls.module=load((target/'voice.py').read_bytes())

    def pipeline_class(self):return self.module.Pipeline


class OverlayParityTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.target=Path(self.directory.name)/'candidate';self.manifest=prepare.build(self.target)
        self.old=prepare.git_file(prepare.BASE)
        self.new=(self.target/'voice.py').read_bytes()

    def test_frozen_manifest_exact_only_delta_and_existing_directory_preserved(self):
        self.assertEqual({p.name for p in self.target.iterdir()},{'voice.py','manifest.json'})
        self.assertEqual(self.manifest['preimages'],{'voice.py':prepare.PREIMAGE})
        self.assertEqual(self.manifest['outputs'],{'voice.py':prepare.sha(self.new)})
        self.assertEqual(self.manifest['cleanup_source_pin'],prepare.CLEANUP_SOURCE)
        self.assertFalse(self.manifest['dependencies_added']);self.assertFalse(self.manifest['default_config_changed'])
        self.assertFalse(self.manifest['actual_model_capability_verified']);self.assertFalse(self.manifest['hardware_acceptance'])
        self.assertEqual(self.new.decode().replace(prepare.AFTER,prepare.BEFORE,1).encode(),self.old)
        # Every node outside stream, including imports, request and handlers is unchanged.
        def outside(source):
            tree=ast.parse(source)
            pipeline=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Pipeline')
            pipeline.body=[n for n in pipeline.body if getattr(n,'name',None)!='stream']
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(outside(self.old),outside(self.new))
        for excluded in ('spoken_reply','reply_constraints','lmstudio','autonomous','transcribe_diagnostic'):
            self.assertNotIn(excluded,self.new.decode())
        marker=self.target/'foreign';marker.write_text('keep')
        with self.assertRaises(FileExistsError):prepare.build(self.target)
        self.assertEqual(marker.read_text(),'keep')

    def test_wrong_preimage_or_reviewed_source_never_creates_output(self):
        for name in ('BASE','CLEANUP_SOURCE'):
            target=Path(self.directory.name)/name
            with patch.object(prepare,'git_file',side_effect=lambda pin:b'foreign' if pin==getattr(prepare,name) else self.old):
                with self.assertRaises(ValueError):prepare.build(target)
            self.assertFalse(target.exists())

    def test_default_reply_audio_events_and_request_bytes_equal_exact_legacy(self):
        results=[]
        for source in (self.old,self.new):
            module=load(source);p=module.Pipeline.__new__(module.Pipeline)
            class Config(dict):token='fixture-token'
            p.config=Config(json.loads((ROOT/'config.example.json').read_text()))
            p.config['conversation']['interaction']['acknowledgements']['enabled']=False
            p.config['tts']['pitch_cents']=0
            p.config['tts']['playback_eq']={'enabled':False}
            p.config['logging']['log_transcripts']=False
            p.config['streaming']['pcm_chunk_bytes']=4
            p.lock=threading.Lock();p.phase='idle';p.sessions={};p.agent_sessions={};p.last_turn=None
            p.check_robot=lambda:None
            p.classify=lambda text:dict(action='answer',intent='other',emotion='neutral')
            p.transcribe=lambda pcm:'fixture input'
            answer_calls=[]
            def answer(text,session,interrupted=False):
                answer_calls.append((text,session,interrupted))
                return 'fixture reply',dict(used=0,messages=[dict(role='assistant',content='fixture reply')])
            p.answer=answer;p.tts_settings=object();synthesis=[];commands=[]
            pcm=b'\1\0\2\0\3\0'
            def synthesize(text,**kwargs):
                synthesis.append((text,kwargs['include_alignments']))
                yield types.SimpleNamespace(sample_channels=1,sample_rate=16000,audio_int16_bytes=pcm)
            p.tts=types.SimpleNamespace(synthesize=synthesize)
            def run(command,**kwargs):
                commands.append((command,kwargs));return types.SimpleNamespace(stdout=kwargs['input'])
            events=[]
            with patch.object(module.time,'monotonic',return_value=10),patch.object(module.subprocess,'run',side_effect=run),\
                    patch('reachy_companion.speech_motion.cues',return_value=[]):
                for path,payload in (('/say',dict(text=' fixture say ',session='say')),
                        ('/text',dict(text=' fixture input ',session='text',previous_reply_interrupted=True)),
                        ('/turn',dict(pcm_base64=base64.b64encode(b'\0\0').decode(),session='turn'))):
                    events.append(list(p.stream(payload,path)))
            self.assertTrue(all(e[-1]['type']=='done' and e[-1]['ok'] for e in events))
            self.assertTrue(all(any(item['type']=='audio' for item in e) for e in events))
            p.http=Mock();requests=[]
            for payload,authenticated in ((None,False),({'text':'fixture'},True)):
                p.http.open.return_value=io.BytesIO(b'{"ok":true}')
                self.assertEqual(p.request('http://127.0.0.1:1/fixture',payload,authenticated,timeout=2),{'ok':True})
                request=p.http.open.call_args.args[0]
                requests.append((request.full_url,request.data,request.headers,p.http.open.call_args.kwargs))
            results.append((events,answer_calls,synthesis,commands,p.sessions,p.last_turn,requests))
        self.assertEqual(results[0],results[1])


if __name__=='__main__':unittest.main()
