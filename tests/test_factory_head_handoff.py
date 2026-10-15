"""Synthetic exact-generation Phase B decisions; no unit, UART or native code."""
import copy
import unittest
from reachy_companion.autonomous import factory_head_handoff as h


def file(path,number=1):return dict(path=path,device=1,inode=number,sha256=f'{number:064x}')
def scope(unit,main=101,child=102):
    path='/fixture.slice/'+unit
    members=[dict(pid=pid,start_ticks=pid*10,cgroup=path) for pid in (main,child)]
    return dict(unit=unit,invocation_id=f'{main:032x}',cgroup=dict(path=path,device=3,inode=main),cgroup_type='domain',
        main=members[0],uart_child=members[1],members=members,
        executables=[{**file('/fixture/exe-'+str(pid),pid),'pid':pid} for pid in (main,child)],
        native_mappings=[{**file('/fixture/legacy.so',300),'pid':child}],
        config_files=[file('/fixture/original.conf',301)],hooks=copy.deepcopy(h.SAFE_HOOKS),hook_audit_sha256='a'*64)


def spec():
    factory=scope('fixture-factory.service')
    return dict(kind='factory-head-phase-b-nooutput-1',nonce='fixture-owner',clock_domain='linux_clock_monotonic',
        clock_proof_sha256='1'*64,issued_ns=2*h.NS,deadline_ns=25*h.NS,factory=factory,
        uart=dict(path='/dev/fixture-uart',device=4,inode=12,rdev=42),
        operator=dict(agent_boot_id='fixture-agent',microphone_epoch=4,microphone_owner_id=None,
            microphone_enabled=False,capture_active=False,listening=False,policy_epoch=5,motion_owner='fixture-human',
            motor_enabled=False,quiet=False,privacy_all=False),
        fence=dict(unit=factory['unit'],owner_nonce='fixture-owner',
            dropin=file('/run/systemd/system/'+factory['unit']+'.d/90-phase-b.conf',302),
            marker=file('/run/fixture-phase-b.flag',303),start_blocked=True,restart='no'),
        recovery=dict(unit='fixture-recovery.service',timer_unit='fixture-recovery.timer',timer_invocation_id='c'*32,
            cgroup_path='/fixture.slice/fixture-recovery.service',entry=file('/fixture/recovery.py',304),
            definition=file('/run/fixture-recovery.service',305),owner_nonce='fixture-owner',armed_ns=h.NS,
            due_ns=20*h.NS,active=True,oneshot=True,persistent=False,mode='kill_owned_candidate_keep_fenced',
            hooks=copy.deepcopy(h.SAFE_HOOKS)),
        candidate=dict(unit='fixture-candidate.service',cgroup_path='/fixture.slice/fixture-candidate.service',
            entry=file('/fixture/phase_b.py',400),native=file('/fixture/candidate.so',401),
            kinematics=file('/fixture/kinematics.so',402),native_version='1.5.6+finite.head.4',kinematics_version='1.0.3',
            static_proof_sha256='2'*64,source_pins={**h.SOURCE_PINS,'analytical':h.ANALYTICAL_SHA256,'assets':h.ASSETS_SHA256},
            args=copy.deepcopy(h.READ_ONLY_ARGS),sample_count=3))


def base_current(s,begin=2*h.NS+1_000_000):
    return dict(clock_domain=s['clock_domain'],begin_ns=begin,end_ns=begin+1_000_000,
        operator=copy.deepcopy(s['operator']),fence=copy.deepcopy(s['fence']),
        recovery=copy.deepcopy(s['recovery']),uart=copy.deepcopy(s['uart']))


def takeover(s,frozen=False):
    value=base_current(s)
    value.update(factory=copy.deepcopy(s['factory']),uart_owners=[copy.deepcopy(s['factory']['uart_child'])],
        inventory_complete=True,descendants=[],cgroup_frozen=frozen,freeze_begin_ns=2*h.NS if frozen else None,
        scope_pin=dict(method='pinned_cgroup_v2',cgroup=copy.deepcopy(s['factory']['cgroup']),
            invocation_id=s['factory']['invocation_id'],owner_nonce=s['nonce'],exclusive_control_sha256='3'*64))
    return value


