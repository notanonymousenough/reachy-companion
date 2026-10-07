"""Robot-side bounded audio transport; classification and rhythm run on the PC."""
import base64
import queue
import threading
import time
from collections import deque

class SoundMonitor:
    def __init__(self, agent):
        self.agent=agent;self.settings=agent.config['conversation']['sound_reactions'];self.music=False
        self.enter=self.leave=0;self.queue=queue.Queue(maxsize=1);self.last_sent=0;self.last_sound=0
        self.frames=deque(maxlen=round(self.settings['window_seconds']*1000/agent.audio['chunk_ms']))
        self.epoch=agent.microphone_epoch;self.last_error=None
        if self.settings['enabled']:threading.Thread(target=self.run,daemon=True).start()

    def reset(self):
        self.frames.clear();self.music=False;self.enter=self.leave=0
        self.epoch=self.agent.microphone_epoch
        while not self.queue.empty():
            try:self.queue.get_nowait()
            except queue.Empty:break

    def feed(self, chunk):
        if not self.settings['enabled']:return
        if self.epoch!=self.agent.microphone_epoch:self.reset()
        self.frames.append(chunk);now=time.monotonic()
        if now-self.last_sent<self.settings['interval_seconds'] or len(self.frames)*self.agent.audio['chunk_ms']<960:return
        self.last_sent=now
        item=(self.epoch,b''.join(self.frames),now)
        try:self.queue.put_nowait(item)
        except queue.Full:
            try:self.queue.get_nowait()
            except queue.Empty:pass
            try:self.queue.put_nowait(item)
            except queue.Full:pass

    def run(self):
        while not self.agent.stopping.is_set():
            try:epoch,pcm,at=self.queue.get(timeout=.3)
            except queue.Empty:continue
            if not self.agent.microphone.enabled or epoch!=self.agent.microphone_epoch:continue
            try:
                result=self.agent.request(self.agent.config['network']['voice_url'],'/sound/classify',{'pcm_base64':base64.b64encode(pcm).decode()},timeout=3)
                if not self.agent.microphone.enabled or epoch!=self.agent.microphone_epoch or self.agent.phase in ('speaking','processing'):continue
                self.last_error=None
                self.enter=self.enter+1 if result['kind']=='music' else 0
                self.leave=0 if result['kind']=='music' else self.leave+1
                if self.enter>=self.settings['music_enter_windows']:self.music=True
                if self.music and self.leave>=self.settings['music_exit_windows']:
                    self.music=False;self.agent.expressions.set('neutral');self.agent.phase='listening'
                if self.music:
                    self.agent.phase='music'
                    if result['kind']=='music':self.agent.expressions.dance(result,at)
                elif result['kind']=='sound' and time.monotonic()-self.last_sound>self.settings['sound_cooldown_seconds']:
                    self.last_sound=time.monotonic();self.agent.expressions.set('reacting','surprised',force=True)
            except Exception as exc:self.last_error=str(exc)
