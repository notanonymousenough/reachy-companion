import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from reachy_companion.autonomous.audio_session_control import create_server,SessionClient,cleanup_receipts


class ControlTests(unittest.TestCase):
    def server(self):
        stop=threading.Event();server=create_server('t'*32,'controller','source',stop,lambda:dict(stage='startup'),port=0)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        client=SessionClient('http://127.0.0.1:'+str(server.server_address[1]),'t'*32,'controller')
        return server,client,stop

    def test_stop_is_owner_fenced_and_acknowledges_only_request(self):
        server,client,stop=self.server();status=client.status()
        self.assertEqual(status['source_boot'],'source');self.assertEqual(status['controller'],'controller')
        for session,source in (('old-session','source'),(status['session_boot'],'old-source')):
            with self.assertRaises(HTTPError):client.stop(session,source)
            self.assertFalse(stop.is_set())
        result=client.stop(status['session_boot'],'source')
        self.assertTrue(result['stop_requested']);self.assertNotIn('stop_known',result)
        self.assertTrue(stop.is_set());self.assertTrue(client.status()['stop_requested'])

    def test_new_session_rejects_old_stop_even_with_same_controller_and_source(self):
        old,client,_=self.server();binding=client.status()
        new,client,stop=self.server()
        self.assertNotEqual(old.session_binding,new.session_binding)
        with self.assertRaises(HTTPError):client.stop(binding['session_boot'],'source')
        self.assertFalse(stop.is_set())
        body=dict(new.session_binding,extra='unknown')
        with self.assertRaises(HTTPError):
            urlopen(Request(client.url+'/stop',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+'t'*32}),timeout=1)
        wrong=SessionClient(client.url,'u'*32,'controller')
        with self.assertRaises(HTTPError):wrong.status()

    def receipts(self):
        hub=dict(controller='controller',session_boot='session',source_boot='source',hub_boot_id='hub',context_enabled=False,
            accepted=False,lease_transport='udp',peer_stop_execution_busy=False,peer_stop=dict(stop_known=True,execution_busy=False),
            execution_busy={key:False for key in ('fast','main','audio','speech','peer_poll','lease','context','context_revoke','context_terminal_revoke')})
        device=dict(controller='controller',source_boot='source',capture_closed=True,microphone_restored=True,
            lease_datagram_execution_busy=False,playback=dict(stop_known=True,execution_busy=False),
            peer_status=dict(closed=True,watch_execution_busy=False,operator_execution_busy=False),
            operator_after=dict(agent_boot_id='agent',microphone_epoch=2,microphone_enabled=False,capture_active=False,
                phase='paused',microphone_state_error=None,microphone_owner_present=False))
        return hub,device

    def audit(self,hub,device):return cleanup_receipts(hub,device,controller='controller',session_boot='session',source_boot='source')

    def test_receipt_cleanup_is_separate_from_voice_acceptance_and_live_readiness(self):
        result=self.audit(*self.receipts())
        self.assertTrue(result['receipt_cleanup_verified']);self.assertFalse(result['voice_acceptance'])
        self.assertFalse(result['live_readiness_verified']);self.assertFalse(result['resume_allowed'])
        hub,device=self.receipts();device['source_boot']='other'
        with self.assertRaises(ValueError):self.audit(hub,device)

    def test_unknown_receipts_busy_slots_and_missing_proof_prevent_cleanup_claim(self):
        for section in ('hub_busy','device_capture','device_stop','watch','mic_owner','datagram','context','missing_slot'):
            hub,device=self.receipts()
            if section=='hub_busy':hub['execution_busy']['main']=True
            elif section=='device_capture':device.pop('capture_closed')
            elif section=='device_stop':device['playback']['stop_known']=False
            elif section=='watch':device['peer_status']['watch_execution_busy']=True
            elif section=='mic_owner':device['operator_after'].pop('microphone_owner_present')
            elif section=='datagram':device.pop('lease_datagram_execution_busy')
            elif section=='context':hub['context_enabled']=True
            else:hub['execution_busy'].pop('context_terminal_revoke')
            self.assertFalse(self.audit(hub,device)['receipt_cleanup_verified'],section)
