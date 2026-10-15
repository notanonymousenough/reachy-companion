import logging
from logging.handlers import RotatingFileHandler
from contextlib import contextmanager
import math
import re
import threading
import time


LATENCY_STAGES = {'worker': ('stt', 'classification', 'answer_call', 'tts', 'audio_convert'),
                  'agent': ('worker_request', 'aplay_wait', 'aplay_communicate', 'aplay_cancel')}
LATENCY_MARKS = {'worker': ('first_raw_pcm', 'first_output_pcm', 'wav_ready'),
                 'agent': ('first_write', 'stream_done', 'cancel_observed')}


class TurnLatency:
    """One fixed-size, content-free record. All times belong to one host clock."""
    def __init__(self, request_id, role, source='live'):
        if (type(request_id) is not str or re.fullmatch('[0-9a-f]{32}', request_id) is None
                or role not in LATENCY_STAGES or source not in ('live', 'replay')):
            raise ValueError('Invalid latency identity')
        self.request_id = request_id;self.role = role;self.source = source
        self.started = time.monotonic();self.lock = threading.Lock()
        self.stages = {name:dict(start_seconds=None, end_seconds=None, active_seconds=0.0, calls=0)
                       for name in LATENCY_STAGES[role]}
        self.marks = dict.fromkeys(LATENCY_MARKS[role])
        self.pcm_frames = self.written_frames = None

    def offset(self):return round(min(86400.0, max(0.0, time.monotonic() - self.started)), 6)

    def mark(self, name):
        with self.lock:
            if name not in self.marks:raise ValueError('Unknown latency mark')
            if self.marks[name] is None:self.marks[name] = self.offset()

    @contextmanager
    def stage(self, name):
        start = self.offset()
        try:yield
        finally:
            end = self.offset()
            with self.lock:
                row = self.stages[name]
                if row['start_seconds'] is None:row['start_seconds'] = start
                row['end_seconds'] = end
                row['active_seconds'] = round(min(86400.0, row['active_seconds'] + max(0.0, end-start)), 6)
                row['calls'] = min(65535, row['calls'] + 1)

    def pcm(self, byte_count, written=False):
        with self.lock:
            name = 'written_frames' if written else 'pcm_frames'
            setattr(self, name, min(10**9, (getattr(self, name) or 0) + byte_count//2))

    def report(self, outcome):
        if outcome not in ('complete', 'cancelled', 'interrupted', 'error'):raise ValueError('Invalid latency outcome')
        with self.lock:
            return dict(version=1, request_id=self.request_id, role=self.role, source=self.source, outcome=outcome,
                elapsed_seconds=self.offset(), stages={key:dict(value) for key,value in self.stages.items()}, marks=dict(self.marks),
                main_first_token_seconds=None, pcm_frames=self.pcm_frames, written_frames=self.written_frames,
                pcm_seconds=None if self.pcm_frames is None else round(self.pcm_frames/16000, 6))


def measured(latency, stage, callback, *args, **kwargs):
    if latency is None:return callback(*args, **kwargs)
    with latency.stage(stage):return callback(*args, **kwargs)


def measured_chunks(latency, chunks):
    if latency is None:
        yield from chunks
        return
    iterator = iter(chunks)
    try:
        while True:
            try:chunk = measured(latency, 'tts', next, iterator)
            except StopIteration:return
            yield chunk
    finally:
        close = getattr(iterator, 'close', None)
        if close is not None:close()


def worker_latency(payload):
    requested = payload.get('latency_diagnostics', False)
    if type(requested) is not bool:raise ValueError('Boolean latency diagnostics required')
    if not requested:
        if 'latency_request_id' in payload:raise ValueError('Latency identity requires diagnostics')
        return None
    return TurnLatency(payload.get('latency_request_id'), 'worker')


def checked_latency(value, request_id):
    """Only this schema can enter Agent status; reject arbitrary worker content."""
    try:
        template = TurnLatency(request_id, 'worker').report('complete')
        if type(value) is not dict or set(value) != set(template):return None
        if (type(value['version']) is not int or value['version'] != 1 or value['request_id'] != request_id
                or value['role'] != 'worker' or value['source'] != 'live'
                or value['outcome'] not in ('complete', 'cancelled', 'interrupted', 'error')
                or value['main_first_token_seconds'] is not None):return None
        def seconds(number, optional=False):
            return (optional and number is None) or (type(number) in (int,float) and 0 <= number <= 86400 and math.isfinite(number))
        if not seconds(value['elapsed_seconds']):return None
        if type(value['marks']) is not dict or set(value['marks']) != set(template['marks']):return None
        if any(not seconds(number, True) for number in value['marks'].values()):return None
        if any(number is not None and number>value['elapsed_seconds'] for number in value['marks'].values()):return None
        if type(value['stages']) is not dict or set(value['stages']) != set(template['stages']):return None
        for row in value['stages'].values():
            if type(row) is not dict or set(row) != {'start_seconds','end_seconds','active_seconds','calls'}:return None
            if not seconds(row['start_seconds'], True) or not seconds(row['end_seconds'], True) or not seconds(row['active_seconds']):return None
            if type(row['calls']) is not int or not 0 <= row['calls'] <= 65535:return None
            if row['calls']==0:
                if row['start_seconds'] is not None or row['end_seconds'] is not None or row['active_seconds']!=0:return None
            elif (row['start_seconds'] is None or row['end_seconds'] is None
                    or not row['start_seconds']<=row['end_seconds']<=value['elapsed_seconds']
                    or row['active_seconds']>row['end_seconds']-row['start_seconds']+1e-6*(row['calls']+1)):
                return None
        for name in ('pcm_frames', 'written_frames'):
            if value[name] is not None and (type(value[name]) is not int or not 0 <= value[name] <= 10**9):return None
        if not seconds(value['pcm_seconds'], True):return None
        if value['written_frames'] is not None:return None
        if value['pcm_frames'] is None:
            if value['pcm_seconds'] is not None:return None
        elif value['pcm_seconds'] is None or abs(value['pcm_seconds']-value['pcm_frames']/16000)>1e-6:return None
        # A JSON roundtrip yields an owned, bounded primitive-only copy.
        import json
        return json.loads(json.dumps(value))
    except (ValueError, TypeError, KeyError):return None


def configure(config, name):
    data = config.path(config['paths']['data_dir'])
    data.mkdir(parents=True, exist_ok=True)
    settings = config['logging']
    logging.basicConfig(level=settings['level'],
                        format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(), RotatingFileHandler(
                            data / (name + '.log'), maxBytes=settings['max_bytes'],
                            backupCount=settings['backup_count'])])
