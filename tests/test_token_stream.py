"""Streaming parser/semantic/TTS seams; no model, audio, GPU or device calls."""
import base64
import ast
import hashlib
import io
import json
import re
from pathlib import Path
import subprocess
import tempfile
import threading
import types
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from reachy_companion import brains,token_stream as stream

ROOT=Path(__file__).resolve().parents[1]


def overlay(old,path):
    lines=old.splitlines(True);hunks=[]
    for line in path.read_text().splitlines(True):
        if line.startswith('@@ '):
            match=re.match(r'@@ -(\d+)(?:,(\d+))? ',line)
            start=int(match[1]);count=int(match[2] or 1)
            hunks.append((start if count==0 else start-1,[],[]))
        elif hunks and line[:1] in (' ','-','+'):
            _,before,after=hunks[-1]
            if line[0] in (' ','-'):before.append(line[1:])
            if line[0] in (' ','+'):after.append(line[1:])
    for start,before,after in reversed(hunks):
        assert lines[start:start+len(before)]==before
        lines[start:start+len(before)]=after
    return ''.join(lines)


def chunk(text='',finish=None,**extra):
    return dict(id='attempt',object='text_completion',model='configured',
        choices=[dict(index=0,text=text,finish_reason=finish)],**extra)


def wire(*events,done=True):
    raw=b''.join(b'data: '+json.dumps(event).encode()+b'\r\n\r\n' for event in events)
    return io.BytesIO(raw+(b'data: [DONE]\n\n' if done else b''))


