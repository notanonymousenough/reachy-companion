"""Synthetic fixtures for the installed R42 package; no artifact-directory loads."""
import ast
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from reachy_companion.r42 import initiative as I

def status():
    return dict(agent_boot_id='fixture-boot', microphone_epoch=303, microphone_owner_id=None, motion_policy_owner_id=None, microphone_enabled=True, listening=True, capture_active=True, microphone_state_error=None, phase='listening', expression_version=0, motion_policy=dict(epoch=142, motor_enabled=False, quiet=False, privacy_all=False))

def hub():
    return dict(ownership=dict(state='free'), action_running=False, stock_motion=dict(selected=True, unknown=False, owned_uuid=None, hub_boot_id='fixture-hub'), daemon=dict(state='running', error=None, backend_status=dict(ready=True, error=None)))

class Checks(unittest.TestCase):

    def setUp(self):
        self.now = 100.0
        self.clock = patch.object(I.time, 'monotonic', side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.value = status()
        self.hub = hub()
        self.active = []
        a = self.a = SimpleNamespace(config=dict(network=dict(hub_url='http://fixture-hub', voice_url='http://fixture-voice', robot_url='http://fixture-robot', llm_base_url='http://fixture-model/v1'), llm=dict(model='existing-9B'), timeouts=dict(http=2), servers=dict(agent=dict(port=8090)), conversation=dict(session='existing')), microphone_lock=threading.Lock(), motion_policy=SimpleNamespace(lock=threading.RLock(), owner_id=None, snapshot=lambda: copy.deepcopy(self.value['motion_policy'])), agent_boot_id='fixture-boot', microphone_epoch=303, microphone_owner_id=None, microphone=SimpleNamespace(enabled=True, error=None), listening=threading.Event(), stopping=threading.Event(), phase='listening', capture_active=True, pending_pcm=None, resume_audio=None, playback_process=None, voice_response=None, audio_lock=threading.Lock(), calibrated=True, sounds=SimpleNamespace(music=False), audio=dict(chunk_ms=100), _capture_enabled=lambda: True, operator_status=lambda: copy.deepcopy(self.value), voice=Mock(return_value=dict(ok=True)), stop_speaker=Mock())

        class Config(dict):
            token = 'x' * 32
        a.config = Config(a.config)
        a.listening.set()
        a.audio_lock.acquire()
        a.expressions = SimpleNamespace(version=0)
        a.request = lambda base, path, **kwargs: copy.deepcopy(self.hub if path == '/status' else self.active)
        a.initiative = I.Initiative(a)
        self.pump = a._capture_pump = SimpleNamespace(condition=threading.RLock(), counters=dict(last_read_monotonic=100.0), permitted=lambda: True, error=None, assembler=SimpleNamespace(frames=[], number=0, seen=10), latest=None, output_active=False, suppress_until=0, generation=1, retire=Mock())
        self.call = 0

        def visual(dispatch, text, epoch, expected):
            self.call += 1
            self.value.update(capture_active=False, phase='processing')
            try:
                return dispatch(a, text, epoch, expected)
            finally:
                self.value.update(capture_active=True, phase='listening')
        a._capture_visual = visual
        self.payload = dict(enabled=True, expected_generation=0, operator_binding=dict(I.binding(self.value), expires_at_monotonic=159.0))
        self.result = dict(kind='companion-vision-snapshot', final_text='Какого цвета этот предмет?', expires_at_monotonic=159.0, frame=dict(frame_id='a' * 32, camera_closed=True, model_instance_preserved=True, raw_pixel_files=0))

    def arm(self):
        return self.a.initiative.arm(copy.deepcopy(self.payload))

    def advance(self, seconds=3.1, seen=31):
        self.now += seconds
        self.pump.counters['last_read_monotonic'] = self.now
        self.pump.assembler.seen += seen

    def foreground(self, phase):
        self.a.phase = self.value['phase'] = phase
        self.a.capture_active = self.value['capture_active'] = phase == 'listening'

    def test_arm_CAS_no_duplicate_pending_or_replayed_optin_fresh_authority(self):
        self.assertEqual(self.arm()['state'], 'armed')
        with self.assertRaises(RuntimeError):
            self.arm()
        newer = copy.deepcopy(self.payload)
        newer['expected_generation'] = 1
        with self.assertRaises(RuntimeError):
            self.a.initiative.arm(newer)
        self.a.initiative.cancel()
        self.assertEqual(self.a.initiative.status()['state'], 'cancelled')
        with self.assertRaises(RuntimeError):
            self.arm()
        newer['expected_generation'] = 2
        self.a.initiative.arm(newer)
        self.assertEqual(self.a.initiative.status()['generation'], 3)
        self.a.initiative.cancel()
        bad = copy.deepcopy(newer)
        bad['expected_generation'] = 4
        bad['operator_binding']['agent_boot_id'] = 'old'
        with self.assertRaises(RuntimeError):
            self.a.initiative.arm(bad)

    def test_elapsed_clock_or_partial_speech_stale_receipt_and_no_new_PCM_never_trigger(self):
        self.arm()
        i = self.a.initiative
        self.assertFalse(i.maybe_run())
        self.advance(seen=0)
        self.assertFalse(i.maybe_run())
        self.pump.assembler.frames = [b'partial']
        self.advance()
        self.assertFalse(i.maybe_run())
        self.assertIsNone(i.quiet)
        self.pump.assembler.frames = []
        self.assertFalse(i.maybe_run())
        self.advance()
        self.pump.latest = object()
        self.assertFalse(i.maybe_run())
        self.pump.latest = None
        self.assertFalse(i.maybe_run())
        self.now += 4
        self.assertFalse(i.maybe_run())
        self.pump.counters['last_read_monotonic'] = self.now
        self.assertFalse(i.maybe_run())
        self.advance()
        self.pump.generation += 1
        self.assertFalse(i.maybe_run())
        self.assertEqual(self.call, 0)
        self.a.voice.assert_not_called()
        self.pump.retire.assert_not_called()

    def test_local_child_protocol_fresh_typed_guard_no_remote_admission(self):
        self.arm()
        i = self.a.initiative
        i.state = 'running'
        self.value.update(capture_active=False, phase='processing')
        packet = dict(config=dict(llm=dict(model='existing-9B')), port=8090, token='x' * 32, expected=I.binding(self.value), deadline=159.0, generation=1)
        payload = dict(initiative=i.status(), operator=copy.deepcopy(self.value))
        events = []
        delay = [0.0]

        class Connection:

            def __init__(self, host, port, timeout):
                self_outer.assertEqual((host, port, timeout), ('127.0.0.1', 8090, 0.3))

            def request(self, method, path, headers):
                events.append((method, path))

            def getresponse(self):
                self_outer.now += delay[0]
                return SimpleNamespace(status=200, read=lambda bound: json.dumps(payload).encode())

            def close(self):
                pass
        self_outer = self
        snapshot = SimpleNamespace(caption_checked=Mock(return_value=self.result))
        with patch.object(I.http.client, 'HTTPConnection', Connection):
            self.assertEqual(I.child(packet, snapshot), self.result)
            snapshot.caption_checked.assert_called_once()
            args = snapshot.caption_checked.call_args
            self.assertEqual(args.args[:3], (packet['config'], 159.0, I.PURPOSE))
            self.assertEqual(args.kwargs, dict(question_only=True))
            self.assertEqual(events, [('GET', '/initiative')])
            snapshot.caption_checked.reset_mock()
            delay[0] = 0.301
            with self.assertRaises(RuntimeError):
                I.child(packet, snapshot)
            snapshot.caption_checked.assert_not_called()
            delay[0] = 0.0
            for change in (dict(generation=True), dict(extra='remote'), dict(deadline=float('nan'))):
                bad = dict(packet, **change)
                with self.assertRaises(ValueError):
                    I.child(bad, snapshot)
            payload['operator']['microphone_epoch'] = True
            with self.assertRaises(ValueError):
                I.child(packet, snapshot)
            snapshot.caption_checked.assert_not_called()

    def process(self, result=None):
        process = Mock(returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = (json.dumps(result or self.result).encode(), None)
        return process

    def test_snapshot_parent_dispatch_no_speech_after_STOP_and_no_replay(self):
        self.arm()
        i = self.a.initiative
        i.state = 'running'
        self.value.update(capture_active=False, phase='processing')
        process = self.process()

        def communicate(*args, **kwargs):
            self.value['microphone_epoch'] += 1
            return (json.dumps(self.result).encode(), None)
        process.communicate.side_effect = communicate
        with patch.object(I.subprocess, 'Popen', return_value=process):
            with self.assertRaises(RuntimeError):
                i.dispatch(1)
        self.a.voice.assert_not_called()
        self.assertIsNone(self.a.pending_pcm)

    def test_one_bounded_question_existing_frontdoor_no_transcript_or_extra_model(self):
        self.arm()
        i = self.a.initiative
        i.state = 'running'
        self.value.update(capture_active=False, phase='processing')
        process = self.process()
        with patch.object(I.subprocess, 'Popen', return_value=process) as start:
            i.dispatch(1)
        args = start.call_args.args[0]
        self.assertEqual(args[0], '/venvs/mini_daemon/bin/python')
        self.assertNotIn('shell', start.call_args.kwargs)
        packet = json.loads(process.communicate.call_args.args[0])
        self.assertNotIn('question', packet)
        self.assertNotIn('transcript', packet)
        self.a.voice.assert_called_once_with('/say', dict(text=self.result['final_text'], session='existing'), expected_epoch=303, expected_policy_epoch=142, valid_until=159.0, allow_barge_in=False, initiative_generation=1)
        for text in ('Описание.', 'Что? Почему?', 'What color?', 'x' * 181 + '?', '<think>Почему?', 'Почему?\n'):
            bad = copy.deepcopy(self.result)
            bad['final_text'] = text
            with self.assertRaises(ValueError):
                I.question(bad)

    def test_child_inference_is_cancelled_promptly_without_audio_or_queued_output(self):
        self.arm()
        i = self.a.initiative
        i.state = 'running'
        self.value.update(capture_active=False, phase='processing')
        process = self.process()
        process.poll.return_value = None

        def communicate(*args, **kwargs):
            if kwargs.get('timeout'):
                i.cancel()
                raise I.subprocess.TimeoutExpired('fixture', 0.2)
            return (b'', None)
        process.communicate.side_effect = communicate
        with patch.object(I.subprocess, 'Popen', return_value=process):
            with self.assertRaises(RuntimeError):
                i.dispatch(1)
        process.kill.assert_called_once()
        self.a.voice.assert_not_called()
        self.a.stop_speaker.assert_called_once()
