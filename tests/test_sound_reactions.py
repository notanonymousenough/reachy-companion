import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from reachy_companion.sound_monitor import SoundMonitor
from reachy_companion.expression_player import ExpressionPlayer
from reachy_companion.speech_clock import SpeechClock

class SoundReactionTests(unittest.TestCase):
    def test_wall_time_clock_never_claims_verified_resume_cursor(self):
        clock=SpeechClock(16000,0);clock.feed(3200)
        self.assertIsNone(clock.resume_cursor())
        clock.started=time.monotonic()-10
        self.assertEqual(clock.position(),3200)
        self.assertIsNone(clock.resume_cursor())
    def test_music_requires_two_windows_and_exits_after_three_nonmusic_windows(self):
        settings={'enabled':True,'window_seconds':3,'interval_seconds':1,'music_enter_windows':2,'music_exit_windows':3,'sound_cooldown_seconds':6}
        config={'conversation':{'sound_reactions':settings},'network':{'voice_url':'http://test'}}
        agent=SimpleNamespace(config=config,audio={'chunk_ms':100},microphone_epoch=0,microphone=SimpleNamespace(enabled=True),stopping=threading.Event(),phase='listening',expressions=Mock())
        replies=[];handled=threading.Event()
        def request(*args,**kwargs):
            result=replies.pop(0);handled.set();return result
        agent.request=request
        monitor=SoundMonitor(agent)
        self.addCleanup(agent.stopping.set)
        def send(kind):
            handled.clear();replies.append({'kind':kind,'steps':[],'beat_seconds':.5,'next_beat_seconds':.1})
            monitor.queue.put((0,b'pcm',time.monotonic()))
            deadline=time.monotonic()+1
            while time.monotonic()<deadline and replies:time.sleep(.01)
            time.sleep(.02)
        send('music');self.assertFalse(monitor.music)
        send('music');self.assertTrue(monitor.music);agent.expressions.dance.assert_called()
        send('speech');send('silence');self.assertTrue(monitor.music)
        send('silence');self.assertFalse(monitor.music)
        agent.microphone.enabled=False
        send('music');self.assertFalse(monitor.music)
        self.assertEqual(len(replies),1)  # muted windows never reach the PC

    def test_first_pose_finishes_before_audio_clock_and_hold_drops_future_cues(self):
        stop=threading.Event();calls=[]
        settings={'enabled':True,'max_total_seconds':3,'settle_seconds':.1,'speech_sync':{'max_cues':10},'repeat_seconds':2}
        config={'conversation':{'expressions':settings},'timeouts':{'http':1},'network':{'voice_url':'http://worker','hub_url':'http://hub'},'streaming':{'max_output_seconds':20}}
        def request(base,path,payload,**kwargs):
            calls.append(path);return {'steps':[]} if path=='/expression/plan' else {'ok':True}
        player=ExpressionPlayer(config,request,stop);self.addCleanup(stop.set)
        # Use valid conservative bounds for the real cue validator.
        settings.update(max_steps=3,max_head_degrees=12,max_antenna_degrees=30)
        step={'head_pose':dict(x=0.,y=0.,z=0.,roll=0.,pitch=0.,yaw=0.),'antennas':[0.,0.],'duration':.55,'interpolation':'minjerk'}
        clock=SpeechClock(16000)
        player.timeline([{'at':0.,'steps':[step]},{'at':10.,'steps':[step]}],clock)
        player.wait_timeline(clock)
        self.assertIn('/actions/expression',calls)
        self.assertIsNone(clock.started)
        player.hold();self.assertEqual(player.cues,[])
        self.assertIsNone(player.clock)
