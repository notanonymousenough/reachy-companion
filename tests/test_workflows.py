"""Finite broker races, durable idempotency and optional scheduler integration."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta

from reachy_companion.autonomous.config import load
from reachy_companion.autonomous.runtime import ReplayGateway, Scheduler

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('workflow_broker',ROOT/'deploy/workflows/broker.py')
broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)


def body(task='t1',attempt='a1',value='synthetic',ttl=5):
    deadline=datetime.now(timezone.utc)+timedelta(seconds=ttl)
    return dict(capability='workflow.synthetic_echo',task_id=task,attempt_id=attempt,
                deadline_at=deadline.isoformat().replace('+00:00','Z'),arguments={'value':value})


def echo(value):
    return dict(task_id=value['task_id'],attempt_id=value['attempt_id'],value=value['arguments']['value'])


def wait(store,key,expected,timeout=1):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        value=store.status(key)
        if value['status']==expected:return value
        time.sleep(.002)
    raise AssertionError((key,expected,store.status(key)))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'tasks.sqlite'
    def store(self, *args, **kwargs):
        value=broker.Store(*args, **kwargs)
        self.addCleanup(value.close)
        return value
    def test_duplicate_and_conflict_are_durable_and_do_not_reinvoke(self):
        calls=[]
        def invoke(value):calls.append(value);return echo(value)
        store=self.store(self.path,invoke);request=body();store.submit(request)
        wait(store,'t1/a1','succeeded')
        for i in range(30):store.submit(request)
        self.assertEqual(len(calls),1)
        with self.assertRaises(FileExistsError):store.submit({**request,'arguments':{'value':'different'}})
        store.close()
        restored=self.store(self.path,invoke);restored.submit(request)
        self.assertEqual(len(calls),1)
        restored.close()
    def test_cancel_and_late_result_never_return_output(self):
        for state in ('cancelled','expired'):
            with self.subTest(state=state):
                release=threading.Event();finished=threading.Event()
                def invoke(value):
                    release.wait(1);finished.set();return echo(value)
                store=self.store(':memory:',invoke)
                try:
                    store.submit(body(ttl=.03 if state=='expired' else 5))
                    wait(store,'t1/a1','running')
                    if state=='cancelled':store.cancel('t1/a1')
                    else:time.sleep(.04)
                    release.set();finished.wait(1)
                    value=wait(store,'t1/a1',state)
                    self.assertIsNone(value['result'])
                finally:release.set()
    def test_outage_quarantine_survives_restart_without_replay(self):
        def fail(value):raise TimeoutError('synthetic outage')
        store=self.store(self.path,fail);store.submit(body())
        wait(store,'t1/a1','execution_unknown')
        self.assertTrue(store.quarantined)
        with self.assertRaises(BlockingIOError):store.submit(body(task='t2'))
        store.close()
        restored=self.store(self.path,echo)
        self.assertTrue(restored.quarantined)
        with self.assertRaises(BlockingIOError):restored.submit(body(task='t2'))
        restored.close()
    def test_capacity_preserves_tombstones_instead_of_breaking_dedupe(self):
        store=self.store(':memory:',echo,capacity=1);request=body();store.submit(request)
        wait(store,'t1/a1','succeeded')
        with self.assertRaises(BlockingIOError):store.submit(body(task='t2'))
        self.assertEqual(store.submit(request)['status'],'succeeded')
    def test_no_workflow_url_shell_extra_arguments_or_expired_task_from_model(self):
        store=self.store(':memory:',echo)
        for request in (body(value='x'*257),{**body(),'capability':'workflow.arbitrary'},
                        {**body(),'workflow_url':'http://untrusted'},{**body(),'arguments':{'value':'ok','shell':'sh'}},body(ttl=-1)):
            with self.assertRaises(ValueError):store.submit(request)
    def test_pending_cap_and_cancel_keep_running_execution_accounted(self):
        release=threading.Event();calls=[]
        def invoke(value):calls.append(value);release.wait(1);return echo(value)
        store=self.store(':memory:',invoke,pending_cap=1)
        try:
            store.submit(body());wait(store,'t1/a1','running');store.cancel('t1/a1')
            self.assertEqual(store.active_executions,1)
            store.submit(body(task='t2'))
            time.sleep(.01)
            self.assertEqual(len(calls),1) # cancel did not release actual permit
            release.set();wait(store,'t2/a1','succeeded')
        finally:release.set()
    def test_note_opt_in_transform_dedupe_and_restart(self):
        request={**body(value='  public\t arithmetic\n result: 6  '),'capability':'workflow.normalize_note'}
        default=self.store(':memory:',echo)
        with self.assertRaises(ValueError):default.submit(request)
        calls=[]
        def invoke(value):calls.append(value);return broker.expected_result(value)
        store=self.store(self.path,invoke,normalize_notes=True);store.submit(request)
        result=wait(store,'t1/a1','succeeded')
        self.assertEqual(result['result']['value'],'public arithmetic result: 6')
        store.close();restored=self.store(self.path,invoke,normalize_notes=True)
        self.assertEqual(restored.submit(request),result);self.assertEqual(len(calls),1)
        with self.assertRaises(FileExistsError):restored.submit({**request,'capability':'workflow.synthetic_echo'})
        restored.close()

    def test_note_empty_extra_arguments_and_wrong_transform_are_rejected(self):
        store=self.store(':memory:',echo,normalize_notes=True)
        request={**body(),'capability':'workflow.normalize_note'}
        for arguments in ({'value':' \n\t\r '},{'value':'ok','url':'http://untrusted'},{'value':'x'*257}):
            with self.assertRaises(ValueError):store.submit({**request,'arguments':arguments})
        store.submit({**request,'arguments':{'value':'  changed  '}})
        wait(store,'t1/a1','execution_unknown');self.assertTrue(store.quarantined)

    def test_note_expressions_are_data_and_ascii_whitespace_preserves_unicode(self):
        store=self.store(':memory:',broker.expected_result,normalize_notes=True)
        request={**body(value='  {{$env.SECRET}}\t\u00a0 public  '),'capability':'workflow.normalize_note'}
        store.submit(request);result=wait(store,'t1/a1','succeeded')
        self.assertEqual(result['result']['value'],'{{$env.SECRET}} \u00a0 public')

    def test_optional_workflow_uses_typed_candidate_and_fresh_commit(self):
        cfg=load(ROOT/'config.autonomous.example.json');cfg.update(period_s=.005)
        cfg['workflows']['enabled']=True
        scheduler=Scheduler(cfg,ReplayGateway(.01))
        scheduler.ingest(dict(type='workflow',value='synthetic echo'))
        end=time.monotonic()+1
        while time.monotonic()<end and scheduler.state.counts['simulated_speech']==0:
            scheduler.advance();time.sleep(.002)
        self.assertEqual(scheduler.state.counts['task_started'],1)
        task=next(iter(scheduler.state.tasks.values()));self.assertEqual(task.kind,'research')
        self.assertEqual(scheduler.state.counts['simulated_speech'],1)
    def test_disabled_workflow_and_outage_do_not_stop_fast_ticks(self):
        cfg=load(ROOT/'config.autonomous.example.json');cfg.update(period_s=.005)
        scheduler=Scheduler(cfg,ReplayGateway());scheduler.ingest(dict(type='workflow',value='synthetic'))
        self.assertFalse(scheduler.state.candidates)
        cfg['workflows']['enabled']=True
        class Unavailable(ReplayGateway):
            def main(self,task):raise ConnectionError('synthetic outage')
        scheduler=Scheduler(cfg,Unavailable());scheduler.ingest(dict(type='workflow',value='synthetic'))
        end=time.monotonic()+1
        while time.monotonic()<end and (scheduler.state.counts['task_failed']==0 or scheduler.gateway.fast_calls<=5):
            scheduler.advance();time.sleep(.002)
        self.assertEqual(scheduler.state.counts['task_failed'],1)
        self.assertGreater(scheduler.gateway.fast_calls,5)


if __name__=='__main__':unittest.main()
