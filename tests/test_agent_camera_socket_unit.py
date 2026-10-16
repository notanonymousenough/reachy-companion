"""Service-only IPC visibility fix; no systemd, namespace or camera operation."""
import configparser
import json
from pathlib import Path
import subprocess
import types
import unittest
from reachy_companion.deployment import service_unit

ROOT=Path(__file__).resolve().parents[1]
BIND='BindReadOnlyPaths=/tmp/reachymini_camera_socket\n'
DROPIN=ROOT/'deploy/systemd/reachy-voice-agent.service.d/30-camera-ipc.conf'


class UnitConfig(dict):
    def path(self,name):return Path('/fixture')/name


class AgentCameraSocketUnitTests(unittest.TestCase):
    def setUp(self):self.config=UnitConfig(json.loads((ROOT/'config.example.json').read_text()))

    def test_robot_agent_unit_preserves_private_tmp_and_other_sandbox_constraints(self):
        unit=service_unit(self.config,'robot','agent')
        parsed=configparser.ConfigParser(interpolation=None,strict=False)
        parsed.read_string(unit);service=parsed['Service']
        for key,value in (('PrivateTmp','yes'),('NoNewPrivileges','yes'),('ProtectSystem','strict'),
                ('ProtectHome','read-only'),('UMask','0077'),('KillMode','control-group')):
            self.assertEqual(service[key],value)
        self.assertEqual(service['BindReadOnlyPaths'],'/tmp/reachymini_camera_socket')
        self.assertNotIn('BindPaths',service)
        self.assertEqual(service['ReadWritePaths'],str(self.config.path(self.config['paths']['data_dir'])))
        self.assertEqual(unit.count(BIND),1)
        self.assertNotIn('PrivateTmp=no',unit)

    def test_only_agent_gets_one_exact_socket_binding_no_optional_or_wildcard_path(self):
        for role,group in (('hub','hub'),('hub','voice'),('worker','worker'),('robot','worker'),('hub','agent')):
            with self.subTest(role=role,group=group):
                unit=service_unit(self.config,role,group)
                self.assertNotIn('BindReadOnlyPaths=',unit)
                self.assertIn('PrivateTmp=yes\n',unit)
        line=next(line for line in service_unit(self.config,'robot','agent').splitlines() if line.startswith('BindReadOnlyPaths='))
        self.assertEqual(line,BIND.rstrip('\n'))  # No '-' optional source or broader /tmp grant.

    def test_dropin_contains_only_same_socket_bind_and_cannot_reset_other_settings(self):
        raw=DROPIN.read_text()
        self.assertEqual(raw,'[Service]\n'+BIND)
        parsed=configparser.ConfigParser(interpolation=None,strict=True);parsed.read_string(raw)
        self.assertEqual(parsed.sections(),['Service'])
        self.assertEqual(dict(parsed['Service']),dict(bindreadonlypaths='/tmp/reachymini_camera_socket'))
        self.assertNotIn('PrivateTmp=',raw);self.assertNotIn('ReadWritePaths=',raw)
        self.assertNotIn('-/tmp',raw);self.assertNotIn('*',raw)

    def test_generation_changes_no_existing_unit_bytes_except_agent_socket_line(self):
        old=subprocess.check_output(['git','show','5e9f940ad2db637e82aba51dab04f7df85d611ee:src/reachy_companion/deployment.py'],cwd=ROOT)
        module=types.ModuleType('prior_unit_generation');exec(compile(old,'prior_deployment.py','exec'),module.__dict__)
        for role,group in (('robot','agent'),('hub','hub'),('hub','voice'),('worker','worker')):
            before=module.service_unit(self.config,role,group);after=service_unit(self.config,role,group)
            if role=='robot':self.assertEqual(after.replace(BIND,''),before)
            else:self.assertEqual(after,before)

    def test_existing_root_validation_still_rejects_unit_escape(self):
        for root in ('/fixture with space','/fixture%name','/fixture"name','/fixture\\name','/fixture\nRootDirectory=/'):
            self.config['deployment']['robot']['root']=root
            with self.subTest(root=root),self.assertRaises(ValueError):service_unit(self.config,'robot','agent')


if __name__=='__main__':unittest.main()
