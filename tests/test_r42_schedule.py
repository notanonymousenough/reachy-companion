"""R42 lifecycle/authority regressions against the importable, packaged runtime."""
import ast,copy,hashlib,io,json,sys,unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock,patch
from reachy_companion.r42 import initiative as I
import r42_fixture as f
PROFILE=Path(I.__file__).resolve().parent
class ScheduleChecks(unittest.TestCase):
    setUp=f.Checks.setUp
    advance=f.Checks.advance
    arm=f.Checks.arm
    process=f.Checks.process
    foreground=f.Checks.foreground
    test_manual_CAS=f.Checks.test_arm_CAS_no_duplicate_pending_or_replayed_optin_fresh_authority
    test_existing_quiet=f.Checks.test_elapsed_clock_or_partial_speech_stale_receipt_and_no_new_PCM_never_trigger
    test_local_child=f.Checks.test_local_child_protocol_fresh_typed_guard_no_remote_admission
    test_existing_say=f.Checks.test_one_bounded_question_existing_frontdoor_no_transcript_or_extra_model
    test_late_result=f.Checks.test_snapshot_parent_dispatch_no_speech_after_STOP_and_no_replay
    test_cancel_child_reap=f.Checks.test_child_inference_is_cancelled_promptly_without_audio_or_queued_output

    def control(self,enabled=True):
        return self.a.initiative.schedule_control(dict(enabled=enabled,
            expected_generation=self.a.initiative.schedule_status()['generation'],
            operator_binding=dict(I.binding(self.value),expires_at_monotonic=self.now+59)))
    def run_one(self,delay=0,response=None):
        i=self.a.initiative
        def dispatch(generation):
            self.now+=delay
            return {'ok':True} if response is None else response
        with patch.object(i,'dispatch',side_effect=dispatch):
            i.maybe_run();self.advance();self.assertTrue(i.maybe_run())

    def test_default_off_and_original_schema(self):
        i=self.a.initiative
        self.assertIsNone(i.idle_deadline());self.assertFalse(i.schedule_status()['enabled'])
        self.assertEqual(set(i.status()),{'generation','state','once_per_arm','frame'})
        for _ in range(10):self.advance(100);self.assertFalse(i.maybe_run())
        self.assertEqual(self.call,0);self.a.voice.assert_not_called()

    def test_pending_off_then_new_on_has_new_child_no_cooldown(self):
        i=self.a.initiative;self.control();i.maybe_run();old=i.generation;policy=i.schedule_generation
        self.assertIsNone(i.schedule_child);self.assertEqual(i.deadline,0)
        self.control(False);self.assertFalse(i.schedule_enabled);self.assertFalse(i.valid(old))
        self.assertEqual(i.schedule_next_due,0);self.advance(1,10);i.maybe_run()
        self.assertEqual(self.call,0);self.control();self.assertGreater(i.schedule_generation,policy)
        self.assertEqual(i.generation,old);self.run_one()
        self.assertGreater(i.generation,old);self.assertFalse(i.valid(old))

    def test_cadence_variable_latency_and_off_on_preserves_completion_fence(self):
        i=self.a.initiative;self.control();self.run_one(delay=40)
        end=self.now;self.assertEqual(i.schedule_next_due,end+300)
        gen=i.generation;self.control(False);self.control()
        self.now=end+299.99;self.pump.counters['last_read_monotonic']=self.now
        for _ in range(3):self.assertFalse(i.maybe_run())
        self.assertEqual(i.generation,gen);self.assertEqual(self.call,1)
        self.now=end+300;self.pump.counters['last_read_monotonic']=self.now
        i.maybe_run();self.assertEqual(i.generation,gen);self.assertIsNone(i.schedule_child)
        self.assertEqual(i.deadline,0);self.assertEqual(i.schedule_status()['state'],'WAITING_FOR_IDLE')
        self.run_one(delay=5);self.assertEqual(self.call,2)
        self.assertEqual(i.generation,gen+1);self.assertEqual(i.schedule_next_due,self.now+300)

    def test_abstention_consumes_cadence_no_immediate_model_retry(self):
        i=self.a.initiative;self.control();self.run_one(response={'initiative_abstained':True})
        self.assertEqual(i.state,'abstained');due=i.schedule_next_due
        for _ in range(5):self.advance();i.maybe_run()
        self.assertEqual(self.call,1);self.assertTrue(i.schedule_enabled);self.assertGreater(due,self.now)

    def test_failure_disables_until_optin_and_reserves_cooldown(self):
        i=self.a.initiative;self.control();i.maybe_run();self.advance()
        with patch.object(i,'dispatch',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):i.maybe_run()
        self.assertEqual(i.state,'failed');self.assertFalse(i.schedule_enabled)
        self.assertEqual(i.schedule_next_due,self.now+300)
        self.advance(400,4000);i.maybe_run();self.assertEqual(self.call,1)
        self.control();i.maybe_run();self.assertEqual(i.state,'off');self.assertIsNone(i.schedule_child)

    def test_foreground_activity_resets_policy_quiet_without_creating_child(self):
        i=self.a.initiative;self.control();i.maybe_run();gen=i.generation
        self.advance(2,20);i.input_activity();self.assertIsNone(i.schedule_quiet)
        self.assertTrue(i.schedule_enabled);i.maybe_run();self.advance(2.9,29);i.maybe_run()
        self.assertEqual(i.generation,gen);self.assertEqual(i.deadline,0);self.assertEqual(self.call,0)
        self.advance(.2,2)
        with patch.object(i,'dispatch',return_value={'ok':True}):self.assertTrue(i.maybe_run())
        self.assertEqual(self.call,1);self.assertEqual(i.generation,gen+1)

    def test_foreground_beyond_old_TTL_keeps_policy_without_child_then_dispatches_once(self):
        i=self.a.initiative;self.control();i.maybe_run();generation=i.generation
        for phase in ('processing','speaking','processing'):
            self.foreground(phase);self.advance(40,400);i.input_activity();i.maybe_run()
            self.assertTrue(i.schedule_enabled);self.assertEqual(i.schedule_status()['state'],'WAITING_FOR_IDLE')
            self.assertEqual(i.generation,generation);self.assertIsNone(i.schedule_child)
            self.assertEqual(i.deadline,0);self.assertIsNone(i.expected);self.assertIsNone(i.frame)
            self.assertEqual(self.call,0);self.a.voice.assert_not_called()
        self.foreground('listening');i.maybe_run();self.advance(2.9,29)
        self.assertFalse(i.maybe_run());self.assertEqual(i.generation,generation)
        self.advance(.2,2);commit=self.now
        def dispatch(child):
            self.assertEqual(child,generation+1);self.assertEqual(i.state,'running')
            self.assertEqual(i.schedule_child,child);self.assertEqual(i.deadline,commit+59)
            return {'ok':True}
        with patch.object(i,'dispatch',side_effect=dispatch) as run:self.assertTrue(i.maybe_run())
        run.assert_called_once();self.assertEqual(self.call,1);self.assertEqual(i.state,'done')
        self.assertEqual(i.schedule_next_due,self.now+300);self.assertTrue(i.schedule_enabled)
        self.assertFalse(i.maybe_run());self.assertEqual(self.call,1)

    def test_authority_withdrawal_including_malformed_policy_during_cooldown(self):
        changes=[('agent_boot_id','new'),('microphone_epoch',304),('microphone_owner_id','foreign'),
                 ('motion_policy_owner_id','foreign'),('microphone_enabled',False),('listening',False),
                 ('microphone_state_error','bad'),('motion_policy','bad')]
        changes += [('policy.'+k,v) for k,v in [('epoch',143),('quiet',True),('privacy_all',True),('epoch',True)]]
        for key,value in changes:
            with self.subTest(key=key,value=value):
                self.setUp();i=self.a.initiative;self.control();i.schedule_next_due=self.now+300
                if key.startswith('policy.'):self.value['motion_policy'][key[7:]]=value
                else:self.value[key]=value
                i.maybe_run();self.assertFalse(i.schedule_enabled);self.assertEqual(self.call,0)
                self.doCleanups()

    def test_stop_disables_pending_and_cooldown_and_newboot_default_off(self):
        i=self.a.initiative;self.control();i.maybe_run();i.cancel('STOP')
        self.assertFalse(i.schedule_enabled);self.advance(400,4000);i.maybe_run();self.assertEqual(self.call,0)
        self.assertFalse(I.Initiative(self.a).schedule_enabled)
        self.control();i.schedule_next_due=self.now+300;self.a.stopping.set();i.maybe_run()
        self.assertFalse(i.schedule_enabled)

    def test_foreign_manual_never_stolen_and_manual_requires_explicit_off(self):
        i=self.a.initiative;self.arm()
        with self.assertRaises(RuntimeError):self.control()
        self.control(False);self.assertEqual(i.state,'armed');self.assertEqual(i.generation,1)
        i.cancel();self.control()
        with self.assertRaises(RuntimeError):i.arm(dict(self.payload,expected_generation=i.generation))
        self.assertTrue(i.schedule_enabled);self.assertNotEqual(i.state,'armed')
        # Unknown/foreign child during a scheduler tick only withdraws scheduler.
        i.state='armed';i.generation+=1;i.schedule_child=None
        i.schedule_tick();self.assertFalse(i.schedule_enabled);self.assertEqual(i.state,'armed')

    def test_stale_tick_cannot_withdraw_new_lease(self):
        i=self.a.initiative;self.control();old=i.schedule_generation
        self.control(False);self.control();new=i.schedule_generation
        i.schedule_withdraw('stale',old)
        self.assertTrue(i.schedule_enabled);self.assertEqual(i.schedule_generation,new)

    def test_on_exact_schema_fresh_binding_and_null_owner(self):
        i=self.a.initiative
        p=dict(self.payload,operator_binding=dict(self.payload['operator_binding']))
        for bad in [dict(p,enabled=1),dict(p,expected_generation=True),dict(p,extra=1),
                    dict(p,operator_binding=dict(p['operator_binding'],expires_at_monotonic=161.))]:
            with self.assertRaises(ValueError):i.schedule_control(bad)
        self.a.microphone_owner_id=self.a.motion_policy.owner_id='owned'
        self.value['microphone_owner_id']=self.value['motion_policy_owner_id']='owned'
        with self.assertRaises(RuntimeError):self.control()
        self.assertFalse(i.schedule_enabled)

    def test_final_admission_CAS_and_authority_recheck(self):
        i=self.a.initiative;self.control();i.maybe_run();generation=i.schedule_generation;self.advance()
        original=i._schedule_commit
        def raced(*args):
            self.a.microphone_epoch+=1
            return original(*args)
        with patch.object(i,'_schedule_commit',side_effect=raced):i.maybe_run()
        self.assertFalse(i.schedule_enabled);self.assertEqual(self.call,0);self.assertEqual(i.state,'off')
        self.assertGreater(i.schedule_generation,generation);self.assertIsNone(i.schedule_child)

    def test_fractional_clock_stays_within_strict_60s_deadline(self):
        self.now=105.10000000000001;self.pump.counters['last_read_monotonic']=self.now
        self.control();i=self.a.initiative;i.maybe_run();self.advance()
        def dispatch(child):
            self.assertTrue(i.valid(child));self.assertLessEqual(i.deadline-self.now,59)
            return {'ok':True}
        with patch.object(i,'dispatch',side_effect=dispatch):self.assertTrue(i.maybe_run())
        self.assertTrue(i.schedule_enabled)

    def test_stale_manual_off_cannot_disable_new_schedule(self):
        i=self.a.initiative;self.control();i.maybe_run()
        with self.assertRaises(RuntimeError):i.arm(dict(self.payload,enabled=False,expected_generation=9))
        self.assertTrue(i.schedule_enabled);self.assertEqual(i.state,'off')
        i.arm(dict(self.payload,enabled=False,expected_generation=i.generation))
        self.assertFalse(i.schedule_enabled);self.assertEqual(i.state,'cancelled')

    def test_scheduled_late_child_result_after_off_never_calls_voice(self):
        i=self.a.initiative;self.control();i.maybe_run();old=i.generation;self.advance()
        process=self.process()
        def communicate(*args,**kw):
            self.control(False)
            return json.dumps(self.result).encode(),None
        process.communicate.side_effect=communicate
        with patch.object(I.subprocess,'Popen',return_value=process):self.assertTrue(i.maybe_run())
        self.assertFalse(i.valid(old));self.assertFalse(i.schedule_enabled)
        self.a.voice.assert_not_called();self.assertIsNone(i.frame)
        self.assertEqual(i.schedule_next_due,self.now+300)
        self.advance(400,4000);i.maybe_run();self.assertEqual(self.call,1)

    def test_real_http_auth_bounds_duplicate_decode_and_schema(self):
        import hmac,logging,types
        from http.server import BaseHTTPRequestHandler
        tree=ast.parse((PROFILE/'agent.py').read_text())
        handler=next(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and n.name=='Handler')
        scope=dict(BaseHTTPRequestHandler=BaseHTTPRequestHandler,hmac=hmac,json=json,
                   config=self.a.config,agent=self.a,LOG=logging.getLogger('r42-test'),__package__='reachy_companion.r42')
        exec(compile(ast.Module(body=[handler],type_ignores=[]),'exact-R42-Handler','exec'),scope)
        h=scope['Handler'].__new__(scope['Handler']);h.reply=Mock();h.path='/initiative/schedule'
        h.headers={};h.do_GET();self.assertEqual(h.reply.call_args.args[0],401)
        h.reply.reset_mock();h.do_POST();self.assertEqual(h.reply.call_args.args[0],401)
        h.headers={'Authorization':'Bearer '+self.a.config.token};h.reply.reset_mock();h.do_GET()
        self.assertEqual(h.reply.call_args.args,(200,self.a.initiative.schedule_status()))
        data=json.dumps(self.payload).encode();h.headers['Content-Length']=str(len(data));h.rfile=io.BytesIO(data)
        h.do_POST();self.assertEqual(h.reply.call_args.args[0],200);self.assertTrue(self.a.initiative.schedule_enabled)
        for data in (b'{"enabled":true,"enabled":false}',b'{}',b'{"enabled":NaN}'):
            h.headers['Content-Length']=str(len(data));h.rfile=io.BytesIO(data)
            with self.assertLogs('r42-test',level='ERROR'):h.do_POST()
            self.assertEqual(h.reply.call_args.args[0],409)
        h.headers['Content-Length']='4097'
        with self.assertLogs('r42-test',level='ERROR'):h.do_POST()
        self.assertEqual(h.reply.call_args.args[0],409)
        self.assertTrue(self.a.initiative.schedule_enabled)

    def test_real_listening_stop_hook_revokes_schedule(self):
        i=self.a.initiative;self.control();i.maybe_run()
        tree=ast.parse((PROFILE/'agent.py').read_text())
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='set_listening')
        scope=dict(time=I.time,math=I.math,nullcontext=nullcontext)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'exact-R42-stop','exec'),scope)
        import threading
        self.pump.retired=threading.Event();self.pump.close=Mock()
        scope['set_listening'](self.a,False,{})
        self.assertFalse(i.schedule_enabled);self.assertEqual(i.state,'off')
        self.assertFalse(self.a.listening.is_set())

    def test_cooldown_idle_deadline_no_periodic_http_loop(self):
        i=self.a.initiative;self.assertIsNone(i.idle_deadline())
        self.control();self.assertEqual(i.idle_deadline(),self.now+.25)
        self.run_one(delay=40);due=i.schedule_next_due
        self.assertEqual(i.idle_deadline(),due)
        self.advance(200,2000);self.assertEqual(i.idle_deadline(),due)
        self.now=due;self.assertEqual(i.idle_deadline(),due+.25)
        i.maybe_run();self.assertEqual(i.state,'off');self.assertIsNone(i.schedule_child);self.assertEqual(i.idle_deadline(),self.now+.25)
        self.control(False);self.assertIsNone(i.idle_deadline());self.assertTrue(i.wake.is_set())

    def test_off_rejects_old_boot_epoch_owner_even_matching_schedule_CAS(self):
        i=self.a.initiative;self.control();i.maybe_run()
        for key,value in [('agent_boot_id','oldboot'),('microphone_epoch',302),('policy_epoch',141),('owner_id','foreign')]:
            p=dict(enabled=False,expected_generation=i.schedule_generation,
                   operator_binding=dict(I.binding(self.value),expires_at_monotonic=self.now+59))
            p['operator_binding'][key]=value
            with self.assertRaises(RuntimeError):i.schedule_control(p)
            self.assertTrue(i.schedule_enabled);self.assertEqual(i.state,'off')
        self.control(False);self.assertFalse(i.schedule_enabled)

    def test_cleanup_helper_error_cannot_mask_original_agent_error(self):
        tree=ast.parse((PROFILE/'agent.py').read_text())
        handler=next(n for n in ast.walk(tree) if isinstance(n,ast.ExceptHandler)
            and any(isinstance(x,ast.Constant) and x.value=='audio_loop_error' for x in ast.walk(n)))
        cleanup=handler.body[0]
        self.assertIsInstance(cleanup,ast.Try)
        a=type('Fake',(),{})();a.initiative=Mock()
        a.initiative.schedule_withdraw.side_effect=RuntimeError('cleanup')
        log=Mock();scope=dict(self=a,LOG=log)
        exec(compile(ast.Module(body=[cleanup],type_ignores=[]),'exact-R42-cleanup','exec'),scope)
        log.exception.assert_called_once_with('schedule_cleanup_failed')

    def test_manual_arm_still_expires_at_original_deadline(self):
        self.arm();i=self.a.initiative;deadline=i.deadline
        self.advance(20,200);i.input_activity();self.assertEqual(i.deadline,deadline)
        self.now=deadline;i.maybe_run();self.assertEqual(i.state,'cancelled')
        self.assertEqual(self.call,0);self.assertFalse(i.schedule_enabled)

    def test_scheduled_postcommit_expiry_is_final_and_consumes_cadence(self):
        i=self.a.initiative;self.control();i.maybe_run();self.advance()
        def dispatch(child):
            self.now=i.deadline
            return {'cancelled':True}
        with patch.object(i,'dispatch',side_effect=dispatch):self.assertTrue(i.maybe_run())
        self.assertFalse(i.schedule_enabled);self.assertEqual(i.state,'cancelled')
        self.assertEqual(i.schedule_next_due,self.now+300)
        self.advance(400,4000);i.maybe_run();self.assertEqual(self.call,1)

    def test_every_existing_quiet_predicate_blocks_child_creation(self):
        changes=[(self.pump.assembler,'frames',[b'partial']), (self.pump,'latest',object()),
            (self.pump,'output_active',True),(self.pump,'suppress_until',self.now+10),
            (self.pump,'error','error'),(self.a,'calibrated',False),(self.a.sounds,'music',True),
            (self.a,'capture_active',False),(self.a,'pending_pcm',object()),
            (self.a,'resume_audio',object()),(self.a,'playback_process',object()),(self.a,'voice_response',object())]
        i=self.a.initiative;self.control()
        for obj,key,value in changes:
            with self.subTest(field=key):
                old=getattr(obj,key);setattr(obj,key,value)
                i.maybe_run();self.advance();i.maybe_run()
                self.assertTrue(i.schedule_enabled);self.assertIsNone(i.schedule_child)
                self.assertEqual(i.generation,0);self.assertEqual(i.deadline,0);self.assertEqual(self.call,0)
                setattr(obj,key,old)
        self.a.audio_lock.release();i.maybe_run();self.advance();i.maybe_run()
        self.assertEqual(i.generation,0);self.a.audio_lock.acquire()
        i.maybe_run();self.advance(seen=0);i.maybe_run();self.assertEqual(i.generation,0)
        self.now+=4;i.maybe_run();self.assertEqual(i.generation,0)  # stale receipt
        self.pump.counters['last_read_monotonic']=self.now;i.maybe_run()
        self.advance();self.pump.generation+=1;i.maybe_run();self.assertEqual(i.generation,0)
        self.run_one();self.assertEqual(self.call,1)

    def test_foreground_arrives_at_final_admission_and_resets_quiet(self):
        i=self.a.initiative;self.control();i.maybe_run();self.advance()
        original=i._schedule_commit
        def raced(*args):
            self.a.pending_pcm=(303,object())
            return original(*args)
        with patch.object(i,'_schedule_commit',side_effect=raced):self.assertFalse(i.maybe_run())
        self.assertTrue(i.schedule_enabled);self.assertEqual(i.generation,0);self.assertIsNone(i.schedule_quiet)
        self.a.pending_pcm=None;self.run_one();self.assertEqual(self.call,1)

    def test_scheduled_dispatch_reuses_same_fresh_frame_model_and_say(self):
        i=self.a.initiative;self.control();i.maybe_run();self.advance()
        process=self.process()
        with patch.object(I.subprocess,'Popen',return_value=process):self.assertTrue(i.maybe_run())
        packet=json.loads(process.communicate.call_args.args[0])
        self.assertEqual(packet['config']['llm']['model'],'existing-9B')
        self.assertEqual(packet['generation'],1);self.assertEqual(packet['deadline'],self.now+59)
        self.assertEqual(i.frame['frame_id'],'a'*32)
        self.a.voice.assert_called_once_with('/say',dict(text=self.result['final_text'],session='existing'),
            expected_epoch=303,expected_policy_epoch=142,valid_until=159.,allow_barge_in=False,initiative_generation=1)
        self.assertEqual(self.call,1);self.assertTrue(i.schedule_enabled)

    def test_off_after_long_foreground_is_final_and_new_on_restarts_quiet(self):
        i=self.a.initiative;self.control();i.maybe_run()
        self.foreground('processing');self.advance(120,1200);i.input_activity();i.maybe_run()
        self.control(False);self.assertFalse(i.schedule_enabled);self.assertIsNone(i.schedule_quiet)
        self.foreground('listening');self.advance(4,40);i.maybe_run()
        self.assertEqual(self.call,0);self.assertIsNone(i.schedule_child)
        self.control();i.maybe_run();self.advance(2.9,29);i.maybe_run()
        self.control(False);self.control();i.maybe_run();self.advance(.2,2)
        self.assertFalse(i.maybe_run());self.assertEqual(i.generation,0)
        self.advance(2.9,29)
        with patch.object(i,'dispatch',return_value={'ok':True}):self.assertTrue(i.maybe_run())
        self.assertEqual(self.call,1)

    def test_manual_PCM_deferral_keeps_same_generation_and_deadline(self):
        self.arm();i=self.a.initiative;i.maybe_run();generation=i.generation;deadline=i.deadline
        self.advance(2.9,29);i.input_activity();i.maybe_run();self.advance(2.9,29)
        self.assertFalse(i.maybe_run());self.assertEqual(i.generation,generation);self.assertEqual(i.deadline,deadline)
        self.advance(.2,2)
        with patch.object(i,'dispatch',return_value={'ok':True}):self.assertTrue(i.maybe_run())
        self.assertEqual(i.generation,generation);self.assertEqual(self.call,1)

    def test_same_model_camera_say_and_core_guards_preserved(self):
        from reachy_companion.r42 import verify
        manifest=verify()
        # Agent now includes the delivered R50 controls and persisted mode.
        # Verify its current packaged identity rather than the R42 preimage.
        self.assertEqual(manifest['files']['agent.py'],hashlib.sha256((PROFILE/'agent.py').read_bytes()).hexdigest())
        self.assertGreaterEqual(manifest['version'],7)
        self.assertEqual(manifest['files']['initiative.py'],hashlib.sha256(Path(I.__file__).read_bytes()).hexdigest())
        self.assertIn('R43',manifest['provenance']['initiative.py']['adaptation'])
        # The pump also includes later delivered barge-in changes. The manifest
        # must identify the packaged implementation, not its R42 ancestor.
        self.assertEqual(manifest['files']['capture_pump.py'],hashlib.sha256((PROFILE/'capture_pump.py').read_bytes()).hexdigest())
        self.assertEqual(manifest['files']['snapshot_vision.py'],'04e63d85d9ce458248d78ef029076878e556f111bfa46a2e8597366721e78e06')
        self.assertEqual(I.PURPOSE,'Задай один короткий вопрос по новому кадру.')
        self.assertEqual(I.NO_BASIS,'НЕТ_ОСНОВАНИЯ')
