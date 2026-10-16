"""One exact external-response window; no speaker identity or acoustic claim."""
import math
import re
import unicodedata

CUE='Алиса, сколько будет два плюс два?'


class CapturedPCM(bytes):
    """Receipt travels with this exact normal-capture buffer, never a cache."""
    def __new__(cls, pcm, receipt):
        result=super().__new__(cls,pcm)
        result.receipt=dict(receipt)
        return result


def validate(trial, binding, text):
    if (type(trial) is not dict or set(trial)!={'nonce','kind'} or trial['kind']!='arithmetic_four'
            or type(trial['nonce']) is not str or not re.fullmatch('[0-9a-f]{32}',trial['nonce'])
            or binding.get('audio_only') is not True or text!=CUE):
        raise ValueError('Exact finite Alice cue required')


class ResponseGate:
    def __init__(self, trial, binding, now):
        validate(trial,binding,CUE)
        if type(now) not in (int,float) or not math.isfinite(now):raise ValueError('Finite gate time required')
        self.binding={k:binding[k] for k in ('agent_boot_id','microphone_epoch','policy_epoch','owner_id')}
        self.nonce=trial['nonce']
        self.deadline=min(now+20,binding['expires_at_monotonic'])
        if self.deadline-now<5:raise ValueError('Response window unavailable')
        self.armed_at=now
        self.accepted_at=None
        self.rejected=0
        self.consumed=False

    def accept(self, text, value, now, receipt=None, source_generation=None):
        # No transcript is stored. A mismatch never restores general model access.
        good=False
        if type(now) in (int,float) and math.isfinite(now) and self.armed_at<=now<self.deadline and not self.consumed:
            policy=value['motion_policy'];b=self.binding
            current=(value['agent_boot_id']==b['agent_boot_id']
                and value['microphone_epoch']==b['microphone_epoch']
                and policy['epoch']==b['policy_epoch']
                and value['microphone_owner_id']==b['owner_id']
                and value['motion_policy_owner_id']==b['owner_id']
                and value['microphone_enabled'] is True and value['listening'] is True
                and value['capture_active'] is False and value['phase']=='processing'
                and value['microphone_state_error'] is None
                and policy['motor_enabled'] is False and policy['quiet'] is False and policy['privacy_all'] is False)
            normalized=' '.join(re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',text).casefold())) if type(text) is str else ''
            fresh=(type(receipt) is dict and set(receipt)=={'started','received','generation'}
                and type(receipt['generation']) is int and receipt['generation']>0
                and receipt['generation']==source_generation
                and all(type(receipt[k]) in (int,float) and math.isfinite(receipt[k]) for k in ('started','received'))
                and self.armed_at<=receipt['started']<=receipt['received']<=now
                and now-receipt['received']<=2)
            good=current and fresh and normalized in ('4','четыре')
        if good:self.consumed=True;self.accepted_at=now
        else:self.rejected=min(self.rejected+1,1000000)
        return good

    def receipt(self):
        return dict(armed_at_monotonic=self.armed_at,deadline_monotonic=self.deadline,
            accepted_at_monotonic=self.accepted_at,consumed=self.consumed,rejected=self.rejected,
            speaker_identity='unknown',acoustic_onset_verified=False,transcript_retained=False)
