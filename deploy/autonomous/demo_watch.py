"""Finite device watch using the existing Agent CAS cleanup and factory API.

Core IO/owned/cleanup/process checks retained from the physically exercised
existing-Agent demo. No audio capture, inference, new motor owner or UART.
"""
import argparse, hashlib, http.client, json, os, stat, subprocess, sys, threading, time, uuid
from pathlib import Path
from urllib.parse import urlsplit
ROOT = Path('/home/pollen/reachy-companion')
PY = '/venvs/mini_daemon/bin/python'
HUB = AGENT = FACTORY = None

class GuardDenied(ValueError):
 def __init__(self,code,changed=None,elapsed=None):self.code=code;self.changed=changed or [];self.elapsed=elapsed;super().__init__(code)

def need(v,code='precondition',changed=None,elapsed=None):
 if not v:raise GuardDenied(code,changed,elapsed)

def authority(value):return {k:value[k] for k in ['agent_boot_id','microphone_epoch','microphone_enabled','microphone_owner_id','motion_policy','motion_policy_owner_id','microphone_state_error']}

def raw(path,cap=100000):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  s=os.fstat(fd);need(stat.S_ISREG(s.st_mode) and s.st_size<=cap);v=os.read(fd,cap+1);need(len(v)==s.st_size);return v
 finally:os.close(fd)

def save(path,value):
 b=json.dumps(value,sort_keys=True,allow_nan=False).encode();temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:os.write(fd,b);os.fsync(fd)
 finally:os.close(fd)
 os.replace(temp,path)

def proc(pid):
 p=Path('/proc')/str(pid);s=(p/'stat').read_text();fields=s[s.rfind(')')+2:].split()
 return dict(pid=pid,ticks=int(fields[19]),ppid=int(fields[1]),cgroup=(p/'cgroup').read_text().strip(),exe=str((p/'exe').resolve()))

def playbacks(pid):
 found=[];children=set()
 for task in (Path('/proc')/str(pid)/'task').iterdir():
  try:children.update(int(x) for x in (task/'children').read_text().split())
  except FileNotFoundError:pass
 parent=proc(pid)
 for child in children:
  try:
   value=proc(child)
   if value['ppid']==pid and value['cgroup']==parent['cgroup'] and value['exe']=='/usr/bin/aplay':found.append(value)
  except (FileNotFoundError,ProcessLookupError):pass
 return found

