import json
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError


def request(config, url, payload=None, timeout=None):
    item = Request(url, data=None if payload is None else json.dumps(payload).encode(),
                   headers={'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + config.token})
    with build_opener(ProxyHandler({})).open(item, timeout=timeout or config['timeouts']['client']) as response:
        return json.load(response)


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
