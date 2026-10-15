"""Manual PC stop: exact private inventory, persistent stop first, no discovery kills.

Standalone stdlib helper. Importing it does not stop anything or write a latch.
"""
import argparse
import base64
import ctypes
from datetime import datetime,timezone
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid


class Denied(RuntimeError):pass


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def strict_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise Denied('duplicate_json')
            result[key]=value
        return result
    def constant(value):raise Denied('nonfinite_json')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)


def windows_path(value):
    if (type(value) is not str or not re.match(r'^[A-Za-z]:\\',value) or len(value)>2048
            or any(c in value for c in '\x00\r\n') or ':' in value[2:]
            or ntpath.normpath(value)!=value):raise Denied('canonical_local_path_required')
    return ntpath.normcase(value)


def checked_manifest(value):
    if (type(value) is not dict or set(value)!={'schema','owner','scope_roots','docker','processes','services','tasks','models'}
            or type(value['schema']) is not int or value['schema']!=1 or value['owner']!='reachy-companion'):
        raise Denied('inventory_schema')
    roots=value['scope_roots']
    if type(roots) is not list or not 1<=len(roots)<=16:raise Denied('inventory_roots')
    roots=[windows_path(root) for root in roots]
    if any(len(root)<=3 for root in roots):raise Denied('scope_directory_required')
    def approved(entry):
        if (type(entry) is not dict or entry.get('confirmed_reachy_owned') is not True
                or not re.fullmatch('[0-9a-f]{64}',entry.get('evidence_sha256',''))
                or windows_path(entry.get('scope_root')) not in roots):raise Denied('ownership_not_confirmed')
    def process(entry,dedicated=False):
        if (type(entry.get('pid')) is not int or not 1<=entry['pid']<2**32
                or type(entry.get('creation_filetime')) is not int or not 0<entry['creation_filetime']<2**64
                or not re.fullmatch('[0-9a-f]{64}',entry.get('command_sha256',''))):raise Denied('process_identity')
        windows_path(entry.get('executable'))
        if dedicated and entry.get('dedicated_to_reachy') is not True:raise Denied('shared_application_preserved')
    docker=value['docker']
    targets=[]
    if docker is not None:
        if type(docker) is not dict or not re.fullmatch(r'npipe:/{2,}\./pipe/[A-Za-z0-9_.-]+',docker.get('endpoint','')):
            raise Denied('local_docker_endpoint')
        windows_path(docker.get('executable'))
        if type(docker.get('engine_id')) is not str or not 1<=len(docker['engine_id'])<=128:raise Denied('docker_engine_identity')
        if type(docker.get('containers')) is not list:raise Denied('container_inventory')
        for entry in docker['containers']:
            approved(entry)
            if (not re.fullmatch('[0-9a-f]{64}',entry.get('id',''))
                    or not re.fullmatch('sha256:[0-9a-f]{64}',entry.get('image_id',''))
                    or not re.fullmatch('[0-9a-f]{64}',entry.get('command_sha256',''))
                    or any(type(entry.get(k)) is not str or not 1<=len(entry[k])<=2048 or '\x00' in entry[k]
                           for k in ('mount_source','mount_destination'))):raise Denied('container_identity')
            targets.append(('container',entry))
    for kind,key in (('task','tasks'),('service','services'),('process','processes'),('model','models')):
        entries=value[key]
        if type(entries) is not list:raise Denied('inventory_list')
        for entry in entries:
            approved(entry)
            if kind=='process':
                if entry.get('role') not in ('launcher','lm_studio_dedicated'):raise Denied('process_role')
                process(entry,entry['role']=='lm_studio_dedicated')
                if (ntpath.basename(entry['executable']).casefold() in ('lm studio.exe','lmstudio.exe','llmster.exe')
                        and entry['role']!='lm_studio_dedicated'):raise Denied('shared_application_preserved')
            elif kind=='service':
                if (not re.fullmatch('[A-Za-z0-9_.-]{1,128}',entry.get('name',''))
                        or type(entry.get('binary_path')) is not str or not 1<=len(entry['binary_path'])<=4096
                        or type(entry.get('start_name')) is not str or not entry['start_name']):raise Denied('service_identity')
            elif kind=='task':
                if (type(entry.get('name')) is not str or not 1<=len(entry['name'])<=128
                        or any(c in entry['name'] for c in '\\/:*?"<>|\x00')
                        or not re.fullmatch(r'\\(?:[^\\/:*?"<>|\x00]+\\)*',entry.get('path',''))
                        or not re.fullmatch('[0-9a-f]{64}',entry.get('xml_sha256',''))):raise Denied('task_identity')
            else:
                if (entry.get('dedicated_to_reachy') is not True
                        or not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}',entry.get('url',''))
                        or not 1<=int(entry['url'].rsplit(':',1)[1])<=65535
                        or any(type(entry.get(k)) is not str or not 1<=len(entry[k])<=256 for k in ('model_key','instance_id'))
                        or not re.fullmatch('[0-9a-f]{64}',entry.get('config_sha256',''))):raise Denied('model_identity')
                process(entry.get('server',{}))
                if entry.get('token_env') is not None and not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}',entry['token_env']):
                    raise Denied('token_environment_name')
            targets.append((kind,entry))
    if not targets or len(targets)>64:raise Denied('bounded_nonempty_inventory_required')
    identities=[(kind,entry.get('id',entry.get('pid',entry.get('instance_id',(entry.get('path'),entry.get('name')))))) for kind,entry in targets]
    if len(set(identities))!=len(identities):raise Denied('duplicate_target')
    # Stop autostart producers first; LM Studio process termination is last.
    targets.sort(key=lambda item: {'task':0,'service':1,'container':2,'process':4 if item[1].get('role')=='lm_studio_dedicated' else 1,'model':3}[item[0]])
    return targets


