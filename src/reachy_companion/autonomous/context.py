"""PC latest-only video cache and persistent memory, independent of inference lanes."""
from collections import deque
import json
import os
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler
from .memory import MemoryStore
from .video_adapter import FrameOrder,identity,decode_packet,LatestFrameProcessor
from .contracts import uid
from .config import context_mode


class LatestVideo:
    def __init__(self):
        self.lock=threading.Lock();self.current=None;self.gaps=0;self.order=FrameOrder()
    def publish(self,metadata,metrics,now):
        identity(metadata)
        with self.lock:
            previous=self.order.head
            try:accepted=self.order.accept(metadata)
            except ValueError:
                if self.order.closed:self.current=None
                raise
            if not accepted:return False
            if previous and previous[0]==metadata['producer_boot_id']:self.gaps+=max(0,metadata['seq']-previous[1]-1)
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
            elapsed=min(2**31-1,max(0,int((now-received)*1000))+int(metadata.get('source_age_lower_ms',0)))
            # Camera exposure preceded PC receipt. This is a valid lower bound;
            # physical sensor latency + robot/PC clock offset remain unbounded.
            state='stale' if elapsed>2000 else 'unknown'
            summary='' # unknown capture freshness is not model evidence; metrics stay in the PC diagnostic cache
            return dict(id='camera.pixel_quality',state=state,age_ms=None,summary=summary[:256],
                        age_bounds_ms=dict(lower=elapsed,upper=None),gaps=min(self.gaps,2**31-1),
                        lineage_id=metadata['lineage_id'],source_id=metadata['frame_id'])