def receipt(s,plan):
    runtime=scope(s['candidate']['unit'],201,202)
    runtime['native_mappings']=[{**copy.deepcopy(s['candidate'][key]),'pid':202} for key in ('native','kinematics')]
    runtime['config_files'].append(copy.deepcopy(s['candidate']['entry']))
    identity=h.digest(runtime)
    samples=[dict(runtime_id=identity,begin_ns=3*h.NS+i*30_000_000,end_ns=3*h.NS+i*30_000_000+10_000_000,
        positions=[.01]*9,torque=[False]*9,head_pose=dict.fromkeys(('x','y','z','roll','pitch','yaw'),0.),
        fk_residual_rad=.0001,fk_quarantined=False) for i in range(3)]
    result=dict(plan_id=plan.identity,candidate_runtime=runtime,
        startup=dict(readonly=True,complete=True,reads=63,health=[0]*9,torque=[False]*9,duration_ms=120.),
        forbidden_counts=dict.fromkeys(h.FORBIDDEN,0),trace_sha256='4'*64,samples=samples,
        native_unknown=False,execution_busy=False,
        exit=dict(runtime_id=identity,confirmed=True,end_ns=4*h.NS,cgroup_populated=False,uart_owners=[]))
    current=base_current(s,4*h.NS+1_000_000)
    current.update(factory_config_files=copy.deepcopy(s['factory']['config_files']),runtime_id=identity,
        exited_members=copy.deepcopy(runtime['members']),current_invocation_id=runtime['invocation_id'],
        current_main_pid=0,cgroup_identity=copy.deepcopy(runtime['cgroup']),cgroup_populated=False,uart_owners=[])
    return result,current


