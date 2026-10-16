"""Exact Agent289 first-only timing/status contract; no devices/playback/network."""
import ast
import base64
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from test_agent_live_latency_patch import load

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('agent_timing_builder',ROOT/'deploy/autonomous/prepare_agent_stream_timing.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class Clock:
    def __init__(self):self.now=100.
    def __call__(self):return self.now
    def advance(self,value=.01):self.now+=value


class AgentStreamTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before,cls.after=builder.candidate();cls.module=load(cls.after.decode());cls.old=load(cls.before.decode())
        cls.validator=staticmethod(builder.load_contract(cls.after))

    def agent(self,module=None):
        module=module or self.module;a=module.Agent.__new__(module.Agent)
        class Config(dict):token='fixture'
        a.config=Config(json.loads((ROOT/'config.example.json').read_text()))
        a.config['streaming']['enabled']=True;a.config['conversation']['barge_in']['enabled']=False
        a.config['audio']['echo_tail_seconds']=0
        a.microphone=SimpleNamespace(enabled=True,error=None);a.microphone_epoch=17;a.agent_boot_id='fixture-boot'
        a.stopping=threading.Event();a.listening=threading.Event();a.listening.set()
        a.motion_policy=Mock();a.motion_policy.snapshot.return_value=dict(epoch=6,motor_enabled=True,quiet=False,privacy_all=False)
        a.expressions=Mock();a.resume_audio=None;a.pending_pcm=None;a.last_voice_at=None
        a.audio=a.config['audio'];return a

    def stream(self,module=None,events=None,cancel_wait=False,barge=False,fail_open=False,empty=False):
        module=module or self.module;a=self.agent(module);clock=Clock();order=[];writes=[]
        pcm=b'\1\0\2\0'
        if events is None:
            events=[dict(type='reply',reply='PRIVATE answer',content_attempt_id='a'*32),
                dict(type='motion',cues=[dict(at=0)]),
                *([] if empty else [dict(type='audio',sample_rate=16000,format='S16_LE',channels=1,pcm_base64=base64.b64encode(pcm).decode())]*2),
                dict(type='done',ok=True,reply='PRIVATE final')]
        class Response(io.BytesIO):
            headers=SimpleNamespace(get_content_type=lambda:'application/x-ndjson')
            def readline(self,*args):order.append('read');clock.advance();return super().readline(*args)
        a.http=Mock()
        def opening(*args,**kwargs):
            order.append('open');clock.advance()
            if fail_open:raise OSError('PRIVATE transport error')
            return Response(b''.join(json.dumps(e).encode()+b'\n' for e in events))
        a.http.open.side_effect=opening
        def timeline(*args):order.append('enqueue');clock.advance()
        def waiting(*args):
            order.append('wait');clock.advance(.2)
            if cancel_wait:a.microphone.enabled=False
        a.expressions.timeline.side_effect=timeline;a.expressions.wait_timeline.side_effect=waiting
        process=Mock();process.stdin.fileno.return_value=55;process.stdin.closed=False
        process.stdin.close.side_effect=lambda:setattr(process.stdin,'closed',True)
        process.returncode=None;process.poll.side_effect=lambda:process.returncode
        process.wait.side_effect=lambda **kwargs:setattr(process,'returncode',0)
        def popen(*args,**kwargs):
            a.observed_popen=(args,kwargs);order.append('popen');clock.advance(.05);return process
        selector=Mock();selector.select.side_effect=lambda **kwargs:(order.append('select') or [object()])
        def write(fd,data):order.append('write');clock.advance(.02);size=min(2,len(data));writes.append(bytes(data[:size]));return size
        monitor=SimpleNamespace(interrupted=threading.Event(),finish=Mock(return_value=None))
        def start():order.append('monitor');clock.advance(.03)
        monitor.start=start;a.config['conversation']['barge_in']['enabled']=barge
        with patch.object(module.time,'monotonic',clock),patch.object(module.subprocess,'Popen',side_effect=popen), \
                patch.object(module.os,'write',side_effect=write),patch.object(module.os,'set_blocking'), \
                patch.object(module.selectors,'DefaultSelector',return_value=selector), \
                patch('reachy_companion.barge_in.BargeInMonitor',return_value=monitor):
            if fail_open:
                with self.assertRaises(OSError):a.voice('/text',dict(text='PRIVATE question'))
                result=None
            else:result=a.voice('/text',dict(text='PRIVATE question'))
        return a,result,order,writes,clock

    def test_exact_preimage_bundle_contract_only_voice_status_and_timing_helpers_change(self):
        def outside(source):
            tree=ast.parse(source)
            tree.body=[n for n in tree.body if getattr(n,'name',None)!='validate_stream_timing' and not
                (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id.startswith('STREAM_TIMING_') for t in n.targets))]
            a=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Agent')
            a.body=[n for n in a.body if getattr(n,'name',None) not in ('voice','status','_stream_timing_begin','_stream_timing_mark','_stream_timing_bind','stream_timing_status')]
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(outside(self.before),outside(self.after))
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/'bundle';manifest=builder.build(destination)
            self.assertEqual(manifest['output_sha256'],builder.AFTER)
            self.assertEqual((destination/'agent.py').read_bytes(),self.after)
            with self.assertRaises(FileExistsError):builder.build(destination)
        with self.assertRaises(ValueError):builder.load_contract(self.before)

    def test_same_audio_actions_and_order_while_gate_and_first_only_marks_are_measured(self):
        a,result,order,writes,_=self.stream(barge=True)
        old,previous,previous_order,previous_writes,_=self.stream(self.old,barge=True)
        self.assertEqual(result,previous);self.assertEqual(order,previous_order);self.assertEqual(writes,previous_writes)
        self.assertEqual(a.observed_popen,old.observed_popen)
        self.assertEqual(a.http.open.call_args.args[0].data,old.http.open.call_args.args[0].data)
        row=a.stream_timing_status(dict(epoch=6));self.assertEqual(len(row),21)
        self.assertEqual(row['content_attempt_id'],'a'*32);self.assertEqual(row['content_binding'],'bound')
        self.assertEqual(row['first_positive_write_bytes'],2)
        self.assertAlmostEqual(row['timeline_wait_end']-row['timeline_wait_begin'],.2)
        self.assertAlmostEqual(row['aplay_popen_end']-row['aplay_popen_begin'],.05)
        marks=[row[key] for key in self.module.STREAM_TIMING_MARKS]
        self.assertEqual(marks,sorted(marks));self.assertTrue(all(value is not None for value in marks))
        self.assertFalse(row['consumption_verified']);self.assertFalse(row['acoustic_verified'])
        self.assertNotIn('PRIVATE',json.dumps(row));self.assertEqual(self.validator(row),row)

    def test_cancel_during_existing_gate_never_launches_aplay_or_invents_later_marks(self):
        a,result,order,writes,_=self.stream(cancel_wait=True)
        self.assertTrue(result['cancelled']);self.assertNotIn('popen',order);self.assertEqual(writes,[])
        row=a.stream_timing_status(dict(epoch=6));self.assertIsNotNone(row['timeline_wait_end'])
        self.assertIsNone(row['aplay_popen_begin']);self.assertIsNone(row['first_positive_write_bytes'])
        self.validator(row)

    def test_empty_and_failed_open_are_nullable_measurements_without_completion_claim(self):
        a,_,_,writes,_=self.stream(empty=True);self.assertEqual(writes,[])
        row=a.stream_timing_status(dict(epoch=6));self.assertIsNone(row['first_audio_line_received'])
        self.assertIsNone(row['first_positive_write']);self.validator(row)
        a,_,_,_,_=self.stream(fail_open=True);row=a.stream_timing_status(dict(epoch=6))
        self.assertIsNotNone(row['response_open_begin']);self.assertIsNone(row['response_open_end'])
        self.assertIsNone(row['content_attempt_id']);self.validator(row)
        self.assertNotIn('PRIVATE',json.dumps(row))

    def test_reset_generation_copy_old_probe_and_id_conflict_fail_closed(self):
        a=self.agent();clock=Clock()
        self.assertIsNone(a.stream_timing_status(dict(epoch=6)))
        with patch.object(self.module.time,'monotonic',clock):
            one=a._stream_timing_begin(17,6);a._stream_timing_bind(one,'a'*32)
            a._stream_timing_mark(one,'first_reply_received');original=copy.deepcopy(one[0])
            clock.advance();a._stream_timing_mark(one,'first_reply_received');self.assertEqual(one[0],original)
            row=a.stream_timing_status(dict(epoch=6));row['content_binding']='invalid'
            self.assertEqual(a.stream_timing_status(dict(epoch=6))['content_binding'],'bound')
            two=a._stream_timing_begin(17,6);a._stream_timing_mark(one,'first_audio_line_received')
            self.assertIsNone(two[0]['content_attempt_id']);self.assertIsNone(two[0]['first_audio_line_received'])
            a._stream_timing_bind(two,'b'*32);a._stream_timing_bind(two,'c'*32)
            self.assertEqual(two[0]['content_binding'],'invalid');self.assertEqual(two[0]['content_attempt_id'],'b'*32)
            a._stream_timing_bind(two,'PRIVATE');self.assertNotIn('PRIVATE',json.dumps(two[0]))
        for key,value in (('microphone_epoch',18),('agent_boot_id','other')):
            previous=getattr(a,key);setattr(a,key,value);self.assertIsNone(a.stream_timing_status(dict(epoch=6)));setattr(a,key,previous)
        self.assertIsNone(a.stream_timing_status(dict(epoch=7)))

    def test_every_mark_and_first_write_count_are_first_only_and_nonpositive_writes_do_not_mark(self):
        a=self.agent();clock=Clock()
        with patch.object(self.module.time,'monotonic',clock):
            probe=a._stream_timing_begin(17,6)
            a._stream_timing_mark(probe,'first_positive_write',0)
            self.assertIsNone(probe[0]['first_positive_write'])
            for name in self.module.STREAM_TIMING_MARKS:
                clock.advance();a._stream_timing_mark(probe,name,2 if name=='first_positive_write' else None)
            first=copy.deepcopy(probe[0])
            for name in self.module.STREAM_TIMING_MARKS:
                clock.advance();a._stream_timing_mark(probe,name,999)
            self.assertEqual(probe[0],first)
            self.validator(first)

    def test_early_cancel_and_nonstream_voice_clear_previous_attempt(self):
        a=self.agent();a._stream_timing_begin(17,6);a.microphone.enabled=False
        result=a.voice('/text',dict(text='PRIVATE'))
        self.assertTrue(result['cancelled']);self.assertIsNone(a.stream_timing_status(dict(epoch=6)))
        a.microphone.enabled=True;a._stream_timing_begin(17,6);a.config['streaming']['enabled']=False
        a.request=Mock(return_value=dict(reply='PRIVATE',audio_base64=''));a.play=Mock()
        a.voice('/text',dict(text='PRIVATE'));self.assertIsNone(a.stream_timing_status(dict(epoch=6)))

    def test_exact_status_projection_and_paired_strict_consumer_never_return_legacy_raw_fields(self):
        a,_,_,_,_=self.stream();a.microphone_lock=threading.Lock();a.motion_actor_status=Mock(return_value={})
        a.phase='paused';a.threshold=1;a.last_error='PRIVATE';a.last_transcript='PRIVATE';a.turns=1
        a.interruptions=0;a.barge_in_error=None;a.resume_blocked_reason=None;a.volume=SimpleNamespace(percent=100)
        a.capture_active=False;a.sounds=SimpleNamespace(music=False,last_error=None)
        a.expressions.last_expression=a.expressions.last_error=None
        value=a.status();row=builder.project_status(value,self.validator,'a'*32)
        self.assertEqual(row,value['stream_timing']);self.assertNotIn('PRIVATE',json.dumps(row))
        self.assertEqual(builder.parse_status(json.dumps(value).encode(),self.validator,'a'*32),row)
        for raw in (b'{\"stream_timing\":null,\"stream_timing\":null}',b'{\"stream_timing\":NaN}',b'x'*16001):
            with self.assertRaises(ValueError):builder.parse_status(raw,self.validator)
        with self.assertRaises(ValueError):builder.project_status(value,self.validator,'b'*32)
        changed=copy.deepcopy(value);changed['microphone_epoch']=True
        with self.assertRaises(ValueError):builder.project_status(changed,self.validator)
        a.microphone_epoch+=1;self.assertIsNone(a.status()['stream_timing'])
        self.assertIsNone(builder.project_status(a.status(),self.validator))

    def test_schema_rejects_unknown_missing_nonfinite_bool_int_enum_and_false_verification_claims(self):
        a,_,_,_,_=self.stream();row=a.stream_timing_status(dict(epoch=6))
        bad=[dict(row,PRIVATE='do not expose'),{k:v for k,v in row.items() if k!='first_positive_write_bytes'}]
        for key in self.module.STREAM_TIMING_MARKS:
            for value in (True,-1,float('nan'),float('inf'),'PRIVATE'):bad.append(dict(row,**{key:value}))
        for key,value in (('version',True),('microphone_epoch',True),('policy_epoch',0.0),('content_binding','PRIVATE'),
                ('content_attempt_id','PRIVATE'),('first_positive_write_bytes',True),('consumption_verified',True),
                ('acoustic_verified',True),('first_positive_write_bytes',None)):
            bad.append(dict(row,**{key:value}))
        for value in bad:
            with self.assertRaises(ValueError) as caught:self.validator(value)
            self.assertNotIn('PRIVATE',str(caught.exception))


if __name__=='__main__':unittest.main()
