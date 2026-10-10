import threading,time,unittest
from reachy_companion.autonomous.playback import Playback,ReplayPCM
from reachy_companion.autonomous.speech_adapter import SpeechAdapter
from reachy_companion.autonomous.motion_adapter import MotionAdapter


def wait(check):
    end=time.monotonic()+1
    while not check():
        if time.monotonic()>end:raise AssertionError('Bounded condition timeout')
        time.sleep(.002)


class PlaybackTests(unittest.TestCase):
    def make(self,backend=None,**kwargs):
        self.now=0.;b=backend or ReplayPCM();p=Playback(b,clock=lambda:self.now,allow_simulated=True,**kwargs)
        p.operator(('owner',1),microphone_enabled=True,valid_until=100)
        self.addCleanup(p.close);return p,b
    def buffer(self,p,b):
        stream=p.begin(('owner',1),'request',deadline=60);p.push(stream,b'\0\0'*100);p.finish(stream)
        wait(lambda:b.streams[stream]['written']==100);b.advance(stream,40);return stream
    def test_verified_frozen_cursor_and_confirmed_three_second_resume(self):
        p,b=self.make();stream=self.buffer(p,b);p.interrupt()
        wait(lambda:not p.status()['execution_busy']);self.assertTrue(p.status()['resumable'])
        self.now=3;self.assertIsNone(p.resume())
        self.assertFalse(p.confirm_no_utterance(since=0,until=float('nan'),authority=('owner',1)))
        self.assertTrue(p.confirm_no_utterance(since=0,until=3,authority=('owner',1)))
        resumed=p.resume();wait(lambda:b.streams[resumed]['written']==60)
        b.advance(resumed,60);wait(lambda:not p.status()['execution_busy'])
        self.assertTrue(p.status()['stop_known']);self.assertEqual(len(b.streams),2)
    def test_echo_is_not_human_and_epoch_withdrawal_discards_resume(self):
        p,b=self.make();stream=self.buffer(p,b)
        p.interrupt('echo');self.assertFalse(b.streams[stream]['stopped'])
        p.interrupt();wait(lambda:not p.status()['execution_busy'])
        p.operator(('owner',2),microphone_enabled=False)
        self.now=4;self.assertFalse(p.status()['resumable']);self.assertIsNone(p.resume())
        self.assertFalse(p.push(stream,b'\0\0'))
    def test_wall_time_cursor_never_authorizes_resume(self):
        class Unverified(ReplayPCM):
            def progress(self,stream):return dict(stream_id=stream,verified=False,consumed_frames=0,provenance='wall_time_estimate')
        p,b=self.make(Unverified());p.begin(('owner',1),'request',deadline=60)
        wait(lambda:p.status()['quarantined']);self.assertFalse(p.status()['resumable'])
    def test_stop_without_frozen_cursor_disables_resume(self):
        class NoCursor(ReplayPCM):
            def stop(self,stream):
                r=super().stop(stream);r['verified']=False;return r
        p,b=self.make(NoCursor());self.buffer(p,b);p.interrupt()
        self.assertTrue(p.status()['stop_known']);self.assertFalse(p.status()['resumable'])
    def test_delayed_start_cannot_write_after_shutdown(self):
        entered=threading.Event();release=threading.Event()
        class Delayed(ReplayPCM):
            def start(self,stream,rate):entered.set();release.wait(1);super().start(stream,rate)
        p,b=self.make(Delayed());stream=p.begin(('owner',1),'request',deadline=60);p.push(stream,b'\0\0'*100)
        self.assertTrue(entered.wait(1));r=p.close();self.assertTrue(r['execution_busy'])
        release.set();wait(lambda:not p.status()['execution_busy'])
        self.assertEqual(b.streams[stream]['written'],0)
    def test_stalled_audio_stop_does_not_delay_motion_stop_or_claim_drained(self):
        release=threading.Event();called=threading.Event()
        class Stalled(ReplayPCM):
            def stop(self,stream):release.wait(1);return super().stop(stream)
        class Motion:
            def stop(self):called.set();return True
        p,b=self.make(Stalled(),stop_timeout=.02,motion=Motion());self.buffer(p,b)
        began=time.monotonic();r=p.interrupt();self.assertLess(time.monotonic()-began,.2)
        self.assertTrue(called.is_set());self.assertTrue(r['execution_busy']);self.assertFalse(r['stop_known'])
        self.assertTrue(r['quarantined']);release.set();wait(lambda:not p.status()['execution_busy'])
    def test_repeated_interrupts_keep_only_one_stalled_backend_stop(self):
        release=threading.Event();calls=[]
        class Stalled(ReplayPCM):
            def stop(self,stream):calls.append(stream);release.wait(1);return super().stop(stream)
        p,b=self.make(Stalled(),stop_timeout=.01);self.buffer(p,b);p.interrupt()
        for _ in range(50):p.interrupt('operator',preserve=False)
        self.assertEqual(len(calls),1);self.assertLessEqual(len(p.stop_jobs),1)
        self.assertLessEqual(len(p.timeline),64);release.set();wait(lambda:not p.status()['execution_busy'])

    def test_expired_operator_policy_stops_without_timer_resume(self):
        p,b=self.make();stream=self.buffer(p,b);self.now=101
        wait(lambda:not p.status()['execution_busy']);self.assertTrue(b.streams[stream]['stopped'])
        self.assertIsNone(p.resume())
    def test_delayed_cancelled_tts_chunks_are_rejected(self):
        entered=threading.Event();release=threading.Event()
        class TTS:
            def stream(self,text,cancel):entered.set();release.wait(1);yield b'\0\0'*10
            def cancel(self):pass
        b=ReplayPCM();p=Playback(b,allow_simulated=True)
        a=SpeechAdapter(p,TTS(),lambda:dict(agent_boot_id='agent',microphone_epoch=1,microphone_enabled=True,motion_policy=dict(epoch=1,quiet=False,privacy_all=False)))
        a.execute(dict(authority='epoch',request_id='request',text='synthetic',deadline=time.monotonic()+2))
        self.assertTrue(entered.wait(1));s=a.close();self.assertTrue(s['tts_execution_busy']);release.set()
        wait(lambda:not a.status()['tts_execution_busy']);self.assertEqual(sum(v['written'] for v in b.streams.values()),0)


