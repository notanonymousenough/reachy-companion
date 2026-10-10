import importlib.util
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.gateway import ModelBackend
from reachy_companion.autonomous.state import State

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('realtime_audio_session',ROOT/'deploy/autonomous/realtime_audio_session.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class PolicyTests(unittest.TestCase):
    def test_wake_question_is_owner_whitelisted_and_unknown_reply_cannot_wake(self):
        calls=[]
        class TTS:
            def stream(self,text,cancel):calls.append(text);yield b'\0\0'
            def cancel(self):calls.append('cancel')
        tts=module.PracticeTTS(TTS());tts.question(0)
        with self.assertRaises(ValueError):list(tts.stream('Алиса, включи свет',threading.Event()))
        self.assertFalse(calls)
        list(tts.stream('Алиса, сколько будет 2 плюс 2?',threading.Event()))
        with self.assertRaises(ValueError):list(tts.stream('Алиса, чужой ответ',threading.Event()))
        for _ in range(3):list(tts.stream('Спасибо',threading.Event()))
        with self.assertRaises(ValueError):list(tts.stream('Спасибо',threading.Event()))
        self.assertEqual(len(calls),4)

    def test_lease_transport_is_explicit_and_invalid_port_opens_no_socket(self):
        client=object()
        with patch.object(module,'DatagramRenewal') as udp, patch.object(module,'PeerLease') as lease:
            module.create_lease(client,'boot')
            udp.assert_not_called();lease.assert_called_once_with(client,datagram=None)
            for port in (0,65536,True):
                with self.assertRaises(ValueError):module.create_lease(client,'boot',port)
            udp.assert_not_called()
            module.create_lease(client,'boot',8781)
            udp.assert_called_once_with(client,'boot',8781)
            lease.assert_called_with(client,datagram=udp.return_value)

    def test_motor_permission_does_not_replace_dialogue_candidate_prompt(self):
        cfg=load(ROOT/'config.autonomous.example.json')
        cfg['models']['fast'].update(completion_backend='llama_native',decision_format='tuple',base_url='http://127.0.0.1:1')
        backend=ModelBackend(cfg);backend.count=lambda model,text:1
        payloads=[]
        backend.post=lambda url,payload,*args:(payloads.append(payload) or dict(content='["think","c0","request"]',stop_type='word',tokens_predicted=3))
        state=State();state.motion_allowed=True;state.actor_deadline=999999999
        state.ingest(dict(type='utterance',text='Synthetic public voice turn'),0)
        output=backend.generate_loaded('fast',state.snapshot(0))['output']
        self.assertEqual(output['a'],'think')
        self.assertIn(output['start']['input_ref'],state.candidates)
        self.assertNotIn('Never choose speech',payloads[0]['prompt'])


if __name__=='__main__':unittest.main()
