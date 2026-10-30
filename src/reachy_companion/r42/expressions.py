"""Expression selection/planning on the compute worker, not on the hub."""
import math
import re

EMOTIONS = ('neutral', 'joy', 'curious', 'skeptical', 'empathetic', 'surprised', 'confident', 'amused', 'concerned', 'thoughtful', 'apologetic', 'excited', 'sad', 'grateful', 'proud', 'confused', 'relieved', 'shy', 'playful', 'frustrated', 'disappointed', 'calm', 'tired', 'disgusted', 'impatient', 'loving', 'uncertain', 'embarrassed')
PHASES = ('neutral', 'listening', 'processing', 'speaking', 'reacting')
TAG = re.compile(r'^\s*<emotion=([a-z]+)>\s*', re.I)


CONTROL = re.compile(r'</?(emotion|gesture)(?:=([a-z_]+))?>', re.I)


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


def plan(settings, phase, emotion='neutral', variant=0):
    if phase not in PHASES or emotion not in EMOTIONS:
        raise ValueError('Unknown expression phase or emotion')
    if not isinstance(variant, int) or isinstance(variant, bool) or not 0 <= variant <= 10000:
        raise ValueError('Invalid expression variant')
    if not settings.get('enabled', False):
        return {'ok': True, 'steps': []}
    from .emotion_library import blend, step
    name = {'neutral': 'neutral', 'listening': 'listening', 'processing': 'thinking'}.get(phase, emotion)
    base = settings['poses'][name]
    count = 3 if phase == 'processing' else 2 if phase == 'speaking' else 1
    count = min(count, settings['max_steps'])
    steps = []
    library_name = phase if phase in ('listening', 'processing') else emotion
    for i in range(count):
        pose = dict(base, antennas=list(base['antennas'])) if phase == 'neutral' else blend(settings, base, library_name, (i+1)*.75+variant*.45, variant)
        if phase == 'speaking' and i == 0:
            pose['pitch'] += settings['speech_nod_degrees']
        steps.append(step(settings, pose))
    return {'ok': True, 'phase': phase, 'emotion': emotion, 'steps': steps}
