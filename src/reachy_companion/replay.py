"""In-memory PCM replay: continue the exact original reply, not a new LLM answer."""
import base64
import json
from types import SimpleNamespace


class ReplayResponse:
    headers = SimpleNamespace(get_content_type=lambda: 'application/x-ndjson')

    def __init__(self, saved, settings):
        self.events = iter(self._events(saved, settings))

    def _events(self, saved, settings):
        yield {'type': 'reply', **saved['result']}
        cursor = saved['cursor']
        offset = cursor / (settings['sample_rate'] * 2)
        cues = []
        earlier = None
        for cue in saved['cues']:
            if cue['at'] <= offset:
                earlier = cue
            else:
                cues.append({**cue, 'at': cue['at']-offset})
        if earlier:
            cues.insert(0, {**earlier, 'at': 0})
        if cues:
            yield {'type': 'motion', 'cues': cues}
        pcm = saved['pcm']
        for start in range(cursor, len(pcm), settings['pcm_chunk_bytes']):
            yield {'type': 'audio', 'sample_rate': settings['sample_rate'], 'format': 'S16_LE',
                   'channels': 1, 'pcm_base64': base64.b64encode(pcm[start:start+settings['pcm_chunk_bytes']]).decode()}
        yield {'type': 'done', 'ok': True, **saved['result']}

    def readline(self, *args):
        event = next(self.events, None)
        return (json.dumps(event, ensure_ascii=False)+'\n').encode() if event else b''

    def __enter__(self): return self
    def __exit__(self, *args): pass