class IO:
 def __init__(self):
  global HUB, AGENT, FACTORY
  cfg=json.loads(raw(ROOT/'config.local.json'))
  def address(key,local=False):
   endpoint=urlsplit(cfg['network'][key]);need(endpoint.scheme=='http' and endpoint.hostname and not endpoint.username,'local_HTTP_endpoint');return ('127.0.0.1' if local else endpoint.hostname),endpoint.port or 80
  HUB,AGENT,FACTORY=address('hub_url'),address('agent_url',True),address('robot_url',True)
  p=Path(cfg['paths']['token_file']);p=p if p.is_absolute() else ROOT/p
  self.token=raw(p,8192).decode().strip();need(len(self.token)>=32);self.last_endpoint=None;self.last_endpoint_by_thread={};self.operator_begin_by_thread={};self.calibration_seconds=cfg['audio']['calibration_chunks']*cfg['audio']['chunk_ms']/1000+.25
 def req(self,where,path,payload=None,expected=None,timeout=2):
  target=('Agent' if where==AGENT else 'Hub' if where==HUB else 'factory' if where==FACTORY else 'router')+path;self.last_endpoint_by_thread[threading.get_ident()]=target;body=None if payload is None else json.dumps(payload).encode();c=http.client.HTTPConnection(*where,timeout=timeout);c.connect()
  try:
   if payload is not None:
    now=self.op();began=self.operator_begin_by_thread[threading.get_ident()];elapsed=time.monotonic()-began;changed=[k for k in now if now[k]!=expected.get(k)];need(authority(now)==authority(expected),'authority_changed',changed,elapsed);need(elapsed<=.3,'operator_GET_expired',changed,elapsed)
    sock=c.sock
    class Fresh:
     def sendall(self,data,*args):
      data=memoryview(data)
      while data:
       remaining=.3-(time.monotonic()-began);need(remaining>0,'actual_send_expired')
       sock.settimeout(min(timeout,remaining));sent=sock.send(data);need(sent>0,'send_failed');data=data[sent:]
     def __getattr__(self,key):return getattr(sock,key)
    c.sock=Fresh()
   self.last_endpoint_by_thread[threading.get_ident()]=target
   if payload is not None and where==AGENT and (path=='/microphone' and payload.get('enabled') is True or path=='/motion-policy' and payload.get('motor_enabled') is True):
    need(now['phase']=='paused' and now['capture_active'] is False and now['listening'] is False and now['microphone_enabled'] is False and now['microphone_owner_id'] is None,'ON_requires_idle_OFF')
    if path=='/motion-policy':need(now['motion_policy_owner_id'] is None and now['motion_policy']['motor_enabled'] is False,'policy_ON_requires_unowned_OFF')
   c.request('GET' if body is None else 'POST',path,body=body,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json','Connection':'close','Cache-Control':'no-store'})
   c.sock.settimeout(timeout)
   r=c.getresponse();b=r.read(100001);need(r.status==200,'HTTP_'+str(r.status));need(len(b)<=100000,'response_size')
   if where==HUB and path=='/control/operator':need('no-store' in r.getheader('Cache-Control','').lower())
   return json.loads(b)
  finally:c.close()
 def op(self):
  for attempt in range(2):
   read_begin=time.monotonic()
   try:
    value=self.req(HUB,'/control/operator');need(time.monotonic()-read_begin<=.3,'operator_GET_expired',elapsed=time.monotonic()-read_begin);break
   except GuardDenied as error:
    if attempt or error.code not in ('HTTP_503','operator_GET_expired'):raise
    time.sleep(.025)
  self.operator_begin_by_thread[threading.get_ident()]=read_begin
  fields={'agent_boot_id','microphone_epoch','microphone_owner_id','microphone_enabled','capture_active','phase','listening','microphone_state_error','motion_policy','motion_policy_owner_id','expression_version'}
  need(type(value) is dict and set(value)==fields,'operator_shape');policy=value['motion_policy'];need(type(policy) is dict and set(policy)=={'epoch','motor_enabled','quiet','privacy_all'},'policy_shape')
  need(type(value['agent_boot_id']) is str and 1<=len(value['agent_boot_id'])<=256,'boot_type');need(value['microphone_state_error'] is None,'microphone_state_unknown')
  need(all(type(x) is int and 0<=x<2**63 for x in [value['microphone_epoch'],value['expression_version'],policy['epoch']]),'epoch_type')
  need(all(type(value[k]) is bool for k in ['microphone_enabled','capture_active','listening']) and all(type(policy[k]) is bool for k in ['motor_enabled','quiet','privacy_all']),'control_type')
  need(all(value[k] is None or type(value[k]) is str and 1<=len(value[k])<=128 for k in ['microphone_owner_id','motion_policy_owner_id']),'owner_type')
  need(value['phase'] in ['starting','paused','listening','recording','processing','speaking','waiting_to_resume','music','error','stopped'],'phase_type');return value
 def status(self):return self.req(AGENT,'/status')

def owned(v,p,kind):
 if v['agent_boot_id']!=p['boot']:return False
 if kind=='mic':return v['microphone_epoch']==p['mic_epoch']+1 and v['microphone_owner_id']==p['owner']
 return v['motion_policy']['epoch']==p['policy_epoch']+1 and v['motion_policy_owner_id']==p['owner']

def cleanup(io,p):
 out={'mic_OFF_POST':False,'policy_OFF_POST':False}
 # Retire an unused admission too: a child delayed past watch exit must not
 # acquire the unchanged baseline later. These are OFF-only CAS operations.
 for kind in ('mic','policy'):
  v=io.op()
  claim=owned(v,p,kind);policy=v['motion_policy']
  mic_current=(v['microphone_epoch'],v['microphone_enabled'],v['microphone_owner_id'])
  baseline=v['agent_boot_id']==p['boot']
  if kind=='mic':
   fence=(baseline and mic_current==(p['mic_epoch'],False,None)
    and not v['capture_active'] and not v['listening'])
  else:
   fence=(baseline and policy['epoch']==p['policy_epoch'] and policy['motor_enabled'] is False
    and v['motion_policy_owner_id'] is None)
  if not claim and not fence:continue
  payload=dict(expected_boot_id=p['boot'])
  if claim:payload['expected_owner_id']=p['owner']
  if kind=='mic':payload.update(enabled=False,listen=False,expected_epoch=v['microphone_epoch']);path='/microphone'
  else:payload.update(motor_enabled=False,quiet=policy['quiet'],privacy_all=policy['privacy_all'],expected_epoch=policy['epoch']);path='/motion-policy'
  try:
   io.req(AGENT,path,payload,v,2);out[kind+'_OFF_POST']=True
   if fence:out[kind+'_baseline_fenced']=True
  except Exception:out[kind+'_POST_unknown']=True
 until=time.monotonic()+4
 good=retired=False;running=None;s={};h={'stock_motion':{'unknown':True}}
 while time.monotonic()<until:
  v=io.op();s=io.status();h=io.req(HUB,'/status');running=io.req(FACTORY,'/api/move/running')
  good=(not v['microphone_enabled'] and not v['capture_active'] and not v['listening'] and v['microphone_owner_id'] is None
    and not v['motion_policy']['motor_enabled'] and v['motion_policy_owner_id'] is None and not playbacks(p['agent_pid']) and running==[])
  retired=(v['agent_boot_id']!=p['boot'] or
    v['microphone_epoch']>p['mic_epoch'] and v['motion_policy']['epoch']>p['policy_epoch'])
  if good and retired:break
  time.sleep(.1)
 out.update(final_OFF=good,admission_retired=retired,volume_percent=s.get('volume_percent'),stock_unknown=h['stock_motion']['unknown'],factory_running_empty=running==[],aplay_absent=not playbacks(p['agent_pid']),
  microphone_epoch=v['microphone_epoch'],policy_epoch=v['motion_policy']['epoch'],newer_owner_preserved=v['agent_boot_id']!=p['boot'] or v['microphone_owner_id'] not in (None,p['owner']) or v['motion_policy_owner_id'] not in (None,p['owner']))
 return out

def state_unit(name):
 x=subprocess.run(['systemctl','show',name,'--property=MainPID,InvocationID,ActiveState,ControlGroup'],capture_output=True,timeout=2);need(x.returncode==0)
 return dict(line.split('=',1) for line in x.stdout.decode().splitlines() if '=' in line)


RUN_BASE = Path('/run')


def owner_uuid(value):
    need(type(value) is str and len(value) == 36, 'owner_type')
    parsed = uuid.UUID(value)
    need(str(parsed) == value and parsed.int != 0, 'canonical_owner')
    return value


def load_plan(run_id, pin, owner):
    need(type(run_id) is str and len(run_id) == 32 and all(c in '0123456789abcdef' for c in run_id), 'run_id')
    need(type(pin) is str and len(pin) == 64 and all(c in '0123456789abcdef' for c in pin), 'plan_pin')
    run = RUN_BASE / ('reachy-companion-demo-' + run_id)
    info = run.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, 'private_run')
    plan = run / 'plan.private.json'
    info = plan.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600, 'private_plan')
    data = raw(plan)
    need(hashlib.sha256(data).hexdigest() == pin, 'plan_changed')
    value = json.loads(data)
    need(value['owner'] == owner_uuid(owner) and value['run'] == str(run), 'plan_owner')
    return run, value


