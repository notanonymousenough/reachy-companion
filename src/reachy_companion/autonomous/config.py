"""Explicit opt-in profile independent from the running companion config."""
import copy
from pathlib import Path
from urllib.parse import urlsplit
from .contracts import decode


def load(path):
    config = decode(Path(path).read_text())
    if config['version'] != 1 or config['actuators'] != 'simulated' or config['export_enabled']:
        raise ValueError('This slice only supports simulated actuators and disabled export')
    for key in ('period_s', 'fast_deadline_s', 'http_timeout_s', 'task_timeout_s', 'proposal_ttl_s'):
        if type(config[key]) not in (int, float) or not 0 < config[key] <= 120:
            raise ValueError('Invalid timing: ' + key)
    for key, cap in [('ledger_cap', 4096), ('sensor_cap', 12), ('task_cap', 8), ('candidate_cap', 8)]:
        if type(config[key]) is not int or not 1 <= config[key] <= cap:
            raise ValueError('Invalid bound: ' + key)
    if type(config['gateway']['port']) is not int or not 1 <= config['gateway']['port'] <= 65535:
        raise ValueError('Invalid port')
    if not config['gateway']['token_env']:
        raise ValueError('Gateway credentials must be supplied through environment')
    workflows = config.get('workflows', {})
    context = config.get('context', {})
    if context:
        if type(context.get('enabled')) is not bool:raise ValueError('Context enable flag')
        if context.get('enabled'):
            if not context.get('memory_path') or not 1<=len(context.get('namespaces',[]))<=4:raise ValueError('Context memory configuration')
            for key,default in [('refresh_s',.5),('video_poll_s',.5)]:
                value=context.get(key,default)
                if type(value) not in (int,float) or not .1<=value<=10:raise ValueError('Context timing bound')
            if context.get('video_url'):
                endpoint=urlsplit(context['video_url'])
                if (endpoint.scheme!='http' or endpoint.hostname not in ('localhost','127.0.0.1','::1')
                        or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
                        or not context.get('video_token_env')):
                    raise ValueError('Video transport requires loopback SSH and token')
    if type(workflows.get('enabled', False)) is not bool:
        raise ValueError('Workflow enable flag must be boolean')
    if workflows:
        for key in ('http_timeout_s', 'poll_s'):
            if type(workflows[key]) not in (int, float) or not 0 < workflows[key] <= 10:
                raise ValueError('Invalid workflow timing')
    for endpoint in (config['gateway'].get('client_url'), workflows.get('broker_url')):
        if endpoint:
            url = urlsplit(endpoint)
            if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
                    or url.fragment or (url.scheme == 'http' and url.hostname not in ('localhost', '127.0.0.1', '::1'))):
                raise ValueError('Token transport requires HTTPS or localhost SSH tunnel')
    for role in ('fast', 'main'):
        model = config['models'][role]
        for key in ('context_tokens', 'input_cap_tokens', 'template_cap_tokens', 'output_tokens', 'reserve_tokens'):
            if type(model[key]) is not int or model[key] < 1:
                raise ValueError('Invalid model budget')
        if model['input_cap_tokens'] + model['template_cap_tokens'] + model['output_tokens'] + model['reserve_tokens'] > model['context_tokens']:
            raise ValueError('Model budget exceeds runtime context')
        admission = model.get('admission_context_tokens', model['context_tokens'])
        if type(admission) is not int or not 1 <= admission <= model['context_tokens']:
            raise ValueError('Invalid admission context')
        if model.get('tokenizer_backend', 'http') not in ('http', 'lmstudio_sdk'):
            raise ValueError('Invalid tokenizer backend')
        if model.get('completion_backend', 'openai') not in ('openai', 'llama_native', 'lmstudio_sdk'):
            raise ValueError('Invalid completion backend')
        if (model.get('tokenizer_backend') == 'lmstudio_sdk') != (model.get('completion_backend') == 'lmstudio_sdk'):
            raise ValueError('SDK tokenizer and completion must be paired')
        if model.get('tokenizer_backend') == 'lmstudio_sdk':
            endpoint = urlsplit(model.get('base_url') or '')
            if (role != 'main' or model.get('completion_backend') != 'lmstudio_sdk' or endpoint.scheme != 'http'
                    or endpoint.hostname not in ('localhost', '127.0.0.1', '::1')):
                raise ValueError('SDK main requires paired loaded-handle completion on loopback')
        if role == 'fast' and model['output_tokens'] > 192:
            raise ValueError('Fast output exceeds design cap')
        if model.get('projection', 'full') not in ('full', 'task_only'):
            raise ValueError('Invalid fast projection')
        if model.get('decision_format','object') not in ('object','tuple'):
            raise ValueError('Invalid fast decision format')
        if model.get('decision_format')=='tuple' and (role!='fast' or model.get('completion_backend')!='llama_native'):
            raise ValueError('Tuple decisions require constrained native fast lane')
        if type(model.get('cache_ram_mb', 0)) is not int or not 0 <= model.get('cache_ram_mb', 0) <= 128:
            raise ValueError('Runtime prompt cache exceeds prototype cap')
        if model.get('projection') == 'task_only' and (role != 'fast' or config['actuators'] != 'simulated'):
            raise ValueError('Task-only projection is limited to simulated fast probes')
        if model.get('base_url'):
            url = urlsplit(model['base_url'])
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
                raise ValueError('Invalid model URL')
    return copy.deepcopy(config)
