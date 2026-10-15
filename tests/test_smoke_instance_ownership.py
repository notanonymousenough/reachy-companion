"""Exact-reference and real cross-process ownership; no model/device calls."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_live_smoke_contract as fixture
from reachy_companion.autonomous.gateway import ModelBackend,Gateway,BudgetRejected,ExecutionUnknown

with patch.object(sys,'path',[str(fixture.DEPLOY),*sys.path]):
    import frozen_main
    import smoke_execution as execution


class Session:
    def __init__(self,binding):
        self.binding=copy.deepcopy(binding);self.reference=binding['instance_reference']
        self.calls=[];self.info_count=0;self.swap_at=None;self.swap_after_token=False;self.swap_after_complete=False
    def get_model_info(self,spec):
        self.calls.append(('info',dict(spec)));self.info_count+=1
        if self.info_count==self.swap_at:self.reference='B'
        return SimpleNamespace(identifier=self.binding['id'],model_key=self.binding['model_key'],
            instance_reference=self.reference,context_length=self.binding['context_tokens'])
    def _get_load_config(self,spec):self.calls.append(('load',dict(spec)));return self.binding['load_config']
    def _tokenize_text(self,spec,text):
        self.calls.append(('tokenize',dict(spec)))
        if self.swap_after_token:self.reference='B'
        return [1]*10
    def _complete_stream(self,spec,prompt,config):
        self.calls.append(('complete',dict(spec)))
        if self.swap_after_complete:self.reference='B'
        return SimpleNamespace(wait_for_result=lambda:SimpleNamespace(content='fixture',
            model_info=SimpleNamespace(model_key=self.binding['model_key']),
            stats=SimpleNamespace(stop_reason='eosFound',predicted_tokens_count=1,time_to_first_token_sec=.1)))


class FrozenInstanceTests(unittest.TestCase):
    def environment(self):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup)
        _,cfg,_,binding,_,_,_=fixture.fixture(Path(td.name))
        # get_load_config is represented exactly as the real helper's repr.
        binding['load_config']=repr('frozen-load')
        session=Session(binding);session.binding['load_config']='frozen-load'
        client=SimpleNamespace(llm=session)
        class Client:
            def __init__(self,host):pass
            def __enter__(self):return client
            def __exit__(self,*args):pass
        sdk=SimpleNamespace(Client=Client,set_sync_api_timeout=lambda value:None)
        with patch.dict(sys.modules,{'lmstudio':sdk}),patch.object(frozen_main,'verify_sdk'):
            backend=frozen_main.FrozenModelBackend(cfg,main_binding=binding,sdk_audit={})
        return cfg,binding,session,sdk,backend

    def test_actual_old_loaded_accepts_matching_alias_context_B_new_path_rejects_before_completion(self):
        cfg,binding,session,sdk,backend=self.environment()
        public_calls=[]
        class B:
            def get_info(self):return SimpleNamespace(identifier=binding['id'],context_length=binding['context_tokens'],instance_reference='B')
            def tokenize(self,text):public_calls.append('tokenize-B');return [1]*10
            def complete(self,prompt,config):
                public_calls.append('complete-B')
                return SimpleNamespace(content='B reply',stats=SimpleNamespace(stop_reason='eosFound',predicted_tokens_count=1,time_to_first_token_sec=.1))
        old=ModelBackend.__new__(ModelBackend);old.config=cfg
        client=SimpleNamespace(llm=SimpleNamespace(list_loaded=lambda:[B()]))
        handle=ModelBackend.loaded(cfg['models']['main'],client)
        old.generate_loaded('main',fixture.contract.MAIN_INPUT,handle)
        self.assertEqual(public_calls,['tokenize-B','tokenize-B','complete-B'])
        session.reference='B'
        with patch.dict(sys.modules,{'lmstudio':sdk}):
            with self.assertRaises(BudgetRejected):Gateway(backend).generate('main',fixture.contract.MAIN_INPUT)
        self.assertFalse(any(name in ('tokenize','complete') for name,_ in session.calls))
        with self.assertRaises(BudgetRejected):backend.generate_loaded('main',fixture.contract.MAIN_INPUT,handle)

    def test_A_B_A_before_after_identity_cannot_hide_wrong_actual_handle(self):
        cfg,binding,session,sdk,backend=self.environment()
        with patch.dict(sys.modules,{'lmstudio':sdk}),patch.object(frozen_main,'verify_sdk'):
            before=frozen_main.main_identity(cfg['models']['main'],binding,{})
            session.reference='B'
            with self.assertRaises(BudgetRejected):Gateway(backend).generate('main',fixture.contract.MAIN_INPUT)
            session.reference=binding['instance_reference']
            after=frozen_main.main_identity(cfg['models']['main'],binding,{})
        self.assertEqual(before,after)
        self.assertFalse(any(name=='complete' for name,_ in session.calls))
        self.assertTrue(all(spec==dict(type='instanceReference',instanceReference=binding['instance_reference'])
            for _,spec in session.calls))

    def test_each_count_and_actual_submit_use_the_reference_and_recheck_identity(self):
        for mode in ('healthy','during_tokenize','before_complete','after_complete'):
            with self.subTest(mode=mode):
                _,binding,session,sdk,backend=self.environment()
                session.swap_after_token=mode=='during_tokenize'
                session.swap_at=7 if mode=='before_complete' else None
                session.swap_after_complete=mode=='after_complete'
                gateway=Gateway(backend)
                with patch.dict(sys.modules,{'lmstudio':sdk}):
                    if mode=='healthy':gateway.generate('main',fixture.contract.MAIN_INPUT)
                    else:
                        with self.assertRaises((BudgetRejected,ExecutionUnknown)):
                            gateway.generate('main',fixture.contract.MAIN_INPUT)
                submitted=[name for name,_ in session.calls if name=='complete']
                self.assertEqual(len(submitted),int(mode in ('healthy','after_complete')))
                self.assertTrue(all(spec==dict(type='instanceReference',instanceReference=binding['instance_reference'])
                    for _,spec in session.calls))
                if mode=='after_complete':
                    self.assertTrue(gateway.health()['busy']['main']);self.assertEqual(gateway.health()['quarantined'],['main'])

    def test_sdk_source_environment_and_typed_context_cannot_be_self_verified(self):
        actual=dict(sdk_version='1.5.0',sdk_sources=frozen_main.SDK_SOURCES,
            sdk_tree_sha256=frozen_main.SDK_TREE,environment_sha256='a'*64)
        expected={**actual,'instance_spec_verified':True}
        with patch.object(frozen_main,'environment_audit',return_value=actual):
            frozen_main.verify_sdk(expected)
            for change in ({'instance_spec_verified':False},{'environment_sha256':'b'*64},{'sdk_version':'other'}):
                with self.assertRaises(ValueError):frozen_main.verify_sdk({**expected,**change})
        cfg,binding,session,_,_=self.environment()
        session.binding['context_tokens']=True
        with self.assertRaises(BudgetRejected):frozen_main.FrozenHandle(SimpleNamespace(llm=session),cfg['models']['main'],binding)


class StableOwnershipTests(unittest.TestCase):
    def scopes(self,root):
        _,cfg,_,binding,_,_,_=fixture.fixture(root)
        return execution.execution_scopes(cfg,binding)

    def test_namespace_ignores_output_reload_reference_and_local_endpoint_alias(self):
        with tempfile.TemporaryDirectory() as td:
            _,cfg,_,binding,_,_,_=fixture.fixture(Path(td));before=execution.execution_scopes(cfg,binding)
            binding.update(instance_reference='B',id='new-symbolic-alias')
            cfg['models']['main'].update(id='new-symbolic-alias',base_url='http://localhost:1234/')
            cfg['models']['fast']['id']='new-fast-alias'
            self.assertEqual(before,execution.execution_scopes(cfg,binding))
        before=execution.guard_root()
        with patch.dict(os.environ,HOME='/not-a-new-guard-root',USERPROFILE='/not-a-new-guard-root'):
            self.assertEqual(before,execution.guard_root())

    def test_actual_other_process_held_then_unknown_blocks_new_owner_without_reclaim(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);stable=root/'account-guard';scopes=self.scopes(root)
            code="""import json,os,sys,threading
