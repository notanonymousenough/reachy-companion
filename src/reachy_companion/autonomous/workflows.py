"""Optional typed broker client. Endpoint/credential never come from model output."""
from datetime import datetime, timezone, timedelta
import json
import os
import re
import time
from urllib.request import Request, build_opener, ProxyHandler
from .contracts import decode


class WorkflowClient:
    def __init__(self, config):
        if not config['enabled'] or not config['broker_url']:
            raise ValueError('Optional workflow broker disabled/unconfigured')
        self.config=config
        self.capability=config.get('capability','workflow.synthetic_echo')
        if self.capability not in ('workflow.synthetic_echo','workflow.normalize_note'):raise ValueError('Static workflow capability required')
        self.token=os.environ.get(config['token_env'],'')
        if len(self.token)<32: raise ValueError('Workflow auth missing')
        self.opener=build_opener(ProxyHandler({}))
    def call(self,path,body=None):
        request=Request(self.config['broker_url'].rstrip('/')+path,
                        data=None if body is None else json.dumps(body).encode(),
                        headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with self.opener.open(request,timeout=self.config['http_timeout_s']) as response:
            raw=response.read(8193)
        if len(raw)>8192: raise ValueError('Workflow result cap')
        return decode(raw)
    def run(self,task):
        remaining=min(60,max(0,task.deadline-time.monotonic()))
        if remaining<=0: raise TimeoutError('task already expired')
        if len(task.prompt)>256: raise ValueError('synthetic argument cap')
        expected_value=task.prompt
        if self.capability=='workflow.normalize_note':
            expected_value=re.sub(r'[ \t\r\n]+',' ',task.prompt.strip(' \t\r\n'))
            if not expected_value:raise ValueError('Empty note')
        deadline=datetime.now(timezone.utc)+timedelta(seconds=remaining)
        body=dict(capability=self.capability,task_id=task.task_id,attempt_id=task.attempt_id,
                  deadline_at=deadline.isoformat().replace('+00:00','Z'),arguments={'value':task.prompt})
        path='/tasks/'+task.task_id+'/'+task.attempt_id
        result=self.call('/tasks',body)
        while time.monotonic()<task.deadline:
            if result['task_id']!=task.task_id or result['attempt_id']!=task.attempt_id:
                raise ValueError('Workflow authority mismatch')
            if result['status']=='succeeded':
                output=result['result']
                if output != dict(task_id=task.task_id,attempt_id=task.attempt_id,value=expected_value):
                    raise ValueError('Workflow result schema mismatch')
                return output['value']
            if result['status'] not in ('queued','running'): raise RuntimeError('Workflow terminal '+result['status'])
            time.sleep(self.config['poll_s'])
            result=self.call(path)
        # Cooperative cancellation suppresses acceptance, not an execution-stop ACK.
        try:self.call(path+'/cancel',{})
        except Exception:pass
        raise TimeoutError('workflow deadline')
