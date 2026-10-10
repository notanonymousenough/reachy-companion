"""Bounded PCM controls and aggregate diagnostics; no device or owner creation."""
import array
import math
import sys


def samples(pcm,channels=1):
    if not isinstance(pcm,bytes) or len(pcm)%(channels*2):raise ValueError('Complete S16LE frames required')
    values=array.array('h');values.frombytes(pcm)
    if sys.byteorder!='little':values.byteswap()
    return values


class Levels:
    def __init__(self):self.count=self.square=self.peak=self.rails=0
    def add(self,values):
        self.count+=len(values);self.square+=sum(value*value for value in values)
        self.peak=max(self.peak,max((abs(value) for value in values),default=0))
        self.rails+=sum(value in (-32768,32767) for value in values)
    def status(self):return dict(samples=self.count,rms=math.sqrt(self.square/self.count) if self.count else 0,
        peak=self.peak,rail_samples=self.rails)


class PcmGain:
    """Gain1 is bit-exact; opt-in gain uses the reviewed 30000-peak soft limiter."""
    def __init__(self,gain=1):
        if type(gain) not in (int,float) or not math.isfinite(gain) or not 1<=gain<=4:raise ValueError('TTS gain1..4 required')
        self.gain=gain;self.input=Levels();self.output=Levels();self.limited=0
    def process(self,pcm):
        if len(pcm)>8192:raise ValueError('Bounded PCM gain chunk required')
        values=samples(pcm);self.input.add(values)
        if self.gain==1:out=pcm;result=values
        else:
            self.limited+=sum(abs(value*self.gain)>30000 for value in values)
            result=array.array('h',(round(30000*math.tanh(self.gain*value/30000)) for value in values))
            out_values=array.array('h',result)
            if sys.byteorder!='little':out_values.byteswap()
            out=out_values.tobytes()
        self.output.add(result);return out
    def status(self):return dict(gain=self.gain,limiter_peak=30000 if self.gain!=1 else None,
        samples_above_soft_limit=self.limited,input=self.input.status(),output=self.output.status(),acoustic_audibility_verified=False)


class StereoChannels:
    def __init__(self,channel=0):
        if type(channel) is not int or channel not in (0,1):raise ValueError('Capture channel0/1 required')
        self.channel=channel;self.levels={scope:[Levels(),Levels()] for scope in ('owned_or_unknown_stop','echo_tail','endpoint')}
    def select(self,pcm,scope):
        if len(pcm)>65536 or scope not in self.levels:raise ValueError('Bounded channel diagnostic required')
        values=samples(pcm,2);channels=[values[0::2],values[1::2]]
        for stats,values in zip(self.levels[scope],channels):stats.add(values)
        selected=channels[self.channel]
        if sys.byteorder!='little':selected.byteswap()
        return selected.tobytes()
    def status(self):return dict(selected_channel=self.channel,scopes={scope:[item.status() for item in pair] for scope,pair in self.levels.items()},
        speaker_identity='unknown',raw_audio_retained=False)


class CaptureExclusion:
    """Capture starts after actual idle/known stop and its timestamped echo tail."""
    def __init__(self,tail_seconds=.2):
        if type(tail_seconds) not in (int,float) or not math.isfinite(tail_seconds) or not .2<=tail_seconds<=.5:
            raise ValueError('Finite echo tail.2...5s required')
        self.tail_seconds=tail_seconds;self.tail_until=0;self.pending_tail=False;self.last_stream=None;self.last_stop=None
    def classify(self,active_stream,status,captured_start,now):
        if any(type(value) not in (int,float) or not math.isfinite(value) for value in (captured_start,now)) or captured_start>now:
            raise ValueError('Local capture timestamp required')
        # Detect even a short owned stream that completed between capture polls.
        for event in status['timeline']:
            known=(event['kind']=='speech_stopped' and event.get('stop_known') is True
                or event['kind']=='joint_stop' and event.get('speech_stop_known') is True)
            if known and event.get('stream_id') is not None and (self.last_stop is None or event['at']>self.last_stop):
                self.last_stop=event['at'];self.last_stream=event['stream_id'];self.tail_until=max(self.tail_until,event['at']+self.tail_seconds)
        if (active_stream is not None or status['execution_busy'] is not False or status['stop_known'] is not True
                or status['closed'] is not False or status['quarantined'] is not False):
            if active_stream is not None:self.last_stream=active_stream
            self.pending_tail=True;return 'owned_or_unknown_stop'
        if self.pending_tail:
            self.tail_until=max(self.tail_until,now+self.tail_seconds);self.pending_tail=False
        return 'echo_tail' if captured_start<self.tail_until else 'endpoint'
