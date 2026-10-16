"""Exact installed-Agent overlay: finite local metadata, no hardware/worker calls."""
import array
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
BASE='2865db30e92fcb069c241c34bae4419ad65ed594'
BEFORE='0a7c0a3d7cbd542eabf9412291fda052c559db8c6bac123db31676b0137bd908'
AFTER='006c1f5b61553bbb35a0f694be8c084e1b11e1ef3589f2542bc43aa0994ef1b4'
PATCH=ROOT/'deploy/patches/reachy-agent-0a7-live-latency-metadata.patch'


def candidate():
    result=subprocess.run(['git','show',BASE+':src/reachy_companion/agent.py'],cwd=ROOT,capture_output=True)
    if result.returncode:raise unittest.SkipTest('Exact legacy Git source unavailable; no fetch performed')
    original=result.stdout
    if hashlib.sha256(original).hexdigest()!=BEFORE:raise ValueError('Wrong Agent preimage')
    source=original.decode();hunks=[]
    for line in PATCH.read_text().splitlines(True):
        if line.startswith('@@ '):hunks.append(([],[]))
        elif hunks and line[:1] in (' ','-','+'):
            old,new=hunks[-1]
            if line[0] in (' ','-'):old.append(line[1:])
            if line[0] in (' ','+'):new.append(line[1:])
    for old,new in hunks:
        old=''.join(old)
        if source.count(old)!=1:raise ValueError('No fuzzy overlay application')
        source=source.replace(old,''.join(new),1)
    return original.decode(),source


def load(source):
    module=types.ModuleType('reachy_companion.live_latency_overlay_fixture')
    module.__package__='reachy_companion'
    with patch.dict(sys.modules,{'webrtcvad':types.SimpleNamespace(Vad=Mock())}):
        exec(compile(source,'agent-0a7-overlay.py','exec'),module.__dict__)
    return module


class Clock:
    def __init__(self):self.now=100.0
    def __call__(self):return self.now


class AgentProbePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old,cls.new=candidate()
        if hashlib.sha256(cls.new.encode()).hexdigest()!=AFTER:raise ValueError('Wrong Agent overlay output')
        cls.module=load(cls.new)

    def agent(self,module=None):
        module=module or self.module
        a=module.Agent.__new__(module.Agent)
        class Config(dict):token='fixture'
        a.config=Config(json.loads((ROOT/'config.example.json').read_text()))
        a.config['streaming']['enabled']=True;a.config['conversation']['barge_in']['enabled']=False
        a.config['audio']['echo_tail_seconds']=0
        a.microphone=types.SimpleNamespace(enabled=True);a.microphone_epoch=17;a.agent_boot_id='fixture-boot'
        a.stopping=threading.Event();a.listening=threading.Event();a.listening.set()
        a.motion_policy=Mock();a.motion_policy.snapshot.return_value=dict(epoch=6,motor_enabled=True,quiet=False,privacy_all=False)
        a.expressions=Mock();a.resume_audio=None;a.pending_pcm=None;a.last_voice_at=None
        a._live_latency_remaining=3;a._live_latency_deadline=None
        a.audio=a.config['audio']
        return a

    def test_only_four_agent_methods_and_three_local_helpers_changed_no_new_imports_or_api(self):
        def outside(source):
            tree=ast.parse(source);agent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Agent')
            agent.body=[n for n in agent.body if getattr(n,'name',None) not in
                ('__init__','capture','voice','run','_live_latency_begin','_live_latency_mark','_live_latency_emit')]
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(outside(self.old),outside(self.new))
        tree=ast.parse(self.new);init=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='__init__')
        activation=next(n for n in init.body if isinstance(n,ast.Assign) and getattr(n.targets[0],'attr',None)=='_live_latency_remaining')
        for logging,expected in (({},0),({'live_latency_metadata':False},0),({'live_latency_metadata':True},3),({'latency_diagnostics':True},0)):
            holder=types.SimpleNamespace()
            exec(compile(ast.Module(body=[activation],type_ignores=[]),'activation','exec'),dict(self=holder,config={'logging':logging}))
            self.assertEqual(holder._live_latency_remaining,expected)

    def test_three_attempts_sixty_second_window_no_reset_duplicate_or_private_content(self):
        a=self.agent();clock=Clock()
        with patch.object(self.module.time,'monotonic',clock),patch.object(self.module.LOG,'info') as log:
            records=[a._live_latency_begin(17) for _ in range(3)]
            self.assertIsNone(a._live_latency_begin(17))
            for record in records:
                a._live_latency_mark(record,'endpoint_decision')
                a._live_latency_emit(record,'error','RuntimeError')
                a._live_latency_emit(record,'complete')
            self.assertEqual(log.call_count,3)
            for call in log.call_args_list:
                body=json.loads(call.args[1]);self.assertLess(len(call.args[1]),2000)
                self.assertFalse(body['consumption_verified']);self.assertFalse(body['acoustic_e2e_verified'])
                self.assertEqual(body['error_class'],'RuntimeError')
                self.assertFalse(any(word in call.args[1] for word in ('transcript','pcm_base64','PRIVATE')))
            a=self.agent();first=a._live_latency_begin(17);clock.now+=60
            self.assertIsNone(a._live_latency_begin(17))
            a._live_latency_mark(first,'final_reply');a._live_latency_emit(first,'complete')
            self.assertEqual(json.loads(log.call_args.args[1])['outcome'],'expired')
            self.assertIsNone(first['marks']['final_reply'])

    def test_first_loud_chunk_and_vad_endpoint_recorded_without_changing_pcm(self):
        a=self.agent();clock=Clock();a.calibrated=True;a.threshold=10
        a.chunk_bytes=a.vad_bytes=640;a.vad=Mock();a.vad.is_speech.side_effect=[True,False]
        a.sounds=types.SimpleNamespace(feed=lambda _:None,music=False)
        a.audio.update(sample_rate=16000,pre_roll_chunks=1,min_speech_frames=1,min_voiced_chunks=1,silence_chunks=1)
        loud=array.array('h',[1000]*320).tobytes();quiet=b'\0'*640
        process=Mock();process.stdout.read.side_effect=[loud,quiet];process.poll.return_value=None
        process.__enter__=Mock(return_value=process);process.__exit__=Mock(return_value=False)
        selector=Mock();selector.select.return_value=[object()]
        chunks=iter([loud,quiet])
        def read(size):clock.now+=.02;return next(chunks)
        process.stdout.read.side_effect=read
        with patch.object(self.module.time,'monotonic',clock),patch.object(self.module.subprocess,'Popen',return_value=process), \
                patch.object(self.module.selectors,'DefaultSelector',return_value=selector):
            record=a._live_latency_begin(17)
            result=a.capture(skip_expression=True,probe=record)
        self.assertEqual(result,loud+quiet)
        self.assertAlmostEqual(record['marks']['last_voiced_chunk_received'],.02)
        self.assertAlmostEqual(record['marks']['endpoint_decision'],.04)
        self.assertFalse(a.capture_active)

    def test_run_error_reports_only_class_and_no_speech_or_exception_payload(self):
        a=self.agent();clock=Clock();a.audio_lock=threading.Lock();a.playback_configured=True
        a.config['conversation'].update(wake_on_start=False,greet_on_start=False)
        a.request=Mock(side_effect=lambda base,path,**kwargs:dict(ok=True) if path=='/health' else dict(ownership=dict(state='free')))
        a.capture=Mock(side_effect=RuntimeError('PRIVATE ERROR PAYLOAD'))
        a.stopping=Mock();a.stopping.is_set.side_effect=[False,True]
        with patch.object(self.module.time,'monotonic',clock),patch.object(self.module.LOG,'info') as log, \
                patch.object(self.module.LOG,'exception'):
            a.run()
        records=[json.loads(call.args[1]) for call in log.call_args_list if call.args[0]=='live_latency_metadata %s']
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['outcome'],'error');self.assertEqual(records[0]['error_class'],'RuntimeError')
        self.assertNotIn('PRIVATE',json.dumps(records[0]));self.assertIsNone(records[0]['marks']['final_write_begin'])

    def test_changed_epoch_after_capture_still_discards_pcm_and_reports_cancelled(self):
        a=self.agent();clock=Clock();a.audio_lock=threading.Lock();a.playback_configured=True
        a.config['conversation'].update(wake_on_start=False,greet_on_start=False)
        a.request=Mock(side_effect=lambda base,path,**kwargs:dict(ok=True) if path=='/health' else dict(ownership=dict(state='free')))
        def capture(**kwargs):a.microphone_epoch+=1;return b'PRIVATE PCM'
        a.capture=capture;a.voice=Mock();a.stopping=Mock();a.stopping.is_set.side_effect=[False,True]
        with patch.object(self.module.time,'monotonic',clock),patch.object(self.module.LOG,'info') as log:
            a.run()
        a.voice.assert_not_called()
        record=json.loads(log.call_args.args[1]);self.assertEqual(record['outcome'],'cancelled')
        self.assertNotIn('PRIVATE',json.dumps(record))

    def stream(self,module,enabled):
        a=self.agent(module);clock=Clock();writes=[]
        events=[dict(type='reply',reply='PRIVATE ACK',acknowledgement=True),
            dict(type='audio',sample_rate=16000,format='S16_LE',channels=1,pcm_base64=base64.b64encode(b'\1\0\2\0').decode()),
            dict(type='reply',reply='PRIVATE FINAL'),
            dict(type='audio',sample_rate=16000,format='S16_LE',channels=1,pcm_base64=base64.b64encode(b'\3\0\4\0').decode()),
            dict(type='done',ok=True,reply='PRIVATE FINAL')]
        class Response(io.BytesIO):
            headers=types.SimpleNamespace(get_content_type=lambda:'application/x-ndjson')
        a.http=Mock();a.http.open.return_value=Response(b''.join(json.dumps(e).encode()+b'\n' for e in events))
        process=Mock();process.stdin.fileno.return_value=55;process.stdin.closed=False
        process.stdin.close.side_effect=lambda:setattr(process.stdin,'closed',True)
        process.poll.side_effect=lambda:process.returncode
        process.returncode=None
        process.wait.side_effect=lambda **kwargs:setattr(process,'returncode',0)
        selector=Mock();selector.select.return_value=[object()]
        sizes=iter([1,3,1,3])
        def write(fd,data):
            size=next(sizes);writes.append(bytes(data[:size]));clock.now+=.01;return size
        with patch.object(module.time,'monotonic',clock),patch.object(module.subprocess,'Popen',return_value=process) as popen, \
                patch.object(module.os,'write',side_effect=write),patch.object(module.os,'set_blocking'), \
                patch.object(module.selectors,'DefaultSelector',return_value=selector),patch.object(module.LOG,'info') as log:
            probe=a._live_latency_begin(17) if enabled else None
            result=a.voice('/turn',dict(pcm_base64='PRIVATE INPUT'),**({'probe':probe} if enabled else {}))
            if enabled:a._live_latency_emit(probe,'complete')
        return result,writes,popen.call_args,a.http.open.call_args.args[0],probe,log

    def test_ack_final_same_attempt_partial_writes_offsets_no_worker_protocol_or_privacy_change(self):
        result,writes,popen,request,probe,log=self.stream(self.module,True)
        body=json.loads(log.call_args.args[1]);self.assertEqual(body['outcome'],'complete')
        self.assertEqual(body['written_bytes'],8);self.assertEqual(body['written_frames'],4)
        self.assertEqual(body['ack_submitted_bytes'],4);self.assertEqual(body['final_submitted_bytes'],4)
        self.assertEqual(body['final_received_offset_bytes'],4);self.assertEqual(body['first_final_write_offset_bytes'],4)
        self.assertLess(body['marks']['ack_write_begin'],body['marks']['final_write_begin'])
        self.assertNotIn('PRIVATE',log.call_args.args[1]);self.assertNotIn('attempt_id',request.data.decode())
        legacy=self.stream(load(self.old),False);disabled=self.stream(self.module,False)
        self.assertEqual(legacy[:3],disabled[:3]);self.assertEqual(legacy[3].data,disabled[3].data)
        self.assertEqual(legacy[1],writes);self.assertEqual(legacy[0],result)
        disabled[-1].assert_not_called()


if __name__=='__main__':unittest.main()
