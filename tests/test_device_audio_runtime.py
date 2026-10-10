"""Synthetic finite device lifecycle; no ALSA, service or hardware access."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock,patch
from reachy_companion.autonomous.audio_peer import AudioPeer
from reachy_companion.autonomous.playback import Playback,ReplayPCM

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('device_audio_runtime_test',ROOT/'deploy/autonomous/device_audio_runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


class DeviceRuntimeTests(unittest.TestCase):
    def test_actual_mute_exit_accepts_only_unchanged_final_owner_baseline(self):
        for newer_command in (False,True):
            with self.subTest(newer_command=newer_command),tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'receipt.json';owner=Path(directory)/'owner.json'
                actual=dict(agent_boot_id='agent',microphone_epoch=0,microphone_owner_id=None,
                    microphone_enabled=False,capture_active=False,listening=False,phase='paused',microphone_state_error=None,
                    motion_policy=dict(epoch=1,quiet=False,privacy_all=False,motor_enabled=False))
                peers=[]
                def agent(cfg,path,payload=None):
                    if path=='/microphone':
                        self.assertEqual(payload['expected_epoch'],actual['microphone_epoch'])
                        actual.update(microphone_epoch=actual['microphone_epoch']+1,
                            microphone_enabled=payload['enabled'],microphone_owner_id=payload.get('owner_id'))
                    return dict(actual)
                def peer(*args,**kwargs):
                    value=AudioPeer(*args,**kwargs);peers.append(value)
                    deadline=time.monotonic()+1
                    while not value.operator_ready() and time.monotonic()<deadline:time.sleep(.002)
                    value.dispatch('/lease',dict(controller='controller'))
                    return value
                class Capture:
                    calls=1;call_seconds=0;max_call_seconds=0
                    def read(self):
                        value=peers[0]
                        value.dispatch('/operator-mute',dict(controller='controller',source_boot=value.boot_id))
                        if newer_command:
                            actual.update(microphone_epoch=3,microphone_enabled=True,listening=True)
                        return dict(pcm=b'\0\0'*640,frames=320,captured_end=time.monotonic())
                    def close(self):return True
                class Config(dict):token='t'*32
                cfg=Config(audio=dict(capture_device='reachymini_audio_src',playback_device='fixture'))
                vad=types.SimpleNamespace(Vad=lambda _:types.SimpleNamespace(is_speech=lambda *args:False))
                argv=['device_audio_runtime','--config','fixture','--output',str(output),'--owner-file',str(owner),
                    '--controller','controller','--allow-capture-output','--allow-agent-mute','--duration','1']
                with patch.object(runtime,'Config',return_value=cfg),patch.object(runtime,'agent',side_effect=agent),\
                        patch.object(runtime,'AudioPeer',side_effect=peer),patch.object(runtime,'AlsaPCM',return_value=ReplayPCM()),\
                        patch.object(runtime,'Playback',side_effect=lambda backend,**kwargs:Playback(backend,allow_simulated=True,**kwargs)),\
                        patch.object(runtime,'AlsaCapture',return_value=Capture()),patch.object(runtime,'create_server',return_value=Mock()),\
                        patch.object(runtime.signal,'signal'),patch.object(sys,'argv',argv),patch.dict(sys.modules,{'webrtcvad':vad}),\
                        contextlib.redirect_stdout(io.StringIO()):
                    if newer_command:
                        with self.assertRaises(SystemExit) as exit:runtime.main()
                        self.assertEqual(exit.exception.code,2)
                    else:runtime.main()
                receipt=json.loads(output.read_text())
                self.assertEqual(receipt['accepted'],not newer_command)
                self.assertFalse(receipt['peer_status']['operator_control_execution_busy'])
                self.assertEqual(receipt['peer_status']['agent_mute_receipt']['microphone_epoch'],2)
                self.assertTrue(receipt['capture_closed']);self.assertTrue(receipt['playback']['stop_known'])
                self.assertNotIn(json.loads(owner.read_text())['owner_id'],output.read_text())
                self.assertEqual(actual['microphone_enabled'],newer_command)


if __name__=='__main__':unittest.main()
