"""Synthetic local files and stub acquisition only; no downloads/models/devices."""
import builtins
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

from reachy_companion.config import Config
from reachy_companion import recognition

ROOT=Path(__file__).resolve().parents[1]
WEIGHTS=b'synthetic reviewed weights'
METADATA=('config.json','tokenizer.json','vocabulary.json')


class WhisperCacheIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.config=Config.__new__(Config);self.config.root=self.root
        self.config.data=json.loads((ROOT/'config.example.json').read_text())
        self.settings=self.config['conversation']['recognition']
        self.settings.update(path='models/whisper',repository='fixture/reviewed',revision='a'*40,
                             sha256=hashlib.sha256(WEIGHTS).hexdigest())
        self.target=self.config.path(self.settings['path'])
        self.download=Mock()
        change=patch.dict(sys.modules,{'huggingface_hub':types.SimpleNamespace(snapshot_download=self.download)})
        change.start();self.addCleanup(change.stop)

    def cache(self,weights=WEIGHTS,missing=()):
        self.target.mkdir(parents=True,exist_ok=True)
        for name in METADATA:
            if name not in missing:(self.target/name).write_bytes(b'{}')
        if 'model.bin' not in missing:(self.target/'model.bin').write_bytes(weights)

    def no_model_imports(self):
        original=builtins.__import__
        def guarded(name,*args,**kwargs):
            if name in ('faster_whisper','numpy'):raise AssertionError('Model import before cache verification')
            return original(name,*args,**kwargs)
        return patch('builtins.__import__',side_effect=guarded)

    def test_valid_reuse_hashes_without_hf_import_download_or_file_mutation(self):
        self.cache();before={path.name:path.read_bytes() for path in self.target.iterdir()}
        original=builtins.__import__
        def guarded(name,*args,**kwargs):
            if name=='huggingface_hub':raise AssertionError('Valid cache must not acquire')
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=guarded):recognition.prepare(self.config)
        self.download.assert_not_called()
        self.assertEqual({path.name:path.read_bytes() for path in self.target.iterdir()},before)

    def test_exactly_one_acquisition_then_configured_hash_check_for_missing_and_bad_existing_cache(self):
        for existing in (False,True):
            if existing:self.cache(weights=b'bad previous cache')
            self.download.reset_mock()
            self.download.side_effect=lambda **kwargs:self.cache()
            recognition.prepare(self.config)
            self.download.assert_called_once_with(repo_id=self.settings['repository'],revision=self.settings['revision'],
                local_dir=str(self.target),allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.*','preprocessor_config.json'])
            self.assertEqual((self.target/'model.bin').read_bytes(),WEIGHTS)

    def test_wrong_download_hash_denies_prepare_and_startup_without_retry_or_cleanup(self):
        self.download.side_effect=lambda **kwargs:self.cache(weights=b'bad downloaded weights')
        with self.assertRaisesRegex(ValueError,'Downloaded Whisper cache'):recognition.prepare(self.config)
        self.download.assert_called_once()
        self.assertEqual((self.target/'model.bin').read_bytes(),b'bad downloaded weights')
        with self.no_model_imports(),self.assertRaisesRegex(ValueError,'Whisper cache'):
            recognition.Recognizer(self.config)
        self.download.assert_called_once()

    def test_missing_required_files_or_directory_instead_of_file_cannot_be_ready(self):
        for name in ('model.bin',*METADATA):
            with self.subTest(name=name):
                self.cache();(self.target/name).unlink()
                self.download.reset_mock();self.download.side_effect=lambda **kwargs:None
                with self.assertRaisesRegex(ValueError,'Downloaded Whisper cache'):recognition.prepare(self.config)
                self.download.assert_called_once()
                with self.no_model_imports(),self.assertRaisesRegex(ValueError,'Whisper cache'):
                    recognition.Recognizer(self.config)
                (self.target/name).mkdir()
                self.assertFalse(recognition.verified_whisper_cache(self.target,self.settings['sha256']))
                (self.target/name).rmdir()

    def test_unreadable_weights_or_metadata_after_acquisition_deny_before_model_import(self):
        self.cache();original=Path.open
        for name in ('model.bin','tokenizer.json'):
            self.download.reset_mock();self.download.side_effect=None
            def opened(path,*args,**kwargs):
                if path.name==name and args and args[0]=='rb':raise PermissionError('synthetic unreadable file')
                return original(path,*args,**kwargs)
            with patch.object(Path,'open',opened):
                with self.assertRaisesRegex(ValueError,'Downloaded Whisper cache'):recognition.prepare(self.config)
                with self.no_model_imports(),self.assertRaisesRegex(ValueError,'Whisper cache'):
                    recognition.Recognizer(self.config)
            self.download.assert_called_once()
        self.assertEqual((self.target/'model.bin').read_bytes(),WEIGHTS)

    def test_malformed_expected_hash_denies_before_directory_hf_or_model_import(self):
        original=builtins.__import__
        def guarded(name,*args,**kwargs):
            if name in ('huggingface_hub','faster_whisper','numpy'):raise AssertionError('Unexpected import')
            return original(name,*args,**kwargs)
        for value in (None,False,1,[],{},'','a'*63,'A'*64,'g'*64):
            self.settings['sha256']=value
            with self.subTest(value=value),patch('builtins.__import__',side_effect=guarded):
                with self.assertRaisesRegex(ValueError,'configured lowercase SHA256'):recognition.prepare(self.config)
                with self.assertRaisesRegex(ValueError,'configured lowercase SHA256'):recognition.Recognizer(self.config)
            self.assertFalse(self.target.exists())
        self.download.assert_not_called()

    def test_verified_startup_and_turn_do_not_acquire_or_rehash_but_postprepare_tamper_denies(self):
        self.cache();recognition.prepare(self.config)
        model=Mock();model.transcribe.side_effect=lambda *args,**kwargs:(iter(()),None)
        constructor=Mock(return_value=model)
        class Samples:
            def astype(self,*args):return self
            def __truediv__(self,*args):return self
        numpy=types.SimpleNamespace(float32=object(),zeros=Mock(return_value=Samples()),frombuffer=Mock(return_value=Samples()))
        with patch.dict(sys.modules,{'faster_whisper':types.SimpleNamespace(WhisperModel=constructor),'numpy':numpy}):
            recognizer=recognition.Recognizer(self.config)
            constructor.assert_called_once_with(str(self.target),device=self.settings['device'],compute_type=self.settings['compute_type'],
                                                cpu_threads=self.settings['cpu_threads'],local_files_only=True)
            with patch.object(recognition,'verified_whisper_cache',side_effect=AssertionError('No per-turn hash')):
                self.assertEqual(recognizer.transcribe(b'\0\0'),'')
        self.assertEqual(model.transcribe.call_count,2);self.download.assert_not_called()
        (self.target/'model.bin').write_bytes(b'post-prepare tamper')
        with self.no_model_imports(),self.assertRaisesRegex(ValueError,'Whisper cache'):
            recognition.Recognizer(self.config)
        self.download.assert_not_called()

    def test_acquisition_failure_propagates_once_and_vosk_path_stays_unchanged(self):
        self.download.side_effect=OSError('synthetic acquisition failure')
        with self.assertRaises(OSError):recognition.prepare(self.config)
        self.download.assert_called_once()
        self.settings.update(backend='vosk',sha256=None)
        self.download.reset_mock();model=object();constructor=Mock(return_value=model)
        with patch.dict(sys.modules,{'vosk':types.SimpleNamespace(Model=constructor,SetLogLevel=Mock())}):
            recognition.prepare(self.config);recognizer=recognition.Recognizer(self.config)
        constructor.assert_called_once_with(str(self.config.path(self.config['models']['stt']['path'])))
        self.assertIs(recognizer.model,model);self.download.assert_not_called()


if __name__=='__main__':unittest.main()
