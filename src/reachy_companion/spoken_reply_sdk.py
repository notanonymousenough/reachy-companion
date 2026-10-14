"""Optional pinned raw SDK prediction boundary; never load a model on demand."""
import math
import threading
import time


class PredictionSlot:
    """One real operation; caller timeout neither cancels nor frees its slot.

    A transport exception after submission gives no cancellation acknowledgement.
    Such a slot stays quarantined for this process, even after the Python worker
    exits. There is deliberately no timer/reset/reclaim API.
    """
    def __init__(self):
        self.condition=threading.Condition()
        self.active=False
        self.quarantined=False
        self.identity=None

    def status(self):
        with self.condition:
            return dict(active=self.active,quarantined=self.quarantined)

    def available(self,identity=None):
        with self.condition:
            if identity is not None and self.identity!=identity:return
            if self.active or self.quarantined:raise RuntimeError('SDK execution busy or completion unknown')

    def execute(self,operation,timeout,identity=None):
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=120:
            raise ValueError('Finite SDK wait required')
        deadline=time.monotonic()+timeout
        box=dict(done=False,abandoned=False,started=False,terminal=False)
        with self.condition:
            if self.active or self.quarantined:raise RuntimeError('SDK execution busy or completion unknown')
            self.active=True
            self.identity=identity

        def mark_started():box['started']=True
        def mark_terminal():box['terminal']=True
        def work():
            value=None;failed=False
            try:value=operation(mark_started,mark_terminal)
            except BaseException:failed=True
            finally:
                with self.condition:
                    unknown=box['started'] and not box['terminal']
                    self.quarantined=self.quarantined or unknown
                    self.active=False
                    if not self.quarantined:self.identity=None
                    box['done']=True
                    box['failed']=failed or unknown
                    if not box['abandoned']:box['value']=value
                    self.condition.notify_all()
        worker=threading.Thread(target=work,name='spoken-sdk-prediction',daemon=True)
        try:worker.start()
        except BaseException:
            with self.condition:self.active=False;self.identity=None
            raise
        with self.condition:
            done=self.condition.wait_for(lambda:box['done'],max(0,deadline-time.monotonic()))
            if not done or time.monotonic()>deadline:
                box['abandoned']=True
                box.pop('value',None)
                raise TimeoutError('SDK caller deadline expired; late output discarded')
            value=box.pop('value',None)
            if box['failed']:raise RuntimeError('SDK operation failed; inspect execution status')
            return value


SLOT=PredictionSlot()

# Audited public PyPI wheel 1.5.0. The private adapter has no version fallback.
SDK_SOURCES={
    'sync_api.py':'888360663dc5655e90c614ff64a285299f97a8f3a9cfeee28cac08dd42dac685',
    'json_api.py':'32146d39cf215e5829102938252e219a2300253981520f7005ab765b8d4b1f80',
    '_sdk_models/__init__.py':'8894904436f8b6322701c05e1fcc01728c3c772a8271ef4eba67ab25b335882a',
}
SDK_TREE='9cd3e9636afed8ec8fb737c8c549b178dab68661a3f62fd84f41803db6c8d47d'
MODE='sdk_raw_instance_v1'


def digest(value):
    import hashlib
    import json
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def template_binding(config):
    settings=config['llm']
    return digest({key:settings[key] for key in ('message_template','assistant_prefix','stop','temperature','max_tokens')})


