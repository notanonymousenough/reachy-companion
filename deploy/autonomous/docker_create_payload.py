"""Pure Engine create body and exact expected inspection; no Docker operations.

Preserves complete Config/HostConfig JSON. Only image, owner label, restart
policy and one read-only brains bind are changed. The caller supplies the full
expected bind inspection rather than accepting an Engine-generated baseline.
"""
import json
import math
import ntpath
from pathlib import PurePosixPath
import re


def _copy(value):
    kind=type(value)
    if value is None or kind in (str,bool,int):return value
    if kind is float and math.isfinite(value):return value
    if kind is list:return [_copy(item) for item in value]
    if kind is dict and all(type(key) is str for key in value):
        return {key:_copy(item) for key,item in value.items()}
    raise ValueError('Strict finite JSON builtins required')


def _target(value):
    if (type(value) is not str or not value.startswith('/') or value.startswith('//') or '\x00' in value
            or '..' in value.split('/') or str(PurePosixPath(value))!=value):
        raise ValueError('Canonical Linux container mount destination required')
    return value


def parse_inspection(raw):
    """Decode an already obtained single inspect JSON object, without I/O."""
    if type(raw) not in (str,bytes):raise ValueError('Raw inspect JSON text required')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate JSON key')
            result[key]=value
        return result
    value=_copy(json.loads(raw,object_pairs_hook=pairs))
    if type(value) is not dict:raise ValueError('One inspect object required')
    return value


def _destinations(config,host,mounts):
    for mount in mounts:
        if type(mount) is not dict:raise ValueError('Complete original mount records required')
        yield _target(mount.get('Destination'))
    for mount in host.get('Mounts') or []:
        if type(mount) is not dict:raise ValueError('Original Engine mount specs required')
        yield _target(mount.get('Target'))
    for bind in host.get('Binds') or []:
        if type(bind) is not str:raise ValueError('Original bind strings required')
        # Linux destinations, including a Windows drive-letter source; no
        # rewrite of the original bind or any attempt to read its source.
        parts=bind.rsplit(':',2)
        yield _target(parts[-1] if len(parts)==1 or parts[-1].startswith('/') else parts[-2])
    for key in (config.get('Volumes'),host.get('Tmpfs')):
        if key is not None:
            if type(key) is not dict:raise ValueError('Original volume/tmpfs map required')
            for target in key:yield _target(target)


def build_create_payload(inspection,*,image_id,owner_label,owner_value,overlay_mount):
    """Return {payload, expected}; neither is a verified deployment receipt.

    overlay_mount is a full explicitly frozen bind inspection record with
    Type/Source/Destination/Mode/RW/Propagation. The Engine's actual output must
    match expected; callers cannot adopt a different clone. Bare Env entries
    remain literal strings and are never resolved against the host environment.
    """
    original=_copy(inspection)
    if type(original) is not dict or any(type(original.get(key)) is not kind
            for key,kind in (('Config',dict),('HostConfig',dict),('Mounts',list))):
        raise ValueError('Complete parsed Config/HostConfig/Mounts required')
    if (type(image_id) is not str or not re.fullmatch(r'sha256:[0-9a-f]{64}',image_id)
            or original.get('Image')!=image_id):
        raise ValueError('Explicit original immutable image ID required')
    if any(type(value) is not str or not value or '\x00' in value for value in (owner_label,owner_value)):
        raise ValueError('Explicit private owner label and value required')
    config=original['Config'];host=original['HostConfig']
    if any(key in config for key in ('HostConfig','NetworkingConfig')):
        raise ValueError('Reserved Engine request field in Config')
    labels=config.get('Labels')
    if labels is not None and (type(labels) is not dict or any(type(v) is not str for v in labels.values())):
        raise ValueError('Original string labels required')
    if labels is not None and owner_label in labels:raise ValueError('Existing private owner label')
    for key in ('Env','Entrypoint','Cmd'):
        value=config.get(key)
        if value is not None and (type(value) is not list or any(type(item) is not str for item in value)):
            raise ValueError('Original raw string array required')
    for key in ('Binds','Mounts'):
        if host.get(key) is not None and type(host[key]) is not list:
            raise ValueError('Original bind/mount array required')
    policy=host.get('RestartPolicy')
    if policy is not None and type(policy) is not dict:raise ValueError('Original restart policy map required')
    overlay=_copy(overlay_mount)
    keys={'Type','Source','Destination','Mode','RW','Propagation'}
    if (type(overlay) is not dict or set(overlay)!=keys or overlay['Type']!='bind'
            or overlay['Mode']!='ro' or overlay['RW'] is not False or overlay['Propagation']!='rprivate'):
        raise ValueError('Explicit complete read-only private bind inspection required')
    source=overlay['Source'];target=_target(overlay['Destination'])
    if (type(source) is not str or not source or '\x00' in source
            or not (source.startswith('/') or (ntpath.splitdrive(source)[0] and ntpath.isabs(source)))
            or PurePosixPath(target).name!='brains.py'):
        raise ValueError('Explicit absolute brains source and destination required')
    if target in set(_destinations(config,host,original['Mounts'])):
        raise ValueError('Overlay destination already occupied')
    config['Image']=image_id
    config['Labels']={**(labels or {}),owner_label:owner_value}
    host['RestartPolicy']={**(policy or {}),'Name':'no','MaximumRetryCount':0}
    mount=dict(Type='bind',Source=source,Target=target,ReadOnly=True,
        BindOptions={'Propagation':'rprivate'})
    host['Mounts']=[*(host.get('Mounts') or []),mount]
    payload={**config,'HostConfig':host}
    expected=dict(Config=_copy(config),HostConfig=_copy(host),Mounts=original['Mounts']+[overlay])
    # Independent output copies, strict serialization, no logging of payloads.
    json.dumps(payload,allow_nan=False)
    return dict(payload=payload,expected=expected)
