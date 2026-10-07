"""Compute-side phoneme timing and bounded expressive speech cues."""
import math
from .expressions import EMOTIONS

GESTURES = ('auto', 'nod', 'shake', 'tilt', 'perk', 'settle', 'shrug', 'laugh', 'ponder', 'celebrate', 'comfort', 'bow', 'sweep', 'wiggle')


def pose_step(settings, emotion, gesture='auto', beat=0):
    if emotion not in EMOTIONS or gesture not in GESTURES:
        raise ValueError('Unknown expressive action')
    from .emotion_library import blend
    base = settings['poses'][emotion]
    pose = blend(settings, base, emotion, beat * settings['speech_sync']['min_cue_interval_seconds'], beat // 12) if gesture != 'settle' else dict(base)
    ears = list(pose['antennas'])
    amplitude = settings['speech_sync']['amplitude_degrees']
    sign = 1 if beat % 2 else -1
    if gesture == 'auto':
        pose['pitch'] += sign * amplitude * .5
        ears = [ears[0]-sign*amplitude*.5, ears[1]+sign*amplitude*.5]
    elif gesture in ('nod', 'bow', 'comfort'):
        pose['pitch'] += sign * amplitude
    elif gesture == 'shake':
        pose['yaw'] += sign * amplitude
    elif gesture == 'tilt':
        pose['roll'] += sign * amplitude
    elif gesture in ('shrug', 'wiggle'):
        pose['roll'] += sign * amplitude
        ears = [ears[0]+sign*amplitude, ears[1]+sign*amplitude]
    elif gesture in ('ponder', 'sweep'):
        pose['yaw'] += sign * amplitude
        pose['roll'] += amplitude*.5
    elif gesture in ('laugh', 'celebrate'):
        pose['pitch'] += sign*amplitude
        pose['roll'] += sign*amplitude*.75
        ears = [ears[0]-sign*amplitude*2, ears[1]+sign*amplitude*2]
    elif gesture == 'perk':
        ears = [ears[0] - sign * amplitude * 2, ears[1] + sign * amplitude * 2]
    head = {axis: math.radians(max(-settings['max_head_degrees'], min(settings['max_head_degrees'], pose[axis])))
            for axis in ('roll', 'pitch', 'yaw')}
    head.update(x=0.0, y=0.0, z=0.0)
    return {'head_pose': head,
            'antennas': [math.radians(max(-settings['max_antenna_degrees'], min(settings['max_antenna_degrees'], a))) for a in ears],
            'duration': settings['duration_seconds'], 'interpolation': 'minjerk'}


def cues(settings, chunk, segment, offset_seconds, rate, pcm_bytes, beat_offset=0):
    sync = settings.get('speech_sync', {})
    if not settings.get('enabled') or not sync.get('enabled'):
        return []
    duration = pcm_bytes / (rate * 2)
    alignments = getattr(chunk, 'phoneme_alignments', None)
    starts = [(0.0, '')]
    if alignments:
        position = 0
        word_start = True
        for alignment in alignments:
            symbol = alignment.phoneme
            seconds = position / chunk.sample_rate
            if word_start and symbol not in ('^', '$', '_', ' '):
                starts.append((seconds, symbol))
                word_start = False
            if symbol.isspace():
                word_start = True
            position += alignment.num_samples
    else:
        # Explicit fallback when a Piper model cannot provide alignment.
        interval = sync['min_cue_interval_seconds']
        starts += [(i * interval, '') for i in range(1, math.ceil(duration / interval))]
    output, previous = [], -math.inf
    for at, phoneme in starts:
        if at >= duration or at - previous < sync['min_cue_interval_seconds']:
            continue
        output.append({'at': round(offset_seconds + at, 4), 'emotion': segment['emotion'],
                       'gesture': segment['gesture'], 'phoneme': phoneme,
                       'alignment': 'piper' if alignments else 'estimated',
                       'steps': [pose_step(settings, segment['emotion'], segment['gesture'], beat_offset+len(output))]})
        previous = at
        if len(output) >= sync['max_cues']:
            break
    return output
