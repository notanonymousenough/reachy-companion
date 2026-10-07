"""Expression selection/planning on the compute worker, not on the hub."""
import math
import re

EMOTIONS = ('neutral', 'joy', 'curious', 'skeptical', 'empathetic', 'surprised')
PHASES = ('neutral', 'listening', 'processing', 'speaking')
TAG = re.compile(r'^\s*<emotion=([a-z]+)>\s*', re.I)


def spoken_expression(reply):
    match = TAG.match(reply)
    if not match:
        return reply, 'neutral'
    emotion = match.group(1).lower()
    return reply[match.end():].strip(), emotion if emotion in EMOTIONS else 'neutral'


def plan(settings, phase, emotion='neutral'):
    if phase not in PHASES or emotion not in EMOTIONS:
        raise ValueError('Unknown expression phase or emotion')
    if not settings.get('enabled', False):
        return {'ok': True, 'steps': []}
    name = {'neutral': 'neutral', 'listening': 'listening', 'processing': 'thinking'}.get(phase, emotion)
    pose = settings['poses'][name]
    def step(nod=0, antenna_offset=0):
        head = {axis: math.radians(pose[axis] + (nod if axis == 'pitch' else 0))
                for axis in ('roll', 'pitch', 'yaw')}
        head.update(x=0.0, y=0.0, z=0.0)
        return {'head_pose': head,
                'antennas': [math.radians(a + antenna_offset) for a in pose['antennas']],
                'duration': settings['duration_seconds'], 'interpolation': 'minjerk'}
    steps = ([step(settings['speech_nod_degrees'], settings['speech_antenna_degrees']), step()]
             if phase == 'speaking' else [step()])
    return {'ok': True, 'phase': phase, 'emotion': emotion, 'steps': steps}
