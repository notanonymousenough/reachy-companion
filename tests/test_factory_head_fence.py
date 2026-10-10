import asyncio
import unittest
from reachy_companion.autonomous.factory_head_fence import FactoryReadOnlyASGI,install_backend_read_fence,READ_PATHS


class FactoryFenceTests(unittest.TestCase):
    def test_rest_post_unknown_get_and_all_websockets_never_reach_original_routes(self):
        reached=[]
        async def app(scope,receive,send):reached.append(scope)
        fence=FactoryReadOnlyASGI(app)
        async def run():
            async def receive():raise AssertionError('Denied body must not be read')
            for path in ('/api/move/goto','/api/move/stop','/api/move/ws/raw/write','/api/motors/set_mode/enabled',
                         '/api/apps/start','/api/daemon/restart','/new-mutation-route'):
                for kind,method in (('http','POST'),('http','GET'),('websocket',None)):
                    responses=[]
                    async def send(value):responses.append(value)
                    await fence(dict(type=kind,method=method,path=path),receive,send)
                    self.assertTrue(responses);self.assertEqual(responses[0].get('status',403),403)
            for path in READ_PATHS:await fence(dict(type='http',method='GET',path=path),receive,lambda _:None)
            await fence(dict(type='lifespan'),receive,lambda _:None)
        asyncio.run(run());self.assertEqual(len(reached),len(READ_PATHS)+1);self.assertEqual(fence.denied,21)
    def test_sdk_unknown_mutators_subclasses_and_rtc_jsonrpc_are_closed(self):
        calls=[]
        class Backend:
            def process_command(self,*args,**kwargs):calls.append(('command',args,kwargs))
            def _handle_webrtc_message(self,*args):calls.append(('rtc',args))
            def request_idle_reset(self,*args):calls.append(('idle',args))
            def cancel_idle_reset(self,*args):calls.append(('cancel_idle',args))
        classes={name:type(name,(),{}) for name in ('GetStateCmd','GetMotorModeCmd','GetVersionCmd')}
        proof=install_backend_read_fence(Backend,classes);backend=Backend();responses=[]
        self.assertFalse(proof['all_mutation_paths_fenced'])
        for name in ('SetTargetCmd','SetFullTargetCmd','SetTorqueCmd','StopMoveCmd','RestartDaemonCmd','NewUnknownCmd'):
            backend.process_command(type(name,(),{})(),responses.append)
        backend.process_command(type('ForgedReadSubclass',(classes['GetStateCmd'],),{})(),responses.append)
        backend._handle_webrtc_message('peer','{"jsonrpc":"2.0","method":"apps.start"}')
        backend.request_idle_reset();backend.cancel_idle_reset();self.assertFalse(calls);self.assertEqual(len(responses),7)
        for cls in classes.values():backend.process_command(cls(),responses.append,peer_id='peer')
        self.assertEqual(len(calls),3)
        with self.assertRaises(ValueError):install_backend_read_fence(Backend,classes)


if __name__=='__main__':unittest.main()
