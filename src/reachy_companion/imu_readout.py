"""One bounded temperature readout from factory IMU data; no I/O or cache.

This describes a reported measurement, not ambient temperature or a physical
freshness guarantee. The caller must retain its existing owner/epoch/privacy
checks and pass expires_at_monotonic to the protected speaker admission.
"""
import math

TTL_SECONDS=20


def temperature_readout(sample, *, received_at, now):
    def clock(value):
        return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1e15
    if not clock(received_at) or not clock(now) or now<received_at:
        raise ValueError('Local monotonic IMU receipt required')
    expires=received_at+TTL_SECONDS
    result=dict(kind='factory-imu-temperature-readout',state='unknown',reason='unavailable',
        source='factory:/api/state/imu',units='degrees_celsius',temperature_celsius=None,
        received_at_monotonic=received_at,expires_at_monotonic=expires,
        physical_sample_time_verified=False,cache_freshness_verified=False,
        ambient_temperature=False,grants_control=False,speech=None)
    if now>=expires:
        result['reason']='expired'
        return result
    if type(sample) is not dict:
        return result
    value=sample.get('temperature')
    # This is a formatting bound, not a BMI088 operating-range assertion.
    if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>1000:
        result['reason']='invalid_temperature'
        return result
    value=round(value,1)
    label=format(value,'.1f').replace('.',',')
    result.update(state='reported',reason=None,temperature_celsius=value,
        speech='Алиса, последнее доступное измерение температуры чипа моего датчика — '
            +label+' градусов Цельсия. Что измеряет такой датчик?')
    return result
