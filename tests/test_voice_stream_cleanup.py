"""Actual Pipeline.stream with synthetic audio/model functions, no inference."""
import concurrent.futures
import sys
import threading
import types
import unittest
from unittest.mock import patch


class StreamCleanupTests(unittest.TestCase):
    def pipeline_class(self):
        piper=types.ModuleType('piper');piper.PiperVoice=piper.SynthesisConfig=object
        vosk=types.ModuleType('vosk');vosk.Model=vosk.KaldiRecognizer=vosk.SetLogLevel=object
        with patch.dict(sys.modules,{'piper':piper,'vosk':vosk}):
            from reachy_companion.voice import Pipeline
        return Pipeline

    def pipeline(self):
        Pipeline=self.pipeline_class()
        p=Pipeline.__new__(Pipeline);p.lock=threading.Lock();p.phase='idle'
        p.config={'conversation':{'interaction':{}}}
        p.prepare=lambda *args:({'reply':'fixture'},'fixture',None)
        p.audio_events=lambda *args,**kwargs:iter(())
        p.completed=lambda *args:{'fixture':True}
        return p

    def test_done_is_received_after_idle_and_lock_release_before_exhaustion(self):
        p=self.pipeline();iterator=p.stream({},'/say')
        self.addCleanup(iterator.close)
        self.assertEqual(next(iterator)['type'],'reply');self.assertTrue(p.lock.locked())
        self.assertEqual(next(iterator),dict(type='done',ok=True,fixture=True))
        self.assertEqual(p.phase,'idle');self.assertFalse(p.lock.locked())
        # Client may stop reading immediately after done; no extra next needed.
        second=p.stream({},'/say');self.assertEqual(next(second)['type'],'reply');second.close()
        with self.assertRaises(StopIteration):next(iterator)

    def test_done_waits_for_actual_acknowledgement_executor_worker_exit(self):
        p=self.pipeline();release_answer=threading.Event();release_worker=threading.Event()
        worker_held=threading.Event();executors=[]
        original=concurrent.futures.ThreadPoolExecutor
        class Executor(original):
            def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);executors.append(self)
            def submit(self,*args,**kwargs):
                future=super().submit(*args,**kwargs)
                def hold(_):worker_held.set();release_worker.wait(2)
                future.add_done_callback(hold)
                return future
        p.config={'conversation':{'session':'s','interaction':{'acknowledgements':{
            'enabled':True,'delay_seconds':0,'phrases':{'other':'intro'}}}},
            'limits':{'max_text_chars':128,'max_session_chars':32}}
        p.check_robot=lambda:None
        p.classify=lambda text:dict(action='answer',intent='other',emotion='neutral')
        p.answer=lambda *args:(release_answer.wait(2) and ('answer',None))
        iterator=p.stream({'text':'fixture'},'/text')
        reader=original(1)
        try:
            with patch('concurrent.futures.ThreadPoolExecutor',Executor):
                self.assertTrue(next(iterator)['acknowledgement'])
                release_answer.set();self.assertTrue(worker_held.wait(1))
                self.assertEqual(next(iterator)['type'],'reply')
                terminal=reader.submit(next,iterator)
                with self.assertRaises(concurrent.futures.TimeoutError):terminal.result(timeout=.05)
                self.assertTrue(p.lock.locked());self.assertEqual(p.phase,'speaking')
                self.assertTrue(any(t.is_alive() for t in executors[0]._threads))
                release_worker.set()
                self.assertTrue(terminal.result(timeout=1)['ok'])
                self.assertFalse(p.lock.locked());self.assertEqual(p.phase,'idle')
                self.assertTrue(all(not t.is_alive() for t in executors[0]._threads))
        finally:
            release_answer.set();release_worker.set();reader.shutdown(wait=True);iterator.close()

    def test_audio_failure_or_early_close_never_yields_success_and_closes_audio(self):
        for fail in (False,True):
            with self.subTest(fail=fail):
                p=self.pipeline();closed=threading.Event()
                def audio(*args,**kwargs):
                    try:
                        yield {'type':'audio'}
                        if fail:raise RuntimeError('audio fixture')
                    finally:closed.set()
                p.audio_events=audio;iterator=p.stream({},'/say')
                self.assertEqual(next(iterator)['type'],'reply')
                self.assertEqual(next(iterator)['type'],'audio')
                if fail:
                    with self.assertRaises(RuntimeError):next(iterator)
                else:iterator.close()
                self.assertTrue(closed.is_set());self.assertFalse(p.lock.locked());self.assertEqual(p.phase,'idle')

    def test_cleanup_failure_releases_lock_without_success(self):
        p=self.pipeline();p.config={'conversation':{'session':'s','interaction':{'acknowledgements':{
            'enabled':True,'delay_seconds':1}}},'limits':{'max_text_chars':128,'max_session_chars':32}}
        p.check_robot=lambda:None;p.classify=lambda text:dict(action='answer')
        p.answer=lambda *args:('answer',None)
        real=concurrent.futures.ThreadPoolExecutor
        class Failing(real):
            def shutdown(self,*args,**kwargs):super().shutdown(*args,**kwargs);raise RuntimeError('cleanup fixture')
        with patch('concurrent.futures.ThreadPoolExecutor',Failing):
            iterator=p.stream({'text':'fixture'},'/text')
            self.assertEqual(next(iterator)['type'],'reply')
            with self.assertRaises(RuntimeError):next(iterator)
        self.assertFalse(p.lock.locked());self.assertEqual(p.phase,'idle')


if __name__=='__main__':unittest.main()
