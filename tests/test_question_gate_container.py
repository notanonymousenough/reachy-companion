"""Pure replacement of two already occupied read-only worker code mounts."""
import copy
import hashlib
import importlib.util
import json
import ntpath
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class QuestionGateContainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('question_container_plan',
            ROOT/'deploy/autonomous/prepare_question_gate_container.py')
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def setUp(self):
        self.cid = 'a'*64
        self.image = 'sha256:'+'b'*64
        self.instance = dict(Pid=123, StartedAt='2026-10-17T00:00:00Z')
        self.root = r'C:\owned'
        self.paths = {name: ntpath.join(r'C:\owned\new-stage', name) for name in self.m.FILES}
        self.sources = {name: b'# parsed, never executed\n' for name in self.m.FILES}
        self.pins = {name: hashlib.sha256(raw).hexdigest() for name, raw in self.sources.items()}
        requests = [dict(Type='bind', Source=r'C:\private-config', Target='/config', ReadOnly=False),
            dict(Type='bind', Source=r'C:\models', Target='/models', ReadOnly=True),
            dict(Type='bind', Source=r'C:\data', Target='/data', ReadOnly=False)]
        requests += [dict(Type='bind', Source=ntpath.join(r'C:\frozen', name),
            Target=self.m.SITE+name, ReadOnly=True, BindOptions=dict(Propagation='rprivate')) for name in self.m.FILES]
        self.snapshot = dict(Id=self.cid, Name='/private-baseline', Image=self.image, RestartCount=0,
            State=dict(Running=True, Paused=False, Restarting=False, OOMKilled=False, **self.instance),
            Config=dict(Image='same-image-tag', Env=['PRIVATE_TOKEN=fixture', 'BARE'],
                Entrypoint=['python'], Cmd=['worker', 'serve'], User='1000', Labels={'keep': 'original'}),
            HostConfig=dict(ReadonlyRootfs=True, Binds=None, Mounts=requests, OomKillDisable=None,
                RestartPolicy=dict(Name='unless-stopped', MaximumRetryCount=0),
                PortBindings={'8082/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8082'}]},
                NetworkMode='bridge', SecurityOpt=['no-new-privileges'], CapDrop=['ALL']),
            Mounts=[dict(Type='bind', Source=req['Source'], Destination=req['Target'],
                Mode='ro' if req['ReadOnly'] else '', RW=not req['ReadOnly'], Propagation='rprivate') for req in requests])

    def prepare(self):
        return self.m.prepare(self.snapshot, self.paths, self.sources, self.pins, self.instance,
            current_id=self.cid, image_id=self.image, stage_root=self.root)

    def test_only_two_source_paths_and_known_engine_type_case_change(self):
        original = copy.deepcopy(self.snapshot)
        result = self.prepare()
        self.assertEqual(self.snapshot, original)
        payload = result['private_create_payload']
        host = payload['HostConfig']
        expected_host = copy.deepcopy(original['HostConfig'])
        expected_host['OomKillDisable'] = False
        for req in expected_host['Mounts']:
            name = req['Target'].rsplit('/', 1)[-1]
            if name in self.paths: req['Source'] = self.paths[name]
        self.assertEqual(host, expected_host)
        expected_config = copy.deepcopy(original['Config'])
        expected_config['Image'] = self.image
        self.assertEqual({k: v for k, v in payload.items() if k != 'HostConfig'}, expected_config)
        self.assertEqual(len(host['Mounts']), 5)
        self.assertEqual(host['RestartPolicy'], original['HostConfig']['RestartPolicy'])
        self.assertEqual(payload['Env'], ['PRIVATE_TOKEN=fixture', 'BARE'])
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(result['public_summary']))
        self.assertEqual(result['public_summary']['Docker_operations'], 0)
        self.assertEqual(result['public_summary']['added_destinations'], [])
        result['private_create_payload']['Env'].append('mutated-result')
        self.assertEqual(self.snapshot, original)

    def test_expected_mount_inventory_preserves_every_other_field(self):
        result = self.prepare()
        expected = copy.deepcopy(self.snapshot['Mounts'])
        for mount in expected:
            name = mount['Destination'].rsplit('/', 1)[-1]
            if name in self.paths: mount['Source'] = self.paths[name]
        self.assertEqual(result['expected']['Mounts'], expected)
        self.assertEqual(result['expected']['HostConfig'], result['private_create_payload']['HostConfig'])

    def test_duplicate_missing_and_nonreadonly_code_destinations_reject(self):
        for case in ('duplicate', 'missing', 'rw', 'source-drift'):
            with self.subTest(case=case):
                before = copy.deepcopy(self.snapshot)
                mounts = self.snapshot['HostConfig']['Mounts']
                if case == 'duplicate': mounts[-1]['Target'] = mounts[-2]['Target']
                if case == 'missing': mounts[-1]['Target'] = '/unrelated'
                if case == 'rw':
                    mounts[-1]['ReadOnly'] = False
                    self.snapshot['Mounts'][-1]['RW'] = True
                if case == 'source-drift': mounts[-1]['Source'] = r'C:\different\config.py'
                with self.assertRaises(ValueError): self.prepare()
                self.snapshot = before

    def test_source_pin_code_and_stage_guards_reject(self):
        original_paths = dict(self.paths)
        for path in (r'C:\outside\voice.py', r'C:\owned\a\..\voice.py',
                     r'C:\owned\voice.py', r'C:\owned\other\voice.py'):
            with self.subTest(path=path):
                self.paths['voice.py'] = path
                with self.assertRaises(ValueError): self.prepare()
        self.paths = dict(original_paths)
        self.paths['voice.py'] = r'C:\frozen\voice.py'
        self.paths['config.py'] = r'C:\frozen\config.py'
        self.root = ntpath.dirname(r'C:\frozen')
        with self.assertRaises(ValueError): self.prepare()
        self.paths = dict(original_paths)
        self.root = r'C:\owned'
        self.pins['voice.py'] = '0'*64
        with self.assertRaises(ValueError): self.prepare()

    def test_current_instance_image_rootfs_and_typed_oom_guards(self):
        for case in ('pid', 'started', 'oom', 'paused', 'image', 'rootfs', 'oom-disable', 'binds'):
            before = copy.deepcopy(self.snapshot)
            if case == 'pid': self.snapshot['State']['Pid'] += 1
            if case == 'started': self.snapshot['State']['StartedAt'] = 'new'
            if case == 'oom': self.snapshot['State']['OOMKilled'] = True
            if case == 'paused': self.snapshot['State']['Paused'] = True
            if case == 'image': self.snapshot['Image'] = 'sha256:'+'c'*64
            if case == 'rootfs': self.snapshot['HostConfig']['ReadonlyRootfs'] = False
            if case == 'oom-disable': self.snapshot['HostConfig']['OomKillDisable'] = True
            if case == 'binds': self.snapshot['HostConfig']['Binds'] = ['unreviewed']
            with self.subTest(case=case):
                with self.assertRaises(ValueError): self.prepare()
            self.snapshot = before

    def test_profile_activation_changes_only_one_new_bool(self):
        value = dict(llm=dict(system_prompt='private fixture', max_tokens=512),
                     conversation=dict(existing=False))
        raw = json.dumps(value).encode()
        changed = json.loads(self.m.acceptance_profile(raw, expected_sha=hashlib.sha256(raw).hexdigest()))
        self.assertIs(changed['conversation'].pop('alice_question_gate'), True)
        self.assertEqual(changed, value)
        raw = b'{"llm":{"max_tokens":512}}'
        changed = json.loads(self.m.acceptance_profile(raw, expected_sha=hashlib.sha256(raw).hexdigest()))
        self.assertEqual(changed, dict(llm=dict(max_tokens=512), conversation=dict(alice_question_gate=True)))

    def test_profile_wrong_preimage_duplicate_or_existing_flag_reject(self):
        for raw in (b'{"conversation":{"alice_question_gate":false}}', b'{"llm":{},"llm":{}}', b'{"llm":{"x":NaN}}'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    self.m.acceptance_profile(raw, expected_sha=hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError): self.m.acceptance_profile(b'{}', expected_sha='0'*64)

    def test_start_permission_requires_all_original_guards_literal_true(self):
        flags = dict(manual_stop_absent=True, operation_slot_owned=True, pending_empty=True,
            robot_OFF_fresh=True, source_config_guards_exact=True, sole_worker_port=True, model_same=True)
        self.assertTrue(self.m.may_start(**flags))
        for key in flags:
            for value in (False, None, 1):
                with self.subTest(key=key, value=value):
                    self.assertFalse(self.m.may_start(**dict(flags, **{key: value})))
