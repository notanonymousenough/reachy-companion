"""Request-scoped spoken-text constraints; no tools, authority or model fallback.

The large autonomous MainProposal carries separate causality/grants. This worker
boundary returns only validated spoken text and reuses its strict JSON decoder.
A no-question punctuation schema is not proof of semantic intent; the independent
fixture's question/wake/TTL checks remain mandatory.
"""
import re
import unicodedata
from urllib.parse import urlsplit
from .autonomous.contracts import decode

QUESTION_MARKS='?？؟'
FORBIDDEN='\x00-\x1f<>*#`'


def constraints(value):
    if (not isinstance(value,dict) or set(value)!={'schema_version','max_chars','no_question','no_wake'}
            or value['schema_version']!='reply-1' or type(value['max_chars']) is not int or not 1<=value['max_chars']<=200
            or type(value['no_question']) is not bool or type(value['no_wake']) is not bool):raise ValueError('Typed finite reply constraints required')
    return dict(value)


def response_format(value):
    value=constraints(value);excluded=FORBIDDEN+(QUESTION_MARKS if value['no_question'] else '')
    return dict(type='json_schema',json_schema=dict(name='spoken_reply_v1',strict=True,schema=dict(
        type='object',properties=dict(reply=dict(type='string',minLength=1,maxLength=value['max_chars'],pattern='^[^'+excluded+']+$')),
        required=['reply'],additionalProperties=False)))


def endpoint(config):
    settings=config['llm'];audit=settings.get('reply_schema',{})
    if isinstance(audit,dict) and audit.get('mode','http_chat')!='http_chat':
        raise ValueError('HTTP chat proof cannot enable another route')
    if (config['brains']['provider']!='lm_studio' or not isinstance(audit,dict) or audit.get('enabled') is not True
            or audit.get('verified') is not True or audit.get('model')!=settings['model'] or audit.get('base_url')!=config['network']['llm_base_url']
            or audit.get('max_length_verified') is not True or audit.get('pattern_verified') is not True):
        raise ValueError('Audited same-model structured reply route required')
    path=audit.get('api_path')
    if path not in ('/chat/completions','/v1/chat/completions'):raise ValueError('Audited chat schema path required')
    url=config['network']['llm_base_url'].rstrip('/')+path;parsed=urlsplit(url)
    if parsed.path!='/v1/chat/completions' or parsed.query or parsed.fragment:raise ValueError('Exact supported chat schema endpoint required')
    return url


def validate_text(text,value):
    value=constraints(value)
    if (not isinstance(text,str) or not 1<=len(text)<=value['max_chars'] or text!=text.strip()
            or re.search('['+FORBIDDEN+']',text)):raise RuntimeError('Spoken reply constraint rejected')
    normalized=''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))
    if not re.search(r'\w+',normalized):raise RuntimeError('Spoken reply has no word')
    if value['no_question'] and any(mark in normalized for mark in QUESTION_MARKS):raise RuntimeError('Question reply rejected')
    mixed=normalized.translate(str.maketrans({'a':'а','l':'л','i':'и','s':'с','c':'с','e':'е'}))
    if value['no_wake'] and (re.search('alice|alisa|алис',normalized) or 'алис' in mixed):raise RuntimeError('Wake reply rejected')
    return text # never truncate, repair, strip tags or substitute a preset


def decode_reply(content,value):
    if not isinstance(content,str) or len(content.encode('utf-8'))>8192:raise RuntimeError('Structured reply envelope bound')
    result=decode(content)
    if not isinstance(result,dict) or set(result)!={'reply'}:raise RuntimeError('Exact spoken reply object required')
    return validate_text(result['reply'],value)


def check_profile(config,value):
    audit=config['llm'].get('reply_schema',{})
    if isinstance(audit,dict) and audit.get('mode')=='sdk_raw_instance_v1':
        from .spoken_reply_sdk import profile
        profile(config,value)
    else:endpoint(config)
