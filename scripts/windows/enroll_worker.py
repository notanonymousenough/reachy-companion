"""Enroll only a just-created, stopped, nonce-labelled worker before its first start."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

from stop_reachy import Denied,WindowsBackend,checked_manifest,digest,strict_json,windows_path


def require_idle(manifest):
    entries=[entry for key in ('processes','services','tasks','models') for entry in manifest[key]]
    if manifest['docker'] is not None:entries+=manifest['docker']['containers']
    if any(entry.get('unknown') is True or entry.get('status') in ('unknown','pending','busy','timeout_unknown','error_unknown')
           for entry in entries):raise Denied('pending_inventory_requires_review')


def enroll(backend,*,inventory_path,scope_root,docker_executable,endpoint,container_id,launch_id,config_sha256,image_id):
    root=windows_path(scope_root)
    if str(uuid.UUID(launch_id))!=launch_id:raise Denied('launch_identity')
    import re
    if not re.fullmatch('[0-9a-f]{64}',container_id):raise Denied('full_container_identity')
    if not re.fullmatch('[0-9a-f]{64}',config_sha256):raise Denied('config_identity')
    windows_path(docker_executable)
    if not re.fullmatch(r'npipe:/{2,}\./pipe/[A-Za-z0-9_.-]+',endpoint):raise Denied('local_engine')
    prefix=[docker_executable,'--host',endpoint]
    engine=backend.command(prefix+['info','--format','{{.ID}}'])
    observed=strict_json(backend.command(prefix+['inspect',container_id]))
    if type(observed) is not list or len(observed)!=1:raise Denied('created_container_observation')
    value=observed[0];labels=value.get('Config',{}).get('Labels',{})
    mounts=[m for m in value.get('Mounts',[]) if m.get('Type')=='bind' and m.get('Destination')=='/config']
    if (value.get('Id')!=container_id or value.get('State',{}).get('Running') is not False
            or value.get('Image')!=image_id
            or value.get('Config',{}).get('Entrypoint')!=['python','-m','reachy_companion']
            or value.get('Config',{}).get('Cmd')!=['--config','/config/config.worker.local.json','worker','serve']
            or value.get('State',{}).get('Status')!='created' or value.get('HostConfig',{}).get('AutoRemove') is not False
            or labels.get('io.reachy-companion.launch-id')!=launch_id
            or windows_path(labels.get('io.reachy-companion.scope-root'))!=root or len(mounts)!=1):
        raise Denied('not_just_created_owned_worker')
    evidence=digest(dict(kind='created_worker',engine_id=engine,id=container_id,launch_id=launch_id,scope_root=root))
    entry=dict(confirmed_reachy_owned=True,evidence_sha256=evidence,scope_root=scope_root,id=container_id,
        image_id=value['Image'],command_sha256=digest(dict(entrypoint=value['Config'].get('Entrypoint'),cmd=value['Config'].get('Cmd'))),
        mount_source=mounts[0]['Source'],mount_destination='/config',worker_config_sha256=config_sha256)
    path=Path(inventory_path);path.parent.mkdir(parents=True,exist_ok=True)
    # One cooperative writer; a crash leaves this marker for explicit review.
    lock=path.with_name(path.name+'.enrolling')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        if path.exists():
            with path.open('rb') as source:raw=source.read(131073)
            if len(raw)>131072:raise Denied('inventory_bound')
            before=strict_json(raw);checked_manifest(before)
            require_idle(before)
            current=before['docker']
            if current is not None and (current['engine_id']!=engine or current['endpoint']!=endpoint
                    or windows_path(current['executable'])!=windows_path(docker_executable)):
                raise Denied('existing_engine_scope_changed')
        else:
            before=dict(schema=1,owner='reachy-companion',scope_roots=[],docker=None,processes=[],services=[],tasks=[],models=[])
        if before['docker'] is None:
            before['docker']=dict(executable=docker_executable,endpoint=endpoint,engine_id=engine,containers=[])
        if any(item['id']==container_id for item in before['docker']['containers']):raise Denied('already_enrolled_requires_review')
        if root not in [windows_path(p) for p in before['scope_roots']]:before['scope_roots'].append(scope_root)
        before['docker']['containers'].append(entry)
        checked_manifest(before)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as output:
                temporary=Path(output.name);json.dump(before,output,ensure_ascii=False,indent=2);output.flush();os.fsync(output.fileno())
            os.replace(temporary,path)
        finally:
            if temporary is not None and temporary.exists():temporary.unlink()
        return dict(enrolled=True,id=container_id,engine_id=engine,inventory=str(path),running=False)
    finally:
        os.close(fd);lock.unlink()


def registered_entry(*,inventory_path,scope_root,docker_executable,endpoint,container_id,config_sha256,image_id):
    with Path(inventory_path).open('rb') as source:raw=source.read(131073)
    if len(raw)>131072:raise Denied('inventory_bound')
    manifest=strict_json(raw);checked_manifest(manifest)
    docker=manifest['docker']
    if (docker is None or docker['endpoint']!=endpoint
            or windows_path(docker['executable'])!=windows_path(docker_executable)):
        raise Denied('registered_engine_scope')
    entries=[entry for entry in docker['containers'] if entry['id']==container_id]
    if (len(entries)!=1 or windows_path(entries[0]['scope_root'])!=windows_path(scope_root)
            or entries[0].get('worker_config_sha256')!=config_sha256 or entries[0]['image_id']!=image_id):
        raise Denied('registered_worker_config_or_image_changed')
    return manifest,entries[0]


def verify_registered(backend,**arguments):
    if Path(str(arguments['inventory_path'])+'.enrolling').exists():raise Denied('enrollment_pending')
    manifest,entry=registered_entry(**arguments);require_idle(manifest)
    observed=backend.docker(entry,manifest,True)
    container_id=entry['id']
    return dict(registered=True,id=container_id,running=observed=='would_stop')


def stop_after_manual_request(backend,*,latch_path,**arguments):
    if not Path(latch_path).exists():raise Denied('manual_stop_not_present')
    manifest,entry=registered_entry(**arguments)
    # Human stop does not wait for or clear any UNKNOWN/enrollment slot.
    state=backend.docker(entry,manifest,False)
    return dict(stopped_after_manual_request=state in ('stopped','already_stopped'),id=entry['id'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for option in ('inventory','scope-root','docker-executable','endpoint','container-id','config-sha256'):
        parser.add_argument('--'+option,required=True)
    parser.add_argument('--launch-id');parser.add_argument('--verify-registered',action='store_true');parser.add_argument('--image-id')
    parser.add_argument('--stop-if-latched',action='store_true');parser.add_argument('--latch-path')
    args=parser.parse_args()
    try:
        arguments=dict(inventory_path=args.inventory,scope_root=args.scope_root,docker_executable=args.docker_executable,
                       endpoint=args.endpoint,container_id=args.container_id,config_sha256=args.config_sha256)
        backend=WindowsBackend(timeout=10)
        backend.deadline=time.monotonic()+30
        if args.stop_if_latched:result=stop_after_manual_request(backend,**arguments,image_id=args.image_id,latch_path=args.latch_path)
        elif args.verify_registered:result=verify_registered(backend,**arguments,image_id=args.image_id)
        else:result=enroll(backend,**arguments,launch_id=args.launch_id,image_id=args.image_id)
    except Exception:
        print(json.dumps(dict(enrolled=False,error='created_worker_enrollment_denied')));return 2
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
