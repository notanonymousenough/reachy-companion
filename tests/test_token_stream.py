"""Streaming parser/semantic/TTS seams; no model, audio, GPU or device calls."""
import base64
import ast
import hashlib
import importlib.util
import io
import json
import re
import socket
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
            with patch.object(brains,'MODEL_EXECUTION',ownership),patch.object(stream,'owned_response') as opener:
                opener.return_value=response
                opener.side_effect=lambda request,deadline,submitted:(submitted(),response)[1]
                tokens=stream.completion_tokens(config,[dict(role='user',content='fixture')])
                self.assertEqual(next(tokens),'First. ')
                payload=json.loads(opener.call_args.args[0].data)
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
            with patch.object(brains,'MODEL_EXECUTION',ownership),patch.object(stream,'owned_response') as opener:
                opener.return_value=response
                opener.side_effect=lambda request,deadline,submitted:(submitted(),response)[1]
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

    def test_running_piper_return_cannot_emit_pcm_or_cues_after_withdrawal(self):
        allowed=[True];closed=[]
        def check():
            if not allowed[0]:raise RuntimeError('withdrawn')
        def audio(*args,**kwargs):
            try:
                allowed[0]=False
                yield dict(type='motion',cues=[dict(start=0)])
                yield dict(type='audio',pcm_base64='AAA=')
            finally:closed.append(True)
        p=SimpleNamespace(config=dict(limits=dict(max_speech_chars=5000),
            conversation=dict(expressions=dict(speech_sync=dict(max_cues=2)))),
            address_speech=lambda text,prefix:text,speech_address_metadata=lambda text,prefix:{},audio_events=audio)
        events=stream.incremental_audio(p,iter([dict(text='First.',emotion='neutral',gesture='auto')]),'',valid=check)
        self.assertEqual(next(events)['type'],'reply')
        with self.assertRaises(RuntimeError):next(events)
        self.assertEqual(closed,[True])


class TimelyReaderTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((ROOT/'config.example.json').read_text())
        self.config['streaming']['content_request_seconds']=5
        self.config['llm']['model']='configured'
        self.guard=brains.ModelExecutionOwnership()
        scoped=patch.object(brains,'MODEL_EXECUTION',self.guard);scoped.start();self.addCleanup(scoped.stop)

    def test_reader_reads_tail_without_waiting_for_tts_but_holds_permit_until_consumer_cleanup(self):
        terminal=threading.Event()
        def tokens(config,messages,**kwargs):
            kwargs['execution'].submitted()
            yield 'First. ';yield 'Last.';kwargs['execution'].terminal();terminal.set()
        with patch.object(stream,'completion_tokens',tokens):
            reader=stream.TimelyReader(self.config,[])
            self.assertTrue(terminal.wait(1))
            self.assertEqual(self.guard.status(brains.model_identity(self.config)),dict(active=True,unknown=False))
            with self.assertRaises(RuntimeError):
                with self.guard.reserve(brains.model_identity(self.config)):pass
            self.assertEqual(list(reader),['First. ','Last.']);reader.close()
        metadata=reader.metadata()
        self.assertTrue(metadata['terminal_verified']);self.assertTrue(metadata['producer_quiesced'])
        self.assertFalse(metadata['queue_backpressure']);self.assertFalse(metadata['queue_overflow'])
        self.assertEqual(self.guard.status(brains.model_identity(self.config)),dict(active=False,unknown=False))

    def test_full_queue_withdraws_then_discards_same_request_without_blocking_reader(self):
        completed=threading.Event()
        def tokens(config,messages,**kwargs):
            kwargs['execution'].submitted()
            for _ in range(8):yield 'chunk'
            kwargs['execution'].terminal();completed.set()
        with patch.object(stream.TimelyReader,'MAX_QUEUE_EVENTS',2),patch.object(stream,'completion_tokens',tokens):
            reader=stream.TimelyReader(self.config,[])
            self.assertTrue(completed.wait(1))
            with self.assertRaises(RuntimeError):next(reader)
            reader.close()
        metadata=reader.metadata();self.assertTrue(metadata['queue_overflow'])
        self.assertTrue(metadata['failed']);self.assertTrue(metadata['terminal_verified'])
        self.assertGreater(metadata['discarded_chunks'],0);self.assertTrue(metadata['producer_quiesced'])

    def test_cancel_discards_through_original_deadline_and_next_turn_waits_both_cleanups(self):
        release=threading.Event();started=threading.Event();calls=[]
        def tokens(config,messages,**kwargs):
            calls.append(kwargs['deadline']);kwargs['execution'].submitted()
            yield 'First. ';started.set();release.wait(3)
            yield 'MUST DISCARD';kwargs['execution'].terminal()
        with patch.object(stream,'completion_tokens',tokens):
            reader=stream.TimelyReader(self.config,[]);self.assertEqual(next(reader),'First. ')
            self.assertTrue(started.wait(1));closed=threading.Event()
            def close():reader.close();closed.set()
            cleanup=threading.Thread(target=close);cleanup.start()
            self.assertFalse(closed.wait(.05))
            with self.assertRaises(RuntimeError):
                with self.guard.reserve(brains.model_identity(self.config)):pass
            release.set();cleanup.join(1);self.assertTrue(closed.is_set())
        self.assertEqual(calls,[reader.deadline]);self.assertEqual(reader.metadata()['discarded_chunks'],1)
        with self.guard.reserve(brains.model_identity(self.config)):pass

    def test_sse_parser_and_semantic_filter_unchanged_from_actual_contract_checkpoint(self):
        original=subprocess.check_output(['git','show','b90d40bbdedddcba397c03f658752566c2e0b4a2:src/reachy_companion/token_stream.py'],cwd=ROOT).decode()
        def selected(text,name):return next(n for n in ast.parse(text).body if getattr(n,'name',None)==name)
        current=Path(stream.__file__).read_text()
        for name in ('sse_tokens','Segments'):
            self.assertEqual(ast.dump(selected(original,name),include_attributes=False),ast.dump(selected(current,name),include_attributes=False))


