"""Robot-side transport of compute-generated plans through the hub."""
import logging
import threading
import time

LOG = logging.getLogger('reachy-expressions')


class ExpressionPlayer:
    def __init__(self, config, request, stopping):
        self.config, self.request, self.stopping = config, request, stopping
        self.settings = config['conversation'].get('expressions', {})
        self.condition = threading.Condition()
        self.state = None
        self.cues = []
        self.clock = None
        self.version = self.completed = 0
        self.last_error = None
        self.last_expression = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        if self.settings.get('enabled', False):
            self.thread.start()

    def set(self, phase, emotion='neutral', wait=False):
        if not self.settings.get('enabled', False):
            return
        with self.condition:
            if self.state != (phase, emotion):
                self.cues = []
                self.clock = None
                self.state = (phase, emotion)
                self.version += 1
                self.condition.notify_all()
            version = self.version
            if wait:
                deadline = time.monotonic() + self.config['timeouts']['http'] + self.settings['max_total_seconds'] + 2
                while self.completed < version and not self.stopping.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Expression did not settle before microphone capture')
                    self.condition.wait(min(remaining, .2))
        if wait:
            self.stopping.wait(self.settings['settle_seconds'])

    def timeline(self, cues, clock):
        if not self.settings.get('enabled', False):
            return
        from .motion_limits import validate_steps
        valid = []
        maximum = self.settings['speech_sync']['max_cues']
        for cue in cues:
            if not isinstance(cue.get('at'), (int, float)) or not 0 <= cue['at'] <= self.config['streaming']['max_output_seconds']:
                raise ValueError('Invalid motion timestamp')
            validate_steps(cue['steps'], self.settings)
            valid.append(cue)
        with self.condition:
            if self.state != ('timeline', 'neutral') or self.clock is not clock:
                self.state = ('timeline', 'neutral')
                self.version += 1
                self.cues = []
                self.clock = clock
            self.cues = sorted((self.cues + valid)[:maximum], key=lambda cue: cue['at'])
            self.condition.notify_all()

    def hold(self):
        with self.condition:
            self.state = None
            self.cues = []
            self.clock = None
            self.version += 1
            self.condition.notify_all()

    def run(self):
        handled = 0
        variant = 0
        while not self.stopping.is_set():
            cue = None
            with self.condition:
                while not self.stopping.is_set():
                    if self.state == ('timeline', 'neutral'):
                        if self.cues and self.cues[0]['at'] <= self.clock.seconds():
                            cue = self.cues.pop(0)
                            # Late cues are merged into the current target, never queued as a backlog.
                            while self.cues and self.cues[0]['at'] <= self.clock.seconds():
                                cue = self.cues.pop(0)
                            break
                        self.condition.wait(.05)
                    elif self.version != handled:
                        break
                    elif self.state and (self.state[0] == 'speaking' or (self.state[0] == 'processing' and self.settings.get('library', {}).get('repeat_processing', False))):
                        self.condition.wait(self.settings['repeat_seconds'])
                        if self.version == handled:
                            break
                    else:
                        self.condition.wait(.5)
                if self.stopping.is_set():
                    break
                state, version = self.state, self.version
            if state is None:
                with self.condition:
                    handled = version
                    self.completed = max(self.completed, version)
                    self.condition.notify_all()
                continue
            try:
                plan = ({'steps': cue['steps']} if cue is not None else
                        self.request(self.config['network']['voice_url'], '/expression/plan',
                                     {'phase': state[0], 'emotion': state[1], 'variant': variant % 10000}, timeout=self.config['timeouts']['http']))
                with self.condition:
                    stale = self.version != version
                if not stale and plan.get('steps'):
                    self.request(self.config['network']['hub_url'], '/actions/expression',
                                 {'steps': plan['steps']}, timeout=self.config['timeouts']['http'])
                    self.last_expression = ({'phase': 'speaking', 'emotion': cue.get('emotion', 'neutral'),
                                             'gesture': cue.get('gesture', 'auto'), 'phoneme': cue.get('phoneme', '')}
                                            if cue is not None else {'phase': state[0], 'emotion': state[1]})
                self.last_error = None
                variant += 1
            except Exception as exc:
                self.last_error = str(exc)
                LOG.warning('expression_unavailable phase=%s error=%s', state[0], exc)
            finally:
                with self.condition:
                    handled = version
                    self.completed = max(self.completed, version)
                    self.condition.notify_all()
