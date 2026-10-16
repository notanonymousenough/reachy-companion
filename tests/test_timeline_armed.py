"""Offline exact7a5 local arming proposal; request stubs never touch hardware."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
from types import ModuleType
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('armed_builder',ROOT/'deploy/autonomous/prepare_timeline_armed.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def load(raw):
    module=ModuleType('reachy_companion.timeline_armed_fixture'); module.__package__='reachy_companion'
    exec(compile(raw,'exact-expression-proposal.py','exec'),module.__dict__)
    return module


class Clock:
    def __init__(self): self.value=0.
    def seconds(self): return self.value
    def __eq__(self,other): return True  # Gate must use identity, not equality.


def step():
    return dict(head_pose={key:0. for key in ('x','y','z','roll','pitch','yaw')},
                antennas=[0.,0.],duration=.5,interpolation='minjerk')


def until(predicate):
    end=time.monotonic()+1
    while not predicate() and time.monotonic()<end: time.sleep(.002)
    if not predicate(): raise AssertionError('Fixture did not reach the expected state')


class TimelineArmedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before,cls.after=builder.candidate(); cls.old=load(cls.before); cls.new=load(cls.after)

    def player(self,mode='local_armed',module=None,blocked=(0,),deny=False,binding_hook=None):
        config=json.loads((ROOT/'config.example.json').read_text())
        config['guarded_motion'].update(enabled=True,transport='stock')
        config['conversation']['expressions']['library']['repeat_processing']=False
        config['conversation']['expressions']['repeat_seconds']=1000
        if mode is None: config['conversation']['expressions'].pop('timeline_gate',None)
        else: config['conversation']['expressions']['timeline_gate']=mode
        state=dict(allowed=True,binding=dict(agent_boot_id='fixture',microphone_epoch=1,
            microphone_enabled=True,policy_epoch=2),actions=[],paths=[],violations=[],waiters=[])
        state['release']=[threading.Event() for _ in range(4)]
        state['entered']=[threading.Event() for _ in range(4)]
        stopping=threading.Event(); holder={}
        def binding():
            p=holder.get('player')
            if p is not None and p.condition._is_owned(): state['violations'].append('binding_under_condition')
            if binding_hook is not None: binding_hook(p,state)
            return dict(state['binding'])
        def request(base,path,payload,**kwargs):
            state['paths'].append(path)
            if path=='/expression/plan': return dict(steps=[step()])
            self.assertEqual(path,'/actions/expression')
            p=holder['player']; self.assertIs(threading.current_thread(),p.thread)
            index=len(state['actions']); state['actions'].append(copy.deepcopy(payload)); state['entered'][index].set()
            if index in blocked: self.assertTrue(state['release'][index].wait(1))
            if deny: raise RuntimeError('fixture rejected motion')
            return dict(ok=True)
        p=(module or self.new).ExpressionPlayer(config,request,stopping,
            permitted=lambda:state['allowed'],binding=binding)
        holder['player']=p
        def cleanup():
            stopping.set(); p.hold()
            for event in state['release']: event.set()
            p.thread.join(1)
            for waiter in state['waiters']: waiter.join(1)
            self.assertFalse(p.thread.is_alive())
            self.assertFalse(any(waiter.is_alive() for waiter in state['waiters']))
        self.addCleanup(cleanup)
        return p,state

    def wait(self,p,state,clock):
        result=dict(done=threading.Event(),errors=[])
        def run():
            try: p.wait_timeline(clock)
            except Exception as error: result['errors'].append(error)
            finally: result['done'].set()
        waiter=threading.Thread(target=run,daemon=True); state['waiters'].append(waiter); waiter.start()
        return result

    def queue(self,p,clock,at=0): p.timeline([dict(at=at,steps=[step()])],clock)

    def test_exact_public_preimage_and_exclusive_proposal_bundle(self):
        self.assertEqual(builder.digest(self.before),builder.BEFORE)
        self.assertEqual(builder.digest(self.after),builder.AFTER)
        self.assertEqual(builder.digest((ROOT/'src/reachy_companion/expression_player.py').read_bytes()),builder.BEFORE)
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'bundle'; manifest=builder.build(target)
            self.assertTrue(manifest['proposal']); self.assertEqual(manifest['default'],'completion')
            self.assertFalse(manifest['hardware_accepted']); self.assertFalse(manifest['antenna_targets_or_sdk_modified'])
            self.assertFalse(manifest['remote_admission_verified']); self.assertFalse(manifest['latency_improvement_verified'])
            with self.assertRaises(FileExistsError): builder.build(target)

    def test_default_and_explicit_fallback_wait_for_existing_completion_with_same_payload(self):
        results=[]
        for module,mode in ((self.old,None),(self.new,None),(self.new,'completion')):
            p,state=self.player(mode,module); clock=Clock(); self.queue(p,clock)
            self.assertTrue(state['entered'][0].wait(1))
            waited=self.wait(p,state,clock); self.assertFalse(waited['done'].wait(.05))
            state['release'][0].set(); self.assertTrue(waited['done'].wait(1))
            self.assertEqual(waited['errors'],[]); results.append((state['paths'],state['actions']))
        self.assertEqual(results[0],results[1]); self.assertEqual(results[0],results[2])

    def test_local_arm_releases_before_http_completion_but_is_not_admission(self):
        p,state=self.player(deny=True); clock=Clock(); self.queue(p,clock)
        self.assertTrue(state['entered'][0].wait(1)); version=p.version
        p.wait_timeline(clock)
        self.assertLess(p.completed,version); self.assertIsNone(p.last_expression)
        self.assertIs(p.timeline_armed[0],clock); self.assertEqual(p.timeline_armed[1],version)
        self.assertEqual(set(state['actions'][0]),{'steps','operator_binding'})
        state['release'][0].set(); until(lambda:p.completed>=version)
        self.assertIsNotNone(p.last_error); self.assertIsNone(p.last_expression)
        self.assertEqual(state['violations'],[])

    def test_positive_first_tick_arms_before_clock_advances_without_sending_early(self):
        p,state=self.player(); clock=Clock(); self.queue(p,clock,.25)
        waited=self.wait(p,state,clock); self.assertTrue(waited['done'].wait(1))
        self.assertEqual(waited['errors'],[]); self.assertEqual(state['actions'],[]); self.assertEqual(p.completed,0)
        clock.value=.25
        with p.condition: p.condition.notify_all()
        self.assertTrue(state['entered'][0].wait(1)); self.assertEqual(len(state['actions']),1)
        self.assertEqual(state['violations'],[])

    def test_prior_processing_completion_cannot_ack_new_ticket_before_scheduler_observes_it(self):
        entered=threading.Event(); allow=threading.Event(); blocking=[False]
        def hook(p,state):
            if p is not None and threading.current_thread() is p.thread and blocking[0]:
                entered.set(); self.assertTrue(allow.wait(1))
        p,state=self.player(blocked=(0,1),binding_hook=hook)
        p.set('processing'); self.assertTrue(state['entered'][0].wait(1))
        clock=Clock(); self.queue(p,clock); version=p.version
        waited=self.wait(p,state,clock); self.assertFalse(waited['done'].wait(.05))
        blocking[0]=True; state['release'][0].set(); self.assertTrue(entered.wait(1))
        self.assertLess(p.completed,version); self.assertFalse(waited['done'].wait(.05))
        allow.set(); self.assertTrue(waited['done'].wait(1)); self.assertEqual(waited['errors'],[])
        self.assertTrue(state['entered'][1].wait(1)); self.assertLess(p.completed,version)
        self.assertEqual(state['violations'],[])

    def test_hold_cancels_pending_ticket_and_old_completion_cannot_resurrect_it(self):
        p,state=self.player(); p.set('processing'); self.assertTrue(state['entered'][0].wait(1))
        clock=Clock(); self.queue(p,clock); waited=self.wait(p,state,clock)
        self.assertFalse(waited['done'].wait(.05)); p.hold()
        self.assertTrue(waited['done'].wait(1)); self.assertIsInstance(waited['errors'][0],RuntimeError)
        state['release'][0].set(); until(lambda:p.completed>=p.version)
        self.assertIsNone(p.timeline_armed); self.assertEqual(len(state['actions']),1)

    def test_new_clock_with_equal_value_cannot_release_old_clock_waiter(self):
        p,state=self.player(); p.set('processing'); self.assertTrue(state['entered'][0].wait(1))
        first,second=Clock(),Clock(); self.queue(p,first)
        old=self.wait(p,state,first); self.assertFalse(old['done'].wait(.05))
        self.queue(p,second,.25); self.assertTrue(old['done'].wait(1))
        self.assertIsInstance(old['errors'][0],RuntimeError)
        state['release'][0].set(); p.wait_timeline(second)
        self.assertIs(p.timeline_armed[0],second); self.assertEqual(len(state['actions']),1)

    def test_changed_binding_or_permission_rejects_already_armed_ticket(self):
        for field,value in (('agent_boot_id','new'),('microphone_epoch',2),('policy_epoch',3),('microphone_enabled',False)):
            p,state=self.player(); clock=Clock(); self.queue(p,clock,.25); p.wait_timeline(clock)
            state['binding'][field]=value
            with self.assertRaises(RuntimeError): p.wait_timeline(clock)
            self.assertEqual(state['actions'],[])
        p,state=self.player(); clock=Clock(); self.queue(p,clock,.25); p.wait_timeline(clock)
        state['allowed']=False
        # Existing disabled-motor/audio-only fallback returns without sending.
        p.wait_timeline(clock); self.assertEqual(state['actions'],[])

    def test_permission_withdrawal_while_waiting_is_cancellation_not_ready(self):
        p,state=self.player(); p.set('processing'); self.assertTrue(state['entered'][0].wait(1))
        clock=Clock(); self.queue(p,clock); waited=self.wait(p,state,clock)
        self.assertFalse(waited['done'].wait(.05)); state['allowed']=False
        with p.condition: p.condition.notify_all()
        self.assertTrue(waited['done'].wait(1)); self.assertIsInstance(waited['errors'][0],RuntimeError)
        self.assertIsNone(p.timeline_armed); self.assertEqual(len(state['actions']),1)

    def test_stop_rejects_previously_armed_future_tick(self):
        p,state=self.player(); clock=Clock(); self.queue(p,clock,.25); p.wait_timeline(clock)
        p.stopping.set()
        with self.assertRaises(RuntimeError): p.wait_timeline(clock)
        self.assertEqual(state['actions'],[])

    def test_bad_binding_and_motion_are_rejected_before_any_arming(self):
        p,state=self.player(); state['binding']['microphone_epoch']=True
        with self.assertRaises(RuntimeError): self.queue(p,Clock())
        self.assertIsNone(p.timeline_armed); self.assertEqual(state['actions'],[])
        state['binding']['microphone_epoch']=1
        bad=step(); bad['duration']=.01
        with self.assertRaises(ValueError): p.timeline([dict(at=0,steps=[bad])],Clock())
        self.assertIsNone(p.timeline_armed); self.assertEqual(state['actions'],[])

    def test_unknown_switch_and_missing_stock_binding_fail_before_thread_creation(self):
        config=json.loads((ROOT/'config.example.json').read_text())
        for mode in (True,None,'remote_admitted'):
            config['conversation']['expressions']['timeline_gate']=mode
            with self.assertRaises(ValueError): self.new.ExpressionPlayer(config,lambda *a:None,threading.Event())
        config['conversation']['expressions']['timeline_gate']='local_armed'
        with self.assertRaises(ValueError): self.new.ExpressionPlayer(config,lambda *a:None,threading.Event())


if __name__=='__main__': unittest.main()