class ExactBundleTests(unittest.TestCase):
    def builder(self):
        spec=importlib.util.spec_from_file_location('prepare_content_stream',ROOT/'deploy/autonomous/prepare_content_stream.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def test_bundle_uses_legacy_preimages_not_head_and_preserves_existing_directory(self):
        builder=self.builder()
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'bundle';manifest=builder.build(target)
            self.assertEqual(set(p.name for p in target.iterdir()),{'brains.py','voice.py','token_stream.py','manifest.json'})
            for name,digest in manifest['outputs'].items():self.assertEqual(builder.sha((target/name).read_bytes()),digest)
            self.assertNotEqual((target/'brains.py').read_bytes(),(ROOT/'src/reachy_companion/brains.py').read_bytes())
            self.assertNotEqual((target/'voice.py').read_bytes(),(ROOT/'src/reachy_companion/voice.py').read_bytes())
            before=(target/'manifest.json').read_bytes()
            with self.assertRaises(FileExistsError):builder.build(target)
            self.assertEqual((target/'manifest.json').read_bytes(),before)

    def test_wrong_helper_hash_never_creates_bundle(self):
        builder=self.builder()
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'bundle'
            with patch.object(builder,'HELPER','0'*64),self.assertRaises(ValueError):builder.build(target)
            self.assertFalse(target.exists())


class HttpBoundaryTests(unittest.TestCase):
    def test_header_trickle_is_aborted_by_original_deadline_and_reader_quiesces(self):
        stop=threading.Event();finished=threading.Event();posts=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                posts.append(True);self.rfile.read(int(self.headers['Content-Length']))
                try:
                    self.wfile.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nX-Slow: ');self.wfile.flush()
                    while not stop.wait(.04):self.wfile.write(b'x');self.wfile.flush()
                except OSError:pass
                finally:finished.set()
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        config=json.loads((ROOT/'config.example.json').read_text())
        config['network']['llm_base_url']='http://127.0.0.1:'+str(server.server_port)+'/v1'
        config['llm']['model']='configured';config['streaming']['content_request_seconds']=.5
        ownership=brains.ModelExecutionOwnership()
        try:
            stream.prepare_endpoint(config)
            with patch.object(brains,'MODEL_EXECUTION',ownership):
                began=stream.time.monotonic();reader=stream.TimelyReader(config,[dict(role='user',content='fixture')])
                with self.assertRaises((RuntimeError,TimeoutError)):next(reader)
                reader.close();self.assertLess(stream.time.monotonic()-began,1.5)
            self.assertEqual(posts,[True]);self.assertTrue(reader.metadata()['producer_quiesced'])
            self.assertTrue(reader.metadata()['model_post_attempted']);self.assertFalse(reader.metadata()['terminal_verified'])
            self.assertEqual(ownership.status(brains.model_identity(config)),dict(active=False,unknown=True))
        finally:stop.set();finished.wait(2);server.shutdown();server.server_close();thread.join(2)

    def test_registered_connect_socket_is_closed_at_deadline_before_any_post(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);fillers=[]
        try:
            pending=False
            for _ in range(16):
                client=socket.socket();client.settimeout(.03)
                try:client.connect(listener.getsockname());fillers.append(client)
                except TimeoutError:client.close();pending=True;break
            if not pending:self.skipTest('Platform did not expose a saturated local TCP accept queue')
            config=json.loads((ROOT/'config.example.json').read_text())
            config['network']['llm_base_url']='http://127.0.0.1:'+str(listener.getsockname()[1])+'/v1'
            stream.prepare_endpoint(config);created=[];original=socket.socket
            def make(*args,**kwargs):
                sock=original(*args,**kwargs);created.append(sock);return sock
            request=stream.Request(config['network']['llm_base_url']+'/completions',data=b'{}')
            began=stream.time.monotonic()
            with patch.object(stream.socket,'socket',side_effect=make),patch.object(stream.http.client.HTTPConnection,'request') as post:
                with self.assertRaises((OSError,ValueError,TimeoutError)):
                    with stream.owned_response(request,stream.time.monotonic()+.3):self.fail('Connected through full backlog')
            self.assertLess(stream.time.monotonic()-began,1.3);post.assert_not_called()
            self.assertEqual(len(created),1);self.assertEqual(created[0].fileno(),-1)
        finally:
            for client in fillers:client.close()
            listener.close()

    def test_timely_reader_preserves_same_response_beyond_fast_grace_and_recovers_next_admission(self):
        stop=threading.Event();posts=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                posts.append(True);self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.send_header('Content-Type','text/event-stream')
                self.send_header('Connection','close');self.end_headers()
                try:
                    self.wfile.write(wire(chunk('First. '),done=False).getvalue());self.wfile.flush()
                    stop.wait(2.3)
                    self.wfile.write(wire(chunk('DISCARD'),chunk(finish='stop')).getvalue());self.wfile.flush()
                except OSError:pass
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        config=json.loads((ROOT/'config.example.json').read_text())
        config['network']['llm_base_url']='http://127.0.0.1:'+str(server.server_port)+'/v1'
        config['llm']['model']='configured';config['streaming']['content_request_seconds']=5
        ownership=brains.ModelExecutionOwnership()
        try:
            with patch.object(brains,'MODEL_EXECUTION',ownership):
                stream.prepare_endpoint(config);reader=stream.TimelyReader(config,[dict(role='user',content='fixture')])
                self.assertEqual(next(reader),'First. ');reader.close()
            metadata=reader.metadata()
            self.assertTrue(metadata['fast_grace_exceeded']);self.assertTrue(metadata['terminal_verified'])
            self.assertTrue(metadata['producer_quiesced']);self.assertEqual(metadata['discarded_chunks'],1)
            self.assertEqual(posts,[True]);self.assertEqual(ownership.status(brains.model_identity(config)),dict(active=False,unknown=False))
            with ownership.reserve(brains.model_identity(config)):pass
        finally:stop.set();server.shutdown();server.server_close();thread.join(2)

    def test_timely_reader_original_total_deadline_stops_trickle_and_preserves_unknown(self):
        stop=threading.Event();finished=threading.Event();posts=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                posts.append(True);self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.send_header('Content-Type','text/event-stream')
                self.send_header('Connection','close');self.end_headers()
                try:
                    self.wfile.write(wire(chunk('First. '),done=False).getvalue());self.wfile.flush()
                    for byte in b'data: '+b' '*100:
                        if stop.wait(.04):break
                        self.wfile.write(bytes([byte]));self.wfile.flush()
                except OSError:pass
                finally:finished.set()
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        config=json.loads((ROOT/'config.example.json').read_text())
        config['network']['llm_base_url']='http://127.0.0.1:'+str(server.server_port)+'/v1'
        config['llm']['model']='configured';config['streaming']['content_request_seconds']=.3
        ownership=brains.ModelExecutionOwnership()
        try:
            with patch.object(brains,'MODEL_EXECUTION',ownership):
                began=stream.time.monotonic();stream.prepare_endpoint(config);reader=stream.TimelyReader(config,[dict(role='user',content='fixture')])
                self.assertEqual(next(reader),'First. ');reader.close()
                self.assertLess(stream.time.monotonic()-began,1.3)
            self.assertEqual(posts,[True]);self.assertTrue(reader.metadata()['producer_quiesced'])
            self.assertFalse(reader.metadata()['terminal_verified'])
            self.assertEqual(ownership.status(brains.model_identity(config)),dict(active=False,unknown=True))
        finally:stop.set();finished.wait(2);server.shutdown();server.server_close();thread.join(2)

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
                stream.prepare_endpoint(config);tokens=stream.completion_tokens(config,[dict(role='user',content='fixture')])
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
                stream.prepare_endpoint(config);tokens=stream.completion_tokens(config,[dict(role='user',content='fixture')])
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
        guard=patch.object(brains,'MODEL_EXECUTION',brains.ModelExecutionOwnership());guard.start();self.addCleanup(guard.stop)
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
            pipeline.body=[n for n in pipeline.body if getattr(n,'name',None) not in ('stream','__init__')]
            return ast.dump(tree,include_attributes=False)
        self.assertEqual(outside(self.old),outside(self.new))
        self.assertEqual(hashlib.sha256(self.new.encode()).hexdigest(),'0bc7617cdce2b61e5b80ad9ffab79e3f35d97e9b7bdb4ceae432028f5b665d8a')
        self.assertEqual(hashlib.sha256(self.brains_source.encode()).hexdigest(),'020e435e37602271d2d40160b055650f781b60a8ee9fc601e3b28d82444bdae6')

    def test_opt_in_startup_resolves_before_model_initialization_with_real_config_facade(self):
        tree=ast.parse(self.new)
        pipeline=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Pipeline')
        init=next(n for n in pipeline.body if getattr(n,'name',None)=='__init__')
        boundary=next(i for i,n in enumerate(init.body) if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Attribute) and t.attr=='http' for t in n.targets))
        for enabled in (False,True):
            values=json.loads((ROOT/'config.example.json').read_text());values['streaming']['content_tokens']=enabled
            class Config:
                def __getitem__(self,key):return values[key]
            config=Config();holder=SimpleNamespace()
            with patch.object(stream,'prepare_endpoint') as prepare:
                exec(compile(ast.Module(body=init.body[:boundary],type_ignores=[]),'readiness-prefix','exec'),
                    dict(self.module.__dict__,self=holder,config=config))
            self.assertIs(holder.config,config)
            if enabled:prepare.assert_called_once_with(config)
            else:prepare.assert_not_called()

    def test_actual_legacy_hook_reader_progresses_independently_and_done_follows_cleanup_with_history(self):
        p=self.pipeline();visited=[]
        values=p.config
        class Config:
            def __getitem__(self,key):return values[key]
        p.config=Config()  # Actual Config is a mapping facade without .get().
        def tokens(config,messages,**kwargs):
            self.assertEqual(messages[-3:],[dict(role='user',content='Remember'),dict(role='assistant',content='Remembered'),dict(role='user',content='Next')])
            kwargs['execution'].submitted()
            yield 'Первое. ';visited.append('lasttoken');yield 'Второе.'
            kwargs['execution'].terminal()
        with patch.object(stream,'completion_tokens',tokens):
            events=p.stream(dict(text='Next',session='existing'),'/text')
            self.assertEqual(next(events)['type'],'reply');self.assertEqual(visited,['lasttoken'])
            self.assertEqual(next(events)['type'],'audio')
            self.assertTrue(brains.MODEL_EXECUTION.status(brains.model_identity(p.config))['active'])
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
            release=threading.Event()
            def tokens(*args,**kwargs):
                kwargs['execution'].submitted()
                yield 'Первое. '
                if fail:
                    release.wait(2)
                    raise ValueError('MODEL FAILURE')
                kwargs['execution'].terminal()
            with patch.object(stream,'completion_tokens',tokens):
                events=p.stream(dict(text='Next',session='existing'),'/text')
                next(events);next(events)
                if fail:
                    release.set()
                    with self.assertRaises(RuntimeError):list(events)
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
