"""Source-only received-caption autonomous path; no device/model calls."""
import copy
import json
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from tests import r42_fixture as f
from reachy_companion.r42 import caption_initiative as C
from reachy_companion.r42 import initiative as I


class CaptionChecks(unittest.TestCase):
    setUp=f.Checks.setUp
    advance_clock=f.Checks.advance

    def setup_caption(self,decision=None):
        self.value['motion_policy']['motor_enabled']=True
        self.a.config['conversation']['session']='existing'
        self.dto=dict(summary='На столе белая чашка.',source='shared-camera-ipc-receipt',frame_id='a'*32,
            receipt_age_s=10,ttl_remaining_s=20,exposure_age_unknown=True)
        self.active=False;self.unknown=False;self.foreground=False
        def authority():
            binding=dict(agent_boot_id='fixture-boot',microphone_epoch=self.value['microphone_epoch'],
                policy_epoch=self.value['motion_policy']['epoch'],intent_generation=1,mode_generation=1,
                microphone_owner_id=None,motion_policy_owner_id=None,motor_enabled=self.value['motion_policy']['motor_enabled'])
            return binding,self.value['microphone_enabled'] and not self.value['motion_policy']['privacy_all'],self.value['motion_policy']['privacy_all']
        def reserve():
            if self.active or self.foreground or self.unknown:return False
            self.active=True;return True
        def finish(unknown):self.active=False;self.unknown|=unknown
        self.bridge=SimpleNamespace(configured=True,camera_enabled=True,caption_initiative_enabled=True,camera_authority=authority,
            visual_context=lambda:None if self.dto is None else dict(self.dto,receipt_age_s=self.now-90,ttl_remaining_s=120-self.now),
            reserve_caption_decision=reserve,finish_caption_decision=finish)
        self.decision=decision or Mock(return_value=dict(question='Зачем тебе эта белая чашка?',unknown=False,failure=None))
        self.c=C.CaptionInitiative(self.a,self.bridge,clock=lambda:self.now,decision=self.decision)
        self.a.initiative.caption_autonomy=self.c
        return self.c

    def enable(self):
        i=self.a.initiative
        i.schedule_control(dict(enabled=True,expected_generation=i.schedule_generation,
            operator_binding=dict(I.binding(self.value),expires_at_monotonic=self.now+59)))

    def harvest(self):
        for _ in range(100):
            if self.c.future is not None and self.c.future.done():return
            time.sleep(.001)
        self.fail('worker did not return')

    def start(self):
        self.enable();self.a.initiative.maybe_run()
        self.advance_clock();self.a.initiative.maybe_run()

    def test_fresh_AUTO_quiet_async_question_existing_say_no_reader_retire(self):
        self.setup_caption();self.start();self.harvest()
        self.assertTrue(self.a.initiative.maybe_run())
        args=self.a.voice.call_args
        self.assertEqual(args.args[0],'/say')
        self.assertEqual(args.args[1]['text'],'Зачем тебе эта белая чашка?')
        self.assertTrue(args.kwargs['manual_authority']())
        self.assertEqual(args.kwargs['valid_until'],120)
        self.pump.retire.assert_not_called();self.assertEqual(self.call,0)
        self.assertEqual(self.c.counts['spoken'],1)
        self.assertGreaterEqual(self.a.initiative.schedule_next_due,self.now+300)
        self.assertNotIn('transcript',args.args[1])

    def test_default_OFF_unknown_stale_or_missing_caption_never_calls_model(self):
        self.setup_caption()
        for _ in range(3):self.a.initiative.maybe_run();self.advance_clock()
        self.decision.assert_not_called()
        self.enable();self.dto=None
        for _ in range(3):self.a.initiative.maybe_run();self.advance_clock()
        self.decision.assert_not_called();self.a.voice.assert_not_called()
        self.pump.retire.assert_not_called()

    def test_WAIT_consumes_cadence_no_retry(self):
        self.setup_caption(Mock(return_value=dict(question=None,unknown=False,failure=None)))
        self.start();self.harvest();self.a.initiative.maybe_run()
        for _ in range(10):self.advance_clock();self.a.initiative.maybe_run()
        self.assertEqual(self.decision.call_count,1)
        self.a.voice.assert_not_called();self.assertEqual(self.c.counts['wait'],1)

    def test_foreground_drops_decision_but_AUTO_and_reader_survive_and_future_drains(self):
        entered=threading.Event();release=threading.Event()
        def decide(*args,**kwargs):
            entered.set();release.wait(1)
            return dict(question='Что это за чашка?',unknown=False,failure=None)
        self.setup_caption(decide);self.addCleanup(release.set)
        self.start();self.assertTrue(entered.wait(1))
        self.assertFalse(self.pump.retire.called)
        self.a.initiative.input_activity()
        self.assertTrue(self.a.initiative.schedule_enabled)
        self.assertTrue(self.active);self.assertTrue(self.c.status()['busy'])
        release.set();self.harvest();self.a.initiative.maybe_run()
        self.a.voice.assert_not_called();self.assertFalse(self.active)

    def test_STOP_privacy_and_epoch_after_model_discard_with_no_output(self):
        for which in ('stop','privacy','epoch'):
            with self.subTest(which=which):
                self.setup_caption()
                if self.a.initiative.schedule_enabled:self.a.initiative.cancel()
                self.value.update(microphone_enabled=True);self.value['motion_policy'].update(privacy_all=False,epoch=142)
                self.a.initiative.schedule_next_due=0;self.a.initiative.state='off'
                self.start();self.harvest()
                if which=='stop':self.a.initiative.cancel()
                if which=='privacy':self.value['motion_policy']['privacy_all']=True
                if which=='epoch':self.value['motion_policy']['epoch']+=1
                self.a.initiative.maybe_run()
                self.a.voice.assert_not_called()

    def test_background_unknown_latches_without_disabling_foreground(self):
        self.setup_caption(Mock(return_value=dict(question=None,unknown=True,failure='transport_unknown')))
        self.start();self.harvest();self.a.initiative.maybe_run()
        self.assertTrue(self.unknown);self.assertTrue(self.c.unknown)
        self.assertEqual(self.c.counts['failed'],1)
        self.assertFalse(self.active);self.a.voice.assert_not_called()
        self.now+=400;self.pump.counters['last_read_monotonic']=self.now
        self.a.initiative.maybe_run();self.assertEqual(self.decision.call_count,1)
        self.assertEqual(self.c.counts['failed'],1)

    def test_question_contract_reuses_existing_NO_BASIS_shape(self):
        self.assertIsNone(C.question('НЕТ_ОСНОВАНИЯ'))
        self.assertEqual(C.question('Какого цвета эта чашка?'),'Какого цвета эта чашка?')
        for value in ('Описание чашки.','<think>почему?</think>','Почему? А зачем?',' why?',None):
            with self.subTest(value=value),self.assertRaises(ValueError):C.question(value)

    def test_rollout_knob_OFF_preserves_camera_and_legacy_AUTO(self):
        self.setup_caption();self.bridge.caption_initiative_enabled=False
        self.assertFalse(self.c.applicable())
        self.assertTrue(self.bridge.camera_enabled)
        with patch.object(self.a.initiative,'dispatch',return_value=dict(ok=True)) as old:
            self.start()
        self.assertTrue(old.called)
        self.decision.assert_not_called()
        self.assertTrue(self.a.initiative.schedule_enabled)

    def test_knob_is_typed_and_defaults_FALSE_in_real_bridge(self):
        from tests.test_r53_sensory_bridge import Fixture
        from reachy_companion.r42.sensory_bridge import SensoryBridge
        a=Fixture();self.addCleanup(a.close)
        self.assertFalse(a.sensory.caption_initiative_enabled)
        a.config['conversation']['sensory_loop']['caption_initiative_enabled']='true'
        with self.assertRaises(ValueError):SensoryBridge(a,start=False)

    def test_question_bound_100_is_in_SYSTEM_and_validator(self):
        self.assertIn('<=100',C.SYSTEM)
        self.assertEqual(len(C.question('Ч'+'а'*98+'?')),100)
        with self.assertRaises(ValueError):C.question('Ч'+'а'*99+'?')

    def test_foreground_during_caption_speech_preserves_AUTO_and_cancels_generation(self):
        self.setup_caption();self.start();self.harvest()
        def voice(*args,**kwargs):
            i=self.a.initiative;generation=i.generation
            self.assertTrue(kwargs['manual_authority']())
            i.input_activity()
            self.assertTrue(i.schedule_enabled)
            self.assertGreater(i.generation,generation)
            self.assertIsNone(i.schedule_child)
            self.assertFalse(kwargs['manual_authority']())
            return dict(ok=True,cancelled=True)
        self.a.voice.side_effect=voice
        self.a.initiative.maybe_run()
        self.a.stop_speaker.assert_not_called()
        self.assertTrue(self.a.initiative.schedule_enabled)
        self.assertEqual(self.c.counts['spoken'],0)
        receipt=self.c.status()['last_decision']
        self.assertEqual(receipt['decision'],'QUESTION')
        self.assertTrue(receipt['issued']);self.assertTrue(receipt['completed'])
        self.assertTrue(receipt['cancelled']);self.assertFalse(receipt['result_ok'])

    def test_bounded_last_decision_product_receipt_and_explicit_redaction(self):
        self.setup_caption();self.start();self.harvest();self.a.initiative.maybe_run()
        receipt=self.c.status()['last_decision']
        self.assertEqual(receipt['decision'],'QUESTION')
        self.assertEqual(receipt['frame_id'],'a'*32)
        self.assertLessEqual(len(receipt['question']),100)
        self.assertTrue(receipt['issued']);self.assertTrue(receipt['completed']);self.assertTrue(receipt['result_ok'])
        self.assertEqual(len(self.c.history),1)
        self.a.initiative.cancel()
        self.assertNotIn('question',self.c.status()['last_decision'])
        self.assertEqual(len(self.c.history),0)
        self.assertFalse(self.a.initiative.schedule_enabled)

    def test_late_model_after_explicit_withdraw_cannot_restore_question_receipt(self):
        entered=threading.Event();release=threading.Event()
        def decide(*args,**kwargs):
            entered.set();release.wait(1)
            return dict(question='Что это за чашка?',unknown=False,failure=None,http_status=200,response_complete=True,body_bytes=100)
        self.setup_caption(decide);self.addCleanup(release.set)
        self.start();self.assertTrue(entered.wait(1))
        self.a.initiative.cancel();release.set();self.harvest()
        receipt=self.c.status()['last_decision']
        self.assertEqual(receipt['decision'],'QUESTION')
        self.assertEqual(receipt['http_status'],200);self.assertTrue(receipt['response_complete'])
        self.assertNotIn('question',receipt)
        self.assertIsNone(self.c.future.result()['question'])
        self.a.voice.assert_not_called()

    def test_actual_Agent_voice_authority_callback_has_no_MIC_reentry(self):
        from tests.test_conversation_mode import ConversationModeTests
        from reachy_companion.r42.sensory_bridge import SensoryBridge
        fixture=ConversationModeTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        a=fixture.agent()
        a.motion_policy.save(dict(motor_enabled=True,quiet=False,privacy_all=False))
        a.config['conversation']['sensory_loop']=dict(enabled=True,camera_enabled=True,caption_initiative_enabled=True,sound_decisions_enabled=False)
        a.sensory=SensoryBridge(a,start=False)
        self.addCleanup(a.sensory.loop.close);self.addCleanup(a.sensory.camera.close)
        a.initiative.schedule_enabled=True
        cap=a.sensory.caption_autonomy;key=cap.key()
        self.assertIsNotNone(key)
        done=threading.Event();fail=[]
        def call():
            try:a.voice('/say',dict(text='Вопрос?'),manual_authority=lambda:cap.valid(key,self.now+1e6))
            except Exception as exc:fail.append(exc)
            finally:done.set()
        thread=threading.Thread(target=call,daemon=True);thread.start()
        self.assertTrue(done.wait(1),'MIC lock callback reentry blocked real Agent.voice')
        self.assertEqual(fail,[])
        a.request.assert_called_once()

    def test_newer_caption_replaces_old_result_and_expiry_never_inflates(self):
        self.setup_caption();self.start();self.harvest()
        self.dto['frame_id']='b'*32
        self.a.initiative.maybe_run();self.a.voice.assert_not_called()
        self.assertIsNone(self.c.pending)
        self.assertEqual(self.decision.call_count,1)

    def test_raw_protocol_exact_model_closed_think_and_terminal_vs_unknown(self):
        config=dict(network=dict(llm_base_url='http://127.0.0.1:1234/v1'),llm=dict(model='loaded',mode='completion',api_path='/completions',
            message_template='<|im_start|>{role}\n{content}<|im_end|>\n',assistant_prefix='<|im_start|>assistant\n<think>\n\n</think>\n\n',stop=['<|im_end|>']))
        inventory=dict(models=[dict(key='loaded',capabilities=dict(vision=True),loaded_instances=[dict(id='instance',config=dict(parallel=4))])])
        from reachy_companion.r42 import snapshot_vision as V
        for mode in ('question','wait','invalid','transport'):
            calls=[];timeouts=[]
            answer='Что это за белая чашка?' if mode=='question' else 'НЕТ_ОСНОВАНИЯ'
            raw=(b'{bad' if mode=='invalid' else json.dumps(dict(model='loaded',choices=[dict(index=0,finish_reason='stop',text=answer)])).encode())
            class Connection:
                def __init__(self,*args,**kwargs):
                    timeouts.append(kwargs['timeout']);self.sock=SimpleNamespace(settimeout=timeouts.append)
                def connect(self):pass
                def request(self,method,path,body,headers):calls.append((path,json.loads(body)))
                def getresponse(self):
                    if mode=='transport':raise TimeoutError()
                    response=SimpleNamespace(status=200,length=len(raw))
                    def read1(n):
                        result=raw[len(raw)-response.length:len(raw)-response.length+n]
                        response.length-=len(result);return result
                    response.read1=read1
                    return response
                def close(self):pass
            with self.subTest(mode=mode),patch.object(V,'native_address',return_value=('127.0.0.1',1234)), \
                 patch.object(V,'get_models',return_value=inventory),patch.object(C.http.client,'HTTPConnection',Connection):
                result=C.decide(config,dict(observation={'summary':'чашка'}),threading.Event(),deadline=103,clock=lambda:100)
                self.assertEqual(calls[0][0],'/v1/completions')
                self.assertEqual(calls[0][1]['model'],'loaded')
                self.assertTrue(calls[0][1]['prompt'].endswith(config['llm']['assistant_prefix']))
                self.assertEqual(calls[0][1]['max_tokens'],192)
                self.assertLessEqual(max(timeouts),3)
                self.assertEqual(result['unknown'],mode=='transport')
                self.assertEqual(result['response_complete'],mode!='transport')
                if mode=='question':self.assertEqual(result['question'],answer)
                if mode=='wait':self.assertIsNone(result['question']);self.assertIsNone(result['failure'])
                if mode=='invalid':self.assertIsNotNone(result['failure'])


if __name__=='__main__':unittest.main()
