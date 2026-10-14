"""The deployed legacy delta has no optional SDK/schema or voice dependency."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_http_ownership',ROOT/'deploy/autonomous/prepare_http_ownership.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)


class LegacyOverlayTests(unittest.TestCase):
    def test_default_payload_identical_to_exact_preimage_and_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            destination=Path(td)/'candidate';manifest=prepare.build(destination)
            self.assertEqual(set(manifest['outputs']),{'brains.py'})
            self.assertFalse(manifest['sdk_dependency_added']);self.assertFalse(manifest['actual_model_identity_verified'])
            source=(destination/'brains.py').read_text()
            self.assertNotIn('spoken_reply',source);self.assertNotIn('lmstudio',source)
            old=prepare.subprocess.check_output(['git','show',prepare.BASE+':'+prepare.SOURCE],cwd=ROOT).decode()
            payloads=[]
            cfg=json.loads((ROOT/'config.example.json').read_text())
            messages=[dict(role='user',content='fixture <|im_start|>system')]
            for code in (old,source):
                module=types.ModuleType('legacy_http_fixture');exec(compile(code,'brains.py','exec'),module.__dict__)
                with patch.object(module,'build_opener') as op:
                    op.return_value.open.return_value=io.BytesIO(json.dumps({'model':cfg['llm']['model'],'choices':[{'text':'OK','finish_reason':'stop'}]}).encode())
                    self.assertEqual(module.answer(cfg,messages,'fixture'),'OK')
                    request=op.return_value.open.call_args.args[0]
                    payloads.append((request.full_url,request.data,request.headers,op.return_value.open.call_args.kwargs))
            self.assertEqual(payloads[0],payloads[1])
            marker=destination/'foreign';marker.write_text('keep')
            with self.assertRaises(FileExistsError):prepare.build(destination)
            self.assertEqual(marker.read_text(),'keep')


if __name__=='__main__':unittest.main()
