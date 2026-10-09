"""Finite VPS verification: repeat an existing task; credentials never displayed."""
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.request import Request,urlopen
from urllib.parse import quote


def main():
    root=Path(__file__).resolve().parent
    values=dict(line.split('=',1) for line in (root/'.env').read_text().splitlines() if '=' in line)
    state=json.loads((root/'admin.local.json').read_text())
    def broker_call(path,body=None):
        request=Request('http://127.0.0.1:15679'+path,data=None if body is None else json.dumps(body).encode(),
                        headers={'Authorization':'Bearer '+values['WORKFLOW_BROKER_TOKEN'],'Content-Type':'application/json'})
        with urlopen(request,timeout=5) as response:return json.load(response)
    def admin_call(path):
        request=Request('http://127.0.0.1:5678'+path,headers={'Cookie':state['cookie']})
        with urlopen(request,timeout=5) as response:return json.load(response)['data']
    health=broker_call('/health');assert health['ok'] and not health['controls']
    smoke=json.loads((root/'smoke.local.json').read_text())
    restored=broker_call(smoke['path'])
    assert restored['status'] in ('succeeded','expired')
    assert broker_call('/tasks',smoke['request'])['status']==restored['status']
    workflow=admin_call('/rest/workflows/'+state['workflow_id'])
    assert workflow['active']
    assert workflow['settings']['saveDataSuccessExecution']=='none'
    assert workflow['settings']['saveDataErrorExecution']=='none'
    records=admin_call('/rest/executions?filter='+quote(json.dumps({'workflowId':state['workflow_id']})))
    container=json.loads(subprocess.check_output(['sudo','-n','docker','inspect','reachy-workflows-broker-1']))[0]
    assert container['HostConfig']['Memory']==96*1024*1024
    assert all(x['HostIp']=='127.0.0.1' for x in container['HostConfig']['PortBindings']['8080/tcp'])
    report=dict(workflow_id=state['workflow_id'],active=True,payload_retention='disabled',
                own_saved_executions=records['count'],persistent_duplicate_status=restored['status'],
                broker_memory_limit_mb=96,broker_loopback_only=True,
                broker_source_sha256=hashlib.sha256((root/'broker.py').read_bytes()).hexdigest())
    print(json.dumps(report))


if __name__=='__main__':main()
