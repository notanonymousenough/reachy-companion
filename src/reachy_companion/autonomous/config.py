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
    for role in ('fast', 'main'):
        model = config['models'][role]
        for key in ('context_tokens', 'input_cap_tokens', 'template_cap_tokens', 'output_tokens', 'reserve_tokens'):
            if type(model[key]) is not int or model[key] < 1:
                raise ValueError('Invalid model budget')
        if model['input_cap_tokens'] + model['template_cap_tokens'] + model['output_tokens'] + model['reserve_tokens'] > model['context_tokens']:
            raise ValueError('Model budget exceeds runtime context')
        if role == 'fast' and model['output_tokens'] > 192:
            raise ValueError('Fast output exceeds design cap')
        if model.get('base_url'):
            url = urlsplit(model['base_url'])
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
                raise ValueError('Invalid model URL')
    return copy.deepcopy(config)
