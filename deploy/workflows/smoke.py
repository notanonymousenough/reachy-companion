"""Live synthetic echo plus isolated fault injection; secrets never printed.
Run on VPS from companion project. Never stops n8n or invokes controls/API/export.
"""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler
from uuid import uuid4
from broker import Store,N8n


def main():
    values=dict(line.split('=',1) for line in Path('.env').read_text().splitlines() if '=' in line)
    opener=build_opener(ProxyHandler({}));base='http://127.0.0.1:15679'
    def call(path,body=None,authenticated=True):
        headers={'Content-Type':'application/json'}
        if authenticated:headers['Authorization']='Bearer '+values['WORKFLOW_BROKER_TOKEN']
        request=Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        with opener.open(request,timeout=5) as response:return json.load(response)
    def body(ttl=5):
        return dict(capability='workflow.synthetic_echo',task_id='smoke-'+str(uuid4()),attempt_id='a1',
                    deadline_at=(datetime.now(timezone.utc)+timedelta(seconds=ttl)).isoformat().replace('+00:00','Z'),arguments={'value':'synthetic-no-controls'})
    def poll(store,key,status):
        end=time.monotonic()+5
        while time.monotonic()<end:
            result=store.status(key)
            if result['status']==status:return result
            time.sleep(.01)
        raise AssertionError((status,result['status']))
    try:call('/health',authenticated=False);raise AssertionError('unauthenticated access')
    except HTTPError as error:assert error.code==401
    health=call('/health');assert health['ok'] and not health['controls']
    request=body();call('/tasks',request)
    path='/tasks/'+request['task_id']+'/'+request['attempt_id']
    end=time.monotonic()+5
    while time.monotonic()<end:
        result=call(path)
        if result['status'] not in ('queued','running'):break
        time.sleep(.05)
    assert result['status']=='succeeded',result['status']
    assert result['result']['value']=='synthetic-no-controls'
    for i in range(10):assert call('/tasks',request)['status']=='succeeded'
    try:call('/tasks',{**request,'arguments':{'value':'conflict'}});raise AssertionError('conflict accepted')
    except HTTPError as error:assert error.code==409
    # Actual n8n transport, with a delayed result in an isolated local store.
    n8n=N8n('http://127.0.0.1:5678/webhook/companion-synthetic-echo',values['WORKFLOW_WEBHOOK_TOKEN'])
    try:
        with opener.open(Request('http://127.0.0.1:5678/webhook/companion-synthetic-echo',data=b'{}',headers={'Content-Type':'application/json'}),timeout=3):
            raise AssertionError('unauthenticated webhook')
    except HTTPError as error:assert error.code==403 or error.code==401
    def delayed(value):
        output=n8n(value);time.sleep(.2);return output
    with tempfile.TemporaryDirectory() as tmp:
        late=Store(Path(tmp)/'late.sqlite',delayed)
        value=body(ttl=.05);late.submit(value);key=value['task_id']+'/'+value['attempt_id']
        assert poll(late,key,'expired')['result'] is None
        late.close()
        outage=Store(Path(tmp)/'outage.sqlite',N8n('http://127.0.0.1:1/absent',values['WORKFLOW_WEBHOOK_TOKEN']))
        value=body();outage.submit(value);key=value['task_id']+'/'+value['attempt_id']
        assert poll(outage,key,'execution_unknown')['result'] is None
        assert outage.quarantined
        outage.close()
    Path('smoke.local.json').write_text(json.dumps({'request':request,'path':path}))
    print(json.dumps({'live_n8n_round_trip':'PASS','duplicates':10,'conflict':'PASS','broker_auth':'PASS',
                      'webhook_auth':'PASS','late_actual_result_isolated_store':'PASS','outage_transport_isolated_store':'PASS',
                      'task_id':request['task_id'],'actuators':False,'export':False,'paid_api':False}))


if __name__=='__main__':main()
