"""Local actor ownership and expiring leases; no hardware adapter is enabled here.

The file lock fences cooperating writers only. Native daemon SDK writers need a
separate verified deployment fence before a physical adapter may be attached.
"""
from dataclasses import asdict, dataclass
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import sqlite3
import threading
import time
from .contracts import Authority, uid


class GuardRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class Lease:
    lease_id: str
    authority: Authority


class OutputGate:
    """RAM output lease; its watchdog never acquires the SQLite owner's mutex.

    enqueue and stop must be bounded adapter operations, with no storage/model
    work or calls back into ActuatorGuard. This removes disk contention, not
    arbitrary callback/OS latency. Physical adapter admission remains gated.
    """
    def __init__(self,stop,clock,poll):
        self.stop,self.clock,self.poll=stop,clock,poll
        self.mutex=threading.RLock();self.lease=None;self.deadline=0
        self.last_stopped=None;self.known=True;self.max_enqueue_s=0
        self.done=threading.Event()
        self.thread=threading.Thread(target=self.watchdog,name='output-watchdog',daemon=True);self.thread.start()

    def arm(self,lease,deadline):
        with self.mutex:
            if self.lease or not self.known or self.clock()>=deadline:raise GuardRejected('Output lease gate')
            self.lease=lease;self.deadline=deadline

    def live(self,lease):
        with self.mutex:return self.lease==lease and self.clock()<self.deadline

    def extend(self,lease,deadline):
        with self.mutex:
            if not self.live(lease):raise GuardRejected('Output lease cannot be revived')
            self.deadline=deadline

    def enqueue(self,lease,enqueue):
        with self.mutex:
            if not self.live(lease):raise GuardRejected('Output withdrawn before enqueue')
            started=time.monotonic()
            try:
                if enqueue() is not True:raise GuardRejected('Enqueue completion unknown')
            finally:self.max_enqueue_s=max(self.max_enqueue_s,time.monotonic()-started)
            if not self.live(lease):raise GuardRejected('Enqueue exceeded live lease')

    def revoke(self,lease):
        with self.mutex:
            if lease==self.last_stopped:return self.known
            if self.lease is not None and self.lease!=lease:return False
            self.lease=None
            try:self.known=self.stop() is True
            except Exception:self.known=False
            self.last_stopped=lease
            return self.known

    def acknowledge(self):
        with self.mutex:
            if self.lease:raise GuardRejected('Output still leased')
            self.known=True

    def watchdog(self):
        while not self.done.wait(self.poll):
            with self.mutex:
                if self.lease and self.clock()>=self.deadline:self.revoke(self.lease)

    def close(self):
        self.done.set();self.thread.join(timeout=self.poll+1)


