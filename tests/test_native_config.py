import json
from pathlib import Path
import tempfile
import unittest
from reachy_companion.autonomous.native_config import load


class NativeOwnerConfigTests(unittest.TestCase):
    def test_default_off_continuous_optin_and_path_port_bounds(self):
        example=Path(__file__).resolve().parents[1]/'config.native-motion.example.json'
        value=load(example);self.assertFalse(value['enabled'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owner.json'
            for patch in ({'version':True},{'port':80},{'socket_path':'relative.sock'},{'duration_s':301},{'enabled':1}):
                path.write_text(json.dumps(dict(value,**patch)))
                with self.assertRaises(ValueError):load(path)
            path.write_text(json.dumps(dict(value,enabled=True,duration_s=0)))
            self.assertEqual(load(path)['duration_s'],0)


if __name__=='__main__':unittest.main()
