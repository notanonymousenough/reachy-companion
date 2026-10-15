"""Exact-reference SDK boundary for the independently audited finite smoke."""
import copy
from reachy_companion.autonomous.gateway import ModelBackend,BudgetRejected,ExecutionUnknown
from reachy_companion.spoken_reply_sdk import environment_audit,SDK_SOURCES,SDK_TREE


def verify_sdk(expected):
    if (type(expected) is not dict or expected.get('sdk_version')!='1.5.0'
            or expected.get('sdk_sources')!=SDK_SOURCES or expected.get('sdk_tree_sha256')!=SDK_TREE
            or expected.get('instance_spec_verified') is not True):
        raise ValueError('Independent exact-instance SDK 1.5.0 capability/source audit required')
    actual=environment_audit()
    if any(actual[key]!=expected.get(key) for key in ('sdk_version','sdk_sources','sdk_tree_sha256','environment_sha256')):
        raise ValueError('Installed SDK source/environment changed')


class FrozenHandle:
    def __init__(self,client,model,binding):
        self.client,self.model,self.binding=client,model,copy.deepcopy(binding)
        required={'id','model_key','instance_reference','context_tokens','load_config'}
        if (type(binding) is not dict or set(binding)!=required
                or any(type(binding[key]) is not str or not binding[key] for key in required-{'context_tokens'})
                or type(binding['context_tokens']) is not int or binding['context_tokens']!=model['context_tokens']
                or binding['id']!=model['id']):
            raise BudgetRejected('Exact frozen main binding required')
        self.spec=dict(type='instanceReference',instanceReference=binding['instance_reference'])
        self.check()

    def check(self):
        info=self.client.llm.get_model_info(dict(self.spec))
        observed=dict(id=info.identifier,model_key=info.model_key,instance_reference=info.instance_reference,
            context_tokens=info.context_length,load_config=repr(self.client.llm._get_load_config(dict(self.spec))))
        if (type(info.context_length) is not int or any(type(observed[key]) is not str
                for key in ('id','model_key','instance_reference','load_config')) or observed!=self.binding):
            raise BudgetRejected('Frozen main instance/load/context changed')
        return observed

    def tokenize(self,text):
        self.check()
        tokens=self.client.llm._tokenize_text(dict(self.spec),text)
        self.check()
        return tokens

    def complete(self,prompt,config):
        self.check() # before submit: failures cannot target an alias replacement
        try:
            result=self.client.llm._complete_stream(dict(self.spec),prompt,config=config).wait_for_result()
            if result.model_info.model_key!=self.binding['model_key']:
                raise RuntimeError('Mismatched prediction model key')
            self.check()
            return result
        except Exception as exc:
            raise ExecutionUnknown('Fixed-reference prediction terminal/identity unknown') from exc


def main_identity(model,binding,sdk_audit):
    verify_sdk(sdk_audit)
    import lmstudio
    from urllib.parse import urlsplit
    lmstudio.set_sync_api_timeout(12)
    with lmstudio.Client(urlsplit(model['base_url']).netloc) as client:
        return FrozenHandle(client,model,binding).check()


class FrozenModelBackend(ModelBackend):
    def __init__(self,config,*,main_binding,sdk_audit):
        verify_sdk(sdk_audit)
        self.main_binding=copy.deepcopy(main_binding)
        super().__init__(config)

    def loaded(self,model,client):
        if model is not self.config['models']['main']:
            raise BudgetRejected('Fixed main boundary cannot select another model')
        return FrozenHandle(client,model,self.main_binding)

    def generate_loaded(self,role,data,handle=None,context_input=False):
        if role=='main':
            if type(handle) is not FrozenHandle or handle.binding!=self.main_binding:
                raise BudgetRejected('Unbound main handle cannot tokenize or complete')
            handle.check()
        return super().generate_loaded(role,data,handle,context_input=context_input)
