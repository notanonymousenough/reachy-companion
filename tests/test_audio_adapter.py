import threading
import time
import unittest
from pathlib import Path
from reachy_companion.autonomous.audio_adapter import AudioAdapter
from reachy_companion.autonomous.runtime import ReplayGateway, Scheduler
from reachy_companion.autonomous.config import load


def operator(now, epoch=1, enabled=True):
    return dict(binding=('agent', epoch, 0), microphone_enabled=enabled,
                quiet=False, privacy_all=False, valid_until=now+.3)


class AudioTests(unittest.TestCase):
    def setup_adapter(self, callback, clock=time.monotonic):
        class STT:
            def transcribe(self, pcm):return callback(pcm)
        adapter=AudioAdapter(STT(), clock=clock)
        adapter.bind_source('capture', 0)
        self.addCleanup(adapter.close)
        return adapter

    def submit(self, adapter, seq=1, **kwargs):
        return adapter.submit(b'\0\0'*320, source_boot='capture', sequence=seq,
            captured_end=adapter.clock(), authority='authority', operator_binding=('agent',1,0), **kwargs)

    def poll(self, adapter, authority='authority', epoch=1, enabled=True):
        return adapter.advance(authority, operator(adapter.clock(), epoch, enabled))

    def drain(self, adapter):
        end=time.monotonic()+1
        while adapter.status()['execution_busy']:
            self.assertLess(time.monotonic(),end);time.sleep(.002)

    def test_fresh_result_has_unknown_identity_lineage_and_no_confirmation(self):
        adapter=self.setup_adapter(lambda pcm:'Четыре')
        self.poll(adapter);self.assertTrue(self.submit(adapter));self.poll(adapter);self.drain(adapter)
        event=self.poll(adapter)
        self.assertEqual(event['text'],'Четыре')
        self.assertEqual(event['audio']['lineage_id'],'capture:1')
        self.assertEqual(event['audio']['speaker_identity'],'unknown')
        self.assertFalse(event['audio']['confirmed'])

    def test_echo_duplicate_and_old_capture_do_not_dispatch(self):
        calls=[];adapter=self.setup_adapter(lambda pcm:calls.append(1) or 'echo')
        self.poll(adapter)
        self.assertFalse(self.submit(adapter, origin='owned_playback',echo_reference='stream'))
        self.assertFalse(self.submit(adapter))
        self.assertFalse(adapter.submit(b'\0\0',source_boot='capture',sequence=2,
            captured_end=adapter.clock()-.26,authority='authority',operator_binding=('agent',1,0)))
        self.poll(adapter);self.assertFalse(calls)
        self.assertEqual(adapter.status()['counts']['echo'],1)

    def test_stall_keeps_actual_slot_and_latest_only_pending(self):
        release=threading.Event();entered=threading.Event();calls=[]
        def stt(pcm):calls.append(1);entered.set();release.wait(2);return 'fixture'
        adapter=self.setup_adapter(stt);self.poll(adapter);self.submit(adapter);self.poll(adapter)
        self.assertTrue(entered.wait(1))
        try:
            self.submit(adapter,2);self.submit(adapter,3)
            start=time.monotonic();self.poll(adapter);self.assertLess(time.monotonic()-start,.1)
            self.assertEqual(len(calls),1);self.assertEqual(adapter.status()['counts']['overwritten'],1)
            adapter.close();self.assertTrue(adapter.status()['execution_busy'])
            release.set();self.drain(adapter)
            self.assertIsNone(self.poll(adapter));self.assertEqual(len(calls),1)
        finally:release.set()

    def test_deadline_epoch_source_and_shutdown_reject_late_result(self):
        for change in ('deadline','epoch','source','shutdown'):
            with self.subTest(change=change):
                release=threading.Event();entered=threading.Event();clock=[10.]
                def stt(pcm):entered.set();release.wait(2);return 'late'
                adapter=self.setup_adapter(stt, lambda:clock[0]);self.poll(adapter)
                self.submit(adapter);self.poll(adapter);self.assertTrue(entered.wait(1))
                try:
                    if change=='deadline':clock[0]+=2.01;self.poll(adapter)
                    elif change=='epoch':self.poll(adapter,epoch=2)
                    elif change=='source':adapter.bind_source('new-capture',1)
                    else:adapter.close()
                    release.set();self.drain(adapter)
                    self.assertIsNone(self.poll(adapter,epoch=2 if change=='epoch' else 1))
                    self.assertGreater(adapter.status()['counts']['stale'],0)
                finally:release.set()

    def test_rejected_owned_echo_advances_replay_fence_without_superseding_stop(self):
        release=threading.Event();entered=threading.Event();calls=[]
        def stt(pcm):calls.append(1);entered.set();release.wait(2);return 'стоп'
        adapter=self.setup_adapter(stt);self.poll(adapter);self.submit(adapter,1);self.poll(adapter)
        self.assertTrue(entered.wait(.5))
        try:
            self.assertFalse(self.submit(adapter,2,origin='owned_playback',echo_reference='actual-stream'))
            self.assertFalse(self.submit(adapter,2))
            self.assertTrue(adapter.status()['execution_busy']);self.assertEqual(calls,[1])
            release.set();self.drain(adapter)
            event=self.poll(adapter);self.assertEqual(event['text'],'стоп')
            self.assertEqual(event['audio']['sequence'],1);self.assertIsNone(self.poll(adapter))
            self.assertEqual(adapter.status()['last_sequence'],2)
            self.assertEqual(adapter.status()['latest_utterance_sequence'],1)
        finally:release.set()

    def test_latest_stop_survives_superseded_completion_without_epoch_change(self):
        for newest,withdraw in ((2,False),(3,False),(3,True)):
            with self.subTest(newest=newest,withdraw=withdraw):
                release=threading.Event();entered=threading.Event();calls=[]
                def stt(pcm):
                    sequence=int.from_bytes(pcm[:2],'little');calls.append(sequence)
                    if sequence==1:entered.set();release.wait(2);return 'obsolete request'
                    return 'замолчи'
                adapter=self.setup_adapter(stt)
                class Speech:
                    def operator_view(self):return operator(time.monotonic())
                    def advance(self,authority):pass
                    def interrupt(self,*args):pass
                    def execute(self,proposal):pass
                    def close(self):pass
                cfg=load(Path(__file__).resolve().parents[1]/'config.autonomous.example.json')
                scheduler=Scheduler(cfg,ReplayGateway(),speech_adapter=Speech(),audio_adapter=adapter)
                scheduler.advance();authority=scheduler.state.authority
                try:
                    for sequence in range(1,newest+1):
                        self.assertTrue(adapter.submit(sequence.to_bytes(2,'little')*320,source_boot='capture',sequence=sequence,
                            captured_end=time.monotonic(),authority=authority,operator_binding=('agent',1,0)))
                        if sequence==1:scheduler.advance();self.assertTrue(entered.wait(.5))
                    self.assertTrue(adapter.status()['execution_busy']);self.assertEqual(calls,[1])
                    if withdraw:scheduler.ingest(dict(type='operator',muted=True))
                    release.set();self.drain(adapter)
                    deadline=time.monotonic()+.5
                    while time.monotonic()<deadline:
                        scheduler.advance()
                        if scheduler.state.counts['audio_turn'] or withdraw:break
                        time.sleep(.002)
                    if withdraw:
                        self.assertEqual(calls,[1]);self.assertEqual(scheduler.state.counts['audio_turn'],0)
                    else:
                        self.assertEqual(calls,[1,newest]);self.assertEqual(scheduler.state.current_utterance,'замолчи')
                        self.assertEqual(scheduler.state.counts['audio_turn'],1)
                        self.assertEqual(scheduler.state.authority.interaction_epoch,authority.interaction_epoch+1)
                        for _ in range(5):scheduler.advance()
                        self.assertEqual(scheduler.state.counts['audio_turn'],1)
                finally:release.set();adapter.close();scheduler.close()

    def test_blocked_stt_does_not_stop_scheduler_ticks_or_operator_ingestion(self):
        release=threading.Event();entered=threading.Event()
        adapter=self.setup_adapter(lambda pcm:(entered.set(),release.wait(2),'fixture')[-1])
        class Speech:
            def operator_view(self):return operator(time.monotonic())
            def advance(self, authority):pass
            def interrupt(self, *args):pass
            def execute(self, proposal):pass
        cfg=load(Path(__file__).resolve().parents[1]/'config.autonomous.example.json');cfg['period_s']=.01
        gateway=ReplayGateway();scheduler=Scheduler(cfg,gateway,speech_adapter=Speech(),audio_adapter=adapter)
        scheduler.advance()
        adapter.submit(b'\0\0'*320,source_boot='capture',sequence=1,captured_end=time.monotonic(),
            authority=scheduler.state.authority,operator_binding=('agent',1,0))
        scheduler.advance();self.assertTrue(entered.wait(1))
        try:
            start=time.monotonic();latencies=[]
            while time.monotonic()-start<1.05:
                began=time.monotonic();scheduler.advance();latencies.append(time.monotonic()-began);time.sleep(.002)
            self.assertGreater(gateway.fast_calls,20);self.assertLess(max(latencies),.1)
            scheduler.ingest(dict(type='operator',muted=True));release.set();self.drain(adapter)
            scheduler.advance();self.assertEqual(scheduler.state.counts['audio_turn'],0)
        finally:release.set()


if __name__=='__main__':unittest.main()