sys.path.insert(0,sys.argv[1])
import smoke_execution as e
e.guard_root=lambda:e.Path(sys.argv[2])
timer=threading.Timer(5,lambda:os._exit(9));timer.daemon=True;timer.start()
lease=e.ExecutionLease(json.loads(sys.argv[3])).acquire()
print('HELD',flush=True)
sys.stdin.readline()
lease.finish(known=False)
"""
            child=subprocess.Popen([sys.executable,'-c',code,str(fixture.DEPLOY),str(stable),json.dumps(scopes)],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'HELD')
                with patch.object(execution,'guard_root',return_value=stable):
                    with self.assertRaises(RuntimeError):execution.ExecutionLease(scopes).acquire()
                second=root/'new-output-held';second.mkdir()
                fixture.HarnessTests().run_harness(second,guard_directory=stable,blocked=True)
                child.communicate('\n',timeout=2);self.assertEqual(child.returncode,0)
                with patch.object(execution,'guard_root',return_value=stable):
                    with self.assertRaises(RuntimeError):execution.ExecutionLease(scopes).acquire()
                third=root/'new-output-unknown';third.mkdir()
                fixture.HarnessTests().run_harness(third,guard_directory=stable,blocked=True)
                self.assertTrue(all(b'UNKNOWN' in path.read_bytes() for path in stable.glob('*/owner.jsonl')))
            finally:
                if child.poll() is None:child.kill();child.communicate(timeout=2)

    def test_known_release_and_unknown_stickiness_foreign_state_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);stable=root/'account-guard';scopes=self.scopes(root)
            with patch.object(execution,'guard_root',return_value=stable):
                known=execution.ExecutionLease(scopes).acquire();known.finish(known=True)
                self.assertTrue(known.status()['released']);self.assertEqual(list(stable.iterdir()),[])
                unknown=execution.ExecutionLease(scopes).acquire();unknown.finish(known=False);unknown.finish(known=True)
                self.assertTrue(unknown.status()['unknown']);self.assertFalse(unknown.status()['released'])
                with self.assertRaises(RuntimeError):execution.ExecutionLease(scopes).acquire()
            # Separate private namespace: a foreign replacement is never unlinked.
            other=root/'other-account-fixture'
            with patch.object(execution,'guard_root',return_value=other):
                lease=execution.ExecutionLease(scopes).acquire()
                path=lease.slots[0]['path'];path.write_bytes(b'foreign state')
                with self.assertRaises(RuntimeError):lease.finish(known=True)
                self.assertEqual(path.read_bytes(),b'foreign state');self.assertFalse(lease.status()['released'])


if __name__=='__main__':unittest.main()
