"""Optional owned nonblocking libasound PCM backend. No aplay/wall-time cursor.

Construct only after explicit local audio opt-in. Stop attempts hardware pause
before reading delay; unsupported pause still drops, but disables resume.
"""
import ctypes as C
import ctypes.util
import threading


class AlsaPCM:
    def __init__(self,device):
        if not isinstance(device,str) or not device or len(device)>128:raise ValueError('Explicit ALSA device')
        path=ctypes.util.find_library('asound')
        if not path:raise RuntimeError('libasound unavailable')
        self.lib=C.CDLL(path);self.device=device;self.lock=threading.Lock()
        self.stream=None;self.handle=None;self.stopped=True;self.written=0;self.cursor=0;self.final={};self.drained=False
        signatures=dict(snd_pcm_open=(C.c_int,[C.POINTER(C.c_void_p),C.c_char_p,C.c_int,C.c_int]),
            snd_pcm_set_params=(C.c_int,[C.c_void_p,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_int,C.c_uint]),
            snd_pcm_writei=(C.c_long,[C.c_void_p,C.c_void_p,C.c_ulong]),
            snd_pcm_delay=(C.c_int,[C.c_void_p,C.POINTER(C.c_long)]),
            snd_pcm_state=(C.c_int,[C.c_void_p]),snd_pcm_pause=(C.c_int,[C.c_void_p,C.c_int]),
            snd_pcm_drain=(C.c_int,[C.c_void_p]),snd_pcm_drop=(C.c_int,[C.c_void_p]),snd_pcm_close=(C.c_int,[C.c_void_p]))
        for name,(result,args) in signatures.items():
            fn=getattr(self.lib,name);fn.restype=result;fn.argtypes=args

    def reserve(self,stream):
        with self.lock:
            if not self.stopped or self.handle:raise RuntimeError('PCM owner still active')
            self.stream=stream;self.stopped=False;self.written=self.cursor=0;self.final={};self.drained=False;self.drained=False

    def start(self,stream,rate):
        with self.lock:
            if stream!=self.stream or self.stopped:raise RuntimeError('PCM stream withdrawn')
            handle=C.c_void_p()
            # Playback=0, NONBLOCK=1. Format S16_LE=2, RW_INTERLEAVED=3, mono.
            if self.lib.snd_pcm_open(C.byref(handle),self.device.encode(),0,1)<0:raise RuntimeError('PCM open failed')
            self.handle=handle
            if self.lib.snd_pcm_set_params(handle,2,3,1,rate,1,100000)<0:raise RuntimeError('PCM params failed')

    def write(self,stream,pcm):
        with self.lock:
            if stream!=self.stream or self.stopped:return 0
            data=C.create_string_buffer(pcm);n=self.lib.snd_pcm_writei(self.handle,data,len(pcm)//2)
            if n==-11:return 0  # EAGAIN; no consumption inferred
            if n<0:raise RuntimeError('PCM write/underrun failure; cursor unknown')
            self.written+=n;return n

    def measured(self):
        if self.lib.snd_pcm_state(self.handle) not in (2,3,5,6):raise RuntimeError('PCM state/cursor unknown')
        delay=C.c_long()
        if self.lib.snd_pcm_delay(self.handle,C.byref(delay))<0 or not 0<=delay.value<=self.written:
            raise RuntimeError('PCM delay unknown')
        cursor=self.written-delay.value
        if cursor<self.cursor:raise RuntimeError('PCM cursor regressed')
        self.cursor=cursor;return cursor

    def finish(self,stream):
        with self.lock:
            if stream!=self.stream or self.stopped:raise RuntimeError('PCM withdrawn')
            if self.drained:return True
            value=self.lib.snd_pcm_drain(self.handle)
            if value==-11:return False
            if value<0 or self.lib.snd_pcm_state(self.handle)!=1:raise RuntimeError('PCM drain unknown')
            self.drained=True;self.cursor=self.written;return True

    def progress(self,stream):
        with self.lock:
            if stream!=self.stream:raise RuntimeError('PCM stream mismatch')
            if self.stopped:return self.final
            return dict(stream_id=stream,consumed_frames=self.written if self.drained else self.measured(),verified=True,provenance='device_consumed_pcm')

    def stop(self,stream):
        with self.lock:
            if stream!=self.stream:raise RuntimeError('PCM stream mismatch')
            if self.stopped:return self.final
            cursor=None;known=True
            if self.handle:
                try:
                    state=self.lib.snd_pcm_state(self.handle)
                    if state==1 and self.drained:cursor=self.written
                    elif state==2 and self.written==0:cursor=0
                    elif self.lib.snd_pcm_pause(self.handle,1)==0 and self.lib.snd_pcm_state(self.handle)==6:
                        cursor=self.measured()  # frozen hardware pointer before drop
                except Exception:cursor=None
                known=self.lib.snd_pcm_drop(self.handle)>=0 and self.lib.snd_pcm_state(self.handle)==1
                closed=self.lib.snd_pcm_close(self.handle)>=0
                known=known and closed;self.handle=None
            else:cursor=0  # withdrawn before start, no audio submitted
            self.stopped=True
            self.final=dict(stream_id=stream,verified_stopped=known,verified=cursor is not None,
                consumed_frames=cursor,provenance='device_consumed_pcm')
            return self.final
