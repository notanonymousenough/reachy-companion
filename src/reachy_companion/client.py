import json
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
import time
import uuid
import http.client
import math
from urllib.parse import urlsplit


def request(config, url, payload=None, timeout=None):
    item = Request(url, data=None if payload is None else json.dumps(payload).encode(),
                   headers={'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + config.token})
    with build_opener(ProxyHandler({})).open(item, timeout=timeout or config['timeouts']['client']) as response:
        return json.load(response)


def control_authority(value):
    """Validate the full operator response; project only control authority."""
    fields = {'agent_boot_id', 'microphone_epoch', 'microphone_owner_id', 'microphone_enabled',
        'capture_active', 'phase', 'listening', 'microphone_state_error', 'motion_policy',
        'motion_policy_owner_id', 'expression_version'}
    if type(value) is not dict or set(value) != fields:
        raise ValueError('Exact operator response required')
    policy = value['motion_policy']
    if (type(policy) is not dict or set(policy) != {'motor_enabled', 'quiet', 'privacy_all', 'epoch'}
            or type(value['agent_boot_id']) is not str or not 1 <= len(value['agent_boot_id']) <= 256
            or any(type(v) is not int or not 0 <= v < 2**63 for v in
                   (value['microphone_epoch'], value['expression_version'], policy.get('epoch')))
            or any(type(value[k]) is not bool for k in ('microphone_enabled', 'capture_active', 'listening'))
            or any(type(policy[k]) is not bool for k in ('motor_enabled', 'quiet', 'privacy_all'))
            or any(value[k] is not None and (type(value[k]) is not str or not 1 <= len(value[k]) <= 128)
                   for k in ('microphone_owner_id', 'motion_policy_owner_id'))
            or value['microphone_state_error'] is not None
            or type(value['phase']) is not str or value['phase'] not in ('starting', 'paused', 'listening',
                'recording', 'processing', 'speaking', 'waiting_to_resume', 'music', 'error', 'stopped')):
        raise ValueError('Typed current operator required')
    return (value['agent_boot_id'], value['microphone_epoch'], value['microphone_enabled'],
        value['microphone_owner_id'], policy['epoch'], policy['motor_enabled'], policy['quiet'],
        policy['privacy_all'], value['motion_policy_owner_id'])


def compare_control_operator(current, expected, *, require_paused=False):
    if control_authority(current) != control_authority(expected):
        raise ValueError('Operator authority changed before control send')
    if require_paused and (current['phase'] != 'paused' or current['microphone_enabled']
            or current['capture_active'] or current['listening']
            or current['motion_policy']['quiet'] or current['motion_policy']['privacy_all']):
        raise ValueError('Current paused microphone/capture/listening OFF required')


def _demo_read(config, url, *, deadline=None):
    """At most two fresh GETs on a transient 503; never retry a mutation."""
    for attempt in range(2):
        began = time.monotonic()
        remaining = 2 if deadline is None else min(2, deadline - began)
        if remaining <= 0:
            raise TimeoutError('Demo deadline expired before read')
        try:
            return request(config, url, timeout=remaining), began
        except HTTPError as exc:
            exc.close()
            if exc.code != 503 or attempt == 1:
                raise


def guarded_control(config, base, path, payload, expected, *, deadline=None, authority_base=None, response_timeout=2):
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
        current, began = _demo_read(config, (authority_base or base) + '/control/operator', deadline=deadline)
        compare_control_operator(current, expected, require_paused=(
            (path == '/control/microphone' and payload.get('enabled') is True)
            or (path == '/control/motion-policy' and payload.get('motor_enabled') is True)))
        connection.deadline = began + .3 if deadline is None else min(began + .3, deadline)
        connection.request('POST', endpoint.path.rstrip('/') + path, body=body,
            headers={'Authorization': 'Bearer ' + config.token, 'Content-Type': 'application/json'})
        connection.sock.settimeout(response_timeout)
        response = connection.getresponse()
        maximum=65536 if path=='/robot/say' else 8192
        raw = response.read(maximum+1)
        if response.status != 200 or len(raw) > maximum:
            raise RuntimeError('Control response unavailable')
        return json.loads(raw)
    finally:
        connection.close()


def demo(config, *, turns=3, seconds=180, owner_id=None, operator_binding=None, vision_text=None, vision_deadline=None, prime_paused=False):
    """Run the existing live Agent, releasing only our unchanged CAS claims."""
    if type(turns) is not int or not 1 <= turns <= 3 or type(seconds) is not int or not 10 <= seconds <= 300:
        raise ValueError('Demo requires 1..3 turns and 10..300 seconds')
    if type(prime_paused) is not bool:
        raise ValueError('Boolean prime-paused mode required')
    if vision_text is not None or vision_deadline is not None:
        if (type(vision_text) is not str or not 0<len(vision_text.strip())<=1600
                or any(tag in vision_text.lower() for tag in ('<think','</think','<|analysis|>','<|im_start|>','<analysis','[analysis]'))
                or type(vision_deadline) not in (int,float) or not math.isfinite(vision_deadline) or vision_deadline<=0):
            raise ValueError('Bounded FINAL snapshot text and Robot deadline required')
    if owner_id is not None:
        if type(owner_id) is not str:
            raise ValueError('Demo owner must be a canonical nonzero UUID')
        parsed_owner = uuid.UUID(owner_id)
        if str(parsed_owner) != owner_id or parsed_owner.int == 0:
            raise ValueError('Demo owner must be a canonical nonzero UUID')
    expected_binding = None
    if operator_binding is not None:
        if (type(operator_binding) is not dict
                or set(operator_binding) != {'agent_boot_id', 'microphone_epoch', 'policy_epoch'}
                or type(operator_binding['agent_boot_id']) is not str
                or not 1 <= len(operator_binding['agent_boot_id']) <= 256
                or any(type(operator_binding[k]) is not int or not 0 <= operator_binding[k] < 2**63
                       for k in ('microphone_epoch', 'policy_epoch'))):
            raise ValueError('Exact typed demo operator binding required')
        expected_binding = tuple(operator_binding[k] for k in ('agent_boot_id', 'microphone_epoch', 'policy_epoch'))
    base = config['network']['hub_url']
    deadline = time.monotonic() + seconds
    cleaning_up = False
    def call(path, payload=None):
        if payload is None:
            return _demo_read(config, base + path, deadline=None if cleaning_up else deadline)[0]
        return request(config, base + path, payload, timeout=2)
    def operator():
        return _demo_read(config, base + '/control/operator', deadline=None if cleaning_up else deadline)
    def write(path, payload, expected, *, target=None, response_timeout=2):
        return guarded_control(config, target or base, path, payload, expected, authority_base=base,
            deadline=None if cleaning_up else deadline,response_timeout=response_timeout)
    def status():
        value = call('/control/status')
        if type(value.get('turns')) is not int or value['turns'] < 0:
            raise ValueError('Agent completed-turn counter unavailable')
        if type(value.get('volume_percent')) is not int or not 0 < value['volume_percent'] <= 100:
            raise ValueError('Audible volume from 1 to 100 required before demo')
        return value
    owner = str(uuid.uuid4()) if owner_id is None else owner_id
    claims = {}
    boot = None
    completed = 0
    receipt = False
    result = 1
    cleanup_failed = False
    cleanup_unknown = False
    vision_speech_completed = False
    print('Runner independent device watchdog required before starting: client timeout cannot survive client/network loss.', flush=True)
    try:
        initial = call('/control/operator')
        control_authority(initial)
        policy = initial['motion_policy']
        if expected_binding is not None and expected_binding != (
                initial['agent_boot_id'], initial['microphone_epoch'], policy['epoch']):
            raise ValueError('Operator changed after watchdog was armed')
        if vision_text is not None:
            capability,_=_demo_read(config,config['network']['agent_url']+'/vision-capabilities',deadline=deadline)
            if (type(capability) is not dict or type(capability.get('bound_snapshot_say')) is not int
                    or capability!={'bound_snapshot_say':1,'agent_boot_id':initial['agent_boot_id']}):
                raise ValueError('Bound snapshot speech overlay unavailable')
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
        compare_control_operator(fresh, initial, require_paused=True)
        claims['policy'] = policy['epoch'] + 1  # Also covers an applied POST with a lost response.
        write('/control/motion-policy', dict(motor_enabled=True, quiet=False, privacy_all=False,
            expected_boot_id=boot, expected_epoch=policy['epoch'], owner_id=owner), fresh)
        current, began = operator()
        if (current['agent_boot_id'] != boot or current['motion_policy_owner_id'] != owner
                or current['motion_policy']['epoch'] != claims['policy']
                or current['microphone_epoch'] != initial['microphone_epoch']):
            raise ValueError('Operator changed before demo listening')
        claims['microphone'] = initial['microphone_epoch'] + 1
        write('/control/microphone', dict(enabled=True, listen=vision_text is None and not prime_paused, expected_boot_id=boot,
            expected_epoch=initial['microphone_epoch'], owner_id=owner), current)
        if vision_text is not None:
            current,_=operator()
            if (current['agent_boot_id']!=boot or current['microphone_epoch']!=claims['microphone']
                    or current['motion_policy']['epoch']!=claims['policy']
                    or current['microphone_owner_id']!=owner or current['motion_policy_owner_id']!=owner):
                raise ValueError('Snapshot speaker owner changed')
            binding=dict(agent_boot_id=boot,microphone_epoch=claims['microphone'],policy_epoch=claims['policy'],
                owner_id=owner,expires_at_monotonic=vision_deadline)
            print('Speaking the captured snapshot FINAL. Ctrl-C or microphone OFF stops.',flush=True)
            spoken=write('/robot/say',dict(text=vision_text,operator_binding=binding),current,
                target=config['network']['voice_url'],response_timeout=min(60,max(.1,deadline-time.monotonic())))
            vision_speech_completed=spoken.get('ok') is True and not spoken.get('cancelled')
            result=0 if vision_speech_completed else 1
        else:
            print('Microphone permission ON, capture paused. Awaiting guarded controller cue/resume. Ctrl-C or microphone OFF stops.'
                  if prime_paused else 'Live demo starting. Ctrl-C or microphone OFF stops.', flush=True)
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
                if completed >= turns:
                    result = 0
                    break
                task = call('/status')['stock_motion']['owned_uuid']
                receipt = receipt or (task is not None and task != previous_task)
                time.sleep(.5)
    except KeyboardInterrupt:
        result = 130
    except Exception:
        # Upstream error bodies may contain private operational information.
        print('Demo stopped: admission, operator or service check failed.', flush=True)
    finally:
        cleaning_up = True
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
        summary=dict(completed_turns=completed, stock_task_observed=receipt,
            physical_motion_verified=False, context_verified=False, cleanup_failed=cleanup_failed,
            cleanup_unknown=cleanup_unknown)
        if vision_text is not None:summary.update(vision_snapshot=True,vision_speech_completed=vision_speech_completed)
        if prime_paused:summary['prime_paused']=True
        print(json.dumps(summary), flush=True)
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
