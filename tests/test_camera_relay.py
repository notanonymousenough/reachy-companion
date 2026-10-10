from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from reachy_companion.autonomous.camera_relay import CameraRelay


class CameraShutdownTests(unittest.TestCase):
    def test_unknown_shutdown_preserves_socket_for_owner_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            relay=CameraRelay.__new__(CameraRelay)
            relay.path=Path(directory)/'camera.sock';relay.path.touch()
            relay.Gst=SimpleNamespace(State=SimpleNamespace(NULL='null'),SECOND=1)
            relay.pipeline=SimpleNamespace(set_state=lambda state:None,
                                           get_state=lambda timeout:(None,'playing',None))
            with self.assertRaises(RuntimeError):relay.close()
            self.assertTrue(relay.path.exists())
            relay.pipeline.get_state=lambda timeout:(None,'null',None)
            relay.close()
            self.assertFalse(relay.path.exists())


if __name__=='__main__':unittest.main()