def arm(io, request):
    need(set(request) == {'action', 'owner', 'seconds'} and request['action'] == 'arm', 'arm_shape')
    owner = owner_uuid(request['owner'])
    seconds = request['seconds']
    need(type(seconds) is int and 10 <= seconds <= 300, 'duration')
    value = io.op()
    status = io.status()
    hub = io.req(HUB, '/status')
    need(value['phase'] == 'paused' and all(value[k] is False for k in ('microphone_enabled', 'capture_active', 'listening')), 'idle_OFF')
    need(value['microphone_owner_id'] is None and value['motion_policy_owner_id'] is None
         and all(value['motion_policy'][k] is False for k in ('motor_enabled', 'quiet', 'privacy_all')), 'unowned_policy_OFF')
    need(status['volume_percent'] == 50 and hub['stock_motion']['selected'] is True
         and hub['stock_motion']['unknown'] is False and hub['stock_motion']['owned_uuid'] is None
         and hub['ownership']['state'] == 'free' and not hub['action_running']
         and hub['robot']['control_mode'] == 'enabled' and io.req(FACTORY, '/api/move/running') == [], 'factory_idle')
    agent = state_unit('reachy-voice-agent.service')
    need(agent['ActiveState'] == 'active', 'agent_active')
    pid = int(agent['MainPID'])
    run_id = uuid.uuid4().hex
    run = RUN_BASE / ('reachy-companion-demo-' + run_id)
    run.mkdir(mode=0o700)
    source = globals().get('SOURCE') or raw(Path(__file__), 200000)
    script = run / 'watch.py'
    script.write_bytes(source)
    script.chmod(0o444)
    plan = dict(boot=value['agent_boot_id'], mic_epoch=value['microphone_epoch'],
        policy_epoch=value['motion_policy']['epoch'], owner=owner, deadline=time.monotonic() + seconds + 20,
        initial_turns=status['turns'], agent_pid=pid, agent_identity=proc(pid), run=str(run))
    path = run / 'plan.private.json'
    save(path, plan)
    pin = hashlib.sha256(raw(path)).hexdigest()
    unit = 'reachy-companion-demo-' + run_id + '.service'
    command = ['systemd-run', '--quiet', '--unit=' + unit, '--property=Type=exec', '--property=User=root',
        '--property=Restart=no', '--property=KillMode=control-group', '--property=RuntimeMaxSec=' + str(seconds + 40) + 's',
        PY, '-I', '-B', str(script), '--production-root', str(ROOT), '--watch', '--plan', str(path), '--pin', pin]
    child = subprocess.run(command, capture_output=True, timeout=3)
    need(child.returncode == 0, 'watch_launch')
    until = time.monotonic() + 3
    while not (run / 'watch-ready.json').exists() and time.monotonic() < until:
        time.sleep(.05)
    ready = json.loads(raw(run / 'watch-ready.json'))
    state = state_unit(unit)
    need(state['ActiveState'] == 'active' and int(state['MainPID']) == ready['pid']
         and proc(ready['pid']) == ready['identity'], 'watch_identity')
    return dict(kind='companion-demo-watch', ready=True, run_id=run_id, plan_sha256=pin,
        owner_sha256=hashlib.sha256(owner.encode()).hexdigest(),
        operator_binding=dict(agent_boot_id=plan['boot'], microphone_epoch=plan['mic_epoch'], policy_epoch=plan['policy_epoch']))


