"""Expression selection/planning on the compute worker, not on the hub."""
import math
import re

EMOTIONS = ('neutral', 'joy', 'curious', 'skeptical', 'empathetic', 'surprised', 'confident', 'amused', 'concerned', 'thoughtful', 'apologetic', 'excited')
PHASES = ('neutral', 'listening', 'processing', 'speaking')
TAG = re.compile(r'^\s*<emotion=([a-z]+)>\s*', re.I)


CONTROL = re.compile(r'</?(emotion|gesture)(?:=([a-z]+))?>', re.I)


def spoken_segments(reply):
    from .speech_motion import GESTURES
    emotion, gesture = 'neutral', 'auto'
    segments = []
    previous = 0
    for tag in CONTROL.finditer(reply):
        text = reply[previous:tag.start()].strip()
        if text:
            segments.append({'text': text, 'emotion': emotion, 'gesture': gesture})
        name, value = tag.group(1).lower(), (tag.group(2) or '').lower()
        if not tag.group().startswith('</'):
            if name == 'emotion': emotion = value if value in EMOTIONS else 'neutral'
            elif name == 'gesture': gesture = value if value in GESTURES else 'auto'
        previous = tag.end()
    text = reply[previous:].strip()
    if text:
        segments.append({'text': text, 'emotion': emotion, 'gesture': gesture})
    if len(segments) > 8:
        segments[7]['text'] = ' '.join(s['text'] for s in segments[7:])
        segments = segments[:8]
    return segments


def spoken_expression(reply):
    segments = spoken_segments(reply)
    return (' '.join(segment['text'] for segment in segments),
            segments[0]['emotion'] if segments else 'neutral')


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
