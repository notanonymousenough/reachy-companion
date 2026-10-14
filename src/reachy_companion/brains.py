"""Text-only backend boundary: local Qwen, OpenClaw or Hermes Agent."""
import json
import os
import re
import sys
import threading
from contextlib import contextmanager
from urllib.request import Request, build_opener, ProxyHandler


class ModelExecutionOwnership:
    """Process-local same-backend admission; unknown entries never auto-expire."""
    def __init__(self,capacity=16):
        self.lock=threading.Lock()
        self.entries={}
        self.capacity=capacity

    class Permit:
        def __init__(self,owner,state):self.owner=owner;self.state=state
        def submitted(self):
            with self.owner.lock:self.state['submitted']=True
        def terminal(self):
            with self.owner.lock:self.state['terminal']=True

    def status(self,identity):
        with self.lock:
            state=self.entries.get(identity)
            return dict(active=bool(state and state['active']),
                        unknown=bool(state and state['submitted'] and not state['terminal'] and not state['active']))

    @contextmanager
    def reserve(self,identity):
        with self.lock:
            if identity in self.entries:raise RuntimeError('Model execution busy or completion unknown')
            if len(self.entries)>=self.capacity:raise RuntimeError('Model execution ownership capacity exhausted')
            state=dict(active=True,submitted=False,terminal=False)
            self.entries[identity]=state
        try:yield self.Permit(self,state)
        finally:
            with self.lock:
                state['active']=False
                if not state['submitted'] or state['terminal']:del self.entries[identity]


MODEL_EXECUTION=ModelExecutionOwnership()


def model_identity(config):
    return config['network']['llm_base_url'].rstrip('/'),config['llm']['model']


def http_model_choice(config,request):
    identity=model_identity(config)
    with MODEL_EXECUTION.reserve(identity) as execution:
        execution.submitted()
        with build_opener(ProxyHandler({})).open(request,timeout=config['timeouts']['llm']) as response:
            raw=response.read(1048577)
            if len(raw)>1048576:raise RuntimeError('HTTP model envelope exceeds bound')
            def reject(value):raise ValueError('Non-finite HTTP model JSON')
            def unique(pairs):
                result={}
                for key,value in pairs:
                    if key in result:raise ValueError('Duplicate HTTP model JSON key')
                    result[key]=value
                return result
            envelope=json.loads(raw,parse_constant=reject,object_pairs_hook=unique)
            if (not isinstance(envelope,dict) or envelope.get('model')!=identity[1]
                    or not isinstance(envelope.get('choices'),list) or len(envelope['choices'])!=1):
                raise RuntimeError('HTTP model response identity unverified')
            choice=envelope['choices'][0]
            if not isinstance(choice,dict) or type(choice.get('index',0)) is not int or choice.get('index',0)!=0 or choice.get('finish_reason') not in ('stop','length'):
                raise RuntimeError('HTTP model terminal response unverified')
            execution.terminal()
            return choice


def raw_prompt(config,messages):
    settings=config['llm']
    def clean(content):return re.sub(r'<\|[^\n]*?\|>', '', content)
    return ''.join(settings['message_template'].format(role=m['role'],content=clean(m['content']))
                   for m in messages)+settings['assistant_prefix']


def answer(config, messages, session, *, reply_constraints=None):
    brains = config['brains']
    selected = brains['provider']
    sdk_boundary=sys.modules.get(__package__+'.spoken_reply_sdk')
    if selected=='lm_studio' and sdk_boundary is not None:
        sdk_boundary.SLOT.available((config['network']['llm_base_url'].rstrip('/'),config['llm']['model']))
    if reply_constraints is not None:
        from .spoken_reply import constraints,response_format,endpoint
        reply_constraints=constraints(reply_constraints)
        if config['llm'].get('reply_schema',{}).get('mode')=='sdk_raw_instance_v1':
            from .spoken_reply_sdk import predict
            return predict(config,messages,reply_constraints)
        url=endpoint(config);settings=config['llm']
        payload=dict(model=settings['model'],messages=messages,temperature=settings['temperature'],
            max_tokens=settings['max_tokens'],stream=False,response_format=response_format(reply_constraints))
        headers={}
    elif selected == 'lm_studio':
        settings = config['llm']
        prompt = raw_prompt(config,messages)
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
    if selected=='lm_studio':choice=http_model_choice(config,request)
    else:
        with build_opener(ProxyHandler({})).open(request, timeout=config['timeouts']['llm']) as response:
            choice = json.load(response)['choices'][0]
    if reply_constraints is not None:
        from .spoken_reply import decode_reply
        if choice.get('finish_reason')!='stop':raise RuntimeError('Incomplete structured spoken reply')
        text=decode_reply(choice.get('message',{}).get('content'),reply_constraints)
        if len(text)>config['limits']['max_speech_chars']:raise RuntimeError('Backend answer exceeds the speech limit')
        return text
    text = choice.get('text', '') if selected == 'lm_studio' else choice.get('message', {}).get('content', '')
    if not isinstance(text, str):
        raise RuntimeError('Backend did not return spoken text')
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()
    if not text or choice.get('finish_reason') == 'length':
        raise RuntimeError('Backend did not produce a complete spoken answer')
    if len(text) > config['limits']['max_speech_chars']:
        raise RuntimeError('Backend answer exceeds the speech limit')
    return text
