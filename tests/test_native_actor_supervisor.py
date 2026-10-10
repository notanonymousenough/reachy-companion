import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_actor_probe', ROOT/'deploy/autonomous/native_actor_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class SupervisorTests(unittest.TestCase):
    def execute(self, child_fails, import_fails=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'config.local.json').write_text('{}')
            args = SimpleNamespace(production_root=root, output=root/'receipt.json', motor_test=True)
            calls = []
            operator = dict(agent_boot_id='agent', microphone_epoch=0, microphone_enabled=False, capture_active=False, phase='paused')
            def command(parts, **kwargs):
                calls.append(parts)
                if import_fails and '-c' in parts: raise ImportError('injected package resolution failure')
                if '--child' in parts:
                    args.output.with_suffix('.child.json').write_text(json.dumps({'accepted': not child_fails}))
                    if child_fails: raise RuntimeError('injected child failure')
                text = 'active\n' if 'is-active' in parts else 'enabled\n' if '--property=UnitFileState' in parts else 'no\n' if '--property=ConditionResult' in parts else '{}'
                return SimpleNamespace(stdout=text)
            class Response:
                def __init__(self, url): self.url = url
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, *args):
                    path = self.url.rsplit('/api/', 1)[1]
                    value = {'motors/status': {'mode': 'disabled'}, 'move/running': [],
                             'daemon/robot-app-lock-status': {'state': 'free'},
                             'daemon/status': {'state': 'running', 'backend_status': {'ready': True}}}[path]
                    return json.dumps(value).encode()
            original_read = Path.read_text
            def read_text(path, *args, **kwargs):
                if str(path) == '/proc/123456789/cgroup': return probe.FACTORY
                return original_read(path, *args, **kwargs)
            with patch.object(probe.os, 'geteuid', return_value=0), patch.object(probe, 'operator', return_value=operator), \
                 patch.object(probe, 'serial_owners', side_effect=[[123456789], [], []]), \
                 patch.object(probe.subprocess, 'run', side_effect=command), patch.object(Path, 'read_text', read_text), \
                 patch.object(probe, 'MARKER', root/'marker'), patch.object(probe, 'DROPIN', root/'dropin'), \
                 patch.object(probe, 'build_opener') as opener:
                opener.return_value.open.side_effect = lambda url, **kwargs: Response(url)
                if import_fails:
                    with self.assertRaises(ImportError): probe.supervisor(args)
                    self.assertFalse((root/'marker').exists())
                    self.assertFalse((root/'dropin').exists())
                    self.assertFalse(any('stop' in parts or 'start' in parts or parts[0]=='systemd-run' for parts in calls))
                    return
                result = probe.supervisor(args)
            report = json.loads(args.output.read_text())
            rollback = [parts for parts in calls if parts[0] == '/bin/bash']
            self.assertEqual(len(rollback), 1)
            unit = next(parts for parts in calls if '--child' in parts)
            self.assertIn('env', unit)
            self.assertTrue(any(part.startswith('PYTHONPATH=') for part in unit))
            preflight = next(parts for parts in calls if '--import-check' in parts)
            self.assertLess(calls.index(preflight), next(i for i, parts in enumerate(calls) if 'stop' in parts))
            self.assertTrue(report['factory_restored'])
            self.assertTrue(report['operator_unchanged'])
            self.assertTrue(report['config_unchanged'])
            self.assertTrue(report['native_ready_after'])
            self.assertTrue(any('reachy-native-fence-rollback.timer' in parts for parts in calls))
            self.assertEqual(result, 2 if child_fails else 0)
            self.assertEqual(report['accepted'], not child_fails)

    def test_failed_native_child_still_runs_independent_release_and_factory_restore(self): self.execute(True)
    def test_accepted_child_requires_restored_factory_and_operator(self): self.execute(False)
    def test_missing_isolated_import_fails_before_service_or_fence_mutation(self): self.execute(False, True)

    def test_recovery_without_durable_enable_intent_never_imports_native_driver(self):
        with tempfile.TemporaryDirectory() as directory, patch('importlib.util.spec_from_file_location', side_effect=AssertionError('native import')):
            probe.recover(SimpleNamespace(intent=Path(directory)/'absent'))
            invalid = Path(directory)/'intent'
            invalid.write_text(json.dumps({'baseline_torque': [1]*9, 'enabled_ids': [17]}))
            with self.assertRaises(RuntimeError): probe.recover(SimpleNamespace(intent=invalid))


if __name__ == '__main__': unittest.main()
