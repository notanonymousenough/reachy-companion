"""Actual SDK work remains owned after caller timeout or unknown completion."""
import threading
import unittest
from reachy_companion.spoken_reply_sdk import PredictionSlot


class SlotTests(unittest.TestCase):
    def test_timeout_does_not_free_real_slot_then_late_terminal_releases(self):
        slot=PredictionSlot();entered=threading.Event();release=threading.Event()
        def operation(started,terminal):
            started();entered.set();release.wait();terminal();return 'late response'
        try:
            with self.assertRaises(TimeoutError):slot.execute(operation,.02)
            self.assertTrue(entered.is_set())
            self.assertEqual(slot.status(),dict(active=True,quarantined=False))
            with self.assertRaises(RuntimeError):slot.execute(lambda *args:'replacement',.1)
        finally:release.set()
        with slot.condition:self.assertTrue(slot.condition.wait_for(lambda:not slot.active,1))
        self.assertEqual(slot.execute(lambda started,terminal:'new',.1),'new')

    def test_thread_start_delay_does_not_reset_original_caller_deadline(self):
        import time
        from unittest.mock import patch
        original=threading.Thread.start
        def delayed(worker):original(worker);time.sleep(.03)
        slot=PredictionSlot()
        with patch.object(threading.Thread,'start',delayed):
            with self.assertRaises(TimeoutError):slot.execute(lambda started,terminal:'late',.01)
        slot.available() # real worker did finish; caller still cannot accept late text

    def test_transport_failure_after_start_quarantines_without_timed_reclaim(self):
        slot=PredictionSlot()
        def operation(started,terminal):started();raise TimeoutError('transport')
        with self.assertRaises(RuntimeError):slot.execute(operation,.1)
        self.assertEqual(slot.status(),dict(active=False,quarantined=True))
        with self.assertRaises(RuntimeError):slot.execute(lambda *args:'replacement',.1)
        with self.assertRaises(RuntimeError):slot.available()

    def test_pre_submission_failure_does_not_poison_and_terminal_guard_failure_does_not_poison(self):
        slot=PredictionSlot()
        def pre(started,terminal):raise ValueError('expected model absent')
        with self.assertRaises(RuntimeError):slot.execute(pre,.1)
        slot.available()
        def invalid(started,terminal):started();terminal();raise ValueError('invalid final JSON')
        with self.assertRaises(RuntimeError):slot.execute(invalid,.1)
        self.assertEqual(slot.status(),dict(active=False,quarantined=False))

    def test_late_transport_failure_after_timeout_stays_quarantined(self):
        slot=PredictionSlot();release=threading.Event()
        def operation(started,terminal):started();release.wait();raise OSError('disconnected')
        try:
            with self.assertRaises(TimeoutError):slot.execute(operation,.02)
        finally:release.set()
        with slot.condition:self.assertTrue(slot.condition.wait_for(lambda:not slot.active,1))
        self.assertTrue(slot.status()['quarantined'])


# The network/SDK is replaced with a strict reference-aware fake, not a model.
import copy
import json
from pathlib import Path
import sys
import types
from unittest.mock import Mock,patch
from reachy_companion import brains,spoken_reply
from reachy_companion import spoken_reply_sdk as sdk

RULE=dict(schema_version='reply-1',max_chars=80,no_question=True,no_wake=True)


def configuration():
    cfg=json.loads((Path(__file__).resolve().parents[1]/'config.example.json').read_text())
    cfg['llm']['reply_schema']=dict(mode=sdk.MODE,enabled=True,verified=True,instance_spec_verified=True,
        model=cfg['llm']['model'],model_key='weight-key',instance_reference='original-ref',context_tokens=32768,
        base_url=cfg['network']['llm_base_url'],sdk_version='1.5.0',sdk_sources=sdk.SDK_SOURCES,
        sdk_tree_sha256=sdk.SDK_TREE,environment_sha256='a'*64,template_sha256=sdk.template_binding(cfg),
        constraints_sha256=sdk.digest(RULE),schema_sha256=sdk.digest(spoken_reply.response_format(RULE)['json_schema']['schema']),
        runtime_build='audited-runtime',max_tokens=96,timeout_s=1)
    return cfg


class SdkBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.cfg=configuration();self.slot=sdk.PredictionSlot()
        self.addCleanup(patch.stopall)
        patch.object(sdk,'SLOT',self.slot).start()
        patch.object(brains,'MODEL_EXECUTION',brains.ModelExecutionOwnership()).start()
        self.environment={key:self.cfg['llm']['reply_schema'][key] for key in ('sdk_version','sdk_sources','sdk_tree_sha256','environment_sha256')}
        self.audit=patch.object(sdk,'environment_audit',return_value=self.environment).start()
        self.client=Mock();self.client.__enter__=Mock(return_value=self.client);self.client.__exit__=Mock(return_value=False)
        self.lms=types.ModuleType('lmstudio');self.lms.Client=Mock(return_value=self.client)
        patch.dict(sys.modules,{'lmstudio':self.lms}).start()
        self.info=types.SimpleNamespace(identifier=self.cfg['llm']['model'],instance_reference='original-ref',model_key='weight-key',context_length=32768)
        self.client.llm.get_model_info.return_value=self.info
        self.result=types.SimpleNamespace(content='{"reply":"Шесть подходит."}',stats=types.SimpleNamespace(stop_reason='eosFound'),model_info=types.SimpleNamespace(model_key='weight-key'))
        self.client.llm._complete_stream.return_value.wait_for_result.return_value=self.result

    def test_exact_reference_survives_symbolic_identifier_rebinding(self):
        spec=dict(type='instanceReference',instanceReference='original-ref')
        def complete(actual,prompt,**kwargs):
            # A symbolic alias has changed after the admission read; exact RPC
            # still addresses the original reference, or the server must reject.
            self.info.instance_reference='new-ref'
            self.assertEqual(actual,spec)
            return types.SimpleNamespace(wait_for_result=lambda:self.result)
        self.client.llm._complete_stream.side_effect=complete
        messages=[dict(role='user',content='Шесть')]
        with patch('reachy_companion.brains.build_opener') as http:
            self.assertEqual(brains.answer(self.cfg,messages,'s',reply_constraints=RULE),'Шесть подходит.')
            http.assert_not_called()
        self.client.llm.get_model_info.assert_called_once_with(spec)
        args,kwargs=self.client.llm._complete_stream.call_args
        self.assertEqual(args[1],brains.raw_prompt(self.cfg,messages))
        self.assertEqual(kwargs['config']['structured']['jsonSchema'],spoken_reply.response_format(RULE)['json_schema']['schema'])
        self.assertEqual(kwargs['config']['maxTokens'],96)
        self.client.llm.model.assert_not_called();self.client.llm.load_new_instance.assert_not_called()

    def test_missing_reference_never_submits_or_autoloads(self):
        self.client.llm.get_model_info.side_effect=RuntimeError('absent')
        with self.assertRaises(RuntimeError):sdk.predict(self.cfg,[],RULE)
        self.client.llm._complete_stream.assert_not_called()
        self.client.llm.model.assert_not_called();self.client.llm.load_new_instance.assert_not_called()
        self.assertEqual(self.slot.status(),dict(active=False,quarantined=False))

    def test_changed_sources_environment_template_schema_or_instance_proof_denied(self):
        for field,value in [('sdk_version','1.6.0'),('sdk_tree_sha256','b'*64),('template_sha256','b'*64),
                            ('schema_sha256','b'*64),('instance_spec_verified',False)]:
            cfg=copy.deepcopy(self.cfg);cfg['llm']['reply_schema'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):sdk.predict(cfg,[],RULE)
        with patch.object(sdk,'environment_audit',return_value={**self.environment,'environment_sha256':'b'*64}):
            with self.assertRaises(ValueError):sdk.predict(self.cfg,[],RULE)
        self.lms.Client.assert_not_called()
        with self.assertRaises(ValueError):spoken_reply.endpoint(self.cfg)

    def test_transport_error_quarantines_and_blocks_legacy_fallback(self):
        self.client.llm._complete_stream.return_value.wait_for_result.side_effect=TimeoutError('transport')
        with self.assertRaises(RuntimeError):brains.answer(self.cfg,[],'s',reply_constraints=RULE)
        with patch('reachy_companion.brains.build_opener') as http:
            with self.assertRaises(RuntimeError):brains.answer(self.cfg,[],'s')
            http.assert_not_called()
        self.assertTrue(self.slot.status()['quarantined'])

    def test_actual_timeout_blocks_same_default_backend_until_real_terminal(self):
        import io
        entered=threading.Event();release=threading.Event()
        def wait():
            entered.set();release.wait();return self.result
        self.client.llm._complete_stream.return_value.wait_for_result.side_effect=wait
        self.cfg['llm']['reply_schema']['timeout_s']=.02
        try:
            with self.assertRaises(TimeoutError):brains.answer(self.cfg,[],'s',reply_constraints=RULE)
            self.assertTrue(entered.is_set());self.assertTrue(self.slot.status()['active'])
            with patch('reachy_companion.brains.build_opener') as http:
                with self.assertRaises(RuntimeError):brains.answer(self.cfg,[],'s')
                http.assert_not_called()
                from urllib.request import Request
                with self.assertRaises(RuntimeError):brains.http_model_choice(self.cfg,Request(self.cfg['network']['llm_base_url']))
                http.assert_not_called()
                other=copy.deepcopy(self.cfg);other['network']['llm_base_url']='http://other.example:1234/v1'
                http.return_value.open.return_value=io.BytesIO(json.dumps({'model':self.cfg['llm']['model'],'choices':[{'text':'ok','finish_reason':'stop'}]}).encode())
                self.assertEqual(brains.answer(other,[],'s'),'ok')
        finally:release.set()
        with self.slot.condition:self.assertTrue(self.slot.condition.wait_for(lambda:not self.slot.active,1))
        with patch('reachy_companion.brains.build_opener') as http:
            http.return_value.open.return_value=io.BytesIO(json.dumps({'model':self.cfg['llm']['model'],'choices':[{'text':'fresh','finish_reason':'stop'}]}).encode())
            self.assertEqual(brains.answer(self.cfg,[],'s'),'fresh')
            http.assert_called_once()

    def test_http_active_or_unknown_blocks_direct_sdk_before_client_io(self):
        identity=brains.model_identity(self.cfg)
        with brains.MODEL_EXECUTION.reserve(identity) as execution:
            execution.submitted()
            with self.assertRaises(RuntimeError):sdk.predict(self.cfg,[],RULE)
            self.lms.Client.assert_not_called()
        with self.assertRaises(RuntimeError):sdk.predict(self.cfg,[],RULE)
        self.lms.Client.assert_not_called()
        self.assertFalse(self.slot.status()['quarantined'])

    def test_sdk_active_blocks_http_helper_and_wrong_result_identity_stays_unknown(self):
        from urllib.request import Request
        identity=brains.model_identity(self.cfg)
        with brains.MODEL_EXECUTION.reserve(identity) as execution:
            execution.submitted()
            with patch('reachy_companion.brains.build_opener') as http:
                with self.assertRaises(RuntimeError):brains.http_model_choice(self.cfg,Request(self.cfg['network']['llm_base_url']))
                http.assert_not_called()
            execution.terminal()
        self.result.model_info.model_key='foreign-model'
        with self.assertRaises(RuntimeError):sdk.predict(self.cfg,[],RULE)
        self.assertTrue(self.slot.status()['quarantined'])
        self.assertTrue(brains.MODEL_EXECUTION.status(identity)['unknown'])

    def test_terminal_invalid_json_reasoning_and_length_fail_without_repair(self):
        for content,reason in [('<think>x</think>{"reply":"ok"}','eosFound'),
                ('{"reply":"ok"}','maxPredictedTokensReached'),('', 'eosFound'),
                ('{"reply":"one","reply":"two"}','eosFound')]:
            self.result.content=content;self.result.stats.stop_reason=reason
            with self.subTest(content=content),self.assertRaises(RuntimeError):sdk.predict(self.cfg,[],RULE)
            self.assertFalse(self.slot.status()['quarantined'])


if __name__=='__main__':unittest.main()
