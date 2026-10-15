"""Causal finite harness regressions; synthetic models/observations, no devices."""
import ast
from collections import Counter
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from reachy_companion.autonomous.gateway import Gateway,ModelBackend,ExecutionUnknown

ROOT=Path(__file__).resolve().parents[1]
DEPLOY=ROOT/'deploy/autonomous'
OLD='25945509504ae1fd8e8eaf5fed44d34b607ceac8'
with patch.object(sys,'path',[str(DEPLOY),*sys.path]):
    spec=importlib.util.spec_from_file_location('live_smoke_fixture',DEPLOY/'live_smoke.py')
    smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)
    import smoke_contract as contract
    import smoke_execution as execution


def fixture(root):
    args=SimpleNamespace(server=root/'server',weights=root/'fast',main_weights=root/'main',config=root/'config',
        output=root/'receipt.json',audit_file=root/'audit.json',audit_sha256='',skip_main=False,
        threads=8,cache_ram_mb=0,period=2,projection='full',decision_format='object',gpu_layers=0,
        vendor_dir=None,gpu_index=0,gpu_reserve_mib=512)
    cfg=json.loads((ROOT/'config.autonomous.example.json').read_text())
    cfg.update(http_timeout_s=12,period_s=2)
    cfg['models']['fast'].update(id='reachy-shadow-fast-cpu',base_url='http://127.0.0.1:18097',
        completion_backend='llama_native',completion_path='/completion',tokenize_path='/tokenize',temperature=0,
        projection='full',cache_ram_mb=0,decision_format='object',execution_profile='cpu_baseline')
    cfg['models']['main'].update(base_url='http://127.0.0.1:1234/v1',context_tokens=32768,
        admission_context_tokens=4096,tokenizer_backend='lmstudio_sdk',completion_backend='lmstudio_sdk')
    hashes={str(args.server):'a'*64,str(args.weights):contract.FAST_WEIGHT_SHA256,
        str(args.main_weights):'b'*64,'/fixture/mapped-runtime.dll':'c'*64}
    for role,weight in (('fast',contract.FAST_WEIGHT_SHA256),('main','b'*64)):
        model=cfg['models'][role]
        model['audit']=dict(verified=True,device='cpu_pc' if role=='fast' else 'gpu_pc',
            runtime_build='a'*64 if role=='fast' else 'independent-runtime-build',weight_sha256=weight,
            tokenizer_sha256=weight,template_sha256=contract.template_hash(model),runtime_context_tokens=model['context_tokens'])
    main=dict(id=cfg['models']['main']['id'],model_key='fixture-main-key',instance_reference='fixture-existing',
        context_tokens=32768,load_config='frozen-load')
    gpu=dict(uuid='GPU-fixture',total_mib=12000,used_mib=10000,free_mib=2000)
    artifacts=dict(fast_server_sha256='a'*64,fast_weights_sha256=contract.FAST_WEIGHT_SHA256,
        main_weights_sha256='b'*64,runtime_components={},main_runtime_files={'/fixture/mapped-runtime.dll':'c'*64})
    audit=dict(kind='live-smoke-audit-1',audit_id='independently-supplied-fixture',
        collected_at_utc='2026-10-15T10:00:00Z',expires_at_utc='2026-10-15T10:30:00Z',
        config_sha256=contract.fingerprint(cfg),knobs=contract.knobs(args),artifacts=artifacts,
        main_identity=main,main_runtime_build='independent-runtime-build',
        sdk={'fixture':'explicit synthetic SDK audit; separate exact-source tests'},
        fast_placement=dict(device='cpu_pc',offloaded_layers=0,total_layers=None),
        gpu=dict(uuid='GPU-fixture',total_mib=12000,reserve_mib=512,minimum_start_free_mib=896))
    return args,cfg,hashes,main,gpu,artifacts,audit


NOW=1792059000 # 2026-10-15 10:10 UTC


