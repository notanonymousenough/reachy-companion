import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'deploy/autonomous/robot_inventory.py'
spec=importlib.util.spec_from_file_location('robot_inventory_test',SOURCE)
inventory=importlib.util.module_from_spec(spec);spec.loader.exec_module(inventory)


class RobotInventoryTests(unittest.TestCase):
    def test_fixed_roles_never_export_unknown_script_or_arguments(self):
        self.assertEqual(inventory.process_hint([b'python',b'-u',b'-m',b'reachy_companion',b'--config',b'/private/config',b'agent',b'serve',b'']), 'companion_agentserve')
        self.assertEqual(inventory.process_hint([b'python',b'/venvs/bin/reachy-mini-daemon',b'private']), 'factory_reachy_mini_daemon')
        self.assertEqual(inventory.process_hint([b'python',b'/private/user-script.py',b'private']), 'unknown_python_entrypoint')
    def test_file_only_pcm_inventory_reports_shared_plugin_without_cursor_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'.asoundrc').write_text('pcm.other { type hw rate 48000 }\npcm.reachymini_audio_sink {\n type dmix\n slave { pcm "hw:0,0" rate 16000 channels 2 }\n}\n')
            status=root/'proc/card0/pcm0p/sub0';status.mkdir(parents=True)
            (status/'status').write_text('state: RUNNING\nowner_pid : 123\nhw_ptr : 42\n')
            value=inventory.pcm_inventory({'audio':{'playback_device':'plug:reachymini_audio_sink'}},root,root/'proc')
            self.assertEqual(value['sink_type'],'dmix');self.assertEqual(value['slave_rate'],16000)
            self.assertEqual(value['slave_channels'],2);self.assertEqual(value['audio_open_attempts'],0)
            self.assertEqual(value['playback_streams'],[dict(state='RUNNING',owner_pid=123)])
            self.assertFalse(value['cursor_verified']);self.assertFalse(value['exclusive_writer_verified'])
