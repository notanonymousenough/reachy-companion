"""Read-only runtime/placement helpers for finite PC experiments."""
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.parse import urlsplit


def native_environment(server,vendor_directory):
    environment=os.environ.copy()
    if vendor_directory is not None:
        vendor_directory=Path(vendor_directory)
        manifest=json.loads((Path(server).parent/'backend-manifest.json').read_text())
        if vendor_directory.name not in manifest.get('vendor_lib_package_names',[]) or not (vendor_directory/'cudart64_12.dll').is_file():
            raise ValueError('Audited installed CUDA vendor package required')
        path_key=next((key for key in environment if key.upper()=='PATH'),'PATH')
        environment[path_key]=str(vendor_directory)+os.pathsep+environment.get(path_key,'')
    return environment


def main_identity(model):
    import lmstudio
    lmstudio.set_sync_api_timeout(12)
    with lmstudio.Client(urlsplit(model['base_url']).netloc) as client:
        matches=[handle for handle in client.llm.list_loaded() if handle.get_info().identifier==model['id']]
        if len(matches)!=1:raise RuntimeError('Expected one already-loaded main')
        info=matches[0].get_info()
        if info.context_length!=model['context_tokens']:raise RuntimeError('Pinned main context changed')
        load_config=repr(matches[0].get_load_config())
        if len(load_config)>8192:raise RuntimeError('Load config receipt bound')
        return dict(id=info.identifier,instance_reference=info.instance_reference,context_tokens=info.context_length,
                    load_config=load_config)


def gpu_sample(index):
    result=subprocess.run(['nvidia-smi','-i',str(index),'--query-gpu=uuid,memory.total,memory.used,memory.free',
                           '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=2,check=True)
    lines=result.stdout.strip().splitlines()
    if len(lines)!=1:raise RuntimeError('Expected one selected GPU')
    fields=[value.strip() for value in lines[0].split(',')]
    if len(fields)!=4 or not fields[0].startswith('GPU-'):raise RuntimeError('GPU metrics unknown')
    values=[int(value) for value in fields[1:]]
    if any(value<0 for value in values):raise RuntimeError('Invalid GPU metrics')
    return dict(uuid=fields[0],total_mib=values[0],used_mib=values[1],free_mib=values[2])


def placement(log_path,gpu_layers):
    text=Path(log_path).read_text(encoding='utf-8',errors='replace')
    if not gpu_layers:
        if 'no GPU support' not in text and 'no GPUs' not in text:raise RuntimeError('CPU-only runtime placement not confirmed')
        return dict(device='cpu_pc',offloaded_layers=0,total_layers=None)
    matches=re.findall(r'offloaded (\d+)/(\d+) layers to GPU',text)
    if len(matches)!=1:raise RuntimeError('GPU offload receipt missing')
    offloaded,total=map(int,matches[0])
    if not 0<offloaded<=total:raise RuntimeError('Invalid offload receipt')
    return dict(device='gpu_pc' if offloaded==total else 'hybrid_pc',offloaded_layers=offloaded,total_layers=total)


class GPUHeadroom:
    """Abort only this private runtime on low/unknown headroom; never respawn."""
    def __init__(self,process,index,reserve,before):
        self.process,self.index,self.reserve=process,index,reserve
        self.minimum_free_mib=before['free_mib'];self.uuid=before['uuid'];self.samples=0
        self.abort_reason=None;self.done=threading.Event();self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()
    def run(self):
        while not self.done.is_set() and self.process.poll() is None:
            try:
                value=gpu_sample(self.index)
                self.minimum_free_mib=min(self.minimum_free_mib,value['free_mib']);self.samples+=1
                if value['uuid']!=self.uuid or value['free_mib']<self.reserve:self.abort_reason='low_or_changed_gpu_headroom'
            except Exception:self.abort_reason='gpu_headroom_unknown'
            if self.abort_reason:
                self.process.terminate();return
            self.done.wait(.2)
    def close(self):self.done.set();self.thread.join(timeout=3)
