"""Finite speech endpoint for a captured response, without speaker identity.

This is an utterance boundary only. It cannot establish a trusted negative
speech window for resuming an interrupted output.
"""
import math


class ResponseEndpoint:
    rate = 16000
    frame_bytes = 640  # 20 ms, mono S16LE

    def __init__(self, vad, *, max_seconds=8, silence_frames=30):
        if (type(max_seconds) not in (int,float) or not math.isfinite(max_seconds) or not 1<=max_seconds<=8
                or type(silence_frames) is not int or not 10<=silence_frames<=50):
            raise ValueError('Finite endpoint bounds required')
        self.vad = vad
        self.limit = int(max_seconds * 50)
        self.silence_frames = silence_frames
        self.pending = bytearray()
        self.frames = self.run = self.silence = 0
        self.started = False
        self.reason = None
        self.pcm = bytearray()

    def feed(self, pcm):
        if self.reason:
            return
        if len(pcm) % 2:
            raise ValueError('Complete S16LE samples required')
        # Reject oversized input before retaining it. A pipe read can include
        # the end of the utterance plus a bounded backlog.
        if len(pcm) > self.limit * self.frame_bytes:
            raise ValueError('Endpoint input exceeds finite bound')
        self.pending.extend(pcm)
        while len(self.pending) >= self.frame_bytes and not self.reason:
            frame = bytes(self.pending[:self.frame_bytes])
            del self.pending[:self.frame_bytes]
            speech = self.vad.is_speech(frame, self.rate)
            self.frames += 1
            self.pcm.extend(frame)
            self.run = self.run + 1 if speech else 0
            if self.run >= 5:
                self.started = True
            self.silence = 0 if speech else self.silence + 1
            if self.started and self.silence >= self.silence_frames:
                self.reason = 'speech_then_silence'
            elif self.frames >= self.limit:
                self.reason = 'response_deadline'
        if self.reason:
            self.pending.clear()

    def receipt(self):
        return dict(reason=self.reason, speech_started=self.started,
                    processed_frames=self.frames,
                    elapsed_s=self.frames * .02,
                    trusted_resume_window=False)

    def clear(self):
        self.pending.clear()
        self.pcm.clear()
