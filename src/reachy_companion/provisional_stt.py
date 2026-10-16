"""Opt-in rolling-window STT: no intent, action, model reply or conversation memory.

One shared strict wire contract. The client owns one active request and one
latest pending snapshot. Windows are re-decoded, not native online Whisper.
"""
import base64
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import time
from uuid import uuid4

MIN_FRAMES = 6400
WINDOW_FRAMES = 64000
CADENCE = .5
TTL = 2.
MAX_TEXT = 1600
MAX_REQUEST = 180000
MAX_RESPONSE = 8192
BINDING_FIELDS = frozenset(('boot', 'microphone_epoch', 'policy_epoch', 'source_generation',
    'utterance_id', 'revision', 'request_id', 'window_start_frame', 'window_frames'))


def require(value):
    if not value:
        raise ValueError('Invalid provisional STT contract')


def enabled(config):
    value = config['conversation'].get('provisional_stt_enabled', False)
    require(type(value) is bool)
    return value


def binding(value):
    require(type(value) is dict and set(value) == BINDING_FIELDS)
    require(type(value['boot']) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', value['boot']) is not None)
    require(type(value['request_id']) is str and re.fullmatch('[0-9a-f]{32}', value['request_id']) is not None)
    for key in BINDING_FIELDS - {'boot', 'request_id'}:
        minimum = 1 if key in ('source_generation', 'utterance_id', 'revision') else 0
        require(type(value[key]) is int and minimum <= value[key] < 2**63)
    require(MIN_FRAMES <= value['window_frames'] <= WINDOW_FRAMES)
    return dict(value)


def unique(pairs):
    result = {}
    for key, item in pairs:
        require(key not in result)
        result[key] = item
    return result


def constant(_):
    raise ValueError('Non-finite provisional STT JSON')


def decode(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=constant)


def request(value):
    require(type(value) is dict and set(value) == {'mode', 'version', 'binding', 'pcm_base64'})
    require(value['mode'] == 'recognize_only' and type(value['version']) is int and value['version'] == 1)
    bound = binding(value['binding'])
    encoded = value['pcm_base64']
    require(type(encoded) is str and len(encoded) <= (WINDOW_FRAMES*2+2)//3*4)
    try:
        pcm = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError('Invalid provisional PCM') from None
    require(len(pcm) == bound['window_frames']*2)
    return bound, pcm


def parse_request(raw):
    value = decode(raw, MAX_REQUEST)
    request(value)
    return value


def response(value, expected):
    require(type(value) is dict and set(value) == {'mode', 'version', 'binding', 'provisional', 'status', 'text'})
    require(value['mode'] == 'recognize_only' and type(value['version']) is int and value['version'] == 1
            and value['provisional'] is True and value['status'] in ('recognized', 'busy'))
    require(binding(value['binding']) == binding(expected))
    require(type(value['text']) is str and len(value['text']) <= MAX_TEXT)
    require(value['status'] != 'busy' or value['text'] == '')
    return dict(value, binding=dict(value['binding']))


def recognize_only(pipeline, payload):
    """Called before Pipeline.transcribe/classify; only the loaded recognizer."""
    require(enabled(pipeline.config))
    bound, pcm = request(payload)
    require(type(pipeline.config['audio']['sample_rate']) is int
            and pipeline.config['audio']['sample_rate'] == 16000)
    require(getattr(pipeline.stt, 'loaded_backend', None) == 'faster_whisper'
            and pipeline.stt.settings['backend'] == pipeline.stt.loaded_backend)
    text = pipeline.stt.transcribe_provisional(pcm)
    result = dict(mode='recognize_only', version=1, binding=bound, provisional=True,
                  status='busy' if text is None else 'recognized', text='' if text is None else text)
    return response(result, bound)


def prepare_transport(url):
    """Reuse the existing owned socket/deadline helper; no application imports."""
    from .owned_http import prepare
    return prepare(url)


def complete_body(incoming, deadline):
    """Accept only a complete, bounded HTTP message, never a valid JSON prefix."""
    lengths = incoming.headers.get_all('Content-Length', [])
    transfers = incoming.headers.get_all('Transfer-Encoding', [])
    # The selected JSON worker emits Content-Length. Reject transfer coding:
    # stdlib chunk parsing tolerates an EOF without the final trailer CRLF.
    require(len(lengths) <= 1 and not transfers and not incoming.chunked)
    if lengths:
        require(re.fullmatch('[0-9]{1,8}', lengths[0]) is not None and not incoming.chunked)
        expected = int(lengths[0])
        require(0 < expected <= MAX_RESPONSE)
        raw = incoming.read(expected+1)
        require(len(raw) == expected and incoming.length == 0)
    else:
        raw = incoming.read(MAX_RESPONSE+1)
        require(len(raw) <= MAX_RESPONSE and incoming.read(1) == b'' and incoming.isclosed())
    require(time.monotonic() < deadline)
    return raw


def exchange(agent, target, payload, deadline):
    from urllib.request import Request
    from .owned_http import owned_response
    url = agent.config['network']['voice_url'].rstrip('/')+'/transcribe'
    item = Request(url, data=json.dumps(payload).encode(), headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer '+agent.config.token})
    with owned_response(item, deadline, target) as incoming:
        require(incoming.headers.get_content_type() == 'application/json')
        raw = complete_body(incoming, deadline)
        result = decode(raw, MAX_RESPONSE)
        require(time.monotonic() < deadline)
    return response(result, payload['binding'])


@dataclass(frozen=True)
class Snapshot:
    binding: dict
    pcm: bytes
    received_end: float
    deadline: float


class IntentLatch:
    """Durable unknown across reload; no audio/text, no automatic recovery."""
    def __init__(self, path, *, clock=time.monotonic):
        self.path = Path(path)
        require(self.path.is_absolute() and '..' not in self.path.parts)
        self.clock = clock
        self.identity = None
        self.parent_identity = None
        self.sha256 = None
        self.request_id = None
        self.deadline = None

    def parent(self):
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open('/', flags)
        try:
            for component in self.path.parent.parts[1:]:
                following = os.open(component, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = following
            observed = os.fstat(descriptor)
            require(stat.S_ISDIR(observed.st_mode) and observed.st_uid == os.getuid()
                    and observed.st_mode & 0o022 == 0)
            if self.parent_identity is not None:
                require(self.parent_identity == (observed.st_dev, observed.st_ino))
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def exists(self):
        directory = self.parent()
        try:
            try: os.stat(self.path.name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError: return False
            return True  # Includes symlinks and malformed markers: never adopt.
        finally:
            os.close(directory)

    @contextmanager
    def namespace(self, deadline, permitted=None):
        """Cooperative namespace guard on the fixed parent inode, not a lockfile.

        All supported begin/complete and future reviewed recovery mutations must
        hold this same directory flock. It cannot serialize arbitrary same-UID
        writes that ignore the protocol or replace the protected parent itself.
        """
        import fcntl
        require(type(deadline) in (int, float) and math.isfinite(deadline))
        directory = self.parent()
        try:
            while True:
                self.allowed(deadline, permitted)
                try:
                    fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(min(.01, max(0., deadline-self.clock())))
            try:
                # Recheck the pathname after waiting: never switch lock domains.
                current = self.parent()
                try:
                    held, observed = os.fstat(directory), os.fstat(current)
                    require((held.st_dev, held.st_ino) == (observed.st_dev, observed.st_ino))
                finally:
                    os.close(current)
                self.allowed(deadline, permitted)
                yield directory
            finally:
                fcntl.flock(directory, fcntl.LOCK_UN)
        finally:
            os.close(directory)

    def allowed(self, deadline, permitted):
        if self.clock() >= deadline or (permitted is not None and permitted() is not True):
            raise TimeoutError('Original provisional intent authority expired')

    def begin(self, bound, received_end, deadline, *, permitted=None):
        require(self.identity is None)
        require(type(received_end) in (int, float) and type(deadline) in (int, float)
                and math.isfinite(received_end) and math.isfinite(deadline)
                and 0 <= received_end < deadline <= received_end+TTL)
        bound = binding(bound)
        raw = json.dumps(dict(kind='provisional-stt-inflight', version=1,
            target_class='voice_transcribe_recognize_only', request_id=bound['request_id'],
            binding=bound, received_end=received_end, deadline=deadline), sort_keys=True).encode()
        require(len(raw) <= 2048)
        with self.namespace(deadline, permitted) as directory:
            parent = os.fstat(directory)
            self.parent_identity = (parent.st_dev, parent.st_ino)
            descriptor = os.open(self.path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            try:
                self.deadline = deadline
                with os.fdopen(descriptor, 'wb', closefd=False) as file:
                    file.write(raw); file.flush(); os.fsync(descriptor)
                observed = os.fstat(descriptor)
                require(stat.S_ISREG(observed.st_mode) and stat.S_IMODE(observed.st_mode) == 0o600
                        and observed.st_nlink == 1 and observed.st_uid == os.getuid())
                self.identity = (observed.st_dev, observed.st_ino, observed.st_size)
                self.sha256 = hashlib.sha256(raw).hexdigest()
                self.request_id = bound['request_id']
                os.fsync(directory)
            finally:
                os.close(descriptor)

    def complete(self, deadline=None, *, permitted=None):
        require(self.identity is not None and self.request_id is not None)
        deadline = self.deadline if deadline is None else deadline
        require(type(deadline) in (int, float) and deadline == self.deadline)
        with self.namespace(deadline, permitted) as directory:
            descriptor = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            try:
                observed = os.fstat(descriptor)
                require(stat.S_ISREG(observed.st_mode) and stat.S_IMODE(observed.st_mode) == 0o600
                        and observed.st_nlink == 1 and observed.st_uid == os.getuid()
                        and self.identity == (observed.st_dev, observed.st_ino, observed.st_size))
                raw = os.read(descriptor, 2049)
                require(hashlib.sha256(raw).hexdigest() == self.sha256)
                value = decode(raw, 2048)
                require(value['request_id'] == self.request_id
                        and binding(value['binding'])['request_id'] == self.request_id)
            finally:
                os.close(descriptor)
            current = os.stat(self.path.name, dir_fd=directory, follow_symlinks=False)
            require(self.identity == (current.st_dev, current.st_ino, current.st_size))
            self.allowed(deadline, permitted)
            os.unlink(self.path.name, dir_fd=directory)
            os.fsync(directory)
            self.identity = self.sha256 = self.request_id = self.deadline = None


class ProvisionalClient:
    def __init__(self, agent, pump, fresh, *, clock=time.monotonic, transport=None, latch=None):
        self.agent = agent
        self.pump = pump
        self.fresh = fresh
        self.clock = clock
        self.latch = latch or IntentLatch(agent.config.path(agent.config['paths']['data_dir'])/'provisional-stt-inflight.json', clock=clock)
        if self.latch.exists():
            agent._provisional_unknown = True
        if transport is None:
            target = prepare_transport(agent.config['network']['voice_url'].rstrip('/')+'/transcribe')
            transport = lambda payload, deadline: exchange(agent, target, payload, deadline)
        self.transport = transport
        self.condition = threading.Condition()
        self.thread = None
        self.stopped = False
        self.pending = None
        self.active = False
        self.work_resolved = True
        self.number = self.revision = self.closed_number = 0
        self.next_at = 0.
        self.latest = self.previous = None

    def start(self):
        with self.condition:
            if self.thread is None and not self.stopped and not getattr(self.agent, '_provisional_unknown', False):
                self.thread = threading.Thread(target=self.run, name='reachy-provisional-stt', daemon=True)
                self.thread.start()

    def begin(self, number):
        require(type(number) is int and 1 <= number < 2**63)
        with self.condition:
            if number != self.number:
                self.number = number
                self.revision = 0
                self.next_at = 0.
                self.pending = self.latest = self.previous = None

    def offer(self, number, pcm, received_end, window_start_frame):
        require(type(pcm) is bytes and len(pcm) % 2 == 0)
        require(type(received_end) in (int, float) and math.isfinite(received_end) and received_end >= 0)
        with self.condition:
            if (self.stopped or getattr(self.agent, '_provisional_unknown', False)
                    or number != self.number or number <= self.closed_number or received_end < self.next_at):
                return False
            self.revision += 1
            boot, mic, policy = self.pump.binding
            bound = dict(boot=boot, microphone_epoch=mic, policy_epoch=policy,
                source_generation=self.pump.generation, utterance_id=number, revision=self.revision,
                request_id=uuid4().hex,
                window_start_frame=window_start_frame, window_frames=len(pcm)//2)
            binding(bound)
            self.pending = Snapshot(bound, pcm, received_end, received_end+TTL)
            self.latest = None
            self.next_at = received_end+CADENCE
            if self.thread is None: self.start()
            self.condition.notify_all()
            return True

    def due(self, number, received_end):
        with self.condition:
            return (not self.stopped and not getattr(self.agent, '_provisional_unknown', False)
                    and number == self.number and number > self.closed_number and received_end >= self.next_at)

    def endpoint(self, number):
        with self.condition:
            self.closed_number = max(self.closed_number, number)
            self.pending = self.latest = self.previous = None
            self.condition.notify_all()

    def retire(self):
        with self.condition:
            if self.active and not self.work_resolved:
                self.agent._provisional_unknown = True
            self.stopped = True
            self.pending = self.latest = self.previous = None
            self.condition.notify_all()

    def close(self):
        self.retire()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(TTL+.5)
            if self.thread.is_alive():
                raise RuntimeError('Provisional STT consumer did not stop')

    def current(self, item):
        # Called only under client condition; never calls back into the pump.
        return (not self.stopped and item.binding['utterance_id'] == self.number
                and self.number > self.closed_number and item.binding['revision'] == self.revision)

    def input_permitted(self, item):
        with self.condition:
            current = self.current(item)
        return current and self.fresh(item)

    def resolved(self):
        with self.condition:
            self.work_resolved = True
            self.agent._provisional_unknown = False

    def metrics(self):
        with self.condition:
            latest = self.latest
            return dict(agent_boot_id=self.pump.binding[0], microphone_epoch=self.pump.binding[1],
                policy_epoch=self.pump.binding[2], source_generation=self.pump.generation,
                active=self.active, pending=self.pending is not None,
                unknown=getattr(self.agent, '_provisional_unknown', False),
                utterance_id=self.number, revision=self.revision,
                accepted_revision=None if latest is None else latest['binding']['revision'],
                text_chars=0 if latest is None else len(latest['text']),
                stable_prefix_chars=0 if latest is None else len(latest['stable_prefix']),
                received_end=None if latest is None else latest['received_end'],
                accepted_at=None if latest is None else latest['accepted_at'])

    def run(self):
        while True:
            with self.condition:
                while self.pending is None and not self.stopped:
                    self.condition.wait(.05)
                if self.stopped:
                    return
                item, self.pending = self.pending, None
                self.active = True
                self.work_resolved = False
            try:
                if not self.fresh(item):
                    continue
                with self.condition:
                    if not self.current(item):
                        continue
                payload = dict(mode='recognize_only', version=1, binding=item.binding,
                               pcm_base64=base64.b64encode(item.pcm).decode('ascii'))
                self.latch.begin(item.binding, item.received_end, item.deadline,
                                 permitted=lambda: self.input_permitted(item))
                cleanup_permitted = lambda: self.latch.request_id == item.binding['request_id']
                with self.condition:
                    current = self.current(item)
                if not current or not self.fresh(item):
                    # Intent was durable but no POST occurred. Only this owned
                    # marker may be removed; no unknown request is retried.
                    self.latch.complete(item.deadline, permitted=cleanup_permitted)
                    self.resolved()
                    continue
                result = response(self.transport(payload, item.deadline), item.binding)
                self.latch.complete(item.deadline, permitted=cleanup_permitted)
                self.resolved()
                if not self.fresh(item):
                    continue
                with self.condition:
                    if not self.current(item):
                        continue
                    if result['status'] == 'busy':
                        self.latest = self.previous = None
                        continue
                    key = (self.number, item.binding['window_start_frame'])
                    stable = []
                    if (self.previous is not None and self.previous[0] == key
                            and self.previous[2]+1 == item.binding['revision']):
                        for before, after in zip(self.previous[1].split(), result['text'].split()):
                            if before != after:
                                break
                            stable.append(after)
                    self.previous = (key, result['text'], item.binding['revision'])
                    self.latest = dict(binding=dict(item.binding), text=result['text'],
                        stable_prefix=' '.join(stable), received_end=item.received_end, accepted_at=self.clock())
            except Exception:
                # Unknown completion never gets a retry, including after a new
                # capture source generation. Explicit process recovery is needed.
                self.agent._provisional_unknown = True
                self.retire()
            finally:
                with self.condition:
                    self.active = False
                    self.condition.notify_all()
