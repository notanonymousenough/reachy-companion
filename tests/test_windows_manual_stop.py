"""Stop selection and backend protocol tests. Native Windows acceptance is separate."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reachy_manual_stop',ROOT/'scripts/windows/stop_reachy.py')
stop=importlib.util.module_from_spec(spec);spec.loader.exec_module(stop)
SCOPE=r'C:\Reachy\repo'


def owned(**extra):return dict(scope_root=SCOPE,confirmed_reachy_owned=True,evidence_sha256='e'*64,**extra)
def container(letter):
    return owned(id=letter*64,image_id='sha256:'+'f'*64,command_sha256=stop.digest(dict(entrypoint=None,cmd=['worker','serve'])),
                 mount_source='/run/desktop/mnt/host/c/Reachy/repo',mount_destination='/config')
def manifest():
    return dict(schema=1,owner='reachy-companion',scope_roots=[SCOPE],
        docker=dict(executable=r'C:\Docker\docker.exe',endpoint='npipe:////./pipe/dockerDesktopLinuxEngine',engine_id='engine-one',
                    containers=[container('a'),container('b')]),processes=[],services=[],tasks=[],models=[])


def fake_kernel(entry):
    api=types.SimpleNamespace(**{name:Mock() for name in ('OpenProcess','CloseHandle','GetProcessTimes',
        'QueryFullProcessImageNameW','WaitForSingleObject','TerminateProcess')})
    api.OpenProcess.return_value=123;api.CloseHandle.return_value=True;api.TerminateProcess.return_value=True
    def times(handle,created,*args):created._obj.dwLowDateTime=110;created._obj.dwHighDateTime=0;return True
    def path(handle,flags,buffer,size):buffer.value=entry['executable'];return True
    api.GetProcessTimes.side_effect=times;api.QueryFullProcessImageNameW.side_effect=path
    api.WaitForSingleObject.side_effect=[258,258,0]
    return api


class FakeBackend:
    def __init__(self):self.calls=[];self.running=set();self.failure={}
    def stop(self,kind,entry,manifest,*,dry_run):
        identity=entry.get('id',entry.get('pid'));self.calls.append((kind,identity,dry_run))
        if identity in self.failure:raise self.failure[identity]
        if identity not in self.running:return 'already_stopped'
        if dry_run:return 'would_stop'
        self.running.remove(identity);return 'stopped'


class WindowsManualStopTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name);self.latch=self.directory/'new-parent'/'manual-stop.json'
        self.inventory=manifest()

    def test_exact_allowlist_dryrun_zero_writes_then_stop_first_and_idempotent(self):
        backend=FakeBackend();backend.running={'a'*64,'b'*64,'foreign'}
        result=stop.stop_inventory(self.inventory,backend,latch_path=self.latch,dry_run=True)
        self.assertTrue(result['ok']);self.assertFalse(self.latch.parent.exists())
        self.assertEqual(backend.running,{'a'*64,'b'*64,'foreign'})
        original=backend.stop
        def check(*args,**kwargs):self.assertTrue(self.latch.exists());return original(*args,**kwargs)
        backend.stop=check
        result=stop.stop_inventory(self.inventory,backend,latch_path=self.latch)
        self.assertTrue(result['ok']);self.assertEqual(backend.running,{'foreign'})
        before=self.latch.read_bytes()
        result=stop.stop_inventory(self.inventory,backend,latch_path=self.latch)
        self.assertTrue(result['ok']);self.assertEqual(before,self.latch.read_bytes())
        self.assertTrue(all(row['status']=='already_stopped' for row in result['results']))
        self.assertFalse(result['gpu_freed_verified'])

    def test_latch_precedes_bad_inventory_and_busy_timeout_never_clears_unknown(self):
        backend=FakeBackend()
        with self.assertRaises(stop.Denied):stop.stop_inventory({},backend,latch_path=self.latch)
        self.assertTrue(self.latch.exists());self.assertEqual(backend.calls,[])
        self.latch.write_text('malformed-presence')
        backend.failure={'a'*64:TimeoutError('SECRET'), 'b'*64:RuntimeError('SECRET')}
        report=stop.stop_inventory(self.inventory,backend,latch_path=self.latch)
        self.assertEqual([row['status'] for row in report['results']],['timeout_unknown','error_unknown'])
        self.assertFalse(report['ok']);self.assertNotIn('SECRET',json.dumps(report))
        self.assertEqual(self.latch.read_text(),'malformed-presence')

    def test_total_deadline_skips_remaining_targets_keeps_latch_and_bounds_each_command(self):
        clock=[10]
        backend=FakeBackend();original=backend.stop
        def delayed(*args,**kwargs):clock[0]+=6;return original(*args,**kwargs)
        backend.stop=delayed
        result=stop.stop_inventory(self.inventory,backend,latch_path=self.latch,total_timeout=5,clock=lambda:clock[0])
        self.assertEqual(len(backend.calls),1)
        self.assertEqual(result['results'][1]['status'],'not_attempted_deadline')
        self.assertFalse(result['ok']);self.assertTrue(self.latch.exists())
        native=stop.WindowsBackend.__new__(stop.WindowsBackend);native.timeout=15;native.deadline=time.monotonic()+.5
        with patch.object(stop.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=b'',stderr=b'')) as run:
            native.command(['fixture'])
        self.assertLessEqual(run.call_args.kwargs['timeout'],.5)

    def test_foreign_missing_shortid_and_shared_application_not_authorized(self):
        cases=[]
        for change in (dict(id='a'*12),dict(confirmed_reachy_owned=False),dict(scope_root=r'C:\Foreign'),dict(evidence_sha256='bad')):
            item=manifest();item['docker']['containers'][0].update(change);cases.append(item)
        item=manifest();item['processes']=[owned(pid=42,creation_filetime=10,executable=r'C:\Apps\LM Studio.exe',
            command_sha256='c'*64,role='lm_studio_dedicated',dedicated_to_reachy=False)];cases.append(item)
        item=manifest();item['processes']=[owned(pid=42,creation_filetime=True,executable=r'C:\Python\python.exe',
            command_sha256='c'*64,role='launcher')];cases.append(item)
        for value in cases:
            with self.assertRaises(stop.Denied):stop.checked_manifest(value)

    def docker_backend(self):
        backend=stop.WindowsBackend.__new__(stop.WindowsBackend);backend.timeout=15;backend.deadline=None
        values={entry['id']:dict(Id=entry['id'],Image=entry['image_id'],Config=dict(Entrypoint=None,Cmd=['worker','serve']),
            Mounts=[dict(Type='bind',Source=entry['mount_source'],Destination='/config')],
            HostConfig=dict(AutoRemove=False),State=dict(Running=True)) for entry in self.inventory['docker']['containers']}
        calls=[]
        def command(args,**kwargs):
            calls.append(args)
            if 'info' in args:return 'engine-one'
            if 'ps' in args:return '\n'.join([*values,'foreign-id'])
            if 'inspect' in args:return json.dumps([values[args[-1]]])
            if 'stop' in args:values[args[-1]]['State']['Running']=False;return args[-1]
            raise AssertionError(args)
        backend.command=Mock(side_effect=command)
        return backend,values,calls

    def test_docker_fullid_image_command_mount_and_engine_checked_no_foreign_stop(self):
        backend,values,calls=self.docker_backend()
        result=stop.stop_inventory(self.inventory,backend,latch_path=self.latch)
        self.assertTrue(result['ok'])
        self.assertEqual([args[-1] for args in calls if 'stop' in args],['a'*64,'b'*64])
        for problem in ('image','command','mount','auto_remove'):
            backend,values,calls=self.docker_backend();item=values['a'*64]
            if problem=='image':item['Image']='sha256:'+'0'*64
            if problem=='command':item['Config']['Cmd']=['foreign']
            if problem=='mount':item['Mounts'][0]['Source']='/foreign'
            if problem=='auto_remove':item['HostConfig']['AutoRemove']=True
            with self.assertRaises(stop.Denied):backend.docker(self.inventory['docker']['containers'][0],self.inventory,False)
            self.assertFalse(any('stop' in args for args in calls))

    def test_docker_dryrun_and_repeat_stop_are_readonly(self):
        backend,values,calls=self.docker_backend();entry=self.inventory['docker']['containers'][0]
        self.assertEqual(backend.docker(entry,self.inventory,True),'would_stop')
        self.assertFalse(any('stop' in args for args in calls))
        values[entry['id']]['State']['Running']=False
        self.assertEqual(backend.docker(entry,self.inventory,False),'already_stopped')
        self.assertFalse(any('stop' in args for args in calls))

    def test_process_snapshot_creation_exe_and_command_hash_not_name_or_port(self):
        command=r'python C:\Reachy\repo\launch.py'
        entry=dict(creation_filetime=110,executable=r'C:\Python\python.exe',command_sha256=hashlib.sha256(command.encode()).hexdigest())
        valid=dict(creation_filetime=110,executable=r'c:\python\PYTHON.exe',command=command)
        self.assertTrue(stop.WindowsBackend.same_process(valid,entry))
        for change in (dict(creation_filetime=111),dict(creation_filetime=True),dict(executable=r'C:\Foreign\python.exe'),dict(command='foreign')):
            self.assertFalse(stop.WindowsBackend.same_process(dict(valid,**change),entry))

    def test_process_termination_uses_original_pinned_handle_and_denies_reused_pid(self):
        command=r'python C:\Reachy\repo\launch.py'
        entry=owned(pid=42,role='launcher',creation_filetime=110,executable=r'C:\Python\python.exe',
                    command_sha256=hashlib.sha256(command.encode()).hexdigest())
        backend=stop.WindowsBackend.__new__(stop.WindowsBackend);backend.timeout=15;backend.deadline=None
        backend.process_snapshot=Mock(return_value=dict(creation_filetime=110,executable=entry['executable'],command=command))
        api=fake_kernel(entry)
        with patch.object(stop.ctypes,'WinDLL',create=True,return_value=api):self.assertEqual(backend.process(entry,False),'stopped')
        api.OpenProcess.assert_called_once();api.TerminateProcess.assert_called_once_with(123,0);api.CloseHandle.assert_called_once_with(123)
        api=fake_kernel(entry);backend.process_snapshot.return_value['creation_filetime']=111
        with patch.object(stop.ctypes,'WinDLL',create=True,return_value=api):
            with self.assertRaises(stop.Denied):backend.process(entry,False)
        api.TerminateProcess.assert_not_called();api.CloseHandle.assert_called_once_with(123)

    def test_process_dryrun_never_terminates_and_command_scope_is_required(self):
        command=r'python C:\Reachy\repo\launch.py'
        entry=owned(pid=42,role='launcher',creation_filetime=110,executable=r'C:\Python\python.exe',
                    command_sha256=hashlib.sha256(command.encode()).hexdigest())
        backend=stop.WindowsBackend.__new__(stop.WindowsBackend);backend.timeout=15;backend.deadline=None
        backend.process_snapshot=Mock(return_value=dict(creation_filetime=110,executable=entry['executable'],command=command))
        api=fake_kernel(entry)
        with patch.object(stop.ctypes,'WinDLL',create=True,return_value=api):self.assertEqual(backend.process(entry,True),'would_stop')
        api.TerminateProcess.assert_not_called()
        self.assertEqual(api.OpenProcess.call_args.args[0]&1,0)
        command=r'python C:\Foreign\launch.py';entry['command_sha256']=hashlib.sha256(command.encode()).hexdigest()
        backend.process_snapshot.return_value['command']=command
        api=fake_kernel(entry)
        with patch.object(stop.ctypes,'WinDLL',create=True,return_value=api):
            with self.assertRaises(stop.Denied):backend.process(entry,False)
        api.TerminateProcess.assert_not_called()

    def test_service_and_task_changed_identity_denies_before_any_stop(self):
        backend=stop.WindowsBackend.__new__(stop.WindowsBackend);backend.timeout=15;backend.deadline=None
        backend.ps=Mock(return_value=dict(binary_path='foreign',start_name='operator',state='Running'))
        with self.assertRaises(stop.Denied):backend.service(dict(name='Reachy',binary_path='ours',start_name='operator'),False)
        self.assertEqual(backend.ps.call_count,1)
        backend.ps=Mock(return_value=dict(xml='foreign',state='Running'))
        with self.assertRaises(stop.Denied):backend.task(dict(name='Reachy',path='\\',xml_sha256='0'*64),False)
        self.assertEqual(backend.ps.call_count,1)

    def test_only_dedicated_model_instance_supported_no_cli_all_or_foreign_selection(self):
        backend=stop.WindowsBackend.__new__(stop.WindowsBackend);backend.timeout=15;backend.deadline=None
        server=dict(pid=42,creation_filetime=110,executable=r'C:\Apps\LM Studio.exe',command_sha256='c'*64)
        entry=owned(model_key='reachy-key',instance_id='reachy-instance',config_sha256=stop.digest(dict(context_length=1024)),
                    dedicated_to_reachy=True,url='http://127.0.0.1:1234',server=server,token_env=None)
        state={'models':[dict(key='reachy-key',loaded_instances=[dict(id='reachy-instance',config=dict(context_length=1024))]),
                         dict(key='foreign-key',loaded_instances=[dict(id='foreign-instance',config={})])]}
        backend.process_snapshot=Mock(return_value={'fixture':'pinned'})
        backend.same_process=Mock(return_value=True);backend.ps=Mock(return_value=[42]);calls=[]
        def command(args,*,input):
            request=json.loads(input);calls.append(request)
            if request['url'].endswith('/unload'):
                self.assertEqual(request['payload'],dict(instance_id='reachy-instance'))
                state['models'][0]['loaded_instances']=[]
                return json.dumps(dict(instance_id='reachy-instance'))
            return json.dumps(state)
        backend.command=Mock(side_effect=command)
        self.assertEqual(backend.model(entry,True),'would_stop');self.assertTrue(all(v['payload'] is None for v in calls))
        calls.clear();self.assertEqual(backend.model(entry,False),'stopped')
        self.assertEqual(state['models'][1]['loaded_instances'][0]['id'],'foreign-instance')
        self.assertEqual(len([v for v in calls if v['payload'] is not None]),1)
        self.assertTrue(all('--all' not in str(v) for v in calls))

    def test_existing_entrypoints_guard_before_writes_launch_and_acceptance(self):
        for name in ('start.ps1','start-worker.ps1','install-startup.ps1','apply-character.ps1'):
            source=(ROOT/'scripts'/name).read_text()
            self.assertIn('Assert-CompanionNotManuallyStopped',source)
            next_action=('Read-CompanionSettings' if 'Read-CompanionSettings' in source else
                         'Invoke-CompanionAcceptedRuntimeVerification' if 'Invoke-CompanionAcceptedRuntimeVerification' in source else '$characterPatch')
            self.assertLess(source.index('Assert-CompanionNotManuallyStopped'),source.index(next_action))
        wrapper=(ROOT/'scripts/windows/stop-reachy.ps1').read_text()
        self.assertLess(wrapper.index('[IO.File]::Open'),wrapper.index('& $PythonExecutable'))
        self.assertIn('if (-not ($DryRun -or $WhatIf))',wrapper)
        self.assertIn('[Console]::IsInputRedirected',wrapper)
        common=(ROOT/'scripts/common.ps1').read_text()
        self.assertIn('[IO.File]::GetAttributes',common)
        self.assertIn('[IO.FileAttributes]::ReparsePoint',common)
        self.assertIn('catch [IO.FileNotFoundException]',common)
        self.assertNotIn('Test-Path',common.split('function Merge-CompanionSettings')[0])


if __name__=='__main__':unittest.main()
