"""Add one namespaced workflow to an existing n8n; no restarts or bulk changes.
REST routes are version-specific: audited against installed n8n2.32.0.
Owner setup is explicit via --owner-email; credentials remain remote-only0600.
"""
import argparse
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import secrets
from urllib.request import Request, build_opener, ProxyHandler


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:5678')
    parser.add_argument('--owner-email')
    args=parser.parse_args()
    os.umask(0o077)
    root=Path(__file__).resolve().parent
    admin=root/'admin.local.json'
    state=json.loads(admin.read_text()) if admin.exists() else {}
    opener=build_opener(ProxyHandler({}))
    def call(method,path,data=None):
        headers={'Content-Type':'application/json'}
        if state.get('cookie'): headers['Cookie']=state['cookie']
        request=Request(args.base_url.rstrip('/')+path,data=None if data is None else json.dumps(data).encode(),headers=headers,method=method)
        with opener.open(request,timeout=10) as response:
            cookie=SimpleCookie(); cookie.load(response.headers.get('Set-Cookie',''))
            if cookie:
                state['cookie']='; '.join(k+'='+v.value for k,v in cookie.items())
                admin.write_text(json.dumps(state))
            body=json.load(response)
        return body.get('data',body)
    settings=call('GET','/rest/settings')
    if settings.get('userManagement',{}).get('showSetupOnFirstLoad'):
        if not args.owner_email: raise ValueError('Owner not configured; explicit --owner-email required')
        state.update(email=args.owner_email,password=secrets.token_urlsafe(32)+'aA1!')
        admin.write_text(json.dumps(state))
        call('POST','/rest/owner/setup',dict(email=state['email'],firstName='Reachy',lastName='Operator',password=state['password']))
    elif not state.get('cookie'):
        raise ValueError('Existing owner: provide authorized session in remote admin.local.json; no reset')
    env=root/'.env'
    if env.exists(): values=dict(line.split('=',1) for line in env.read_text().splitlines() if '=' in line)
    else:
        values={k:secrets.token_hex(32) for k in ('WORKFLOW_WEBHOOK_TOKEN','WORKFLOW_BROKER_TOKEN')}
        with env.open('x') as file:file.write(''.join(k+'='+v+'\n' for k,v in values.items()))
    if not state.get('credential_id'):
        credential=call('POST','/rest/credentials',dict(name='Reachy companion webhook only',type='httpHeaderAuth',data={'name':'X-Companion-Token','value':values['WORKFLOW_WEBHOOK_TOKEN']}))
        state['credential_id']=credential['id']; admin.write_text(json.dumps(state))
    if not state.get('workflow_id'):
        workflow=json.loads((root/'synthetic-echo.json').read_text())
        for node in workflow['nodes']:
            if 'credentials' in node: node['credentials']['httpHeaderAuth']['id']=state['credential_id']
        workflow={k:workflow[k] for k in ('name','nodes','connections','settings')}
        created=call('POST','/rest/workflows',workflow)
        state.update(workflow_id=created['id'],version_id=created['versionId']);admin.write_text(json.dumps(state))
    workflow=call('GET','/rest/workflows/'+state['workflow_id'])
    if not workflow.get('active'):
        call('POST','/rest/workflows/'+state['workflow_id']+'/activate',dict(versionId=workflow['versionId']))
    print(json.dumps({'workflow_id':state['workflow_id'],'capability':'workflow.synthetic_echo','secrets_displayed':False}))


if __name__=='__main__':main()
