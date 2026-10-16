"""S2 synthetic source/schema/recognizer/queue fixtures; no devices or models."""
import ast
import base64
import copy
from contextlib import contextmanager
import importlib.util
import json
import os
import selectors
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from reachy_companion import provisional_stt as partial
from test_agent_live_latency_patch import load as load_agent
from test_stream_cleanup_overlay import load as load_voice
import test_capture_pump as s1

ROOT = Path(__file__).resolve().parents[1]
PCM = bytes(partial.MIN_FRAMES*2)
spec = importlib.util.spec_from_file_location('s2_builder', ROOT/'deploy/autonomous/prepare_provisional_stt.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


def bound(**changes):
    return dict(dict(boot='fixture-boot', microphone_epoch=1, policy_epoch=2, source_generation=1,
        utterance_id=1, revision=1, request_id='a'*32, window_start_frame=0,
        window_frames=partial.MIN_FRAMES), **changes)


def payload(**changes):
    return dict(dict(mode='recognize_only', version=1, binding=bound(),
                     pcm_base64=base64.b64encode(PCM).decode()), **changes)


def answer(request, text='one two', status='recognized'):
    return dict(mode='recognize_only', version=1, binding=copy.deepcopy(request['binding']),
                provisional=True, status=status, text=text)


def wait_for(predicate):
    end = time.monotonic()+1
    while not predicate() and time.monotonic() < end: time.sleep(.002)
    if not predicate(): raise AssertionError('Fixture condition did not complete')


class FakeLatch:
    def __init__(self): self.present=False; self.starts=[]; self.completions=0; self.request_id=None
    def exists(self): return self.present
    def begin(self, binding, received_end, deadline, *, permitted=None):
        if self.present: raise FileExistsError()
        if permitted is not None and not permitted(): raise TimeoutError()
        self.request_id=binding['request_id']; self.deadline=deadline
        self.present=True; self.starts.append((copy.deepcopy(binding), received_end, deadline))
    def complete(self, deadline=None, *, permitted=None):
        if permitted is not None and not permitted(): raise TimeoutError()
        if deadline is not None and deadline!=self.deadline: raise ValueError()
        self.present=False; self.completions+=1; self.request_id=None


class S2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before, cls.files = builder.candidate()
        cls.voice = load_voice(cls.files['PC/voice.py'].decode())
        cls.agent = load_agent(cls.files['Robot/agent.py'].decode())
        cls.recognition = ModuleType('recognition_fixture')
        exec(compile(cls.files['PC/recognition.py'], 'recognition-S2.py', 'exec'), cls.recognition.__dict__)
        cls.pump_module = ModuleType('pump_fixture')
        cls.pump_module.__package__ = 'reachy_companion'
        # Dataclasses require registration during class construction.
        import sys
        with patch.dict(sys.modules, {'pump_fixture': cls.pump_module}):
            exec(compile(cls.files['Robot/capture_pump.py'], 'capture-S2.py', 'exec'), cls.pump_module.__dict__)

    def pipeline(self):
        p = self.voice.Pipeline.__new__(self.voice.Pipeline)
        p.config = json.loads((ROOT/'config.example.json').read_text())
        p.config['conversation']['provisional_stt_enabled'] = True
        p.stt = SimpleNamespace(loaded_backend='faster_whisper', settings=dict(backend='faster_whisper'),
                               transcribe_provisional=Mock(return_value='one two'))
        for name in ('transcribe', 'classify', 'request', 'synthesize', 'stream'): setattr(p, name, Mock())
        p.sounds = SimpleNamespace(classify=Mock())
        p.sessions = dict(existing=[dict(role='user', content='fixture memory')])
        p.agent_sessions = dict(existing='fixture'); p.last_turn = dict(existing=True)
        return p

    def client(self, transport=None, *, agent=None, latch=None, generation=1):
        a = agent or SimpleNamespace()
        clock = s1.Clock()
        if isinstance(latch,partial.IntentLatch): latch.clock=clock
        pump = SimpleNamespace(binding=('fixture-boot', 1, 2), generation=generation)
        transport = transport or (lambda request, deadline: answer(request))
        fresh = lambda item: item.received_end <= clock() <= item.deadline
        client = partial.ProvisionalClient(a, pump, fresh, clock=clock, transport=transport,
                                            latch=latch or FakeLatch())
        client.begin(1)
        self.addCleanup(client.close)
        return a, clock, client

    def test_exact_layered_builder_transport_derivation_and_s1_unchanged(self):
        builder.transport_derivation()
        self.assertEqual(builder.digest(self.before['recognition']), builder.RECOGNITION_INSTALLED)
        self.assertEqual(builder.digest(self.before['voice']), 'bbdb7be523946396cedd16a2f629caabdb54bf3d9979bfd5e7403f2730995764')
        self.assertEqual(builder.digest(self.before['agent']), 'cf50c54680d8e30fb97090e80d0e687a9dad903159f464d2211414aefcaca069')
        self.assertEqual(builder.digest(self.before['capture']), 'b7b1ffa551d8b3ad4346cc2920f0e17d04e37c2300d8583abf336ea90fb9e5b0')
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            target = Path(directory)/'bundle'; manifest = builder.build(target)
            self.assertFalse(manifest['default_enabled']); self.assertFalse(manifest['partial_acceptance'])
            with self.assertRaises(FileExistsError): builder.build(target)
        for name in ('provisional_stt.py', 'owned_http.py'):
            self.assertEqual(self.files['PC/'+name], self.files['Robot/'+name])
        transport = ast.parse(self.files['Robot/owned_http.py'])
        self.assertFalse(any(isinstance(n, ast.Name) and n.id == 'ENDPOINTS' for n in ast.walk(transport)))

    def test_provisional_never_classifies_calls_llm_sound_or_changes_context(self):
        p = self.pipeline(); context = copy.deepcopy((p.sessions, p.agent_sessions, p.last_turn))
        value = p.transcribe_response(payload())
        self.assertEqual(value['text'], 'one two'); self.assertTrue(value['provisional'])
        self.assertNotIn('decision', value)
        for name in ('transcribe', 'classify', 'request', 'synthesize', 'stream'): getattr(p, name).assert_not_called()
        p.sounds.classify.assert_not_called()
        self.assertEqual(context, (p.sessions, p.agent_sessions, p.last_turn))
        p.stt.transcribe_provisional.assert_called_once_with(PCM)

    def test_default_off_and_loaded_backend_guard_cannot_fall_through_to_final(self):
        for flag in (False, 1, 'true', None):
            p = self.pipeline(); p.config['conversation']['provisional_stt_enabled'] = flag
            with self.assertRaises(ValueError): p.transcribe_response(payload())
            p.stt.transcribe_provisional.assert_not_called(); p.classify.assert_not_called()
        p = self.pipeline(); p.stt.loaded_backend = 'vosk'
        with self.assertRaises(ValueError): p.transcribe_response(payload())
        p.stt.transcribe_provisional.assert_not_called()

    def test_missing_provisional_mode_and_busy_response_never_classify(self):
        p=self.pipeline(); missing=payload(); missing.pop('mode')
        with self.assertRaises(ValueError): p.transcribe_response(missing)
        p.classify.assert_not_called(); p.transcribe.assert_not_called()
        p.stt.transcribe_provisional.return_value=None
        result=p.transcribe_response(payload())
        self.assertEqual(result['status'],'busy'); self.assertEqual(result['text'],'')
        p.classify.assert_not_called(); p.sounds.classify.assert_not_called()

    def test_ordinary_transcribe_path_and_decision_remain_unchanged(self):
        p = self.pipeline(); p.transcribe.return_value = 'final'; p.classify.return_value = dict(action='answer')
        p.config['conversation']['provisional_stt_enabled'] = False
        result = p.transcribe_response(dict(pcm_base64=base64.b64encode(PCM).decode()))
        self.assertEqual(result, dict(ok=True, transcript='final', decision=dict(action='answer')))
        p.transcribe.assert_called_once_with(PCM); p.classify.assert_called_once_with('final')
        p.stt.transcribe_provisional.assert_not_called()

    def test_schema_rejects_missing_unknown_bool_duplicate_nonfinite_and_pcm_bounds(self):
        bad = [dict(payload(), extra=True), {k:v for k,v in payload().items() if k != 'binding'},
               payload(version=True), payload(mode='final'), payload(pcm_base64='?'), payload(pcm_base64='AA=='),
               payload(pcm_base64='A'*(partial.MAX_REQUEST+1))]
        for key in partial.BINDING_FIELDS - {'boot', 'request_id'}:
            bad.append(payload(binding=bound(**{key: True})))
        for value in ('bad id', 'a'*31, 'G'*32): bad.append(payload(binding=bound(request_id=value)))
        bad.append(payload(binding=bound(window_frames=partial.WINDOW_FRAMES+1)))
        for value in bad:
            with self.assertRaises(ValueError): partial.request(value)
        for raw in (b'{"mode":"recognize_only","mode":"recognize_only"}', b'{"mode":NaN}',
                    b'x'*(partial.MAX_REQUEST+1)):
            with self.assertRaises(ValueError): partial.parse_request(raw)
        duplicate = json.dumps(payload()).replace('"revision": 1', '"revision": 1, "revision": 2').encode()
        with self.assertRaises(ValueError): partial.parse_request(duplicate)

    def test_response_binding_extra_action_and_limits_are_strict(self):
        good = answer(payload())
        for value in (dict(good, decision=dict(action='stop')), dict(good, provisional=1),
                      dict(good, binding=bound(revision=2)), dict(good, text='x'*(partial.MAX_TEXT+1)),
                      dict(good, status='busy', text='not empty')):
            with self.assertRaises(ValueError): partial.response(value, bound())

    def recognizer(self):
        r = self.recognition.Recognizer.__new__(self.recognition.Recognizer)
        r.config = dict(audio=dict(sample_rate=16000, max_input_seconds=30))
        r.settings = dict(backend='faster_whisper'); r.loaded_backend='faster_whisper'
        r.lock = threading.Lock(); r._decode_pcm = Mock(return_value='decoded')
        return r

    def test_loaded_recognizer_trylock_busy_is_failfast_and_does_not_decode(self):
        r = self.recognizer(); r.lock.acquire()
        try:
            began = time.monotonic(); self.assertIsNone(r.transcribe_provisional(PCM))
            self.assertLess(time.monotonic()-began, .1); r._decode_pcm.assert_not_called()
        finally: r.lock.release()
        self.assertEqual(r.transcribe_provisional(PCM), 'decoded')
        self.assertTrue(r.lock.acquire(False)); r.lock.release()

    def test_partial_and_ordinary_final_share_one_model_lock_without_partial_queue(self):
        r = self.recognizer(); entered=threading.Event(); release=threading.Event(); calls=[]; active=[0]; peak=[0]
        def decode(pcm):
            active[0]+=1; peak[0]=max(peak[0],active[0]); calls.append(True)
            try:
                if len(calls)==1: entered.set(); self.assertTrue(release.wait(1))
                return 'decoded'
            finally: active[0]-=1
        r._decode_pcm=decode
        first=threading.Thread(target=r.transcribe_provisional,args=(PCM,)); first.start(); self.assertTrue(entered.wait(1))
        final=threading.Thread(target=r.transcribe,args=(PCM,)); final.start()
        for _ in range(10): self.assertIsNone(r.transcribe_provisional(PCM))
        self.assertEqual(len(calls),1); release.set(); first.join(1); final.join(1)
        self.assertFalse(first.is_alive()); self.assertFalse(final.is_alive())
        self.assertEqual(len(calls),2); self.assertEqual(peak[0],1)

    def test_recognizer_shared_decode_is_exact_original_model_code(self):
        old = ast.parse(self.before['recognition']); new = ast.parse(self.files['PC/recognition.py'])
        old_method = next(n for n in ast.walk(old) if isinstance(n,ast.FunctionDef) and n.name=='transcribe')
        old_decode = next(n for n in old_method.body if isinstance(n,ast.With)).body
        new_method = next(n for n in ast.walk(new) if isinstance(n,ast.FunctionDef) and n.name=='_decode_pcm')
        self.assertEqual([ast.dump(n,include_attributes=False) for n in old_decode],
                         [ast.dump(n,include_attributes=False) for n in new_method.body[1:]])
        old_init=next(n for n in ast.walk(old) if isinstance(n,ast.FunctionDef) and n.name=='__init__')
        new_init=next(n for n in ast.walk(new) if isinstance(n,ast.FunctionDef) and n.name=='__init__')
        new_init.body=new_init.body[:-1]  # Only record the backend already loaded.
        self.assertEqual(ast.dump(old_init,include_attributes=False),ast.dump(new_init,include_attributes=False))

    def test_client_active_one_latest_one_cadence_and_revision_drop(self):
        entered=threading.Event(); release=threading.Event(); calls=[]
        def transport(request, deadline):
            calls.append(request['binding']['revision'])
            if len(calls)==1: entered.set(); self.assertTrue(release.wait(1))
            return answer(request)
        a, clock, client=self.client(transport); client.start()
        self.assertTrue(client.offer(1,PCM,clock(),0)); self.assertTrue(entered.wait(1))
        self.assertFalse(client.offer(1,PCM,clock()+.1,0))
        clock.now+=.6; self.assertTrue(client.offer(1,PCM,clock(),0))
        clock.now+=.6; self.assertTrue(client.offer(1,PCM,clock(),0))
        self.assertEqual(client.pending.binding['revision'],3); self.assertTrue(client.metrics()['active'])
        release.set(); wait_for(lambda: client.latest is not None)
        self.assertEqual(calls,[1,3]); self.assertEqual(client.latest['binding']['revision'],3)

    def test_stable_prefix_requires_two_same_origin_results_and_resets_on_shift(self):
        texts=iter(('one two','one three','one three'))
        a, clock, client=self.client(lambda request,deadline:answer(request,next(texts))); client.start()
        client.offer(1,PCM,clock(),0); wait_for(lambda:client.latest is not None)
        self.assertEqual(client.latest['stable_prefix'],'')
        clock.now+=.6; client.offer(1,PCM,clock(),0); wait_for(lambda:client.latest is not None)
        self.assertEqual(client.latest['stable_prefix'],'one')
        clock.now+=.6; client.offer(1,PCM,clock(),1600); wait_for(lambda:client.latest is not None)
        self.assertEqual(client.latest['stable_prefix'],'')
        client.begin(2); self.assertIsNone(client.latest); self.assertIsNone(client.previous)

    def test_endpoint_clears_partial_and_late_response_never_becomes_final(self):
        entered=threading.Event(); release=threading.Event()
        def transport(request,deadline): entered.set(); self.assertTrue(release.wait(1)); return answer(request)
        a,clock,client=self.client(transport); client.start(); client.offer(1,PCM,clock(),0)
        self.assertTrue(entered.wait(1)); client.endpoint(1); release.set()
        wait_for(lambda:not client.active)
        self.assertIsNone(client.latest); self.assertIsNone(client.pending)
        self.assertFalse(client.offer(1,PCM,clock()+1,0))

    def test_original_receipt_expiry_and_new_utterance_reject_late_result(self):
        for newer in (False,True):
            entered=threading.Event(); release=threading.Event()
            def transport(request,deadline): entered.set(); self.assertTrue(release.wait(1)); return answer(request)
            a,clock,client=self.client(transport); client.start(); client.offer(1,PCM,clock(),0)
            self.assertTrue(entered.wait(1))
            if newer: client.begin(2)
            else: clock.now+=40
            release.set(); wait_for(lambda:not client.active)
            self.assertIsNone(client.latest); self.assertEqual(client.latch.completions,1)

    def test_timeout_is_sticky_across_source_generation_and_new_agent_reload(self):
        latch=FakeLatch(); transport=Mock(side_effect=TimeoutError('fixture'))
        a,clock,client=self.client(transport,latch=latch); client.start(); client.offer(1,PCM,clock(),0)
        wait_for(lambda:client.stopped); self.assertTrue(a._provisional_unknown); self.assertTrue(latch.exists())
        for owner in (a,SimpleNamespace()):
            retry=Mock(); _,clock,next_client=self.client(retry,agent=owner,latch=latch,generation=2)
            next_client.start(); self.assertFalse(next_client.offer(1,PCM,clock(),0))
            self.assertTrue(owner._provisional_unknown); retry.assert_not_called()
        self.assertEqual(transport.call_count,1)

    def test_marker_durable_before_post_removed_only_after_bound_completion(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            path=Path(directory)/'intent.json'; latch=partial.IntentLatch(path,clock=lambda:100.)
            def transport(request,deadline):
                self.assertTrue(path.exists()); self.assertEqual(path.stat().st_mode&0o777,0o600)
                value=json.loads(path.read_text()); self.assertEqual(value['binding'],request['binding'])
                self.assertEqual(value['deadline'],deadline); self.assertNotIn('pcm_base64',value)
                self.assertNotIn('text',value); return answer(request)
            a,clock,client=self.client(transport,latch=latch); client.start(); client.offer(1,PCM,clock(),0)
            wait_for(lambda:client.latest is not None); self.assertFalse(path.exists())

    def test_intent_exclusive_reload_no_adoption_symlink_and_replaced_identity(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            path=Path(directory)/'intent.json'; first=partial.IntentLatch(path,clock=lambda:100.)
            first.begin(bound(),100,102)
            second=partial.IntentLatch(path,clock=lambda:100.); self.assertTrue(second.exists())
            retry=Mock(); owner,clock,reloaded=self.client(retry,latch=second)
            reloaded.start(); self.assertFalse(reloaded.offer(1,PCM,clock(),0))
            self.assertTrue(owner._provisional_unknown); retry.assert_not_called()
            with self.assertRaises(FileExistsError): second.begin(bound(request_id='b'*32),100,102)
            with self.assertRaises(ValueError): second.complete()
            path.unlink(); replacement=partial.IntentLatch(path,clock=lambda:100.); replacement.begin(bound(request_id='b'*32),100,102)
            with self.assertRaises(ValueError): first.complete()
            self.assertTrue(path.exists()); replacement.complete(); self.assertFalse(path.exists())
            target=Path(directory)/'outside'; target.write_text('fixture')
            path.symlink_to(target); third=partial.IntentLatch(path,clock=lambda:100.); self.assertTrue(third.exists())
            with self.assertRaises(FileExistsError): third.begin(bound(),100,102)
            self.assertEqual(target.read_text(),'fixture')

    def test_late_old_response_cannot_remove_replacement_intent_or_publish_text(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            path=Path(directory)/'intent'; entered=threading.Event(); release=threading.Event()
            def transport(request,deadline): entered.set(); self.assertTrue(release.wait(1)); return answer(request)
            owner,clock,client=self.client(transport,latch=partial.IntentLatch(path,clock=lambda:100.))
            client.start(); client.offer(1,PCM,clock(),0); self.assertTrue(entered.wait(1))
            path.unlink(); replacement=partial.IntentLatch(path,clock=lambda:100.)
            replacement.begin(bound(request_id='b'*32,source_generation=2),100,102)
            release.set(); wait_for(lambda:client.stopped)
            self.assertTrue(owner._provisional_unknown); self.assertIsNone(client.latest)
            self.assertEqual(json.loads(path.read_text())['request_id'],'b'*32)

    def test_concurrent_exclusive_intents_allow_only_one_post(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            path=Path(directory)/'intent'; barrier=threading.Barrier(2)
            entered=threading.Event(); release=threading.Event(); posts=[]
            class Latch(partial.IntentLatch):
                def begin(self,*args,**kwargs): barrier.wait(1); return super().begin(*args,**kwargs)
            def transport(request,deadline):
                posts.append(request['binding']['request_id']); entered.set()
                self.assertTrue(release.wait(1)); return answer(request)
            clients=[]
            for _ in range(2):
                owner,clock,client=self.client(transport,latch=Latch(path)); clients.append((owner,clock,client))
            for owner,clock,client in clients: client.start(); client.offer(1,PCM,clock(),0)
            self.assertTrue(entered.wait(1)); wait_for(lambda:any(client.stopped for _,_,client in clients))
            self.assertEqual(len(posts),1); release.set()
            wait_for(lambda:all(not client.active for _,_,client in clients))
            self.assertEqual(len(posts),1)

    def test_last_stat_checkpoint_serializes_legitimate_new_intent_and_preserves_it(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            path=Path(directory)/'intent'; old=partial.IntentLatch(path,clock=lambda:100.); old.begin(bound(),100,102)
            newer=partial.IntentLatch(path,clock=lambda:100.); attempted=threading.Event(); completed=threading.Event(); errors=[]
            def replace():
                attempted.set()
                try: newer.begin(bound(request_id='b'*32,source_generation=2),100,102)
                except Exception as error: errors.append(error)
                finally: completed.set()
            replacement=threading.Thread(target=replace); observed=[]; original=partial.os.stat
            def last_stat(name,*args,**kwargs):
                value=original(name,*args,**kwargs)
                if name==path.name and kwargs.get('follow_symlinks') is False and not observed:
                    observed.append(True); replacement.start(); self.assertTrue(attempted.wait(1))
                    self.assertFalse(completed.wait(.05))
                return value
            with patch.object(partial.os,'stat',side_effect=last_stat): old.complete()
            replacement.join(1); self.assertFalse(replacement.is_alive()); self.assertEqual(errors,[])
            self.assertTrue(observed); self.assertTrue(path.exists())
            self.assertEqual(json.loads(path.read_text())['request_id'],'b'*32)
            with self.assertRaises(ValueError): old.complete()
            self.assertTrue(path.exists())
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()),['intent'])  # No replaceable lockfile.

    def test_namespace_lock_is_same_directory_inode_across_another_process(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            path=Path(directory)/'intent'; latch=partial.IntentLatch(path)
            code='''import os,sys,time
from reachy_companion.provisional_stt import IntentLatch
print('attempt',flush=True)
with IntentLatch(sys.argv[1]).namespace(time.monotonic()+2) as descriptor:
    value=os.fstat(descriptor)
    print(str(value.st_dev)+':'+str(value.st_ino),flush=True)
'''
            process=None
            try:
                with latch.namespace(time.monotonic()+2) as descriptor:
                    expected=os.fstat(descriptor)
                    process=subprocess.Popen([sys.executable,'-B','-c',code,str(path)],
                        env=dict(os.environ,PYTHONPATH=str(ROOT/'src')),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                    selector=selectors.DefaultSelector(); selector.register(process.stdout,selectors.EVENT_READ)
                    try:
                        self.assertTrue(selector.select(1)); self.assertEqual(process.stdout.readline(),b'attempt\n')
                        self.assertFalse(selector.select(.05)); self.assertIsNone(process.poll())
                    finally: selector.close()
                output,error=process.communicate(timeout=1)
                self.assertEqual(process.returncode,0,error.decode())
                self.assertEqual(output.strip(),('%s:%s'%(expected.st_dev,expected.st_ino)).encode())
                self.assertEqual(list(Path(directory).iterdir()),[])
            finally:
                if process is not None and process.poll() is None: process.kill(); process.communicate(timeout=1)

    def test_namespace_begin_and_completion_wait_only_original_deadline(self):
        for completing in (False,True):
            with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
                path=Path(directory)/'intent'; owner=partial.IntentLatch(path)
                received=time.monotonic(); deadline=received+.15
                if completing: owner.begin(bound(),received,deadline)
                entered=threading.Event(); release=threading.Event(); errors=[]
                def holder():
                    try:
                        with partial.IntentLatch(path).namespace(time.monotonic()+2):
                            entered.set(); release.wait(1)
                    except Exception as error: errors.append(error)
                thread=threading.Thread(target=holder); thread.start(); self.assertTrue(entered.wait(1))
                began=time.monotonic()
                try:
                    with self.assertRaises(TimeoutError):
                        if completing: owner.complete(deadline,permitted=lambda:True)
                        else: owner.begin(bound(),received,deadline,permitted=lambda:True)
                    self.assertLess(time.monotonic()-began,.5)
                    self.assertEqual(path.exists(),completing)
                    if completing:
                        with self.assertRaises(ValueError): owner.complete(time.monotonic()+2)
                finally:
                    release.set(); thread.join(1)
                self.assertFalse(thread.is_alive()); self.assertEqual(errors,[])
                self.assertEqual(path.exists(),completing)

    def test_retirement_cancels_lock_wait_and_new_generations_start_no_waiting_workers(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            path=Path(directory)/'intent'; held=threading.Event(); release=threading.Event(); attempted=threading.Event()
            def holder():
                with partial.IntentLatch(path).namespace(time.monotonic()+2):
                    held.set(); release.wait(1)
            thread=threading.Thread(target=holder); thread.start(); self.assertTrue(held.wait(1))
            class ObservedLatch(partial.IntentLatch):
                @contextmanager
                def namespace(self,deadline,permitted=None):
                    attempted.set()
                    with super().namespace(deadline,permitted) as descriptor: yield descriptor
            owner=SimpleNamespace(); transport=Mock()
            fresh=lambda item:item.received_end<=time.monotonic()<=item.deadline
            client=partial.ProvisionalClient(owner,SimpleNamespace(binding=('fixture',1,2),generation=1),
                fresh,latch=ObservedLatch(path),transport=transport)
            self.addCleanup(client.close)
            try:
                client.begin(1); client.start(); client.offer(1,PCM,time.monotonic(),0)
                self.assertTrue(attempted.wait(1)); self.assertTrue(client.active)
                began=time.monotonic(); client.retire(); self.assertLess(time.monotonic()-began,.05)
                client.thread.join(.3); self.assertFalse(client.thread.is_alive())
                self.assertTrue(owner._provisional_unknown); self.assertFalse(path.exists())
                for generation in range(2,12):
                    next_client=partial.ProvisionalClient(owner,
                        SimpleNamespace(binding=('fixture',1,2),generation=generation),fresh,
                        latch=partial.IntentLatch(path),transport=transport)
                    self.addCleanup(next_client.close); next_client.begin(1); next_client.start()
                    self.assertFalse(next_client.offer(1,PCM,time.monotonic(),0))
                    self.assertIsNone(next_client.thread)
                transport.assert_not_called()
            finally:
                release.set(); thread.join(1)
            self.assertFalse(thread.is_alive())

    def test_intent_parent_nofollow_partial_write_and_digest_tamper_fail_closed(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            root=Path(directory); parent=root/'real'; parent.mkdir(); link=root/'link'; link.symlink_to(parent,target_is_directory=True)
            with self.assertRaises(OSError): partial.IntentLatch(link/'intent',clock=lambda:100.).exists()
            path=parent/'intent'; latch=partial.IntentLatch(path,clock=lambda:100.)
            with patch.object(partial.os,'fsync',side_effect=OSError('fixture')):
                with self.assertRaises(OSError): latch.begin(bound(),100,102)
            self.assertTrue(path.exists())
            with self.assertRaises(FileExistsError): partial.IntentLatch(path,clock=lambda:100.).begin(bound(),100,102)
            path.unlink(); latch=partial.IntentLatch(path,clock=lambda:100.); latch.begin(bound(),100,102)
            raw=path.read_bytes().replace(b'fixture-boot',b'changed-boot'); path.write_bytes(raw)
            with self.assertRaises(ValueError): latch.complete()
            self.assertTrue(path.exists())

    def test_s2_default_false_and_primed_status_do_not_create_partial_client(self):
        a=s1.agent()
        with patch('reachy_companion.provisional_stt.ProvisionalClient') as constructor:
            pump=self.pump_module.CapturePump(a,1)
        self.assertIsNone(pump.provisional); constructor.assert_not_called()
        a.config['conversation']['capture_pump_enabled']=False
        a.config['conversation']['provisional_stt_enabled']=True
        instance=self.agent.Agent.__new__(self.agent.Agent); instance.__dict__.update(vars(a))
        with self.assertRaises(ValueError): instance._capture_enabled()

    def test_s2_default_false_voice_operation_and_status_shape_match_s1(self):
        fixture_class=s1.AgentStreamTimingTests; fixture_class.setUpClass(); fixture=fixture_class()
        old=load_agent(self.before['agent'].decode())
        a,old_result,old_order,old_writes,_=fixture.stream(module=old)
        a,result,order,writes,_=fixture.stream(module=self.agent)
        self.assertEqual((result,order,writes),(old_result,old_order,old_writes))
        original=dict(fixture=True)
        a._status_without_provisional=Mock(return_value=original)
        self.assertIs(a.status(),original); self.assertNotIn('provisional_stt',original)

    def test_s2_pump_partial_before_endpoint_and_original_final_once(self):
        a=s1.agent(); a.audio['max_recording_seconds']=4
        a.config['conversation'].update(capture_pump_enabled=True,provisional_stt_enabled=True)
        clock=s1.Clock(); clients=[]; real_client=partial.ProvisionalClient
        def constructor(agent,pump,fresh,**kwargs):
            client=real_client(agent,pump,fresh,clock=clock,
                transport=lambda request,deadline:answer(request),latch=FakeLatch())
            clients.append(client); return client
        with patch('reachy_companion.provisional_stt.ProvisionalClient',side_effect=constructor):
            pump=self.pump_module.CapturePump(a,1,clock=clock)
        client=clients[0]; self.addCleanup(client.close); client.start()
        for _ in range(16): clock.now+=.03; pump._publish(s1.LOUD,clock())
        wait_for(lambda:client.latest is not None)
        self.assertTrue(pump.assembler.frames); self.assertIsNone(pump.latest)
        self.assertGreater(client.metrics()['text_chars'],0)
        for _ in range(2): clock.now+=.03; pump._publish(s1.QUIET,clock())
        packet=pump.latest; self.assertTrue(packet.final)
        self.assertTrue(pump.claim(packet)); self.assertFalse(pump.claim(packet))
        self.assertIsNone(client.latest); self.assertIsNone(client.pending)
        pump.retire(); self.assertTrue(client.stopped)

    def test_agent_final_stt_and_model_dispatch_once_after_provisional_windows(self):
        a=self.agent.Agent.__new__(self.agent.Agent); a.__dict__.update(vars(s1.agent()))
        a.config['conversation'].update(capture_pump_enabled=True,provisional_stt_enabled=True,
                                        greet_on_start=False,wake_on_start=False)
        clock=s1.Clock(); real=partial.ProvisionalClient; clients=[]
        def constructor(agent,pump,fresh,**kwargs):
            client=real(agent,pump,fresh,clock=clock,latch=FakeLatch(),
                        transport=lambda request,deadline:answer(request))
            clients.append(client); return client
        with patch('reachy_companion.provisional_stt.ProvisionalClient',side_effect=constructor):
            pump=self.pump_module.CapturePump(a,1,clock=clock)
        client=clients[0]; self.addCleanup(client.close); client.start()
        for _ in range(16): clock.now+=.03; pump._publish(s1.LOUD,clock())
        wait_for(lambda:client.latest is not None)
        for _ in range(2): clock.now+=.03; pump._publish(s1.QUIET,clock())
        packet=pump.latest; self.assertTrue(pump.claim(packet)); pump.mode(True)
        a._capture_pump=pump; a._capture_packet=packet; a.capture=Mock(return_value=packet.pcm)
        a.pending_pcm=a.resume_audio=None; a.audio_lock=threading.Lock(); a.turns=0; a.playback_configured=True
        a.operator_status=Mock(return_value=dict(agent_boot_id=a.agent_boot_id,microphone_epoch=a.microphone_epoch,
            microphone_owner_id='fixture',motion_policy=dict(epoch=3)))
        paths=[]
        def request(base,path,*args,**kwargs):
            paths.append(path)
            if path=='/health': return dict(ok=True)
            if path=='/status': return dict(ownership=dict(state='free'))
            self.assertEqual(path,'/transcribe')
            return dict(ok=True,transcript='ordinary fixture question',decision=dict(action='answer'))
        a.request=request; a.voice=Mock(return_value=dict(reply='fixture answer')); waits=[]
        def wait(**kwargs):
            if not waits: waits.append(True); return True
            a.stopping.set(); return False
        a.listening.wait=wait; a.run()
        self.assertEqual(paths.count('/transcribe'),1); a.voice.assert_called_once()
        self.assertEqual(a.voice.call_args.args[0],'/text'); self.assertEqual(a.turns,1)
        self.assertIsNone(client.latest)


if __name__ == '__main__': unittest.main()
