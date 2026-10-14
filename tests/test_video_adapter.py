"""Actual worker synchronization, synthetic RAM frames; no camera/model imports."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from reachy_companion.autonomous.video_adapter import LatestFrameProcessor,decode_packet,FrameOrder
from reachy_companion.autonomous.context import ContextProvider,LatestVideo
from reachy_companion.autonomous.state import State

RAW=b'P6\n1 1\n255\n\x01\x02\x03'
def meta(seq=0,boot='camera',**kw):
    return dict(producer_boot_id=boot,seq=seq,frame_id=f'{boot}-{seq}',lineage_id='one-session',frame_sha256=hashlib.sha256(RAW).hexdigest(),
        source_capture_time_verified=False,source_age_upper_ms=None,**kw)

class ProcessorTests(unittest.TestCase):
    def test_blocked_actual_slot_latest_pending_replaces_middle_and_close_is_truthful(self):
        entered=threading.Event();release=threading.Event();published=threading.Event();calls=[];out=[]
        def process(raw,digest):
            calls.append(raw)
            if len(calls)==1:entered.set();release.wait(2)
            return dict(mean_luminance=1)
        def deliver(worker,job,result):worker.commit(job,lambda:(out.append(job[1]['seq']),published.set(),True)[-1])
        worker=LatestFrameProcessor(deliver,process=process)
        try:
            worker.submit(meta(1),RAW,time.monotonic(),'scope');self.assertTrue(entered.wait(1))
            worker.submit(meta(2),RAW,time.monotonic(),'scope');worker.submit(meta(3),RAW,time.monotonic(),'scope')
            self.assertTrue(worker.status()['execution_busy']);self.assertEqual(worker.status()['pending_raw_frames'],1)
            release.set();self.assertTrue(published.wait(1));self.assertEqual(out,[3]);self.assertEqual(len(calls),2)
        finally:release.set();worker.close()
        entered.clear();release.clear();calls.clear();worker=LatestFrameProcessor(deliver,process=process)
        worker.submit(meta(4),RAW,time.monotonic(),'scope');self.assertTrue(entered.wait(1))
        self.assertFalse(worker.close());self.assertTrue(worker.status()['execution_busy']);self.assertEqual(worker.status()['pending_raw_frames'],0)
        release.set();worker.thread.join(1);self.assertFalse(worker.status()['execution_busy'])
    def test_processing_age_and_invalidation_drop_late_result_without_freeing_slot(self):
        now=[0.];entered=threading.Event();release=threading.Event();out=[]
        def process(*args):entered.set();release.wait(1);return dict(mean_luminance=1)
        worker=LatestFrameProcessor(lambda *args:out.append(args),process=process,clock=lambda:now[0])
        try:
            worker.submit(meta(),RAW,0,'old');self.assertTrue(entered.wait(1));worker.invalidate()
            self.assertTrue(worker.status()['execution_busy']);now[0]=3;release.set();worker.thread.join(.05)
            self.assertFalse(out);self.assertGreaterEqual(worker.expired,1)
        finally:release.set();worker.close()
    def test_pending_ttl_purge_does_not_release_running_buffer_or_replay_old_result(self):
        now=[0.];entered=threading.Event();release=threading.Event();out=[]
        def process(*args):entered.set();release.wait(1);return dict(mean_luminance=1)
        worker=LatestFrameProcessor(lambda *args:out.append(args),process=process,clock=lambda:now[0])
        try:
            worker.submit(meta(1),RAW,0,'scope');self.assertTrue(entered.wait(1));worker.submit(meta(2),RAW,0,'scope')
            now[0]=3;worker.expire_pending()
            self.assertTrue(worker.status()['execution_busy']);self.assertEqual(worker.status()['pending_raw_frames'],0)
        finally:release.set();worker.close()
        self.assertFalse(out)
    def test_frame_order_survives_clear_restart_and_exhaustion_without_ABA(self):
        cache=LatestVideo();cache.publish(meta(3),dict(mean_luminance=1),0);cache.clear()
        self.assertFalse(cache.publish(meta(3),dict(mean_luminance=1),1))
        cache.publish(meta(0,'new'),dict(mean_luminance=1),1);cache.clear()
        with self.assertRaises(ValueError):cache.publish(meta(999),dict(mean_luminance=1),2)
        order=FrameOrder()
        for n in range(129):order.accept(meta(0,str(n)))
        with self.assertRaises(ValueError):order.accept(meta(0,'overflow'))
        with self.assertRaises(ValueError):order.accept(meta(1,'0'))
    def test_age_lower_accumulates_processing_and_producer_residence_but_upper_stays_unknown(self):
        cache=LatestVideo();cache.publish(meta(source_age_lower_ms=450),dict(mean_luminance=1),10)
        view=cache.snapshot(10.6);self.assertGreaterEqual(view['age_bounds_ms']['lower'],1049)
        self.assertIsNone(view['age_bounds_ms']['upper']);self.assertEqual(view['state'],'unknown')
        self.assertEqual(cache.snapshot(12)['state'],'stale')
        state=State();state.update_context(dict(memory=dict(store_id='fixture-store',revision=0,items=[]),sensors=[view]),10.6)
        state.ingest(dict(type='utterance',text='fixture actual mandatory question'),10.6)
        ref=next(iter(state.candidates));task=state.apply(dict(a='think',why='start',start=dict(type='main',input_ref=ref)),state.bind(10.6,10),10.6)
        self.assertEqual(task.prompt['observations'],[]);self.assertEqual(state.snapshot(10.6)['sensors'][0]['summary'],'')
    def test_versioned_packet_only_retains_selected_provenance_and_rejects_fake_capture_upper(self):
        m=meta(scope=dict(hub_boot_id='hub',compute_boot_id='pc',operator_epoch=0),admission_id='new',video_protocol=2,audio_initialised=False)
        def packet(metadata):
            header=json.dumps(metadata).encode();return struct.pack('!I',len(header))+header+RAW
        selected,raw=decode_packet(packet({**m,'secret':'must-not-retain'}));self.assertNotIn('secret',selected);self.assertEqual(raw,RAW)
        for wrong in ({**m,'source_capture_time_verified':True},{**m,'source_age_upper_ms':100},{**m,'admission_id':None},{**m,'video_protocol':1}):
            with self.assertRaises(ValueError):decode_packet(packet(wrong))

class ScopeTests(unittest.TestCase):
    def test_privacy_ABA_epoch_and_expired_owner_drop_real_blocked_worker_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            provider=ContextProvider(dict(memory_path=str(Path(directory)/'store'),namespaces=['fixture']),'pc')
            entered=threading.Event();release=threading.Event()
            def process(*args):entered.set();release.wait(2);return dict(mean_luminance=1)
            provider.video_worker=LatestFrameProcessor(provider.video_completed,process=process)
            try:
                provider.snapshot('',False,'hub',0);scope=dict(provider.scope);ticket=(scope,provider.video_generation,provider.video_admission)
                old=meta(scope=scope,admission_id=provider.video_admission)
                self.assertTrue(provider.admit_video(old,RAW,time.monotonic(),ticket));self.assertTrue(entered.wait(1))
                provider.snapshot('',True,'hub',0);provider.snapshot('',False,'hub',0)
                self.assertFalse(provider.admit_video({**old,'seq':1},RAW,time.monotonic(),ticket))
                self.assertTrue(provider.video_worker.status()['execution_busy']);release.set()
                provider.video_worker.thread.join(.05);self.assertIsNone(provider.video.current)
                provider.snapshot('',False,'hub',1)
                self.assertFalse(provider.admit_video({**old,'seq':2},RAW,time.monotonic(),ticket))
                with provider.policy_lock:provider.owner_deadline=0
                self.assertFalse(provider.admit_video({**old,'seq':3},RAW,time.monotonic(),ticket))
            finally:release.set();provider.close()
    def test_producer_generation_blocks_privacy_ABA_and_reports_only_RAM_residence(self):
        source=Path(__file__).resolve().parents[1]/'deploy/autonomous/video_server.py'
        spec=importlib.util.spec_from_file_location('video_source_boundary',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'token').write_text('x'*32);(root/'config.local.json').write_text(json.dumps(dict(paths=dict(token_file='token'),network=dict(agent_url='http://127.0.0.1:8770'))))
            policy=root/'policy';policy.write_text('{"camera_enabled":true,"privacy_all":false}')
            producer=module.Producer(SimpleNamespace(production_root=root,policy_file=policy));scope=dict(hub_boot_id='hub',compute_boot_id='pc',operator_epoch=0)
            with patch.object(module.time,'monotonic',return_value=10):
                producer.set_policy(dict(scope=scope,seq=0,privacy_all=False,admission_id='a'));generation=producer.generation
                producer.set_policy(dict(scope=scope,seq=1,privacy_all=True,admission_id='b'))
                producer.set_policy(dict(scope=scope,seq=2,privacy_all=False,admission_id='c'))
                self.assertFalse(producer.publish_frame(meta(),RAW,scope,generation,10))
                self.assertTrue(producer.publish_frame(meta(),RAW,scope,producer.generation,9.6))
                packet=producer.packet();n=struct.unpack('!I',packet[:4])[0];metadata=json.loads(packet[4:4+n])
                self.assertGreaterEqual(metadata['source_age_lower_ms'],400);self.assertFalse(metadata['source_capture_time_verified'])
                with self.assertRaises(ValueError):producer.set_policy(dict(scope=scope,seq=99,privacy_all=True,admission_id='a'))
            with patch.object(module.time,'monotonic',return_value=13):self.assertIsNone(producer.packet());self.assertIsNone(producer.latest)

if __name__=='__main__':unittest.main()
