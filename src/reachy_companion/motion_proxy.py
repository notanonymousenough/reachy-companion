"""Authenticated Agent boundary to a robot-local, sole-writer Unix service."""
import os
from pathlib import Path
import socket
import stat
import struct
from .autonomous.contracts import decode
import json


def receive(connection, limit):
    def exact(count):
        value = bytearray()
        while len(value) < count:
            part = connection.recv(count-len(value))
            if not part: raise RuntimeError('Native IPC completion unknown')
            value.extend(part)
        return bytes(value)
    size = struct.unpack('!I', exact(4))[0]
    if not 0 < size <= limit: raise ValueError('Native IPC bound')
    return decode(exact(size))


def send(connection, value):
    body = json.dumps(value, allow_nan=False).encode()
    if len(body) > 16384: raise ValueError('Native IPC bound')
    connection.sendall(struct.pack('!I',len(body))+body)


class MotionProxy:
    def __init__(self, enabled, socket_path, operator):
        self.enabled, self.socket_path, self.operator = enabled, Path(socket_path), operator

    def ipc(self, value):
        info = self.socket_path.stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise RuntimeError('Native socket ownership unknown')
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(.8)
            connection.connect(str(self.socket_path))
            if hasattr(socket,'SO_PEERCRED'):
                pid, uid, _ = struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                if uid != os.getuid(): raise RuntimeError('Native peer ownership unknown')
            send(connection,value)
            result=receive(connection,16384)
            if hasattr(socket,'SO_PEERCRED') and (not isinstance(result,dict) or result.get('writer_pid')!=pid):
                raise RuntimeError('Native peer receipt mismatch')
            return result

    def status(self):
        if not self.enabled: return dict(enabled=False,ready=False,reason='guarded_motion_disabled')
        try:
            value = self.ipc({'kind':'status'})
            if (not isinstance(value,dict) or value.get('owner_verified') is not True
                    or value.get('kernel_exclusive') is not True):
                raise RuntimeError('Native ownership receipt unknown')
            return dict(value,enabled=True)
        except Exception: return dict(enabled=True,ready=False,reason='native_runtime_unavailable')

    def handle(self, envelope):
        if not self.enabled: raise RuntimeError('Guarded motion disabled')
        if set(envelope) != {'command_id','hub_boot_id','path','payload'} or envelope['path'] != '/native/antenna':
            raise ValueError('Only typed bounded antenna commands are supported')
        for key in ('command_id','hub_boot_id'):
            if not isinstance(envelope[key],str) or not 1 <= len(envelope[key]) <= 128: raise ValueError('Command identity')
        payload = envelope['payload']
        operator = self.operator()
        if (not isinstance(payload,dict) or payload.get('agent_boot_id') != operator['agent_boot_id']
                or type(payload.get('operator_epoch')) is not int
                or payload['operator_epoch'] != operator['microphone_epoch']):
            raise RuntimeError('Stale Agent/operator binding')
        value = self.ipc(envelope)
        if (not isinstance(value,dict) or value.get('command_id') != envelope['command_id']
                or value.get('hub_boot_id') != envelope['hub_boot_id']):
            raise RuntimeError('Native IPC receipt mismatch')
        return value
