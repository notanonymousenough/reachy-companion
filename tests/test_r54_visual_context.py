"""R54 synthetic integration only: no camera, model, sound device or motors."""
import threading
import time
import unittest
from unittest.mock import patch

from tests.test_r53_sensory_bridge import Fixture
from tests.test_conversation_mode import ConversationModeTests
from tests.test_semantic_observer import frame
from reachy_companion.r42.semantic_observer import semantic_result
from reachy_companion.r42.sensory_bridge import SensoryBridge


class VisualIntegration(unittest.TestCase):
    def agent(self):
        a=Fixture()
        self.addCleanup(a.close)
        return a

    def test_disabled_sound_decisions_keep_real_source_observations(self):
        a=self.agent();b=a.sensory
        b.sound_decisions_enabled=False
        ticket=b.ticket()
        observation=b.observe_sound(dict(kind='sound',top_class=67),a.microphone_epoch,time.monotonic(),.5,ticket)
        self.assertIsNotNone(observation)
        with patch('reachy_companion.r42.sensory_bridge.http.client.HTTPConnection',side_effect=AssertionError('no model')):
            result=b.decide(b.loop.snapshot(),threading.Event())
        self.assertEqual(result['action'],'wait')
        self.assertFalse(b.status()['sound_decisions_enabled'])
        self.assertFalse(b.model_active)

    def test_camera_opt_in_is_explicit_and_does_not_reset_sound_fallback(self):
        a=self.agent()
        self.assertIsNone(a.sensory.camera)
        a.config['conversation']['sensory_loop'].update(camera_enabled=True,sound_decisions_enabled=False)
        b=SensoryBridge(a,start=False)
        self.addCleanup(b.loop.close);self.addCleanup(b.camera.close)
        self.assertIsNotNone(b.camera)
        self.assertFalse(b.sound_decisions_enabled)
        self.assertEqual((b.camera.ttl,b.camera.timeout),(30,24))

    def test_camera_admission_ignores_known_terminal_sound_fault_but_not_busy(self):
        a=self.agent();b=a.sensory;b.camera_enabled=True
        b.model_failure_latched=True
        self.assertTrue(b.camera_model_available())
        self.assertTrue(b.camera_slot_active)
        self.assertFalse(b.camera_model_available())
        b.camera_model_finished(False)
        b.model_unknown=True
        self.assertFalse(b.camera_model_available())
        b.model_unknown=False;b.model_active=True
        self.assertFalse(b.camera_model_available())
        b.model_active=False;a.phase='processing'
        self.assertFalse(b.camera_model_available())

    def test_foreground_does_not_wait_for_camera_and_unknown_blocks_only_background(self):
        a=self.agent();b=a.sensory;b.camera_enabled=True
        self.assertTrue(b.camera_model_available())
        with b.foreground_model():
            self.assertTrue(b.foreground_active)
            self.assertTrue(b.camera_slot_active)
            self.assertFalse(b.camera_model_available())
        self.assertFalse(b.foreground_active)
        b.camera_model_finished(True)
        self.assertTrue(b.camera_slot_unknown)
        self.assertFalse(b.camera_model_available())
        with b.foreground_model():
            self.assertTrue(b.foreground_active)
        self.assertIsNone(b.model_owner)

    def test_voice_dispatch_uses_one_current_snapshot_and_drops_stale_caller_data(self):
        fixture=ConversationModeTests();fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        a=fixture.agent()
        a.config['conversation']['sensory_loop']=dict(enabled=True,camera_enabled=True,sound_decisions_enabled=False)
        b=a.sensory=SensoryBridge(a,start=False)
        self.addCleanup(b.loop.close);self.addCleanup(b.camera.close)
        binding,enabled,private=b.camera_authority()
        b.visual_cache.install(semantic_result(frame(), 'На столе синяя чашка.',time.monotonic()),binding)
        a.voice('/text',dict(text='Что видно?',visual_context={'summary':'untrusted caller override'}))
        payload=a.request.call_args.args[2]
        self.assertEqual(payload['visual_context']['summary'],'На столе синяя чашка.')
        self.assertEqual(len(payload['visual_context']['frame_id']),32)
        self.assertTrue(payload['visual_context']['exposure_age_unknown'])
        self.assertEqual(payload['conversation_mode'],'alice_test')
        a.microphone_epoch+=1
        a.voice('/text',dict(text='Что видно?',visual_context={'summary':'stale'}))
        self.assertNotIn('visual_context',a.request.call_args.args[2])

    def test_new_pcm_withdraws_actions_but_keeps_cache_and_submitted_caption(self):
        a=self.agent();b=a.sensory;b.camera_enabled=True
        from types import SimpleNamespace
        from concurrent.futures import Future
        b.camera=SimpleNamespace(cancel=threading.Event(),future=Future())
        b.camera_slot_active=True
        b.visual_cache.install(semantic_result(frame(),'Чашка.',time.monotonic()),b.camera_authority()[0])
        a._sensory_withdraw(preserve_visual=True)
        self.assertFalse(b.camera.cancel.is_set())
        self.assertFalse(b.camera.future.done())
        self.assertTrue(b.camera_slot_active)
        self.assertEqual(b.visual_context()['summary'],'Чашка.')
        # Actual privacy, rather than unrelated output cancellation, fences cache.
        a.policy['privacy_all']=True
        a._sensory_withdraw()
        self.assertIsNone(b.visual_context())

    def test_privacy_clears_at_read_and_observer_withdraws_without_control_lock_reentry(self):
        from reachy_companion.r42.semantic_observer import SemanticObserver
        a=self.agent();b=a.sensory;b.camera_enabled=True
        release=threading.Event()
        b.camera=SemanticObserver(a.config,b.camera_authority,b.loop.publish,
            model_available=b.camera_model_available,
            runner=lambda *args,**kwargs: (release.wait(1) or {}) )
        self.addCleanup(release.set);self.addCleanup(b.camera.close)
        b.visual_cache.install(semantic_result(frame(),'Чашка.',time.monotonic()),b.camera_authority()[0])
        b.camera.advance()
        returned=threading.Event()
        with a.microphone_lock:
            a.policy['privacy_all']=True
            thread=threading.Thread(target=lambda: (b.invalidate(),returned.set()),daemon=True)
            thread.start()
            returned_without_reentry=returned.wait(.2)
        thread.join(1)
        self.assertTrue(returned_without_reentry)
        self.assertIsNone(b.visual_context())
        b.camera.advance()
        self.assertTrue(b.camera.cancel.is_set())
        self.assertIsNotNone(b.camera.future)

    def test_manual_capture_pause_keeps_current_caption_but_durable_OFF_does_not(self):
        a=self.agent();b=a.sensory;b.camera_enabled=True
        b.visual_cache.install(semantic_result(frame(),'Чашка.',time.monotonic()),b.camera_authority()[0])
        a.listening.clear()
        b.invalidate()
        self.assertEqual(b.visual_context()['summary'],'Чашка.')
        a.intent['listening_requested']=False
        self.assertIsNone(b.visual_context())
