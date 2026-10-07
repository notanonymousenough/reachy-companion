"""Small audio event model and beat estimation, executed on the compute PC."""
import base64
import threading

class SoundEvents:
    def __init__(self, config):
        self.config=config;self.settings=config['conversation']['sound_reactions'];self.lock=threading.Lock()
        self.session=None
        if self.settings['enabled']:
            import onnxruntime as ort
            options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
            self.session=ort.InferenceSession(str(config.path(self.settings['model_path'])),options,providers=['CPUExecutionProvider'])

    def classify(self, pcm):
        import numpy as np
        s=self.settings
        if not pcm or len(pcm)%2 or len(pcm)>int(s['window_seconds']*16000*2)+3200:raise ValueError('Invalid sound window')
        wave=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
        if self.session is None:return {'kind':'speech','speech':0.,'music':0.}
        with self.lock:scores=self.session.run(['output_0'],{'waveform':wave})[0].mean(axis=0)
        music=float(max(scores[132],scores[133:277].max()))
        speech=float(max(scores[0],scores[1:7].max()))
        top=int(scores.argmax())
        kind='music' if music>=s['music_threshold'] else 'speech' if speech>=s['speech_threshold'] else 'silence' if float(np.sqrt(np.mean(wave**2)))<.004 else 'sound'
        result={'kind':kind,'speech':round(speech,4),'music':round(music,4),'top_class':top}
        if kind=='music':
            # Rhythm from short-time energy onsets; octave ambiguity is normal.
            hop=160;wave=wave[:len(wave)//hop*hop].reshape(-1,hop)
            energy=np.sqrt(np.mean(wave*wave,axis=1));onsets=np.maximum(0,np.diff(energy,prepend=energy[0]));onsets-=onsets.mean()
            lo=round(6000/s['max_bpm']);hi=min(len(onsets)-1,round(6000/s['min_bpm']))
            correlations=[float(np.dot(onsets[:-lag],onsets[lag:])) for lag in range(lo,hi+1)]
            lag=lo+int(np.argmax(correlations)) if correlations and max(correlations)>1e-6 else 50
            period=lag*.01
            peaks=np.maximum(0,np.diff(energy,prepend=energy[0]));recent=min(len(peaks),round(period*100))
            elapsed=(recent-1-int(np.argmax(peaks[-recent:]))) *.01
            result.update(beat_seconds=round(period,3),next_beat_seconds=round((period-elapsed)%period,3))
            from .speech_motion import pose_step
            result['steps']=[pose_step(self.config['conversation']['expressions'],'playful','wiggle',i) for i in range(4)]
        return result

def prepare(config):
    settings=config['conversation'].get('sound_reactions',{})
    if settings.get('enabled'):
        from .deployment import fetch
        fetch(settings['model_url'],config.path(settings['model_path']),settings['sha256'])
