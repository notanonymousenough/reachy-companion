"""Capture near-end speech through the robot's hardware AEC while it talks."""
import logging
import base64
import re
from difflib import SequenceMatcher
import threading

LOG = logging.getLogger('reachy-barge-in')


class BargeInMonitor:
    def __init__(self, agent):
        self.agent = agent
        self.epoch = agent.microphone_epoch
        self.stop = threading.Event()
        self.interrupted = threading.Event()
        self.pcm = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def trigger(self, pcm=None):
        if self.epoch != self.agent.microphone_epoch or self.stop.is_set():
            return False
        if pcm and self.agent.config['conversation']['barge_in'].get('confirm_with_stt', False):
            try:
                recognized = self.agent.request(self.agent.config['network']['voice_url'], '/transcribe',
                    {'pcm_base64': base64.b64encode(pcm).decode()}, timeout=self.agent.config['timeouts']['http'])
                text = recognized['transcript']
                if not text:
                    return False
                if recognized['decision']['action'] != 'stop':
                    heard = re.findall(r'\w+', text.lower().replace('ё', 'е').replace('reachy', 'ричи'))
                    own = set(re.findall(r'\w+', self.agent.current_reply_text.lower().replace('ё', 'е')))
                    if heard and sum(any(word == other or SequenceMatcher(None, word, other).ratio() >= .8 for other in own) for word in heard)/len(heard) >= self.agent.config['conversation']['barge_in'].get('echo_word_overlap', .75):
                        return False
                if self.epoch != self.agent.microphone_epoch or not self.agent.microphone.enabled:
                    return False
            except Exception as exc:
                LOG.warning('interruption_confirmation_failed error=%s', exc)
                self.agent.barge_in_error = str(exc)
                return False
        if not self.interrupted.is_set():
            self.interrupted.set()
            self.agent.interruptions += 1
            self.agent.phase = 'recording'
            self.agent.expressions.hold()
            self.agent.stop_speaker(abort_stream=False)
            self.agent.barge_in_error = None
            LOG.info('speech_interrupted_reply')
        return True

    def run(self):
        try:
            self.pcm = self.agent.capture(during_reply=True, on_speech=self.trigger, stop_event=self.stop)
        except Exception as exc:
            LOG.warning('barge_in_capture_failed error=%s', exc)
            self.agent.barge_in_error = str(exc)

    def finish(self):
        if not self.interrupted.is_set() or self.epoch != self.agent.microphone_epoch:
            self.stop.set()
        timeout = (self.agent.audio['max_recording_seconds'] + 3 if self.interrupted.is_set()
                   else self.agent.config['timeouts']['process_stop'] + 2)
        self.thread.join(timeout=timeout)
        if self.thread.is_alive():
            self.stop.set()
            self.thread.join(timeout=self.agent.config['timeouts']['process_stop'] + 2)
        if self.thread.is_alive():
            raise RuntimeError('Interruption microphone did not stop')
        if self.interrupted.is_set() and self.epoch == self.agent.microphone_epoch and self.agent.microphone.enabled:
            return self.pcm
        return None
