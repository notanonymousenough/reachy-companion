"""Pure delta of the existing five-mount worker clone plan; no operations.

Private Docker inspection/config/env stays with the caller. Execution still
requires the existing SourceFences, OperationSlot, stopped-candidate admission,
exclusive port transition and exact recovery method. No payload is printed.
"""
import ast
import copy
import hashlib
import json
import ntpath
import re

SITE = '/usr/local/lib/python3.13/site-packages/reachy_companion/'
FILES = ('voice.py', 'config.py')


def need(value):
    if not value:
        raise ValueError('Question-gate worker preparation invariant')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def windows_equal(a, b):
    return (type(a) is str and type(b) is str and
            ntpath.normcase(ntpath.normpath(a)) == ntpath.normcase(ntpath.normpath(b)))


def stable_projection(snapshot, expected_instance, *, current_id, image_id):
    need(type(current_id) is str and re.fullmatch('[0-9a-f]{64}', current_id))
    need(type(image_id) is str and re.fullmatch('sha256:[0-9a-f]{64}', image_id))
    need(type(snapshot) is dict and snapshot.get('Id') == current_id and snapshot.get('Image') == image_id)
    need(type(expected_instance) is dict and set(expected_instance) == {'Pid', 'StartedAt'})
    state = snapshot['State']
    need(type(expected_instance['Pid']) is int and expected_instance['Pid'] > 1
        and type(expected_instance['StartedAt']) is str and 1 <= len(expected_instance['StartedAt']) <= 128)
    need(state.get('Running') is True and type(state.get('Pid')) is int
        and state['Pid'] == expected_instance['Pid'] and state.get('StartedAt') == expected_instance['StartedAt']
        and state.get('Paused') is False and state.get('Restarting') is False and state.get('OOMKilled') is False
        and type(snapshot.get('RestartCount')) is int and snapshot['RestartCount'] == 0)
    need(type(snapshot.get('Config')) is dict and type(snapshot.get('HostConfig')) is dict
        and type(snapshot.get('Mounts')) is list)
    result = copy.deepcopy({k: snapshot[k] for k in ('Id', 'Name', 'Image', 'Config', 'HostConfig', 'Mounts')})
    result['Mounts'] = sorted(result['Mounts'], key=lambda mount: mount['Destination'])
    digest(result)  # Reject non-finite/non-JSON private input without exporting it.
    return result