class MotionClosingTests(unittest.TestCase):
    def test_shutdown_during_pending_arm_reports_unknown_and_never_sends_trajectory(self):
        entered=threading.Event();release=threading.Event();calls=[]
        binding=dict(agent_boot_id='agent',operator_epoch=0,actor_boot_id='actor',session_id='session',motor_epoch=1)
        class Hub:
            boot_id='hub'
            def agent(self,path):return dict(agent_boot_id='agent',microphone_epoch=0,motion_actor=dict(actor_boot_id='actor',session_id='session',policy=dict(epoch=1,motor_enabled=True,quiet=False,privacy_all=False),ready=True,command_high_watermark=0))
            def native_motion(self,value,**extra):
                calls.append(value['kind'])
                if value['kind']=='arm':entered.set();release.wait(1);return dict(lease_id='lease')
                if value['kind']=='revoke':return dict(verified_stopped=True)
                raise AssertionError('Late trajectory forbidden')
        a=MotionAdapter(Hub());t=threading.Thread(target=a.execute,args=(dict(request_id='r',deadline=time.monotonic()+2,motion='attentive',actual_binding=binding),));t.start()
        self.assertTrue(entered.wait(1));self.assertFalse(a.close());self.assertTrue(a.status()['execution_busy'])
        release.set();t.join(1);self.assertFalse(t.is_alive());self.assertEqual(calls,['arm','revoke']);self.assertTrue(a.status()['stop_known'])

if __name__=='__main__':unittest.main()
