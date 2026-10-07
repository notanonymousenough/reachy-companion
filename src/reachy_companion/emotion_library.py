"""Worker-side sampling of adapted, bundled Pollen Robotics emotion curves."""
import json
import math
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def catalog(name):
    if name != 'pollen-emotions-v1':
        raise ValueError('Unknown bundled emotion library')
    return json.loads(files('reachy_companion').joinpath('assets', name+'.json').read_text())['clips']


def sample(settings, name, seconds, variant=0):
    library = settings.get('library', {})
    if not library.get('enabled', False):
        return None
    names = library.get('emotions', {}).get(name, library.get('phases', {}).get(name, []))
    if not names:
        return None
    clip_name = names[variant % len(names)]
    clip = catalog(library['name'])[clip_name]
    duration = max(.5, clip['duration'])
    frames = clip['frames']
    position = (max(0, seconds) % duration) / duration * (len(frames)-1)
    index = min(len(frames)-2, int(position))
    weight = position-index
    values = [a+(b-a)*weight for a,b in zip(frames[index],frames[index+1])]
    return {'roll': values[0], 'pitch': values[1], 'yaw': values[2], 'antennas': values[3:], 'clip':clip_name}


def blend(settings, base, name, seconds, variant=0):
    motion = sample(settings, name, seconds, variant)
    if motion is None:
        return dict(base, antennas=list(base['antennas']))
    strength = settings['library']['strength']
    pose = {axis:base[axis]*(1-strength)+motion[axis]*strength for axis in ('roll','pitch','yaw')}
    pose['antennas'] = [a*(1-strength)+b*strength for a,b in zip(base['antennas'],motion['antennas'])]
    return pose


def step(settings, pose):
    head={axis:math.radians(max(-settings['max_head_degrees'],min(settings['max_head_degrees'],pose[axis]))) for axis in ('roll','pitch','yaw')}
    head.update(x=0.,y=0.,z=0.)
    return {'head_pose':head,'antennas':[math.radians(max(-settings['max_antenna_degrees'],min(settings['max_antenna_degrees'],a))) for a in pose['antennas']],
            'duration':settings['duration_seconds'],'interpolation':'minjerk'}
