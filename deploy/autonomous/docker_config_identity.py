"""Pure Docker Config/HostConfig/Mounts identity; no inspection or operations.

The legacy fingerprint equates HostConfig.OomKillDisable exact False and None.
Its top-level inspection Mounts is a set keyed by canonical Destination; nested
lists keep order. The separate candidate comparator has a scoped directional
exception instead. Callers keep raw inspection and separate ownership checks.
"""
import hashlib
import json
import math
from pathlib import PurePosixPath


def _json_copy(value):
    """Copy strict JSON builtins without bool/int equality or coercion."""
    kind=type(value)
    if value is None or kind in (str,bool,int):return value
    if kind is float:
        if not math.isfinite(value):raise ValueError('Finite JSON number required')
        return value
    if kind is list:return [_json_copy(item) for item in value]
    if kind is dict:
        if any(type(key) is not str for key in value):raise ValueError('JSON string keys required')
        return {key:_json_copy(item) for key,item in value.items()}
    raise ValueError('Strict JSON builtins required')


def container_config_identity(inspection):
    """Return canonical UTF-8 bytes for all three required inspect sections.

    Dictionary key order and top-level Mounts record order have no identity
    meaning; all nested array order does. Missing or
    malformed sections reject. Missing OomKillDisable remains a distinct key
    absence. No other top-level inspect fields are covered by this identity.
    """
    if type(inspection) is not dict:raise ValueError('One parsed Docker inspection object required')
    expected={'Config':dict,'HostConfig':dict,'Mounts':list}
    if any(type(inspection.get(key)) is not kind for key,kind in expected.items()):
        raise ValueError('Complete Config/HostConfig/Mounts sections required')
    identity={key:_json_copy(inspection[key]) for key in expected}
    destinations=set()
    for record in identity['Mounts']:
        target=record.get('Destination') if type(record) is dict else None
        if (type(target) is not str or not target.startswith('/') or target.startswith('//')
                or '\x00' in target or '\\' in target or '..' in target.split('/')
                or str(PurePosixPath(target))!=target or target in destinations):
            raise ValueError('Unique canonical nonempty mount Destination required')
        destinations.add(target)
    identity['Mounts'].sort(key=lambda record:record['Destination'])
    host=identity['HostConfig']
    if 'OomKillDisable' in host and host['OomKillDisable'] is None:
        host['OomKillDisable']=False
    return json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=True,
        allow_nan=False).encode('utf-8')


def container_config_fingerprint(inspection):
    """SHA256 of derived identity; does not log or mutate raw inspection."""
    return hashlib.sha256(container_config_identity(inspection)).hexdigest()


def candidate_config_matches(expected, actual, *, engine_version=None, api_version=None, owned_start=None):
    """Strict Config/HostConfig equality with one directional Engine exception.

    Unlike the legacy fingerprint above, this never generally equates null and
    False. expected includes the caller's freshly created owned candidate Id.
    owned_start is retained ONLY from the verified private receipt for this own
    204 start under its pending lifetime: exactly {Id, StartedAt, Pid}. Never
    infer it from an arbitrary running inspect. This pure helper cannot attest
    receipt issuance; see content-stream-engine-oom-comparison.md issuer contract.
    Both validation and compensation must call this same function, preserving
    their separate image/owner/mount/network/state/source-fence checks.
    """
    from datetime import datetime

    if type(expected) is not dict or type(actual) is not dict:
        raise ValueError('Parsed expected and actual candidate required')
    for value in (expected, actual):
        if any(type(value.get(key)) is not dict for key in ('Config','HostConfig')):
            raise ValueError('Complete Config and HostConfig required')
    # JSON encodings retain bool/int/float distinctions and every nested field.
    def exact(left, right):
        def encoded(value):
            return json.dumps(_json_copy(value),sort_keys=True,separators=(',',':'),allow_nan=False)
        return encoded(left)==encoded(right)

    candidate_id=expected.get('Id')
    if (type(candidate_id) is not str or not candidate_id
            or type(actual.get('Id')) is not str or actual['Id']!=candidate_id):return False
    if not exact(expected['Config'],actual['Config']):return False
    before=_json_copy(expected['HostConfig']);after=_json_copy(actual['HostConfig'])
    if exact(before,after):return True
    if (before.get('OomKillDisable', 'missing') is not False
            or 'OomKillDisable' not in after or after['OomKillDisable'] is not None):return False
    if (type(engine_version) is not str or engine_version!='29.7.2'
            or type(api_version) is not str or api_version!='1.55'):return False
    if (type(owned_start) is not dict or set(owned_start)!={'Id','StartedAt','Pid'}
            or type(owned_start['Id']) is not str or owned_start['Id']!=candidate_id
            or type(owned_start['Pid']) is not int or owned_start['Pid']<=0):return False
    started=owned_start['StartedAt']
    if type(started) is not str or len(started)>40 or not started.endswith('Z'):return False
    try:
        if datetime.fromisoformat(started[:-1]+'+00:00').year<1970:return False
    except ValueError:return False
    state=actual.get('State')
    if (type(state) is not dict or type(state.get('StartedAt')) is not str
            or state['StartedAt']!=started or type(state.get('Running')) is not bool
            or type(state.get('Pid')) is not int
            or state['Pid']!=(owned_start['Pid'] if state['Running'] else 0)
            or type(actual.get('RestartCount')) is not int or actual['RestartCount']!=0):return False
    after['OomKillDisable']=False
    return exact(before,after)
