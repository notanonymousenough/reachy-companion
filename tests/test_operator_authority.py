"""Finite test cleanup must not overwrite a concurrent operator command."""
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock,patch

from reachy_companion.microphone import MicrophoneState


class OperatorAuthorityTests(unittest.TestCase):
    def setUp(self):
        # Hardware VAD is unused by these control-method tests.
        with patch.dict(sys.modules,{'webrtcvad':types.ModuleType('webrtcvad')}):
            Agent=importlib.import_module('reachy_companion.agent').Agent
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.agent=Agent.__new__(Agent)
        self.agent.microphone=MicrophoneState(Path(self.tmp.name)/'mic.json',False)
        self.agent.microphone_epoch=0;self.agent.agent_boot_id='current'
        self.agent.microphone_owner_id=None
        self.agent.microphone_lock=threading.Lock();self.agent.listening=threading.Event()
        self.agent.capture_active=False;self.agent.expressions=Mock();self.agent.sounds=Mock()
        self.agent.stop_speaker=Mock()

    def test_stale_cleanup_preserves_newer_operator_state_and_file(self):
        agent=self.agent
        agent.set_microphone(True,False,expected_boot_id='current',expected_epoch=0)
        agent.set_microphone(True) # fresh human command enables listening
        before=agent.microphone.path.read_bytes()
        with self.assertRaises(RuntimeError):
            agent.set_microphone(False,expected_boot_id='current',expected_epoch=1)
        self.assertTrue(agent.microphone.enabled);self.assertTrue(agent.listening.is_set())
        self.assertEqual(agent.microphone_epoch,2)
        self.assertEqual(agent.microphone.path.read_bytes(),before)
        agent.stop_speaker.assert_not_called()

    def test_exact_owner_cleanup_and_old_boot_rejection(self):
        agent=self.agent
        with self.assertRaises(RuntimeError):
            agent.set_microphone(True,False,expected_boot_id='old',expected_epoch=0)
        self.assertEqual(agent.microphone_epoch,0)
        agent.set_microphone(True,False,expected_boot_id='current',expected_epoch=0)
        self.assertFalse(agent.listening.is_set())
        result=agent.set_microphone(False,expected_boot_id='current',expected_epoch=1)
        self.assertFalse(result['microphone_enabled']);self.assertEqual(result['microphone_epoch'],2)
        agent.stop_speaker.assert_called_once()

    def test_two_concurrent_authority_commands_only_one_can_commit(self):
        barrier=threading.Barrier(3);results=[]
        def invoke():
            barrier.wait()
            try:self.agent.set_microphone(True,False,expected_boot_id='current',expected_epoch=0);results.append('committed')
            except RuntimeError:results.append('stale')
        threads=[threading.Thread(target=invoke) for _ in range(2)]
        for thread in threads:thread.start()
        barrier.wait()
        for thread in threads:thread.join(1);self.assertFalse(thread.is_alive())
        self.assertCountEqual(results,['committed','stale']);self.assertEqual(self.agent.microphone_epoch,1)

    def test_partial_or_noninteger_authority_cannot_change_state(self):
        for kwargs in ({'expected_epoch':0},{'expected_boot_id':'current'},
                       {'expected_boot_id':'current','expected_epoch':True},
                       {'expected_boot_id':'current','expected_epoch':-1}):
            with self.assertRaises(ValueError):self.agent.set_microphone(True,**kwargs)
        self.assertEqual(self.agent.microphone_epoch,0)

    def test_failed_activation_cannot_claim_a_human_command_at_same_epoch(self):
        agent=self.agent
        agent.set_microphone(True) # human wins before queued test activation
        with self.assertRaises(RuntimeError):
            agent.set_microphone(True,False,expected_boot_id='current',expected_epoch=0,owner_id='test')
        with self.assertRaises(RuntimeError):
            agent.set_microphone(False,expected_boot_id='current',expected_epoch=1,expected_owner_id='test')
        self.assertTrue(agent.listening.is_set());self.assertTrue(agent.microphone.enabled)
        self.assertIsNone(agent.microphone_owner_id)

    def test_cleanup_before_delayed_activation_invalidates_its_authority(self):
        agent=self.agent
        agent.set_microphone(False,expected_boot_id='current',expected_epoch=0)
        with self.assertRaises(RuntimeError):
            agent.set_microphone(True,False,expected_boot_id='current',expected_epoch=0,owner_id='test')
        self.assertFalse(agent.microphone.enabled)

    def test_owned_cleanup_requires_exact_nonce_and_unconditional_command_clears_it(self):
        agent=self.agent
        agent.set_microphone(True,False,expected_boot_id='current',expected_epoch=0,owner_id='test')
        with self.assertRaises(RuntimeError):
            agent.set_microphone(False,expected_boot_id='current',expected_epoch=1,expected_owner_id='other')
        agent.set_microphone(False,expected_boot_id='current',expected_epoch=1,expected_owner_id='test')
        self.assertIsNone(agent.microphone_owner_id);self.assertFalse(agent.microphone.enabled)

    def test_device_cancel_uses_real_agent_cas_and_cleanup_preserves_later_command(self):
        spec=importlib.util.spec_from_file_location('device_audio_runtime',Path(__file__).resolve().parents[1]/'deploy/autonomous/device_audio_runtime.py')
        runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
        agent=self.agent
        owner=dict(agent_boot_id='current',initial_microphone_epoch=0,owned_microphone_epoch=1,owner_id='private-owner')
        owner_path=Path(self.tmp.name)/'owner.json';owner_path.write_text(json.dumps(owner))
        agent.set_microphone(True,False,expected_boot_id='current',expected_epoch=0,owner_id='private-owner')
        def request(cfg,path,payload=None):
            if path=='/microphone':return agent.set_microphone(**payload)
            return dict(agent_boot_id=agent.agent_boot_id,microphone_epoch=agent.microphone_epoch,
                microphone_owner_id=agent.microphone_owner_id,microphone_enabled=agent.microphone.enabled)
        with patch.object(runtime,'agent',side_effect=request) as rpc:
            receipt=runtime.mute_owned_agent(None,owner)
            self.assertFalse(receipt['microphone_enabled']);self.assertEqual(receipt['microphone_epoch'],2)
            self.assertFalse(receipt['microphone_owner_present']);self.assertNotIn('private-owner',str(receipt))
            before=agent.microphone.path.read_bytes();runtime.cleanup(None,owner_path)
            self.assertEqual(agent.microphone.path.read_bytes(),before)
            agent.set_microphone(True) # newer human command must survive delayed cancel/ExecStopPost
            before=agent.microphone.path.read_bytes();runtime.cleanup(None,owner_path)
            with self.assertRaises(RuntimeError):runtime.mute_owned_agent(None,owner)
            self.assertEqual(agent.microphone.path.read_bytes(),before);self.assertTrue(agent.listening.is_set())
            agent.agent_boot_id='new-boot';runtime.cleanup(None,owner_path)
            with self.assertRaises(RuntimeError):runtime.mute_owned_agent(None,owner)
            self.assertEqual(agent.microphone.path.read_bytes(),before)
            for call in rpc.call_args_list:
                if call.args[1]=='/microphone':
                    self.assertFalse(call.args[2]['enabled']);self.assertFalse(call.args[2]['listen'])
                    self.assertEqual(call.args[2]['expected_owner_id'],'private-owner')


if __name__=='__main__':unittest.main()
