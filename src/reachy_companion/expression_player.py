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

    def run(self):
        handled = 0
        while not self.stopping.is_set():
            with self.condition:
                while self.version == handled and not self.stopping.is_set():
                    if self.state and self.state[0] == 'speaking':
                        self.condition.wait(self.settings['repeat_seconds'])
                        if self.version == handled:
                            break
                    else:
                        self.condition.wait(.5)
                if self.stopping.is_set():
                    break
                state, version = self.state, self.version
            if state is None:
                continue
            try:
                plan = self.request(self.config['network']['voice_url'], '/expression/plan',
                                    {'phase': state[0], 'emotion': state[1]}, timeout=self.config['timeouts']['http'])
                with self.condition:
                    stale = self.version != version
                if not stale and plan.get('steps'):
                    self.request(self.config['network']['hub_url'], '/actions/expression',
                                 {'steps': plan['steps']}, timeout=self.config['timeouts']['http'])
                    self.last_expression = {'phase': state[0], 'emotion': state[1]}
                self.last_error = None
            except Exception as exc:
                # Cosmetic failures never prevent a spoken answer.
                self.last_error = str(exc)
                LOG.warning('expression_unavailable phase=%s error=%s', state[0], exc)
            finally:
                with self.condition:
                    handled = version
                    self.completed = max(self.completed, version)
                    self.condition.notify_all()
