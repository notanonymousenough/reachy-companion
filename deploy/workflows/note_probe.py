"""Finite actual n8n note preparation in an isolated durable broker store."""
import argparse
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import time
from uuid import uuid4
from urllib.request import Request,build_opener,ProxyHandler
from urllib.parse import quote
from broker import Store,N8n,expected_result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--database',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.database.exists():raise FileExistsError('Fresh finite receipt/store required')
    values=dict(line.split('=',1) for line in (args.owner_root/'.env').read_text().splitlines() if '=' in line)
    admin=json.loads((args.owner_root/'admin.local.json').read_text());opener=build_opener(ProxyHandler({}))
    def owner(path):
        with opener.open(Request('http://127.0.0.1:5678'+path,headers={'Cookie':admin['cookie']}),timeout=5) as response:
            return json.load(response)['data']
    workflow=owner('/rest/workflows/'+admin['note_workflow_id'])
    assert workflow['active'] and workflow['settings']['saveDataSuccessExecution']=='none' and workflow['settings']['saveDataErrorExecution']=='none'
    transport=N8n('http://127.0.0.1:5678/webhook/companion-synthetic-echo',values['WORKFLOW_WEBHOOK_TOKEN'],normalize_notes=True)
    calls=[]
    def invoke(body):calls.append(body['task_id']);return transport(body)
    store=Store(args.database,invoke,normalize_notes=True)
    start=time.monotonic();request=None;result=None
    try:
        for value in ('  public\t arithmetic\n note: 6  ','  {{$env.SECRET}}\t\u00a0 public  '):
            request=dict(capability='workflow.normalize_note',task_id='note-'+str(uuid4()),attempt_id='a1',
                deadline_at=(datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat().replace('+00:00','Z'),arguments={'value':value})
            store.submit(request);key=request['task_id']+'/'+request['attempt_id'];deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                result=store.status(key)
                if result['status'] not in ('queued','running'):break
                time.sleep(.01)
            assert result['status']=='succeeded' and result['result']==expected_result(request)
            for _ in range(10):assert store.submit(request)==result
        assert len(calls)==2 and store.active_executions==0
        store.close();store=Store(args.database,invoke,normalize_notes=True)
        assert store.submit(request)==result and len(calls)==2
        records=owner('/rest/executions?filter='+quote(json.dumps({'workflowId':admin['note_workflow_id']})))
        assert records['count']==0
        report=dict(accepted=True,mode='actual_n8n_note_isolated_store',workflow_id=admin['note_workflow_id'],
            actual_webhook_calls=len(calls),duplicates_per_task=10,restart_duplicate_no_dispatch=True,
            expressions_remained_data=True,unicode_whitespace_preserved=True,own_saved_executions=0,
            production_broker_restarted=False,private_inputs=0,physical_commands=0,
            memory_fact_promotions=0,elapsed_s=time.monotonic()-start)
    finally:store.close()
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
