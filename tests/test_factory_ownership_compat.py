import io
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

from reachy_companion.hub import Hub


class FactoryOwnershipCompatibilityTests(unittest.TestCase):
    def hub(self, current):
        hub=Hub({'network':{'robot_url':'http://127.0.0.1:8000'},'timeouts':{'robot':1}})
        hub.http=Mock()
        hub.http.open.side_effect=[HTTPError('http://factory',404,'missing',{},None),io.BytesIO(current)]
        return hub

    def test_new_factory_without_running_app_is_free(self):
        hub=self.hub(b'null')
        self.assertEqual(hub.factory('/api/daemon/robot-app-lock-status'),{'state':'free','app':None})
        self.assertTrue(hub.http.open.call_args.args[0].full_url.endswith('/api/apps/current-app-status'))

    def test_running_app_is_never_reclassified_as_free(self):
        self.assertEqual(self.hub(b'{"name":"other"}').factory('/api/daemon/robot-app-lock-status')['state'],'locked')

    def test_transport_or_server_failure_does_not_claim_free_robot(self):
        hub=self.hub(b'null')
        hub.http.open.side_effect=HTTPError('http://factory',503,'unavailable',{},None)
        with self.assertRaises(HTTPError):hub.factory('/api/daemon/robot-app-lock-status')
        self.assertEqual(hub.http.open.call_count,1)
