"""Temporary factory transport fence; no import installs or mutates anything.

Use only in a fresh pinned finite factory process with media/startup apps off.
Class patch must precede backend construction/listeners. Existing live instances
and queued producers cannot be adopted. Restoration is process replacement after
verified cleanup, not reopening a previously fenced process.
"""

READ_PATHS=frozenset(('/health-check','/api/daemon/status','/api/daemon/robot-app-lock-status',
    '/api/motors/status','/api/state/present_head_pose','/api/state/present_antenna_joint_positions',
    '/api/state/present_body_yaw','/api/state/full'))


class FactoryReadOnlyASGI:
    """Close REST and every WebSocket mutation path before the router executes."""
    def __init__(self,app):self.app=app;self.denied=0
    async def __call__(self,scope,receive,send):
        kind=scope['type']
        if kind=='lifespan':return await self.app(scope,receive,send)
        if kind=='http' and scope.get('method')=='GET' and scope.get('path') in READ_PATHS:
            return await self.app(scope,receive,send)
        self.denied+=1
        if kind=='websocket':await send(dict(type='websocket.close',code=1008))
        elif kind=='http':
            body=b'{"error":"finite_factory_transport_sealed"}'
            await send(dict(type='http.response.start',status=403,headers=[(b'content-type',b'application/json')]))
            await send(dict(type='http.response.body',body=body))
        else:raise ValueError('Unsupported ASGI scope')


def install_backend_read_fence(backend_class,command_classes):
    """Prepare class before any SDK/RTC listener starts; never detach/reopen.

    Exact parsed command types only. RTC entry is completely denied, including
    its JSON-RPC app relay bypass. No mutation/stop/reset command is whitelisted;
    the owner adapter uses its private IPC and scoped native operations instead.
    """
    if getattr(backend_class,'_finite_head_transport_sealed',False):raise ValueError('Fresh factory class required')
    required=('process_command','_handle_webrtc_message','request_idle_reset','cancel_idle_reset')
    if any(not callable(getattr(backend_class,name,None)) for name in required):raise ValueError('Pinned factory dispatch ABI required')
    names=('GetStateCmd','GetMotorModeCmd','GetVersionCmd')
    if set(command_classes)!=set(names) or any(not isinstance(value,type) for value in command_classes.values()):
        raise ValueError('Exact reviewed read command classes required')
    allowed=frozenset(command_classes.values());original=backend_class.process_command
    def process(self,cmd,send_response,peer_id=None):
        if type(cmd) not in allowed:
            send_response(dict(status='rejected',reason='finite_factory_transport_sealed'));return
        return original(self,cmd,send_response,peer_id=peer_id)
    def rtc(self,peer_id,message):return None # deny JSON-RPC and raw/typed RTC uniformly
    def idle(self,*args,**kwargs):return None # no disconnect-driven sleep/reset trajectory
    backend_class.process_command=process;backend_class._handle_webrtc_message=rtc
    backend_class.request_idle_reset=idle;backend_class.cancel_idle_reset=idle
    backend_class._finite_head_transport_sealed=True
    return dict(sdk_exact_read_allowlist=list(names),rtc_and_jsonrpc_denied=True,idle_reset_denied=True,
        fresh_process_required=True,all_mutation_paths_fenced=False) # ASGI/startup/internal producer proof still required
