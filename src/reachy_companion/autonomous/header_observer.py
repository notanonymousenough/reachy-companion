"""Finite Linux kernel-truncated Ethernet/IPv4/UDP metadata observer.

No receive socket admits packets before exact-flow cBPF is attached and locked.
Capture buffers are always 42 bytes; packet payload is never delivered to them.
"""
import ctypes
import errno
import ipaddress
import socket
import struct
import sys
import time

SNAPLEN=42
SO_ATTACH_FILTER=26
SO_LOCK_FILTER=44
SOL_PACKET=263
PACKET_STATISTICS=6
SO_TIMESTAMPNS=35


def flow(client,server,port):
    client=ipaddress.IPv4Address(client);server=ipaddress.IPv4Address(server)
    if client==server or type(port) is not int or not 1<=port<=65535:raise ValueError('Explicit distinct IPv4 endpoints and server port required')
    return int(client),int(server),port


def compile_filter(client,server,port):
    client,server,port=flow(client,server,port)
    code=[];labels={}
    def emit(op,k=0,jt=None,jf=None):code.append((op,jt,jf,k))
    def label(name):labels[name]=len(code)
    def eq(k):emit(0x15,k,None,'reject')
    emit(0x80);emit(0x35,42,None,'reject');emit(0x02,0) # length -> M0
    emit(0x28,12);eq(0x0800)
    emit(0x30,14);eq(0x45)
    emit(0x30,23);eq(17)
    emit(0x28,20);emit(0x45,0xbfff,'reject') # only DF may be set
    emit(0x28,16);emit(0x35,28,None,'reject');emit(0x02,1)
    emit(0x04,14);emit(0x61,0);emit(0x2d,0,'reject') # IP length fits full skb
    emit(0x60,1);emit(0x14,20);emit(0x02,2)
    emit(0x28,38);emit(0x61,2);emit(0x1d,0,None,'reject') # UDP length == IP-20
    emit(0x20,26);emit(0x15,client,'forward','reverse')
    label('forward');emit(0x20,30);eq(server);emit(0x28,36);eq(port)
    emit(0x28,34);emit(0x15,0,'reject','accept')
    label('reverse');emit(0x20,26);eq(server);emit(0x20,30);eq(client)
    emit(0x28,34);eq(port);emit(0x28,36);emit(0x15,0,'reject','accept')
    label('accept');emit(0x06,42)
    label('reject');emit(0x06,0)
    result=[]
    for index,(op,jt,jf,k) in enumerate(code):
        jumps=[0 if target is None else labels[target]-index-1 for target in (jt,jf)]
        if any(not 0<=jump<=255 for jump in jumps):raise ValueError('Forward bounded cBPF jumps required')
        result.append((op,*jumps,k))
    return result


def evaluate(code,packet):
    """Test-only interpreter for the emitted cBPF subset; never a capture fallback."""
    a=x=pc=0;memory=[0]*16
    while pc<len(code):
        op,jt,jf,k=code[pc];pc+=1
        if op in (0x20,0x28,0x30):
            size={0x20:4,0x28:2,0x30:1}[op]
            if k+size>len(packet):return 0
            a=int.from_bytes(packet[k:k+size],'big')
        elif op==0x80:a=len(packet)
        elif op==0x02:memory[k]=a
        elif op==0x60:a=memory[k]
        elif op==0x61:x=memory[k]
        elif op==0x04:a=(a+k)&0xffffffff
        elif op==0x14:a=(a-k)&0xffffffff
        elif op==0x06:return k
        elif op in (0x15,0x35,0x45,0x2d,0x1d):
            condition={0x15:a==k,0x35:a>=k,0x45:bool(a&k),0x2d:a>x,0x1d:a==x}[op]
            pc+=jt if condition else jf
        else:raise ValueError('Unsupported test opcode')
    raise ValueError('cBPF missing return')


class Instruction(ctypes.Structure):
    _fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint)]
class Program(ctypes.Structure):
    _fields_=[('length',ctypes.c_ushort),('instructions',ctypes.POINTER(Instruction))]