def profile(config,rule):
    from .spoken_reply import constraints,response_format
    from urllib.parse import urlsplit
    rule=constraints(rule);settings=config['llm'];audit=settings.get('reply_schema',{})
    parsed=urlsplit(config['network']['llm_base_url'])
    if (config['brains']['provider']!='lm_studio' or not isinstance(audit,dict)
            or audit.get('mode')!=MODE or audit.get('enabled') is not True or audit.get('verified') is not True
            or audit.get('instance_spec_verified') is not True or audit.get('model')!=settings['model']
            or audit.get('base_url')!=config['network']['llm_base_url']
            or parsed.scheme!='http' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('','/','/v1','/v1/') or parsed.query or parsed.fragment
            or audit.get('sdk_version')!='1.5.0' or audit.get('sdk_sources')!=SDK_SOURCES or audit.get('sdk_tree_sha256')!=SDK_TREE
            or audit.get('template_sha256')!=template_binding(config)
            or audit.get('constraints_sha256')!=digest(rule)
            or audit.get('schema_sha256')!=digest(response_format(rule)['json_schema']['schema'])
            or not isinstance(audit.get('runtime_build'),str) or not 1<=len(audit['runtime_build'])<=128
            or type(audit.get('max_tokens')) is not int or not 1<=audit['max_tokens']<=min(512,settings['max_tokens'])
            or type(audit.get('context_tokens')) is not int or not 1<=audit['context_tokens']<=1048576):
        raise ValueError('Audited fixed-instance raw SDK profile required')
    timeout=audit.get('timeout_s')
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=min(120,config['timeouts']['llm']):
        raise ValueError('Audited finite SDK caller wait required')
    for name in ('instance_reference','model_key','environment_sha256'):
        if not isinstance(audit.get(name),str) or not 1<=len(audit[name])<=512:
            raise ValueError('SDK identity/environment binding required')
    if len(audit['environment_sha256'])!=64 or any(c not in '0123456789abcdef' for c in audit['environment_sha256']):
        raise ValueError('SDK environment hash required')
    return dict(audit),parsed.netloc


def environment_audit():
    """Read metadata/source only; never import SDK, connect or install packages."""
    import hashlib
    from importlib import metadata
    packages={}
    for distribution in metadata.distributions():
        name=distribution.metadata['Name'].lower().replace('_','-')
        if name in packages:raise ValueError('Ambiguous installed distribution')
        packages[name]=distribution.version
    sdk=metadata.distribution('lmstudio')
    sources={name:hashlib.sha256(sdk.locate_file('lmstudio/'+name).read_bytes()).hexdigest() for name in SDK_SOURCES}
    root=sdk.locate_file('lmstudio')
    tree={str(path.relative_to(root)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob('*.py')}
    return dict(sdk_version=sdk.version,sdk_sources=sources,sdk_tree_sha256=digest(tree),environment_sha256=digest(packages))


def predict(config,messages,rule):
    from .spoken_reply import decode_reply,response_format
    audit,host=profile(config,rule)
    actual=environment_audit()
    if any(actual[key]!=audit[key] for key in ('sdk_version','sdk_sources','sdk_tree_sha256','environment_sha256')):
        raise ValueError('Installed SDK dependency/source audit mismatch')
    # Import only after exact local source/version/environment validation.
    import lmstudio
    from .brains import raw_prompt
    prompt=raw_prompt(config,messages)
    schema=response_format(rule)['json_schema']['schema']
    def operation(started,terminal):
        with lmstudio.Client(host) as client:
            # Public RPC supports the exact reference. It never calls getOrLoad.
            spec=dict(type='instanceReference',instanceReference=audit['instance_reference'])
            info=client.llm.get_model_info(spec)
            if (info.identifier!=audit['model'] or info.instance_reference!=audit['instance_reference']
                    or info.model_key!=audit['model_key'] or info.context_length!=audit['context_tokens']):
                raise ValueError('Expected already-loaded instance absent or changed')
            # Source-pinned private core used by .complete. A string selector here
            # would be an identifier query and permit ABA; never substitute one.
            started()
            stream=client.llm._complete_stream(spec,prompt,config=dict(
                maxTokens=audit['max_tokens'],temperature=config['llm']['temperature'],
                stopStrings=config['llm']['stop'],structured=dict(type='json',jsonSchema=schema)))
            result=stream.wait_for_result()
            terminal() # actual SDK terminal response, not a cancellation request
            if result.model_info.model_key!=audit['model_key'] or result.stats.stop_reason not in ('eosFound','stopStringFound'):
                raise RuntimeError('Incomplete or mismatched raw SDK result')
            text=decode_reply(result.content,rule)
            if len(text)>config['limits']['max_speech_chars']:raise RuntimeError('SDK reply exceeds speech limit')
            return text
    return SLOT.execute(operation,audit['timeout_s'],(audit['base_url'].rstrip('/'),audit['model']))
