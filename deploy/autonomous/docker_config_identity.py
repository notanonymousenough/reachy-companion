"""Pure Docker Config/HostConfig/Mounts identity; no inspection or operations.

The sole value equivalence is HostConfig.OomKillDisable: exact False == None.
All other JSON values retain their types, presence, and list order. Callers keep
raw inspection and their separate container/operation ownership checks.
"""
import hashlib
import json
import math


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

    Dictionary key order has no identity meaning; array order does. Missing or
    malformed sections reject. Missing OomKillDisable remains a distinct key
    absence. No other top-level inspect fields are covered by this identity.
    """
    if type(inspection) is not dict:raise ValueError('One parsed Docker inspection object required')
    expected={'Config':dict,'HostConfig':dict,'Mounts':list}
    if any(type(inspection.get(key)) is not kind for key,kind in expected.items()):
        raise ValueError('Complete Config/HostConfig/Mounts sections required')
    identity={key:_json_copy(inspection[key]) for key in expected}
    host=identity['HostConfig']
    if 'OomKillDisable' in host and host['OomKillDisable'] is None:
        host['OomKillDisable']=False
    return json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=True,
        allow_nan=False).encode('utf-8')


def container_config_fingerprint(inspection):
    """SHA256 of derived identity; does not log or mutate raw inspection."""
    return hashlib.sha256(container_config_identity(inspection)).hexdigest()
