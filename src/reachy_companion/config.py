"""One configuration for operator, hub and robot; credentials stay outside JSON."""
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit


class Config:
    def __init__(self, filename=None, require_token=True):
        self.filename = Path(filename or os.environ.get('REACHY_COMPANION_CONFIG',
                                                       'config.local.json')).expanduser().resolve()
        self.root = self.filename.parent
        self.data = json.loads(self.filename.read_text())
        # Only known optional settings may be introduced by a newer profile.
        def fill(target, defaults):
            import copy
            for key, value in defaults.items():
                if key not in target:
                    target[key] = copy.deepcopy(value)
                elif isinstance(value, dict) and isinstance(target[key], dict):
                    fill(target[key], value)
        example_path = self.root / 'config.example.json'
        defaults = json.loads(example_path.read_text()) if example_path.exists() else {}
        for section, optional in [('tts', ('playback_eq',)),
                                  ('conversation', ('expressions', 'barge_in', 'recognition', 'interaction'))]:
            for key in optional:
                if key in defaults.get(section, {}):
                    fill(self.data[section], {key: defaults[section][key]})
        for section in ('power', 'container'):
            if section in defaults:
                fill(self.data, {section: defaults[section]})
        profile = self.data.get('runtime', {}).get('profile', '')
        if profile:
            profile_path = (self.root / profile).resolve()
            if not profile_path.is_relative_to(self.root):
                raise ValueError('Profile must be inside the repository')
            values = json.loads(profile_path.read_text())
            if not isinstance(values, dict) or set(values) - {'llm', 'tts', 'conversation'}:
                raise ValueError('Profile may only change llm, tts and conversation')
            def merge(target, patch):
                for key, value in patch.items():
                    if key not in target:
                        raise ValueError('Unknown profile field: ' + key)
                    if isinstance(value, dict):
                        merge(target[key], value)
                    else:
                        target[key] = value
            merge(self.data, values)
        self.validate()
        self.token = ''
        if require_token:
            self.token = os.environ.get('REACHY_COMPANION_TOKEN', '')
            if not self.token:
                self.token = self.path(self.data['paths']['token_file']).read_text().strip()
            if len(self.token) < 32:
                raise ValueError('Use a nonempty token of at least 32 characters')

    def __getitem__(self, key):
        return self.data[key]

    def path(self, value):
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.root / path

    def value(self, dotted):
        value = self.data
        for key in dotted.split('.'):
            value = value[key]
        return value

    def validate(self):
        if self.data['version'] != 1:
            raise ValueError('Unsupported configuration version')
        for key in ('hub_url', 'voice_url', 'agent_url', 'robot_url', 'llm_base_url', 'compute_url'):
            url = urlsplit(self.data['network'][key])
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
                raise ValueError('Invalid network URL: ' + key)
        for role in ('hub', 'voice', 'agent', 'worker'):
            server = self.data['servers'][role]
            if not isinstance(server['port'], int) or not 1 <= server['port'] <= 65535:
                raise ValueError('Invalid server port: ' + role)
        recognition = self.data['conversation'].get('recognition', {})
        if recognition:
            if recognition['backend'] not in ('vosk', 'faster_whisper') or recognition['device'] not in ('cuda', 'cpu'):
                raise ValueError('Invalid speech recognition backend or device')
            if not 1 <= recognition['beam_size'] <= 5 or not 1 <= recognition['cpu_threads'] <= 32:
                raise ValueError('Invalid speech recognition limits')
            if Path(recognition['path']).is_absolute() or not self.path(recognition['path']).resolve().is_relative_to(self.root):
                raise ValueError('Recognition model must stay inside the repository')
        interaction = self.data['conversation'].get('interaction', {})
        if interaction:
            if not 0 <= interaction['resume_after_empty_seconds'] <= 10:
                raise ValueError('Invalid empty interruption timeout')
            if interaction['classifier']['provider'] not in ('rules', 'lm_studio'):
                raise ValueError('Invalid action classifier provider')
            ack = interaction['acknowledgements']
            if not 0 <= ack['delay_seconds'] <= 5 or any(not isinstance(v, str) or len(v) > 100 for v in ack['phrases'].values()):
                raise ValueError('Invalid acknowledgement settings')
        power = self.data.get('power', {})
        if power and not 1 <= power['remind_after_minutes'] <= 1440:
            raise ValueError('Invalid charge reminder interval')
        mixer = self.data['audio'].get('playback_mixer', {})
        if mixer.get('enabled', False) and not 0 <= mixer['volume_percent'] <= 100:
            raise ValueError('Playback mixer volume must be between 0 and 100')
        if self.data['audio']['sample_rate'] != 16000 or self.data['audio']['vad_frame_ms'] != 20:
            raise ValueError('The current protocol uses mono S16_LE at 16000 Hz and 20 ms VAD frames')
        if self.data['audio']['chunk_ms'] % self.data['audio']['vad_frame_ms']:
            raise ValueError('chunk_ms must be a multiple of vad_frame_ms')
        if not 0 <= self.data['audio']['vad_mode'] <= 3:
            raise ValueError('vad_mode must be between 0 and 3')
        if not 0 <= self.data['tts']['synthesis']['volume'] <= 1:
            raise ValueError('TTS volume must be between 0 and 1')
        if not 0.5 <= self.data['tts']['synthesis']['length_scale'] <= 2:
            raise ValueError('TTS length_scale must be between 0.5 and 2')
        if not -1200 <= self.data['tts']['pitch_cents'] <= 1200:
            raise ValueError('TTS pitch must be between -1200 and 1200 cents')
        eq = self.data['tts'].get('playback_eq', {})
        if eq.get('enabled', False):
            if not 20 <= eq['highpass_hz'] <= 300:
                raise ValueError('Speaker highpass must be between 20 and 300 Hz')
            for key in ('bass_hz', 'presence_hz'):
                if not 20 <= eq[key] <= 7000:
                    raise ValueError('Invalid speaker EQ frequency')
            for key in ('bass_width_q', 'presence_width_q'):
                if not 0.3 <= eq[key] <= 3:
                    raise ValueError('Invalid speaker EQ width')
            for key in ('bass_db', 'presence_db', 'treble_db'):
                if not -12 <= eq[key] <= 12:
                    raise ValueError('Invalid speaker EQ gain')
            if not 0 <= eq['headroom_db'] <= 12:
                raise ValueError('Invalid speaker EQ headroom')
        barge = self.data['conversation'].get('barge_in', {})
        if not 0 <= barge.get('warmup_chunks', 9) <= 30:
            raise ValueError('Invalid barge-in warmup')
        if barge.get('enabled', False):
            if not 3 <= barge['min_voiced_chunks'] <= 10 or not 1 <= barge['threshold_multiplier'] <= 4:
                raise ValueError('Invalid speech interruption settings')
        expressions = self.data['conversation'].get('expressions', {})
        sync = expressions.get('speech_sync', {})
        if sync:
            if not .6 <= sync['min_cue_interval_seconds'] <= 3 or not 1 <= sync['max_cues'] <= 240 or not 0 <= sync['amplitude_degrees'] <= 3:
                raise ValueError('Invalid speech motion synchronization limits')
        if expressions.get('enabled', False):
            from .expressions import EMOTIONS, PHASES, plan
            if not 0 < expressions['max_head_degrees'] <= 15 or not 0 < expressions['max_antenna_degrees'] <= 35:
                raise ValueError('Expression angle limits are too large')
            if not .5 <= expressions['duration_seconds'] <= 1.5 or not .1 <= expressions['settle_seconds'] <= 2:
                raise ValueError('Invalid expression timing')
            if not 2 <= expressions['repeat_seconds'] <= 10 or not 1 <= expressions['max_steps'] <= 4 or not 1 <= expressions['max_total_seconds'] <= 4:
                raise ValueError('Invalid expression sequence limits')
            from .motion_limits import validate_steps
            for phase in PHASES:
                for emotion in EMOTIONS:
                    validate_steps(plan(expressions, phase, emotion)['steps'], expressions)
        for role in ('hub', 'robot', 'worker'):
            item = self.data['deployment'][role]
            if not Path(item['root']).is_absolute() or '\n' in item['root']:
                raise ValueError('Deployment root must be an absolute single-line path')
            for key in ('host', 'user'):
                if not item[key] or any(c.isspace() for c in item[key]) or item[key].startswith('-'):
                    raise ValueError('Invalid SSH ' + key)
        if self.data['voice']['mode'] not in ('local', 'remote'):
            raise ValueError('voice.mode must be local or remote')
        if self.data['brains']['provider'] not in ('lm_studio', 'openclaw', 'hermes'):
            raise ValueError('Unsupported brains.provider')
        if not 2 <= self.data['streaming']['pcm_chunk_bytes'] <= 65536 or self.data['streaming']['pcm_chunk_bytes'] % 2:
            raise ValueError('Invalid PCM stream chunk size')
        if self.data['streaming']['sample_rate'] != 16000:
            raise ValueError('Streaming protocol requires mono S16_LE at 16000 Hz')
        if not 1 <= self.data['streaming']['relay_chunk_bytes'] <= 65536:
            raise ValueError('Invalid relay chunk size')
        if self.data['llm']['mode'] != 'completion':
            raise ValueError('Only raw completion LLM mode is currently supported')
        if self.data['audio']['chunk_ms'] <= 0:
            raise ValueError('chunk_ms must be positive')
        if not self.data['llm']['history_messages'] > 0:
            raise ValueError('history_messages must be positive')


def initialize(root, example='config.example.json'):
    root = Path(root).resolve()
    target = root / 'config.local.json'
    if target.exists():
        raise FileExistsError('config.local.json already exists; it was not overwritten')
    data = json.loads((root / example).read_text())
    token = root / data['paths']['token_file']
    token.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not token.exists():
        fd = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            output.write(secrets.token_urlsafe(32) + '\n')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(data, output, ensure_ascii=False, indent=2)
        output.write('\n')
    return target
