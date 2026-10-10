import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


SOURCE=Path(__file__).resolve().parents[1]/'deploy/autonomous/agent_update.py'


class PinnedAgentUpdateTests(unittest.TestCase):
    def run_update(self,root,changes,*,apply=False,change_operator=False):
        spec=importlib.util.spec_from_file_location('agent_update_test',SOURCE)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        root=Path(root).resolve();(root/'data').mkdir();(root/'data/microphone-state.json').write_text('{"enabled":false}')
        (root/'token').write_text('x'*32)
        (root/'config.local.json').write_text(json.dumps(dict(paths=dict(token_file='token',data_dir='data'),network=dict(agent_url='http://127.0.0.1:8770'))))
        calls=[];base='a'*40;target='b'*40;output=root/'receipt.json'
        def run(argv,**kwargs):
            calls.append(argv)
            if argv[:3]==['git','rev-parse','HEAD']:result=base
            elif argv[:2]==['git','rev-parse']:result=target
            elif argv[:2]==['git','diff']:result='\n'.join(changes)
            elif argv[:2]==['systemctl','show']:result='12345'
            else:result=''
            if change_operator and argv[:4]==['sudo','-n','systemctl','stop']:
                (root/'data/microphone-state.json').write_text('{"enabled":true}')
            return SimpleNamespace(returncode=0,stdout=result)
        def open_request(request,**kwargs):
            url=request.full_url
            if '/motors/' in url:value={'mode':'disabled'}
            elif '/move/' in url:value=[]
            else:value=dict(microphone_enabled=False,capture_active=False,phase='paused',volume_percent=100)
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self,*args):return json.dumps(value).encode()
            return Response()
        original_read=Path.read_bytes;original_resolve=Path.resolve
        def read(path):
            if str(path)=='/proc/12345/cmdline':return ('python\0-m\0reachy_companion\0--config\0'+str(root/'config.local.json')+'\0agent\0serve\0').encode()
            return original_read(path)
        def resolve(path,*args,**kwargs):return root if str(path)=='/proc/12345/cwd' else original_resolve(path,*args,**kwargs)
        argv=['agent_update','--production-root',str(root),'--expected-base',base,'--target',target,'--output',str(output)]
        if apply:argv.append('--apply')
        with patch('sys.argv',argv),patch.object(module,'build_opener',return_value=SimpleNamespace(open=open_request)),patch.object(module.subprocess,'run',side_effect=run),patch.object(Path,'read_bytes',read),patch.object(Path,'resolve',resolve),patch.object(module.time,'monotonic',side_effect=[0,16]):
            try:module.main();error=None
            except (RuntimeError,TimeoutError) as exc:error=exc
        return calls,error,json.loads(output.read_text()) if output.exists() else None

    def test_unexpected_active_code_cannot_stop_or_start_service(self):
        with tempfile.TemporaryDirectory() as root:
            calls,error,receipt=self.run_update(root,['src/reachy_companion/hub.py'],apply=True)
            self.assertIsInstance(error,RuntimeError)
            self.assertFalse(any(call[0]=='sudo' for call in calls))

    def test_failed_new_agent_readiness_rolls_back_pinned_base_with_mute_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            calls,error,receipt=self.run_update(root,['src/reachy_companion/agent.py'],apply=True)
            self.assertIsInstance(error,TimeoutError);self.assertTrue(receipt['rollback'])
            self.assertEqual(json.loads((Path(root)/'data/microphone-state.json').read_text()),{'enabled':False})
            self.assertIn(['git','checkout','--detach','a'*40],calls)

    def test_operator_change_withholds_recovery_start_and_never_overwrites_switch(self):
        with tempfile.TemporaryDirectory() as root:
            calls,error,receipt=self.run_update(root,['src/reachy_companion/agent.py'],apply=True,change_operator=True)
            self.assertIsInstance(error,RuntimeError);self.assertIn('recovery_start_withheld',receipt)
            self.assertFalse(any(call[:4]==['sudo','-n','systemctl','start'] for call in calls))
            self.assertTrue(json.loads((Path(root)/'data/microphone-state.json').read_text())['enabled'])


if __name__=='__main__':unittest.main()
