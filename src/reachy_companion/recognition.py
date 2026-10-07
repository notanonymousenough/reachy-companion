"""Speech recognition runs exclusively on the compute PC."""
import json
import threading


class Recognizer:
    def __init__(self, config):
        self.config = config
        self.settings = config['conversation'].get('recognition', {'backend': 'vosk'})
        self.lock = threading.Lock()
        if self.settings['backend'] == 'faster_whisper':
            from faster_whisper import WhisperModel
            self.model = WhisperModel(str(config.path(self.settings['path'])),
                                      device=self.settings['device'], compute_type=self.settings['compute_type'],
                                      cpu_threads=self.settings['cpu_threads'], local_files_only=True)
            # Compile CUDA kernels before health becomes ready, not on the first user turn.
            import numpy as np
            segments, _ = self.model.transcribe(np.zeros(16000, dtype=np.float32),
                                                language=self.settings['language'], beam_size=1,
                                                vad_filter=False, condition_on_previous_text=False, temperature=0)
            list(segments)
        else:
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            self.model = Model(str(config.path(config['models']['stt']['path'])))

    def transcribe(self, pcm):
        audio = self.config['audio']
        if not pcm or len(pcm) % 2 or len(pcm) > audio['max_input_seconds'] * audio['sample_rate'] * 2:
            raise ValueError('Invalid mono 16 kHz PCM input')
        with self.lock:
            if self.settings['backend'] == 'faster_whisper':
                import numpy as np
                samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
                s = self.settings
                segments, _ = self.model.transcribe(samples, language=s['language'], beam_size=s['beam_size'],
                    initial_prompt=s['initial_prompt'], vad_filter=s['vad_filter'],
                    condition_on_previous_text=False, temperature=0,
                    no_speech_threshold=s['no_speech_threshold'], log_prob_threshold=s['log_prob_threshold'])
                return ' '.join(seg.text.strip() for seg in segments
                                if seg.avg_logprob >= s['log_prob_threshold'] and seg.no_speech_prob < s['no_speech_threshold']).strip()
            from vosk import KaldiRecognizer
            recognizer = KaldiRecognizer(self.model, audio['sample_rate'])
            parts = []
            for offset in range(0, len(pcm), 8000):
                if recognizer.AcceptWaveform(pcm[offset:offset+8000]):
                    parts.append(json.loads(recognizer.Result()).get('text', ''))
            parts.append(json.loads(recognizer.FinalResult()).get('text', ''))
            return ' '.join(p for p in parts if p).strip()


def prepare(config):
    settings = config['conversation'].get('recognition', {})
    if settings.get('backend') != 'faster_whisper':
        return
    import hashlib
    target = config.path(settings['path'])
    weights = target / 'model.bin'
    if weights.exists() and all((target/name).exists() for name in ('config.json','tokenizer.json','vocabulary.json')):
        with weights.open('rb') as source:
            actual = hashlib.file_digest(source, 'sha256').hexdigest()
        if actual == settings['sha256']:
            return
    from huggingface_hub import snapshot_download
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=settings['repository'], revision=settings['revision'], local_dir=str(target),
                      allow_patterns=['model.bin', 'config.json', 'tokenizer.json', 'vocabulary.*', 'preprocessor_config.json'])

