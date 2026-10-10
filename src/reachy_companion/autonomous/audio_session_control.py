"""Owner-fenced status/stop for one finite Hub session; no device-start API."""
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading
from urllib.request import Request
from .audio_peer import PeerClient
from .contracts import decode,uid


def create_server(token,controller,source_boot,stop,read_status,*,port=8790):
    if (len(token)<32 or not isinstance(controller,str) or not 1<=len(controller)<=128
            or not isinstance(source_boot,str) or not 1<=len(source_boot)<=128):
        raise ValueError('Owned session control required')
    session_boot=uid();slots=threading.BoundedSemaphore(2)
    binding=dict(controller=controller,source_boot=source_boot,session_boot=session_boot)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup();self.connection.settimeout(.5)
        def log_message(self,*args):pass
        def reply(self,status,value):
            payload=json.dumps(value).encode()
            self.send_response(status);self.send_header('Content-Length',str(len(payload)))
            self.send_header('Content-Type','application/json');self.end_headers()
            try:self.wfile.write(payload)
            except OSError:pass
        def authorized(self):
            if hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):return True
            self.reply(401,dict(error='unauthorized'));return False
        def do_GET(self):
            if not self.authorized():return
            if self.path!='/status':self.reply(404,{});return
            self.reply(200,{**read_status(),**binding, 'stop_requested':stop.is_set()})
        def do_POST(self):
            if not self.authorized():return
            if self.path!='/stop':self.reply(404,{});return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 1<=size<=4096:raise ValueError('Bounded stop envelope')
                body=decode(self.rfile.read(size))
                if body!=binding:raise ValueError('Session stop owner mismatch')
            except Exception:self.reply(409,dict(error='invalid_or_stale_session'));return
            stop.set()
            # Admission acknowledgement is never a physical stop receipt.
            self.reply(202,dict(stop_requested=True,**binding))
    class Server(ThreadingHTTPServer):
        daemon_threads=True
        def process_request(self,request,address):
            if not slots.acquire(False):request.close();return
            try:super().process_request(request,address)
            except BaseException:slots.release();raise
        def process_request_thread(self,request,address):
            try:super().process_request_thread(request,address)
            finally:slots.release()
    server=Server(('127.0.0.1',port),Handler);server.session_binding=binding
    return server


class SessionClient(PeerClient):
    def _request(self,path,body=None):
        request=Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers={
            'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with self.opener.open(request,timeout=self.timeout) as response:raw=response.read(65537)
        if len(raw)>65536:raise ValueError('Bounded session receipt')
        return decode(raw)
    def status(self):return self._request('/status')
    def stop(self,session_boot,source_boot):
        binding=dict(controller=self.controller,session_boot=session_boot,source_boot=source_boot)
        result=self._request('/stop',binding)
        if result!=dict(stop_requested=True,**binding) or result.get('stop_requested') is not True:
            raise ValueError('Session stop acknowledgement mismatch')
        return result


def cleanup_receipts(hub,device,*,controller,session_boot,source_boot):
    """Audit finite receipts only. Live readiness remains a separate owner check."""
    if any(not isinstance(value,str) or not 1<=len(value)<=128 for value in (controller,session_boot,source_boot)):
        raise ValueError('Explicit cleanup owner scope')
    if (hub.get('controller')!=controller or device.get('controller')!=controller
            or hub.get('session_boot')!=session_boot or hub.get('source_boot')!=source_boot
            or device.get('source_boot')!=source_boot):raise ValueError('Cleanup receipt owner mismatch')
    errors=[]
    busy=hub.get('execution_busy')
    if (not isinstance(busy,dict) or not {'fast','main','audio','speech','peer_poll','lease','context','context_revoke','context_terminal_revoke'}<=set(busy)
            or any(type(value) is not bool or value for value in busy.values())):errors.append('hub_execution_busy_or_unknown')
    if (hub.get('peer_stop_execution_busy') is not False or hub.get('peer_stop',{}).get('stop_known') is not True
            or hub.get('peer_stop',{}).get('execution_busy') is not False):
        errors.append('hub_physical_stop_unknown')
    if type(hub.get('context_enabled')) is not bool:errors.append('context_configuration_unknown')
    if hub.get('context_enabled'):
        revoke=hub.get('context_terminal_revoke',{}).get('output',{})
        if (revoke.get('revoked') is not True or revoke.get('terminal') is not True
                or not isinstance(hub.get('hub_boot_id'),str) or revoke.get('hub_boot_id')!=hub['hub_boot_id']):
            errors.append('context_terminal_revoke_unknown')
    if hub.get('context_terminal_revoke_unknown'):errors.append('context_revoke_unknown')
    if device.get('capture_closed') is not True:errors.append('device_capture_unknown')
    playback=device.get('playback',{})
    if playback.get('stop_known') is not True or playback.get('execution_busy') is not False:errors.append('device_stop_unknown')
    peer=device.get('peer_status',{})
    actual_cancel=hub.get('cancel_kind')=='actual_agent'
    if actual_cancel and (not isinstance(busy,dict) or 'agent_cancel' not in busy or 'operator_control_execution_busy' not in peer):
        errors.append('agent_cancel_occupancy_unknown')
    if (peer.get('source_boot')!=source_boot or peer.get('closed') is not True or peer.get('watch_execution_busy') is not False
            or peer.get('operator_execution_busy') is not False
            or peer.get('operator_control_execution_busy',False) is not False):
        errors.append('device_owner_busy_or_unknown')
    if hub.get('lease_transport') not in ('tcp','udp'):errors.append('lease_transport_unknown')
    if (hub.get('lease_transport')=='udp' or 'lease_datagram_execution_busy' in device) and device.get('lease_datagram_execution_busy') is not False:
        errors.append('device_datagram_busy')
    operator=device.get('operator_after',{})
    if (device.get('microphone_restored') is not True or operator.get('microphone_enabled') is not False
            or operator.get('capture_active') is not False or operator.get('phase')!='paused'
            or 'microphone_state_error' not in operator or operator['microphone_state_error'] is not None
            or operator.get('microphone_owner_present') is not False
            or not isinstance(operator.get('agent_boot_id'),str) or not 1<=len(operator['agent_boot_id'])<=256
            or type(operator.get('microphone_epoch')) is not int or not 0<=operator['microphone_epoch']<2**63):
        errors.append('operator_cleanup_unknown')
    return dict(receipt_cleanup_verified=not errors,errors=errors,controller=controller,session_boot=session_boot,
        source_boot=source_boot,live_readiness_verified=False,voice_acceptance=hub.get('accepted') is True
            and (not actual_cancel or device.get('accepted') is True),
        resume_allowed=False)
