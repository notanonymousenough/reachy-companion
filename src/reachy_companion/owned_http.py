"""Pure owned HTTP transport derived from the accepted a4aa socket watchdog.

Resolved target is explicit; no endpoint registry, model producer or app imports.
"""
from contextlib import contextmanager
import http.client
import socket
import threading
import time
from urllib.parse import urlsplit


def need(value):
    if not value:raise ValueError('Invalid bounded HTTP request')


def prepare(url):
    endpoint=urlsplit(url)
    need(endpoint.scheme=='http' and endpoint.hostname and not endpoint.username and not endpoint.password
         and not endpoint.query and not endpoint.fragment)
    addresses=socket.getaddrinfo(endpoint.hostname,endpoint.port or 80,type=socket.SOCK_STREAM)
    need(0<len(addresses)<=32)
    return url,endpoint,tuple(addresses)


@contextmanager
def owned_response(request,deadline,target,submitted=None):
    """Absolute watchdog owns the socket before connect, headers and body."""
    need(request.full_url == target[0])
    endpoint,addresses=target[1:]
    remaining=deadline-time.monotonic();need(remaining>0)
    connection=http.client.HTTPConnection(endpoint.hostname,endpoint.port or 80,timeout=remaining)
    lock=threading.Lock();holder=[None];expired=threading.Event();response=None
    def abort():
        with lock:
            expired.set();sock=holder[0]
            if sock is not None:
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
                try:sock.close()
                except OSError:pass
    timer=threading.Timer(remaining,abort);timer.daemon=True;timer.start()
    try:
        for family,kind,protocol,_,address in addresses:
            remaining=deadline-time.monotonic();need(remaining>0 and not expired.is_set())
            sock=socket.socket(family,kind,protocol);sock.settimeout(remaining)
            with lock:
                if expired.is_set() or time.monotonic()>=deadline:sock.close();raise TimeoutError('Owned request expired')
                holder[0]=sock;connection.sock=sock
            try:sock.connect(address);break
            except OSError:
                with lock:sock.close();connection.sock=None
        else:raise OSError('Owned endpoint unavailable')
        need(time.monotonic()<deadline and not expired.is_set())
        if submitted is not None:submitted()
        connection.request('POST',endpoint.path or '/',body=request.data,headers=dict(request.header_items()))
        response=connection.getresponse()
        need(response.status==200 and time.monotonic()<deadline and not expired.is_set())
        yield response
    finally:
        timer.cancel();timer.join()
        if response is not None:response.close()
        connection.close()
        with lock:sock=holder[0]
        if sock is not None:sock.close()

