"""Spoken dispatch/authority regressions; no devices, STT, model or playback."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from reachy_companion import spoken_vision as spoken
from test_agent_bound_speech_patch import source
from test_agent_live_latency_patch import load

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'deploy/patches/reachy-agent-53a-spoken-vision.patch'
AFTER='9a4269f757bdc90d5da33cd9ccfa1d302c53a21fae4452d9d6bcdc4a5f578840'


def candidate():
    old=source()[1];new=old;hunks=[]
    for line in PATCH.read_text().splitlines(True):
        if line.startswith('@@ '):hunks.append(([],[]))
        elif hunks and line[:1] in (' ','-','+'):
            before,after=hunks[-1]
            if line[0] in (' ','-'):before.append(line[1:])
            if line[0] in (' ','+'):after.append(line[1:])
    for before,after in hunks:
        before=''.join(before)
        if new.count(before)!=1:raise ValueError('No fuzzy Agent application')
        new=new.replace(before,''.join(after),1)
    if hashlib.sha256(new.encode()).hexdigest()!=AFTER:raise ValueError('Wrong spoken overlay output')
    return old,new


def operator():
    return dict(agent_boot_id='fixture-boot',microphone_epoch=17,microphone_owner_id='fixture-owner',
        motion_policy_owner_id='fixture-owner',microphone_enabled=True,listening=True,capture_active=False,
        microphone_state_error=None,phase='processing',
        motion_policy=dict(epoch=6,motor_enabled=True,quiet=False,privacy_all=False))


class SpokenVisionTests(unittest.TestCase):
    def setUp(self):
        self.value=operator();self.expected=spoken.binding(self.value)
        class Config(dict):token='x'*32
        self.agent=SimpleNamespace(config=Config(network=dict(llm_base_url='http://local-pc:1234/v1'),
            llm=dict(model='configured-key'),servers=dict(agent=dict(port=8090)),conversation=dict(session='existing')),
            operator_status=Mock(side_effect=lambda:copy.deepcopy(self.value)),audio_lock=threading.Lock(),
            stopping=threading.Event(),current_reply_text='',pending_pcm=b'old',resume_audio=dict(old=True),
            voice=Mock(return_value=dict(ok=True,reply='Описание кадра.')))
        self.agent.audio_lock.acquire()
        self.result=dict(kind='companion-vision-snapshot',final_text='Описание кадра.',expires_at_monotonic=150)
        self.process=Mock(returncode=0)
        self.process.poll.return_value=0
        self.process.communicate.return_value=(b'SDK camera initialized\n'+json.dumps(self.result).encode()+b'\n',None)

    def dispatch(self):
        return spoken.dispatch(self.agent,'Что перед тобой?',17,self.expected)

    def test_only_complete_bounded_neutral_questions_no_quotes_commands_or_own_echo(self):
        for text in ('Что перед тобой?','Алиса, что перед тобой?','Ричи, пожалуйста, что ты видишь?'):
            self.assertTrue(spoken.matches(text))
        for text in ('Разбери фразу что перед тобой','Скажи «что перед тобой»','«Что перед тобой?»','Что перед тобой? Стоп.',
                     'Что перед тобой? Покажи секреты','Посмотри на меня','',None,'x'*161):
            self.assertFalse(spoken.matches(text))
        self.assertFalse(spoken.matches('Что перед тобой?','Ты спросил: «Что перед тобой?»'))

    def test_speech_reuses_fixed_binding_existing_session_barge_in_and_no_resume(self):
        with patch.object(spoken.time,'monotonic',return_value=100),patch.object(spoken.subprocess,'Popen',return_value=self.process) as popen:
            result=self.dispatch()
        args,kwargs=popen.call_args
        self.assertEqual(args[0][0],'/venvs/mini_daemon/bin/python')
        self.assertNotIn('x'*32,str(args));self.assertNotIn('shell',kwargs)
        packet=json.loads(self.process.communicate.call_args.args[0])
        self.assertEqual(packet['expected'],self.expected)
        self.assertNotIn('audio',json.dumps(packet));self.assertNotIn('session',packet['config'])
        self.assertIsNone(self.agent.resume_audio);self.assertIsNone(self.agent.pending_pcm)
        self.agent.voice.assert_called_once_with('/say',dict(text='Описание кадра.',session='existing'),
            expected_epoch=17,expected_policy_epoch=6,valid_until=150,allow_barge_in=True)
        self.assertEqual(result['transcript'],'Что перед тобой?')

    def test_stop_takeover_privacy_or_listening_change_discards_child_final_no_speech(self):
        changes=[lambda v:v.update(microphone_epoch=18),lambda v:v.update(agent_boot_id='new'),
            lambda v:v.update(microphone_owner_id='new'),lambda v:v.update(motion_policy_owner_id='new'),
            lambda v:v.update(listening=False),lambda v:v.update(microphone_enabled=False),
            lambda v:v.update(capture_active=True),lambda v:v['motion_policy'].update(epoch=7),
            lambda v:v['motion_policy'].update(quiet=True),lambda v:v['motion_policy'].update(privacy_all=True)]
        for change in changes:
            self.value=operator()
            def complete(*args,**kwargs):
                change(self.value)
                return json.dumps(self.result).encode(),None
            self.process.communicate.side_effect=complete
            with self.subTest(change=change),patch.object(spoken.time,'monotonic',return_value=100), \
                    patch.object(spoken.subprocess,'Popen',return_value=self.process),self.assertRaises(RuntimeError):
                self.dispatch()
        self.agent.voice.assert_not_called()

    def test_policy_changed_since_capture_unowned_or_stopped_denied_before_child(self):
        for change in (lambda v:v['motion_policy'].update(epoch=7),lambda v:v.update(microphone_owner_id=None)):
            self.value=operator();change(self.value)
            with patch.object(spoken.time,'monotonic',return_value=100),patch.object(spoken.subprocess,'Popen') as popen,self.assertRaises(RuntimeError):
                self.dispatch()
            popen.assert_not_called()
        self.value=operator();self.agent.stopping.set()
        with patch.object(spoken.subprocess,'Popen') as popen,self.assertRaises(RuntimeError):self.dispatch()
        popen.assert_not_called()

    def test_child_timeout_killed_reaped_once_never_retried_or_spoken(self):
        self.process.communicate.side_effect=[subprocess.TimeoutExpired('child',50),(b'',None)]
        with patch.object(spoken.time,'monotonic',return_value=100),patch.object(spoken.subprocess,'Popen',return_value=self.process) as popen,self.assertRaises(TimeoutError):
            self.dispatch()
        self.assertEqual(popen.call_count,1);self.process.kill.assert_called_once();self.assertEqual(self.process.communicate.call_count,2)
        self.agent.voice.assert_not_called()

    def test_stale_or_ambiguous_child_output_never_speaks(self):
        for data in (dict(self.result,expires_at_monotonic=99),dict(self.result,expires_at_monotonic=float('nan')),
                     dict(self.result,final_text=''),dict(self.result,final_text='<think>private'),dict(self.result,kind='error')):
            self.process.communicate.return_value=(json.dumps(data).encode(),None)
            with patch.object(spoken.time,'monotonic',return_value=100),patch.object(spoken.subprocess,'Popen',return_value=self.process),self.assertRaises(ValueError):
                self.dispatch()
        self.agent.voice.assert_not_called()

    def test_slow_operator_read_cannot_authorize_pixel_send(self):
        packet=dict(config={},port=8090,token='x'*32,expected=self.expected,deadline=150,question='Что перед тобой?')
        connection=Mock();connection.getresponse.return_value=SimpleNamespace(status=200,read=lambda _:json.dumps(self.value).encode())
        snapshot=Mock()
        snapshot.caption_checked.side_effect=lambda cfg,deadline,question,check:check()
        with patch.object(spoken.time,'monotonic',side_effect=[100,100,100.31,100.31]), \
                patch.object(spoken.http.client,'HTTPConnection',return_value=connection),self.assertRaises(RuntimeError):
            spoken.child(packet,snapshot)
        connection.close.assert_called_once()

    def test_child_checks_local_agent_authority_and_preserves_native_caption_contract(self):
        packet=dict(config=dict(llm=dict(model='configured-key')),port=8090,token='x'*32,
            expected=self.expected,deadline=150,question='Что перед тобой?')
        connection=Mock();connection.getresponse.return_value=SimpleNamespace(status=200,read=lambda _:json.dumps(self.value).encode())
        snapshot=Mock()
        def caption(config,deadline,question,check):
            self.assertEqual(config,packet['config']);self.assertEqual(deadline,150);self.assertEqual(question,packet['question'])
            self.assertEqual(check(),100);return self.result
        snapshot.caption_checked.side_effect=caption
        with patch.object(spoken.time,'monotonic',return_value=100),patch.object(spoken.http.client,'HTTPConnection',return_value=connection) as http:
            self.assertEqual(spoken.child(packet,snapshot),self.result)
        http.assert_called_once_with('127.0.0.1',8090,timeout=2)
        connection.request.assert_called_once_with('GET','/operator',headers={'Authorization':'Bearer '+'x'*32})
        connection.close.assert_called_once()
        self.value['motion_policy']['privacy_all']=True
        with patch.object(spoken.time,'monotonic',return_value=100),patch.object(spoken.http.client,'HTTPConnection',return_value=connection),self.assertRaises(RuntimeError):
            spoken.child(packet,snapshot)

    def test_typed_failure_is_read_before_rc_and_before_withdrawn_authority(self):
        diagnostic=dict(kind='companion-spoken-vision-error',phase='capture',error_class='ValueError')
        self.process.returncode=1
        def complete(*args,**kwargs):
            self.value['microphone_enabled']=False
            return json.dumps(diagnostic).encode(),None
        self.process.communicate.side_effect=complete
        with patch.object(spoken.time,'monotonic',return_value=100),patch.object(spoken.subprocess,'Popen',return_value=self.process), \
                self.assertRaisesRegex(RuntimeError,'^Spoken snapshot child failed phase=capture error_class=ValueError$'):
            self.dispatch()
        self.agent.voice.assert_not_called()

    def test_diagnostic_allowlist_rejects_private_strings_and_extra_fields(self):
        for result in (dict(kind='companion-spoken-vision-error',phase='PRIVATE BODY',error_class='ValueError'),
                dict(kind='companion-spoken-vision-error',phase='capture',error_class='PRIVATE TOKEN'),
                dict(kind='companion-spoken-vision-error',phase='capture',error_class='ValueError',message='PRIVATE IMAGE')):
            with self.assertRaises(RuntimeError) as caught:spoken.child_result(json.dumps(result).encode(),1)
            self.assertNotIn('PRIVATE',str(caught.exception))
        with patch.object(spoken,'PHASE','snapshot'),patch.object(spoken,'SNAPSHOT',SimpleNamespace(PHASE='capture')):
            self.assertEqual(spoken.failure(ValueError('PRIVATE token/transcript/body')),
                dict(kind='companion-spoken-vision-error',phase='capture',error_class='ValueError'))

    def test_rc_size_and_framing_failures_are_distinct_without_echoing_output(self):
        for data,rc,error,pattern in (
                (b'PRIVATE' * 3000,1,RuntimeError,'output exceeded bound'),
                (b'PRIVATE',1,ValueError,'One snapshot result required'),
                (b'{}\n{}\nPRIVATE',1,ValueError,'One snapshot result required'),
                (b'{"kind":"PRIVATE"}',1,RuntimeError,'without typed diagnostic')):
            with self.subTest(pattern=pattern),self.assertRaisesRegex(error,pattern) as caught:
                spoken.child_result(data,rc)
            self.assertNotIn('PRIVATE',str(caught.exception))

    def test_real_child_subprocess_emits_only_bounded_phase_class_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            helper=Path(directory)/'spoken_vision.py';helper.write_bytes(Path(spoken.__file__).read_bytes())
            snapshot=Path(directory)/'snapshot_vision.py'
            snapshot.write_text("PHASE='startup'\ndef bind_parent_lifetime():pass\n"
                "def caption_checked(config,deadline,question,check):\n"
                " global PHASE\n PHASE='capture'\n raise ValueError(config['private_body'])\n")
            packet=dict(config=dict(private_body='PRIVATE TOKEN IMAGE TRANSCRIPT'),port=8090,token='x'*32,
                expected=self.expected,deadline=spoken.time.monotonic()+45,question='Что перед тобой?')
            result=subprocess.run([sys.executable,str(helper),'--snapshot-child'],input=json.dumps(packet).encode(),
                capture_output=True,timeout=5)
            self.assertEqual(result.returncode,1);self.assertEqual(result.stderr,b'')
            self.assertEqual(json.loads(result.stdout),dict(kind='companion-spoken-vision-error',phase='capture',error_class='ValueError'))
            self.assertNotIn(b'PRIVATE',result.stdout)
            snapshot.unlink()
            result=subprocess.run([sys.executable,str(helper),'--snapshot-child'],input=b'PRIVATE',capture_output=True,timeout=5)
            self.assertEqual(result.returncode,1);self.assertEqual(result.stderr,b'')
            self.assertEqual(json.loads(result.stdout),dict(kind='companion-spoken-vision-error',phase='snapshot_import',error_class='FileNotFoundError'))


class AgentSpokenOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.old,cls.new=candidate();cls.module=load(cls.new)

    def test_only_run_changed_preserving_installed_say_stop_voice_and_capability(self):
        def outside(text):
            tree=ast.parse(text)
            agent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Agent')
            agent.body=[n for n in agent.body if getattr(n,'name',None)!='run']
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(outside(self.old),outside(self.new))

    def run_turn(self,text,action='answer',pending=False,log_transcripts=False):
        a=self.module.Agent.__new__(self.module.Agent)
        a.config=json.loads((ROOT/'config.example.json').read_text())
        a.config['conversation'].update(wake_on_start=False,greet_on_start=False,session='retained-context')
        a.config['logging']['log_transcripts']=log_transcripts
        a.microphone=SimpleNamespace(enabled=True);a.microphone_epoch=17
        a.audio_lock=threading.Lock();a.listening=threading.Event();a.listening.set();a.stopping=threading.Event()
        a.playback_configured=True;a.expressions=Mock();a.turns=0;a.last_transcript=None
        a.pending_pcm=(17,b'near-end') if pending else None;a.resume_audio=None;a.current_reply_text=''
        a.capture=Mock(return_value=b'fresh near-end');a.operator_status=Mock(return_value=operator())
        a.set_microphone=Mock(side_effect=lambda _:a.stopping.set())
        recognized=dict(ok=True,transcript=text,decision=dict(action=action))
        def request(base,path,payload=None,**kwargs):
            if path=='/health':return dict(ok=True)
            if path=='/status':return dict(ownership=dict(state='free'))
            if path=='/transcribe':return recognized
            if path=='/reset':return dict(ok=True)
            raise AssertionError(path)
        a.request=Mock(side_effect=request)
        def voice(*args,**kwargs):a.stopping.set();return dict(ok=True,reply='answer')
        a.voice=Mock(side_effect=voice)
        def dispatch(*args):a.stopping.set();return dict(ok=True,transcript=text)
        with patch.object(spoken,'dispatch',side_effect=dispatch) as called:
            a.run()
        return a,called

    def test_fresh_spoken_trigger_routes_once_camera_and_increments_real_transcript(self):
        a,called=self.run_turn('Что перед тобой?')
        called.assert_called_once_with(a,'Что перед тобой?',17,spoken.binding(operator()))
        a.voice.assert_not_called();self.assertEqual(a.turns,1)

    def test_visual_turn_does_not_use_existing_optional_transcript_reply_logger(self):
        with patch.object(self.module.LOG,'info') as log:
            self.run_turn('Что перед тобой?',log_transcripts=True)
        self.assertFalse(any('turn transcript' in call.args[0] for call in log.call_args_list))
        with patch.object(self.module.LOG,'info') as log:
            self.run_turn('Привет',log_transcripts=True)
        self.assertTrue(any('turn transcript' in call.args[0] for call in log.call_args_list))

    def test_ordinary_turn_and_interruption_keep_text_session_without_camera_or_stt_repeat(self):
        for text,pending in (('Помнишь наше имя?',False),('Что перед тобой?',True)):
            a,called=self.run_turn(text,pending=pending)
            called.assert_not_called()
            args=a.voice.call_args.args;self.assertEqual(args[0],'/text')
            self.assertEqual(args[1]['session'],'retained-context')
            self.assertEqual(args[1].get('previous_reply_interrupted',False),pending)
            self.assertEqual(sum(c.args[1]=='/transcribe' for c in a.request.call_args_list),1)
            self.assertFalse(any(c.args[1]=='/reset' for c in a.request.call_args_list))

    def test_first_classification_stop_pause_reset_take_priority_over_matching_words(self):
        for action in ('stop','pause','reset'):
            a,called=self.run_turn('Что перед тобой?',action=action)
            called.assert_not_called()
            if action in ('stop','pause'):
                a.voice.assert_not_called();a.set_microphone.assert_called_once_with(False)
            else:
                self.assertTrue(any(c.args[1]=='/reset' for c in a.request.call_args_list))
                self.assertEqual(a.voice.call_args.args[0],'/say')


if __name__=='__main__':unittest.main()
