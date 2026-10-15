"""Clean checkout configuration and just-created worker enrollment, no real Docker."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock

from reachy_companion.config import Config,initialize

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/windows'))
try:
    import enroll_worker as enroll
    import check_pc
finally:sys.path.pop(0)


class WindowsCleanPCTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name);self.inventory=self.path/'private'/'stop-inventory.local.json'
        self.container_id='a'*64;self.image='sha256:'+'f'*64
        self.launch='00000000-0000-4000-8000-000000000001';self.scope=r'C:\Reachy\repo'
        self.value=dict(Id=self.container_id,Image=self.image,State=dict(Status='created',Running=False),
            HostConfig=dict(AutoRemove=False),Config=dict(Entrypoint=['python','-m','reachy_companion'],
            Cmd=['--config','/config/config.worker.local.json','worker','serve'],Labels={
                'io.reachy-companion.launch-id':self.launch,'io.reachy-companion.scope-root':self.scope}),
            Mounts=[dict(Type='bind',Source='/run/desktop/mnt/host/c/Reachy/repo',Destination='/config')])
        self.backend=enroll.WindowsBackend.__new__(enroll.WindowsBackend);self.backend.timeout=10;self.backend.deadline=None
        self.calls=[]
        def command(args,**kwargs):
            self.calls.append(args)
            if 'info' in args:return 'engine-one'
            if 'inspect' in args:return json.dumps([self.value])
            if 'ps' in args:return self.container_id
            raise AssertionError('No resource writes are allowed: '+str(args))
        self.backend.command=Mock(side_effect=command)
        self.args=dict(inventory_path=self.inventory,scope_root=self.scope,docker_executable=r'C:\Docker\docker.exe',
            endpoint='npipe:////./pipe/dockerDesktopLinuxEngine',container_id=self.container_id,launch_id=self.launch,
            config_sha256='c'*64,image_id=self.image)

    def test_just_created_worker_is_locally_enrolled_before_any_start_or_stop(self):
        result=enroll.enroll(self.backend,**self.args)
        self.assertTrue(result['enrolled']);self.assertFalse(result['running'])
        data=json.loads(self.inventory.read_text())
        self.assertEqual(data['docker']['containers'][0]['id'],self.container_id)
        self.assertEqual(data['docker']['containers'][0]['worker_config_sha256'],'c'*64)
        self.assertEqual(data['scope_roots'],[self.scope])
        self.assertEqual(data['models'],[])
        self.assertFalse(any('start' in call or 'stop' in call or 'rm' in call for call in self.calls))

    def test_wrong_nonce_running_wrong_image_command_or_mount_denies_no_inventory_write(self):
        original=copy.deepcopy(self.value)
        for problem in ('nonce','running','image','command','mount'):
            self.value=copy.deepcopy(original)
            if problem=='nonce':self.value['Config']['Labels']['io.reachy-companion.launch-id']='foreign'
            if problem=='running':self.value['State'].update(Status='running',Running=True)
            if problem=='image':self.value['Image']='sha256:'+'0'*64
            if problem=='command':self.value['Config']['Cmd']=['foreign']
            if problem=='mount':self.value['Mounts'][0]['Destination']='/foreign'
            with self.assertRaises(enroll.Denied):enroll.enroll(self.backend,**self.args)
            self.assertFalse(self.inventory.exists())

    def test_existing_targets_preserved_but_engine_change_busy_and_unknown_deny(self):
        enroll.enroll(self.backend,**self.args);old=json.loads(self.inventory.read_text())
        old['services']=[dict(name='ReachyExtra',binary_path=r'C:\Reachy\repo\service.exe',start_name='LocalSystem',
            confirmed_reachy_owned=True,evidence_sha256='e'*64,scope_root=self.scope)]
        self.inventory.write_text(json.dumps(old))
        self.container_id='b'*64;self.value['Id']=self.container_id;self.args['container_id']=self.container_id
        enroll.enroll(self.backend,**self.args)
        current=json.loads(self.inventory.read_text())
        self.assertEqual(current['docker']['containers'][0],old['docker']['containers'][0])
        self.assertEqual(current['services'],old['services'])
        self.assertEqual(len(current['docker']['containers']),2)
        self.container_id='d'*64;self.value['Id']=self.container_id;self.args['container_id']=self.container_id
        lock=self.inventory.with_name(self.inventory.name+'.enrolling');lock.write_text('pending')
        with self.assertRaises(FileExistsError):enroll.enroll(self.backend,**self.args)
        self.assertEqual(lock.read_text(),'pending');lock.unlink()
        before=self.inventory.read_bytes()
        current['docker']['engine_id']='foreign';self.inventory.write_text(json.dumps(current))
        with self.assertRaises(enroll.Denied):enroll.enroll(self.backend,**self.args)
        self.assertEqual(json.loads(self.inventory.read_text())['docker']['engine_id'],'foreign')
        current['docker']['engine_id']='engine-one';current['docker']['containers'][0]['unknown']=True
        self.inventory.write_text(json.dumps(current))
        with self.assertRaises(enroll.Denied):enroll.enroll(self.backend,**self.args)
        self.assertTrue(json.loads(self.inventory.read_text())['docker']['containers'][0]['unknown'])

    def test_registered_reuse_requires_exact_config_image_scope_and_current_identity(self):
        enroll.enroll(self.backend,**self.args)
        args={key:value for key,value in self.args.items() if key!='launch_id'}
        result=enroll.verify_registered(self.backend,**args)
        self.assertTrue(result['registered']);self.assertFalse(result['running'])
        for changes in (dict(config_sha256='0'*64),dict(image_id='sha256:'+'0'*64),dict(container_id='b'*64),dict(scope_root=r'C:\Other')):
            with self.assertRaises(enroll.Denied):enroll.verify_registered(self.backend,**dict(args,**changes))
        self.value['State'].update(Status='running',Running=True)
        self.assertTrue(enroll.verify_registered(self.backend,**args)['running'])

    def test_public_config_preflight_requires_real_inputs_without_mutating_token_or_config(self):
        shutil.copy(ROOT/'config.example.json',self.path);shutil.copytree(ROOT/'profiles',self.path/'profiles')
        initialize(self.path);config=Config(self.path/'config.local.json')
        before=config.filename.read_bytes();token=config.path(config['paths']['token_file']).read_bytes()
        self.assertIn('explicit_hub_ipv4_required',check_pc.check(config,self.path))
        config.data['security']['robot']['hub_source_ipv4']='192.0.2.10'
        self.assertEqual(check_pc.check(config,self.path),[])
        self.assertEqual(config.filename.read_bytes(),before);self.assertEqual(config.path(config['paths']['token_file']).read_bytes(),token)

    def test_manual_stop_during_start_targets_only_registered_id_and_keeps_latch(self):
        enroll.enroll(self.backend,**self.args)
        arguments={key:value for key,value in self.args.items() if key!='launch_id'}
        latch=self.path/'manual-stop.json'
        with self.assertRaises(enroll.Denied):enroll.stop_after_manual_request(self.backend,latch_path=latch,**arguments)
        latch.write_text('human-stop-presence')
        self.backend.docker=Mock(return_value='stopped')
        result=enroll.stop_after_manual_request(self.backend,latch_path=latch,**arguments)
        self.assertTrue(result['stopped_after_manual_request'])
        self.assertEqual(self.backend.docker.call_args.args[0]['id'],self.container_id)
        self.assertFalse(self.backend.docker.call_args.args[2])
        self.assertEqual(latch.read_text(),'human-stop-presence')
        with self.assertRaises(enroll.Denied):enroll.stop_after_manual_request(self.backend,latch_path=latch,**dict(arguments,container_id='f'*64))
        self.assertEqual(self.backend.docker.call_count,1)

    def test_public_startup_create_enroll_start_order_and_no_name_based_removal(self):
        source=(ROOT/'scripts/start-worker.ps1').read_text()
        self.assertLess(source.index("@('create'"),source.index('--launch-id $workerLaunchID'))
        self.assertLess(source.index('--launch-id $workerLaunchID'),source.index("@('start',$workerCreatedID)"))
        self.assertIn('--verify-registered',source)
        self.assertNotIn('@("rm", "-f", $workerName)',source)
        self.assertIn('Assert-CompanionNotManuallyStopped',source)


if __name__=='__main__':unittest.main()
