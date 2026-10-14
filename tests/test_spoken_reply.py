"""Constrained generation remains causal, request-local and fail-closed."""
import copy
import io
import json
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch

from reachy_companion import brains, spoken_reply as spoken

ROOT=Path(__file__).resolve().parents[1]
RULE=dict(schema_version='reply-1',max_chars=60,no_question=True,no_wake=True)


def config():
    cfg=json.loads((ROOT/'config.example.json').read_text())
    cfg['llm']['reply_schema']=dict(enabled=True,verified=True,model=cfg['llm']['model'],
        base_url=cfg['network']['llm_base_url'],api_path='/chat/completions',
        max_length_verified=True,pattern_verified=True)
    return cfg


class ReplyTests(unittest.TestCase):
    def response(self,content='{"reply":"Шесть подходит."}',finish='stop'):
        return io.BytesIO(json.dumps({'choices':[{'message':{'content':content},'finish_reason':finish}]}).encode())

    def test_default_raw_payload_and_cleanup_unchanged(self):
        cfg=config(); messages=[dict(role='user',content='Число шесть')]
        response=io.BytesIO(b'{"choices":[{"text":"<think>x</think> OK ","finish_reason":"stop"}]}')
        with patch('reachy_companion.brains.build_opener') as op:
            op.return_value.open.return_value=response
            self.assertEqual(brains.answer(cfg,messages,'s'),'OK')
        request=op.return_value.open.call_args.args[0]
        self.assertEqual(json.loads(request.data),dict(model=cfg['llm']['model'],
            prompt=cfg['llm']['message_template'].format(**messages[0])+cfg['llm']['assistant_prefix'],
            temperature=cfg['llm']['temperature'],max_tokens=cfg['llm']['max_tokens'],stream=False,stop=cfg['llm']['stop']))
        self.assertTrue(request.full_url.endswith('/v1/completions'))

    def test_same_model_messages_schema_and_exact_reply(self):
        cfg=config();messages=[dict(role='user',content='Число шесть')]
        with patch('reachy_companion.brains.build_opener') as op:
            op.return_value.open.return_value=self.response()
            self.assertEqual(brains.answer(cfg,messages,'s',reply_constraints=RULE),'Шесть подходит.')
        request=op.return_value.open.call_args.args[0];payload=json.loads(request.data)
        self.assertEqual(request.full_url,cfg['network']['llm_base_url']+'/chat/completions')
        self.assertEqual(payload['messages'],messages);self.assertEqual(payload['model'],cfg['llm']['model'])
        self.assertEqual(payload['max_tokens'],cfg['llm']['max_tokens'])
        self.assertEqual(payload['response_format'],spoken.response_format(RULE))
        self.assertNotIn('prompt',payload);self.assertNotIn('stop',payload)

    def test_unverified_changed_model_host_or_provider_never_calls_backend(self):
        for change in ('absent','model','host','provider','pattern'):
            cfg=config()
            if change=='absent':del cfg['llm']['reply_schema']
            if change=='model':cfg['llm']['model']='other'
            if change=='host':cfg['network']['llm_base_url']='http://other/v1'
            if change=='provider':cfg['brains']['provider']='hermes'
            if change=='pattern':cfg['llm']['reply_schema']['pattern_verified']=False
            with self.subTest(change=change),patch('reachy_companion.brains.build_opener') as op:
                with self.assertRaises(ValueError):brains.answer(cfg,[],'s',reply_constraints=RULE)
                op.assert_not_called()

    def test_rejects_malformed_or_incomplete_without_cleanup_or_fallback(self):
        bad=['{"reply":"one","reply":"two"}','{"reply":"ok","tool":"x"}',
             '```{"reply":"ok"}```','{"reply":NaN}','{"reply":null}',
             '{"reply":"<think>x</think>ok"}','{"reply":" OK "}',
             json.dumps({'reply':'x'*61}),json.dumps({'reply':'Что？'}),json.dumps({'reply':'Аlисa'}),
             '{"reply":"..."}']
        for content in bad:
            with self.subTest(content=content),patch('reachy_companion.brains.build_opener') as op:
                op.return_value.open.return_value=self.response(content)
                with self.assertRaises((ValueError,RuntimeError)):brains.answer(config(),[],'s',reply_constraints=RULE)
                self.assertEqual(op.return_value.open.call_count,1)
        with patch('reachy_companion.brains.build_opener') as op:
            op.return_value.open.return_value=self.response(finish='length')
            with self.assertRaises(RuntimeError):brains.answer(config(),[],'s',reply_constraints=RULE)

    def test_request_rules_do_not_leak(self):
        barrier=threading.Barrier(2);results=[]
        def run(limit):
            rule={**RULE,'max_chars':limit};barrier.wait()
            try:results.append((limit,spoken.decode_reply('{"reply":"six"}',rule)))
            except RuntimeError:results.append((limit,'rejected'))
        workers=[threading.Thread(target=run,args=(n,)) for n in (2,3)]
        for t in workers:t.start()
        for t in workers:t.join()
        self.assertEqual(sorted(results),[(2,'rejected'),(3,'six')])
        for key,value in [('max_chars',True),('no_wake','true'),('no_question',None)]:
            with self.assertRaises(ValueError):spoken.constraints({**RULE,key:value})


