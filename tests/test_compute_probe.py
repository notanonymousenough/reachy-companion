import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch

SOURCE=Path(__file__).resolve().parents[1]/'deploy/autonomous/compute_probe.py'


class ComputeProbeTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('compute_probe_test',SOURCE)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    def test_vendor_dll_path_only_changes_child_and_requires_manifest_match(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);vendor=root/'known-vendor';vendor.mkdir();(vendor/'cudart64_12.dll').touch()
            (root/'backend-manifest.json').write_text(json.dumps(dict(vendor_lib_package_names=['known-vendor'])))
            before=dict(os.environ);environment=module.native_environment(root/'server.exe',vendor)
            self.assertEqual(dict(os.environ),before)
            key=next(key for key in environment if key.upper()=='PATH')
            self.assertTrue(environment[key].startswith(str(vendor)+os.pathsep))
            (root/'backend-manifest.json').write_text('{}')
            with self.assertRaises(ValueError):module.native_environment(root/'server.exe',vendor)
    def test_gpu_receipt_distinguishes_partial_full_and_missing_offload(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'runtime.log'
            for text in ('offloaded 8/25 layers to GPU','offloaded 25/25 layers to GPU'):
                path.write_text(text)
                self.assertEqual(module.placement(path,8)['device'],'hybrid_pc' if '8/' in text else 'gpu_pc')
            path.write_text('model loaded')
            with self.assertRaises(RuntimeError):module.placement(path,8)
    def test_low_or_unknown_headroom_only_terminates_owned_runtime(self):
        module=self.module()
        for value in (dict(uuid='GPU-fixture',free_mib=500),RuntimeError('unknown metrics')):
            process=Mock();process.poll.return_value=None
            kwargs={'side_effect':value} if isinstance(value,Exception) else {'return_value':value}
            with patch.object(module,'gpu_sample',**kwargs):
                monitor=module.GPUHeadroom(process,0,512,dict(uuid='GPU-fixture',free_mib=1500))
                monitor.thread.join(1);monitor.close()
            self.assertIsNotNone(monitor.abort_reason);process.terminate.assert_called_once()

    def test_gateway_shutdown_failure_still_reaps_private_runtime(self):
        with patch.object(sys,'path',[str(SOURCE.parent),*sys.path]):
            spec=importlib.util.spec_from_file_location('gateway_probe_test',SOURCE.parent/'gateway_probe.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);token=root/'token';token.write_text('x'*64)
            args=SimpleNamespace(server=root/'server',weights=root/'weights',config=root/'config',token_file=token,
                output=root/'receipt.json',duration=0,threads=8,video_token_file=None,gpu_layers=0,
                vendor_dir=None,gpu_index=0,gpu_reserve_mib=512)
            cfg=dict(gateway=dict(bind='127.0.0.1',port=8097,token_env='FIXTURE_GATEWAY_TOKEN'),http_timeout_s=1,
                models=dict(fast=dict(base_url='http://127.0.0.1:18097',context_tokens=4096,id='fixture',
                    audit=dict(weight_sha256='fixture-hash',runtime_build='fixture-hash')),main={}))
            process=Mock();process.poll.side_effect=[None,0]
            api=Mock();api.shutdown.side_effect=RuntimeError('injected close failure')
            with patch.dict(os.environ,{},clear=False),patch.object(module.argparse.ArgumentParser,'parse_args',return_value=args),\
                    patch.object(module,'load',return_value=cfg),patch.object(module,'digest',return_value='fixture-hash'),\
                    patch.object(module,'main_identity',return_value={'id':'fixture-main'}),\
                    patch.object(module,'native_environment',return_value={}),patch.object(module.subprocess,'Popen',return_value=process),\
                    patch.object(module,'urlopen'),patch.object(module,'create_server',return_value=api),\
                    patch.object(module.threading.Thread,'start'):
                with self.assertRaises(SystemExit):module.main()
            process.terminate.assert_called_once();process.wait.assert_called_once()
            receipt=json.loads(args.output.read_text())
            self.assertTrue(receipt['process_reaped']);self.assertFalse(receipt['accepted'])
            self.assertEqual(receipt['cleanup_error'],'RuntimeError')
            self.assertEqual(json.loads((root/'inference-quarantine.local.json').read_text())['reason'],'gateway_cleanup_unknown')


if __name__=='__main__':unittest.main()