def finish(request):
    need(set(request) == {'action', 'owner', 'run_id', 'plan_sha256'} and request['action'] == 'finish', 'finish_shape')
    run, _ = load_plan(request['run_id'], request['plan_sha256'], request['owner'])
    save(run / 'controller.done', dict(done=True))
    until = time.monotonic() + 16
    while not (run / 'watch-result.json').exists() and time.monotonic() < until:
        time.sleep(.1)
    return dict(kind='companion-demo-cleanup', cleanup=json.loads(raw(run / 'watch-result.json')))


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('--production-root', type=Path, default=ROOT)
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--pin')
    args = parser.parse_args()
    need(os.geteuid() == 0, 'existing_privileged_watch_required')
    ROOT = args.production_root
    io = IO()
    if args.watch:
        data = raw(args.plan)
        need(hashlib.sha256(data).hexdigest() == args.pin, 'watch_plan_changed')
        plan = json.loads(data)
        run, plan = load_plan(args.plan.parent.name.removeprefix('reachy-companion-demo-'), args.pin, plan['owner'])
        save(run / 'watch-ready.json', dict(pid=os.getpid(), identity=proc(os.getpid())))
        try:
            while time.monotonic() < plan['deadline'] and not (run / 'controller.done').exists():
                time.sleep(.1)
        finally:
            try: result = cleanup(io, plan)
            except BaseException as error: result = dict(final_OFF=False, error_type=type(error).__name__)
            save(run / 'watch-result.json', result)
        return
    data = sys.stdin.buffer.read(2049)
    need(0 < len(data) <= 2048, 'request_size')
    request = json.loads(data)
    need(type(request) is dict, 'request_type')
    result = arm(io, request) if request.get('action') == 'arm' else finish(request)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    try: main()
    except BaseException as error:
        print(json.dumps(dict(kind='companion-demo-watch-error', error_type=type(error).__name__)), flush=True)
        raise SystemExit(1)
