"""Text-only backend boundary: local Qwen, OpenClaw or Hermes Agent."""
import json
import os
import re
from urllib.request import Request, build_opener, ProxyHandler


def answer(config, messages, session):
    brains = config['brains']
    selected = brains['provider']
    if selected == 'lm_studio':
        settings = config['llm']
        def clean(content):
            return re.sub(r'<\|[^\n]*?\|>', '', content)
        prompt = ''.join(settings['message_template'].format(role=m['role'], content=clean(m['content']))
                         for m in messages) + settings['assistant_prefix']
        payload = {'model': settings['model'], 'prompt': prompt,
                   'temperature': settings['temperature'], 'max_tokens': settings['max_tokens'],
                   'stream': False, 'stop': settings['stop']}
        url = config['network']['llm_base_url'].rstrip('/') + settings['api_path']
        headers = {}
    else:
        settings = brains[selected]
        key = os.environ.get(settings['api_key_env'], '')
        if not key:
            raise ValueError('Set worker environment variable ' + settings['api_key_env'])
        # OpenClaw owns its transcript. Hermes chat/completions uses the
        # full client transcript; session header also supplies an identity.
        payload = {'model': settings['model'], 'messages': [messages[0], messages[-1]] if selected == 'openclaw' else messages, 'stream': False}
        headers = {'Authorization': 'Bearer ' + key}
        url = settings['base_url'].rstrip('/') + settings['api_path']
        if selected == 'openclaw':
            payload['user'] = 'reachy:' + session
        elif selected == 'hermes':
            headers['X-Hermes-Session-Id'] = 'reachy:' + session
    headers['Content-Type'] = 'application/json'
    request = Request(url, data=json.dumps(payload).encode(), headers=headers)
    with build_opener(ProxyHandler({})).open(request, timeout=config['timeouts']['llm']) as response:
        choice = json.load(response)['choices'][0]
    text = choice.get('text', '') if selected == 'lm_studio' else choice.get('message', {}).get('content', '')
    if not isinstance(text, str):
        raise RuntimeError('Backend did not return spoken text')
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()
    if not text or choice.get('finish_reason') == 'length':
        raise RuntimeError('Backend did not produce a complete spoken answer')
    if len(text) > config['limits']['max_speech_chars']:
        raise RuntimeError('Backend answer exceeds the speech limit')
    return text
