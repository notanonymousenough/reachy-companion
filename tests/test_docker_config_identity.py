"""Synthetic Docker create/runtime shapes; no daemon, files or operations."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('docker_config_identity',ROOT/'deploy/autonomous/docker_config_identity.py')
identity=importlib.util.module_from_spec(spec);spec.loader.exec_module(identity)


def fixture():
    return dict(Id='container-fixture',Name='/fixture-worker',Image='sha256:fixture',
        State=dict(Running=False,Pid=0),
        Config=dict(Hostname='fixture',Image='fixture:image',User='1000',WorkingDir='/app',
            Env=['MODE=fixture','TOKEN=synthetic-not-secret'],Cmd=['python','-m','fixture'],
            Entrypoint=None,Labels={'trial.owner':'owner-1','trial.generation':'generation-1'},
            ExposedPorts={'8080/tcp':{}},OpenStdin=False),
        HostConfig=dict(OomKillDisable=False,Memory=0,Privileged=False,ReadonlyRootfs=True,
            NetworkMode='bridge',Binds=['/fixture/config:/app/config:ro'],
            DeviceRequests=[dict(Driver='nvidia',Count=-1,DeviceIDs=['GPU-fixture'],
                Capabilities=[['gpu']],Options={})],
            PortBindings={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'8080'}]},
            RestartPolicy=dict(Name='no',MaximumRetryCount=0)),
        Mounts=[dict(Type='bind',Source='/fixture/config',Destination='/app/config',
            Mode='ro',RW=False,Propagation='rprivate')])


class DockerConfigIdentityTests(unittest.TestCase):
    def test_exact_false_and_null_only_equivalent_without_raw_mutation(self):
        created=fixture();runtime=copy.deepcopy(created);runtime['HostConfig']['OomKillDisable']=None
        before_created=copy.deepcopy(created);before_runtime=copy.deepcopy(runtime)
        self.assertEqual(identity.container_config_identity(created),identity.container_config_identity(runtime))
        self.assertEqual(identity.container_config_fingerprint(created),identity.container_config_fingerprint(runtime))
        self.assertEqual(created,before_created);self.assertEqual(runtime,before_runtime)
        self.assertIs(runtime['HostConfig']['OomKillDisable'],None)
        derived=json.loads(identity.container_config_identity(runtime))
        self.assertEqual(set(derived),{'Config','HostConfig','Mounts'})
        self.assertIs(derived['HostConfig']['OomKillDisable'],False)
        self.assertEqual(derived['Config'],created['Config']);self.assertEqual(derived['Mounts'],created['Mounts'])

    def test_true_missing_int_zero_and_string_false_are_pairwise_distinct(self):
        fingerprints=[]
        for value in (False,True,0,0.0,'false',[],{}):
            candidate=fixture();candidate['HostConfig']['OomKillDisable']=value
            fingerprints.append(identity.container_config_identity(candidate))
        missing=fixture();del missing['HostConfig']['OomKillDisable']
        fingerprints.append(identity.container_config_identity(missing))
        self.assertEqual(len(set(fingerprints)),len(fingerprints))

    def test_any_other_leaf_change_or_removal_denies_even_with_null_normalization(self):
        baseline=fixture();expected=identity.container_config_identity(baseline)
        def leaves(value,path=()):
            if type(value) is dict:
                for key,item in value.items():yield from leaves(item,path+(key,))
                if not value:yield path,value
            elif type(value) is list:
                for index,item in enumerate(value):yield from leaves(item,path+(index,))
                if not value:yield path,value
            else:yield path,value
        sectioned={key:baseline[key] for key in ('Config','HostConfig','Mounts')}
        for path,value in leaves(sectioned):
            if path==('HostConfig','OomKillDisable'):continue
            with self.subTest(path=path):
                for remove in (False,True):
                    changed=copy.deepcopy(baseline);changed['HostConfig']['OomKillDisable']=None
                    parent=changed
                    for key in path[:-1]:parent=parent[key]
                    if remove:del parent[path[-1]]
                    else:parent[path[-1]]='changed-fixture' if value!='changed-fixture' else 'different'
                    self.assertNotEqual(identity.container_config_identity(changed),expected)

    def test_other_field_types_presence_list_order_and_new_keys_preserved(self):
        baseline=fixture();expected=identity.container_config_identity(baseline)
        changes=[(('HostConfig','Memory'),False),(('HostConfig','Memory'),0.0),
            (('Config','OpenStdin'),0),(('Config','Entrypoint'),[]),
            (('Config','Env'),list(reversed(baseline['Config']['Env']))),
            (('Config','Cmd'),list(reversed(baseline['Config']['Cmd']))),
            (('Config','Labels'),{'trial.owner':'new-owner','trial.generation':'generation-1'}),
            (('HostConfig','NetworkMode'),'host'),
            (('HostConfig','DeviceRequests'),[]),(('Mounts',),[])]
        for path,value in changes:
            with self.subTest(path=path,value=value):
                changed=copy.deepcopy(baseline);parent=changed
                for key in path[:-1]:parent=parent[key]
                parent[path[-1]]=value
                self.assertNotEqual(identity.container_config_identity(changed),expected)
        for section in ('Config','HostConfig'):
            changed=copy.deepcopy(baseline);changed[section]['new-field']=None
            self.assertNotEqual(identity.container_config_identity(changed),expected)
        changed=copy.deepcopy(baseline);changed['Mounts'][0]['new-field']=None
        self.assertNotEqual(identity.container_config_identity(changed),expected)
        changed=copy.deepcopy(baseline);changed['Config']['OomKillDisable']=None
        different=copy.deepcopy(changed);different['Config']['OomKillDisable']=False
        self.assertNotEqual(identity.container_config_identity(changed),identity.container_config_identity(different))

    def test_invalid_sections_and_non_json_values_reject(self):
        for section in ('Config','HostConfig','Mounts'):
            for invalid in (None,0,False,'',[] if section!='Mounts' else {}):
                changed=fixture();changed[section]=invalid
                with self.assertRaises(ValueError):identity.container_config_identity(changed)
            changed=fixture();del changed[section]
            with self.assertRaises(ValueError):identity.container_config_identity(changed)
        for value in (float('nan'),float('inf'),set(),(1,),object(),{1:'numeric-key'}):
            changed=fixture();changed['Config']['invalid']=value
            with self.assertRaises(ValueError):identity.container_config_identity(changed)

    def test_object_order_has_no_effect_and_top_level_identity_remains_caller_owned(self):
        baseline=fixture();reordered=copy.deepcopy(baseline)
        reordered['HostConfig']=dict(reversed(list(reordered['HostConfig'].items())))
        self.assertEqual(identity.container_config_identity(baseline),identity.container_config_identity(reordered))
        # This deliberately narrow helper cannot replace separate ID/image/state ownership checks.
        reordered.update(Id='foreign',Image='foreign',Name='/foreign',State={'Running':True})
        self.assertEqual(identity.container_config_identity(baseline),identity.container_config_identity(reordered))


if __name__=='__main__':unittest.main()
