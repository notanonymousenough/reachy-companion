import copy
import io
import json
import shutil
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from reachy_companion.config import Config, initialize
from reachy_companion.expressions import EMOTIONS, plan, spoken_expression
from reachy_companion.hub import Hub
from reachy_companion.microphone import MicrophoneState
from reachy_companion.motion_limits import validate_steps

ROOT = Path(__file__).resolve().parents[1]


class ExpressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy(ROOT / 'config.example.json', self.root)
        shutil.copytree(ROOT / 'profiles', self.root / 'profiles')
        initialize(self.root)
        self.config = Config(self.root / 'config.local.json')

    def agent(self):
        with patch.dict(sys.modules, {'webrtcvad': types.SimpleNamespace(Vad=lambda mode: None)}):
            from reachy_companion.agent import Agent
        self.config.data['conversation']['expressions']['enabled'] = False
        self.config.data['conversation']['barge_in']['enabled'] = False
        self.config.data['conversation']['barge_in']['confirm_with_stt'] = False
        self.config.data['conversation']['sound_reactions']['enabled'] = False
        a = Agent(self.config)
        self.addCleanup(a.stopping.set)
        return a

    def test_old_private_config_gets_expression_settings_after_pull(self):
        data = json.loads(self.config.filename.read_text())
        del data['conversation']['expressions']
        self.config.filename.write_text(json.dumps(data))
        c = Config(self.config.filename)
        self.assertTrue(c['conversation']['expressions']['enabled'])
        self.assertEqual(c.token, self.config.token)

    def test_all_emotions_produce_bounded_plans_and_reject_injected_motion(self):
        settings = self.config['conversation']['expressions']
        for emotion in EMOTIONS:
            steps = plan(settings, 'speaking', emotion)['steps']
            validate_steps(steps, settings)
            for mutation in ('translation', 'body', 'angle', 'nan', 'duration'):
                broken = copy.deepcopy(steps)
                if mutation == 'translation': broken[0]['head_pose']['z'] = .001
                if mutation == 'body': broken[0]['body_yaw'] = 0
                if mutation == 'angle': broken[0]['head_pose']['roll'] = 1
                if mutation == 'nan': broken[0]['antennas'][0] = float('nan')
                if mutation == 'duration': broken[0]['duration'] = .1
                with self.assertRaises(ValueError): validate_steps(broken, settings)

    def test_expression_never_enables_motors_or_overrides_other_app(self):
        payload = plan(self.config['conversation']['expressions'], 'speaking', 'joy')
        for mode, ownership in [('disabled','free'), ('gravity_compensation','free'), ('enabled','locked')]:
            hub = Hub(self.config)
            hub.status = Mock(return_value={'daemon': {'state':'running','backend_status':{'ready':True}},
                                            'ownership':{'state':ownership},'robot':{'control_mode':mode}})
            hub.robot = Mock(return_value=[])
            hub.move = Mock()
            with self.assertRaises(RuntimeError): hub.expression(payload)
            hub.move.assert_not_called()
            self.assertFalse(hub.lock.locked())

    def test_emotion_tag_is_not_spoken_or_stored_in_history(self):
        piper = types.SimpleNamespace(PiperVoice=object, SynthesisConfig=object)
        vosk = types.SimpleNamespace(Model=object, KaldiRecognizer=object, SetLogLevel=object)
        with patch.dict(sys.modules, {'piper':piper,'vosk':vosk}):
            from reachy_companion.voice import Pipeline
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.config = self.config
        pipeline.check_robot = lambda: None
        pending = {'messages':[{'role':'assistant','content':'<emotion=joy> Отлично!'}]}
        pipeline.answer = lambda *args: ('<emotion=joy> Отлично!', pending)
        result, _, updated = pipeline.prepare({'text':'привет'}, '/text')
        self.assertEqual(result['reply'], 'Отлично!')
        self.assertEqual(result['emotion'], 'joy')
        self.assertEqual(updated['messages'][-1]['content'], 'Отлично!')
        self.assertEqual(spoken_expression('<emotion=unknown> Привет'), ('Привет','neutral'))
        self.assertEqual(spoken_expression('<emotion=joy> Отлично!</emotion=joy>'), ('Отлично!','joy'))
        self.assertEqual(spoken_expression('<emotion=joy> Отлично!</emotion>'), ('Отлично!','joy'))

    def test_barge_in_stops_speaker_keeps_microphone_and_returns_complete_phrase(self):
        from reachy_companion.barge_in import BargeInMonitor
        a = self.agent()
        a.expressions = Mock()
        a.stop_speaker = Mock()
        expected = b'near-end-speech'
        def capture(**kwargs):
            kwargs['on_speech']()
            kwargs['on_speech']()
            return expected
        a.capture = capture
        monitor = BargeInMonitor(a)
        monitor.start()
        self.assertTrue(monitor.interrupted.wait(1))
        self.assertEqual(monitor.finish(), expected)
        self.assertEqual(a.interruptions, 1)
        a.stop_speaker.assert_called_once()
        self.assertTrue(a.microphone.enabled)
        self.assertTrue(a.listening.is_set())

    def test_barge_in_requires_continuous_speech_not_separated_echo_spikes(self):
        a = self.agent()
        a.calibrated = True
        a.config.data['conversation']['barge_in'].update(min_voiced_chunks=6, warmup_chunks=0)
        a.vad = types.SimpleNamespace(is_speech=lambda *args: True)
        loud = b'\x10\x27' * (a.chunk_bytes // 2)
        quiet = b'\x00\x00' * (a.chunk_bytes // 2)
        chunks = ([loud] * 3 + [quiet]) * 3 + [loud] * 6 + [quiet] * a.audio['silence_chunks']
        reads = []
        def read(*args):
            reads.append(len(reads) + 1)
            return chunks[len(reads)-1]
        process = Mock()
        process.__enter__ = Mock(return_value=process)
        process.__exit__ = Mock(return_value=False)
        process.stdout.read.side_effect = read
        selector = Mock()
        selector.select.return_value = [True]
        triggered = []
        with patch('reachy_companion.agent.subprocess.Popen', return_value=process), \
             patch('reachy_companion.agent.selectors.DefaultSelector', return_value=selector):
            pcm = a.capture(during_reply=True, on_speech=lambda pcm: triggered.append(len(reads)))
        self.assertEqual(triggered, [18])
        self.assertTrue(pcm)
        process.terminate.assert_called_once()

    def test_mute_drops_pending_barge_in_phrase(self):
        from reachy_companion.barge_in import BargeInMonitor
        a = self.agent()
        a.expressions = Mock()
        monitor = BargeInMonitor(a)
        def capture(**kwargs):
            kwargs['on_speech']()
            a.set_microphone(False)
            return b'private audio'
        a.capture = capture
        monitor.start()
        self.assertTrue(monitor.interrupted.wait(1))
        self.assertIsNone(monitor.finish())
        self.assertFalse(a.microphone.enabled)

    def test_volume_changes_only_speaker_and_persists_zero_and_restoration(self):
        from reachy_companion.volume import PlaybackVolume
        a = self.agent()
        for percent, switch in [(0, 'mute'), (65, 'unmute')]:
            with patch('reachy_companion.agent.subprocess.run') as run:
                a.set_volume(percent)
            self.assertEqual(run.call_args.args[0], ['amixer', '-c', 'Audio', 'sset', 'PCM,0', str(percent)+'%', switch])
            self.assertEqual(PlaybackVolume(a.volume.path, 95).percent, percent)
            self.assertTrue(a.microphone.enabled)
        for bad in [-1, 101, True, 42.5, '50']:
            with patch('reachy_companion.agent.subprocess.run') as run:
                with self.assertRaises(ValueError): a.set_volume(bad)
                run.assert_not_called()

    def test_mute_persists_and_invalid_saved_state_stays_muted(self):
        a = self.agent()
        a.set_microphone(False)
        self.assertFalse(a.listening.is_set())
        self.assertFalse(MicrophoneState(a.microphone.path).enabled)
        self.assertEqual(a.microphone.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError): a.set_microphone('false')
        a.microphone.path.write_text('corrupt')
        self.assertFalse(MicrophoneState(a.microphone.path).enabled)

    def test_mute_stops_playback_and_manual_finally_does_not_unmute(self):
        a = self.agent()
        process = Mock()
        process.poll.return_value = None
        a.playback_process = process
        def response(*args, **kwargs):
            a.set_microphone(False)
            return {'ok':True,'cancelled':True}
        a.voice = response
        a.manual('/say', {'text':'hello'})
        process.terminate.assert_called_once()
        self.assertFalse(a.listening.is_set())
        self.assertFalse(a.microphone.enabled)

    def test_agent_boot_and_saved_epoch_fence_restart(self):
        first=self.agent();first.set_microphone(False)
        second=self.agent()
        self.assertNotEqual(first.agent_boot_id,second.agent_boot_id)
        self.assertEqual(first.microphone_epoch,second.microphone_epoch)
        self.assertFalse(second.listening.is_set())
        self.assertFalse(second.microphone.enabled)

    def test_mute_holds_expression_instead_of_scheduling_new_neutral_motion(self):
        a=self.agent();a.expressions=Mock()
        a.set_microphone(False)
        a.expressions.hold.assert_called_once()
        a.expressions.set.assert_not_called()

    def test_muted_manual_voice_and_play_never_start_compute_audio_or_motion(self):
        a=self.agent();a.set_microphone(False);a.expressions=Mock();a.request=Mock()
        with patch('reachy_companion.agent.subprocess.Popen') as popen:
            self.assertTrue(a.manual('/say',{'text':'fixture'})['cancelled'])
            a.play('not decoded because muted',a.microphone_epoch)
        popen.assert_not_called();a.request.assert_not_called();a.expressions.set.assert_not_called()

    def test_microphone_write_failure_revokes_playback_and_listening(self):
        a=self.agent();a.playback_process=Mock();a.playback_process.poll.return_value=None
        a.pending_pcm=(a.microphone_epoch,b'fixture');a.resume_audio={'fixture':True}
        with patch('reachy_companion.microphone.os.fsync',side_effect=OSError('fixture fsync')):
            with self.assertRaises(OSError):a.set_microphone(True)
        self.assertFalse(a.microphone.enabled);self.assertFalse(a.listening.is_set())
        self.assertIsNone(a.pending_pcm);self.assertIsNone(a.resume_audio)
        a.playback_process.terminate.assert_called_once()

    def test_mute_during_startup_prevents_wake_and_greeting(self):
        a = self.agent()
        paths = []
        def request(base, path, *args, **kwargs):
            paths.append(path)
            if path == '/health':
                a.set_microphone(False)
                a.stopping.set()
                return {'ok':True}
            return {'ownership':{'state':'free'}}
        a.request = request
        a.voice = Mock()
        a.run()
        a.voice.assert_not_called()
        self.assertNotIn('/actions/wake', paths)

    def test_mute_discards_partially_captured_phrase_and_closes_recorder(self):
        a = self.agent()
        a.calibrated = True
        a.config.data['audio']['max_recording_seconds'] = .1
        a.vad = types.SimpleNamespace(is_speech=lambda *args: True)
        chunk = b'\xe8\x03' * (a.chunk_bytes // 2)
        reads = 0
        def read(*args):
            nonlocal reads
            reads += 1
            if reads == 2: a.set_microphone(False)
            return chunk
        process = Mock()
        process.__enter__ = Mock(return_value=process)
        process.__exit__ = Mock(return_value=False)
        process.stdout.read.side_effect = read
        selector = Mock()
        selector.select.return_value = [True]
        with patch('reachy_companion.agent.subprocess.Popen', return_value=process), \
             patch('reachy_companion.agent.selectors.DefaultSelector', return_value=selector):
            self.assertIsNone(a.capture())
        process.terminate.assert_called_once()
        self.assertFalse(a.capture_active)

    def test_mute_during_model_wait_discards_audio_before_player_starts(self):
        a = self.agent()
        class Response:
            headers = types.SimpleNamespace(get_content_type=lambda: 'application/x-ndjson')
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def readline(self, *args):
                a.set_microphone(False)
                return b'{"type":"reply","reply":"must not be played"}\n'
        a.http = types.SimpleNamespace(open=lambda *args, **kwargs:Response())
        with patch('reachy_companion.agent.subprocess.Popen') as player:
            result = a.voice('/text', {'text':'hello'})
        self.assertTrue(result['cancelled'])
        player.assert_not_called()


if __name__ == '__main__': unittest.main()