class CompletionStreamTests(unittest.TestCase):
    def parse(self,response):
        self.terminal=Mock()
        return stream.sse_tokens(response,'configured',deadline=stream.time.monotonic()+30,terminal=self.terminal)

    def test_text_before_terminal_and_done_requires_same_model_id_index(self):
        tokens=self.parse(wire(chunk('Первое. '),chunk('Далее.'),chunk(finish='stop')))
        self.assertEqual(next(tokens),'Первое. ');self.terminal.assert_not_called()
        self.assertEqual(list(tokens),['Далее.']);self.terminal.assert_called_once()
        bad=[dict(chunk('x'),model='changed'),dict(chunk('x'),id='changed')]
        for event in bad:
            with self.assertRaises(ValueError):list(self.parse(wire(chunk('ok'),event,chunk(finish='stop'))))

    def test_early_eof_bad_terminal_reason_duplicate_json_and_tool_fields_fail(self):
        for response in (wire(chunk('text'),done=False),wire(chunk('text')),wire(chunk('x','length')),
                wire(dict(chunk('x'),choices=[dict(index=True,text='x',finish_reason=None)])),
                wire(dict(chunk('x'),choices=[dict(index=0,text='x',finish_reason=None,reasoning_content='PRIVATE')])),
                io.BytesIO(b'data: {"model":"configured","model":"changed"}\n\n'),
                io.BytesIO(b'data: '+b'x'*32769+b'\n\n')):
            with self.subTest(response=response),self.assertRaises((ValueError,json.JSONDecodeError)):
                list(self.parse(response))

    def test_terminal_failure_is_known_model_completion_but_never_success(self):
        tokens=self.parse(wire(chunk('incomplete','length')))
        with self.assertRaises(ValueError):list(tokens)
        self.terminal.assert_called_once()

    def test_stop_without_done_keeps_backend_terminal_unverified(self):
        tokens=self.parse(wire(chunk('First. '),chunk(finish='stop'),done=False))
        self.assertEqual(next(tokens),'First. ')
        with self.assertRaises(ValueError):list(tokens)
        self.terminal.assert_not_called()

    def test_valid_choices_with_error_or_incompatible_top_level_channel_never_reach_tts(self):
        for key in ('error','reasoning','reasoning_content','content','output','message','delta','tool_calls','function_call'):
            p=SimpleNamespace(config=dict(limits=dict(max_speech_chars=5000),
                conversation=dict(expressions=dict(speech_sync=dict(max_cues=2)))),audio_events=Mock())
            events=stream.incremental_audio(p,stream.semantic_segments(self.parse(wire(chunk('PRIVATE sentence. ',**{key:None}))),5000),'')
            with self.subTest(key=key),self.assertRaises(ValueError):list(events)
            p.audio_events.assert_not_called()

    def test_keepalive_comments_cannot_extend_absolute_drain_deadline(self):
        clock=[100.0];timeouts=[]
        def readline(bound):clock[0]+=.6;return b': keepalive\n'
        response=SimpleNamespace(readline=readline)
        with patch.object(stream.time,'monotonic',side_effect=lambda:clock[0]),self.assertRaises(ValueError):
            list(stream.sse_tokens(response,'configured',deadline=lambda:102,terminal=Mock(),set_timeout=timeouts.append))
        self.assertLessEqual(len(timeouts),4)
        self.assertLess(timeouts[-1],.3)

    def test_done_read_after_deadline_cannot_mark_terminal(self):
        clock=[100.0];body=wire(chunk(finish='stop'));terminal=Mock()
        def readline(bound):
            line=body.readline(bound)
            if b'[DONE]' in line:clock[0]=103
            return line
        with patch.object(stream.time,'monotonic',side_effect=lambda:clock[0]),self.assertRaises(ValueError):
            list(stream.sse_tokens(SimpleNamespace(readline=readline),'configured',deadline=102,terminal=terminal))
        terminal.assert_not_called()

    def test_closed_or_incomplete_http_stream_keeps_existing_unknown_admission(self):
        config=dict(brains=dict(provider='lm_studio'),network=dict(llm_base_url='http://local-pc/v1'),
            llm=dict(model='configured',api_path='/completions',message_template='{role}:{content}',assistant_prefix='assistant:',
                temperature=0,max_tokens=512,stop=['END']),timeouts=dict(llm=30))
        for complete in (True,False):
            response=wire(chunk('First. '),chunk(finish='stop'))
            response.headers=SimpleNamespace(get_content_type=lambda:'text/event-stream')
            ownership=brains.ModelExecutionOwnership()
            with patch.object(brains,'MODEL_EXECUTION',ownership),patch.object(stream,'build_opener') as opener:
                opener.return_value.open.return_value=response
                tokens=stream.completion_tokens(config,[dict(role='user',content='fixture')])
                self.assertEqual(next(tokens),'First. ')
                payload=json.loads(opener.return_value.open.call_args.args[0].data)
                self.assertIs(payload['stream'],True);self.assertNotIn('reasoning',payload)
                if complete:list(tokens)
                else:tokens.close()
                self.assertTrue(response.closed)
                self.assertEqual(ownership.status(brains.model_identity(config))['unknown'],not complete)

    def test_cancel_drain_discards_remaining_tokens_and_releases_only_verified_terminal(self):
        config=dict(brains=dict(provider='lm_studio'),network=dict(llm_base_url='http://local-pc/v1'),
            llm=dict(model='configured',api_path='/completions',message_template='{role}:{content}',assistant_prefix='',
                temperature=0,max_tokens=512,stop=[]),timeouts=dict(llm=30))
        for terminal in (True,False):
            response=wire(chunk('First. '),chunk('DISCARD'),*( [chunk(finish='stop')] if terminal else []),done=terminal)
            response.headers=SimpleNamespace(get_content_type=lambda:'text/event-stream')
            response.fp=SimpleNamespace(raw=SimpleNamespace(_sock=Mock()))
            ownership=brains.ModelExecutionOwnership()
            with patch.object(brains,'MODEL_EXECUTION',ownership),patch.object(stream,'build_opener') as opener:
                opener.return_value.open.return_value=response
                tokens=stream.completion_tokens(config,[dict(role='user',content='fixture')])
                self.assertEqual(next(tokens),'First. ');tokens.close()
            self.assertEqual(ownership.status(brains.model_identity(config))['unknown'],not terminal)
            self.assertTrue(response.closed)


