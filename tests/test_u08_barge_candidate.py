"""Synthetic PCM/authority/concurrency only; not acoustic/AEC acceptance."""
import array
import math
import json
from pathlib import Path
import sys
import threading
import time
import types
import unittest
from unittest.mock import Mock,patch

try:
    import webrtcvad
except ImportError:
    sys.modules['webrtcvad']=types.SimpleNamespace(Vad=Mock())
from reachy_companion.agent import Agent
from reachy_companion.capture_pump import CapturePump
from reachy_companion.barge_candidate import BargeCandidate,waveform_match,REFERENCE_BYTES,REFERENCE_MARKS,own_text_veto


def pcm(frequency=213,amplitude=2000):
    return array.array('h',(int(amplitude*math.sin(2*math.pi*frequency*n/16000)) for n in range(1600))).tobytes()


class CandidateTests(unittest.TestCase):
    def fixture(self,clock=time.monotonic):
        a=Agent.__new__(Agent)
        a.audio=dict(sample_rate=16000,chunk_ms=100,vad_mode=2,min_speech_frames=3,
            pre_roll_chunks=5,calibration_chunks=10,rms_floor=500,noise_multiplier=1.8,
            silence_chunks=10,max_recording_seconds=25,min_voiced_chunks=4,echo_tail_seconds=.4)
        a.config=dict(conversation=dict(barge_in=dict(enabled=True,confirm_with_stt=True,threshold_multiplier=1.4,
            min_voiced_chunks=4,warmup_chunks=6),capture_pump_enabled=True),streaming=dict(enabled=True),
            network=dict(voice_url='http://no-network.invalid'))
        a.microphone_lock=threading.Lock();a.agent_boot_id='boot';a.microphone_epoch=1
        a.microphone=types.SimpleNamespace(enabled=True,error=None);a.microphone_owner_id=None
        a.listening=threading.Event();a.listening.set();a.stopping=threading.Event()
        policy=dict(epoch=2,motor_enabled=True,quiet=False,privacy_all=False)
        intent=dict(generation=3,listening_requested=True)
        mode=dict(generation=4,mode='normal',error=None)
        a.motion_policy=types.SimpleNamespace(lock=threading.RLock(),owner_id=None,snapshot=lambda:dict(policy))
        a.durable_intent=types.SimpleNamespace(lock=threading.RLock(),error=False,snapshot=lambda:dict(intent))
        a.conversation_mode=types.SimpleNamespace(lock=threading.RLock(),snapshot=lambda:dict(mode))
        a.initiative=types.SimpleNamespace(lock=threading.RLock())
        a.phase='speaking';a.threshold=1000.;a.vad_bytes=640;a.calibrated=True;a.interruptions=0
        a.pending_pcm=a.resume_audio=None;a.resume_blocked_reason=None;a.barge_in_error=None
        a.expressions=types.SimpleNamespace(hold=Mock());a.current_reply_text='Мой ответ о погоде.'
        player=types.SimpleNamespace(pid=99,poll=lambda:None,terminate=Mock())
        a.playback_process=player;a.request=Mock(return_value=dict(transcript='Расскажи про музыку',decision=dict(action='answer')))
        def final_mic(enabled,**kwargs):
            with a.microphone_lock,a.motion_policy.lock,a.initiative.lock,a.durable_intent.lock:
                kwargs['admission']()
        a.set_microphone=Mock(side_effect=final_mic)
        pump=CapturePump(a,5,clock=clock);a._capture_pump=pump
        candidate=BargeCandidate(a,pump,clock=clock,vad=types.SimpleNamespace(is_speech=lambda *args:True))
        a._capture_control=pump.candidate=candidate
        pump.output(True)
        self.addCleanup(candidate.cancel)
        return a,pump,candidate,policy,intent,mode,player

    def token(self,c):return (c.serial,c.generation,c.clock(),99)

    def test_default_off_requires_explicit_typed_opt_in(self):
        a,*_=self.fixture()
        self.assertFalse(a._barge_candidate_enabled())
        a.config['conversation']['barge_candidate_enabled']='true'
        with self.assertRaises(ValueError):a._barge_candidate_enabled()
        a.config['conversation']['barge_candidate_enabled']=True
        self.assertTrue(a._barge_candidate_enabled())

    def test_waveform_reference_tri_state_own_and_unrelated(self):
        own=pcm()
        self.assertGreater(waveform_match(own,own*2),.99)
        self.assertLess(waveform_match(pcm(719,8000),own*2),.2)
        self.assertIsNone(waveform_match(bytes(3200),own))
        self.assertIsNone(waveform_match(own,b''))

    def test_unaligned_unknown_never_submits_even_loud_speech(self):
        now=[100.];a,p,c,*_=self.fixture(lambda:now[0])
        for i in range(20):
            now[0]+=.1
            c._measure((pcm(719,12000),now[0],c.serial,c.generation))
        self.assertEqual(c.counts['stt_submitted'],0)
        self.assertEqual(c.counts['unknown'],20)
        a.request.assert_not_called()

    def test_continuing_writes_choose_only_reference_accepted_before_mic_receipt(self):
        now=[100.];a,p,c,*_=self.fixture(lambda:now[0])
        own=pcm();future=pcm(719,8000)
        for index in range(3):
            now[0]=100.+index*.1
            c.written(own,99,'a'*32,c.reference_end,16000)
            received=now[0]+.04
            selected_end=c.reference_end
            now[0]+=.06
            c.written(future,99,'a'*32,c.reference_end,16000)
            # Simulates delayed worker after the next actual playback write.
            with patch('reachy_companion.barge_candidate.waveform_match',wraps=waveform_match) as match:
                c._measure((own,received,c.serial,c.generation))
            self.assertTrue(match.called)
            self.assertTrue(match.call_args.args[1].endswith(own))
            self.assertEqual(c.metrics['selected_reference_end_byte'],selected_end)
            self.assertAlmostEqual(c.metrics['reference_receipt_age_s'],.04)
            self.assertGreater(c.metrics['correlation'],.99)
        self.assertEqual(c.own_matches,3)
        self.assertTrue(c.status()['calibrated_in_current_playback'])
        a.request.assert_not_called()

    def test_reference_receipt_history_is_bounded_and_eviction_abstains(self):
        now=[100.];a,p,c,*_=self.fixture(lambda:now[0])
        for index in range(REFERENCE_MARKS*3):
            now[0]+=.001
            c.written(pcm()[:2],99,None,c.reference_end,16000)
        self.assertLessEqual(len(c.reference_marks),REFERENCE_MARKS)
        self.assertLessEqual(len(c.reference),REFERENCE_BYTES)
        # Delayed input whose eligible mark has been evicted remains unknown.
        with c.condition:
            data,at,end=c.reference_before(100.001)
        self.assertEqual(data,b'');self.assertIsNone(at);self.assertIsNone(end)
        c.transition(p.playback_generation,False)
        self.assertEqual(c.status()['reference_history_entries'],0)
        self.assertEqual(c.own_matches,0)

    def test_own_only_calibrates_but_never_interrupts(self):
        now=[100.];a,p,c,*_=self.fixture(lambda:now[0])
        own=pcm()
        for i in range(15):
            c.written(own,99,'a'*32,c.reference_end,16000)
            now[0]+=.1;c._measure((own,now[0],c.serial,c.generation))
        self.assertGreaterEqual(c.own_matches,3)
        self.assertEqual(c.counts['stt_submitted'],0)
        self.assertFalse(c.interrupted.is_set())
        a.playback_process.terminate.assert_not_called()

    def test_calibrated_novel_stops_exact_player_without_replay(self):
        now=[100.];a,p,c,_,_,_,player=self.fixture(lambda:now[0])
        own=pcm()
        for i in range(7):
            c.written(own,99,'a'*32,c.reference_end,16000)
            now[0]+=.1;c._measure((own,now[0],c.serial,c.generation))
        for i in range(4):
            c.written(own,99,'a'*32,c.reference_end,16000)
            now[0]+=.1;c._measure((pcm(719,10000),now[0],c.serial,c.generation))
        self.assertEqual(c.counts['stt_submitted'],1)
        self.assertTrue(c.interrupted.is_set())
        self.assertEqual(a.interruptions,1)
        player.terminate.assert_called_once()
        self.assertIsNone(a.resume_audio);self.assertIsNone(a.pending_pcm)
        self.assertEqual(a.resume_blocked_reason,'candidate_output_resume_disabled')
        self.assertEqual(a.request.call_args.kwargs['timeout'],2.)

    def test_own_text_veto_also_precedes_stop_effect(self):
        a,p,c,*_=self.fixture()
        a.current_reply_text='Пожалуйста, скажи стоп.'
        a.request.return_value=dict(transcript='стоп',decision=dict(action='stop'))
        c._confirm(pcm(),self.token(c))
        a.set_microphone.assert_not_called()
        self.assertEqual(c.counts['text_veto'],1)
        self.assertFalse(c.interrupted.is_set())
        self.assertTrue(own_text_veto('СТОП','скажи стоп'))

    def test_post_stt_all_authority_and_generation_changes_abstain(self):
        changes=(lambda a,p,c,pol,iv,mode:setattr(a,'microphone_epoch',9),
            lambda a,p,c,pol,iv,mode:pol.update(privacy_all=True),
            lambda a,p,c,pol,iv,mode:pol.update(epoch=9),
            lambda a,p,c,pol,iv,mode:mode.update(generation=9),
            lambda a,p,c,pol,iv,mode:iv.update(generation=9),
            lambda a,p,c,pol,iv,mode:setattr(p,'playback_generation',9),
            lambda a,p,c,pol,iv,mode:setattr(a,'_capture_pump',None),
            lambda a,p,c,pol,iv,mode:c.cancel())
        for change in changes:
            with self.subTest(change=change):
                a,p,c,pol,iv,mode,_=self.fixture();token=self.token(c)
                def stt(*args,**kwargs):
                    change(a,p,c,pol,iv,mode)
                    return dict(transcript='Стоп сейчас',decision=dict(action='stop'))
                a.request.side_effect=stt
                c._confirm(pcm(),token)
                self.assertEqual(c.counts['stale_after_stt'],1)
                self.assertFalse(c.interrupted.is_set());a.playback_process.terminate.assert_not_called()
                # CAS method may be entered, but its final admission must fail.

    def test_actual_stop_uses_final_admission_and_epoch_cas(self):
        a,p,c,*_=self.fixture();token=self.token(c)
        def set_mic(enabled,**kwargs):
            self.assertFalse(enabled);self.assertEqual(kwargs['expected_epoch'],1)
            with a.microphone_lock,a.motion_policy.lock,a.initiative.lock,a.durable_intent.lock:
                kwargs['admission']()
        a.set_microphone.side_effect=set_mic
        a.request.return_value=dict(transcript='Стоп сейчас',decision=dict(action='stop'))
        c._confirm(pcm(),token)
        self.assertTrue(c.interrupted.is_set());self.assertEqual(a.interruptions,1)

    def test_ack_without_content_id_and_later_reply_keep_owned_player_reference(self):
        a,p,c,*_=self.fixture()
        c.written(pcm(),99,None,0,16000)
        c.written(pcm(),99,'a'*32,3200,16000)
        self.assertFalse(c.stop.is_set())
        self.assertEqual(c.reference_end,6400)

    def test_expired_confirmation_and_new_player_never_stop_any_output(self):
        for change in ('ttl','player'):
            with self.subTest(change=change):
                now=[100.];a,p,c,*_=self.fixture(lambda:now[0]);token=self.token(c)
                def stt(*args,**kwargs):
                    if change=='ttl':now[0]+=3
                    else:a.playback_process=types.SimpleNamespace(pid=100,poll=lambda:None,terminate=Mock())
                    return dict(transcript='Измени тему',decision=dict(action='answer'))
                a.request.side_effect=stt
                c._confirm(pcm(),token)
                self.assertFalse(c.interrupted.is_set())
                a.playback_process.terminate.assert_not_called()

    def test_actual_agent_stream_hooks_only_accepted_writes_and_reaps_worker(self):
        a,p,old,*_=self.fixture()
        a.config=type('C',(dict,),{'token':'unit-test-only'})(json.loads((Path(__file__).resolve().parents[1]/'config.example.json').read_text()))
        a.config['conversation'].update(capture_pump_enabled=True,barge_candidate_enabled=True)
        a.config['conversation']['barge_in'].update(enabled=True,confirm_with_stt=True)
        a.config['streaming'].update(enabled=True,sample_rate=16000)
        a.audio.update(echo_tail_seconds=0,playback_device='no-device')
        a.expressions.set=Mock();a._capture_get=lambda:p
        a.playback_process=None;a._capture_suspended=False
        a._capture_enabled=lambda:True
        events=[dict(type='reply',reply='Ответ.',content_attempt_id='a'*32),
                dict(type='audio',format='S16_LE',sample_rate=16000,channels=1,
                     pcm_base64=__import__('base64').b64encode(pcm()).decode()),dict(type='done',ok=True)]
        lines=[json.dumps(e).encode()+b'\n' for e in events]
        class Response:
            headers=types.SimpleNamespace(get_content_type=lambda:'application/x-ndjson')
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def readline(self,*args):return lines.pop(0) if lines else b''
        a.http=types.SimpleNamespace(open=lambda *args,**kwargs:Response())
        class Player:
            pid=99;returncode=None
            stdin=types.SimpleNamespace(fileno=lambda:123,close=lambda:None,closed=False)
            stderr=types.SimpleNamespace(close=lambda:None)
            def poll(self):return self.returncode
            def wait(self,**kwargs):self.returncode=0
            def terminate(self):self.returncode=-15
            def kill(self):self.returncode=-9
        class Selector:
            def register(self,*args):pass
            def select(self,**kwargs):return [True]
            def close(self):pass
        writes=[];original=BargeCandidate.written
        def written(c,data,*args):writes.append((data,args));return original(c,data,*args)
        with patch('reachy_companion.agent.subprocess.Popen',return_value=Player()) as popen, \
             patch('reachy_companion.agent.os.set_blocking'), \
             patch('reachy_companion.agent.os.write',side_effect=lambda fd,data:min(1600,len(data))), \
             patch('reachy_companion.agent.selectors.DefaultSelector',Selector), \
             patch.object(BargeCandidate,'written',written):
            result=a.voice('/text',dict(text='Вопрос'))
        self.assertTrue(result['ok'])
        self.assertEqual([len(data) for data,args in writes],[1600,1600])
        self.assertEqual([args[2] for data,args in writes],[0,1600])
        self.assertEqual(b''.join(data for data,args in writes),pcm())
        self.assertEqual(popen.call_count,1)
        self.assertEqual(popen.call_args.args[0][0],'aplay')
        self.assertFalse(p.candidate.thread.is_alive())
        self.assertEqual(p.candidate.status()['reference_bytes'],0)

    def test_reference_bounded_contiguous_and_invalid_write_disables(self):
        a,p,c,*_=self.fixture()
        for _ in range(40):c.written(pcm(),99,'a'*32,c.reference_end,16000)
        self.assertEqual(len(c.reference),REFERENCE_BYTES)
        c.written(pcm(),99,'a'*32,c.reference_end+2,16000)
        self.assertTrue(c.stop.is_set());self.assertEqual(c.failure,'reference_discontinuity')

    def test_reader_never_waits_for_stt_and_cancel_retains_busy_until_terminal(self):
        a,p,c,*_=self.fixture();entered=threading.Event();release=threading.Event()
        def stt(*args,**kwargs):
            entered.set();release.wait(2)
            return dict(transcript='Чужая фраза',decision=dict(action='answer'))
        a.request.side_effect=stt
        # Exercise the actual worker -> blocking confirmation while reader offers.
        c.own_matches=3;c.echo_rms=100;c.seen=7;c.novel_run=3
        c.written(pcm(),99,'a'*32,0,16000)
        with patch('reachy_companion.barge_candidate.waveform_match',return_value=0.):
            c.thread.start()
            try:
                p._publish(pcm(719,10000),time.monotonic())
                self.assertTrue(entered.wait(1))
                begin=time.monotonic()
                for _ in range(30):p._publish(pcm(719,10000),time.monotonic())
                self.assertLess(time.monotonic()-begin,.2)
                status=c.status()
                self.assertTrue(status['execution_busy']);self.assertLessEqual(status['pending'],1)
                self.assertGreater(status['counts']['replaced'],0)
                self.assertGreater(p.counters['suppressed_frames'],0)
                self.assertEqual(p.assembler.frames,[])
                c.cancel();self.assertTrue(c.thread.is_alive());self.assertTrue(c.status()['execution_busy'])
            finally:release.set();c.finish()
        self.assertFalse(c.thread.is_alive());self.assertFalse(c.interrupted.is_set())
        a.playback_process.terminate.assert_not_called()


if __name__=='__main__':unittest.main()
