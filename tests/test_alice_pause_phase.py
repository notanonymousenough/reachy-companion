"""Existing cf50 pause semantics used by finite Alice tests; no device changes."""
import importlib.util
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock
from test_agent_live_latency_patch import load
from test_agent_stream_timing import AgentStreamTimingTests

ROOT=Path(__file__).resolve().parents[1]


class AlicePausePhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('alice_pause_cf50',ROOT/'deploy/autonomous/prepare_capture_pump.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        _,data=builder.candidate();cls.module=load(data['agent.py'].decode())

    def test_pause_during_real_voice_loop_does_not_cancel_or_drop_pcm(self):
        fixture=AgentStreamTimingTests();a=fixture.agent(self.module);seen=[]
        def policy():
            seen.append(True)
            if len(seen)>=2:a.listening.clear()
            return dict(epoch=6,motor_enabled=True,quiet=False,privacy_all=False)
        a.motion_policy.snapshot.side_effect=policy
        fixture.agent=lambda module:a
        _,result,order,writes,_=fixture.stream(module=self.module)
        self.assertTrue(result['ok']);self.assertFalse(result.get('cancelled',False))
        self.assertFalse(a.listening.is_set());self.assertIn('popen',order);self.assertTrue(writes)

    def test_paused_run_cannot_consume_pending_input_or_open_next_model(self):
        a=self.module.Agent.__new__(self.module.Agent)
        a.stopping=threading.Event();a.listening=Mock();a.audio_lock=threading.Lock()
        a.microphone=Mock(enabled=True);a.expressions=Mock();a.pending_pcm=(17,b'old-pending')
        a.request=Mock();a.capture=Mock();a.voice=Mock()
        def paused(timeout):a.stopping.set();return False
        a.listening.wait.side_effect=paused
        a.run()
        a.request.assert_not_called();a.capture.assert_not_called();a.voice.assert_not_called()
        self.assertEqual(a.pending_pcm,(17,b'old-pending'))  # Existing OFF retires it next.

    def test_mic_withdrawal_after_pause_still_cancels_before_aplay(self):
        fixture=AgentStreamTimingTests();a=fixture.agent(self.module);seen=[]
        def policy():
            seen.append(True)
            a.listening.clear()
            if len(seen)>=3:a.microphone.enabled=False
            return dict(epoch=6,motor_enabled=True,quiet=False,privacy_all=False)
        a.motion_policy.snapshot.side_effect=policy
        fixture.agent=lambda module:a
        _,result,order,writes,_=fixture.stream(module=self.module)
        self.assertTrue(result['cancelled']);self.assertNotIn('popen',order);self.assertEqual(writes,[])


if __name__=='__main__':unittest.main()