class SemanticStreamTests(unittest.TestCase):
    def test_all_single_character_boundaries_never_expose_think_or_style_tags(self):
        raw='<think>PRIVATE. Hidden <thinker>tags</think><emotion=curious><gesture=tilt>Вижу чашку. Она синяя!'
        result=list(stream.semantic_segments(iter(raw),5000))
        self.assertEqual([s['text'] for s in result],['Вижу чашку.','Она синяя!'])
        self.assertEqual([(s['emotion'],s['gesture']) for s in result],[('curious','tilt')]*2)
        self.assertNotIn('PRIVATE',str(result))

    def test_only_first_complete_sentence_is_pulled_before_tts_audio_and_model_tail(self):
        visited=[]
        def tokens():
            try:
                yield 'Первое предложение. '
                visited.append('last_model_token');yield 'Последнее предложение.'
            finally:visited.append('model_closed')
        p=SimpleNamespace(config=dict(limits=dict(max_speech_chars=5000),
                conversation=dict(expressions=dict(speech_sync=dict(max_cues=2)))),
            address_speech=lambda text,prefix:prefix+text,speech_address_metadata=lambda text,prefix:{})
        calls=[]
        def audio(segments,total,speech_address_prefix):
            calls.append((segments,total,speech_address_prefix));visited.append('tts_first')
            yield dict(type='motion',cues=[dict(start=total),dict(start=total+1)])
            yield dict(type='audio',pcm_base64=base64.b64encode(b'\0\0'*4).decode())
        p.audio_events=audio
        events=stream.incremental_audio(p,stream.semantic_segments(tokens(),5000),'Алиса, ')
        self.assertEqual(next(events)['type'],'reply')
        self.assertNotIn('last_model_token',visited)
        self.assertEqual(next(events)['type'],'motion')
        self.assertEqual(next(events)['type'],'audio')
        self.assertEqual(visited,['tts_first'])
        rest=list(events)
        self.assertEqual(calls[1][1:],(8,''))
        self.assertFalse(any(e['type']=='motion' for e in rest))
        self.assertLess(visited.index('tts_first'),visited.index('last_model_token'))
        self.assertIn('model_closed',visited)

    def test_incomplete_tag_reasoning_oversize_and_analysis_never_flush_tail(self):
        for raw in ('<thi','<think>PRIVATE','<analysis>PRIVATE','[analysis]PRIVATE','x'*601,
                    '<emotion=unknown>sentence.'):
            spoken=[]
            with self.subTest(raw=raw[:20]),self.assertRaises(ValueError):
                for segment in stream.semantic_segments(iter(raw),5000):spoken.append(segment['text'])
            self.assertEqual(spoken,[])

    def test_early_audio_generator_close_closes_model_and_no_tail_is_requested(self):
        closed=[]
        def tokens():
            try:yield 'Один. ';raise AssertionError('No tail after stop')
            finally:closed.append(True)
        segments=stream.semantic_segments(tokens(),5000)
        p=SimpleNamespace(config=dict(limits=dict(max_speech_chars=5000),
            conversation=dict(expressions=dict(speech_sync=dict(max_cues=2)))),
            address_speech=lambda text,prefix:text,speech_address_metadata=lambda text,prefix:{},
            audio_events=lambda *args,**kwargs:iter(()))
        events=stream.incremental_audio(p,segments,'')
        self.assertEqual(next(events)['type'],'reply');events.close()
        self.assertEqual(closed,[True])


