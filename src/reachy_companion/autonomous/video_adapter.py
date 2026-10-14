"""PC-only bounded latest-frame processing; no camera/audio/model imports.

One actual worker and one replaceable pending frame. Invalidation drops pending
RAM and fences late output; it cannot erase the running function's owned buffer.
A blocked function retains its actual slot until return (also after close).
"""
import copy
import math
import struct
import threading
import time
from .contracts import decode
from .perception import pixel_metrics


def identity(metadata):
    if not isinstance(metadata,dict):raise ValueError('Video metadata required')
    for key in ('producer_boot_id','frame_id','lineage_id'):
        if not isinstance(metadata.get(key),str) or not 1<=len(metadata[key])<=128:raise ValueError('Video provenance bound')
    if type(metadata.get('seq')) is not int or not 0<=metadata['seq']<2**63:raise ValueError('Video sequence bound')
    if metadata.get('source_capture_time_verified',False) is not False or metadata.get('source_age_upper_ms') is not None:
        raise ValueError('Capture clock mapping has not been verified')
    lower=metadata.get('source_age_lower_ms',0)
    if type(lower) not in (int,float) or not math.isfinite(lower) or not 0<=lower<=2**31-1:raise ValueError('Video age bound')
    return metadata['producer_boot_id'],metadata['seq']


class FrameOrder:
    def __init__(self):self.head=None;self.retired=set();self.closed=False
    def accept(self,metadata):
        boot,seq=identity(metadata)
        if self.closed or boot in self.retired:raise ValueError('Retired/exhausted video producer fence')
        if self.head:
            old,previous=self.head
            if boot==old and seq<=previous:return False
            if boot!=old:
                if len(self.retired)>=128:self.closed=True;raise ValueError('Video producer fence capacity exhausted')
                self.retired.add(old)
        self.head=(boot,seq);return True


def decode_packet(payload):
    if not isinstance(payload,bytes) or not 4<=len(payload)<=1048576:raise ValueError('Video packet bound')
    length=struct.unpack('!I',payload[:4])[0]
    if not 1<=length<=8192 or length+4>=len(payload):raise ValueError('Video metadata bound')
    metadata=decode(payload[4:4+length]);identity(metadata)
    admission=metadata.get('admission_id')
    if type(metadata.get('video_protocol')) is not int or metadata['video_protocol']!=2 or not isinstance(admission,str) or not 1<=len(admission)<=128:raise ValueError('Versioned video admission required')
    if metadata.get('audio_initialised') is not False:raise ValueError('Camera-only producer required')
    scope=metadata.get('scope')
    if (not isinstance(scope,dict) or set(scope)!={'hub_boot_id','compute_boot_id','operator_epoch'}
            or any(not isinstance(scope[k],str) or not 1<=len(scope[k])<=128 for k in ('hub_boot_id','compute_boot_id'))
            or type(scope['operator_epoch']) is not int or not 0<=scope['operator_epoch']<2**63):raise ValueError('Video owner scope')
    digest=metadata.get('frame_sha256')
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Video digest')
    # No arbitrary source-header content is retained alongside the PC cache.
    selected={k:metadata[k] for k in ('producer_boot_id','seq','frame_id','lineage_id','scope','frame_sha256','source_age_lower_ms','admission_id') if k in metadata}
    for key in ('robot_boot_id','reader_boot_id'):
        value=metadata.get(key)
        if value is not None:
            if not isinstance(value,str) or not 1<=len(value)<=128:raise ValueError('Video source boot bound')
            selected[key]=value
    for key in ('pts_ns','buffer_running_time_ns','consumer_clock_ns','consumer_base_time_ns'):
        value=metadata.get(key)
        if value is not None and (type(value) is not int or not 0<=value<2**64):raise ValueError('Presentation clock observation bound')
        selected[key]=value
    selected.update(source_capture_time_verified=False,source_age_upper_ms=None)
    return selected,payload[4+length:]


class LatestFrameProcessor:
    def __init__(self,deliver,*,process=pixel_metrics,clock=time.monotonic,ttl_s=2):
        if type(ttl_s) not in (int,float) or not .1<=ttl_s<=2:raise ValueError('Video processing TTL bound')
        self.deliver=deliver;self.process=process;self.clock=clock;self.ttl=ttl_s
        self.condition=threading.Condition();self.order=FrameOrder();self.pending=None;self.active=False;self.closed=False
        self.serial=0;self.coalesced=0;self.expired=0;self.failed=0
        self.thread=threading.Thread(target=self.run,name='video-pixel-latest-only',daemon=True);self.thread.start()
    def submit(self,metadata,raw,received,ticket):
        if not isinstance(raw,bytes) or len(raw)>1048576:raise ValueError('Bounded RAM frame required')
        if type(received) not in (int,float) or not math.isfinite(received) or not 0<=self.clock()-received<=self.ttl:return False
        with self.condition:
            if self.closed:return False
            try:accepted=self.order.accept(metadata)
            except ValueError:
                if self.order.closed:self.closed=True;self.pending=None;self.condition.notify()
                raise
            if not accepted:return False
            self.serial+=1
            if self.pending is not None:self.coalesced+=1
            self.pending=(self.serial,copy.deepcopy(metadata),raw,received,ticket);self.condition.notify();return True
    def invalidate(self):
        with self.condition:self.serial+=1;self.pending=None;self.condition.notify()
    def expire_pending(self):
        with self.condition:
            if self.pending is not None and self.clock()-self.pending[3]>self.ttl:
                self.pending=None;self.expired+=1
    def commit(self,job,callback):
        # Caller holds its policy lock; callback may only update the local cache.
        with self.condition:
            if self.closed or job[0]!=self.serial or self.clock()-job[3]>self.ttl:return False
            return callback()
    def status(self):
        self.expire_pending()
        with self.condition:return dict(execution_busy=self.active,pending_raw_frames=int(self.pending is not None),
            closed=self.closed,coalesced=self.coalesced,expired=self.expired,failed=self.failed,
            running_buffer_owned_until_return=self.active)
    def run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.closed or self.pending is not None)
                if self.closed:return
                job=self.pending;self.pending=None;self.active=True
            result=None
            try:
                if self.clock()-job[3]>self.ttl:self.expired+=1;continue
                result=self.process(job[2],job[1]['frame_sha256'])
                if self.clock()-job[3]>self.ttl:self.expired+=1;continue
                with self.condition:
                    if self.closed or job[0]!=self.serial:continue
                self.deliver(self,job,result)
            except Exception:self.failed+=1
            finally:
                job=result=None
                with self.condition:self.active=False
    def close(self):
        with self.condition:self.closed=True;self.serial+=1;self.pending=None;self.condition.notify()
        self.thread.join(timeout=.2)
        return not self.thread.is_alive() # no false completion if the function remains blocked
