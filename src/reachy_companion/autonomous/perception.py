"""Bounded PC pixel measurements. No object labels or scene inference from metrics."""
import hashlib
import math


def pixel_metrics(payload, expected_sha256):
    if not isinstance(payload, bytes) or len(payload)>1048576:
        raise ValueError('Frame transport exceeds bound')
    digest=hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        raise ValueError('Frame provenance digest mismatch')
    header=payload.split(b'\n',3)
    if len(header)!=4 or header[0]!=b'P6' or header[2]!=b'255' or len(header[1])>32:
        raise ValueError('Unsupported frame transport')
    dimensions=header[1].split(b' ')
    if len(dimensions)!=2 or not all(x.isdigit() for x in dimensions):
        raise ValueError('Invalid frame dimensions')
    width,height=map(int,dimensions)
    if not 1<=width<=640 or not 1<=height<=480 or len(header[3])!=width*height*3:
        raise ValueError('Invalid frame size')
    channels=[0,0,0];total=squares=dark=clipped=0;count=width*height
    for offset in range(0,len(header[3]),3):
        red,green,blue=header[3][offset:offset+3]
        channels[0]+=red;channels[1]+=green;channels[2]+=blue
        luminance=(54*red+183*green+19*blue)/256
        total+=luminance;squares+=luminance*luminance
        dark+=luminance<16;clipped+=luminance>239
    mean=total/count
    return dict(frame_sha256=digest,width=width,height=height,mean_rgb=[round(x/count,3) for x in channels],
                mean_luminance=round(mean,3),luminance_std=round(math.sqrt(max(0,squares/count-mean*mean)),3),
                dark_fraction=round(dark/count,6),bright_fraction=round(clipped/count,6),
                semantic_scene_inferred=False)


def shadow_event(metrics):
    # Receipt time is NOT capture time. Until the producer provides verified
    # capture-clock mapping, these metrics cannot masquerade as fresh evidence.
    return dict(type='sensor',id='camera.pixel_quality',availability='unknown',summary='',ttl_ms=2000)
