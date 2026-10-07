import json
import shutil
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from reachy_companion.config import Config, initialize
from reachy_companion.intents import classify
from reachy_companion.expressions import spoken_segments, spoken_expression
from reachy_companion.replay import ReplayResponse
from reachy_companion.charge_reminder import ChargeReminder
from reachy_companion.speech_motion import cues
from reachy_companion.motion_limits import validate_steps

ROOT = Path(__file__).resolve().parents[1]


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy(ROOT/'config.example.json', self.root)
        shutil.copytree(ROOT/'profiles', self.root/'profiles')
        initialize(self.root)
        self.config = Config(self.root/'config.local.json')

    def agent(self):
        with patch.dict(sys.modules, {'webrtcvad': types.SimpleNamespace(Vad=lambda mode: None)}):
            from reachy_companion.agent import Agent
        self.config.data['conversation']['expressions']['enabled'] = False
        self.config.data['conversation']['greet_on_start'] = False
        self.config.data['conversation']['wake_on_start'] = False
        a = Agent(self.config)
        a.playback_configured = True
        self.addCleanup(a.stopping.set)
        return a

    def test_existing_model_storage_symlink_is_compatible_with_config_migration(self):
        shared = self.root/'shared-model-storage'
        shared.mkdir()
        (self.root/'models').symlink_to(shared, target_is_directory=True)
        updated = Config(self.config.filename)
        self.assertEqual(updated['conversation']['recognition']['path'], 'models/whisper-small')

    def test_stop_is_direct_command_and_does_not_mute_or_match_a_quotation(self):
        settings = self.config['conversation']['interaction']
        for text in ('Замолчи!', 'Ричи, замолчи, пожалуйста.', 'Заткнись', 'Хватит говорить'):
            self.assertEqual(classify(text, settings)['action'], 'stop')
        for text in ('Почему люди говорят «замолчи»?', 'Не замолчи, а продолжай', 'Расскажи про тишину'):
            self.assertEqual(classify(text, settings)['action'], 'answer')

    def test_model_selects_multiple_emotions_and_gestures_without_spoken_markup(self):
        raw = '<emotion=curious><gesture=tilt>Серьёзно? <emotion=amused><gesture=nod>Ну ты дал.</emotion>'
        segments = spoken_segments(raw)
        self.assertEqual([(s['emotion'], s['gesture']) for s in segments], [('curious','tilt'), ('amused','nod')])
        self.assertEqual(spoken_expression(raw), ('Серьёзно? Ну ты дал.', 'curious'))

    def test_phoneme_word_cues_follow_actual_audio_and_remain_bounded(self):
        settings = self.config['conversation']['expressions']
        a = lambda symbol, count: types.SimpleNamespace(phoneme=symbol, num_samples=count)
        chunk = types.SimpleNamespace(sample_rate=16000, phoneme_alignments=[a('a',8000),a(' ',8000),a('b',8000),a(' ',8000),a('c',8000)])
        result = cues(settings, chunk, {'emotion':'excited','gesture':'perk'}, 2, 16000, 80000)
        self.assertEqual([c['at'] for c in result], [2.0,3.0,4.0])
        for cue in result:
            self.assertEqual(cue['alignment'], 'piper')
            validate_steps(cue['steps'], settings)

    def test_resume_replays_exact_unspoken_pcm_and_shifts_motion_timestamps(self):
        import base64
        pcm = b'\x01\x02' * 32000
        saved = {'pcm':pcm,'cursor':32000,'result':{'reply':'original'},
                 'cues':[{'at':.5,'steps':[]}, {'at':1.5,'steps':[]}]}
        response = ReplayResponse(saved, self.config['streaming'])
        events = []
        while line := response.readline(): events.append(json.loads(line))
        self.assertEqual(events[1]['cues'][0]['at'], 0)
        self.assertEqual(events[1]['cues'][1]['at'], .5)
        played = b''.join(base64.b64decode(e['pcm_base64']) for e in events if e['type']=='audio')
        self.assertEqual(played, pcm[32000:])

    def test_empty_interruption_waits_until_deadline_then_continues_saved_reply(self):
        a = self.agent()
        saved = {'pcm':b'original audio','cursor':2,'epoch':0,'deadline':time.monotonic()+3}
        a.resume_audio = saved
        a.pending_pcm = (0, b'\x00\x00'*1600)
        def request(base, path, *args, **kwargs):
            if path == '/health': return {'ok':True}
            if path == '/status': return {'ownership':{'state':'free'}}
            if path == '/transcribe': return {'transcript':'','decision':{'action':'none'}}
            raise AssertionError(path)
        a.request = request
        a.capture = Mock(return_value=None)
        played = []
        def voice(*args, **kwargs):
            played.append(kwargs['replay'])
            a.stopping.set()
            return {'ok':True}
        a.voice = voice
        a.run()
        self.assertEqual(played, [saved])
        self.assertEqual(a.capture.call_args.kwargs['idle_deadline'], saved['deadline'])

    def test_spoken_stop_drops_saved_reply_without_muting_microphone(self):
        a = self.agent()
        a.resume_audio = {'pcm':b'old answer'}
        a.pending_pcm = (0, b'\x00\x00'*1600)
        def request(base, path, *args, **kwargs):
            if path == '/health': return {'ok':True}
            if path == '/status': return {'ownership':{'state':'free'}}
            if path == '/transcribe':
                a.stopping.set()
                return {'transcript':'замолчи','decision':{'action':'stop'}}
            raise AssertionError(path)
        a.request = request
        a.voice = Mock()
        a.run()
        a.voice.assert_not_called()
        self.assertIsNone(a.resume_audio)
        self.assertTrue(a.microphone.enabled)

    def test_charge_reminder_counts_only_observed_online_time_and_never_percent(self):
        clock = [0]
        with patch('reachy_companion.charge_reminder.time.monotonic', side_effect=lambda:clock[0]):
            reminder = ChargeReminder(self.root/'charge.json', {'reminder_enabled':True,'remind_after_minutes':1})
            reminder.observe(True)
            clock[0]=60
            reminder.observe(True)
            self.assertTrue(reminder.status()['charge_reminder_due'])
            self.assertIsNone(reminder.status()['battery_percent'])
            reminder.observe(False)
            clock[0]=600
            reminder.observe(False)
            self.assertEqual(reminder.status()['active_minutes'],1)
            reminder.reset()
            self.assertFalse(reminder.status()['charge_reminder_due'])
            self.assertEqual(json.loads((self.root/'charge.json').read_text())['active_seconds'],0)

    def test_asr_rejects_silence_and_own_reply_before_stopping_speaker(self):
        from reachy_companion.barge_in import BargeInMonitor
        a = self.agent()
        a.current_reply_text = 'Сейчас разберёмся с твоим вопросом.'
        a.stop_speaker = Mock()
        for text in ('', 'С твоим вопросом'):
            a.request = Mock(return_value={'transcript':text,'decision':{'action':'answer'}})
            self.assertFalse(BargeInMonitor(a).trigger(b'audio'))
        a.request = Mock(return_value={'transcript':'замолчи','decision':{'action':'stop'}})
        monitor = BargeInMonitor(a)
        self.assertTrue(monitor.trigger(b'audio'))
        a.stop_speaker.assert_called_once_with(abort_stream=False)