class PipelineTests(unittest.TestCase):
    def setUp(self):
        piper=types.ModuleType('piper');piper.PiperVoice=piper.SynthesisConfig=object
        vosk=types.ModuleType('vosk');vosk.Model=vosk.KaldiRecognizer=vosk.SetLogLevel=object
        with patch.dict(sys.modules,{'piper':piper,'vosk':vosk}):
            from reachy_companion.voice import Pipeline
        self.pipeline=Pipeline.__new__(Pipeline);p=self.pipeline
        p.config=config();p.sessions={};p.agent_sessions={};p.phase='idle';p.lock=threading.Lock()
        p.check_robot=lambda:None;p.last_turn=None
        p.classify=lambda text:dict(action='answer',intent='other',emotion='neutral')
        p.synthesize=lambda text:'audio'

    def test_commands_empty_and_say_do_not_reset_history_or_infer(self):
        p=self.pipeline;p.sessions={'s':dict(used=1,messages=[])};before=copy.deepcopy(p.sessions)
        for action in ('pause','reset','stop'):
            p.classify=lambda text:dict(action=action)
            with patch('reachy_companion.brains.answer') as answer:
                with self.assertRaises(ValueError):p.prepare(dict(text='command',session='s',reply_constraints=RULE),'/text')
                answer.assert_not_called();self.assertEqual(p.sessions,before)
        with self.assertRaises(ValueError):p.prepare(dict(text='hello',reply_constraints=RULE),'/say')
        with self.assertRaises(ValueError):p.prepare(dict(pcm_base64='',reply_constraints=RULE),'/turn',recognized_text='')

    def test_invalid_reply_cannot_synthesize_or_commit_history(self):
        p=self.pipeline
        with patch('reachy_companion.brains.answer',return_value='Продолжить?'),patch.object(p,'synthesize') as synth:
            with self.assertRaises(RuntimeError):p.turn(dict(text='Шесть',reply_constraints=RULE),'/text')
            synth.assert_not_called();self.assertEqual(p.sessions,{});self.assertIsNone(p.last_turn)

    def test_unchanged_reply_reaches_tts_and_history_only_after_success(self):
        p=self.pipeline
        with patch('reachy_companion.brains.answer',return_value='Шесть подходит.') as answer,patch.object(p,'synthesize',return_value='audio') as synth:
            result=p.turn(dict(text='Шесть',session='s',reply_constraints=RULE),'/text')
            synth.assert_called_once_with('Шесть подходит.')
            self.assertEqual(result['reply'],'Шесть подходит.')
            self.assertEqual(p.sessions['s']['messages'][-1]['content'],'Шесть подходит.')
            self.assertEqual(answer.call_args.kwargs['reply_constraints'],RULE)

    def test_constrained_stream_never_emits_canned_acknowledgement(self):
        p=self.pipeline
        p.config['conversation']['interaction']={'acknowledgements':dict(enabled=True,delay_seconds=0,phrases={'other':'preset'})}
        p.audio_events=lambda *args,**kw:iter([])
        with patch('reachy_companion.brains.answer',return_value='Шесть подходит.') as answer:
            events=list(p.stream(dict(text='Шесть',reply_constraints=RULE),'/text'))
        self.assertEqual(answer.call_count,1)
        self.assertEqual([e['reply'] for e in events if e['type']=='reply'],['Шесть подходит.'])
        self.assertFalse(any(e.get('acknowledgement') for e in events))


if __name__=='__main__':unittest.main()
