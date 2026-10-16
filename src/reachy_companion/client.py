import json
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
import time
import uuid
import http.client
from urllib.parse import urlsplit


def request(config, url, payload=None, timeout=None):
    item = Request(url, data=None if payload is None else json.dumps(payload).encode(),
                   headers={'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + config.token})
    with build_opener(ProxyHandler({})).open(item, timeout=timeout or config['timeouts']['client']) as response:
        return json.load(response)


def guarded_control(config, base, path, payload, expected):
    """Preconnect/serialize, then reread authority and guard every socket send."""
    endpoint = urlsplit(base)
    if endpoint.scheme not in ('http', 'https') or endpoint.query or endpoint.fragment or endpoint.username:
        raise ValueError('Direct Hub HTTP endpoint required')
    parent = http.client.HTTPSConnection if endpoint.scheme == 'https' else http.client.HTTPConnection
    class Connection(parent):
        deadline = None
        auto_open = 0
        def send(self, data):
            if self.sock is None:
                raise ConnectionError('Prepared control connection lost')
            data = memoryview(data)
            while data:
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Operator expired before socket send')
                self.sock.settimeout(min(2, remaining))
                count = self.sock.send(data)
                if count <= 0:
                    raise ConnectionError('Control send failed')
                data = data[count:]
    body = json.dumps(payload).encode()
    connection = Connection(endpoint.hostname, endpoint.port, timeout=2)
    try:
        connection.connect()
        began = time.monotonic()
        current = request(config, base + '/control/operator', timeout=2)
        if current != expected:
            raise ValueError('Operator changed before control send')
        connection.deadline = began + .3
        connection.request('POST', endpoint.path.rstrip('/') + path, body=body,
            headers={'Authorization': 'Bearer ' + config.token, 'Content-Type': 'application/json'})
        connection.sock.settimeout(2)
        response = connection.getresponse()
        raw = response.read(8193)
        if response.status != 200 or len(raw) > 8192:
            raise RuntimeError('Control response unavailable')
        return json.loads(raw)
    finally:
        connection.close()


def demo(config, *, turns=3, seconds=180):
    """Run the existing live Agent, releasing only our unchanged CAS claims."""
    if type(turns) is not int or not 1 <= turns <= 3 or type(seconds) is not int or not 10 <= seconds <= 300:
        raise ValueError('Demo requires 1..3 turns and 10..300 seconds')
    base = config['network']['hub_url']
    def call(path, payload=None):
        return request(config, base + path, payload, timeout=2)
    def operator():
        began = time.monotonic()
        value = call('/control/operator')
        return value, began
    def write(path, payload, expected):
        return guarded_control(config, base, path, payload, expected)
    def status():
        value = call('/control/status')
        if type(value.get('turns')) is not int or value['turns'] < 0:
            raise ValueError('Agent completed-turn counter unavailable')
        if type(value.get('volume_percent')) is not int or not 0 < value['volume_percent'] <= 50:
            raise ValueError('Set audible volume to at most 50 before demo')
        return value
    owner = str(uuid.uuid4())
    claims = {}
    boot = None
    completed = 0
    receipt = False
    result = 1
    cleanup_failed = False
    cleanup_unknown = False
    print('Runner independent device watchdog required before starting: client timeout cannot survive client/network loss.', flush=True)
    try:
        initial = call('/control/operator')
        policy = initial['motion_policy']
        hardware = call('/status')
        stock = hardware['stock_motion']
        if (initial['microphone_enabled'] or initial['capture_active'] or initial['listening']
                or initial['phase'] != 'paused' or initial['microphone_owner_id'] is not None
                or initial['motion_policy_owner_id'] is not None or policy['quiet'] or policy['privacy_all']
                or stock['selected'] is not True or stock['unknown'] is not False
                or hardware['action_running'] or hardware['ownership']['state'] != 'free'
                or hardware['robot']['control_mode'] != 'enabled'):
            raise ValueError('Demo requires idle muted Agent, free enabled stock motors and no quiet/privacy owner')
        start = status()['turns']
        previous_task = stock['owned_uuid']
        boot = initial['agent_boot_id']
        fresh, began = operator()
        if fresh != initial:
            raise ValueError('Operator changed during admission')
        claims['policy'] = policy['epoch'] + 1  # Also covers an applied POST with a lost response.
        write('/control/motion-policy', dict(motor_enabled=True, quiet=False, privacy_all=False,
            expected_boot_id=boot, expected_epoch=policy['epoch'], owner_id=owner), fresh)
        current, began = operator()
        if (current['agent_boot_id'] != boot or current['motion_policy_owner_id'] != owner
                or current['motion_policy']['epoch'] != claims['policy']
                or current['microphone_epoch'] != initial['microphone_epoch']):
            raise ValueError('Operator changed before demo listening')
        claims['microphone'] = initial['microphone_epoch'] + 1
        write('/control/microphone', dict(enabled=True, listen=True, expected_boot_id=boot,
            expected_epoch=initial['microphone_epoch'], owner_id=owner), current)
        deadline = time.monotonic() + seconds
        print('Live demo starting. Ctrl-C or microphone OFF stops.', flush=True)
        listening_reported = False
        while time.monotonic() < deadline:
            current = call('/control/operator')
            if (current['agent_boot_id'] != boot or current['microphone_owner_id'] != owner
                    or current['microphone_epoch'] != claims['microphone']
                    or current['motion_policy_owner_id'] != owner
                    or current['motion_policy']['epoch'] != claims['policy']):
                raise ValueError('Operator changed; demo stopped')
            value = status()
            if current['capture_active'] and current['listening'] and not listening_reported:
                print('Microphone capture active: speak related turns now.', flush=True)
                listening_reported = True
            completed = max(0, value['turns'] - start)
            task = call('/status')['stock_motion']['owned_uuid']
            receipt = receipt or (task is not None and task != previous_task)
            if completed >= turns and current['phase'] == 'listening':
                result = 0
                break
            time.sleep(.5)
    except KeyboardInterrupt:
        result = 130
    except Exception:
        # Upstream error bodies may contain private operational information.
        print('Demo stopped: admission, operator or service check failed.', flush=True)
    finally:
        for kind in ('microphone', 'policy'):
            if kind not in claims:
                continue
            try:
                current, began = operator()
                epoch = current['microphone_epoch'] if kind == 'microphone' else current['motion_policy']['epoch']
                key = 'microphone_owner_id' if kind == 'microphone' else 'motion_policy_owner_id'
                if current['agent_boot_id'] != boot or current[key] != owner or epoch != claims[kind]:
                    cleanup_unknown = True
                    continue
                payload = dict(expected_boot_id=boot, expected_epoch=epoch, expected_owner_id=owner)
                if kind == 'microphone':
                    payload.update(enabled=False, listen=False)
                    write('/control/microphone', payload, current)
                else:
                    payload.update(motor_enabled=False, quiet=current['motion_policy']['quiet'],
                                   privacy_all=current['motion_policy']['privacy_all'])
                    write('/control/motion-policy', payload, current)
                after, _ = operator()
                if kind == 'microphone':
                    for _ in range(10):
                        if (not after['capture_active'] or after['agent_boot_id'] != boot
                                or after['microphone_epoch'] != epoch + 1):
                            break
                        time.sleep(.1)
                        after, _ = operator()
                after_epoch = after['microphone_epoch'] if kind == 'microphone' else after['motion_policy']['epoch']
                if (after['agent_boot_id'] != boot or after_epoch != epoch + 1 or after[key] is not None
                        or (kind == 'microphone' and (after['microphone_enabled'] or after['listening'] or after['capture_active']))
                        or (kind == 'policy' and after['motion_policy']['motor_enabled'])):
                    cleanup_unknown = True
            except Exception:
                cleanup_failed = True
        if claims:
            try:
                final = call('/status')
                stock = final['stock_motion']
                if (final['action_running'] or stock['unknown']
                        or (stock['owned_uuid'] is not None and stock['stop_observed'] is not True)):
                    cleanup_unknown = True
            except Exception:
                cleanup_unknown = True
        print(json.dumps(dict(completed_turns=completed, stock_task_observed=receipt,
            physical_motion_verified=False, context_verified=False, cleanup_failed=cleanup_failed,
            cleanup_unknown=cleanup_unknown)), flush=True)
    return 1 if cleanup_failed or cleanup_unknown else result


def control(config, role, command, text=None):
    network = config['network']
    if role == 'hub' and command == 'control':
        import webbrowser
        from urllib.parse import quote
        webbrowser.open(network['hub_url'] + '/control#' + quote(config.token, safe=''))
        print('Control page opened: ' + network['hub_url'] + '/control')
        return 0

    if role == 'hub':
        base = network['hub_url']
        path = '/status' if command == 'status' else '/actions/' + command
        payload = None if command == 'status' else {}
    elif role == 'voice':
        base = network['voice_url']
        path = ('/robot/' if command in ('ask', 'say') else '/') + command
        payload = None if command == 'status' else {'text': text, 'session': config['conversation']['session']}
        if command in ('microphone-on', 'microphone-off'):
            path, payload = '/microphone', {'enabled': command == 'microphone-on'}
    else:
        raise ValueError('Unknown client role')
    try:
        value = request(config, base + path, payload)
    except HTTPError as exc:
        print(exc.read().decode())
        return 1
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0