def attach(sock,code):
    instructions=(Instruction*len(code))(*(Instruction(*row) for row in code))
    program=Program(len(code),instructions)
    sock.setsockopt(socket.SOL_SOCKET,SO_ATTACH_FILTER,bytes(program))


def open_capture(interface,code,*,synthetic=False):
    if sys.platform!='linux':raise RuntimeError('Linux kernel filtering required; no fallback')
    if not isinstance(interface,str) or not 1<=len(interface)<=15:raise ValueError('Explicit interface required')
    sock=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,0)
    try:
        attach(sock,code)
        sock.setsockopt(socket.SOL_SOCKET,SO_LOCK_FILTER,1)
        # Fail if the kernel did not make this filter immutable.
        try:attach(sock,code)
        except OSError as exc:
            if exc.errno!=errno.EPERM:raise
        else:raise RuntimeError('Kernel filter lock not enforced')
        sock.setsockopt(socket.SOL_SOCKET,SO_TIMESTAMPNS,1)
        if not synthetic:
            import fcntl
            hardware=fcntl.ioctl(sock,0x8927,struct.pack('256s',interface.encode()))
            if struct.unpack_from('H',hardware,16)[0]!=1:raise RuntimeError('Ethernet link layout required')
        # Protocol zero prevented reception before the attach/lock operations.
        sock.bind((interface,3));sock.settimeout(.05)
        return sock
    except BaseException:sock.close();raise


def receive_header(sock):
    buffer=bytearray(SNAPLEN)
    count,ancillary,flags,_=sock.recvmsg_into([buffer],128,socket.MSG_TRUNC)
    if count!=SNAPLEN or flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC):raise RuntimeError('Kernel truncation/layout proof failed')
    received_mono=time.monotonic_ns();received_wall=time.time_ns();kernel_ns=None
    for level,kind,data in ancillary:
        if level==socket.SOL_SOCKET and kind==SO_TIMESTAMPNS:
            if len(data)!=struct.calcsize('@ll'):raise RuntimeError('Unsupported kernel timestamp layout')
            seconds,nanos=struct.unpack('@ll',data)
            if not 0<=nanos<1000000000:raise RuntimeError('Invalid kernel timestamp')
            kernel_ns=seconds*1000000000+nanos
    if kernel_ns is None:raise RuntimeError('Kernel timestamp unavailable')
    return bytes(buffer),dict(local_kernel_wall_ns=kernel_ns,local_receive_monotonic_ns=received_mono,
        local_delivery_delay_ns=received_wall-kernel_ns if received_wall>=kernel_ns else None)


def metadata(header,client,server,port):
    client,server,port=flow(client,server,port)
    if len(header)!=42 or header[12:14]!=b'\x08\x00' or header[14]!=0x45 or header[23]!=17:
        raise ValueError('Unsupported header layout')
    total,identity,fragment=struct.unpack_from('!HHH',header,16)
    source,destination=struct.unpack_from('!II',header,26)
    sport,dport,length=struct.unpack_from('!HHH',header,34)
    if total<28 or length!=total-20 or fragment&0xbfff or not sport or not dport:raise ValueError('Inconsistent header')
    if source==client and destination==server and dport==port:direction='client_to_server';client_port=sport
    elif source==server and destination==client and sport==port:direction='server_to_client';client_port=dport
    else:raise ValueError('Foreign flow')
    return dict(direction=direction,client_port=client_port,ipid=identity,ip_length=total,udp_length=length,captured_header_bytes=42)


def statistics(sock):
    return dict(zip(('packets','drops'),struct.unpack('II',sock.getsockopt(SOL_PACKET,PACKET_STATISTICS,8))))


