"""Owned nonblocking capture with explicitly monotonic ALSA timestamps.

No import opens a device. Unsupported timestamp mapping fails closed; receipt
time is never substituted for capture time.
"""
import ctypes as C
import ctypes.util
import time


class Timespec(C.Structure):
    _fields_=[('seconds', C.c_long), ('nanoseconds', C.c_long)]


class AlsaCapture:
    rate=16000
    channels=2
    def __init__(self, device):
        self.lib=C.CDLL(ctypes.util.find_library('asound'))
        self.handle=C.c_void_p();self.previous_end=None;self.closed=False
        self.calls=0;self.call_seconds=0;self.max_call_seconds=0
        signatures=dict(
            snd_pcm_open=(C.c_int,[C.POINTER(C.c_void_p),C.c_char_p,C.c_int,C.c_int]),
            snd_pcm_set_params=(C.c_int,[C.c_void_p,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_int,C.c_uint]),
            snd_pcm_sw_params_malloc=(C.c_int,[C.POINTER(C.c_void_p)]),
            snd_pcm_sw_params_free=(None,[C.c_void_p]),
            snd_pcm_sw_params_current=(C.c_int,[C.c_void_p,C.c_void_p]),
            snd_pcm_sw_params_set_tstamp_mode=(C.c_int,[C.c_void_p,C.c_void_p,C.c_int]),
            snd_pcm_sw_params_set_tstamp_type=(C.c_int,[C.c_void_p,C.c_void_p,C.c_int]),
            snd_pcm_sw_params=(C.c_int,[C.c_void_p,C.c_void_p]),
            snd_pcm_readi=(C.c_long,[C.c_void_p,C.c_void_p,C.c_ulong]),
            snd_pcm_avail_update=(C.c_long,[C.c_void_p]),
            snd_pcm_start=(C.c_int,[C.c_void_p]),
            snd_pcm_htimestamp=(C.c_int,[C.c_void_p,C.POINTER(C.c_ulong),C.POINTER(Timespec)]),
            snd_pcm_drop=(C.c_int,[C.c_void_p]),snd_pcm_close=(C.c_int,[C.c_void_p]))
        for name,(result,args) in signatures.items():
            fn=getattr(self.lib,name);fn.restype=result;fn.argtypes=args
        def checked(name,*args):
            if getattr(self.lib,name)(*args)<0:raise RuntimeError(name+' unavailable')
        try:
            checked('snd_pcm_open',C.byref(self.handle),device.encode(),1,1)
            checked('snd_pcm_set_params',self.handle,2,3,2,16000,0,100000)
            parameters=C.c_void_p()
            checked('snd_pcm_sw_params_malloc',C.byref(parameters))
            try:
                checked('snd_pcm_sw_params_current',self.handle,parameters)
                checked('snd_pcm_sw_params_set_tstamp_mode',self.handle,parameters,1)
                checked('snd_pcm_sw_params_set_tstamp_type',self.handle,parameters,1)
                checked('snd_pcm_sw_params',self.handle,parameters)
            finally:self.lib.snd_pcm_sw_params_free(parameters)
            checked('snd_pcm_start',self.handle)
        except BaseException:
            self.close();raise

    def read(self, max_frames=1024):
        start=time.monotonic()
        try:return self._read(max_frames)
        finally:
            elapsed=time.monotonic()-start;self.calls+=1;self.call_seconds+=elapsed
            self.max_call_seconds=max(self.max_call_seconds,elapsed)

    def _read(self, max_frames):
        if self.closed or type(max_frames) is not int or not 1<=max_frames<=4096:raise ValueError('Capture bound')
        ready=self.lib.snd_pcm_avail_update(self.handle)
        if ready<0:raise RuntimeError('Capture continuity unavailable: '+str(ready))
        if ready<320:return None
        buffer=C.create_string_buffer(max_frames*4)
        count=self.lib.snd_pcm_readi(self.handle,buffer,max_frames)
        if count==-11:return None
        if count<=0:raise RuntimeError('Capture overrun/unknown continuity')
        available=C.c_ulong();stamp=Timespec()
        if self.lib.snd_pcm_htimestamp(self.handle,C.byref(available),C.byref(stamp))<0:
            raise RuntimeError('Capture timestamp unavailable')
        captured_end=stamp.seconds+stamp.nanoseconds/1e9-available.value/16000
        now=time.monotonic()
        if (not 0<=now-captured_end<=.25
                or self.previous_end is not None and captured_end<self.previous_end):
            raise RuntimeError('Capture clock mapping stale/nonmonotonic')
        self.previous_end=captured_end
        return dict(pcm=buffer.raw[:count*4],frames=count,captured_end=captured_end,
                    provenance='alsa_monotonic_available_position')

    def close(self):
        if self.closed:return True
        self.closed=True
        if not self.handle:return True
        dropped=self.lib.snd_pcm_drop(self.handle)>=0
        closed=self.lib.snd_pcm_close(self.handle)>=0
        self.handle=None
        return dropped and closed