def prepare(snapshot, staged_sources, source_bytes, final_pins, expected_instance, *, current_id, image_id, stage_root):
    original = stable_projection(snapshot, expected_instance, current_id=current_id, image_id=image_id)
    need(set(staged_sources) == set(source_bytes) == set(final_pins) == set(FILES))
    need(type(stage_root) is str and ntpath.isabs(stage_root) and ntpath.normpath(stage_root) == stage_root)
    paths = []
    for name in FILES:
        raw, pin, path = source_bytes[name], final_pins[name], staged_sources[name]
        need(type(raw) is bytes and type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin)
            and hashlib.sha256(raw).hexdigest() == pin)
        ast.parse(raw, filename=name)
        need(type(path) is str and ntpath.isabs(path) and ntpath.normpath(path) == path
            and path.endswith('\\'+name) and '\x00' not in path)
        paths.append(path)
    stage = ntpath.dirname(paths[0])
    need(all(ntpath.dirname(path) == stage for path in paths))
    need(windows_equal(ntpath.commonpath([stage, stage_root]), stage_root) and not windows_equal(stage, stage_root))
    cfg, host = copy.deepcopy(snapshot['Config']), copy.deepcopy(snapshot['HostConfig'])
    need(host.get('ReadonlyRootfs') is True and host.get('Binds') is None)
    requests = host.get('Mounts')
    need(type(requests) is list and len(requests) == len(snapshot['Mounts']) == 5)
    destinations = [mount['Target'] for mount in requests]
    need(len(set(destinations)) == 5 and SITE+'brains.py' not in destinations and SITE+'token_stream.py' not in destinations)
    for req in requests:
        actual = [mount for mount in snapshot['Mounts'] if mount['Destination'] == req['Target']]
        need(len(actual) == 1 and req.get('Type') == actual[0].get('Type') == 'bind'
            and windows_equal(req['Source'], actual[0]['Source'])
            and type(req.get('ReadOnly', False)) is bool and type(actual[0].get('RW')) is bool
            and req.get('ReadOnly', False) == (actual[0]['RW'] is False))
    new = copy.deepcopy(requests)
    mounts = copy.deepcopy(snapshot['Mounts'])
    for name in FILES:
        target = SITE+name
        need(destinations.count(target) == 1)
        index = destinations.index(target)
        need(requests[index].get('ReadOnly') is True
            and not windows_equal(requests[index]['Source'], staged_sources[name]))
        new[index]['Source'] = staged_sources[name]
        actual = next(mount for mount in mounts if mount['Destination'] == target)
        actual['Source'] = staged_sources[name]
    host['Mounts'] = new
    # Retain the previously reviewed exact Engine case: running baseline null
    # becomes false in the newly created stopped candidate, not an OOM exemption.
    need(host.get('OomKillDisable') is None)
    host['OomKillDisable'] = False
    cfg['Image'] = image_id
    expected_cfg = copy.deepcopy(snapshot['Config'])
    expected_cfg['Image'] = image_id
    need(cfg == expected_cfg)
    restored_host = copy.deepcopy(host)
    restored_host['Mounts'] = requests
    restored_host['OomKillDisable'] = None
    need(restored_host == snapshot['HostConfig'] and len(new) == 5)
    need(sum(a != b for a, b in zip(new, requests)) == 2)
    payload = copy.deepcopy(cfg)
    payload['HostConfig'] = host
    expected = dict(Config=copy.deepcopy(cfg), HostConfig=copy.deepcopy(host), Mounts=mounts)
    summary = dict(kind='existing-worker-two-source-replacement-preparation',
        current_identity_verified=True, immutable_image_verified=True,
        stable_current_spec_SHA256=digest(original), candidate_payload_SHA256=digest(payload),
        source_SHA256=dict(final_pins), replaced_RO_destinations=[SITE+name for name in FILES],
        existing_mount_count=5, desired_mount_count=5, added_destinations=[],
        readonly_rootfs_preserved=True, restart_policy_preserved=True,
        explicit_Engine_OomKillDisable_null_to_false=True, all_other_HostConfig_exact=True,
        all_other_Config_exact=True, private_environment_exported=False, Docker_operations=0, model_requests=0)
    return dict(private_baseline_spec=original, private_create_payload=payload, expected=expected, public_summary=summary)


def acceptance_profile(original_bytes, *, expected_sha):
    need(type(original_bytes) is bytes and len(original_bytes) <= 1000000
        and type(expected_sha) is str and re.fullmatch('[0-9a-f]{64}', expected_sha)
        and hashlib.sha256(original_bytes).hexdigest() == expected_sha)
    def unique(items):
        result = {}
        for key, value in items:
            need(key not in result)
            result[key] = value
        return result
    def reject(value): raise ValueError('Non-finite private profile JSON')
    value = json.loads(original_bytes, object_pairs_hook=unique, parse_constant=reject)
    need(type(value) is dict and not set(value)-{'llm', 'tts', 'conversation'})
    need('conversation' not in value or type(value['conversation']) is dict)
    need('alice_question_gate' not in value.get('conversation', {}))
    candidate = copy.deepcopy(value)
    candidate.setdefault('conversation', {})['alice_question_gate'] = True
    check = copy.deepcopy(candidate)
    del check['conversation']['alice_question_gate']
    if 'conversation' not in value: del check['conversation']
    need(check == value)
    return json.dumps(candidate, ensure_ascii=False, indent=2, allow_nan=False).encode()+b'\n'


def may_start(*, manual_stop_absent, operation_slot_owned, pending_empty, robot_OFF_fresh,
              source_config_guards_exact, sole_worker_port, model_same):
    return all(value is True for value in (manual_stop_absent, operation_slot_owned, pending_empty,
        robot_OFF_fresh, source_config_guards_exact, sole_worker_port, model_same))
