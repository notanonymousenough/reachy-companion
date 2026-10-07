"""Bounded command validation. No trajectories or inference on the router."""
import math


def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('Motion values must be finite numbers')
    return value


def validate_steps(steps, settings):
    if not isinstance(steps, list) or not 1 <= len(steps) <= settings['max_steps']:
        raise ValueError('Invalid expression step count')
    total = 0
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'head_pose', 'antennas', 'duration', 'interpolation'}:
            raise ValueError('Expression can only control head orientation and antennas')
        duration = number(step['duration'])
        if not .5 <= duration <= 1.5 or step['interpolation'] != 'minjerk':
            raise ValueError('Expression must use a slow smooth movement')
        total += duration
        head = step['head_pose']
        if not isinstance(head, dict) or set(head) != {'x', 'y', 'z', 'roll', 'pitch', 'yaw'}:
            raise ValueError('Invalid expression head pose')
        if any(number(head[axis]) != 0 for axis in ('x', 'y', 'z')):
            raise ValueError('Expression translations are disabled')
        if any(abs(number(head[axis])) > math.radians(settings['max_head_degrees']) for axis in ('roll', 'pitch', 'yaw')):
            raise ValueError('Expression head angle exceeds limits')
        antennas = step['antennas']
        if not isinstance(antennas, list) or len(antennas) != 2 or any(abs(number(a)) > math.radians(settings['max_antenna_degrees']) for a in antennas):
            raise ValueError('Expression antenna angle exceeds limits')
    if total > settings['max_total_seconds']:
        raise ValueError('Expression is too long')
    return steps
