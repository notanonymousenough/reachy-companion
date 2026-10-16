#!/usr/bin/env python3
"""Exact installed Agent289 overlay and its shared pure status consumer contract."""
import argparse
import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BASE='2865db30e92fcb069c241c34bae4419ad65ed594'
INITIAL='0a7c0a3d7cbd542eabf9412291fda052c559db8c6bac123db31676b0137bd908'
BEFORE='289469a5de57f01295e6c8ddde3e78ba2804fe2f5e6c603a4789e3d70e6ebeb9'
AFTER='c2fcb832501c55dd56a86abd7b87c71b05c013f968a2482dbfc1a27d3283f2f5'
LAYERS=(('reachy-agent-0a7-bound-vision-speech.patch','53a43647c4744dde3c7b112d12212477943ce22f9f33b90ffbeeb916d28f23c3'),
    ('reachy-agent-53a-spoken-vision.patch','9a4269f757bdc90d5da33cd9ccfa1d302c53a21fae4452d9d6bcdc4a5f578840'),
    ('reachy-agent-9a-vision-route-observation.patch',BEFORE),
    ('reachy-agent-289-stream-timing.patch',AFTER))


def digest(raw):return hashlib.sha256(raw).hexdigest()


def candidate():
    spec=importlib.util.spec_from_file_location('exact_overlay_tools',ROOT/'deploy/autonomous/prepare_content_stream.py')
    patcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(patcher)
    raw=subprocess.check_output(['git','show',BASE+':src/reachy_companion/agent.py'],cwd=ROOT)
    if digest(raw)!=INITIAL:raise ValueError('Wrong legacy Agent preimage')
    before=None
    for name,expected in LAYERS:
        if name==LAYERS[-1][0]:before=raw
        raw=patcher.apply_exact(raw.decode(),(ROOT/'deploy/patches'/name).read_text()).encode()
        if digest(raw)!=expected:raise ValueError('Wrong exact Agent overlay output')
    return before,raw


def load_contract(raw):
    """Extract only the SAME schema/validator from hash-pinned Agent, no app imports."""
    if type(raw) is not bytes or digest(raw)!=AFTER:raise ValueError('Pinned timing Agent source required')
    tree=ast.parse(raw);names={'STREAM_TIMING_MARKS','STREAM_TIMING_FIELDS'}
    nodes=[node for node in tree.body if
        isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in node.targets)
        or isinstance(node,ast.FunctionDef) and node.name=='validate_stream_timing']
    if len(nodes)!=3:raise ValueError('Exact timing contract required')
    namespace=dict(math=math)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'pinned-timing-contract','exec'),namespace)
    return namespace['validate_stream_timing']


def project_status(status,validator,expected_attempt=None):
    """Existing finite observer returns ONLY the validated current-generation record."""
    def require(good):
        if not good:raise ValueError('Invalid Agent timing projection')
    require(type(status) is dict and 'stream_timing' in status)
    if expected_attempt is not None:
        require(type(expected_attempt) is str and len(expected_attempt)==32
                and all(c in '0123456789abcdef' for c in expected_attempt))
    if status['stream_timing'] is None:return None
    row=validator(status['stream_timing'])
    require(type(status.get('agent_boot_id')) is str and status['agent_boot_id']==row['agent_boot_id'])
    require(type(status.get('microphone_epoch')) is int and status['microphone_epoch']==row['microphone_epoch'])
    policy=status.get('motion_policy')
    require(type(policy) is dict and type(policy.get('epoch')) is int and policy['epoch']==row['policy_epoch'])
    if expected_attempt is not None:
        require(row['content_binding']=='bound' and row['content_attempt_id']==expected_attempt)
    return row



def parse_status(raw,validator,expected_attempt=None):
    """Bounded existing /status body; reject duplicate/nonfinite JSON before projection."""
    if type(raw) is not bytes or len(raw)>16000:raise ValueError('Invalid Agent timing status body')
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('Duplicate Agent timing status key')
            value[key]=item
        return value
    def constant(_):raise ValueError('Non-finite Agent timing status number')
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    return project_status(value,validator,expected_attempt)


def build(destination):
    before,raw=candidate();compile(raw,'exact-agent-stream-timing.py','exec');load_contract(raw)
    manifest=dict(kind='exact-agent289-stream-timing-1',preimage_sha256=digest(before),output_sha256=digest(raw),
        contract_source='agent.py:validate_stream_timing',consumer='prepare_agent_stream_timing.project_status',
        fields=21,devices_modified=False,actual_onset_verified=False)
    destination.mkdir(mode=0o700)
    with (destination/'agent.py').open('xb') as file:file.write(raw)
    with (destination/'manifest.json').open('x') as file:file.write(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    print(json.dumps(build(parser.parse_args().destination),indent=2))
