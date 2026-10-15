"""Independent synthetic Engine shape; no transport, host-env or file lookup."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('docker_create_payload',ROOT/'deploy/autonomous/docker_create_payload.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
identity_spec=importlib.util.spec_from_file_location('create_identity_fixture',ROOT/'deploy/autonomous/docker_config_identity.py')
identity=importlib.util.module_from_spec(identity_spec);identity_spec.loader.exec_module(identity)
IMAGE='sha256:'+'1'*64
OWNER='fixture.private-owner'
OVERLAY=dict(Type='bind',Source='C:\\fixture\\brains.py',
    Destination='/app/src/reachy_companion/brains.py',Mode='ro',RW=False,Propagation='rprivate')


def original():
    return dict(Id='original-container',Name='/original',Image=IMAGE,State={'Running':False},
        Config=dict(Hostname='original-host',Domainname='',User='1000',Image='fixture:tag',
            AttachStdin=False,AttachStdout=True,AttachStderr=True,Tty=False,OpenStdin=False,StdinOnce=False,
            Env=['A=value','FIRST_BARE','SECOND_BARE','EMPTY=','DUP=a','DUP=b','LITERAL=${HOST_ENV}'],
            Cmd=['python','-m','reachy_companion','worker'],Entrypoint=['/entrypoint','--literal'],
            WorkingDir='/app',Labels={'fixture.generation':'old'},Volumes={'/cache':{}},
            StopSignal='SIGTERM',Healthcheck={'Test':['CMD','fixture'],'Interval':30000000000},
            FutureConfig={'null':None,'false':False,'zero':0,'float':0.0}),
        HostConfig=dict(ReadonlyRootfs=True,Tmpfs={'/tmp':'rw,noexec,nosuid,size=65536k'},
            ConsoleSize=[0,0],RestartPolicy={'Name':'unless-stopped','MaximumRetryCount':7,'FuturePolicy':False},
            OomKillDisable=None,AutoRemove=False,NetworkMode='bridge',Links=None,
            PortBindings={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'8080'}]},
            Binds=['C:\\fixture\\config:/app/config:ro'],
            Mounts=[{'Type':'volume','Source':'fixture-cache','Target':'/cache','ReadOnly':False}],
            DeviceRequests=[{'Driver':'nvidia','Count':-1,'DeviceIDs':['GPU-fixture'],
                'Capabilities':[['gpu']],'Options':{}}],
            LogConfig={'Type':'json-file','Config':{'max-size':'1m'}},
            SecurityOpt=['no-new-privileges'],CapDrop=['ALL'],Memory=512000000,NanoCpus=2000000000,
            FutureHost={'zero':0,'false':False,'list':['keep',None]}),
        Mounts=[{'Type':'bind','Source':'C:\\fixture\\config','Destination':'/app/config',
            'Mode':'ro','RW':False,'Propagation':'rprivate'},
            {'Type':'volume','Name':'fixture-cache','Source':'/fixture/cache','Destination':'/cache',
                'Driver':'local','Mode':'','RW':True,'Propagation':''}])


def build(value,**overrides):
    arguments=dict(image_id=IMAGE,owner_label=OWNER,owner_value='new-owner-nonce',overlay_mount=OVERLAY)
    return builder.build_create_payload(value,**{**arguments,**overrides})


class CreatePayloadTests(unittest.TestCase):
    def test_complete_config_host_and_mount_contract_only_allowlisted_changes(self):
        inspected=original();before=copy.deepcopy(inspected);overlay_before=copy.deepcopy(OVERLAY)
        plan=build(inspected);payload=plan['payload'];expected=plan['expected']
        config={key:value for key,value in payload.items() if key!='HostConfig'}
        self.assertEqual(set(payload),set(inspected['Config'])|{'HostConfig'})
        for key,value in inspected['Config'].items():
            if key not in ('Image','Labels'):
                self.assertEqual(json.dumps(config[key]),json.dumps(value),key)
        self.assertEqual(config['Image'],IMAGE)
        self.assertEqual(config['Labels'],{'fixture.generation':'old',OWNER:'new-owner-nonce'})
        host=payload['HostConfig']
        self.assertEqual(set(host),set(inspected['HostConfig']))
        for key,value in inspected['HostConfig'].items():
            if key not in ('RestartPolicy','Mounts'):
                self.assertEqual(json.dumps(host[key]),json.dumps(value),key)
        self.assertEqual(host['RestartPolicy'],{'Name':'no','MaximumRetryCount':0,'FuturePolicy':False})
        self.assertEqual(host['Mounts'],inspected['HostConfig']['Mounts']+[
            {'Type':'bind','Source':'C:\\fixture\\brains.py','Target':'/app/src/reachy_companion/brains.py',
             'ReadOnly':True,'BindOptions':{'Propagation':'rprivate'}}])
        self.assertEqual(expected,{'Config':config,'HostConfig':host,'Mounts':inspected['Mounts']+[OVERLAY]})
        self.assertEqual(inspected,before);self.assertEqual(OVERLAY,overlay_before)
        # Outputs are independent, even nested metadata and overlay records.
        host['FutureHost']['list'].append('mutated')
        expected['Mounts'][-1]['Source']='mutated'
        self.assertEqual(inspected,before);self.assertEqual(OVERLAY,overlay_before)
        self.assertNotIn('mutated',expected['HostConfig']['FutureHost']['list'])

    def test_raw_environment_and_attach_console_readonly_tmpfs_are_exact(self):
        inspected=original();plan=build(inspected)
        self.assertEqual(plan['payload']['Env'],[
            'A=value','FIRST_BARE','SECOND_BARE','EMPTY=','DUP=a','DUP=b','LITERAL=${HOST_ENV}'])
        self.assertIs(plan['payload']['AttachStdin'],False)
        self.assertIs(plan['payload']['AttachStdout'],True);self.assertIs(plan['payload']['AttachStderr'],True)
        self.assertEqual(plan['payload']['HostConfig']['ConsoleSize'],[0,0])
        self.assertIs(plan['payload']['HostConfig']['ReadonlyRootfs'],True)
        self.assertEqual(plan['payload']['HostConfig']['Tmpfs'],{'/tmp':'rw,noexec,nosuid,size=65536k'})
        self.assertIsNone(plan['payload']['HostConfig']['OomKillDisable'])

    def test_expected_contract_rejects_lost_settings_with_only_reviewed_oom_equivalence(self):
        expected=build(original())['expected'];fingerprint=identity.container_config_fingerprint(expected)
        runtime=copy.deepcopy(expected);runtime['HostConfig']['OomKillDisable']=False
        self.assertEqual(identity.container_config_fingerprint(runtime),fingerprint)
        changes=[(('Config','Env'),['A=value']), (('Config','AttachStdout'),False),
            (('Config','Cmd'),[]), (('Config','Labels'),{}),
            (('HostConfig','ReadonlyRootfs'),False), (('HostConfig','Tmpfs'),{}),
            (('HostConfig','ConsoleSize'),[]), (('HostConfig','DeviceRequests'),[]),
            (('HostConfig','NetworkMode'),'host'), (('Mounts',),expected['Mounts'][:-1])]
        for path,value in changes:
            with self.subTest(path=path):
                wrong=copy.deepcopy(runtime);parent=wrong
                for key in path[:-1]:parent=parent[key]
                parent[path[-1]]=value
                self.assertNotEqual(identity.container_config_fingerprint(wrong),fingerprint)

    def test_null_absent_and_empty_unmodified_values_are_not_coerced(self):
        for entrypoint in (None,[],['literal']):
            for mounts in (None,[]):
                inspected=original();inspected['Config']['Entrypoint']=entrypoint
                inspected['Config']['Labels']=None;inspected['HostConfig']['Mounts']=mounts
                inspected['HostConfig']['RestartPolicy']=None
                plan=build(inspected)
                self.assertEqual(plan['payload']['Entrypoint'],entrypoint)
                self.assertEqual(len(plan['payload']['HostConfig']['Mounts']),1)
                self.assertEqual(plan['payload']['HostConfig']['RestartPolicy'],{'Name':'no','MaximumRetryCount':0})
        inspected=original();del inspected['Config']['Env'];del inspected['HostConfig']['Mounts']
        plan=build(inspected);self.assertNotIn('Env',plan['payload'])
        self.assertEqual(len(plan['payload']['HostConfig']['Mounts']),1)

    def test_existing_owner_or_wrong_image_is_never_adopted(self):
        for value in ('foreign','new-owner-nonce',''):
            inspected=original();inspected['Config']['Labels'][OWNER]=value
            with self.assertRaises(ValueError):build(inspected)
        for image in ('fixture:tag','sha256:'+'2'*64,'',None):
            with self.assertRaises(ValueError):build(original(),image_id=image)

    def test_overlay_destination_collisions_all_original_representations(self):
        target=OVERLAY['Destination']
        mutations=[lambda x:x['Mounts'].append({'Destination':target}),
            lambda x:x['HostConfig']['Mounts'].append({'Target':target}),
            lambda x:x['HostConfig']['Binds'].append('/source:'+target+':ro'),
            lambda x:x['HostConfig']['Binds'].append('C:\\source:'+target),
            lambda x:x['HostConfig']['Binds'].append('C:\\source:'+target+':ro'),
            lambda x:x['HostConfig']['Tmpfs'].update({target:'ro'}),
            lambda x:x['Config']['Volumes'].update({target:{}})]
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                inspected=original();mutate(inspected);before=copy.deepcopy(inspected)
                with self.assertRaises(ValueError):build(inspected)
                self.assertEqual(inspected,before)
        inspected=original();inspected['Mounts'][0]['Destination']='/app'
        build(inspected) # an existing directory parent is not the same destination

    def test_malformed_json_sections_env_owner_overlay_reject(self):
        for raw in ('{', '{"Config":{},"Config":{}}','{"number":NaN}','{"number":1e999}', '[]',b'\xff'):
            with self.assertRaises(ValueError):builder.parse_inspection(raw)
        parsed=builder.parse_inspection(json.dumps(original()).encode())
        self.assertEqual(build(parsed),build(original()))
        for inspected in (None,[],{},'{}',{'Config':{},'HostConfig':[],'Mounts':[]}):
            with self.assertRaises(ValueError):build(inspected)
        for key,value in (('Env','A=value'),('Cmd',[0]),('Labels',[]),('Entrypoint',False),('HostConfig',{})):
            inspected=original();inspected['Config'][key]=value
            with self.assertRaises(ValueError):build(inspected)
        for change in ({'RW':0},{'RW':True},{'Mode':'rw'},{'Propagation':'shared'},
                {'Source':'relative.py'},{'Destination':'/app/../brains.py'},
                {'Destination':'//app/brains.py'},
                {'Destination':'/app/other.py'},{'Source':'\\relative-drive-root'}):
            with self.assertRaises(ValueError):build(original(),overlay_mount={**OVERLAY,**change})
        for value in ('',None,0):
            with self.assertRaises(ValueError):build(original(),owner_value=value)
        inspected=original();inspected['HostConfig']['future']=float('inf')
        with self.assertRaises(ValueError):build(inspected)


if __name__=='__main__':unittest.main()