class ActuatorGuard:
    """One process owner, one lease, bounded durable command dedupe.

    stop must stop AND verify the adapter's outputs; False/exception means
    execution unknown. No LLM or network roundtrip runs in the watchdog.
    Deadlines always use this process's monotonic clock, never caller clocks.
    """
    def __init__(self, directory, stop, *, clock=time.monotonic, ttl=.5, poll=.05):
        if not .01 <= ttl <= .5 or not .005 <= poll <= .1:
            raise ValueError('Lease/watchdog exceed bounds')
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock_file = (self.directory/'owner.lock').open('a+b')
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            raise GuardRejected('Another local owner is running') from None
        self.db = sqlite3.connect(self.directory/'guard.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), value TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, lease_id TEXT NOT NULL)')
        self.mutex = threading.RLock()
        self.clock, self.ttl, self.poll, self.stop = clock, ttl, poll, stop
        self.robot_boot_id = uid()
        row = self.db.execute('SELECT value FROM state WHERE singleton=1').fetchone()
        old = json.loads(row[0]) if row else {}
        # A crashed active/stopping owner cannot prove hardware completion.
        self.quarantined = old.get('status') in ('active', 'stopping', 'quarantined')
        self.lease = None
        self.deadline = 0
        self.sequence = -1
        self.closed = False
        self.max_durable_transaction_s = 0
        self.max_stop_call_s = 0
        self.write('quarantined' if self.quarantined else 'idle')
        self.output=OutputGate(self.stop_output,clock,poll)
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.watchdog, name='actor-watchdog', daemon=True)
        self.thread.start()

    def write(self, status):
        value = json.dumps(dict(status=status, robot_boot_id=self.robot_boot_id,
                               lease=asdict(self.lease) if self.lease else None))
        with self.transaction():
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1, ?)', (value,))

    @contextmanager
    def transaction(self):
        started = time.monotonic()
        try:
            with self.db:
                yield
        finally:
            self.max_durable_transaction_s = max(self.max_durable_transaction_s, time.monotonic()-started)

    def arm(self, authority, *, microphone_enabled, quiet, privacy_all, fence_attested):
        with self.mutex:
            if (self.closed or self.quarantined or self.lease or fence_attested is not True
                    or microphone_enabled is not True or quiet is not False or privacy_all is not False
                    or authority.robot_boot_id != self.robot_boot_id):
                raise GuardRejected('Owner/operator/boot gate not satisfied')
            self.lease = Lease(uid(), authority)
            self.deadline = self.clock()+self.ttl
            self.sequence = -1
            # Tombstones survive lease/boot changes. Re-arming cannot replay an
            # already admitted command under freshly rebound authority.
            self.write('active')
            try:self.output.arm(self.lease,self.deadline)
            except GuardRejected:
                self.revoke_locked();raise
            return self.lease

    def check(self, lease):
        if self.closed or self.quarantined or not self.lease or lease != self.lease:
            raise GuardRejected('Lease/authority no longer current')
        if self.clock() >= self.deadline or not self.output.live(lease):
            self.revoke_locked()
            raise GuardRejected('Lease expired')

    def heartbeat(self, lease, sequence):
        with self.mutex:
            self.check(lease)
            if type(sequence) is not int or not 0 <= sequence <= 2**63-1 or sequence <= self.sequence:
                raise GuardRejected('Heartbeat sequence not fresh')
            self.sequence = sequence
            deadline = self.clock()+self.ttl
            self.output.extend(lease,deadline)
            self.deadline = deadline

    def admit(self, lease, command_id):
        """Persist intent BEFORE dispatch. Duplicate returns False, never replay.

        This only authorizes a future adapter dispatch; it does not move/speak.
        Physical adapters must use dispatch for the final output lease fence.
        This legacy intent API alone does not authorize external SDK writes.
        """
        with self.mutex:
            self.check(lease)
            if not isinstance(command_id, str) or not 1 <= len(command_id) <= 128:
                raise ValueError('Invalid command ID')
            if self.db.execute('SELECT 1 FROM commands WHERE id=?', (command_id,)).fetchone():
                return False
            if self.db.execute('SELECT count(*) FROM commands').fetchone()[0] >= 256:
                self.revoke_locked()
                raise GuardRejected('Dedupe capacity exhausted; no eviction/replay')
            with self.transaction():
                self.db.execute('INSERT INTO commands VALUES (?, ?)', (command_id, lease.lease_id))
            self.check(lease)
            return True

    def dispatch(self,lease,command_id,enqueue):
        """Persist intent, then atomically fence bounded enqueue with output lease.

        No SQLite lock is held during enqueue; the independent output watchdog
        can stop while admission is blocked on fsync. No direct SDK I/O here.
        """
        if not self.admit(lease,command_id):return False
        try:self.output.enqueue(lease,enqueue)
        except BaseException:
            self.revoke();raise
        return True

    def stop_output(self):
        started=time.monotonic()
        try:return self.stop() is True
        finally:self.max_stop_call_s=max(self.max_stop_call_s,time.monotonic()-started)

    def revoke_locked(self):
        if not self.lease:
            return
        # The durable row is already active: crash at any point means unknown.
        # Stop before additional fsync so storage failure cannot skip stopping.
        lease=self.lease;self.lease = None
        self.quarantined = True
        known = self.output.revoke(lease)
        self.quarantined = not known
        try:
            self.write('quarantined' if self.quarantined else 'idle')
        except sqlite3.Error:
            # Old durable active row forces quarantine on restart as well.
            self.quarantined = True

    def revoke(self):
        with self.mutex:
            self.revoke_locked()

    def acknowledge_stopped(self, *, verified_stopped):
        """Trusted operator audit only; never exposed as a model tool."""
        with self.mutex:
            if self.closed or self.lease or verified_stopped is not True:
                raise GuardRejected('Stop audit not verified')
            self.quarantined = False
            self.output.acknowledge()
            self.write('idle')

    def watchdog(self):
        while not self.done.wait(self.poll):
            with self.mutex:
                if self.lease and (self.clock() >= self.deadline or not self.output.live(self.lease)):
                    self.revoke_locked()

    def status(self):
        with self.mutex:
            if self.lease and not self.output.live(self.lease):self.revoke_locked()
            return dict(robot_boot_id=self.robot_boot_id, quarantined=self.quarantined,
                        leased=self.lease is not None, closed=self.closed,
                        max_durable_transaction_s=self.max_durable_transaction_s,
                        max_stop_call_s=self.max_stop_call_s,max_enqueue_s=self.output.max_enqueue_s)

    def close(self):
        self.done.set()
        self.thread.join(timeout=self.poll+1)
        with self.mutex:
            if self.closed:
                return
            self.revoke_locked()
            self.output.close()
            self.closed = True
            self.db.close()
            fcntl.flock(self.lock_file, fcntl.LOCK_UN)
            self.lock_file.close()
