"""Model-independent effective Python source identity; never changes sys.path."""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import sysconfig


MODULES = {'reachy_companion'} | {'reachy_companion.' + name for name in (
    '__main__ agent barge_in brains client code_identity config control_page deployment '
    'emotion_library expression_player expressions firewall hub intents logging_utils microphone '
    'motion_limits motion_policy motion_proxy recognition replay router sound_events sound_monitor '
    'speech_clock speech_motion spoken_reply spoken_reply_sdk spoken_vision token_stream voice volume worker_container').split()}


def source_manifest(root, package_root):
    """Build expectations from reviewed source, not the installed observation."""
    modules = {}
    for path in sorted(Path(root).glob('*.py')):
        name = 'reachy_companion' + ('.' + path.stem if path.stem != '__init__' else '')
        modules[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return validate_manifest(dict(version=1, package_root=str(package_root), modules=modules))


def validate_manifest(value):
    if (type(value) is not dict or set(value) != {'version', 'package_root', 'modules'}
            or type(value['version']) is not int or value['version'] != 1
            or type(value['modules']) is not dict or set(value['modules']) != MODULES
            or type(value['package_root']) is not str):
        raise ValueError('Invalid code identity manifest')
    root = Path(value['package_root'])
    if (not root.is_absolute() or value['package_root'].startswith('//')
            or str(root) != value['package_root'] or '..' in root.parts
            or any(ord(c) < 32 or ord(c) == 127 for c in value['package_root'])):
        raise ValueError('Invalid code identity package root')
    for name, digest in value['modules'].items():
        if (type(name) is not str or not re.fullmatch(r'reachy_companion(?:\.[a-zA-Z_]\w*)?', name)
                or type(digest) is not str or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('Invalid code identity manifest entry')
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:raise ValueError('Duplicate manifest key')
        result[key] = value
    return result


def effective_identity(manifest_path=None):
    """Resolve effective loaders without importing voice or model dependencies.

    This is startup provenance, not attestation of an already-running process.
    Loader bytecode must also match fresh compilation of the reported source.
    """
    expected = None
    expected_root = None
    manifest_sha256 = None
    errors = []
    try:
        if manifest_path is not None:
            raw = Path(manifest_path).read_bytes()
            if len(raw) > 1024 * 1024:raise ValueError('Oversized manifest')
            manifest = validate_manifest(json.loads(raw, object_pairs_hook=unique_object))
            expected = manifest['modules']
            expected_root = Path(manifest['package_root'])
            manifest_sha256 = hashlib.sha256(raw).hexdigest()
        else:
            errors.append('expected_manifest_required')
    except (OSError, ValueError, TypeError):
        errors.append('invalid_expected_manifest')
    rows = {}
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        for name in sorted(MODULES):
            try:
                spec = importlib.util.find_spec(name)
                if (spec is None or type(spec.loader) is not importlib.machinery.SourceFileLoader
                        or not spec.origin or not spec.origin.endswith('.py')):
                    raise ValueError('Source loader required')
                source = Path(spec.origin).read_bytes()
                digest = hashlib.sha256(source).hexdigest()
                code = spec.loader.get_code(name)
                fresh = compile(source, spec.origin, 'exec', dont_inherit=True, optimize=sys.flags.optimize)
                row = dict(origin=spec.origin, sha256=digest, loader_matches_source=code == fresh)
                rows[name] = row
                if expected_root is not None:
                    target = expected_root / ('__init__.py' if name == 'reachy_companion' else name.split('.')[-1] + '.py')
                    if Path(spec.origin) != target or Path(spec.origin).resolve() != target:
                        errors.append('origin_mismatch:' + name)
                if not row['loader_matches_source']:errors.append('bytecode_source_mismatch:' + name)
                if expected is not None and digest != expected[name]:errors.append('source_mismatch:' + name)
            except (ImportError, OSError, ValueError, TypeError, SyntaxError):
                rows[name] = dict(error='effective_source_unavailable')
                errors.append('effective_source_unavailable:' + name)
    finally:
        sys.dont_write_bytecode = previous
    return dict(ok=not errors, errors=errors, modules=rows, executable=sys.executable,
                cwd=os.getcwd(), python_flags=str(sys.flags), imports_models=False,
                pycache_prefix=sys.pycache_prefix,
                expected_manifest_sha256=manifest_sha256, expected_package_root=str(expected_root) if expected_root else None,
                scope='top_level_package_python_sources')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--write-manifest', required=True)
    parser.add_argument('--package-root', default=str(Path(sysconfig.get_path('purelib')) / 'reachy_companion'))
    args = parser.parse_args()
    Path(args.write_manifest).write_text(json.dumps(source_manifest(args.source_root, args.package_root), sort_keys=True) + '\n')


if __name__ == '__main__':main()
