import importlib.util
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.gateway import ModelBackend
from reachy_companion.autonomous.state import State

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('realtime_audio_session',ROOT/'deploy/autonomous/realtime_audio_session.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class PolicyTests(unittest.TestCase):
    def test_working_audio_receipt_requires_actual_canonical_admission_and_exports_no_transcript(self):
        state=State();event=dict(type='utterance',text='Neutral fixture utterance',audio=dict(
            source_boot='capture',sequence=1,pcm_sha256='a'*64,lineage_id='capture:1',origin='unknown',
            capture_age_ms=10,operator_binding=['agent',1,0]))
        ingest=lambda event,now:state.ingest(event,0 if now is None else now)
        state.ingest(dict(type='operator',muted=True),0)
        self.assertIsNone(module.admit_working_audio(ingest,state,event))
        state.ingest(dict(type='operator',muted=False),0)
        result=module.admit_working_audio(ingest,state,event)
        self.assertEqual(result['working_input_ref'],next(iter(state.candidates)))
        self.assertEqual(result['working_authority'],state.authority.wire())
        self.assertNotIn('Neutral fixture utterance',str(result))
        self.assertIsNone(module.admit_working_audio(lambda *args:None,state,event))

    def test_slow_reducer_cannot_hide_cancel_deadline_crossing_before_ack_and_stop(self):
        for began,work,expected in ((.483,.042,False),(.440,.042,True)):
            with self.subTest(began=began):
                now=[began];order=[]
                reducer=SimpleNamespace(advance=lambda:(order.append('reducer_work'),now.__setitem__(0,now[0]+work)))
                stale_iteration_time=now[0];reducer.advance()
                def result():
                    order.append('actual_ack')
                    return dict(source_boot='source',agent_mute_verified=True)
                def status():
                    order.append('fresh_stop');return dict(stop_known=True,execution_busy=False)
                job=SimpleNamespace(future=SimpleNamespace(done=lambda:True,result=result))
                completion=module.cancel_completion(SimpleNamespace(status=status),job,'source',0,
                    actual_agent=True,clock=lambda:(order.append('completion_clock') or now[0]))
                self.assertEqual(completion[0]<=.5,expected)
                self.assertTrue(stale_iteration_time<=.5) # old harness falsely passed both
                self.assertEqual(order,['reducer_work','actual_ack','fresh_stop','completion_clock'])
                self.assertLess(work,.1) # reducer budget passing cannot replace cancel deadline

    def test_cancel_completion_rechecks_stop_after_ack_and_keeps_unknown_pending(self):
        speech=SimpleNamespace(status=lambda:dict(stop_known=True,execution_busy=True))
        job=SimpleNamespace(future=SimpleNamespace(done=lambda:True,
            result=lambda:dict(source_boot='source',agent_mute_verified=True)))
        self.assertIsNone(module.cancel_completion(speech,job,'source',0,actual_agent=True))
        job.future.done=lambda:False
        self.assertIsNone(module.cancel_completion(speech,job,'source',0,actual_agent=True))
        job.future.done=lambda:True;job.future.result=lambda:dict(source_boot='retired',agent_mute_verified=True)
        with self.assertRaises(RuntimeError):module.cancel_completion(speech,job,'source',0,actual_agent=True)

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
