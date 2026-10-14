"""The legacy overlay contains only its feature delta and explicit decoder closure."""
import ast
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_spoken_reply',ROOT/'deploy/autonomous/prepare_spoken_reply.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)


class OverlayTests(unittest.TestCase):
    def test_default_requires_existing_dependency_and_has_no_diagnostics(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'candidate';manifest=prepare.build(target)
            self.assertEqual(set(manifest['outputs']),{'voice.py','brains.py','spoken_reply.py'})
            self.assertIn('autonomous/contracts.py',manifest['required_existing_dependencies'])
            self.assertNotIn('def transcribe_diagnostic',(target/'voice.py').read_text())
            self.assertFalse(manifest['actual_model_capability_verified'])
            marker=target/'foreign';marker.write_text('keep')
            with self.assertRaises(FileExistsError):prepare.build(target)
            self.assertEqual(marker.read_text(),'keep')

    def test_absent_package_closure_imports_without_models_or_jsonschema(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'reachy_companion';manifest=prepare.build(target,include_decoder=True)
            self.assertEqual(manifest['required_absent_directory'],'autonomous')
            self.assertEqual(manifest['required_existing_dependencies'],{})
            self.assertEqual(len(manifest['outputs']),5)
            self.assertIsNone(manifest['preimages']['autonomous/contracts.py'])
            init=ast.parse((target/'autonomous/__init__.py').read_text())
            self.assertEqual(len(init.body),1)
            self.assertIsInstance(init.body[0],ast.Expr)
            self.assertIsInstance(init.body[0].value,ast.Constant)
            (target/'__init__.py').write_text('')
            code="""import sys
from reachy_companion.spoken_reply import decode_reply
r=dict(schema_version='reply-1',max_chars=10,no_question=True,no_wake=True)
assert decode_reply('{"reply":"six"}',r)=='six'
try: decode_reply('{"reply":"one","reply":"two"}',r)
except ValueError: pass
else: raise AssertionError('duplicate accepted')
assert not {'jsonschema','torch','piper','vosk','reachy_mini'} & set(sys.modules)
"""
            subprocess.run([sys.executable,'-c',code],cwd=td,check=True,capture_output=True)


if __name__=='__main__':unittest.main()