def write_latch(path):
    path=Path(path)
    if path.is_symlink():raise Denied('latch_symlink')
    path.parent.mkdir(parents=True,exist_ok=True)
    try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:return False # Even malformed existing presence denies startup.
    with os.fdopen(fd,'w',encoding='utf-8') as output:
        json.dump(dict(schema=1,kind='reachy_manual_stop',request_id=str(uuid.uuid4()),
                       requested_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')),output)
        output.flush();os.fsync(output.fileno())
    return True


def stop_inventory(manifest,backend,*,latch_path,dry_run=False,total_timeout=90,clock=time.monotonic):
    if type(total_timeout) is not int or not 5<=total_timeout<=300:raise Denied('total_timeout_bound')
    deadline=clock()+total_timeout
    backend.deadline=deadline
    report=dict(dry_run=dry_run,latch_present=False,results=[],shared_lm_studio='preserved_unless_explicit_dedicated_inventory',
                gpu_freed_verified=False,automatic_resume=False)
    # Human stop has priority even over malformed inventory / busy operations.
    if not dry_run:write_latch(latch_path);report['latch_present']=True
    targets=checked_manifest(manifest)
    for kind,entry in targets:
        identifier=entry.get('id',entry.get('pid',entry.get('instance_id',entry.get('name'))))
        row=dict(kind=kind,target=str(identifier),status='unknown')
        if clock()>=deadline:
            row['status']='not_attempted_deadline';report['results'].append(row);continue
        try:row['status']=backend.stop(kind,entry,manifest,dry_run=dry_run)
        except Denied:row['status']='denied_identity'
        except (TimeoutError,subprocess.TimeoutExpired):row['status']='timeout_unknown'
        except Exception:row['status']='error_unknown'
        report['results'].append(row)
    report['ok']=all(row['status'] in ('stopped','already_stopped','would_stop') for row in report['results'])
    return report


class WindowsBackend:
    def __init__(self,*,timeout=15):
        if os.name!='nt':raise Denied('windows_only')
        self.timeout=timeout
        self.deadline=None
        self.powershell=str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe')

    def command(self,args,*,input=None):
        result=subprocess.run(args,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=self.remaining(),
                              creationflags=0x08000000)
        if result.returncode:raise Denied('command_failed')
        if len(result.stdout)>1048576:raise Denied('command_output_bound')
        return result.stdout.decode('utf-8-sig').strip()

    def remaining(self):
        value=self.timeout if getattr(self,'deadline',None) is None else min(self.timeout,self.deadline-time.monotonic())
        if value<=0:raise TimeoutError()
        return value

    def ps(self,script,data):
        source="$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);$d=[Console]::In.ReadToEnd()|ConvertFrom-Json;"+script
        encoded=base64.b64encode(source.encode('utf-16-le')).decode()
        raw=self.command([self.powershell,'-NoProfile','-NonInteractive','-EncodedCommand',encoded],input=json.dumps(data).encode())
        return strict_json(raw) if raw else None

    def process_snapshot(self,pid):
        # CIM CreationDate can truncate sub-microsecond FILETIME precision.
        # .NET StartTime uses native process times; CIM supplies command/path.
        return self.ps("$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$d.pid);if($p){$n=[Diagnostics.Process]::GetProcessById($d.pid);try{@{creation_filetime=$n.StartTime.ToUniversalTime().ToFileTimeUtc();executable=$p.ExecutablePath;command=$p.CommandLine}|ConvertTo-Json -Compress}finally{$n.Dispose()}}",dict(pid=pid))

    @staticmethod
    def same_process(snapshot,entry):
        return (type(snapshot) is dict and type(snapshot.get('creation_filetime')) is int
                and snapshot.get('creation_filetime')==entry['creation_filetime']
                and windows_path(snapshot.get('executable'))==windows_path(entry['executable'])
                and type(snapshot.get('command')) is str
                and hashlib.sha256(snapshot['command'].encode()).hexdigest()==entry['command_sha256'])

    def process(self,entry,dry_run):
        # Pin the original process handle; never re-open PID for termination.
        from ctypes import wintypes as W
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];api.OpenProcess.restype=W.HANDLE
        api.CloseHandle.argtypes=[W.HANDLE];api.CloseHandle.restype=W.BOOL
        api.GetProcessTimes.argtypes=[W.HANDLE,*([ctypes.POINTER(W.FILETIME)]*4)];api.GetProcessTimes.restype=W.BOOL
        api.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)];api.QueryFullProcessImageNameW.restype=W.BOOL
        api.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];api.WaitForSingleObject.restype=W.DWORD
        api.TerminateProcess.argtypes=[W.HANDLE,W.UINT];api.TerminateProcess.restype=W.BOOL
        handle=api.OpenProcess(0x100000|0x1000|(0 if dry_run else 1),False,entry['pid'])
        if not handle:
            if ctypes.get_last_error()==87:return 'already_stopped'
            raise Denied('process_handle')
        try:
            state=api.WaitForSingleObject(handle,0)
            if state==0:return 'already_stopped'
            if state!=258:raise Denied('process_state')
            times=[W.FILETIME() for _ in range(4)]
            if not api.GetProcessTimes(handle,*[ctypes.byref(v) for v in times]):raise Denied('process_times')
            created=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
            size=W.DWORD(32768);path=ctypes.create_unicode_buffer(size.value)
            if not api.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)):raise Denied('process_path')
            if created!=entry['creation_filetime'] or windows_path(path.value)!=windows_path(entry['executable']):raise Denied('process_replaced')
            snapshot=self.process_snapshot(entry['pid'])
            if not self.same_process(snapshot,entry):raise Denied('process_command_changed')
            if (entry['role']=='launcher' and windows_path(entry['scope_root']).rstrip('\\')+'\\'
                    not in snapshot['command'].casefold().replace('/','\\')):raise Denied('launcher_scope_not_in_command')
            if dry_run:return 'would_stop'
            state=api.WaitForSingleObject(handle,0)
            if state==0:return 'already_stopped'
            if state!=258:raise Denied('process_state')
            self.remaining()
            if not api.TerminateProcess(handle,0):raise Denied('process_stop_failed')
            if api.WaitForSingleObject(handle,max(1,int(self.remaining()*1000)))!=0:raise TimeoutError()
            return 'stopped'
        finally:api.CloseHandle(handle)

    def docker(self,entry,manifest,dry_run):
        settings=manifest['docker'];prefix=[settings['executable'],'--host',settings['endpoint']]
        if self.command(prefix+['info','--format','{{.ID}}'])!=settings['engine_id']:raise Denied('docker_engine_changed')
        ids=self.command(prefix+['ps','-aq','--no-trunc']).splitlines()
        if entry['id'] not in ids:return 'already_stopped'
        def inspect():
            values=strict_json(self.command(prefix+['inspect',entry['id']]))
            if type(values) is not list or len(values)!=1:raise Denied('container_observation')
            value=values[0]
            if (value['Id']!=entry['id'] or value['Image']!=entry['image_id']
                    or digest(dict(entrypoint=value['Config'].get('Entrypoint'),cmd=value['Config'].get('Cmd')))!=entry['command_sha256']
                    or not any(m.get('Type')=='bind' and m.get('Source')==entry['mount_source']
                               and m.get('Destination')==entry['mount_destination'] for m in value['Mounts'])
                    or value.get('HostConfig',{}).get('AutoRemove') is not False):raise Denied('container_replaced')
            return value
        value=inspect()
        if value['State']['Running'] is False:return 'already_stopped'
        if value['State']['Running'] is not True:raise Denied('container_state')
        if dry_run:return 'would_stop'
        inspect() # Revalidate exact immutable ID immediately before the write.
        self.command(prefix+['stop','--time',str(max(1,int(self.timeout)-2)),entry['id']])
        if inspect()['State']['Running'] is not False:raise TimeoutError()
        return 'stopped'

    def service(self,entry,dry_run):
        read="$s=Get-CimInstance Win32_Service -Filter ('Name='+[char]39+$d.name+[char]39);if($s){@{binary_path=$s.PathName;start_name=$s.StartName;state=$s.State}|ConvertTo-Json -Compress}"
        value=self.ps(read,entry)
        if value is None:return 'already_stopped'
        if value.get('binary_path')!=entry['binary_path'] or value.get('start_name')!=entry['start_name']:raise Denied('service_changed')
        if value.get('state')=='Stopped':return 'already_stopped'
        if dry_run:return 'would_stop'
        # Revalidate inside the same bounded worker before the service request.
        script="$s=Get-CimInstance Win32_Service -Filter ('Name='+[char]39+$d.name+[char]39);if(!$s -or $s.PathName -cne $d.binary_path -or $s.StartName -cne $d.start_name){throw 'identity'};Stop-Service -Name $d.name -ErrorAction Stop;$s=Get-Service -Name $d.name;$s.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped,[TimeSpan]::FromSeconds($d.timeout));@{stopped=$true}|ConvertTo-Json -Compress"
        result=self.ps(script,dict(entry,timeout=max(1,self.timeout-2)))
        if not result or result.get('stopped') is not True:raise TimeoutError()
        return 'stopped'

    def task(self,entry,dry_run):
        script="$t=Get-ScheduledTask -TaskName $d.name -TaskPath $d.path -ErrorAction SilentlyContinue;if($t){@{xml=(Export-ScheduledTask -TaskName $d.name -TaskPath $d.path);state=[string]$t.State}|ConvertTo-Json -Compress}"
        value=self.ps(script,entry)
        if value is None:return 'already_stopped'
        if hashlib.sha256(value['xml'].encode()).hexdigest()!=entry['xml_sha256']:raise Denied('task_changed')
        if value['state']!='Running':return 'already_stopped'
        if dry_run:return 'would_stop'
        script="$xml=Export-ScheduledTask -TaskName $d.name -TaskPath $d.path;$h=[Security.Cryptography.SHA256]::Create();$sha=([BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($xml)))).Replace('-','').ToLowerInvariant();if($sha -cne $d.xml_sha256){throw 'identity'};Stop-ScheduledTask -TaskName $d.name -TaskPath $d.path;$until=[DateTime]::UtcNow.AddSeconds($d.timeout);do{$t=Get-ScheduledTask -TaskName $d.name -TaskPath $d.path;if($t.State -ne 'Running'){@{stopped=$true}|ConvertTo-Json -Compress;exit};Start-Sleep -Milliseconds 100}while([DateTime]::UtcNow -lt $until);throw 'timeout'"
        result=self.ps(script,dict(entry,timeout=max(1,self.timeout-2)))
        if not result or result.get('stopped') is not True:raise TimeoutError()
        return 'stopped'

    def model(self,entry,dry_run):
        server=entry['server']
        def verify():
            if not self.same_process(self.process_snapshot(server['pid']),server):raise Denied('model_server_changed')
            port=int(entry['url'].rsplit(':',1)[1])
            owners=self.ps("@(Get-NetTCPConnection -State Listen -LocalPort $d.port -ErrorAction Stop|Select-Object -ExpandProperty OwningProcess -Unique)|ConvertTo-Json -Compress",dict(port=port))
            if owners!=server['pid'] and owners!=[server['pid']]:raise Denied('model_endpoint_owner')
        def call(path,payload=None):
            # Own bounded request worker: a trickling HTTP response cannot
            # extend the total stop deadline. Tokens stay in inherited env.
            script="""import json,os,sys
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
d=json.load(sys.stdin);headers={'Content-Type':'application/json'}
if d['token_env']:headers['Authorization']='Bearer '+os.environ[d['token_env']]
request=Request(d['url'],data=None if d['payload'] is None else json.dumps(d['payload']).encode(),headers=headers)
with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=d['timeout']) as response:
 raw=response.read(1048577)
 if len(raw)>1048576:raise ValueError('response bound')
 sys.stdout.buffer.write(raw)
"""
            return strict_json(self.command([sys.executable,'-I','-B','-c',script],input=json.dumps(dict(
                url=entry['url']+path,payload=payload,token_env=entry.get('token_env'),timeout=self.remaining())).encode()))
        def observe():
            verify();value=call('/api/v1/models')
            found=[]
            for model in value['models']:
                for instance in model['loaded_instances']:
                    if instance['id']==entry['instance_id']:found.append((model,instance))
            if not found:return False
            if len(found)!=1 or found[0][0]['key']!=entry['model_key'] or digest(found[0][1]['config'])!=entry['config_sha256']:
                raise Denied('model_instance_changed')
            return True
        if not observe():return 'already_stopped'
        if dry_run:return 'would_stop'
        if not observe():return 'already_stopped'
        result=call('/api/v1/models/unload',dict(instance_id=entry['instance_id']))
        if result.get('instance_id')!=entry['instance_id'] or observe():raise Denied('model_unload_unknown')
        return 'stopped'

    def stop(self,kind,entry,manifest,*,dry_run):
        if kind=='container':return self.docker(entry,manifest,dry_run)
        if kind=='process':return self.process(entry,dry_run)
        return getattr(self,kind)(entry,dry_run)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--latch-path',type=Path,required=True,help='Canonical per-user path supplied by the PS launcher')
    parser.add_argument('--dry-run',action='store_true');parser.add_argument('--timeout',type=int,default=15)
    parser.add_argument('--total-timeout',type=int,default=90)
    args=parser.parse_args()
    try:
        if not args.dry_run:write_latch(args.latch_path) # Before inventory IO/backend creation.
        if not 3<=args.timeout<=60:raise Denied('timeout_bound')
        with args.inventory.open('rb') as inventory:raw=inventory.read(131073)
        if len(raw)>131072:raise Denied('inventory_bound')
        manifest=strict_json(raw);backend=WindowsBackend(timeout=args.timeout)
        report=stop_inventory(manifest,backend,latch_path=args.latch_path,dry_run=args.dry_run,total_timeout=args.total_timeout)
    except Exception:
        report=dict(ok=False,dry_run=args.dry_run,error='stop_incomplete',latch_present=args.latch_path.exists(),
                    automatic_resume=False,gpu_freed_verified=False)
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if report['ok'] else 2


if __name__=='__main__':raise SystemExit(main())