def vectors():
    """Synthetic frames only; payload sentinel is never printed or saved."""
    client='198.18.0.1';server='198.18.0.2';port=8781
    def frame(source=client,destination=server,sport=42001,dport=port):
        payload=b'SYNTHETIC_PAYLOAD_MUST_NOT_REACH_RECEIVER'*4
        ip=struct.pack('!BBHHHBBH4s4s',0x45,0,28+len(payload),42,0,64,17,0,
            socket.inet_aton(source),socket.inet_aton(destination))
        udp=struct.pack('!HHHH',sport,dport,8+len(payload),0)
        return b'\0'*12+b'\x08\x00'+ip+udp+payload
    good=frame();reverse=frame(server,client,port,42001)
    def change(packet,offset,data):return packet[:offset]+data+packet[offset+len(data):]
    invalid=dict(foreign_ip=frame(source='198.18.0.3'),wrong_server_port=frame(dport=port+1),
        wrong_direction=frame(server,client,42001,port),vlan=change(good,12,b'\x81\x00'),
        options=change(good,14,b'\x46'),ipv6=change(good,12,b'\x86\xdd'),
        more_fragments=change(good,20,b'\x20\x00'),fragment_offset=change(good,20,b'\x00\x01'),
        reserved_flag=change(good,20,b'\x80\x00'),short=good[:41],ip_overrun=change(good,16,b'\xff\xff'),
        ip_too_short=change(good,16,b'\x00\x1b'),udp_length_mismatch=change(good,38,b'\x00\x08'),
        tcp=change(good,23,b'\x06'),zero_client_port=change(good,34,b'\0\0'))
    return client,server,port,dict(forward=good,reverse=reverse),invalid


def kernel_preflight():
    client,server,port,accepted,rejected=vectors();code=compile_filter(client,server,port)
    capture=open_capture('lo',code,synthetic=True)
    sender=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,0);sender.bind(('lo',0))
    try:
        checks={};deadline=time.monotonic()+25;received=0
        for name,packet in {**accepted,**rejected}.items():
            # Drain only already kernel-truncated headers from earlier vectors.
            while time.monotonic()<deadline and received<2000:
                try:receive_header(capture);received+=1
                except socket.timeout:break
            if time.monotonic()>=deadline or received>=2000:raise RuntimeError('Synthetic preflight bounds exceeded')
            sender.send(packet);seen=0;until=min(deadline,time.monotonic()+.15)
            while time.monotonic()<until:
                try:
                    header,_=receive_header(capture)
                    metadata(header,client,server,port)
                    seen+=1;received+=1
                    if received>=2000:raise RuntimeError('Synthetic preflight record cap')
                except socket.timeout:pass
            if time.monotonic()>=deadline:raise RuntimeError('Synthetic preflight duration cap')
            checks[name]=(seen>0) if name in accepted else (seen==0)
        counts=statistics(capture)
        return dict(mode='synthetic_linux_kernel_header_preflight',accepted=all(checks.values()) and counts['drops']==0,
            checks=checks,statistics=counts,filter_locked=True,kernel_snaplen=42,raw_payload_retained=False)
    finally:sender.close();capture.close()


def observe(interface,client,server,port,*,duration=20,cap=2000):
    if type(duration) not in (int,float) or not .1<=duration<=25 or type(cap) is not int or not 1<=cap<=2000:
        raise ValueError('Explicit finite observer bounds required')
    code=compile_filter(client,server,port);capture=open_capture(interface,code)
    records=[];errors=[];clock_anomalies=0;start=time.monotonic()
    try:
        while time.monotonic()-start<duration and len(records)<cap:
            try:
                header,timing=receive_header(capture)
                if timing['local_delivery_delay_ns'] is None:clock_anomalies+=1
                records.append(dict(**metadata(header,client,server,port),**timing))
            except socket.timeout:continue
            except (RuntimeError,ValueError):errors.append('capture_proof_failed');break
        counts=statistics(capture)
    finally:capture.close()
    return dict(mode='finite_kernel_header_metadata',records=records,record_count=len(records),statistics=counts,
        elapsed_s=time.monotonic()-start,errors=errors,clock_anomalies=clock_anomalies,filter_locked=True,kernel_snaplen=42,record_cap_reached=len(records)==cap,
        observer_complete=not errors and not clock_anomalies and counts['drops']==0 and len(records)<cap,raw_payload_retained=False,
        delivery_proven=False,flow_ownership_verified=False,absence_inference_allowed=False,
        excluded_layouts_counted=False,layout='Ethernet/IPv4 IHL5/unfragmented UDP',
        timestamps_cross_host_comparable=False)
