"""Pure Phase B no-output plan/admission; never opens UART or controls a unit.

Only trusted, independently frozen runner metadata is validated here. A grant
is not an executor, hardware attestation, permission to arm, or a restart recipe.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import PurePosixPath
import re
from .factory_head_process import SOURCE_PINS
from .factory_head_kinematics import ANALYTICAL_SHA256,ASSETS_SHA256

NS=1_000_000_000
READ_ONLY_ARGS=dict(autostart=True,no_media=True,wake_up_on_start=False,goto_sleep_on_stop=False,
    preload_datasets=False,dataset_update_interval_hours=0,fastapi_host='127.0.0.1',sim=False,mockup_sim=False,
    hardware_config_filepath=None,kinematics_engine='AnalyticalKinematics',check_collision=False)
SAFE_HOOKS={**{key:[] for key in ('ExecStop','ExecStopPost','OnFailure','OnSuccess','RestartForceExitStatus',
    'TriggeredBy','PartOf','Upholds','ExternalRestartSources')},'Restart':'no','FailureAction':'none',
    'SuccessAction':'none','StartLimitAction':'none','WatchdogUSec':0}
FORBIDDEN=('arm','refresh','torque_enable','torque_write','goal','mode_write','pid_write','raw_write','reboot','sleep_trajectory')
UNSAFE_LEGACY=frozenset(('c820c8097f4516b350f898067701e33f564dc82a6f2d678523d238017b8edd94',
    'ccc3e29366a9047ed32ce0dd8add3b7b35b40faf582d6b9858851c039fb7ada9'))


def canonical(value):
    def check(item):
        kind=type(item)
        if item is None or kind in (str,int,bool):return
        if kind is float and math.isfinite(item):return
        if kind is list:
            for child in item:check(child)
            return
        if kind is dict and all(type(key) is str for key in item):
            for child in item.values():check(child)
            return
        raise ValueError('Strict finite JSON metadata required')
    check(value)
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def _same(left,right):return canonical(left)==canonical(right)
def _keys(value,keys):
    if type(value) is not dict or set(value)!=set(keys.split()):raise ValueError('Complete exact typed metadata required')
def _int(value,low=0):
    if type(value) is not int or value<low:raise ValueError('Exact bounded integer required')
    return value
def _sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('Frozen SHA256 required')
def _text(value):
    if type(value) is not str or not 1<=len(value)<=256 or '\x00' in value:raise ValueError('Opaque binding required')
def _path(value):
    _text(value)
    if (not value.startswith('/') or value.startswith('//') or '\\' in value or '..' in value.split('/')
            or str(PurePosixPath(value))!=value):raise ValueError('Canonical absolute Linux path required')
def _unit(value,suffix='service'):
    if type(value) is not str or not re.fullmatch(r'[a-zA-Z0-9_@.:-]+\.'+suffix,value):raise ValueError('Exact unit name required')
def _pid(value,cgroup):
    _keys(value,'pid start_ticks cgroup');_int(value['pid'],2);_int(value['start_ticks'],1)
    if value['cgroup']!=cgroup:raise ValueError('Foreign cgroup process')
def _file(value,*,mapped=False):
    _keys(value,'path device inode sha256'+(' pid' if mapped else ''))
    _path(value['path']);_int(value['device']);_int(value['inode'],1);_sha(value['sha256'])
    if mapped:_int(value['pid'],2)
def _uart(value):
    _keys(value,'path device inode rdev');_path(value['path']);_int(value['device']);_int(value['inode'],1);_int(value['rdev'],1)
def _hooks(value):
    if not _same(value,SAFE_HOOKS):raise ValueError('Unknown exit hooks/restart sources are not admitted')


def _scope(value):
    _keys(value,'unit invocation_id cgroup cgroup_type main uart_child members executables native_mappings config_files hooks hook_audit_sha256')
    _unit(value['unit']);_sha(value['hook_audit_sha256'])
    if type(value['invocation_id']) is not str or not re.fullmatch('[0-9a-f]{32}',value['invocation_id']):
        raise ValueError('Exact unit InvocationID required')
    node=value['cgroup'];_keys(node,'path device inode');_path(node['path']);_int(node['device']);_int(node['inode'],1)
    if not node['path'].endswith('/'+value['unit']) or value['cgroup_type']!='domain':raise ValueError('Exact nonroot domain cgroup required')
    _hooks(value['hooks'])
    members=value['members']
    if type(members) is not list or not 1<=len(members)<=16:raise ValueError('Bounded complete cgroup members required')
    for member in [*members,value['main'],value['uart_child']]:_pid(member,node['path'])
    if (len({m['pid'] for m in members})!=len(members) or value['main'] not in members or value['uart_child'] not in members):
        raise ValueError('MainPID and actual UART child must belong to exact inventory')
    for key in ('executables','native_mappings','config_files'):
        files=value[key]
        if type(files) is not list or not 1<=len(files)<=32:raise ValueError('Complete mapped/config file identities required')
        for item in files:
            _file(item,mapped=key!='config_files')
            if key!='config_files' and item['pid'] not in {m['pid'] for m in members}:raise ValueError('Foreign mapped executable/native')
    if {f['pid'] for f in value['executables']}!={m['pid'] for m in members}:raise ValueError('Every process executable must be frozen')
    if value['uart_child']['pid'] not in {f['pid'] for f in value['native_mappings']}:raise ValueError('Actual UART child native mapping required')


def _operator(value):
    _keys(value,'agent_boot_id microphone_epoch microphone_owner_id microphone_enabled capture_active listening policy_epoch motion_owner motor_enabled quiet privacy_all')
    for key in ('agent_boot_id','motion_owner'):_text(value[key])
    for key in ('microphone_epoch','policy_epoch'):_int(value[key])
    if value['microphone_owner_id'] is not None:_text(value['microphone_owner_id'])
    if any(value[key] is not False for key in ('microphone_enabled','capture_active','listening','motor_enabled')):
        raise ValueError('No-output baseline requires actual capture/listen/motor policy off')
    if any(type(value[key]) is not bool for key in ('quiet','privacy_all')):raise ValueError('Typed operator policy required')


def _validate(spec):
    _keys(spec,'kind nonce clock_domain clock_proof_sha256 issued_ns deadline_ns factory uart operator fence recovery candidate')
    if spec['kind']!='factory-head-phase-b-nooutput-1':raise ValueError('Unarmed Phase B plan required')
    if spec['clock_domain']!='linux_clock_monotonic':raise ValueError('Verified Linux monotonic domain required')
    _sha(spec['clock_proof_sha256'])
    _text(spec['nonce']);_int(spec['issued_ns']);_int(spec['deadline_ns'])
    if not 0<spec['deadline_ns']-spec['issued_ns']<=30*NS:raise ValueError('Finite Phase B deadline required')
    _scope(spec['factory']);_uart(spec['uart']);_operator(spec['operator'])
    fence=spec['fence'];_keys(fence,'unit owner_nonce dropin marker start_blocked restart')
    _file(fence['dropin']);_file(fence['marker'])
    if (fence['unit']!=spec['factory']['unit'] or fence['owner_nonce']!=spec['nonce']
            or fence['start_blocked'] is not True or fence['restart']!='no'
            or not fence['dropin']['path'].startswith('/run/systemd/system/'+fence['unit']+'.d/')
            or not fence['marker']['path'].startswith('/run/')):raise ValueError('Exact runtime restart/start fence required')
    candidate=spec['candidate']
    _keys(candidate,'unit cgroup_path entry native kinematics native_version kinematics_version static_proof_sha256 source_pins args sample_count')
    _unit(candidate['unit']);_path(candidate['cgroup_path'])
    if not candidate['cgroup_path'].endswith('/'+candidate['unit']):raise ValueError('Exact candidate cgroup required')
    for key in ('entry','native','kinematics'):_file(candidate[key])
    _sha(candidate['static_proof_sha256'])
    if (candidate['entry']['sha256'] in UNSAFE_LEGACY or candidate['native_version']!='1.5.6+finite.head.4'
            or candidate['kinematics_version']!='1.0.3' or not _same(candidate['args'],READ_ONLY_ARGS)
            or any(PurePosixPath(candidate[key]['path']).suffix!='.so' for key in ('native','kinematics'))
            or not _same(candidate['source_pins'],{**SOURCE_PINS,'analytical':ANALYTICAL_SHA256,'assets':ASSETS_SHA256})
            or not 3<=_int(candidate['sample_count'])<=16):raise ValueError('Reviewed fresh readonly .4 preparation required')
    recovery=spec['recovery']
    _keys(recovery,'unit timer_unit timer_invocation_id cgroup_path entry definition owner_nonce armed_ns due_ns active oneshot persistent mode hooks')
    _unit(recovery['unit']);_unit(recovery['timer_unit'],'timer');_path(recovery['cgroup_path'])
    _file(recovery['entry']);_file(recovery['definition']);_hooks(recovery['hooks'])
    if (type(recovery['timer_invocation_id']) is not str or not re.fullmatch('[0-9a-f]{32}',recovery['timer_invocation_id'])
            or recovery['entry']['sha256'] in UNSAFE_LEGACY
            or recovery['owner_nonce']!=spec['nonce'] or recovery['active'] is not True or recovery['oneshot'] is not True
            or recovery['persistent'] is not False or recovery['mode']!='kill_owned_candidate_keep_fenced'
            or not _int(recovery['armed_ns'])<=spec['issued_ns']<_int(recovery['due_ns'])<=spec['deadline_ns']
            or not recovery['cgroup_path'].endswith('/'+recovery['unit'])):raise ValueError('Independent finite recovery must already be armed')
    groups=[spec['factory']['cgroup']['path'],candidate['cgroup_path'],recovery['cgroup_path']]
    if any(a==b or a.startswith(b+'/') or b.startswith(a+'/') for i,a in enumerate(groups) for b in groups[i+1:]):
        raise ValueError('Factory/candidate/recovery must be independent exact scopes')


@dataclass(frozen=True)
class PhaseBPlan:
    encoded:bytes
    @property
    def identity(self):return hashlib.sha256(self.encoded).hexdigest()
    def data(self):return json.loads(self.encoded)


def freeze_plan(spec,*,expected_sha256):
    _validate(spec);_sha(expected_sha256)
    if digest(spec)!=expected_sha256:raise ValueError('Independently frozen plan digest mismatch')
    return PhaseBPlan(canonical(spec))


def _fresh(spec,observed,now_ns):
    _int(now_ns);_int(observed['begin_ns']);_int(observed['end_ns'])
    if not (spec['issued_ns']<=observed['begin_ns']<=observed['end_ns']<=now_ns<spec['deadline_ns']
            and now_ns-observed['begin_ns']<NS//10):raise ValueError('Fresh original-BEGIN runtime evidence required')
    if observed['clock_domain']!=spec['clock_domain']:raise ValueError('Foreign clock domain')
    for key in ('operator','fence','recovery'):
        if not _same(observed[key],spec[key]):raise ValueError('Newer/foreign operator/fence/recovery wins')
    if not _same(observed['uart'],spec['uart']):raise ValueError('UART device identity changed')
    files=observed['factory']['config_files'] if 'factory' in observed else observed['factory_config_files']
    if not _same(files,spec['factory']['config_files']):raise ValueError('Original factory configuration changed')
    if now_ns>=spec['recovery']['due_ns']:raise ValueError('Recovery firing/unknown; no takeover admission')


def authorize_takeover(plan,observed,*,now_ns,action):
    """Admit only pinned-cgroup freeze or SIGKILL; no ordinary stop signal."""
    spec=plan.data();_validate(spec)
    _keys(observed,'clock_domain begin_ns end_ns factory operator fence recovery uart uart_owners inventory_complete descendants cgroup_frozen freeze_begin_ns scope_pin')
    _fresh(spec,observed,now_ns);_scope(observed['factory'])
    if (not _same(observed['factory'],spec['factory']) or observed['inventory_complete'] is not True
            or observed['descendants']!=[] or not _same(observed['uart_owners'],[spec['factory']['uart_child']])):
        raise ValueError('PID/start/native/config/cgroup/serial ownership changed or incomplete')
    pin=observed['scope_pin'];_keys(pin,'method cgroup invocation_id owner_nonce exclusive_control_sha256')
    _sha(pin['exclusive_control_sha256'])
    if (pin['method']!='pinned_cgroup_v2' or not _same(pin['cgroup'],spec['factory']['cgroup'])
            or pin['invocation_id']!=spec['factory']['invocation_id'] or pin['owner_nonce']!=spec['nonce']):
        raise ValueError('Exact retained kernel cgroup pin required; no name/PID lookup kill')
    if action=='freeze':
        if observed['cgroup_frozen'] is not False or observed['freeze_begin_ns'] is not None:raise ValueError('Unexpected prior freeze')
    elif action=='kill':
        if (observed['cgroup_frozen'] is not True or type(observed['freeze_begin_ns']) is not int
                or not spec['recovery']['armed_ns']<=observed['freeze_begin_ns']<=observed['begin_ns']):
            raise ValueError('Recovery-before-freeze and actual frozen event required')
    else:raise ValueError('No ordinary SIGTERM/systemctl stop/Daemon.stop action exists')
    return dict(kind='pinned_cgroup_freeze' if action=='freeze' else 'pinned_cgroup_sigkill',plan_id=plan.identity,
        owner_nonce=spec['nonce'],scope_pin=json.loads(canonical(pin)),members=spec['factory']['members'],
        expires_ns=min(observed['begin_ns']+NS//10,spec['recovery']['due_ns'],spec['deadline_ns']),
        automatic_restart=False,restore_operator=False,physical_stop_proven=False)


def authorize_candidate(plan,observed,*,now_ns):
    spec=plan.data();_validate(spec)
    _keys(observed,'clock_domain begin_ns end_ns operator fence recovery uart factory_config_files retired_factory exited_members current_invocation_id current_main_pid cgroup_identity cgroup_populated uart_owners')
    _fresh(spec,observed,now_ns)
    if (observed['retired_factory']!=digest(spec['factory']) or not _same(observed['exited_members'],spec['factory']['members'])
            or observed['current_invocation_id'] not in ('',spec['factory']['invocation_id']) or observed['current_main_pid']!=0
            or type(observed['current_main_pid']) is not int
            or observed['cgroup_identity'] is not None and not _same(observed['cgroup_identity'],spec['factory']['cgroup'])
            or observed['cgroup_populated'] is not False or observed['uart_owners']!=[]):
        raise ValueError('Known exact old-generation exit and UART-free proof required')
    return dict(kind='prepare_factory_app_unarmed',plan_id=plan.identity,candidate=spec['candidate'],
        deadline_ns=spec['deadline_ns'],arm_allowed=False,torque_enable_allowed=False,goals_allowed=False,
        automatic_restart=False,restore_operator=False)


def assess_readonly(plan,receipt,current,*,now_ns):
    """Safe handback-review eligibility, never automatic restoration/capability."""
    result=dict(accepted=False,keep_fence=True,automatic_restart=False,restore_operator=False,
        head_hardware_acceptance=False,movement_admission=False,eligible_for_separate_handback_review=False)
    try:
        spec=plan.data();_validate(spec);_fresh(spec,current,now_ns)
        _keys(current,'clock_domain begin_ns end_ns operator fence recovery uart factory_config_files runtime_id exited_members current_invocation_id current_main_pid cgroup_identity cgroup_populated uart_owners')
        _keys(receipt,'plan_id candidate_runtime startup forbidden_counts trace_sha256 samples native_unknown execution_busy exit')
        if receipt['plan_id']!=plan.identity:raise ValueError('Wrong Phase B generation')
        runtime=receipt['candidate_runtime'];_scope(runtime)
        child_mappings=[{k:v for k,v in f.items() if k!='pid'} for f in runtime['native_mappings'] if f['pid']==runtime['uart_child']['pid']]
        if (runtime['unit']!=spec['candidate']['unit'] or runtime['cgroup']['path']!=spec['candidate']['cgroup_path']
                or spec['candidate']['native'] not in child_mappings or spec['candidate']['kinematics'] not in child_mappings
                or spec['candidate']['entry'] not in runtime['config_files']
                or receipt['native_unknown'] is not False or receipt['execution_busy'] is not False):raise ValueError('Candidate runtime/native completion unknown')
        _sha(receipt['trace_sha256'])
        _keys(receipt['forbidden_counts'],' '.join(FORBIDDEN))
        if any(type(v) is not int or v!=0 for v in receipt['forbidden_counts'].values()):
            raise ValueError('Phase B forbids arm, enable, writes, goals and sleep')
        startup=receipt['startup'];_keys(startup,'readonly complete reads health torque duration_ms')
        if (startup['readonly'] is not True or startup['complete'] is not True or type(startup['reads']) is not int
                or startup['reads']!=63 or startup['torque']!=[False]*9 or any(v is not False for v in startup['torque'])
                or type(startup['health']) is not list or len(startup['health'])!=9
                or any(type(v) is not int or v not in (0,1) for v in startup['health'])
                or type(startup['duration_ms']) not in (int,float) or not math.isfinite(startup['duration_ms'])
                or not 0<=startup['duration_ms']<=1000):raise ValueError('Actual readonly 63-read constructor proof required')
        if type(receipt['samples']) is not list or len(receipt['samples'])!=spec['candidate']['sample_count']:raise ValueError('Planned actual samples required')
        previous=-1;last_end=-1
        for frame in receipt['samples']:
            _keys(frame,'runtime_id begin_ns end_ns positions torque head_pose fk_residual_rad fk_quarantined')
            if frame['runtime_id']!=digest(runtime):raise ValueError('Foreign sample producer')
            begin=_int(frame['begin_ns']);end=_int(frame['end_ns'])
            if not spec['issued_ns']<=begin<end<=spec['deadline_ns'] or end-begin>NS//10 or begin<=previous or begin<last_end:
                raise ValueError('Read/FK original-BEGIN span/order exceeded')
            previous=begin;last_end=end
            values=frame['positions']
            if (type(values) is not list or len(values)!=9 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values)
                    or frame['torque']!=[False]*9 or any(v is not False for v in frame['torque']) or frame['fk_quarantined'] is not False):
                raise ValueError('Fresh all-nine position/torque proof required')
            _keys(frame['head_pose'],'x y z roll pitch yaw')
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in frame['head_pose'].values()):raise ValueError('Finite actual FK required')
            residual=frame['fk_residual_rad']
            if (type(residual) not in (int,float) or not math.isfinite(residual) or not 0<=residual<=.002
                    or math.cos(frame['head_pose']['roll'])*math.cos(frame['head_pose']['pitch'])<=0):raise ValueError('Actual bounded upright FK proof required')
        exit=receipt['exit'];_keys(exit,'runtime_id confirmed end_ns cgroup_populated uart_owners')
        if (exit['runtime_id']!=digest(runtime) or exit['confirmed'] is not True or exit['cgroup_populated'] is not False
                or exit['uart_owners']!=[] or not last_end<=_int(exit['end_ns'])<=now_ns
                or current['runtime_id']!=digest(runtime) or not _same(current['exited_members'],runtime['members'])
                or current['current_invocation_id'] not in ('',runtime['invocation_id']) or type(current['current_main_pid']) is not int
                or current['current_main_pid']!=0
                or current['cgroup_identity'] is not None and not _same(current['cgroup_identity'],runtime['cgroup'])
                or current['cgroup_populated'] is not False or current['uart_owners']!=[]):
            raise ValueError('Known exact candidate exit and fresh UART-free inventory required')
        result.update(accepted=True,eligible_for_separate_handback_review=True)
    except (ValueError,TypeError,KeyError,OverflowError):pass
    return result
