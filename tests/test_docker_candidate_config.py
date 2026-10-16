"""Own candidate Engine normalization boundary; synthetic inspect, no Docker I/O."""
import copy
import unittest
from test_docker_config_identity import identity, fixture


class CandidateConfigTests(unittest.TestCase):
    def setUp(self):
        self.expected=fixture()
        self.actual=copy.deepcopy(self.expected)
        self.actual.update(RestartCount=0,State=dict(Running=True,Pid=23,StartedAt='2026-10-16T12:30:37.732414669Z'))
        self.actual['HostConfig']['OomKillDisable']=None
        self.witness=dict(Id=self.expected['Id'],Pid=23,StartedAt=self.actual['State']['StartedAt'])
        self.context=dict(engine_version='29.7.2',api_version='1.55',owned_start=self.witness)

    def matches(self,**context):
        return identity.candidate_config_matches(self.expected,self.actual,**(self.context|context))

    def test_same_comparison_accepts_own_running_and_stopped_after_start_without_mutation(self):
        for running in (True,False):
            self.actual['State'].update(Running=running,Pid=23 if running else 0)
            before=copy.deepcopy((self.expected,self.actual,self.context))
            self.assertTrue(self.matches())
            self.assertEqual((self.expected,self.actual,self.context),before)

    def test_never_started_requires_raw_false_even_on_known_engine(self):
        self.actual['State']=dict(Running=False,Pid=0,StartedAt='0001-01-01T00:00:00Z')
        self.assertFalse(self.matches(owned_start=None))
        self.assertFalse(self.matches())
        self.actual['HostConfig']['OomKillDisable']=False
        self.assertTrue(self.matches(owned_start=None))
        self.assertTrue(identity.candidate_config_matches(self.expected,self.actual))

    def test_exception_is_directional_and_only_literal_false_to_null(self):
        for before in (None,True,0,0.0,'false',[],{}):
            self.expected['HostConfig']['OomKillDisable']=before
            self.actual['HostConfig']['OomKillDisable']=False
            self.assertFalse(self.matches())
        self.expected['HostConfig']['OomKillDisable']=False
        for after in (True,0,0.0,'false',[],{}):
            self.actual['HostConfig']['OomKillDisable']=after
            self.assertFalse(self.matches())
        for target in (self.expected,self.actual):
            saved=target['HostConfig'].pop('OomKillDisable')
            self.assertFalse(self.matches());target['HostConfig']['OomKillDisable']=saved

    def test_unknown_runtime_or_missing_owned_start_never_normalizes(self):
        for context in (dict(engine_version='29.7.3'),dict(engine_version=None),dict(engine_version=29),
                dict(api_version='1.54'),dict(api_version=None),dict(api_version=1.55),dict(owned_start=None)):
            with self.subTest(context=context):self.assertFalse(self.matches(**context))

    def test_wrong_start_identity_pid_generation_and_restarts_reject(self):
        for field,values in (('Id',('foreign',None,0)),('Pid',(0,True,'23',24)),
                ('StartedAt',('0001-01-01T00:00:00Z','not-timeZ','2026-10-16T12:31:37Z',None))):
            for value in values:
                with self.subTest(field=field,value=value):
                    self.assertFalse(self.matches(owned_start=self.witness|{field:value}))
        for witness in ({},self.witness|{'extra':True},[],True):self.assertFalse(self.matches(owned_start=witness))
        for key,value in (('Pid',True),('Pid',0),('Pid',24),('Running',0),('StartedAt','new')):
            before=copy.deepcopy(self.actual['State']);self.actual['State'][key]=value
            self.assertFalse(self.matches());self.actual['State']=before
        for value in (True,1,0.0,None):
            self.actual['RestartCount']=value;self.assertFalse(self.matches())
        self.actual['RestartCount']=0;self.actual['Id']='foreign';self.assertFalse(self.matches())

    def test_every_other_config_host_leaf_presence_type_and_array_order_stays_exact(self):
        def leaves(value,path=()):
            if type(value) is dict and value:
                for key,item in value.items():yield from leaves(item,path+(key,))
            elif type(value) is list and value:
                for index,item in enumerate(value):yield from leaves(item,path+(index,))
            else:yield path,value
        for section in ('Config','HostConfig'):
            for path,value in leaves(self.expected[section]):
                if path==('OomKillDisable',):continue
                for remove in (False,True):
                    with self.subTest(section=section,path=path,remove=remove):
                        actual=copy.deepcopy(self.actual);parent=actual[section]
                        for key in path[:-1]:parent=parent[key]
                        if remove:del parent[path[-1]]
                        else:parent[path[-1]]='changed'
                        self.assertFalse(identity.candidate_config_matches(self.expected,actual,**self.context))
            extra=copy.deepcopy(self.actual);extra[section]['unknown']=None
            self.assertFalse(identity.candidate_config_matches(self.expected,extra,**self.context))
        for section,key,value in (('HostConfig','Memory',False),('HostConfig','Memory',0.0),
                ('Config','OpenStdin',0),('Config','Env',list(reversed(self.actual['Config']['Env'])))):
            changed=copy.deepcopy(self.actual);changed[section][key]=value
            self.assertFalse(identity.candidate_config_matches(self.expected,changed,**self.context))

    def test_full_nested_host_mounts_and_config_network_remain_exact(self):
        self.expected['HostConfig']['Mounts']=[dict(Target='/one',ReadOnly=True),dict(Target='/two',ReadOnly=True)]
        self.actual['HostConfig']['Mounts']=copy.deepcopy(self.expected['HostConfig']['Mounts'])
        self.assertTrue(self.matches())
        self.actual['HostConfig']['Mounts'].reverse();self.assertFalse(self.matches())
        self.actual['HostConfig']['Mounts'].reverse()
        self.actual['HostConfig']['NetworkMode']='host';self.assertFalse(self.matches())

    def test_no_general_normalization_of_nulls_or_other_named_oom_fields(self):
        self.expected['Config']['OomKillDisable']=False;self.actual['Config']['OomKillDisable']=None
        self.assertFalse(self.matches())
        del self.expected['Config']['OomKillDisable'];del self.actual['Config']['OomKillDisable']
        self.expected['HostConfig']['Future']=False;self.actual['HostConfig']['Future']=None
        self.assertFalse(self.matches())

    def test_malformed_or_non_json_sections_reject_without_diagnostics_containing_values(self):
        for section in ('Config','HostConfig'):
            for value in (None,False,[],0):
                changed=copy.deepcopy(self.actual);changed[section]=value
                with self.assertRaises(ValueError):identity.candidate_config_matches(self.expected,changed,**self.context)
        changed=copy.deepcopy(self.actual);changed['Config']['private']={'PRIVATE'}
        with self.assertRaises(ValueError) as caught:identity.candidate_config_matches(self.expected,changed,**self.context)
        self.assertNotIn('PRIVATE',str(caught.exception))


if __name__=='__main__':unittest.main()
