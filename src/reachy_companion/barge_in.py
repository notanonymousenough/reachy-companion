"""Capture near-end speech through the robot's hardware AEC while it talks."""
import logging
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

    def trigger(self):
        if self.epoch != self.agent.microphone_epoch or self.stop.is_set():
            return
        if not self.interrupted.is_set():
            self.interrupted.set()
            self.agent.interruptions += 1
            self.agent.phase = 'recording'
            self.agent.expressions.hold()
            self.agent.stop_speaker()
            LOG.info('speech_interrupted_reply')

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
