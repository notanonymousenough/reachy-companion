"""Public delegation seam only. Fake adapters prove no native slot/runtime claim."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('startup_verification',ROOT/'scripts/windows/verify_startup.py')
startup=importlib.util.module_from_spec(spec);spec.loader.exec_module(startup)


class StartupVerificationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.config=self.root/'config.local.json'
        self.adapter=self.root/'adapter.py';self.selector=self.root/'opaque.selector'
        self.selector.write_bytes(b'OPAQUE PRIVATE FORMAT, not JSON')
        self.latch=self.root/'LocalAppData/ReachyCompanion/manual-stop.json'
        self.calls=self.root/'calls.json'
        self.configure()

    def configure(self,body=None):
        if body is None:
            body=('import json\nfrom pathlib import Path\n'
                  'def verify_accepted_runtime(**kwargs):\n'
                  '    path=Path(kwargs["configuration_path"]).with_name("calls.json")\n'
                  '    assert not path.exists()\n'
                  '    path.write_text(json.dumps(kwargs))\n'
                  '    print("PRIVATE ADAPTER OUTPUT")\n'
                  '    return '+repr(startup.EXPECTED_RESULT)+'\n')
        self.adapter.write_text(body)
        self.settings=dict(startup_adapter_path='adapter.py',startup_adapter_sha256=hashlib.sha256(self.adapter.read_bytes()).hexdigest(),
                           accepted_runtime_selector='opaque.selector')
        self.save_config()

    def save_config(self):self.config.write_text(json.dumps(dict(runtime=dict(windows=self.settings),private_value='PRIVATE CONFIG')))

    def run_main(self):
        output=io.StringIO()
        with patch.object(startup,'canonical_manual_stop',return_value=self.latch), \
                patch.object(sys,'argv',['verify_startup.py','--configuration',str(self.config)]),patch('sys.stdout',output):
            status=startup.main()
        return status,json.loads(output.getvalue())

    def test_one_exact_read_only_call_with_opaque_selector_and_no_config_mutation(self):
        before=self.config.read_bytes();selector=self.selector.read_bytes()
        status,report=self.run_main()
        self.assertEqual(status,0);self.assertTrue(report['ok']);self.assertFalse(report['lifecycle_allowed'])
        self.assertIn('independent_review',report['assurance'])
        self.assertEqual(json.loads(self.calls.read_text()),dict(configuration_path=str(self.config),selector_path=str(self.selector),
                                                               manual_stop_path=str(self.latch),allow_lifecycle=False))
        self.assertEqual(self.config.read_bytes(),before);self.assertEqual(self.selector.read_bytes(),selector)
        self.assertNotIn('PRIVATE',json.dumps(report))

    def test_latch_presence_even_malformed_denies_before_any_configuration_io(self):
        self.latch.parent.mkdir(parents=True);self.latch.write_bytes(b'not JSON')
        with patch.object(startup,'read_bounded',side_effect=AssertionError('No configuration read')):
            status,report=self.run_main()
        self.assertEqual(status,2);self.assertEqual(report['error'],'manual_stop_present')
        self.assertFalse(self.calls.exists());self.assertEqual(self.latch.read_bytes(),b'not JSON')

    def test_latch_lookup_access_error_or_reparse_denies_without_fallback(self):
        original=Path.lstat
        def denied(path,*args,**kwargs):
            if path==self.latch:raise PermissionError('PRIVATE error')
            return original(path,*args,**kwargs)
        with patch.object(Path,'lstat',denied):
            status,report=self.run_main()
        self.assertEqual(status,2);self.assertEqual(report['error'],'manual_stop_unavailable')
        # A mocked Windows stat without native attributes cannot prove safety.
        with patch.object(startup,'os',types.SimpleNamespace(name='nt')):
            with self.assertRaisesRegex(startup.StartupDenied,'manual_stop_unavailable'):
                startup.require_manual_stop_clear(self.latch)
        self.latch.parent.mkdir(parents=True);target=self.root/'foreign';target.mkdir()
        link=self.root/'linked';link.symlink_to(target,target_is_directory=True)
        with self.assertRaisesRegex(startup.StartupDenied,'manual_stop_reparse'):
            startup.verify_startup(self.config,link/'manual-stop.json')
        self.assertFalse(self.calls.exists())

    def test_missing_empty_wrong_hash_and_missing_selector_never_execute_adapter(self):
        for change in (dict(startup_adapter_path=''),dict(startup_adapter_sha256=''),
                       dict(startup_adapter_sha256='0'*64),dict(accepted_runtime_selector='missing'),
                       dict(startup_adapter_sha256=True),dict(startup_adapter_path=None)):
            original=dict(self.settings);self.settings.update(change);self.save_config()
            status,report=self.run_main();self.assertEqual(status,2);self.assertFalse(report['ok'])
            self.assertFalse(self.calls.exists());self.settings=original
        self.config.write_text('{}');status,report=self.run_main();self.assertEqual(status,2)
        self.assertFalse(self.calls.exists())

    def test_duplicate_nonfinite_and_oversized_configuration_denies_without_adapter(self):
        for raw in ('{"runtime": {}, "runtime": {}}','{"runtime": NaN}', ' '*1048577):
            self.config.write_text(raw);status,report=self.run_main()
            self.assertEqual(status,2);self.assertFalse(report['ok']);self.assertFalse(self.calls.exists())

    def test_compiles_exact_pinned_bytes_without_second_pathname_read(self):
        original=startup.read_bounded
        def read(path):
            raw=original(path)
            if path==self.adapter:self.adapter.write_text('raise RuntimeError("Wrong reopened source")')
            return raw
        with patch.object(startup,'read_bounded',side_effect=read):status,report=self.run_main()
        self.assertEqual(status,0);self.assertTrue(report['ok']);self.assertTrue(self.calls.exists())

    def test_unknown_busy_stopped_unreleased_nonboolean_and_extra_content_results_deny(self):
        cases=[None,[],True,dict(startup.EXPECTED_RESULT,private='PRIVATE')]
        cases += [dict(startup.EXPECTED_RESULT,**{key:not value}) for key,value in startup.EXPECTED_RESULT.items()]
        cases += [dict(startup.EXPECTED_RESULT,runtime_running=1)]
        for value in cases:
            self.configure('def verify_accepted_runtime(**kwargs):\n    return '+repr(value)+'\n')
            status,report=self.run_main();self.assertEqual(status,2)
            self.assertEqual(report['error'],'adapter_verification_denied');self.assertNotIn('PRIVATE',json.dumps(report))

    def test_adapter_exception_interface_error_and_private_error_text_are_sanitized(self):
        for body in ('raise RuntimeError("PRIVATE")','def verify_accepted_runtime(**kwargs):\n    raise ValueError("PRIVATE")',
                     'value=1','from __main__ import __name__\ndef verify_accepted_runtime(**kwargs):\n    return None'):
            self.configure(body);status,report=self.run_main()
            self.assertEqual(status,2);self.assertNotIn('PRIVATE',json.dumps(report));self.assertFalse(report['lifecycle_allowed'])

    def test_manual_stop_created_during_adapter_execution_wins_and_remains(self):
        self.configure('from pathlib import Path\ndef verify_accepted_runtime(**kwargs):\n'
            '    path=Path(kwargs["manual_stop_path"]);path.parent.mkdir(parents=True,exist_ok=True);path.write_text("operator stop")\n'
            '    return '+repr(startup.EXPECTED_RESULT)+'\n')
        status,report=self.run_main()
        self.assertEqual(status,2);self.assertEqual(report['error'],'manual_stop_present')
        self.assertEqual(self.latch.read_text(),'operator stop')

    def test_start_entrypoints_delegate_once_and_disabled_bootstrap_is_not_fallback(self):
        for name in ('start.ps1','start-worker.ps1'):
            source=(ROOT/'scripts'/name).read_text()
            self.assertEqual(source.count('Invoke-CompanionAcceptedRuntimeVerification'),1)
            self.assertLess(source.index('Assert-CompanionNotManuallyStopped'),source.index('Invoke-CompanionAcceptedRuntimeVerification'))
            for forbidden in ('Invoke-WorkerDocker','Invoke-RestMethod','Start-Process','Start-ScheduledTask','WriteAllText',
                              'Read-CompanionSettings','git pull','bootstrap.ps1','bootstrap-worker.ps1'):
                self.assertNotIn(forbidden,source)
        for name in ('bootstrap.ps1','bootstrap-worker.ps1'):
            source=(ROOT/'scripts'/name).read_text()
            self.assertTrue(source.splitlines()[0].startswith('param('));self.assertTrue(source.splitlines()[1].startswith('throw '))
        common=(ROOT/'scripts/common.ps1').read_text().split('function Assert-CompanionNotManuallyStopped')[0]
        self.assertEqual(common.count('& $PythonExecutable'),1)
        self.assertEqual(common.count('Assert-CompanionNotManuallyStopped'),2)
        self.assertIn("@('-I','-B'",common)


if __name__=='__main__':unittest.main()
