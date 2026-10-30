"""Bounded SSH/scp using an environment-provided credential only in RAM."""
import os,pty,re,select,signal,sys,time
password=os.environ.get('REACHY_FACTORY_SSH_PASSWORD', '')
if not password:raise SystemExit('Set REACHY_FACTORY_SSH_PASSWORD')
args=sys.argv[1:]
if not args or args[0] not in ('ssh','scp'):raise SystemExit('SSH/scp only')
duration=int(os.environ.get('REACHY_FACTORY_SSH_LIFETIME_SECONDS','65'))
if not 10<=duration<=600:raise SystemExit('Finite SSH lifetime must be 10..600 seconds')
pid,fd=pty.fork()
if pid==0:os.execvp(args[0],args)
buffer=bytearray();pending='';answered=False;deadline=time.monotonic()+duration;status=None
try:
 while time.monotonic()<deadline:
  if select.select([fd],[],[],.1)[0]:
   try:raw=os.read(fd,8192)
   except OSError:break
   if not raw:break
   buffer.extend(raw);pending+=raw.decode(errors='replace')
   if re.search(r'(?i)password:\s*$',pending):
    if answered:raise RuntimeError('Second credential prompt denied')
    os.write(fd,(password+'\n').encode());answered=True;pending=''
  done,wait=os.waitpid(pid,os.WNOHANG)
  if done:status=wait;break
 if status is None:
  done,wait=os.waitpid(pid,os.WNOHANG)
  if done:status=wait
  elif time.monotonic()>=deadline:os.killpg(pid,signal.SIGTERM);_,status=os.waitpid(pid,0)
  else:_,status=os.waitpid(pid,0)
finally:os.close(fd)
text=buffer.decode(errors='replace').replace(password,'[credential withheld]')
print(text,end='');raise SystemExit(os.waitstatus_to_exitcode(status))
