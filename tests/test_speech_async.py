"""Scheduler keeps making progress while actual transport/backend slots stall."""
import threading
import time
import unittest
from pathlib import Path
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.playback import Playback,ReplayPCM
from reachy_companion.autonomous.speech_adapter import SpeechAdapter
from reachy_companion.autonomous.runtime import ReplayGateway,Scheduler


def wait(predicate,timeout=2):
    end=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>=end:raise AssertionError('Finite condition timeout')
        time.sleep(.002)


def actual(epoch=1):
    return dict(agent_boot_id='agent',microphone_epoch=epoch,microphone_enabled=True,
        motion_policy=dict(epoch=1,quiet=False,privacy_all=False))


class TTS:
    def stream(self,text,cancel):yield b'\0\0'*1000
    def cancel(self):pass


class SpeechAsyncTests(unittest.TestCase):
    def adapter(self,operator,backend=None,tts=None,motion=None):
        backend=backend or ReplayPCM()
        p=Playback(backend,allow_simulated=True,motion=motion,stop_timeout=.02)
        a=SpeechAdapter(p,tts or TTS(),operator);self.addCleanup(a.close)
        return a,p,backend

    def test_blocked_http_keeps_ticks_completions_and_ingestion_for_one_second(self):
        release=threading.Event();entered=threading.Event();calls=[]
        def operator():calls.append(1);entered.set();release.wait(2);return actual()
        a,p,b=self.adapter(operator)
        cfg=load(Path(__file__).resolve().parents[1]/'config.autonomous.example.json');cfg['period_s']=.01
        g=ReplayGateway(.01);s=Scheduler(cfg,g,speech_adapter=a)
        s.ingest(dict(type='operator',muted=False));s.ingest(dict(type='utterance',text='synthetic'))
        s.advance();self.assertTrue(entered.wait(1))
        start=time.monotonic();latencies=[]
        try:
            while time.monotonic()-start<1.05:
                began=time.monotonic();s.advance();latencies.append(time.monotonic()-began);time.sleep(.002)
            self.assertGreater(g.fast_calls,20)
            self.assertEqual(s.state.counts['task_started'],1)
            self.assertTrue(a.status()['operator_execution_busy']);self.assertEqual(len(calls),1)
            self.assertLess(max(latencies),.1);self.assertFalse(a.status()['operator_receipt_fresh'])
            self.assertFalse(b.streams)
            s.ingest(dict(type='operator',muted=True));s.advance()
            a.close();release.set();wait(lambda:not a.status()['operator_execution_busy'])
            self.assertGreaterEqual(a.status()['rejected_refreshes'],1);self.assertIsNone(a.binding)
        finally:release.set()

    def test_ttl_withdraws_audio_and_motion_with_one_blocked_refresh(self):
        release=threading.Event();entered=threading.Event();stopped=threading.Event();calls=[]
        def operator():
            calls.append(1)
            if len(calls)>1:entered.set();release.wait(2)
            return actual()
        class Motion:
            def stop(self):stopped.set();return True
        a,p,b=self.adapter(operator,motion=Motion());a.advance('epoch')
        wait(lambda:a.status()['operator_receipt_fresh'] and not p.status()['execution_busy'])
        a.execute(dict(authority='epoch',request_id='r',text='synthetic',deadline=time.monotonic()+2))
        wait(lambda:bool(b.streams) and next(iter(b.streams.values()))['written']>0)
        stream=b.current;stopped.clear();self.assertTrue(entered.wait(1))
        try:
            wait(lambda:b.streams[stream]['stopped'])
            self.assertTrue(stopped.wait(.2));self.assertFalse(a.status()['operator_receipt_fresh'])
            self.assertTrue(a.status()['operator_execution_busy']);self.assertEqual(len(calls),2)
            a.advance('new-epoch');a.close();release.set()
            wait(lambda:not a.status()['operator_execution_busy'])
            self.assertEqual(a.binding[1],1);self.assertFalse(a.status()['resumable'])
        finally:release.set()

    def test_slow_receipt_rejected_even_when_control_thread_has_not_polled_it(self):
        a,p,b=self.adapter(lambda:(time.sleep(.35),actual())[1]);a.advance('epoch')
        wait(lambda:a.status()['rejected_refreshes']>0)
        a.close();self.assertIsNone(a.binding);self.assertFalse(b.streams)

    def test_reserve_and_cancel_stalls_do_not_lock_scheduler_status_or_close(self):
        entered=threading.Event();release=threading.Event();cancel_entered=threading.Event();cancel_release=threading.Event()
        class Backend(ReplayPCM):
            def reserve(self,stream):entered.set();release.wait(2);super().reserve(stream)
        class SlowCancel(TTS):
            def cancel(self):cancel_entered.set();cancel_release.wait(2)
        a,p,b=self.adapter(lambda:actual(),Backend(),SlowCancel());a.advance('epoch')
        wait(lambda:a.status()['operator_receipt_fresh'] and not p.status()['execution_busy'])
        a.execute(dict(authority='epoch',request_id='r',text='synthetic',deadline=time.monotonic()+2))
        self.assertTrue(entered.wait(1))
        try:
            start=time.monotonic();a.advance('new');report=a.close()
            self.assertLess(time.monotonic()-start,.1)
            self.assertTrue(report['execution_busy']);self.assertTrue(cancel_entered.wait(.2))
            release.set();cancel_release.set()
            wait(lambda:not a.status()['execution_busy'])
            self.assertEqual(sum(v['written'] for v in b.streams.values()),0)
        finally:release.set();cancel_release.set()

    def test_actual_operator_epoch_invalidates_pending_model_completion(self):
        epoch=[1];release=threading.Event();entered=threading.Event()
        a,p,b=self.adapter(lambda:actual(epoch[0]))
        class Gateway(ReplayGateway):
            def main(self,task):entered.set();release.wait(2);return super().main(task)
        cfg=load(Path(__file__).resolve().parents[1]/'config.autonomous.example.json');cfg['period_s']=.01
        s=Scheduler(cfg,Gateway(.01),speech_adapter=a)
        def pump_until(predicate):
            end=time.monotonic()+2
            while not predicate():
                self.assertLess(time.monotonic(),end);s.advance();time.sleep(.002)
        try:
            pump_until(lambda:s.state.speech_operator_signature is not None and a.status()['operator_receipt_fresh'])
            s.ingest(dict(type='utterance',text='synthetic'));pump_until(entered.is_set)
            epoch[0]=2;pump_until(lambda:s.state.authority.microphone_epoch==2)
            release.set();pump_until(lambda:s.state.counts['task_result_stale']>0)
            self.assertFalse(b.streams)
        finally:release.set();a.close()


if __name__=='__main__':unittest.main()
