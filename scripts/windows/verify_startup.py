"""Fail-closed read-only delegation seam; no runtime/OperationSlot implementation."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types


class StartupDenied(ValueError):pass


def canonical_manual_stop():
    if os.name!='nt':raise StartupDenied('windows_only')
    import ctypes
    buffer=ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None,28,None,0,buffer)!=0 or not buffer.value:
        raise StartupDenied('manual_stop_location_unavailable')
    return Path(buffer.value)/'ReachyCompanion/manual-stop.json'


def require_manual_stop_clear(path):
    for item in (*reversed(path.parents),path):
        try:value=item.lstat()
        except FileNotFoundError:continue
        except OSError:raise StartupDenied('manual_stop_unavailable') from None
        if os.name=='nt' and not hasattr(value,'st_file_attributes'):
            raise StartupDenied('manual_stop_unavailable')
        if stat.S_ISLNK(value.st_mode) or getattr(value,'st_file_attributes',0)&0x400:
            raise StartupDenied('manual_stop_reparse')
        if item==path:raise StartupDenied('manual_stop_present')


def read_bounded(path):
    if not path.is_file():raise StartupDenied('integration_file_unavailable')
    with path.open('rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):raise StartupDenied('integration_file_unavailable')
        raw=source.read(1048577)
    if len(raw)>1048576:raise StartupDenied('integration_file_bound')
    return raw


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise StartupDenied('configuration_duplicate_key')
        result[key]=value
    return result


def reject_constant(value):raise StartupDenied('configuration_nonfinite')


def configured_path(root,value):
    if type(value) is not str or not value or any(c in value for c in '\x00\r\n'):
        raise StartupDenied('integration_not_configured')
    path=Path(value)
    if not path.is_absolute() and path.anchor:raise StartupDenied('integration_path_ambiguous')
    return path if path.is_absolute() else root/path


class DiscardOutput:
    def write(self,value):return len(value)
    def flush(self):pass


EXPECTED_RESULT=dict(admission_known=True,operation_released=True,runtime_verified=True,
                     runtime_running=True,operation_unknown=False)
ERROR_CODES=frozenset(('windows_only','manual_stop_location_unavailable','manual_stop_unavailable',
    'manual_stop_reparse','manual_stop_present','integration_file_unavailable','integration_file_bound',
    'configuration_duplicate_key','configuration_nonfinite','integration_not_configured',
    'integration_path_ambiguous','adapter_hash_required','selector_unavailable','adapter_hash_mismatch',
    'adapter_interface_missing','adapter_verification_denied'))


def verify_startup(configuration,manual_stop):
    require_manual_stop_clear(manual_stop)
    configuration=Path(configuration).absolute()
    value=json.loads(read_bounded(configuration),object_pairs_hook=unique,parse_constant=reject_constant)
    try:settings=value['runtime']['windows']
    except (TypeError,KeyError):raise StartupDenied('integration_not_configured') from None
    if type(settings) is not dict:raise StartupDenied('integration_not_configured')
    adapter=configured_path(configuration.parent,settings.get('startup_adapter_path'))
    expected=settings.get('startup_adapter_sha256')
    selector=configured_path(configuration.parent,settings.get('accepted_runtime_selector'))
    if type(expected) is not str or re.fullmatch('[0-9a-f]{64}',expected) is None:
        raise StartupDenied('adapter_hash_required')
    if not selector.is_file():raise StartupDenied('selector_unavailable')
    raw=read_bounded(adapter)
    if hashlib.sha256(raw).hexdigest()!=expected:raise StartupDenied('adapter_hash_mismatch')
    require_manual_stop_clear(manual_stop)
    # Exact reviewed bytes, not a second pathname import or a second slot.
    module=types.ModuleType('_reachy_startup_adapter_'+expected)
    module.__file__=str(adapter);module.__package__=''
    previous=sys.modules.get(module.__name__)
    sys.modules[module.__name__]=module
    try:
        with contextlib.redirect_stdout(DiscardOutput()),contextlib.redirect_stderr(DiscardOutput()):
            exec(compile(raw,str(adapter),'exec'),module.__dict__)
            callback=getattr(module,'verify_accepted_runtime',None)
            if not callable(callback):raise StartupDenied('adapter_interface_missing')
            require_manual_stop_clear(manual_stop)
            result=callback(configuration_path=str(configuration),selector_path=str(selector),
                            manual_stop_path=str(manual_stop),allow_lifecycle=False)
        require_manual_stop_clear(manual_stop)
        if (type(result) is not dict or set(result)!=set(EXPECTED_RESULT)
                or any(type(result[key]) is not bool or result[key] is not expected for key,expected in EXPECTED_RESULT.items())):
            raise StartupDenied('adapter_verification_denied')
        return dict(ok=True,mode='pinned_external_adapter_read_only',lifecycle_allowed=False,
                    assurance='adapter_implementation_and_native_interoperability_require_independent_review')
    finally:
        if previous is None:sys.modules.pop(module.__name__,None)
        else:sys.modules[module.__name__]=previous


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration',required=True)
    args=parser.parse_args()
    try:report=verify_startup(args.configuration,canonical_manual_stop())
    except StartupDenied as exc:
        code=str(exc)
        report=dict(ok=False,error=code if code in ERROR_CODES else 'startup_adapter_denied_or_failed',lifecycle_allowed=False)
    except BaseException:report=dict(ok=False,error='startup_adapter_denied_or_failed',lifecycle_allowed=False)
    print(json.dumps(report,sort_keys=True))
    return 0 if report['ok'] else 2


if __name__=='__main__':raise SystemExit(main())
