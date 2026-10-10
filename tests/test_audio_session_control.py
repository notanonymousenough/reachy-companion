import json
from pathlib import Path
import subprocess
import sys
import tempfile
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

    def test_client_rejects_a_stop_acknowledgement_for_another_owner(self):
        client=SessionClient('http://127.0.0.1:1','t'*32,'controller')
        client._request=lambda *args:dict(controller='controller',source_boot='source',session_boot='old-session',stop_requested=True)
        with self.assertRaises(ValueError):client.stop('current-session','source')

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
            peer_status=dict(source_boot='source',closed=True,watch_execution_busy=False,operator_execution_busy=False),
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

    def test_actual_agent_cancel_requires_explicit_drained_control_slots(self):
        hub,device=self.receipts();hub['cancel_kind']='actual_agent'
        self.assertFalse(self.audit(hub,device)['receipt_cleanup_verified'])
        hub['execution_busy']['agent_cancel']=False;device['peer_status']['operator_control_execution_busy']=False
        self.assertTrue(self.audit(hub,device)['receipt_cleanup_verified'])
        hub['accepted']=True
        self.assertFalse(self.audit(hub,device)['voice_acceptance'])
        device['accepted']=True
        self.assertTrue(self.audit(hub,device)['voice_acceptance'])
        device['peer_status']['operator_control_execution_busy']=True
        self.assertFalse(self.audit(hub,device)['receipt_cleanup_verified'])
        hub['execution_busy']=None
        self.assertFalse(self.audit(hub,device)['receipt_cleanup_verified'])

    def test_cleanup_cli_exit_status_reflects_final_proof_without_live_admission(self):
        root=Path(__file__).resolve().parents[1];hub,device=self.receipts()
        with tempfile.TemporaryDirectory() as directory:
            hub_path=Path(directory)/'hub.json';device_path=Path(directory)/'device.json'
            hub_path.write_text(json.dumps(hub));device_path.write_text(json.dumps(device))
            command=[sys.executable,str(root/'deploy/autonomous/realtime_audio_control.py'),'check-cleanup',
                '--controller','controller','--session-boot','session','--source-boot','source',
                '--hub-receipt',str(hub_path),'--device-receipt',str(device_path)]
            good=subprocess.run(command,cwd=root,text=True,capture_output=True,timeout=5)
            self.assertEqual(good.returncode,0,good.stderr)
            result=json.loads(good.stdout);self.assertTrue(result['receipt_cleanup_verified'])
            self.assertFalse(result['live_readiness_verified']);self.assertFalse(result['voice_acceptance'])
            hub['execution_busy']['main']=True;hub_path.write_text(json.dumps(hub))
            busy=subprocess.run(command,cwd=root,text=True,capture_output=True,timeout=5)
            self.assertEqual(busy.returncode,2,busy.stderr)
            self.assertFalse(json.loads(busy.stdout)['receipt_cleanup_verified'])

    def test_unknown_receipts_busy_slots_and_missing_proof_prevent_cleanup_claim(self):
        for section in ('hub_busy','device_capture','device_stop','watch','mic_owner','datagram','context','missing_slot','foreign_peer','invalid_epoch','transport','tcp_udp_busy'):
            hub,device=self.receipts()
            if section=='hub_busy':hub['execution_busy']['main']=True
            elif section=='device_capture':device.pop('capture_closed')
            elif section=='device_stop':device['playback']['stop_known']=False
            elif section=='watch':device['peer_status']['watch_execution_busy']=True
            elif section=='mic_owner':device['operator_after'].pop('microphone_owner_present')
            elif section=='datagram':device.pop('lease_datagram_execution_busy')
            elif section=='context':hub['context_enabled']=True
            elif section=='missing_slot':hub['execution_busy'].pop('context_terminal_revoke')
            elif section=='foreign_peer':device['peer_status']['source_boot']='old-source'
            elif section=='invalid_epoch':device['operator_after']['microphone_epoch']=-1
            elif section=='transport':hub.pop('lease_transport')
            else:hub['lease_transport']='tcp';device['lease_datagram_execution_busy']=True
            self.assertFalse(self.audit(hub,device)['receipt_cleanup_verified'],section)
