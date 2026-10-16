"""Bounded SSH/scp using the documented factory credential only in RAM."""
import os,pathlib,pty,re,select,signal,sys,time
readme=(pathlib.Path(__file__).resolve().parents[1] / 'README.md').read_text()
line=next(s for s in readme.splitlines() if 'заводской пароль' in s)
values=re.findall(r'`([^`]*)`',line)
if len(values)!=2:raise SystemExit('Documented credential format changed')
password=values[1];args=sys.argv[1:]
if not args or args[0] not in ('ssh','scp'):raise SystemExit('SSH/scp only')
pid,fd=pty.fork()
if pid==0:os.execvp(args[0],args)
buffer=bytearray();pending='';answered=False;deadline=time.monotonic()+65;status=None
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
