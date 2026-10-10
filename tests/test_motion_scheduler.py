import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.state import State
from reachy_companion.autonomous.gateway import fast_schema,fast_tuple_schema,tuple_choice
from reachy_companion.autonomous.runtime import Scheduler
from reachy_companion.autonomous.motion_adapter import MotionAdapter


def receipt():
    return dict(binding=dict(agent_boot_id='agent',operator_epoch=0,actor_boot_id='actor',session_id='session',motor_epoch=1),
        policy=dict(motor_enabled=True,quiet=False,privacy_all=False,epoch=1),microphone_enabled=False,
        motion_allowed=True,received=time.monotonic(),high_watermark=0)


class SchedulerMotionTests(unittest.TestCase):
    def config(self):
        cfg=load(Path(__file__).resolve().parents[1]/'config.autonomous.example.json');cfg['period_s']=.03;return cfg
    def test_muted_motion_proposal_requires_fresh_actor_and_policy_epoch(self):
        state=State(config=self.config());current=receipt();state.set_actor(current);now=time.monotonic()
        view=state.snapshot(now)
        self.assertFalse(view['op']['microphone_enabled']);self.assertTrue(view['op']['motion_allowed'])
        self.assertEqual(tuple_choice(['explore','attentive','gesture'],view)['motion'],'attentive')
        self.assertIn('attentive',str(fast_schema(view)));self.assertIn('attentive',str(fast_tuple_schema(view)))
        binding=state.bind(now,1)
        newer=receipt();newer['binding']['motor_epoch']=2;newer['policy']['epoch']=2;newer['policy']['quiet']=True
        newer['motion_allowed']=False;state.set_actor(newer)
        state.apply(dict(a='explore',why='old proposal',motion='attentive'),binding,time.monotonic())
        self.assertFalse(state.motion_proposals)
        with self.assertRaises(ValueError):tuple_choice(['explore','attentive','gesture'],state.snapshot(time.monotonic()))

    def test_scheduler_dispatches_model_proposal_only_through_adapter_while_muted(self):
        class Gateway:
            boot_id='compute'
            def fast(self,request_id,view):
                output=dict(a='explore',why='gesture',motion='attentive') if view['op']['motion_allowed'] else dict(a='wait',why='unavailable')
                return dict(request_id=request_id,compute_boot_id='compute',output=output)
        class Adapter:
            hub=SimpleNamespace(boot_id=None)
            receipts=[]
            def refresh(self):return receipt()
            def execute(self,proposal):
                self.receipts.append(dict(accepted=True,request_id=proposal['request_id']));return self.receipts[-1]
            def close(self):return True
        adapter=Adapter();scheduler=Scheduler(self.config(),Gateway(),adapter)
        deadline=time.monotonic()+1
        while time.monotonic()<deadline and not adapter.receipts:scheduler.advance();time.sleep(.002)
        self.assertTrue(adapter.receipts);self.assertTrue(scheduler.state.muted)
        self.assertEqual(scheduler.state.counts['motion_proposed'],1)
        self.assertEqual(scheduler.state.counts['simulated_speech'],0)
        self.assertEqual(adapter.hub.boot_id,scheduler.state.authority.hub_boot_id)

    def test_busy_operator_poll_invalidates_pending_model_without_serial_status(self):
        class Hub:
            def agent(self,path):
                self.asserted_path=path
                if path!='/operator':raise AssertionError('Busy poll must avoid native serial status')
                return dict(agent_boot_id='agent',microphone_epoch=0,microphone_enabled=False,
                    motion_policy=dict(motor_enabled=False,quiet=True,privacy_all=False,epoch=2))
        hub=Hub();adapter=MotionAdapter(hub);adapter.busy=True;adapter.cached=receipt()
        state=State(config=self.config());state.set_actor(adapter.cached)
        binding=state.bind(time.monotonic(),1)
        state.set_actor(adapter.refresh())
        state.apply(dict(a='explore',why='stale grant',motion='attentive'),binding,time.monotonic())
        self.assertEqual(hub.asserted_path,'/operator')
        self.assertFalse(state.motion_proposals)
        self.assertFalse(state.snapshot(time.monotonic())['op']['motion_allowed'])


if __name__=='__main__':unittest.main()