class AuditTests(unittest.TestCase):
    def test_exact_old_block_self_certified_but_new_contract_rejects(self):
        old=subprocess.check_output(['git','show',OLD+':deploy/autonomous/live_smoke.py'],cwd=ROOT).decode()
        tree=ast.parse(old);main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        block=next(n for n in main.body if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple))
        cfg=json.loads((ROOT/'config.autonomous.example.json').read_text())
        self.assertFalse(cfg['models']['main']['audit']['verified'])
        namespace=dict(cfg=cfg,args=SimpleNamespace(weights=Path('fast'),main_weights=Path('main'),server=Path('server')),
            digest=lambda path:'a'*64,hashlib=hashlib,json=json)
        exec(compile(ast.Module(body=[block],type_ignores=[]),'old-smoke-exact-ast','exec'),namespace)
        self.assertTrue(cfg['models']['main']['audit']['verified'])
        self.assertEqual(cfg['models']['main']['audit']['runtime_build'],'LM Studio llama.cpp CUDA 2.55.0')
        with tempfile.TemporaryDirectory() as td:
            args,current,_,identity,gpu,artifacts,audit=fixture(Path(td))
            current['models']['main']['audit']['verified']=False
            audit['config_sha256']=contract.fingerprint(current)
            with self.assertRaises(ValueError):contract.verify_audit(audit,current,args,artifacts,identity,gpu,now=NOW)

    def test_fresh_frozen_identity_matches_and_every_independent_axis_change_rejects(self):
        with tempfile.TemporaryDirectory() as td:
            args,cfg,_,main,gpu,artifacts,audit=fixture(Path(td))
            contract.verify_audit(audit,cfg,args,artifacts,main,gpu,now=NOW)
            mutations=[lambda a:a.update(expires_at_utc='2026-10-15T10:01:00Z'),
                lambda a:a.update(config_sha256='f'*64),lambda a:a['knobs'].update(threads=4),
                lambda a:a['main_identity'].update(instance_reference='new-owner'),
                lambda a:a['main_identity'].update(load_config='new-load'),
                lambda a:a['main_identity'].update(context_tokens=4096),
                lambda a:a.update(main_runtime_build='different-runtime'),
                lambda a:a['artifacts']['main_runtime_files'].update({'/fixture/mapped-runtime.dll':'f'*64}),
                lambda a:a['gpu'].update(uuid='GPU-foreign'),lambda a:a['gpu'].update(minimum_start_free_mib=2100)]
            for index,mutate in enumerate(mutations):
                with self.subTest(index=index):
                    candidate=copy.deepcopy(audit);mutate(candidate)
                    with self.assertRaises(ValueError):contract.verify_audit(candidate,cfg,args,artifacts,main,gpu,now=NOW)
            wrong=copy.deepcopy(artifacts);wrong['fast_weights_sha256']='9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031'
            wrong_audit=copy.deepcopy(audit);wrong_audit['artifacts']=wrong
            with self.assertRaises(ValueError):contract.verify_audit(wrong_audit,cfg,args,wrong,main,gpu,now=NOW)

    def test_file_hash_is_required_and_old_output_flag_cannot_substitute_for_health(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'audit';path.write_text('{}')
            with self.assertRaises(ValueError):contract.read_audit(path,'0'*64)
            self.assertEqual(contract.read_audit(path,hashlib.sha256(b'{}').hexdigest()),{})
        old=subprocess.check_output(['git','show',OLD+':deploy/autonomous/live_smoke.py'],cwd=ROOT).decode()
        tree=ast.parse(old);main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        final=main.body[-1]
        report=dict(acceptance_passed=True,mixed_passed=True,cadence_passed=True,main_preserved=True,process_reaped=False)
        exec(compile(ast.Module(body=[final],type_ignores=[]),'old-exit-exact-ast','exec'),{'report':report})
        self.assertFalse(contract.accepted(report))

    def test_actual_gateway_held_or_unknown_execution_cannot_pass_terminal_receipt(self):
        release=threading.Event();entered=threading.Event()
        class Backend:
            def generate(self,role,data):entered.set();release.wait(1);return dict(output='fixture')
        gateway=Gateway(Backend());worker=threading.Thread(target=lambda:gateway.generate('main','fixture'));worker.start()
        try:
            self.assertTrue(entered.wait(1));self.assertFalse(contract.idle_health(gateway.health()))
        finally:release.set();worker.join(1)
        self.assertTrue(contract.idle_health(gateway.health()))
        class Unknown:
            def generate(self,*args):raise ExecutionUnknown('remote unknown')
        unknown=Gateway(Unknown())
        with self.assertRaises(ExecutionUnknown):unknown.generate('main','fixture')
        self.assertFalse(contract.idle_health(unknown.health()))
        self.assertEqual(unknown.health()['quarantined'],['main'])


class HarnessTests(unittest.TestCase):
    def run_harness(self,root,*,unverified=False,close_error=False,unreaped=False,placement_change=False,
            main_unknown=False,guard_directory=None,blocked=False,anchor=None):
        args,cfg,hashes,main,gpu,artifacts,audit=fixture(root)
        stable=(guard_directory or root/'account-guard').resolve()
        with patch.object(execution,'guard_root',return_value=stable):
            if anchor is None:anchor=execution.provision_namespace(execution.execution_scopes(cfg,main))
        audit['execution_anchor']=anchor
        if unverified:
            cfg['models']['main']['audit']['verified']=False;audit['config_sha256']=contract.fingerprint(cfg)
        args.audit_file.write_text(json.dumps(audit));args.audit_sha256=hashlib.sha256(args.audit_file.read_bytes()).hexdigest()
        actual_requests=[]
        class Handle:
            def tokenize(self,text):return [1]*10
            def complete(self,prompt,config):
                actual_requests.append((prompt,copy.deepcopy(config)))
                return SimpleNamespace(content='fixture main reply',stats=SimpleNamespace(stop_reason='eosFound',
                    predicted_tokens_count=3,time_to_first_token_sec=.01))
        native=ModelBackend.__new__(ModelBackend);native.config=cfg
        class Backend:
            def generate(self,role,data):
                if role=='main':
                    if main_unknown:raise ExecutionUnknown('actual return without remote terminal evidence')
                    return native.generate_loaded('main',data,Handle())
                output={'a':'wait','why':'fixture'}
                if data['op']['microphone_enabled']:
                    if data['ready']:output={'a':'converse','why':'fixture','commit':data['ready'][0]['alias']}
                    elif data['candidates'] and not data['pending']:
                        output={'a':'think','why':'fixture','start':dict(type='main',input_ref=data['candidates'][0]['alias'])}
                return dict(output=output,usage={})
        class Scheduler:
            def __init__(self,cfg,transport):
                self.transport=transport;self.fast_job=self.main_job=None
                self.state=SimpleNamespace(counts=Counter(task_started=1,simulated_speech=1))
            def run(self,duration,events):
                self.transport.main(SimpleNamespace(prompt=events[0]['text'],attempt_id='attempt'))
                return dict(counts=dict(self.state.counts))
            def close(self):
                if close_error:raise RuntimeError('cleanup fixture')
        process=Mock(pid=123);process.poll.return_value=None
        def wait(**kwargs):
            if unreaped:raise subprocess.TimeoutExpired('owned',5)
            process.poll.return_value=0
        process.wait.side_effect=wait
        monitor=SimpleNamespace(close=lambda:None,minimum_free_mib=1500,samples=5,abort_reason=None,
            thread=SimpleNamespace(is_alive=lambda:False))
        with patch.object(smoke.argparse.ArgumentParser,'parse_args',return_value=args),\
                patch.object(smoke,'load',return_value=cfg),patch.object(smoke,'digest',side_effect=lambda path:hashes[str(path)]),\
                patch.object(smoke,'main_identity',return_value=main) as lookup,patch.object(smoke,'gpu_sample',return_value=gpu),\
                patch.object(smoke,'verify_sdk'),patch.object(execution,'guard_root',return_value=stable),\
                patch.object(smoke,'native_environment',return_value={}),patch.object(smoke,'urlopen'),\
                patch.object(smoke,'placement',return_value=(dict(device='gpu_pc') if placement_change else audit['fast_placement'])),\
                patch.object(smoke,'ModelBackend',return_value=Backend()),patch.object(smoke,'Scheduler',Scheduler),\
                patch.object(smoke,'GPUHeadroom',return_value=monitor),patch.object(smoke.subprocess,'Popen',return_value=process) as spawn,\
                patch.object(contract.time,'time',return_value=NOW),patch('socket.socket'),contextlib.redirect_stdout(io.StringIO()):
            if blocked:
                with self.assertRaises(RuntimeError):smoke.main()
                spawn.assert_not_called();lookup.assert_not_called()
                self.assertEqual(actual_requests,[]);return None,actual_requests
            if unverified:
                with self.assertRaises(ValueError):smoke.main()
                spawn.assert_not_called();return None,actual_requests
            if close_error or unreaped or placement_change or main_unknown:
                with self.assertRaises(SystemExit):smoke.main()
            else:smoke.main()
        return json.loads(args.output.read_text()),actual_requests

    def test_unaudited_config_cannot_spawn_even_with_matching_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as td:self.run_harness(Path(td),unverified=True)

    def test_unknown_run_blocks_new_output_directory_before_popen_or_sdk_post(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);first=root/'first';second=root/'second';first.mkdir();second.mkdir()
            stable=root/'account-guard'
            _,cfg,_,binding,_,_,_=fixture(root)
            with patch.object(execution,'guard_root',return_value=stable.resolve()):
                anchor=execution.provision_namespace(execution.execution_scopes(cfg,binding))
            report,_=self.run_harness(first,main_unknown=True,guard_directory=stable,anchor=anchor)
            self.assertTrue(report['execution_guard']['unknown'])
            self.assertFalse(report['execution_guard']['released'])
            self.run_harness(second,guard_directory=stable,blocked=True,anchor=anchor)
            self.assertFalse((second/'receipt.json').exists())

    def test_identical_actual_backend_prompt_and_budget_then_final_health_and_reap(self):
        with tempfile.TemporaryDirectory() as td:
            report,requests=self.run_harness(Path(td))
        self.assertEqual(len(requests),2);self.assertEqual(requests[0],requests[1])
        self.assertTrue(report['accepted']);self.assertTrue(contract.idle_health(report['gateway_final']))
        self.assertTrue(report['process_reaped']);self.assertEqual(report['process_returncode'],0)
        self.assertEqual(report['main']['request_identity'],report['mixed_main_request_identity'])
        old=subprocess.check_output(['git','show',OLD+':deploy/autonomous/live_smoke.py'],cwd=ROOT).decode()
        calls=[n for n in ast.walk(ast.parse(old)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        baseline=next(n.args[1].value for n in calls if n.func.attr=='generate' and len(n.args)>1
            and isinstance(n.args[0],ast.Constant) and n.args[0].value=='main' and isinstance(n.args[1],ast.Constant))
        mixed=next(ast.literal_eval(n.args[1])[0]['text'] for n in calls if n.func.attr=='run')
        self.assertNotEqual(baseline,mixed)

    def test_cleanup_failure_still_reaps_and_missing_reap_or_placement_denies(self):
        for failure in ('close_error','unreaped','placement_change','main_unknown'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as td:
                report,_=self.run_harness(Path(td),**{failure:True})
                self.assertFalse(report['accepted'])
                self.assertEqual(report['process_reaped'],failure!='unreaped')
                if failure in ('unreaped','main_unknown'):
                    self.assertTrue((Path(td)/'inference-quarantine.local.json').is_file())
                if failure=='main_unknown':
                    self.assertTrue(report['gateway_final']['busy']['main'])
                    self.assertEqual(report['gateway_final']['quarantined'],['main'])


if __name__=='__main__':unittest.main()
