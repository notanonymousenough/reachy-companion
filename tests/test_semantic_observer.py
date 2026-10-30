"""Synthetic PTS/observer/process contracts; no SDK camera or model is opened."""
import contextlib
import io
import json
import subprocess
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

from reachy_companion import semantic_observer as S
from reachy_companion import snapshot_vision as V


def frame(now=None, ttl=10):
    now = time.monotonic() if now is None else now
    return dict(frame_id='a'*32, pts_ns=0, previous_pts_ns=0, all_sample_pts_zero=True,
                received_monotonic=now-.2, previous_received_monotonic=now-.3,
                received_sample_count=2,ipc_delivery_progress_verified=True,
                source_presentation_time_verified=False,source_capture_time_verified=False,
                timestamp_reference='local_ipc_sample_receipt_source_and_exposure_unknown',
                expires_monotonic=now+ttl,camera_closed=True)


class SemanticChecks(unittest.TestCase):
    def test_result_keeps_source_and_exposure_unknown_and_ttl_from_receipt(self):
        f=frame(100)
        result=S.semantic_result(f,'На столе синяя чашка.',101)
        self.assertIsNone(result['source_presentation_age_s'])
        self.assertAlmostEqual(result['receipt_age_s'],1.2)
        self.assertIsNone(result['physical_exposure_age_s']['upper'])
        obs=result['observation']
        self.assertEqual(obs['observed_monotonic'],99.8)
        self.assertAlmostEqual(obs['observed_monotonic']+obs['ttl_s'],f['expires_monotonic'])
        self.assertIn('source presentation and physical exposure age unknown',obs['summary'])
        self.assertEqual(obs['source'],'shared-camera-ipc-receipt')
        for changed in (dict(ipc_delivery_progress_verified=False),dict(source_capture_time_verified=True),
                        dict(source_presentation_time_verified=True),dict(expires_monotonic=100),dict(received_sample_count=1)):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                S.semantic_result(dict(f,**changed),'caption',101)

    def test_observer_publishes_only_after_terminal_and_current_authority(self):
        entered, release = threading.Event(), threading.Event()
        control = dict(enabled=True, binding={'boot': 'b', 'epoch': 1})
        outputs = []
        def authority():
            return dict(control['binding']), control['enabled'], False
        def runner(packet, read, binding, available, cancel, **kwargs):
            entered.set()
            release.wait(2)
            return dict(result=S.semantic_result(frame(), 'Красная коробка.', time.monotonic()),
                        model_execution_unknown=False)
        observer = S.SemanticObserver(dict(network=dict(llm_base_url='http://127.0.0.1:1234/v1'), llm=dict(model='loaded')),
                                      authority, outputs.append, model_available=lambda: True, runner=runner)
        self.addCleanup(release.set)
        self.addCleanup(observer.close)
        observer.advance()
        self.assertTrue(entered.wait(1))
        self.assertTrue(observer.status()['execution_busy'])
        self.assertEqual(outputs, [])
        control['binding']['epoch'] = 2
        observer.advance()
        self.assertTrue(observer.cancel.is_set())
        self.assertTrue(observer.status()['execution_busy'])
        release.set()
        until = time.monotonic()+2
        while observer.future is not None and time.monotonic() < until:
            observer.advance();time.sleep(.001)
        self.assertEqual(outputs, [])
        self.assertEqual(observer.counts['discarded'], 1)
        self.assertFalse(observer.status()['execution_busy'])

    def test_observer_emits_real_contract_shape_and_latches_unknown(self):
        for unknown in (False, True):
            output = []
            def runner(*args, **kwargs):
                return dict(result=None if unknown else S.semantic_result(frame(), 'Жёлтая лампа.', time.monotonic()),
                            model_execution_unknown=unknown)
            observer = S.SemanticObserver(dict(network=dict(llm_base_url='local'), llm=dict(model='loaded')),
                lambda: ({'epoch': 1}, True, False), output.append, model_available=lambda: True, runner=runner)
            self.addCleanup(observer.close)
            observer.advance()
            until = time.monotonic()+2
            while observer.future is not None and time.monotonic() < until:
                observer.advance();time.sleep(.001)
            self.assertEqual(len(output), 0 if unknown else 1)
            self.assertEqual(observer.model_unknown, unknown)
            observer.next_due = 0
            if unknown:
                observer.advance()
                self.assertEqual(observer.counts['started'], 1)
                self.assertTrue(observer.status()['model_execution_busy'])

    def test_child_uses_loaded_local_vlm_and_no_pixels_in_stdout(self):
        f = frame()
        inventory = dict(models=[dict(key='loaded', loaded_instances=[dict(id='instance',config=dict(parallel=4))],
                                      capabilities=dict(vision=True))])
        calls = []
        class Connection:
            def __init__(self, *args, **kwargs):pass
            def request(self, method, path, body, headers):
                calls.append((path, json.loads(body), headers))
            def getresponse(self):
                raw = json.dumps(dict(model_instance_id='instance', output=[dict(type='message', content='На столе чашка.')])).encode()
                return types.SimpleNamespace(status=200, read=lambda n: raw)
            def close(self):pass
        out = io.StringIO()
        with patch.object(V, 'bind_parent_lifetime'), patch.object(V, 'native_address', return_value=('127.0.0.1', 1234)), \
             patch.object(V, 'get_models', return_value=inventory), patch.object(S, 'capture_frame', return_value=(b'PRIVATE_PIXEL_BYTES', f)), \
             patch.object(S.http.client, 'HTTPConnection', Connection), patch.object(S.sys, 'stdin', io.StringIO('go\n')), \
             contextlib.redirect_stdout(out):
            S.child(dict(deadline=time.monotonic()+15, ttl_s=15, model_timeout_s=8, model='loaded', llm_base_url='local'))
        events = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([e['event'] for e in events], ['ready_for_model', 'model_terminal', 'result'])
        self.assertNotIn('PRIVATE_PIXEL_BYTES', out.getvalue())
        self.assertNotIn('data:image', out.getvalue())
        path, packet, headers = calls[0]
        self.assertEqual(path, '/api/v1/chat')
        self.assertEqual(packet['model'], 'instance')
        self.assertEqual(packet['max_output_tokens'], 2048)
        self.assertFalse(packet['store'])
        self.assertEqual(packet['integrations'], [])
        self.assertNotIn('Authorization', headers)

    def test_capture_accepts_two_real_deliveries_with_zero_pts_without_source_age_claim(self):
        class Pixels:
            def reshape(self,*args):return self
            def __getitem__(self,key):return self
            def copy(self):return self
            def tobytes(self):return bytes(640*3)
        buffer=types.SimpleNamespace(pts=0,get_size=lambda:1280*720*3,extract_dup=lambda start,n:b'PRIVATE')
        caps=types.SimpleNamespace(get_structure=lambda i:types.SimpleNamespace(get_value=lambda key:{'width':1280,'height':720,'format':'BGR'}[key]))
        sample=types.SimpleNamespace(get_buffer=lambda:buffer,get_caps=lambda:caps)
        deliveries=[]
        def emit(*args):deliveries.append(1);return sample
        camera=types.SimpleNamespace(open=lambda:None,close=lambda:None,
            pipeline=types.SimpleNamespace(get_state=lambda timeout:types.SimpleNamespace(state='NULL')),
            _appsink_video=types.SimpleNamespace(get_property=lambda key:{'drop':True,'max-buffers':1}[key],emit=emit))
        gst=types.SimpleNamespace(version=lambda:(1,26,2,0),version_string=lambda:'1.26.2',State=types.SimpleNamespace(NULL='NULL'),
            ElementFactory=types.SimpleNamespace(find=lambda name:types.SimpleNamespace(get_plugin=lambda:types.SimpleNamespace(get_version=lambda:'1.26.2'))))
        modules={'numpy':types.SimpleNamespace(frombuffer=lambda *args,**kwargs:Pixels(),uint8='uint8'),
            'reachy_mini.media.camera_gstreamer':types.SimpleNamespace(GStreamerCamera=lambda **kwargs:camera,Gst=gst),
            'reachy_mini.media.camera_constants':types.SimpleNamespace(get_camera_specs_by_name=lambda name:'wireless')}
        now=[100.]
        def clock():now[0]+=.01;return now[0]
        with patch.dict(sys.modules,modules),patch.object(S.importlib.metadata,'version',return_value='1.11.0'):
            png,metadata=S.capture_frame(130,30,monotonic=clock)
        self.assertEqual(len(deliveries),2)
        self.assertTrue(png.startswith(b'\x89PNG'))
        self.assertTrue(metadata['all_sample_pts_zero'])
        self.assertTrue(metadata['ipc_delivery_progress_verified'])
        self.assertFalse(metadata['source_presentation_time_verified'])
        self.assertNotIn('source_progress_verified',metadata)
        self.assertEqual(len(metadata['frame_id']),32)
        result=S.semantic_result(metadata,'Чашка.',clock())
        self.assertIsNone(result['source_presentation_age_s'])
        self.assertIsNone(result['physical_exposure_age_s']['upper'])

    def test_complete_http_parse_failure_acknowledges_terminal_first(self):
        class Connection:
            def __init__(self, *args, **kwargs):pass
            def request(self, *args, **kwargs):pass
            def getresponse(self):return types.SimpleNamespace(status=200, read=lambda n:b'{invalid', length=0)
            def close(self):pass
        out = io.StringIO()
        inventory = dict(models=[dict(key='loaded',loaded_instances=[dict(id='instance',config=dict(parallel=4))],capabilities=dict(vision=True))])
        with patch.object(V,'bind_parent_lifetime'), patch.object(V,'native_address',return_value=('127.0.0.1',1234)), \
             patch.object(V,'get_models',return_value=inventory), patch.object(S,'capture_frame',return_value=(b'pixels',frame())), \
             patch.object(S.http.client,'HTTPConnection',Connection), patch.object(S.sys,'stdin',io.StringIO('go\n')), \
             contextlib.redirect_stdout(out), self.assertRaises(ValueError):
            S.child(dict(deadline=time.monotonic()+30,ttl_s=30,model_timeout_s=15,model='loaded',llm_base_url='local'))
        events=[json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([e['event'] for e in events],['ready_for_model','model_terminal'])
        self.assertEqual(events[-1]['http_status'],200)
        self.assertEqual(events[-1]['body_bytes'],8)

    def test_cache_recomputes_age_at_dispatch_and_expires_or_clears_epoch(self):
        now=[100.]
        cache=S.VisualContextCache(lambda:now[0])
        receipt=S.semantic_result(frame(100), 'Синяя чашка.',100)
        binding={'epoch':1}
        cache.install(receipt,binding)
        now[0]=103.
        ctx=cache.snapshot(binding,True,False)
        self.assertEqual(set(ctx),{'summary','source','frame_id','receipt_age_s','ttl_remaining_s','exposure_age_unknown'})
        self.assertAlmostEqual(ctx['receipt_age_s'],3.2)
        self.assertAlmostEqual(ctx['ttl_remaining_s'],6.999999)
        self.assertTrue(ctx['exposure_age_unknown'])
        self.assertIsNone(cache.snapshot({'epoch':2},True,False))
        self.assertIsNone(cache.snapshot(binding,True,False))
        cache.install(receipt,binding)
        self.assertIsNone(cache.snapshot(binding,True,True))
        cache.install(receipt,binding)
        now[0]=110.
        self.assertIsNone(cache.snapshot(binding,True,False))

    def test_known_pregrant_fault_latches_without_claiming_unknown_backend(self):
        def runner(*args,**kwargs):
            return dict(result=None,model_execution_unknown=False,failure_class='capture_or_config_failed')
        observer=S.SemanticObserver(dict(network=dict(llm_base_url='local'),llm=dict(model='loaded')),
            lambda:({'epoch':1},True,False),lambda item:None,model_available=lambda:True,runner=runner)
        self.addCleanup(observer.close)
        observer.advance()
        until=time.monotonic()+1
        while observer.future is not None and time.monotonic()<until:
            observer.advance();time.sleep(.001)
        self.assertFalse(observer.model_unknown)
        self.assertTrue(observer.failure_latched)
        observer.next_due=0;observer.advance()
        self.assertEqual(observer.counts['started'],1)

    def process_runner(self, script, cancel, available, *, cleanup_failure=False):
        processes = []
        def popen(command, **kwargs):
            self.assertEqual(command[0],'/venvs/mini_daemon/bin/python')
            self.assertEqual(kwargs['env']['PYTHONPATH'],str(S.Path(S.__file__).resolve().parents[1]))
            process = subprocess.Popen([sys.executable, '-c', script], **kwargs)
            if cleanup_failure:
                original=process.stdin
                def close():
                    original.close()
                    raise BrokenPipeError('synthetic cleanup failure')
                process.stdin=types.SimpleNamespace(write=original.write,flush=original.flush,close=close)
            processes.append(process)
            return process
        packet = dict(deadline=time.monotonic()+4, ttl_s=4, llm_base_url='local', model='loaded', model_timeout_s=1)
        result = S.run_child(packet, lambda: ({'epoch': 1}, True, False), {'epoch': 1}, available, cancel, popen=popen)
        self.assertTrue(all(p.poll() is not None for p in processes))
        return result

    def test_cancel_before_model_grant_reaps_child_without_unknown_backend(self):
        script = """import sys,json,time
json.loads(sys.stdin.readline())
print(json.dumps({'event':'ready_for_model','frame':{'expires_monotonic':time.monotonic()+4}}),flush=True)
sys.stdin.readline()
time.sleep(4)
"""
        cancel = threading.Event()
        def available():
            cancel.set()
            return False
        result = self.process_runner(script, cancel, available)
        self.assertTrue(result['withdrawn'])
        self.assertFalse(result['model_execution_unknown'])
        self.assertIsNone(result['failure_class'])

    def test_cancel_after_grant_reaps_process_and_keeps_backend_unknown(self):
        script = """import sys,json,time
json.loads(sys.stdin.readline())
print(json.dumps({'event':'ready_for_model','frame':{'expires_monotonic':time.monotonic()+4}}),flush=True)
assert sys.stdin.readline().strip()=='go'
time.sleep(4)
"""
        cancel = threading.Event()
        timer = threading.Timer(.2, cancel.set)
        timer.start()
        self.addCleanup(timer.cancel)
        result = self.process_runner(script, cancel, lambda: True)
        self.assertTrue(result['withdrawn'])
        self.assertTrue(result['model_execution_unknown'])
        self.assertIsNone(result['result'])

    def test_withdraw_after_grant_drains_terminal_and_never_returns_private_caption(self):
        script = """import sys,json,time
json.loads(sys.stdin.readline())
print(json.dumps({'event':'ready_for_model','frame':{'expires_monotonic':time.monotonic()+4}}),flush=True)
assert sys.stdin.readline().strip()=='go'
time.sleep(.35)
print(json.dumps({'event':'model_terminal','http_status':200,'body_bytes':123}),flush=True)
print(json.dumps({'event':'result','data':{'semantic_summary':'PRIVATE_WITHDRAWN_CAPTION'}}),flush=True)
"""
        cancel=threading.Event()
        timer=threading.Timer(.15,cancel.set);timer.start();self.addCleanup(timer.cancel)
        result=self.process_runner(script,cancel,lambda:True)
        self.assertTrue(result['withdrawn'])
        self.assertEqual(result['withdrawal_reason'],'authority_withdrawn')
        self.assertTrue(result['response_complete'])
        self.assertFalse(result['model_execution_unknown'])
        self.assertIsNone(result['result'])

    def test_child_rejects_single_slot_model_before_capture_or_submission(self):
        inventory=dict(models=[dict(key='loaded',loaded_instances=[dict(id='instance',config=dict(parallel=1))],capabilities=dict(vision=True))])
        with patch.object(V,'bind_parent_lifetime'),patch.object(V,'native_address',return_value=('127.0.0.1',1234)), \
             patch.object(V,'get_models',return_value=inventory), \
             patch.object(S,'capture_frame',side_effect=AssertionError('must reject before camera')), \
             patch.object(S.http.client,'HTTPConnection',side_effect=AssertionError('must not submit')):
            with self.assertRaises(ValueError):
                S.child(dict(deadline=time.monotonic()+30,ttl_s=30,model_timeout_s=15,model='loaded',llm_base_url='local'))

    def test_background_cooldown_begins_after_completion_not_start(self):
        from concurrent.futures import Future
        now=[100.]
        observer=S.SemanticObserver(dict(network=dict(llm_base_url='local'),llm=dict(model='loaded')),
            lambda:({'epoch':1},True,False),lambda item:None,model_available=lambda:True,clock=lambda:now[0])
        observer.future=Future();observer.cancel=threading.Event();observer.binding={'epoch':1}
        observer.next_due=115;observer.counts['started']=1
        now[0]=117
        observer.future.set_result(dict(result=None,model_execution_unknown=False))
        observer.advance()
        self.assertEqual(observer.next_due,132)
        self.assertEqual(observer.counts['started'],1)
        self.assertIsNone(observer.future)
        observer.close()

    def test_child_failure_after_complete_http_is_terminal_not_unknown(self):
        script = """import sys,json
json.loads(sys.stdin.readline())
print(json.dumps({'event':'ready_for_model','frame':{'expires_monotonic':__import__('time').monotonic()+4}}),flush=True)
assert sys.stdin.readline().strip()=='go'
print(json.dumps({'event':'model_terminal','http_status':200,'body_bytes':123}),flush=True)
print(json.dumps({'event':'failure'}),flush=True)
sys.exit(1)
"""
        result=self.process_runner(script,threading.Event(),lambda:True)
        self.assertFalse(result['model_execution_unknown'])
        self.assertTrue(result['response_complete'])
        self.assertEqual(result['http_status'],200)
        self.assertEqual(result['failure_class'],'semantic_child_failed')

    def test_cleanup_broken_pipe_keeps_post_GO_uncertainty(self):
        script="""import sys,json,time
json.loads(sys.stdin.readline())
print(json.dumps({'event':'ready_for_model','frame':{'expires_monotonic':time.monotonic()+4}}),flush=True)
assert sys.stdin.readline().strip()=='go'
time.sleep(.05)
"""
        result=self.process_runner(script,threading.Event(),lambda:True,cleanup_failure=True)
        self.assertTrue(result['model_execution_unknown'])
        self.assertFalse(result['response_complete'])


if __name__ == '__main__':
    unittest.main()
