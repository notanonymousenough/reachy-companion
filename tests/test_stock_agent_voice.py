"""Production Agent/worker/Hub glue with synthetic IO, never hardware acceptance."""
import base64
import copy
import json
import io
from email.message import Message
import subprocess
import sys
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

import test_stock_motion_routing as stock_fixture
from reachy_companion.expressions import plan


class StockAgentVoiceTests(unittest.TestCase):
    setUpFixture = stock_fixture.StockMotionTests.setUp
    factory = stock_fixture.StockMotionTests.factory

    def setUp(self):
        self.setUpFixture()
        self.config.data['conversation'].update(listen_on_start=False,wake_on_start=False,greet_on_start=False)
        self.config.data['conversation']['barge_in']['enabled']=False
        self.config.data['conversation']['barge_in']['confirm_with_stt']=False
        self.config.data['conversation']['sound_reactions']['enabled']=False
        self.config.data['conversation']['interaction']['acknowledgements']['enabled']=False
        settings=self.config.data['conversation']['expressions']
        settings.update(max_steps=2,max_head_degrees=2,max_antenna_degrees=2,duration_seconds=.5,settle_seconds=.1)
        self.config.data['audio'].update(echo_tail_seconds=0,min_voiced_chunks=1,silence_chunks=1)
        self.config.data['timeouts']['move']=1
        with patch.dict(sys.modules,{'webrtcvad':types.SimpleNamespace(Vad=lambda mode:Mock(is_speech=lambda b,rate:any(b)))}):
            from reachy_companion.agent import Agent
        with patch('reachy_companion.agent.webrtcvad.Vad',return_value=Mock(is_speech=lambda b,rate:any(b))):
            self.agent=Agent(self.config)
        self.addCleanup(self.cleanup_agent)
        self.agent.set_motion_policy(dict(motor_enabled=True,quiet=False,privacy_all=False))
        self.agent.set_microphone(True,listen=False)
        self.agent.calibrated=True
        self.agent.playback_configured=True
        self.hub.agent=Mock(side_effect=lambda path:self.agent.operator_status())
        self.rpc_entered=threading.Event();self.rpc_release=None;self.rpc=[]
        self.plan_entered=threading.Event();self.plan_release=None
        self.pipeline=None
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path=='/health':self.reply(dict(ok=True))
                elif self.path=='/status':self.reply(fixture.hub.status())
                else:self.send_error(404)
            def reply(self,value,status=200):
                body=json.dumps(value).encode()
                self.send_response(status);self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            def do_POST(self):
                if self.headers.get('Authorization')!='Bearer '+fixture.config.token:
                    self.reply({},401);return
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.rpc.append((self.path,copy.deepcopy(payload)))
                if self.path=='/expression/plan':
                    fixture.plan_entered.set()
                    if fixture.plan_release:fixture.plan_release.wait(2)
                    self.reply(plan(settings,**payload));return
                if self.path=='/actions/expression':
                    fixture.rpc_entered.set()
                    if fixture.rpc_release:fixture.rpc_release.wait(2)
                    try:self.reply(fixture.hub.expression(payload))
                    except Exception as exc:self.reply(dict(error=type(exc).__name__),409)
                    return
                if self.path=='/stream/turn':
                    fixture.assertFalse(fixture.agent.capture_active)
                    self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.end_headers()
                    for event in fixture.pipeline.stream(payload,'/turn'):
                        self.wfile.write(json.dumps(event).encode()+b'\n');self.wfile.flush()
                    return
                self.send_error(404)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server_thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.server_thread.start()
        self.addCleanup(self.cleanup_server)
        url='http://127.0.0.1:'+str(self.server.server_port)
        self.config.data['network'].update(voice_url=url,hub_url=url)

    def cleanup_agent(self):
        if self.rpc_release:self.rpc_release.set()
        if self.plan_release:self.plan_release.set()
        self.agent.stopping.set()
        self.agent.expressions.hold()
        self.agent.expressions.thread.join(2)

    def cleanup_server(self):
        if self.rpc_release:self.rpc_release.set()
        self.cleanup_agent()
        self.server.shutdown();self.server.server_close();self.server_thread.join(2)

    def wait(self,predicate):
        end=time.monotonic()+2
        while not predicate() and time.monotonic()<end:time.sleep(.002)
        self.assertTrue(predicate())

    def test_late_http_after_hold_denies_before_any_factory_post(self):
        self.rpc_release=threading.Event()
        self.agent.expressions.set('speaking')
        self.assertTrue(self.rpc_entered.wait(1))
        payload=next(body for path,body in self.rpc if path=='/actions/expression')
        original=payload['operator_binding']['expression_version']
        self.agent.expressions.hold()
        self.assertGreater(self.agent.expressions.version,original)
        self.rpc_release.set()
        self.wait(lambda:self.agent.expressions.last_error is not None)
        self.assertEqual(self.writes,[])
        self.assertFalse(self.hub.lock.locked())

    def test_held_compute_plan_drops_before_hub_dispatch(self):
        self.plan_release=threading.Event()
        self.agent.expressions.set('speaking')
        self.assertTrue(self.plan_entered.wait(1))
        self.agent.expressions.hold()
        version=self.agent.expressions.version
        self.plan_release.set()
        self.wait(lambda:self.agent.expressions.completed>=version)
        self.assertFalse(any(path=='/actions/expression' for path,_ in self.rpc))
        self.assertEqual(self.writes,[])

    def test_hold_while_binding_is_captured_cannot_enqueue_old_phase(self):
        entered=threading.Event();release=threading.Event()
        original=self.agent.expressions.binding
        def binding():
            value=original();entered.set();release.wait(2);return value
        self.agent.expressions.binding=binding
        thread=threading.Thread(target=lambda:self.agent.expressions.set('speaking'))
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.agent.expressions.hold()
            version=self.agent.expressions.version
        finally:release.set();thread.join(2)
        self.assertEqual(self.agent.expressions.version,version)
        self.assertIsNone(self.agent.expressions.state)
        self.assertEqual(self.rpc,[])

    def test_midmove_hold_same_microphone_epoch_stops_only_owned_and_no_next_step(self):
        from reachy_companion.barge_in import BargeInMonitor
        epoch=self.agent.microphone_epoch
        self.on_poll=lambda:None
        monitor=BargeInMonitor(self.agent)
        self.on_post=monitor.trigger
        self.agent.expressions.set('speaking')
        self.wait(lambda:self.hub.stock_stop_observed is True)
        self.assertEqual(self.agent.microphone_epoch,epoch)
        self.assertTrue(self.agent.motor_permitted())
        self.assertTrue(monitor.interrupted.is_set())
        self.assertEqual(self.agent.interruptions,1)
        self.assertEqual([path for path,_ in self.writes],['/api/move/goto','/api/move/stop'])
        self.assertEqual(self.writes[-1][1],dict(uuid=stock_fixture.OWN))

    def test_late_binding_changed_epoch_or_restart_boot_never_revives(self):
        self.agent.expressions.set('speaking')
        self.wait(lambda:self.agent.expressions.completed>=1)
        payload=next(body for path,body in self.rpc if path=='/actions/expression')
        self.writes.clear()
        for field in ('microphone_epoch','policy_epoch','agent_boot_id'):
            stale=copy.deepcopy(payload)
            stale['operator_binding'][field]='old-boot' if field=='agent_boot_id' else stale['operator_binding'][field]+1
            with self.assertRaises(RuntimeError) as error:self.hub.expression(stale)
            self.assertNotIn('old-boot',str(error.exception))
            self.assertIn(dict(microphone_epoch='mic_epoch',policy_epoch='policy_epoch',agent_boot_id='boot')[field],
                str(error.exception))
        self.assertEqual(self.writes,[])

    def test_binding_missing_fields_none_bool_and_malformed_operator_version_deny(self):
        step=plan(self.config['conversation']['expressions'],'neutral')['steps']
        valid=dict(self.agent.expression_binding(),expression_version=self.agent.expressions.version)
        invalid=[None,{},dict(valid,expression_version=True),dict(valid,microphone_epoch=True),dict(valid,policy_epoch=True),
                 dict(valid,microphone_enabled=1)]
        for binding in invalid:
            with self.assertRaises(RuntimeError):self.hub.expression(dict(steps=step,operator_binding=binding))
        self.hub.agent=Mock(return_value=dict(self.agent.operator_status(),expression_version=True))
        with self.assertRaises(RuntimeError):self.hub.expression(dict(steps=step,operator_binding=valid))
        self.assertEqual(self.writes,[])

    def test_failed_neutral_expression_completes_wait_and_does_not_prevent_capture(self):
        self.hub.stock_unknown=True
        self.agent.listening.set()
        capture=b'\xff\x1f'*(self.agent.chunk_bytes//2)+b'\0'*self.agent.chunk_bytes
        real_popen=subprocess.Popen;processes=[]
        def popen(command,*args,**kwargs):
            self.assertEqual(command[0],'arecord')
            process=real_popen([sys.executable,'-c',
                'import sys,time;sys.stdout.buffer.write(bytes.fromhex(sys.argv[1]));sys.stdout.flush();time.sleep(2)',
                capture.hex()],*args,**kwargs)
            processes.append(process);return process
        with patch('reachy_companion.agent.subprocess.Popen',side_effect=popen):
            actual=self.agent.capture()
        self.assertEqual(actual,capture)
        self.assertTrue(self.rpc_entered.is_set())
        self.assertEqual(self.writes,[])
        self.assertTrue(all(process.poll() is not None for process in processes))
        self.assertFalse(self.agent.capture_active)

    def test_capture_opens_and_pcm_completes_while_neutral_http_is_still_blocked(self):
        self.rpc_release=threading.Event()
        self.agent.expressions.set('neutral')
        self.assertTrue(self.rpc_entered.wait(1))
        self.agent.listening.set()
        capture=b'\xff\x1f'*(self.agent.chunk_bytes//2)+b'\0'*self.agent.chunk_bytes
        real_popen=subprocess.Popen;opened=threading.Event();processes=[];result=[];errors=[]
        def popen(command,*args,**kwargs):
            self.assertEqual(command[0],'arecord')
            process=real_popen([sys.executable,'-c',
                'import sys,time;data=bytes.fromhex(sys.argv[1]);n=int(sys.argv[2]);'
                'sys.stdout.buffer.write(data[:n]);sys.stdout.flush();time.sleep(.03);'
                'sys.stdout.buffer.write(data[n:]);sys.stdout.flush();time.sleep(2)',
                capture.hex(),str(self.agent.chunk_bytes)],*args,**kwargs)
            processes.append(process);opened.set();return process
        def capture_once():
            try:result.append(self.agent.capture())
            except BaseException as exc:errors.append(exc)
        with patch('reachy_companion.agent.subprocess.Popen',side_effect=popen):
            thread=threading.Thread(target=capture_once,daemon=True);thread.start()
            try:
                self.assertTrue(opened.wait(.5))
                thread.join(1)
                self.assertFalse(thread.is_alive())
                self.assertFalse(self.rpc_release.is_set())
                self.assertEqual(result,[capture]);self.assertEqual(errors,[])
                self.assertEqual(self.writes,[])
                self.assertTrue(all(process.poll() is not None for process in processes))
            finally:self.rpc_release.set();thread.join(2)

    def test_muted_capture_and_epoch_change_before_open_deny_audio_process(self):
        self.agent.microphone.enabled=False
        self.agent.listening.set() # A stale event cannot grant a muted mic.
        with patch('reachy_companion.agent.subprocess.Popen') as popen:
            self.assertIsNone(self.agent.capture());popen.assert_not_called()
        self.agent.microphone.enabled=True
        def change_epoch(*args,**kwargs):self.agent.microphone_epoch+=1
        with patch.object(self.agent.expressions,'set',side_effect=change_epoch),patch(
                'reachy_companion.agent.subprocess.Popen') as popen:
            self.assertIsNone(self.agent.capture());popen.assert_not_called()

    def test_mute_or_epoch_change_after_process_open_returns_no_pcm_and_reaps_process(self):
        real_popen=subprocess.Popen
        for change in ('mute','epoch'):
            self.agent.microphone.enabled=True;self.agent.listening.set();processes=[]
            def popen(command,*args,**kwargs):
                process=real_popen([sys.executable,'-c','import time;time.sleep(2)'],*args,**kwargs)
                processes.append(process)
                if change=='mute':self.agent.microphone.enabled=False
                else:self.agent.microphone_epoch+=1
                return process
            with patch('reachy_companion.agent.subprocess.Popen',side_effect=popen):
                self.assertIsNone(self.agent.capture())
            self.assertTrue(all(process.poll() is not None for process in processes))
            self.assertFalse(self.agent.capture_active)
    def test_actual_capture_run_worker_stream_playback_and_stock_expression(self):
        piper=types.ModuleType('piper');piper.PiperVoice=piper.SynthesisConfig=object
        vosk=types.ModuleType('vosk');vosk.Model=vosk.KaldiRecognizer=vosk.SetLogLevel=object
        with patch.dict(sys.modules,{'piper':piper,'vosk':vosk}):
            from reachy_companion.voice import Pipeline
        pipeline=Pipeline.__new__(Pipeline);self.pipeline=pipeline
        pipeline.config=self.config;pipeline.lock=threading.Lock();pipeline.sessions={};pipeline.agent_sessions={}
        pipeline.check_robot=Mock();pipeline.transcribe=Mock(return_value='fixture fresh microphone question')
        pipeline.classify=Mock(return_value=dict(action='answer',emotion='neutral',intent='other'))
        step=plan(self.config['conversation']['expressions'],'neutral')['steps']
        def audio_events(*args,**kwargs):
            yield dict(type='motion',cues=[dict(at=0,steps=step)])
            yield dict(type='audio',format='S16_LE',sample_rate=self.config['streaming']['sample_rate'],
                channels=1,pcm_base64=base64.b64encode(b'\0\0'*160).decode())
        pipeline.audio_events=audio_events
        capture=(b'\xff\x1f'* (self.agent.chunk_bytes//2)+b'\0'*self.agent.chunk_bytes)
        real_popen=subprocess.Popen;processes=[]
        def popen(command,*args,**kwargs):
            if command[0]=='arecord':
                script='import sys,time;sys.stdout.buffer.write(bytes.fromhex(sys.argv[1]));sys.stdout.flush();time.sleep(2)'
                replacement=[sys.executable,'-c',script,capture.hex()]
            elif command[0]=='aplay':replacement=[sys.executable,'-c','import sys;sys.stdin.buffer.read()']
            else:raise AssertionError(command)
            process=real_popen(replacement,*args,**kwargs);processes.append((command[0],process));return process
        original_voice=self.agent.voice
        def one_turn(*args,**kwargs):
            try:return original_voice(*args,**kwargs)
            finally:self.agent.stopping.set()
        self.agent.voice=one_turn
        self.agent.listening.set()
        watchdog=threading.Timer(5,self.agent.stopping.set);watchdog.start()
        try:
            with patch('reachy_companion.agent.subprocess.Popen',side_effect=popen),patch(
                    'reachy_companion.brains.answer',return_value='A synthetic backend answer.') as backend:
                self.agent.run()
        finally:watchdog.cancel()
        self.assertEqual(self.agent.turns,1)
        self.assertIsNone(self.agent.last_error)
        pipeline.transcribe.assert_called_once()
        self.assertEqual(pipeline.transcribe.call_args.args[0],capture)
        backend.assert_called_once()
        self.assertEqual(backend.call_args.args[1][-1]['content'],'fixture fresh microphone question')
        self.assertTrue(any(path=='/stream/turn' for path,_ in self.rpc))
        self.assertTrue(any(path=='/actions/expression' for path,_ in self.rpc))
        self.assertTrue(self.writes)
        self.assertTrue(all('operator_binding' in body for path,body in self.rpc if path=='/actions/expression'))
        self.assertEqual([name for name,_ in processes],['arecord','aplay'])
        self.assertTrue(all(process.poll() is not None for _,process in processes))
        self.assertFalse(self.agent.capture_active)
        self.assertIsNone(self.agent.playback_process)
        self.assertIsNone(self.agent.voice_response)
        self.assertFalse(self.agent.motion_proxy.enabled)

    def test_spoken_text_echo_reference_typed_fallback_and_alice_short_reply_selfecho(self):
        from reachy_companion.barge_in import BargeInMonitor
        self.config.data['conversation']['expressions']['enabled']=False
        cases=[({},'да'),({'spoken_text':None},'да'),({'spoken_text':42},'да'),
               ({'spoken_text':''},'да'),({'spoken_text':' '},'да'),
               ({'spoken_text':'x'*(self.config['limits']['max_speech_chars']+1)},'да'),
               ({'spoken_text':'Алиса, да'},'Алиса, да')]
        for extra,expected in cases:
            events=[dict(type='reply',reply='да',**extra),dict(type='done',ok=True,reply='да')]
            response=io.BytesIO(b''.join(json.dumps(event).encode()+b'\n' for event in events))
            response.headers=Message();response.headers['Content-Type']='application/x-ndjson'
            with patch.object(self.agent.http,'open',return_value=response):self.agent.voice('/turn',{})
            self.assertEqual(self.agent.current_reply_text.strip(),expected)
        self.config.data['conversation']['barge_in']['confirm_with_stt']=True
        with patch.object(self.agent,'request',return_value=dict(transcript='Алиса, да',decision=dict(action='answer'))):
            monitor=BargeInMonitor(self.agent)
            self.assertFalse(monitor.trigger(b'fixture'))
            self.assertFalse(monitor.interrupted.is_set())
        self.assertEqual(self.agent.interruptions,0)

    def test_late_reply_after_epoch_change_never_updates_echo_reference(self):
        self.config.data['conversation']['expressions']['enabled']=False
        fixture=self
        class Response(io.BytesIO):
            def readline(self,*args):
                result=super().readline(*args)
                if change=='mic':fixture.agent.microphone_epoch+=1
                else:fixture.agent.set_motion_policy(dict(motor_enabled=True,quiet=False,privacy_all=False))
                return result
        for change in ('mic','policy'):
            response=Response(json.dumps(dict(type='reply',reply='old',spoken_text='Алиса, stale')).encode()+b'\n')
            response.headers=Message();response.headers['Content-Type']='application/x-ndjson'
            with patch.object(self.agent.http,'open',return_value=response):result=self.agent.voice('/turn',{})
            self.assertTrue(result['cancelled']);self.assertEqual(self.agent.current_reply_text,'')

    def test_agent_profile_address_forwarded_explicitly_for_unary_and_stream_without_payload_mutation(self):
        self.config.data['conversation']['expressions']['enabled']=False
        self.config.data['conversation']['speech_address_prefix']='Алиса, '
        payload=dict(text='Вопрос')
        self.config.data['streaming']['enabled']=False
        with patch.object(self.agent,'request',return_value=dict(ok=True,audio_base64='')) as request:
            self.agent.voice('/say',payload)
        self.assertEqual(request.call_args.args[2]['speech_address_prefix'],'Алиса, ')
        self.assertEqual(payload,dict(text='Вопрос'))
        self.config.data['streaming']['enabled']=True
        for prefix in ('Алиса, ',''):
            self.config.data['conversation']['speech_address_prefix']=prefix
            response=io.BytesIO(b'{"type":"reply","reply":"fixture"}\n{"type":"done","ok":true}\n')
            response.headers=Message();response.headers['Content-Type']='application/x-ndjson'
            with patch.object(self.agent.http,'open',return_value=response) as opened:self.agent.voice('/turn',{})
            self.assertEqual(json.loads(opened.call_args.args[0].data)['speech_address_prefix'],prefix)


    def test_opt_in_latency_first_real_pipe_write_owned_drain_and_epoch_cancel_cleanup(self):
        from reachy_companion.logging_utils import TurnLatency
        self.config.data['logging']['latency_diagnostics']=True
        self.config.data['conversation']['expressions']['enabled']=False
        real_popen=subprocess.Popen
        for cancel in (False,True):
            processes=[]
            def opened(item,**kwargs):
                request=json.loads(item.data)
                worker=TurnLatency(request['latency_request_id'],'worker').report('complete')
                events=[dict(type='reply',reply='PRIVATE'),dict(type='audio',format='S16_LE',sample_rate=16000,
                    channels=1,pcm_base64=base64.b64encode(b'\0\0'*160).decode()),dict(type='done',ok=True,latency=worker)]
                fixture=self
                class Response(io.BytesIO):
                    reads=0
                    def readline(self,*args):
                        self.reads+=1
                        if cancel and self.reads==3:fixture.agent.microphone_epoch+=1
                        return super().readline(*args)
                response=Response(b''.join(json.dumps(event).encode()+b'\n' for event in events))
                response.headers=Message();response.headers['Content-Type']='application/x-ndjson'
                return response
            def popen(command,*args,**kwargs):
                self.assertEqual(command[0],'aplay')
                process=real_popen([sys.executable,'-c','import sys,time;sys.stdin.buffer.read();time.sleep(.02)'],*args,**kwargs)
                processes.append(process);return process
            with patch.object(self.agent.http,'open',side_effect=opened),patch('reachy_companion.agent.subprocess.Popen',side_effect=popen):
                result=self.agent.voice('/turn',{})
            report=result['latency'];own=report['agent']
            self.assertIsNotNone(own['marks']['first_write'])
            self.assertEqual(own['written_frames'],160);self.assertEqual(own['pcm_seconds'],.01)
            self.assertTrue(all(process.poll() is not None for process in processes))
            self.assertIsNone(self.agent.voice_response);self.assertIsNone(self.agent.playback_process)
            if cancel:
                self.assertTrue(result['cancelled']);self.assertIsNotNone(own['marks']['cancel_observed'])
                self.assertEqual(own['stages']['aplay_cancel']['calls'],1)
                self.assertEqual(own['stages']['aplay_wait']['calls'],0)
                self.assertIsNone(report['worker'])
            else:
                self.assertEqual(own['stages']['aplay_wait']['calls'],1)
                self.assertLessEqual(own['marks']['first_write'],own['stages']['aplay_wait']['start_seconds'])
                self.assertEqual(report['worker']['request_id'],report['request_id'])
            self.assertNotIn('PRIVATE',json.dumps(self.agent.status()['last_voice_latency']))


if __name__=='__main__':unittest.main()
