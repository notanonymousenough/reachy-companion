"""Mac/watch orchestration checks. No SSH or device process is started."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import stat
import subprocess
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launcher = load('demo_launcher_test', 'scripts/companion_demo.py')
watch = load('demo_watch_test', 'deploy/autonomous/demo_watch.py')


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.events=[]; self.packet=None
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.hosts=Path(self.tmp.name)/'known_hosts';self.hosts.write_text('fixture public key')
        self.binding=dict(agent_boot_id='boot',microphone_epoch=130,policy_epoch=41)
        self.cleaned=dict(final_OFF=True,factory_running_empty=True,aplay_absent=True,volume_percent=50,stock_unknown=False)

    def robot(self,config,hosts,payload):
        self.events.append(payload['action'])
        if payload['action']=='arm':
            self.owner=payload['owner']
            return dict(kind='companion-demo-watch',ready=True,run_id='a'*32,plan_sha256='b'*64,
                owner_sha256=hashlib.sha256(self.owner.encode()).hexdigest(),operator_binding=self.binding)
        self.assertEqual(payload['owner'],self.owner)
        return dict(kind='companion-demo-cleanup',cleanup=self.cleaned)

    def child(self,*args,**kwargs):
        self.events.append('child');self.packet=json.loads(kwargs['input'])
        return SimpleNamespace(returncode=0)

    def run_launch(self,child=None,robot=None):
        with patch.object(launcher,'robot_call',side_effect=robot or self.robot), \
                patch.object(launcher,'hub_command',return_value=['fixture-ssh']), \
                patch.object(launcher.subprocess,'run',side_effect=child or self.child),patch('builtins.print'):
            return launcher.launch({},self.hosts,turns=3,seconds=180)

    def test_verified_watch_before_child_same_owner_and_baseline_then_finish(self):
        self.assertEqual(self.run_launch(),0)
        self.assertEqual(self.events,['arm','child','finish'])
        self.assertEqual(self.packet['owner'],self.owner)
        self.assertEqual(self.packet['operator_binding'],self.binding)

    def test_unverified_watch_never_starts_child(self):
        def bad(*args):
            value=self.robot(*args);value['owner_sha256']='0'*64;return value
        self.assertEqual(self.run_launch(robot=bad),1)
        self.assertEqual(self.events,['arm']);self.assertIsNone(self.packet)

    def test_ctrl_c_and_child_failure_request_owned_finish_without_regrant(self):
        def interrupted(*args,**kwargs):self.events.append('child');raise KeyboardInterrupt
        self.assertEqual(self.run_launch(child=interrupted),130)
        self.assertEqual(self.events,['arm','child','finish'])
        self.events=[]
        def failed(*args,**kwargs):self.events.append('child');raise TimeoutError
        self.assertEqual(self.run_launch(child=failed),1)
        self.assertEqual(self.events,['arm','child','finish'])

    def test_unknown_stock_or_missing_cleanup_cannot_claim_success(self):
        self.cleaned['stock_unknown']=True
        self.assertEqual(self.run_launch(),1)
        def lost(*args):
            if args[-1]['action']=='finish':raise TimeoutError
            return self.robot(*args)
        self.assertEqual(self.run_launch(robot=lost),1)

    def test_owned_mux_255_requires_validated_transfer_explicit_close_and_natural_reap(self):
        cfg=dict(deployment=dict(robot=dict(user='pollen',host='robot',root='/home/pollen/reachy-companion'),
            hub=dict(user='deploy',host='hub')))
        for close_status,forced,valid,accepted in ((0,False,True,True),(1,False,True,False),
                (0,True,True,False),(0,False,False,False)):
            with self.subTest(close=close_status,forced=forced,valid=valid):
                master=Mock();master.poll.return_value=None;master.returncode=None;calls=[]
                def communicate(**kwargs):
                    calls.append(True)
                    if forced and len(calls)==1:raise subprocess.TimeoutExpired('fixture',2)
                    master.returncode=255
                    return b'controlled helper EOF',b''
                master.communicate.side_effect=communicate
                def run(command,**kwargs):
                    if '-O' in command:
                        return SimpleNamespace(returncode=close_status if 'exit' in command else 0)
                    return SimpleNamespace(returncode=0,stdout=b'{}' if valid else b'not JSON')
                with patch.object(launcher.subprocess,'Popen',return_value=master), \
                        patch.object(launcher.subprocess,'run',side_effect=run), \
                        patch.object(Path,'lstat',return_value=SimpleNamespace(st_mode=stat.S_IFSOCK|0o600,st_uid=os.geteuid())):
                    if accepted:self.assertEqual(launcher.robot_call(cfg,self.hosts,dict(action='fixture')), {})
                    else:
                        with self.assertRaises(RuntimeError):launcher.robot_call(cfg,self.hosts,dict(action='fixture'))


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.value=dict(agent_boot_id='current',microphone_epoch=130,microphone_enabled=False,
            capture_active=False,listening=False,phase='paused',microphone_owner_id=None,motion_policy_owner_id=None,
            motion_policy=dict(epoch=41,motor_enabled=False,quiet=False,privacy_all=False),
            microphone_state_error=None,expression_version=1)
        self.owner='00112233-4455-4677-8899-aabbccddeeff'
        self.io=Mock();self.io.op.side_effect=lambda:copy.deepcopy(self.value)
        self.io.status.return_value=dict(volume_percent=50,turns=2)
        hub=dict(stock_motion=dict(selected=True,unknown=False,owned_uuid=None),ownership=dict(state='free'),
            action_running=False,robot=dict(control_mode='enabled'))
        self.io.req.side_effect=lambda where,path:[] if path=='/api/move/running' else hub

    def arm(self,wrong_pid=False):
        def unit(name):
            return dict(ActiveState='active',MainPID='10' if name=='reachy-voice-agent.service' else '20')
        def spawn(command,**kwargs):
            self.command=command;run=Path(command[command.index('--plan')+1]).parent
            watch.save(run/'watch-ready.json',dict(pid=21 if wrong_pid else 20,identity=dict(pid=20)))
            return SimpleNamespace(returncode=0)
        with patch.object(watch,'RUN_BASE',self.base),patch.object(watch,'state_unit',side_effect=unit), \
                patch.object(watch,'proc',side_effect=lambda pid:dict(pid=pid)), \
                patch.object(watch.subprocess,'run',side_effect=spawn):
            return watch.arm(self.io,dict(action='arm',owner=self.owner,seconds=180))

    def test_dynamic_epochs_independent_systemd_and_verified_process(self):
        ready=self.arm()
        self.assertEqual(ready['operator_binding'],dict(agent_boot_id='current',microphone_epoch=130,policy_epoch=41))
        self.assertEqual(self.command[0],'systemd-run')
        self.assertIn('--property=RuntimeMaxSec=220s',self.command)
        self.assertTrue(all(len(call.args)==2 for call in self.io.req.call_args_list))
        with patch.object(watch,'RUN_BASE',self.base):
            run,plan=watch.load_plan(ready['run_id'],ready['plan_sha256'],self.owner)
            self.assertEqual(plan['mic_epoch'],130);self.assertEqual(plan['policy_epoch'],41)
            with self.assertRaises(watch.GuardDenied):
                watch.finish(dict(action='finish',owner='11112233-4455-4677-8899-aabbccddeeff',
                    run_id=ready['run_id'],plan_sha256=ready['plan_sha256']))
            self.assertFalse((run/'controller.done').exists())

    def test_wrong_watch_pid_cannot_return_ready(self):
        with self.assertRaises(watch.GuardDenied):self.arm(wrong_pid=True)

    def test_cleanup_never_posts_for_newer_owner(self):
        self.value.update(microphone_owner_id='human',motion_policy_owner_id='human')
        self.value['microphone_epoch']+=2;self.value['motion_policy']['epoch']+=2
        plan=dict(boot='current',mic_epoch=130,policy_epoch=41,owner=self.owner,agent_pid=10)
        with patch.object(watch,'playbacks',return_value=[]),patch.object(watch.time,'monotonic',side_effect=[0,0,5]), \
                patch.object(watch.time,'sleep'):
            result=watch.cleanup(self.io,plan)
        self.assertTrue(result['newer_owner_preserved']);self.assertFalse(result['final_OFF'])
        self.assertFalse(result['mic_OFF_POST']);self.assertFalse(result['policy_OFF_POST'])
        self.assertTrue(all(len(call.args)==2 for call in self.io.req.call_args_list))

    def cleanup_state(self):
        self.posts=[]
        def request(where,path,payload=None,expected=None,timeout=2):
            if payload is not None:
                self.assertEqual(watch.authority(expected),watch.authority(self.value))
                self.assertEqual(payload['expected_boot_id'],self.value['agent_boot_id'])
                self.assertNotIn(None,payload.values())
                mic=path=='/microphone';state=self.value if mic else self.value['motion_policy']
                epoch='microphone_epoch' if mic else 'epoch'
                self.assertEqual(payload['expected_epoch'],state[epoch])
                self.posts.append((path,copy.deepcopy(payload)));state[epoch]+=1
                if mic:self.value.update(microphone_enabled=False,capture_active=False,listening=False,microphone_owner_id=None)
                else:self.value['motion_policy']['motor_enabled']=False;self.value['motion_policy_owner_id']=None
                return {}
            return [] if path=='/api/move/running' else dict(stock_motion=dict(unknown=False))
        self.io.req.side_effect=request
        plan=dict(boot='current',mic_epoch=130,policy_epoch=41,owner=self.owner,agent_pid=10)
        with patch.object(watch,'playbacks',return_value=[]):result=watch.cleanup(self.io,plan)
        return result

    def test_unused_watch_fences_both_off_epochs_and_late_child_cannot_grant(self):
        result=self.cleanup_state()
        self.assertTrue(result['final_OFF']);self.assertTrue(result['mic_baseline_fenced']);self.assertTrue(result['policy_baseline_fenced'])
        self.assertEqual(self.value['microphone_epoch'],131);self.assertEqual(self.value['motion_policy']['epoch'],42)
        self.assertEqual(len(self.posts),2)
        self.assertTrue(all('expected_owner_id' not in payload for _,payload in self.posts))
        from reachy_companion.client import demo
        current=dict(self.value,expression_version=1,microphone_state_error=None)
        with patch('reachy_companion.client.request',return_value=current) as io,patch('builtins.print'):
            self.assertEqual(demo({'network':{'hub_url':'http://fixture'}},owner_id=self.owner,
                operator_binding=dict(agent_boot_id='current',microphone_epoch=130,policy_epoch=41)),1)
            self.assertEqual(io.call_count,1);self.assertIsNone(io.call_args.kwargs.get('payload'))

    def test_partial_claim_released_and_remaining_baseline_fenced(self):
        self.value['motion_policy'].update(epoch=42,motor_enabled=True)
        self.value['motion_policy_owner_id']=self.owner
        result=self.cleanup_state()
        self.assertTrue(result['mic_baseline_fenced']);self.assertTrue(result['policy_OFF_POST'])
        self.assertNotIn('expected_owner_id',self.posts[0][1])
        self.assertEqual(self.posts[1][1]['expected_owner_id'],self.owner)
        self.setUp()
        self.value.update(microphone_epoch=131,microphone_enabled=True,capture_active=True,listening=True,microphone_owner_id=self.owner)
        result=self.cleanup_state()
        self.assertTrue(result['mic_OFF_POST']);self.assertTrue(result['policy_baseline_fenced'])
        self.assertEqual(self.posts[0][1]['expected_owner_id'],self.owner)
        self.assertNotIn('expected_owner_id',self.posts[1][1])

    def test_newer_unowned_epoch_is_preserved_without_fence_post(self):
        self.value['microphone_epoch']+=1
        self.cleanup_state()
        self.assertEqual(self.posts,[])

    def test_watch_partial_socket_send_rechecks_freshness_before_continuing(self):
        import threading
        clock=[0];sent=[]
        io=watch.IO.__new__(watch.IO)
        io.token='fixture';io.last_endpoint_by_thread={};io.operator_begin_by_thread={}
        def operator():
            io.operator_begin_by_thread[threading.get_ident()]=clock[0]
            return copy.deepcopy(self.value)
        io.op=operator
        def connect(connection):
            def send(data):sent.append(bytes(data));clock[0]+=.301;return 1
            connection.sock=SimpleNamespace(send=send,settimeout=lambda _:None,close=lambda:None)
        with patch.object(watch.time,'monotonic',side_effect=lambda:clock[0]), \
                patch('http.client.HTTPConnection.connect',connect), \
                patch('http.client.HTTPConnection.getresponse') as response:
            with self.assertRaises(watch.GuardDenied):
                io.req(('127.0.0.1',8090),'/microphone',dict(enabled=False),self.value)
            response.assert_not_called()
        self.assertEqual(len(sent),1)


if __name__=='__main__':unittest.main()
