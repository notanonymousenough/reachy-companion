"""Actual installed-package resolution with dormant src, no Docker/models/devices."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import venv

from reachy_companion import code_identity

ROOT = Path(__file__).resolve().parents[1]


class WorkerCodeIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        environment = self.root / 'venv'
        venv.EnvBuilder(with_pip=False).create(environment)
        self.python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        self.env = {key:value for key,value in os.environ.items()
                    if key not in ('PYTHONPATH', 'PYTHONHOME', 'REACHY_COMPANION_CODE_MANIFEST')}
        purelib = subprocess.check_output([str(self.python), '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'],
                                         env=self.env, text=True).strip()
        self.installed = Path(purelib).resolve() / 'reachy_companion'
        self.app = self.root / 'app';self.app.mkdir()
        self.reviewed = self.app / 'src/reachy_companion'
        for target in (self.installed, self.reviewed):
            shutil.copytree(ROOT / 'src/reachy_companion', target, ignore=shutil.ignore_patterns('__pycache__'))
        self.manifest = self.app / 'worker-code-identity.json'
        self.write_manifest()
        self.env['REACHY_COMPANION_CODE_MANIFEST'] = str(self.manifest)
        self.flags = ['-B', '-X', 'pycache_prefix=' + str(self.root / 'pycache')]

    def write_manifest(self):
        value = code_identity.source_manifest(self.reviewed, self.installed)
        self.manifest.write_text(json.dumps(value, sort_keys=True) + '\n')
        return value

    def run_worker(self, action='code-identity'):
        result = subprocess.run([str(self.python), *self.flags, '-m', 'reachy_companion',
                                 '--config', str(self.root / 'nonexistent-private-config.json'), 'worker', action],
                                cwd=self.app, env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.stderr, '')
        return result.returncode, json.loads(result.stdout)

    def test_installed_origins_match_manifest_without_config_token_model_or_bytecode_writes(self):
        status, report = self.run_worker()
        self.assertEqual(status, 0);self.assertTrue(report['ok'])
        self.assertEqual(report['expected_manifest_sha256'], hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        self.assertEqual(report['cwd'], str(self.app));self.assertFalse(report['imports_models'])
        self.assertIn('dont_write_bytecode=1', report['python_flags'])
        self.assertEqual(report['pycache_prefix'], str(self.root / 'pycache'))
        self.assertEqual(set(report['modules']), code_identity.MODULES)
        self.assertEqual(report['modules']['reachy_companion.voice']['origin'], str(self.installed / 'voice.py'))
        self.assertTrue(all(row['loader_matches_source'] for row in report['modules'].values()))
        self.assertFalse((self.root / 'pycache').exists())

    def test_dormant_src_hash_match_cannot_prove_effective_installed_overlay_for_any_worker_action(self):
        for name in ('voice.py', 'config.py'):
            path = self.reviewed / name;path.write_bytes(path.read_bytes() + b'\n# reviewed new generation\n')
        self.write_manifest()
        for action in ('code-identity', 'prepare', 'serve'):
            status, report = self.run_worker(action)
            self.assertEqual(status, 2)
            self.assertIn('source_mismatch:reachy_companion.voice', report['errors'])
            self.assertIn('source_mismatch:reachy_companion.config', report['errors'])
            self.assertEqual(report['modules']['reachy_companion.voice']['origin'], str(self.installed / 'voice.py'))

    def test_identical_cwd_shadow_package_is_denied_by_pinned_origin_root(self):
        shutil.copytree(self.installed, self.app / 'reachy_companion')
        status, report = self.run_worker()
        self.assertEqual(status, 2);self.assertIn('origin_mismatch:reachy_companion.voice', report['errors'])
        self.assertEqual(report['modules']['reachy_companion.voice']['sha256'],
                         json.loads(self.manifest.read_text())['modules']['reachy_companion.voice'])

    def test_missing_namespace_and_symlink_escape_deny(self):
        voice = self.installed / 'voice.py';source = voice.read_bytes();voice.unlink()
        status, report = self.run_worker()
        self.assertEqual(status, 2);self.assertIn('effective_source_unavailable:reachy_companion.voice', report['errors'])
        voice.write_bytes(source)
        (self.installed / '__init__.py').unlink()
        status, report = self.run_worker()
        self.assertEqual(status, 2);self.assertIn('effective_source_unavailable:reachy_companion', report['errors'])
        shutil.copyfile(self.reviewed / '__init__.py', self.installed / '__init__.py')
        outside = self.root / 'outside.py';outside.write_bytes(source);voice.unlink()
        try:voice.symlink_to(outside)
        except OSError:self.skipTest('Symlink creation unavailable')
        status, report = self.run_worker()
        self.assertEqual(status, 2);self.assertIn('origin_mismatch:reachy_companion.voice', report['errors'])

    def test_valid_timestamp_size_bytecode_still_must_match_source(self):
        voice = self.installed / 'voice.py'
        subprocess.run([str(self.python), *self.flags, '-c',
                        'import py_compile,sys; py_compile.compile(sys.argv[1],doraise=True)', str(voice)],
                       env=self.env, cwd=self.app, check=True, capture_output=True)
        stat = voice.stat()
        source = voice.read_bytes();changed = source.replace(b'reachy-voice', b'reachy-voicz')
        self.assertNotEqual(source, changed);self.assertEqual(len(source), len(changed))
        voice.write_bytes(changed);os.utime(voice, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        (self.reviewed / 'voice.py').write_bytes(changed);self.write_manifest()
        status, report = self.run_worker()
        self.assertEqual(status, 2);self.assertIn('bytecode_source_mismatch:reachy_companion.voice', report['errors'])
        self.assertNotIn('source_mismatch:reachy_companion.voice', report['errors'])

    def test_invalid_absent_unreadable_manifest_never_reports_verified(self):
        self.manifest.unlink()
        for action in ('code-identity', 'prepare', 'serve'):
            status, report = self.run_worker(action)
            self.assertEqual(status, 2);self.assertIn('invalid_expected_manifest', report['errors'])
        self.env['REACHY_COMPANION_CODE_MANIFEST'] = ''
        for action in ('code-identity', 'prepare', 'serve'):
            status, report = self.run_worker(action)
            self.assertEqual(status, 2);self.assertIn('invalid_expected_manifest', report['errors'])
        del self.env['REACHY_COMPANION_CODE_MANIFEST']
        status, report = self.run_worker()
        self.assertEqual(status, 2);self.assertIn('expected_manifest_required', report['errors'])
        self.env['REACHY_COMPANION_CODE_MANIFEST'] = str(self.manifest)
        raw = json.dumps(self.write_manifest())
        self.manifest.write_text(raw.replace('"version": 1', '"version": 0, "version": 1'))
        status, report = self.run_worker()
        self.assertEqual(status, 2);self.assertIn('invalid_expected_manifest', report['errors'])

    def test_manifest_schema_exact_module_set_hash_types_and_root_are_required(self):
        value = self.write_manifest()
        candidates = [None, {}, dict(value, version=True), dict(value, extra='field')]
        for root in ('relative', '//a/b', '/a/../b', '/a/./b', '/a\n', None):
            candidates.append(dict(value, package_root=root))
        for digest in (None, 0, 'a'*63, 'g'*64, []):
            changed = copy.deepcopy(value);changed['modules']['reachy_companion.voice'] = digest;candidates.append(changed)
        for name in ('reachy_companion.voice', 'reachy_companion.brains'):
            changed = copy.deepcopy(value);del changed['modules'][name];candidates.append(changed)
        changed = copy.deepcopy(value);changed['modules']['reachy_companion...escape'] = 'a'*64;candidates.append(changed)
        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):code_identity.validate_manifest(candidate)

    def test_unreadable_effective_source_is_typed_denial_without_model_import(self):
        manifest = self.root / 'source-expected.json'
        manifest.write_text(json.dumps(code_identity.source_manifest(ROOT / 'src/reachy_companion', ROOT / 'src/reachy_companion')))
        original = Path.read_bytes
        def read(path):
            if path.name == 'voice.py':raise PermissionError('fixture')
            return original(path)
        with patch.object(Path, 'read_bytes', read):report = code_identity.effective_identity(manifest)
        self.assertFalse(report['ok']);self.assertIn('effective_source_unavailable:reachy_companion.voice', report['errors'])
        with patch.object(Path, 'read_bytes', side_effect=PermissionError('fixture')):
            report = code_identity.effective_identity(manifest)
        self.assertFalse(report['ok']);self.assertIn('invalid_expected_manifest', report['errors'])

    def test_build_manifest_generator_uses_reviewed_tree_and_explicit_install_root(self):
        self.manifest.unlink()
        subprocess.run([str(self.python), *self.flags, str(self.reviewed / 'code_identity.py'),
                        '--source-root', str(self.reviewed), '--write-manifest', str(self.manifest),
                        '--package-root', str(self.installed)],
                       cwd=self.app, env=self.env, check=True, capture_output=True)
        self.assertEqual(json.loads(self.manifest.read_text())['package_root'], str(self.installed))
        status, report = self.run_worker()
        self.assertEqual(status, 0);self.assertTrue(report['ok'])


if __name__ == '__main__':unittest.main()
