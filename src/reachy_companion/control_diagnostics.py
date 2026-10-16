"""Optional RAM-only RPC observers: no retries, I/O, owners or error bodies.

Apply only to an isolated, source-pinned client module. The caller supplies a
bounded, nonblocking sink. HTTP status stays unknown unless the original error
exposes a typed HTTPError code; diagnostic failure never replaces an RPC result.
"""
import math
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit

_PATHS=frozenset(('/control/operator','/control/microphone','/control/motion-policy',
    '/control/volume','/control/status','/status','/robot/say'))
_ERRORS=frozenset(('HTTPError','URLError','TimeoutError','ConnectionError','ConnectionResetError',
    'ConnectionRefusedError','BrokenPipeError','RemoteDisconnected','OSError','RuntimeError',
    'ValueError','TypeError','KeyError','JSONDecodeError','KeyboardInterrupt','SystemExit'))


def _path(value):
    if type(value) is not str:return 'other'
    try:result=urlsplit(value).path
    except Exception:return 'other'
    return result if result in _PATHS else 'other'


def _clock(clock):
    try:value=clock()
    except Exception:return None
    return value if type(value) in (int,float) and 0<=value<=1e15 and math.isfinite(value) else None


def _metadata(path,payload):
    result=dict(path=_path(path),expected_epoch=None,desired_state={})
    if type(payload) is not dict:return result
    keys={'/control/microphone':('enabled','listen'),
        '/control/motion-policy':('motor_enabled','quiet','privacy_all')}.get(result['path'],())
    result['desired_state']={key:payload[key] for key in keys if key in payload and type(payload[key]) is bool}
    epoch=payload.get('expected_epoch')
    if keys and type(epoch) is int and 0<=epoch<2**63:result['expected_epoch']=epoch
    return result


def _emit(sink,kind,metadata,start,end,error):
    elapsed=end-start if start is not None and end is not None else None
    if elapsed is not None and not 0<=elapsed<=86400:elapsed=None
    name=type(error).__name__ if error is not None else None
    if name is not None and name not in _ERRORS:name='OtherError'
    status=error.code if isinstance(error,HTTPError) else None
    if type(status) is not int or not 100<=status<=599:status=None
    row=dict(metadata,kind=kind,success=error is None,exception_class=name,http_status=status,
        elapsed_seconds=round(elapsed,6) if elapsed is not None else None)
    try:sink(row)
    except Exception:pass  # KeyboardInterrupt/SystemExit retain their normal priority.


def trace_guarded_control(original,sink,*,clock=time.monotonic):
    """Forward every argument/result/exception once; emit only safe metadata."""
    def observed(*args,**kwargs):
        path=args[2] if len(args)>2 else kwargs.get('path')
        payload=args[3] if len(args)>3 else kwargs.get('payload')
        metadata=_metadata(path,payload);start=_clock(clock)
        try:result=original(*args,**kwargs)
        except BaseException as error:
            _emit(sink,'guarded_control',metadata,start,_clock(clock),error)
            raise
        _emit(sink,'guarded_control',metadata,start,_clock(clock),None)
        return result
    return observed


def trace_operator_reads(original,sink,*,clock=time.monotonic):
    """Observe failed operator GETs only; existing caller read retries remain."""
    def observed(*args,**kwargs):
        url=args[1] if len(args)>1 else kwargs.get('url')
        payload=args[2] if len(args)>2 else kwargs.get('payload')
        watched=_path(url)=='/control/operator' and payload is None
        start=_clock(clock) if watched else None
        try:return original(*args,**kwargs)
        except BaseException as error:
            if watched:_emit(sink,'operator_get',_metadata('/control/operator',None),start,_clock(clock),error)
            raise
    return observed
