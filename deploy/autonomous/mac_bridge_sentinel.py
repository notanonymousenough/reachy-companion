"""Bounded health observations of an existing Mac bridge; never reconnect/rearm.

A failed read is health UNKNOWN, not proof of SSH loss. The reverse listener
socket inode is pinned by the sole transport owner before this process starts.
"""
import argparse
from collections import Counter, deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler


class LinkLost(Exception):
    pass


class IdentityMismatch(Exception):
    pass


def listener_identity():
    # Linux kernel socket identity: does not require reading keys/process env.
    entries = []
    for row in Path('/proc/net/tcp').read_text().splitlines()[1:]:
        fields = row.split()
        if fields[1] == '0100007F:46B1' and fields[3] == '0A':  # 127.0.0.1:18097
            entries.append(fields[9])
    if not entries:
        raise LinkLost()
    if len(entries) != 1:
        raise IdentityMismatch()
    return {'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'listener_inode': entries[0]}


def check_identity(expected):
    if listener_identity() != expected:
        raise IdentityMismatch()


def health_read(opener):
    status = None
    try:
        with opener.open('http://127.0.0.1:18097/health', timeout=.4) as response:
            status = response.status
            raw = response.read(4097)
        if len(raw) > 4096 or json.loads(raw) != {'status': 'ok'}:
            return {'ok': False, 'error': 'invalid_health', 'status': status}
        return {'ok': True, 'error': None, 'status': status}
    except (OSError, ValueError, HTTPError, URLError) as exc:
        # Exception messages/HTTP bodies may contain content: never persist them.
        reason = getattr(exc, 'reason', None)
        return {'ok': False, 'error': type(exc).__name__,
                'cause': type(reason).__name__ if reason is not None else None,
                'status': getattr(exc, 'code', status)}


class Monitor:
    def __init__(self, identity, probe, persist, ready, *, clock=time.monotonic,
                 budget=3., interval=.2):
        self.identity, self.probe, self.persist, self.ready = identity, probe, persist, ready
        self.clock, self.budget, self.interval = clock, budget, interval
        self.start = clock()
        self.unavailable_at = None
        self.is_ready = False
        self.counts = Counter()
        self.recent = deque(maxlen=16)
        self.last_write = float('-inf')
        self.state = 'STARTING'
        self.terminal = None
        self.max_latency_s = 0.
        self.last_failure = None
        self.unavailable_total_s = 0.

    def snapshot(self):
        now = self.clock()
        return dict(version=1, utc=datetime.now(timezone.utc).isoformat(),
                    elapsed_s=now-self.start, state=self.state, terminal=self.terminal,
                    counts=dict(self.counts), recent=list(self.recent),
                    max_latency_s=self.max_latency_s, last_failure=self.last_failure,
                    unavailable_total_s=self.unavailable_total_s + (0 if self.unavailable_at is None else now-self.unavailable_at),
                    unavailable_s=0 if self.unavailable_at is None else now-self.unavailable_at,
                    unavailable_budget_s=self.budget, ready=self.is_ready)

    def save(self, force=False):
        now = self.clock()
        if force or now-self.last_write >= 5:
            self.persist(self.snapshot())
            self.last_write = now

    def step(self):
        before = self.clock()
        previous = self.state
        try:
            self.identity()
            result = self.probe()
            self.identity()  # A response cannot certify a replaced listener.
        except (LinkLost, IdentityMismatch) as exc:
            self.state, self.terminal = 'TERMINAL', type(exc).__name__
            self.counts[self.terminal] += 1
            self.save(True)
            return False
        now = self.clock()
        latency = now-before
        self.max_latency_s = max(self.max_latency_s, latency)
        self.counts['reads'] += 1
        receipt = dict(elapsed_s=now-self.start, latency_s=latency,
                       status=result.get('status'), error=result.get('error'),
                       cause=result.get('cause'))
        self.recent.append(receipt)
        if result['ok']:
            self.counts['ok'] += 1
        else:
            self.counts['read_failures'] += 1
            self.counts[result['error']] += 1
            self.last_failure = receipt
            if self.unavailable_at is None:
                self.unavailable_at = before
        if self.unavailable_at is not None and now-self.unavailable_at >= self.budget:
            self.state, self.terminal = 'TERMINAL', 'health_unavailable_budget'
        elif result['ok']:
            if self.unavailable_at is not None:
                self.counts['recoveries'] += 1
                self.unavailable_total_s += now-self.unavailable_at
            self.unavailable_at = None
            self.state = 'HEALTHY'
            if not self.is_ready:
                self.ready()
                self.is_ready = True
        else:
            self.state = 'HEALTH_UNAVAILABLE'
        self.save(self.state != previous)
        return self.terminal is None


def atomic_save(path, value):
    raw = json.dumps(value, separators=(',', ':')).encode()
    if len(raw) > 16384:
        raise ValueError('Bounded sentinel metadata required')
    temporary = path.with_name(path.name+'.tmp')
    fd = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw)
    os.replace(temporary, path)


def notify_ready():
    address = os.environ['NOTIFY_SOCKET']
    if address.startswith('@'):
        address = '\0'+address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notify:
        notify.connect(address)
        notify.sendall(b'READY=1\nSTATUS=Pinned Mac reverse listener; fresh backend health observed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    args = parser.parse_args()
    raw = args.identity.read_bytes()
    if len(raw) > 1024:
        raise ValueError('Bounded bridge identity required')
    expected = json.loads(raw)
    if set(expected) != {'boot', 'listener_inode'}:
        raise ValueError('Exact bridge identity required')
    opener = build_opener(ProxyHandler({}))
    monitor = Monitor(lambda: check_identity(expected), lambda: health_read(opener),
                      lambda value: atomic_save(args.metadata, value), notify_ready)
    while monitor.step():
        time.sleep(monitor.interval)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
