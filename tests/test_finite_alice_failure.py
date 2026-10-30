"""Offline regression against the exact historical finite runner plus R0 patch.

Set FINITE_ALICE_BASELINE to its Alice-factual-resume directory. Only three
pinned Python sources and two posthoc sources are read; no SSH/device calls.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    'controller.py': 'c8e05779b4ed8e6903281ca9046cd37ae4b4284bc919d2090907098f60f852c4',
    'controller-driver.py': '2688e1749d13e919af2c11d2c13b804b53ae892d65cf992dee9fa469e4cee239',
    'run.py': '50a59b197b1b955a99d2e4c79fc48bca546827e712b0a778d402969049ffe59a',
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


watch = load('r0_offline_watch', ROOT / 'deploy/autonomous/demo_watch.py')


@unittest.skipUnless(os.environ.get('FINITE_ALICE_BASELINE'), 'Set FINITE_ALICE_BASELINE to the pinned source directory')
class FiniteFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.stage = Path(cls.tmp.name).resolve()
        baseline = Path(os.environ['FINITE_ALICE_BASELINE'])
        for name, pin in PINS.items():
            raw = (baseline / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != pin:
                raise AssertionError('Historical finite source changed: ' + name)
            (cls.stage / name).write_bytes(raw)
        applied = subprocess.run(['patch', '--batch', '-p1', '-d', str(cls.stage)],
            input=(ROOT / 'deploy/patches/finite-alice-controller-failure.patch').read_bytes(),
            capture_output=True, timeout=5)
        if applied.returncode:
            raise AssertionError(applied.stderr.decode() + applied.stdout.decode())
        cls.controller = load('r0_offline_controller', cls.stage / 'controller.py')
        cls.runner = load('r0_offline_runner', cls.stage / 'run.py')
        cls.driver = load('r0_offline_driver', cls.stage / 'controller-driver.py')
        for name in ('posthoc.py', 'posthoc-driver.py'):
            (cls.stage / name).write_bytes((baseline / name).read_bytes())

    def setUp(self):
        self.io = watch.IO.__new__(watch.IO)
        self.io.token = 'DO_NOT_EXPORT_TOKEN'
        self.io.last_endpoint_by_thread = {}
        self.io.operator_begin_by_thread = {threading.get_ident(): 0}
        self.value = dict(agent_boot_id='DO_NOT_EXPORT_BOOT', microphone_epoch=3,
            microphone_enabled=True, microphone_owner_id='DO_NOT_EXPORT_OWNER',
            motion_policy_owner_id='DO_NOT_EXPORT_OWNER', microphone_state_error=None,
            motion_policy=dict(epoch=4, motor_enabled=True, quiet=False, privacy_all=False),
            phase='paused', capture_active=False, listening=False, expression_version=1)

    def guard_failure(self, kind):
        connection = Mock()
        connection.getresponse.return_value = SimpleNamespace(status=503, read=lambda cap:b'{}')
        if kind == 'HTTP':
            with patch.object(watch.http.client, 'HTTPConnection', return_value=connection):
                try:self.io.req(('fixture.invalid', 80), '/status')
                except watch.GuardDenied as error:return error
        elif kind == 'freshness':
            def request(*args):
                self.io.last_endpoint_by_thread[threading.get_ident()] = 'Hub/control/operator'
                return self.value
            with patch.object(self.io, 'req', side_effect=request), \
                    patch.object(watch.time, 'monotonic', side_effect=[0, .31, .32, 1, 1.31, 1.32]), \
                    patch.object(watch.time, 'sleep'):
                try:self.io.op()
                except watch.GuardDenied as error:return error
        elif kind == 'authority':
            changed = dict(self.value, microphone_epoch=5, microphone_owner_id='DO_NOT_EXPORT_NEW_OWNER')
            with patch.object(self.io, 'op', return_value=changed), \
                    patch.object(watch.time, 'monotonic', return_value=.01), \
                    patch.object(watch.http.client, 'HTTPConnection', return_value=connection):
                try:self.io.req(('fixture.invalid', 80), '/pause', {}, self.value)
                except watch.GuardDenied as error:
                    connection.request.assert_not_called()
                    return error
        self.fail('Real watch guard did not deny ' + kind)

    def test_real_guard_codes_elapsed_and_changed_names_are_retained(self):
        for kind, code in (('freshness','operator_GET_expired'), ('HTTP','HTTP_503'), ('authority','authority_changed')):
            with self.subTest(kind=kind):
                error = self.guard_failure(kind)
                result = self.controller.failure_metadata(error, self.io)
                self.assertEqual(result['failure_code'], code)
                self.assertEqual(result['operator_GET_elapsed'], error.elapsed)
                self.assertEqual(result['changed_operator_keys'], error.changed)
                self.assertIsNotNone(result['last_endpoint'])
                self.assertEqual(result['last_endpoint_by_thread'], self.io.last_endpoint_by_thread)
                self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))

    def test_main_persists_primary_and_cleanup_denials_and_always_signals_watch(self):
        for kind in ('freshness', 'HTTP', 'authority'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                error = self.guard_failure(kind)
                cleanup_error = watch.GuardDenied('HTTP_409', ['microphone_epoch'], .02)
                base = Path(directory)
                run = base / ('reachy-companion-demo-' + 'a' * 32)
                run.mkdir(mode=0o700)
                (run / 'watch.py').write_bytes(b'offline watch fixture')
                agent = base / 'agent.py';agent.write_bytes(b'offline Agent fixture')
                plan = dict(mic_epoch=2, policy_epoch=3, agent_pid=10, boot='DO_NOT_EXPORT_BOOT',
                    owner='DO_NOT_EXPORT_OWNER', agent_identity={'pid':10}, initial_turns=1,
                    deadline=time.monotonic()+100)
                (run / 'plan.private.json').write_text(json.dumps(plan))
                (run / 'watch-ready.json').write_text(json.dumps(dict(pid=20,identity={'pid':20})))
                resumed = [False]
                io = SimpleNamespace(last_endpoint_by_thread={})
                def op():
                    io.last_endpoint_by_thread[threading.get_ident()] = 'Hub/control/operator'
                    if resumed[0]:raise error
                    return copy.deepcopy(self.value)
                def req(where, path, *args):
                    io.last_endpoint_by_thread[threading.get_ident()] = 'Agent'+path
                    if path == '/resume':resumed[0]=True;return {}
                    if path == '/say':return dict(ok=True, transcript=self.controller.CUE, reply=self.controller.CUE)
                    return dict(worker=dict(phase='idle', last_turn=dict(transcript=self.controller.CUE,reply=self.controller.CUE)))
                io.op=op;io.req=req
                io.status=lambda:dict(turns=1,interruptions=0,resumable_reply=False)
                def cleanup(*args):
                    io.last_endpoint_by_thread[threading.get_ident()] = 'Agent/microphone'
                    raise cleanup_error
                m = SimpleNamespace(IO=lambda:io, raw=lambda p:p.read_bytes(), need=watch.need,
                    owned=watch.owned, GuardDenied=watch.GuardDenied, AGENT=('fixture.invalid',80),
                    state_unit=lambda name:dict(ActiveState='active',MainPID='20'), proc=lambda pid:{'pid':pid},
                    cleanup=cleanup, save=watch.save)
                spec = SimpleNamespace(loader=Mock())
                def path(value):
                    if value == '/run':return base
                    if value.startswith('/home/pollen/'):return agent
                    return Path(value)
                actual_lstat=Path.lstat
                def lstat(p, *args, **kwargs):
                    if p == run:return SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0,st_mtime=time.time())
                    return actual_lstat(p,*args,**kwargs)
                argv=['controller','--case','sky','--agent-pid','10','--boot-sha256',hashlib.sha256(plan['boot'].encode()).hexdigest(),
                    '--microphone-epoch','2','--policy-epoch','3']
                with patch.object(self.controller,'Path',side_effect=path),patch.object(Path,'lstat',lstat), \
                        patch.object(self.controller,'WATCH',hashlib.sha256((run/'watch.py').read_bytes()).hexdigest()), \
                        patch.object(self.controller,'AGENT_SHA',hashlib.sha256(agent.read_bytes()).hexdigest()), \
                        patch.object(self.controller.importlib.util,'spec_from_file_location',return_value=spec), \
                        patch.object(self.controller.importlib.util,'module_from_spec',return_value=m), \
                        patch.object(self.controller,'speaker_playbacks',return_value=[]), \
                        patch.object(sys,'argv',argv),patch('builtins.print') as printed:
                    self.controller.main()
                result=json.loads(printed.call_args.args[0])
                durable=json.loads((run/'natural-Alice-phase.public.json').read_text())
                self.assertFalse(result['accepted'])
                self.assertEqual(result['stage'],'observe_first_true_reply_playback')
                self.assertEqual(result['failure_reason'],error.code)
                self.assertEqual(result['failure_code'],error.code)
                self.assertEqual(result['operator_GET_elapsed'],error.elapsed)
                self.assertEqual(result['changed_operator_keys'],error.changed)
                self.assertEqual(result['last_endpoint'],'Hub/control/operator')
                self.assertEqual(result['cleanup_failure']['failure_code'],'HTTP_409')
                self.assertEqual(result['cleanup_failure']['last_endpoint'],'Agent/microphone')
                self.assertEqual(result['cleanup_status'],'unknown')
                self.assertTrue(result['controller_done_saved'])
                self.assertEqual(json.loads((run/'controller.done').read_text()),{'done':True})
                self.assertEqual(durable['failure_code'],error.code)
                self.assertIn('elapsed_seconds',durable)
                self.assertNotIn('DO_NOT_EXPORT',json.dumps(result))

    def test_cleanup_budget_cannot_be_swallowed_by_watch_except_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            def cleanup(io, plan):
                try:time.sleep(2)
                except Exception:time.sleep(2)
            m=SimpleNamespace(GuardDenied=watch.GuardDenied,cleanup=cleanup,save=watch.save)
            out={};began=time.monotonic();original_handler=signal.getsignal(signal.SIGALRM)
            self.controller.finish_failed_controller(m,self.io,{},Path(directory),out,cleanup_seconds=.03)
            self.assertLess(time.monotonic()-began,.5)
            self.assertEqual(out['cleanup_status'],'unknown')
            self.assertEqual(out['cleanup_error_class'],'CleanupBudgetExpired')
            self.assertTrue(out['controller_done_saved'])
            self.assertEqual(signal.getsignal(signal.SIGALRM),original_handler)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL)[0],0)

    def test_swallowed_cleanup_post_denial_is_still_recorded_and_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            def request(*args):
                self.io.last_endpoint_by_thread[threading.get_ident()]='Agent/microphone'
                raise watch.GuardDenied('authority_changed',['microphone_owner_id'],.01)
            self.io.req=request
            def cleanup(io, plan):
                try:io.req(None,'/microphone')
                except Exception:pass
                return dict(final_OFF=False)
            out={};m=SimpleNamespace(GuardDenied=watch.GuardDenied,cleanup=cleanup,save=watch.save)
            self.controller.finish_failed_controller(m,self.io,{},Path(directory),out)
            self.assertEqual(out['cleanup_status'],'unverified')
            self.assertEqual(out['cleanup_guard_failures'][0]['failure_code'],'authority_changed')
            self.assertEqual(out['cleanup_guard_failures'][0]['changed_operator_keys'],['microphone_owner_id'])
            self.assertIs(self.io.req,request)

    def test_failed_done_save_does_not_claim_watch_was_signalled(self):
        m=SimpleNamespace(GuardDenied=watch.GuardDenied,cleanup=Mock(side_effect=watch.GuardDenied('HTTP_503')),
            save=Mock(side_effect=OSError('DO_NOT_EXPORT_RAW')))
        out={}
        self.controller.finish_failed_controller(m,self.io,{},Path('/unused'),out)
        self.assertFalse(out['controller_done_saved'])
        self.assertEqual(out['controller_done_error_class'],'OSError')
        self.assertNotIn('DO_NOT_EXPORT',json.dumps(out))

    def test_cleanup_verified_requires_all_evidence_and_volume(self):
        clean=dict(final_OFF=True,admission_retired=True,volume_preserved=True,factory_running_empty=True,
            aplay_absent=True,stock_unknown=False,volume_percent=100)
        for values, status in ((clean,'verified'),(dict(clean,stock_unknown=True),'unverified'),
                (dict(clean,volume_percent=None),'unverified')):
            with tempfile.TemporaryDirectory() as directory:
                m=SimpleNamespace(GuardDenied=watch.GuardDenied,cleanup=lambda *args:values,save=watch.save)
                out={}
                self.controller.finish_failed_controller(m,self.io,{},Path(directory),out)
                self.assertEqual(out['cleanup_status'],status)

    def test_runner_detects_failure_malformed_or_lost_transport_without_waiting_for_hub(self):
        for output in (b'{}',b'not JSON',json.dumps(dict(result=dict(accepted=False,failure_code='HTTP_503'))).encode()):
            child=Mock(returncode=0);child.poll.return_value=0;child.communicate.return_value=(output,b'DO_NOT_EXPORT')
            state=dict(controller=child,ready=dict(run_id='a'*32))
            self.assertTrue(self.runner.controller_failed(state))
            calls=child.communicate.call_count
            self.assertTrue(self.runner.controller_failed(state))
            self.assertEqual(child.communicate.call_count,calls)
        child=Mock();child.poll.return_value=None
        state=dict(controller=child,controller_began=time.monotonic()-73)
        self.assertTrue(self.runner.controller_failed(state))
        self.assertTrue(state['controller_wait_expired'])

    def test_successful_controller_with_correct_run_waits_for_natural_hub_exit(self):
        child=Mock(returncode=0);child.poll.return_value=0
        phase=dict(accepted=True,phase_handshake_accepted=True,run_id='a'*32)
        child.communicate.return_value=(json.dumps(dict(result=phase)).encode(),b'')
        self.assertFalse(self.runner.controller_failed(dict(controller=child,ready=dict(run_id='a'*32))))
        self.assertTrue(self.runner.controller_failed(dict(controller=child,ready=dict(run_id='b'*32))))

    def test_failed_controller_terminates_real_hub_wait_and_requests_finish(self):
        launcher=load('r0_integrated_launcher',ROOT/'scripts/companion_demo.py')
        with tempfile.TemporaryDirectory() as directory:
            hosts=Path(directory)/'known_hosts';hosts.write_text('offline fixture')
            receipt=json.dumps(dict(result=dict(accepted=False,failure_code='operator_GET_expired')))
            child=subprocess.Popen([sys.executable,'-c',
                'import time;time.sleep(.15);print('+repr(receipt)+')'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.addCleanup(lambda:child.poll() is None and child.kill())
            state=dict(controller=child,controller_began=time.monotonic(),ready=dict(run_id='a'*32))
            events=[]
            def robot(config,known_hosts,payload):
                events.append(payload['action'])
                if payload['action']=='arm':return dict(kind='companion-demo-watch',ready=True,run_id='a'*32,
                    plan_sha256='b'*64,owner_sha256=hashlib.sha256(payload['owner'].encode()).hexdigest(),
                    operator_binding=dict(agent_boot_id='offline',microphone_epoch=2,policy_epoch=3))
                return dict(kind='companion-demo-cleanup',cleanup=dict(final_OFF=False))
            began=time.monotonic()
            with patch.object(launcher,'robot_call',side_effect=robot), \
                    patch.object(launcher,'hub_command',return_value=[sys.executable,'-c','import time;time.sleep(30)']), \
                    patch('builtins.print') as printed:
                code=launcher.launch({},hosts,turns=1,seconds=180,stop_requested=lambda:self.runner.controller_failed(state))
            self.assertEqual(code,1)
            self.assertEqual(events,['arm','finish'])
            self.assertLess(time.monotonic()-began,3)
            self.assertEqual(state['phase']['failure_code'],'operator_GET_expired')
            self.assertFalse(json.loads(printed.call_args.args[0])['cleanup_verified'])

    def test_all_revised_pins_match_prepared_source_without_hardware(self):
        self.assertEqual(self.runner.CONTROLLER,hashlib.sha256((self.stage/'controller.py').read_bytes()).hexdigest())
        self.assertEqual(self.driver.INSTALLER_SHA,self.runner.CONTROLLER)
        self.assertEqual(self.driver.INSTALLER,self.stage/'controller.py')
        self.assertEqual(self.runner.DRIVER,hashlib.sha256((self.stage/'controller-driver.py').read_bytes()).hexdigest())
        with patch.object(self.runner,'ROOT',ROOT),patch.object(self.runner.subprocess,'Popen') as process:
            module,state=self.runner.prepare('sky',210,114)
            self.assertTrue(callable(module.launch))
            self.assertEqual(state,{})
            process.assert_not_called()


if __name__ == '__main__':unittest.main()
