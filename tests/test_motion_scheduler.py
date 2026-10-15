import time
import threading
import unittest
from unittest.mock import patch
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
    def test_run_exception_withdraws_owner_but_keeps_actual_motion_job_occupied(self):
        entered=threading.Event();release=threading.Event();failure=RuntimeError('fixture loop failure')
        class Gateway:
            boot_id='compute'
            def fast(self,request_id,view):
                output=dict(a='explore',why='fixture',motion='attentive') if view['op']['motion_allowed'] else dict(a='wait',why='unavailable')
                return dict(request_id=request_id,compute_boot_id=self.boot_id,output=output)
        class Adapter:
            def __init__(self):self.hub=SimpleNamespace(boot_id=None);self.closed=False;self.close_calls=0
            def refresh(self):return receipt()
            def execute(self,proposal):
                entered.set();release.wait(2)
                return dict(accepted=False,request_id=proposal['request_id'])
            def close(self):self.closed=True;self.close_calls+=1;return False
        adapter=Adapter();scheduler=Scheduler(self.config(),Gateway(),adapter);advance=scheduler.advance
        def fail_after_dispatch(now=None):
            advance(now)
            if entered.is_set():raise failure
        try:
            with patch.object(scheduler,'advance',side_effect=fail_after_dispatch):
                with self.assertRaises(RuntimeError) as caught:scheduler.run(1)
            self.assertIs(caught.exception,failure);self.assertTrue(scheduler.closed);self.assertTrue(adapter.closed)
            self.assertEqual(adapter.close_calls,1);self.assertIsNotNone(scheduler.motion_job)
            self.assertFalse(scheduler.motion_job.future.done())
            scheduler.ingest(dict(type='utterance',text='late fixture input'));self.assertFalse(scheduler.state.candidates)
        finally:
            release.set()
            if scheduler.motion_job:scheduler.motion_job.thread.join(1)

    def test_interrupt_closes_motion_even_when_another_adapter_close_fails(self):
        class Speech:
            def close(self):raise RuntimeError('fixture close failure')
        class Adapter:
            hub=SimpleNamespace(boot_id=None)
            closed=False
            def close(self):self.closed=True;raise OSError('fixture motion close failure')
        from reachy_companion.autonomous.runtime import ReplayGateway
        adapter=Adapter();scheduler=Scheduler(self.config(),ReplayGateway(),adapter,Speech())
        with patch.object(scheduler,'advance',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt) as caught:scheduler.run(1)
        self.assertTrue(any('RuntimeError' in note for note in caught.exception.__notes__))
        self.assertTrue(any('OSError' in note for note in caught.exception.__notes__))
        self.assertTrue(scheduler.closed);self.assertTrue(adapter.closed)

    def test_all_close_failures_attempted_and_first_exception_preserved(self):
        from reachy_companion.autonomous.runtime import ReplayGateway
        calls=[];first=RuntimeError('fixture revoke failure');second=ValueError('fixture speech failure')
        class Speech:
            def close(self):calls.append('speech');raise second
        class Audio:
            closed=False
            def close(self):self.closed=True;calls.append('audio');raise OSError('fixture audio failure')
        audio=Audio();scheduler=Scheduler(self.config(),ReplayGateway(),speech_adapter=Speech(),audio_adapter=audio)
        def revoke(*args):calls.append('context');raise first
        with patch.object(scheduler,'revoke_context',side_effect=revoke):
            with self.assertRaises(RuntimeError) as caught:scheduler.close()
        self.assertIs(caught.exception,first);self.assertEqual(calls,['context','speech','audio'])
        self.assertTrue(scheduler.closed);self.assertTrue(audio.closed);self.assertEqual(len(first.__notes__),2)
        scheduler.close();self.assertEqual(len(calls),3)

    def test_failing_speech_close_withdraws_real_audio_adapter_without_releasing_held_stt(self):
        from reachy_companion.autonomous.runtime import ReplayGateway
        from reachy_companion.autonomous.audio_adapter import AudioAdapter
        entered=threading.Event();release=threading.Event();revoked=threading.Event()
        class STT:
            def transcribe(self,pcm):entered.set();release.wait(2);return 'late fixture transcript'
        class Speech:
            def close(self):raise RuntimeError('fixture speech close failure')
        class Gateway(ReplayGateway):
            def revoke_context(self,authority,terminal=False):
                revoked.set();release.wait(2);return dict(revoked=True,terminal=terminal)
        cfg=self.config();cfg['context']['enabled']=True
        audio=AudioAdapter(STT());scheduler=Scheduler(cfg,Gateway(),speech_adapter=Speech(),audio_adapter=audio)
        authority=scheduler.state.authority
        operator=dict(binding=('fixture-agent',1,1),microphone_enabled=True,quiet=False,privacy_all=False,valid_until=time.monotonic()+1)
        try:
            audio.bind_source('fixture-source',0);audio.advance(authority,operator)
            self.assertTrue(audio.submit(b'\x00\x00'*160,source_boot='fixture-source',sequence=1,captured_end=time.monotonic(),authority=authority,operator_binding=operator['binding']))
            audio.advance(authority,operator);self.assertTrue(entered.wait(1));job=audio.job
            with self.assertRaisesRegex(RuntimeError,'fixture speech close failure'):scheduler.close()
            self.assertTrue(revoked.wait(1));self.assertFalse(scheduler.context_terminal_job.future.done())
            self.assertTrue(audio.closed);self.assertIs(audio.job,job);self.assertTrue(audio.status()['execution_busy'])
            self.assertFalse(audio.submit(b'\x00\x00',source_boot='fixture-source',sequence=2,captured_end=time.monotonic(),authority=authority,operator_binding=operator['binding']))
            release.set();job.join(1);self.assertIsNone(audio.advance(authority,operator));self.assertIsNone(audio.result)
            self.assertFalse(audio.status()['execution_busy'])
        finally:
            release.set();audio.close()
            if scheduler.context_terminal_job:scheduler.context_terminal_job.thread.join(1)

    def test_initial_event_iterator_failure_also_closes_constructed_owner(self):
        class Events:
            def __iter__(self):raise ValueError('fixture event startup failure')
        class Adapter:
            hub=SimpleNamespace(boot_id=None)
            closed=False
            def close(self):self.closed=True;return False
        from reachy_companion.autonomous.runtime import ReplayGateway
        adapter=Adapter();scheduler=Scheduler(self.config(),ReplayGateway(),adapter)
        with self.assertRaisesRegex(ValueError,'fixture event startup failure'):scheduler.run(1,Events())
        self.assertTrue(scheduler.closed);self.assertTrue(adapter.closed)

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
