"""Finite trial queue/authority tests; no hardware or synthetic acoustic claims."""
import copy
import types
import unittest
from unittest.mock import Mock
import test_u08_barge_candidate as candidate_fixture
from reachy_companion.barge_trial import BargeTrial,EitherEvent,TEXT

class TrialTests(unittest.TestCase):
    def setUp(self):
        self.now=[100.]
        fixture=candidate_fixture.CandidateTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.a,self.p,self.c,self.policy,self.intent,self.mode,self.player=fixture.fixture(lambda:self.now[0])
        a=self.a;a.phase='listening';a.capture_active=True;a.playback_process=None;a.voice_response=None
        a.config['conversation'].update(barge_candidate_enabled=True,barge_trial_enabled=True,session='qa')
        a.calibrated=True;a.sounds=types.SimpleNamespace(music=False)
        self.p.output(False);self.p.counters['last_read_monotonic']=self.now[0]
        self.p.thread=types.SimpleNamespace(is_alive=lambda:True)
        a.audio_lock=types.SimpleNamespace(locked=lambda:True)
        self.trial=a.barge_trial=BargeTrial(a,clock=lambda:self.now[0])
        self.binding=dict(agent_boot_id='boot',microphone_epoch=1,policy_epoch=2,intent_generation=3,
            mode_generation=4,source_generation=5,expires_at_monotonic=144.)
        self.measurement=dict(reference_player_pid=99,playback_generation=1,own_matches=3,
            counts=dict(accepted=0),metrics=dict(correlation=.9),accepted_reference_end_byte=32000)
        def voice(path,payload,**kw):
            self.assertEqual(path,'/say');self.assertEqual(payload['text'],TEXT)
            self.assertTrue(a.listening.is_set());self.assertTrue(a.capture_active)
            self.assertTrue(kw['allow_barge_in']);self.assertTrue(kw['manual_authority']())
            self.trial.observe(types.SimpleNamespace(status=lambda:copy.deepcopy(self.measurement)))
            return dict(ok=True)
        a.voice=Mock(side_effect=voice)

    def submit(self,case='own_only',**changes):
        binding={**self.binding,**changes}
        return self.trial.submit(dict(case=case,binding=binding))

    def test_trial_only_keeps_ordinary_and_pending_barge_OFF_then_scopes_to_running(self):
        self.assertTrue(self.a._barge_candidate_enabled())  # Absent flag preserves existing opt-in.
        self.a.config['conversation']['barge_candidate_trial_only']=True
        self.assertFalse(self.a._barge_candidate_enabled());self.assertTrue(self.trial.configured())
        self.submit();self.assertFalse(self.a._barge_candidate_enabled())
        original=self.a.voice.side_effect
        def voice(*args,**kwargs):
            self.assertTrue(self.a._barge_candidate_enabled())
            return original(*args,**kwargs)
        self.a.voice.side_effect=voice;self.trial.consume()
        self.assertFalse(self.a._barge_candidate_enabled());self.assertIsNone(self.trial.running)

    def test_trial_only_cancel_and_expired_TTL_disable_running_candidate(self):
        for withdrawal in ('cancel','expiry'):
            with self.subTest(withdrawal=withdrawal):
                self.setUp();self.a.config['conversation']['barge_candidate_trial_only']=True;self.submit()
                def voice(*args,**kwargs):
                    self.assertTrue(self.a._barge_candidate_enabled())
                    if withdrawal=='cancel':self.trial.cancel()
                    else:self.now[0]=145.
                    self.assertFalse(self.a._barge_candidate_enabled())
                    return dict(ok=True,cancelled=True)
                self.a.voice.side_effect=voice;self.trial.consume()
                self.assertFalse(self.a._barge_candidate_enabled())
                self.assertEqual(self.trial.snapshot()['last']['outcome'],'WITHDRAWN')

    def test_post_STT_effect_after_trial_TTL_abstains_with_otherwise_fresh_candidate(self):
        self.a.config['conversation']['barge_candidate_trial_only']=True;self.submit()
        def voice(*args,**kwargs):
            self.p.output(True);self.a.playback_process=self.player
            token=(self.c.serial,self.c.generation,143.,99)
            self.now[0]=144.1  # Trial expired; candidate receipt itself is still <2.5s old.
            for action in ('answer','stop'):
                self.assertFalse(self.a.barge_candidate_effect(self.c,token,action))
            self.assertFalse(self.c.interrupted.is_set());self.player.terminate.assert_not_called()
            return dict(ok=True,cancelled=True)
        self.a.voice.side_effect=voice;self.trial.consume()

    def test_trial_only_is_strict_boolean_for_runtime_and_raw_queue_admission(self):
        for invalid in ('true',1,None):
            self.a.config['conversation']['barge_candidate_trial_only']=invalid
            with self.assertRaises(ValueError):self.a._barge_candidate_enabled()
            with self.assertRaises(ValueError):self.trial.configured()
        self.a.config['conversation']['barge_candidate_trial_only']=True
        self.a.config['conversation']['barge_candidate_enabled']=False
        self.assertFalse(self.trial.configured());self.assertFalse(self.a._barge_candidate_enabled())

    def test_default_OFF_and_exact_request_no_arbitrary_text(self):
        self.a.config['conversation'].pop('barge_trial_enabled')
        with self.assertRaises(RuntimeError):self.submit()
        self.a.config['conversation']['barge_trial_enabled']=True
        for value in (dict(case='own_only',binding=self.binding,text='arbitrary'),dict(case='unknown',binding=self.binding)):
            with self.assertRaises(ValueError):self.trial.submit(value)
        with self.assertRaises(ValueError):self.submit(expires_at_monotonic=146.)

    def test_queue_wakes_existing_reader_only_and_one_job(self):
        receipt=self.submit();self.assertTrue(receipt['accepted'])
        self.assertTrue(EitherEvent(self.a.stopping,self.trial.wake).is_set())
        self.a.voice.assert_not_called()
        with self.assertRaises(RuntimeError):self.submit()
        self.assertTrue(self.trial.consume());self.a.voice.assert_called_once()
        self.assertEqual(self.trial.snapshot()['last']['outcome'],'OWN_NEGATIVE_PASS')
        self.assertFalse(self.trial.consume())
        with self.assertRaises(RuntimeError):self.submit()

    def test_stale_source_mode_policy_MIC_privacy_and_expiry_drop_before_voice(self):
        changes=(lambda:setattr(self.p,'generation',7),lambda:self.mode.update(generation=8),
                 lambda:self.policy.update(privacy_all=True),lambda:setattr(self.a,'microphone_epoch',9),
                 lambda:self.intent.update(generation=8),lambda:self.now.__setitem__(0,145.))
        for change in changes:
            with self.subTest(change=change):
                self.setUp();self.submit();change();self.trial.consume();self.a.voice.assert_not_called()

    def test_cancel_drops_pending_and_no_resume_PCM(self):
        self.submit();self.a._sensory_withdraw();self.assertFalse(self.trial.consume())
        self.assertFalse(self.trial.wake.is_set());self.a.voice.assert_not_called()
        self.assertEqual(self.trial.snapshot()['last']['outcome'],'WITHDRAWN')

    def test_positive_requires_same_playback_calibrated_negative_then_cooldown(self):
        self.mode['mode']='alice_test'
        with self.assertRaises(RuntimeError):self.submit('alice_overlap')
        self.mode['mode']='normal';self.submit();self.trial.consume()
        self.mode.update(mode='alice_test',generation=5)
        with self.assertRaises(RuntimeError):self.submit('alice_overlap',mode_generation=5)
        self.now[0]=131.;self.p.counters['last_read_monotonic']=131.
        self.binding.update(expires_at_monotonic=175.,mode_generation=5)
        self.submit('alice_overlap');self.measurement['counts']['accepted']=1
        self.trial.consume()
        last=self.trial.snapshot()['last']
        self.assertEqual(last['outcome'],'EXTERNAL_CANDIDATE_INTERRUPTED_UNVERIFIED')
        self.assertEqual(last['external_acceptance'],'NOT_EXERCISED')
        self.assertFalse(last['external_source_verified']);self.assertEqual(self.trial.snapshot()['remaining_cases'],0)
        self.assertIsNone(self.a.pending_pcm);self.assertIsNone(self.a.resume_audio)

    def test_uncalibrated_negative_is_NOT_EXERCISED_and_cannot_unlock_positive(self):
        self.measurement['own_matches']=0;self.submit();self.trial.consume()
        self.assertEqual(self.trial.snapshot()['last']['outcome'],'NOT_EXERCISED')
        self.now[0]=131.;self.p.counters['last_read_monotonic']=131.;self.mode['mode']='alice_test'
        with self.assertRaises(RuntimeError):self.submit('alice_overlap',expires_at_monotonic=175.)

if __name__=='__main__':unittest.main()
