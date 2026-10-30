import subprocess,time,uuid,json,sys
payload=json.load(sys.stdin);suffix=uuid.uuid4().hex[:6];a='rc-r-'+suffix;b='rc-c-'+suffix;server=None

def run(args,**kw):return subprocess.run(args,text=True,capture_output=True,check=True,timeout=12,**kw)
def ns(n,args,**kw):return run(['ip','netns','exec',n,*args],**kw)
def tcp(address,port,expected):
 program="import socket; s=socket.socket(socket.AF_INET6 if ':' in %r else socket.AF_INET); s.settimeout(.7); s.connect((%r,%d)); s.close()"%(address,address,port)
 r=subprocess.run(['ip','netns','exec',b,'python3','-c',program],capture_output=True,timeout=3)
 if (r.returncode==0)!=expected:raise RuntimeError('TCP assertion failed '+address+':'+str(port))

def udp(expected,source="198.18.0.2"):
 program="import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind((%r,68));s.settimeout(.7);s.sendto(b'probe',('198.18.0.1',67));assert s.recv(64)==b'probe'" % source
 r=subprocess.run(['ip','netns','exec',b,'python3','-c',program],capture_output=True,timeout=3)
 if (r.returncode==0)!=expected:raise RuntimeError('DHCP-direction assertion failed')
try:
 for n in [a,b]:run(['ip','netns','add',n]);ns(n,['ip','link','set','lo','up'])
 run(['ip','link','add','rca'+suffix,'type','veth','peer','name','rcb'+suffix])
 run(['ip','link','set','rca'+suffix,'netns',a]);run(['ip','link','set','rcb'+suffix,'netns',b])
 for n,old,new,ip,ip6 in [(a,'rca'+suffix,'robot0','198.18.0.1/24','fd00:1234::1/64'),(b,'rcb'+suffix,'client0','198.18.0.2/24','fd00:1234::2/64')]:
  ns(n,['ip','link','set',old,'name',new]);ns(n,['ip','addr','add',ip,'dev',new]);ns(n,['ip','-6','addr','add',ip6,'dev',new,'nodad']);ns(n,['ip','link','set',new,'up'])
 ns(a,['nft','-f','-'],input=payload['rules'])
 service="""import socket,select
socks=[]
for family,addr in [(socket.AF_INET,'0.0.0.0'),(socket.AF_INET6,'::')]:
 for port in [22,8000,8090]:
  s=socket.socket(family,socket.SOCK_STREAM)
  if family==socket.AF_INET6:s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
  s.bind((addr,port));s.listen();socks.append(s)
u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);u.bind(('0.0.0.0',67));socks.append(u)
while True:
 for s in select.select(socks,[],[],1)[0]:
  if s is u:
   d,addr=s.recvfrom(1000);s.sendto(d,addr)
  else:
   c,addr=s.accept();c.close()
"""
 server=subprocess.Popen(['ip','netns','exec',a,'python3','-c',service],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 time.sleep(.5)
 if server.poll() is not None:raise RuntimeError('Test server failed')
 for addr in ['198.18.0.1','fd00:1234::1']:tcp(addr,22,True);tcp(addr,8000,False);tcp(addr,8090,False)
 udp(False)
 ns(a,['nft','add','element','inet','reachy_companion','recovery_interfaces','{','"robot0"','}'])
 for addr in ['198.18.0.1','fd00:1234::1']:tcp(addr,8000,True);tcp(addr,8090,False)
 udp(True)
 ns(a,['nft','flush','set','inet','reachy_companion','recovery_interfaces'])
 tcp('198.18.0.1',8000,False)
 ns(b,['ip','addr','add','198.18.0.3/24','dev','client0'])
 udp(False,source='198.18.0.3')
 print('ISOLATED_PACKET_TESTS_PASS: IPv4+IPv6 SSH, API blocks, hotspot API+DHCP, return to client')
finally:
 if server:
  server.terminate()
  try:server.wait(timeout=3)
  except subprocess.TimeoutExpired:server.kill();server.wait()
 for n in [a,b]:subprocess.run(['ip','netns','delete',n],capture_output=True)