class ContextProvider:
    def __init__(self,config,boot_id):
        self.memory_only=context_mode(config)=='memory_only'
        self.config=config;self.video=None if self.memory_only else LatestVideo()
        self.memory=MemoryStore(config['memory_path'],config['namespaces'])
        self.boot_id=boot_id;self.policy_lock=threading.Lock();self.scope=None;self.privacy_all=True;self.policy_seq=0
        self.owner_deadline=0;self.revoked_epochs={}
        self.retired_hubs=deque(maxlen=128)
        self.done=threading.Event();self.thread=None;self.video_worker=None;self.video_generation=0;self.ingress_boot=None;self.video_admission=uid()
        if not self.memory_only and config.get('video_url'):
            if len(os.environ.get(config['video_token_env'],''))<32:raise ValueError('Video token required')
            self.video_worker=LatestFrameProcessor(self.video_completed,ttl_s=config.get('video_processing_ttl_s',2))
            self.thread=threading.Thread(target=self.poll,name='video-latest-only',daemon=True);self.thread.start()
    def poll(self):
        if self.memory_only:return
        opener=build_opener(ProxyHandler({}))
        while not self.done.is_set():
            try:
                scope,privacy_all,sequence=self.policy(time.monotonic())
                if scope is None:
                    self.done.wait(.1);continue
                policy=dict(scope=scope,privacy_all=privacy_all,seq=sequence)
                with self.policy_lock:ticket=(dict(scope),self.video_generation,self.video_admission)
                policy['admission_id']=ticket[2]
                policy_request=Request(self.config['video_url'].rstrip('/')+'/policy',data=json.dumps(policy).encode(),
                                       headers={'Authorization':'Bearer '+os.environ[self.config['video_token_env']],'Content-Type':'application/json'})
                with opener.open(policy_request,timeout=1) as response:response.read(1024)
                if privacy_all:
                    self.video.clear();self.done.wait(self.config.get('video_poll_s',.5));continue
                request=Request(self.config['video_url'].rstrip('/')+'/latest',headers={'Authorization':'Bearer '+os.environ[self.config['video_token_env']]})
                with opener.open(request,timeout=1) as response:payload=response.read(1048577)
                received=time.monotonic() # AFTER response; request-BEGIN cannot prove capture preceded it
                metadata,raw=decode_packet(payload)
                self.admit_video(metadata,raw,received,ticket)
            except Exception:self.video.failure()
            finally:
                payload=raw=None
                if self.video_worker:self.video_worker.expire_pending()
            self.done.wait(self.config.get('video_poll_s',.5))
    def invalidate_video(self):
        # Called under policy_lock. Retain sequence/retirement fences on clear.
        self.video_generation+=1;self.video_admission=uid()
        if self.video is not None:self.video.clear()
        if self.video_worker:self.video_worker.invalidate()
    def admit_video(self,metadata,raw,received,ticket):
        with self.policy_lock:
            if not self.video_current(ticket) or metadata.get('scope')!=self.scope or metadata.get('admission_id')!=self.video_admission:return False
            try:accepted=self.video_worker.submit(metadata,raw,received,ticket)
            except ValueError:
                if self.video_worker.closed:self.video.clear()
                raise
            if accepted and self.ingress_boot!=metadata['producer_boot_id']:
                self.video.clear();self.ingress_boot=metadata['producer_boot_id']
            return accepted
    def video_current(self,ticket):
        return (not self.memory_only and not self.done.is_set() and not self.privacy_all and time.monotonic()<self.owner_deadline
            and ticket==(self.scope,self.video_generation,self.video_admission))
    def video_completed(self,worker,job,metrics):
        with self.policy_lock:
            if not self.video_current(job[4]):return False
            return worker.commit(job,lambda:self.video.publish(job[1],metrics,job[3]))
    def policy(self,now):
        with self.policy_lock:
            scope=dict(self.scope) if self.scope else None
            private=self.privacy_all or now>=self.owner_deadline
            if private:self.invalidate_video()
            self.policy_seq+=1
            return scope,private,self.policy_seq
    def revoke(self,hub_boot_id,operator_epoch,terminal=False):
        if not isinstance(hub_boot_id,str) or not 1<=len(hub_boot_id)<=128 or type(operator_epoch) is not int or not 0<=operator_epoch<2**63 or type(terminal) is not bool:
            raise ValueError('Context revoke scope')
        with self.policy_lock:
            if hub_boot_id not in self.revoked_epochs and len(self.revoked_epochs)>=128:
                # Never evict a fence to admit an old delayed request.
                self.done.set();self.privacy_all=True;self.owner_deadline=0;self.invalidate_video()
                raise RuntimeError('Context fence capacity exhausted')
            floor=2**63-1 if terminal else operator_epoch
            self.revoked_epochs[hub_boot_id]=max(floor,self.revoked_epochs.get(hub_boot_id,-1))
            if self.scope is None or self.scope['hub_boot_id']==hub_boot_id:
                self.privacy_all=True;self.owner_deadline=0;self.invalidate_video()
            return dict(revoked=True,hub_boot_id=hub_boot_id,operator_epoch=operator_epoch,terminal=terminal)

    def snapshot(self,query,privacy_all,hub_boot_id,operator_epoch):
        if not isinstance(hub_boot_id,str) or not 1<=len(hub_boot_id)<=128 or type(operator_epoch) is not int or not 0<=operator_epoch<2**63 or type(privacy_all) is not bool:
            raise ValueError('Context owner scope')
        with self.policy_lock:
            if self.done.is_set() or operator_epoch<=self.revoked_epochs.get(hub_boot_id,-1):raise ValueError('Revoked context owner')
            if hub_boot_id in self.retired_hubs:raise ValueError('Retired context owner')
            if self.scope:
                if self.scope['hub_boot_id']==hub_boot_id and operator_epoch<self.scope['operator_epoch']:raise ValueError('Old operator epoch')
                if self.scope['hub_boot_id']!=hub_boot_id:
                    if len(self.retired_hubs)>=128:
                        self.done.set();self.privacy_all=True;self.owner_deadline=0;self.invalidate_video()
                        raise RuntimeError('Context owner fence capacity exhausted')
                    self.retired_hubs.append(self.scope['hub_boot_id'])
            next_scope=dict(hub_boot_id=hub_boot_id,operator_epoch=operator_epoch,compute_boot_id=self.boot_id)
            if self.scope!=next_scope or self.privacy_all!=privacy_all or time.monotonic()>=self.owner_deadline:self.invalidate_video()
            self.scope=next_scope
            self.privacy_all=privacy_all
            self.owner_deadline=time.monotonic()+self.config.get('owner_ttl_s',1.5)
            if privacy_all and self.video is not None:self.video.clear()
        memory=self.memory.recall(query if not privacy_all else '')
        with self.policy_lock:
            if self.done.is_set() or operator_epoch<=self.revoked_epochs.get(hub_boot_id,-1):raise ValueError('Revoked context owner')
            if self.scope['hub_boot_id']!=hub_boot_id or self.scope['operator_epoch']!=operator_epoch:raise ValueError('Changed context owner')
            private=privacy_all or self.privacy_all or time.monotonic()>=self.owner_deadline
            if private:memory['items']=[]
            return dict(memory=memory,sensors=[] if self.memory_only else [self.video.snapshot(time.monotonic(),private)],
                video_processing=self.video_worker.status() if self.video_worker else None)
    def close(self):
        self.done.set()
        self.privacy_all=True
        with self.policy_lock:self.invalidate_video()
        if self.thread:self.thread.join(timeout=2)
        if self.video_worker:self.video_worker.close()
        if self.video is not None:self.video.clear()
        self.memory.close()
        return dict(poll_execution_busy=bool(self.thread and self.thread.is_alive()),
            processor=self.video_worker.status() if self.video_worker else None,raw_files_created=0)
