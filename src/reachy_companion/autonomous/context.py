"""PC latest-only video cache and persistent memory, independent of inference lanes."""
from collections import deque
import json
import os
import struct
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler
from .memory import MemoryStore
from .perception import pixel_metrics


class LatestVideo:
    def __init__(self):
        self.lock=threading.Lock();self.current=None;self.gaps=0;self.retired=deque(maxlen=128)
    def publish(self,metadata,metrics,now):
        if not isinstance(metadata['producer_boot_id'],str) or not 1<=len(metadata['producer_boot_id'])<=128 or type(metadata['seq']) is not int or not 0<=metadata['seq']<=2**63-1:
            raise ValueError('Invalid video producer sequence')
        with self.lock:
            if metadata['producer_boot_id'] in self.retired:raise ValueError('Retired video producer')
            if self.current:
                old=self.current[0]
                if metadata['producer_boot_id']==old['producer_boot_id']:
                    if metadata['seq']<=old['seq']:return False
                    self.gaps+=max(0,metadata['seq']-old['seq']-1)
                else:self.retired.append(old['producer_boot_id'])
            self.current=(dict(metadata),dict(metrics),now)
            return True
    def failure(self):
        with self.lock:self.gaps+=1
    def clear(self):
        with self.lock:self.current=None
    def snapshot(self,now,privacy_all=False):
        with self.lock:
            if privacy_all or not self.current:
                return dict(id='camera.pixel_quality',state='disabled' if privacy_all else 'no_data',age_ms=None,summary='',
                            age_bounds_ms=dict(lower=0,upper=None),gaps=min(self.gaps,2**31-1))
            metadata,metrics,received=self.current
            elapsed=max(0,int((now-received)*1000))
            # Camera exposure preceded PC receipt. This is a valid lower bound;
            # physical sensor latency + robot/PC clock offset remain unbounded.
            state='stale' if elapsed>2000 else 'unknown'
            summary=f"Sample {metadata['frame_id']}: pixel luminance {metrics['mean_luminance']}/255; capture age upper bound unknown."
            return dict(id='camera.pixel_quality',state=state,age_ms=None,summary=summary[:256],
                        age_bounds_ms=dict(lower=elapsed,upper=None),gaps=min(self.gaps,2**31-1),
                        lineage_id=metadata['lineage_id'],source_id=metadata['frame_id'])


class ContextProvider:
    def __init__(self,config,boot_id):
        self.config=config;self.video=LatestVideo();self.memory=MemoryStore(config['memory_path'],config['namespaces'])
        self.boot_id=boot_id;self.policy_lock=threading.Lock();self.scope=None;self.privacy_all=True;self.policy_seq=0
        self.retired_hubs=deque(maxlen=128)
        self.done=threading.Event();self.thread=None
        if config.get('video_url'):
            if len(os.environ.get(config['video_token_env'],''))<32:raise ValueError('Video token required')
            self.thread=threading.Thread(target=self.poll,name='video-latest-only',daemon=True);self.thread.start()
    def poll(self):
        opener=build_opener(ProxyHandler({}))
        while not self.done.is_set():
            try:
                with self.policy_lock:
                    scope=dict(self.scope) if self.scope else None;privacy_all=self.privacy_all
                    self.policy_seq+=1;sequence=self.policy_seq
                if scope is None:
                    self.done.wait(.1);continue
                policy=dict(scope=scope,privacy_all=privacy_all,seq=sequence)
                policy_request=Request(self.config['video_url'].rstrip('/')+'/policy',data=json.dumps(policy).encode(),
                                       headers={'Authorization':'Bearer '+os.environ[self.config['video_token_env']],'Content-Type':'application/json'})
                with opener.open(policy_request,timeout=1) as response:response.read(1024)
                if privacy_all:
                    self.video.clear();self.done.wait(self.config.get('video_poll_s',.5));continue
                request=Request(self.config['video_url'].rstrip('/')+'/latest',headers={'Authorization':'Bearer '+os.environ[self.config['video_token_env']]})
                with opener.open(request,timeout=1) as response:payload=response.read(1048577)
                if not 4<=len(payload)<=1048576:raise ValueError('Video packet bound')
                length=struct.unpack('!I',payload[:4])[0]
                if not 1<=length<=8192 or length+4>=len(payload):raise ValueError('Video header bound')
                metadata=json.loads(payload[4:4+length]);raw=payload[4+length:]
                if metadata.get('audio_initialised') is not False:raise ValueError('Video-only gate')
                if any(not isinstance(metadata.get(key),str) or not 1<=len(metadata[key])<=128 for key in ('frame_id','lineage_id')):raise ValueError('Video provenance')
                metrics=pixel_metrics(raw,metadata['frame_sha256'])
                with self.policy_lock:
                    if not self.privacy_all and self.scope==scope and metadata.get('scope')==scope:
                        self.video.publish(metadata,metrics,time.monotonic())
            except Exception:self.video.failure()
            finally:
                payload=raw=None
            self.done.wait(self.config.get('video_poll_s',.5))
    def snapshot(self,query,privacy_all,hub_boot_id,operator_epoch):
        if not isinstance(hub_boot_id,str) or not 1<=len(hub_boot_id)<=128 or type(operator_epoch) is not int or operator_epoch<0:
            raise ValueError('Context owner scope')
        with self.policy_lock:
            if hub_boot_id in self.retired_hubs:raise ValueError('Retired context owner')
            if self.scope:
                if self.scope['hub_boot_id']==hub_boot_id and operator_epoch<self.scope['operator_epoch']:raise ValueError('Old operator epoch')
                if self.scope['hub_boot_id']!=hub_boot_id:self.retired_hubs.append(self.scope['hub_boot_id'])
            self.scope=dict(hub_boot_id=hub_boot_id,operator_epoch=operator_epoch,compute_boot_id=self.boot_id)
            self.privacy_all=privacy_all
            if privacy_all:self.video.clear()
        memory=self.memory.recall(query if not privacy_all else '')
        if privacy_all:memory['items']=[]
        return dict(memory=memory,
                    sensors=[self.video.snapshot(time.monotonic(),privacy_all)])
    def close(self):
        self.done.set()
        if self.thread:self.thread.join(timeout=2)
        self.video.clear();self.memory.close()