class HttpBoundaryTests(unittest.TestCase):
    def test_real_urllib_socket_discard_drain_observes_terminal_before_next_admission(self):
        release=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.send_header('Content-Type','text/event-stream')
                self.send_header('Connection','close');self.end_headers()
                self.wfile.write(wire(chunk('First. '),done=False).getvalue());self.wfile.flush()
                release.wait(2)
                self.wfile.write(wire(chunk('DISCARD'),chunk(finish='stop')).getvalue());self.wfile.flush()
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        config=json.loads((ROOT/'config.example.json').read_text())
        config['network']['llm_base_url']='http://127.0.0.1:'+str(server.server_port)+'/v1'
        config['llm']['model']='configured'
        ownership=brains.ModelExecutionOwnership()
        try:
            with patch.object(brains,'MODEL_EXECUTION',ownership):
                tokens=stream.completion_tokens(config,[dict(role='user',content='fixture')])
                self.assertEqual(next(tokens),'First. ');release.set();tokens.close()
            self.assertEqual(ownership.status(brains.model_identity(config)),dict(active=False,unknown=False))
            with ownership.reserve(brains.model_identity(config)):pass
        finally:
            release.set();server.shutdown();server.server_close();thread.join(2)

    def test_trickled_partial_sse_line_cannot_extend_cancel_drain_past_two_seconds(self):
        release=threading.Event();stop=threading.Event();finished=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.send_header('Content-Type','text/event-stream')
                self.send_header('Connection','close');self.end_headers()
                try:
                    self.wfile.write(wire(chunk('First. '),done=False).getvalue());self.wfile.flush();release.wait(2)
                    for byte in b'data: '+b' '*100:
                        if stop.wait(.04):break
                        self.wfile.write(bytes([byte]));self.wfile.flush()
                except OSError:pass
                finally:finished.set()
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        config=json.loads((ROOT/'config.example.json').read_text())
        config['network']['llm_base_url']='http://127.0.0.1:'+str(server.server_port)+'/v1';config['llm']['model']='configured'
        ownership=brains.ModelExecutionOwnership()
        try:
            with patch.object(brains,'MODEL_EXECUTION',ownership):
                tokens=stream.completion_tokens(config,[dict(role='user',content='fixture')])
                self.assertEqual(next(tokens),'First. ');release.set();began=stream.time.monotonic();tokens.close()
                self.assertLess(stream.time.monotonic()-began,2.8)
            self.assertEqual(ownership.status(brains.model_identity(config)),dict(active=False,unknown=True))
        finally:
            release.set();stop.set();finished.wait(2);server.shutdown();server.server_close();thread.join(2)


class ExactWorkerOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_stream_cleanup_overlay as legacy
        cls.old=subprocess.check_output(['git','show','2865db30e92fcb069c241c34bae4419ad65ed594:src/reachy_companion/voice.py'],cwd=ROOT).decode()
        if hashlib.sha256(cls.old.encode()).hexdigest()!='92cf69096fd6f08551a13a9c44d85fbbfc0470ca2f17315616691044018ab865':
            raise ValueError('Wrong installed worker preimage')
        cls.new=overlay(cls.old,ROOT/'deploy/patches/reachy-worker-92cf-content-stream.patch')
        cls.module=legacy.load(cls.new)
        before=subprocess.check_output(['git','show','39dffa0f1b4d3201765f851be4a932b0a0e079aa:src/reachy_companion/brains.py'],cwd=ROOT).decode()
        if hashlib.sha256(before.encode()).hexdigest()!='9c69d27979dce500148c06ee8d1dc58e90aabae3e5a2b1d3fc8edfb9e754642d':
            raise ValueError('Wrong installed brains preimage')
        cls.brains_source=overlay(before,ROOT/'deploy/patches/reachy-brains-9c69-content-stream.patch')
        cls.brains=types.ModuleType('legacy_stream_brains')
        exec(compile(cls.brains_source,'legacy_stream_brains.py','exec'),cls.brains.__dict__)

    def pipeline(self):
        p=self.module.Pipeline.__new__(self.module.Pipeline)
        p.config=json.loads((ROOT/'config.example.json').read_text());p.config['streaming']['content_tokens']=True
        p.config['logging']['log_transcripts']=False
        p.config['llm'].update(model='configured',history_messages=8)
        p.lock=threading.Lock();p.phase='idle';p.agent_sessions={};p.last_turn=None
        p.sessions={'existing':dict(used=stream.time.monotonic(),messages=[dict(role='user',content='Remember'),dict(role='assistant',content='Remembered')])}
        p.check_robot=Mock();p.classify=Mock(return_value=dict(action='answer',emotion='neutral',intent='question'))
        p.audio_events=lambda *args,**kwargs:iter([dict(type='audio',pcm_base64='AAA=')])
        return p

    def test_only_stream_method_changes_and_exact_output_pins(self):
        def outside(source):
            tree=ast.parse(source)
            pipeline=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Pipeline')
            pipeline.body=[n for n in pipeline.body if getattr(n,'name',None)!='stream']
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(outside(self.old),outside(self.new))
        self.assertEqual(hashlib.sha256(self.new.encode()).hexdigest(),'d97656e8d76b0802e4d177654369a31775ac0b74507c11718480f2d58e081a65')
        self.assertEqual(hashlib.sha256(self.brains_source.encode()).hexdigest(),'020e435e37602271d2d40160b055650f781b60a8ee9fc601e3b28d82444bdae6')

    def test_actual_legacy_hook_audio_before_tail_and_done_after_lock_release_with_history(self):
        p=self.pipeline();visited=[]
        values=p.config
        class Config:
            def __getitem__(self,key):return values[key]
        p.config=Config()  # Actual Config is a mapping facade without .get().
        def tokens(config,messages):
            self.assertEqual(messages[-3:],[dict(role='user',content='Remember'),dict(role='assistant',content='Remembered'),dict(role='user',content='Next')])
            yield 'Первое. ';visited.append('lasttoken');yield 'Второе.'
        with patch.object(stream,'completion_tokens',tokens):
            events=p.stream(dict(text='Next',session='existing'),'/text')
            self.assertEqual(next(events)['type'],'reply');self.assertEqual(visited,[])
            self.assertEqual(next(events)['type'],'audio');self.assertEqual(visited,[])
            remaining=list(events)
        self.assertEqual(remaining[-1]['type'],'done');self.assertFalse(p.lock.locked());self.assertEqual(p.phase,'idle')
        self.assertEqual(p.sessions['existing']['messages'][-1]['content'],'Первое. Второе.')
        self.assertFalse(any(e.get('acknowledgement') for e in remaining))

    def test_default_off_legacy_route_supports_exact_config_facade_without_get(self):
        p=self.pipeline();values=p.config;values['streaming']['content_tokens']=False
        class Config:
            def __getitem__(self,key):return values[key]
        p.config=Config();p.config['conversation']['interaction']['acknowledgements']['enabled']=False
        p.prepare=Mock(return_value=(dict(reply='Legacy',segments=[]),'existing',None))
        result=list(p.stream(dict(text='Next',session='existing'),'/text'))
        self.assertEqual(result[-1]['type'],'done');p.prepare.assert_called_once()
        self.assertFalse(p.lock.locked())

    def test_early_close_or_model_error_does_not_commit_history_or_done(self):
        for fail in (True,False):
            p=self.pipeline();before=json.dumps(p.sessions,sort_keys=True)
            def tokens(*args):
                yield 'Первое. '
                raise ValueError('MODEL FAILURE')
            with patch.object(stream,'completion_tokens',tokens):
                events=p.stream(dict(text='Next',session='existing'),'/text')
                next(events);next(events)
                if fail:
                    with self.assertRaises(ValueError):list(events)
                else:events.close()
            self.assertFalse(p.lock.locked());self.assertEqual(p.phase,'idle')
            self.assertEqual(json.dumps(p.sessions,sort_keys=True),before);self.assertIsNone(p.last_turn)

    def test_ordinary_and_stream_share_the_same_admission_after_opt_in(self):
        cfg=self.pipeline().config
        identity=self.brains.model_identity(cfg)
        with self.brains.MODEL_EXECUTION.reserve(identity) as permit:
            permit.submitted()
        with patch.object(self.brains,'build_opener') as opener,self.assertRaises(RuntimeError):
            self.brains.answer(cfg,[dict(role='user',content='Next')],'existing')
        opener.assert_not_called()




if __name__=='__main__':unittest.main()