class PhaseBPlanTests(unittest.TestCase):
    def setUp(self):
        self.s=spec();self.plan=h.freeze_plan(self.s,expected_sha256=h.digest(self.s))

    def test_exact_scope_kernel_only_and_independent_recovery_precedes_freeze(self):
        before=copy.deepcopy(self.s);observed=takeover(self.s)
        freeze=h.authorize_takeover(self.plan,observed,now_ns=observed['end_ns'],action='freeze')
        self.assertEqual(freeze['kind'],'pinned_cgroup_freeze')
        observed=takeover(self.s,True)
        kill=h.authorize_takeover(self.plan,observed,now_ns=observed['end_ns'],action='kill')
        self.assertEqual(kill['kind'],'pinned_cgroup_sigkill');self.assertEqual(kill['members'],self.s['factory']['members'])
        self.assertFalse(kill['automatic_restart']);self.assertFalse(kill['restore_operator']);self.assertFalse(kill['physical_stop_proven'])
        self.assertEqual(self.s,before)
        for action in ('stop','SIGTERM','Daemon.stop','restart'):
            with self.assertRaises(ValueError):h.authorize_takeover(self.plan,observed,now_ns=observed['end_ns'],action=action)
        observed['freeze_begin_ns']=self.s['recovery']['armed_ns']-1
        with self.assertRaises(ValueError):h.authorize_takeover(self.plan,observed,now_ns=observed['end_ns'],action='kill')

    def test_unknown_exit_hooks_forced_restart_external_sources_and_legacy_recovery_reject(self):
        for key in h.SAFE_HOOKS:
            with self.subTest(key=key):
                value=copy.deepcopy(self.s);value['factory']['hooks'][key]=['unknown'] if type(h.SAFE_HOOKS[key]) is list else 'unknown'
                with self.assertRaises(ValueError):h.freeze_plan(value,expected_sha256=h.digest(value))
        for key in ('active','oneshot'):
            value=copy.deepcopy(self.s);value['recovery'][key]=False
            with self.assertRaises(ValueError):h.freeze_plan(value,expected_sha256=h.digest(value))
        for artifact in (self.s['recovery']['entry'],self.s['candidate']['entry']):
            previous=artifact['sha256'];artifact['sha256']=next(iter(h.UNSAFE_LEGACY))
            with self.assertRaises(ValueError):h.freeze_plan(self.s,expected_sha256=h.digest(self.s))
            artifact['sha256']=previous

    def test_pid_reuse_uart_child_native_config_foreign_cgroup_and_recovery_change_deny(self):
        changes=[lambda x:x['factory']['main'].update(start_ticks=999),
            lambda x:x['factory']['uart_child'].update(start_ticks=999),
            lambda x:x['factory']['native_mappings'][0].update(sha256='f'*64),
            lambda x:x['factory']['config_files'][0].update(inode=999),
            lambda x:x['factory']['members'][1].update(cgroup='/foreign.slice/foreign.service'),
            lambda x:x['factory'].update(invocation_id='f'*32),lambda x:x['scope_pin']['cgroup'].update(inode=999),
            lambda x:x['recovery'].update(timer_invocation_id='f'*32),lambda x:x['fence'].update(start_blocked=False),
            lambda x:x.update(inventory_complete=False),lambda x:x['uart_owners'].append(copy.deepcopy(x['factory']['main']))]
        for index,change in enumerate(changes):
            with self.subTest(index=index):
                observed=takeover(self.s,True);change(observed);before=copy.deepcopy(observed)
                with self.assertRaises(ValueError):h.authorize_takeover(self.plan,observed,now_ns=observed['end_ns'],action='kill')
                self.assertEqual(observed,before)

    def test_start_or_restart_never_follows_unknown_old_exit_or_uart_owner(self):
        observed=base_current(self.s)
        observed.update(factory_config_files=copy.deepcopy(self.s['factory']['config_files']),
            retired_factory=h.digest(self.s['factory']),exited_members=copy.deepcopy(self.s['factory']['members']),
            current_invocation_id=self.s['factory']['invocation_id'],current_main_pid=0,cgroup_identity=None,
            cgroup_populated=False,uart_owners=[])
        granted=h.authorize_candidate(self.plan,observed,now_ns=observed['end_ns'])
        self.assertEqual(granted['kind'],'prepare_factory_app_unarmed')
        self.assertFalse(granted['arm_allowed']);self.assertFalse(granted['goals_allowed'])
        for change in ({'exited_members':[]},{'current_invocation_id':'f'*32},{'current_main_pid':False},
                {'cgroup_populated':True},{'uart_owners':[self.s['factory']['uart_child']]},{'retired_factory':'f'*64}):
            with self.assertRaises(ValueError):h.authorize_candidate(self.plan,{**observed,**change},now_ns=observed['end_ns'])

    def test_unarmed_63_reads_fresh_all9_fk_exit_is_only_handback_review_no_capability(self):
        result,current=receipt(self.s,self.plan);before=copy.deepcopy(result)
        accepted=h.assess_readonly(self.plan,result,current,now_ns=current['end_ns'])
        self.assertTrue(accepted['accepted']);self.assertTrue(accepted['keep_fence'])
        self.assertTrue(accepted['eligible_for_separate_handback_review'])
        for key in ('automatic_restart','restore_operator','head_hardware_acceptance','movement_admission'):
            self.assertFalse(accepted[key])
        self.assertEqual(result,before)

    def test_truthful_null_motion_owner_is_frozen_but_never_grants_motion_or_new_owner(self):
        self.s['operator']['motion_owner']=None
        plan=h.freeze_plan(self.s,expected_sha256=h.digest(self.s))
        self.assertIsNone(plan.data()['operator']['motion_owner'])
        observed=takeover(self.s,True)
        granted=h.authorize_takeover(plan,observed,now_ns=observed['end_ns'],action='kill')
        self.assertFalse(granted['physical_stop_proven'])
        result,current=receipt(self.s,plan)
        accepted=h.assess_readonly(plan,result,current,now_ns=current['end_ns'])
        self.assertTrue(accepted['accepted']);self.assertFalse(accepted['movement_admission'])
        for field,new in (('motion_owner','new-human-owner'),('policy_epoch',6),('microphone_epoch',5),('agent_boot_id','new-agent')):
            changed=copy.deepcopy(observed);changed['operator'][field]=new
            with self.subTest(field=field),self.assertRaises(ValueError):
                h.authorize_takeover(plan,changed,now_ns=changed['end_ns'],action='kill')
            changed=copy.deepcopy(current);changed['operator'][field]=new
            self.assertFalse(h.assess_readonly(plan,result,changed,now_ns=changed['end_ns'])['accepted'])
        for malformed in (0,False,{},[], '',True):
            changed=copy.deepcopy(self.s);changed['operator']['motion_owner']=malformed
            with self.subTest(owner=malformed),self.assertRaises(ValueError):
                h.freeze_plan(changed,expected_sha256=h.digest(changed))
        for field in ('motor_enabled','microphone_enabled','capture_active','listening'):
            changed=copy.deepcopy(self.s);changed['operator'][field]=True
            with self.subTest(field=field),self.assertRaises(ValueError):
                h.freeze_plan(changed,expected_sha256=h.digest(changed))

    def test_fault_and_human_epoch_change_keep_fence_without_replaying_old_state(self):
        changes=[lambda r:r['startup'].update(reads=62),lambda r:r['startup']['torque'].__setitem__(0,0),
            lambda r:r.update(forbidden_counts=list(h.FORBIDDEN)),lambda r:r['startup']['health'].__setitem__(0,True),
            lambda r:r['forbidden_counts'].update(arm=1),lambda r:r.update(native_unknown=True),
            lambda r:r.update(execution_busy=True),lambda r:r['samples'][0].update(end_ns=4*h.NS),
            lambda r:r['samples'][1]['torque'].__setitem__(3,True),
            lambda r:r['samples'][1]['positions'].__setitem__(0,float('nan')),
            lambda r:r['samples'][1]['head_pose'].update(roll=3.141592653589793),
            lambda r:r['samples'][1].update(fk_residual_rad=.003),lambda r:r['exit'].update(confirmed=False),
            lambda r:r['exit'].update(uart_owners=[self.s['factory']['uart_child']]),
            lambda r:r['candidate_runtime']['native_mappings'][1].update(sha256='f'*64)]
        for index,change in enumerate(changes):
            with self.subTest(index=index):
                result,current=receipt(self.s,self.plan);change(result)
                decision=h.assess_readonly(self.plan,result,current,now_ns=current['end_ns'])
                self.assertFalse(decision['accepted']);self.assertTrue(decision['keep_fence']);self.assertFalse(decision['automatic_restart'])
        result,current=receipt(self.s,self.plan);current['operator']['microphone_epoch']+=1
        self.assertFalse(h.assess_readonly(self.plan,result,current,now_ns=current['end_ns'])['accepted'])
        self.assertEqual(current['operator']['microphone_epoch'],self.s['operator']['microphone_epoch']+1)

    def test_no_arm_profile_digest_clock_and_original_begin_bounds_fail_closed(self):
        for key,value in (('wireless_version',True),('wireless_version',0),('wake_up_on_start',True),('goto_sleep_on_stop',True),('no_media',False),('hardware_config_filepath','/fixture/pid.json')):
            value_spec=copy.deepcopy(self.s);value_spec['candidate']['args'][key]=value
            with self.assertRaises(ValueError):h.freeze_plan(value_spec,expected_sha256=h.digest(value_spec))
        with self.assertRaises(ValueError):h.freeze_plan(self.s,expected_sha256='f'*64)
        observed=takeover(self.s,True)
        with self.assertRaises(ValueError):h.authorize_takeover(self.plan,observed,now_ns=observed['begin_ns']+h.NS//10,action='kill')
        observed['clock_domain']='wall_clock'
        with self.assertRaises(ValueError):h.authorize_takeover(self.plan,observed,now_ns=observed['end_ns'],action='kill')


if __name__=='__main__':unittest.main()
