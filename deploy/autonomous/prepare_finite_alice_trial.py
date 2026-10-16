"""Build one opt-in Alice arithmetic trial; no device actions."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
AFTER='5174b92b44b3bb51de10e24dadd080118b05de974db0b4804fcdf0ac59ca7fb1'
PATCH='21837055101654271fce385bc62a657aa735e2f08b85939d1946aaf1e2b5783c'
HELPER='f3ce4da5bdf35dcef53a2ac37f60a3ebdb31250d5c29cd1fc9750ad4db89e894'


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'deploy/autonomous'/file)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def candidate():
    bound=module('finite_bound_base','prepare_bound_audio_only.py')
    _,before=bound.candidate()
    patch=(ROOT/'deploy/patches/reachy-agent-bound-audio-finite-alice.patch').read_bytes()
    helper=(ROOT/'src/reachy_companion/finite_alice_trial.py').read_bytes()
    digest=lambda raw:hashlib.sha256(raw).hexdigest()
    if digest(before)!=bound.AFTER or digest(patch)!=PATCH or digest(helper)!=HELPER:
        raise ValueError('Exact finite Alice input required')
    after=module('finite_alice_patch','prepare_content_stream.py').apply_exact(before.decode(),patch.decode()).encode()
    if digest(after)!=AFTER:raise ValueError('Exact finite Alice output required')
    compile(after,'finite-alice-agent.py','exec');compile(helper,'finite_alice_trial.py','exec')
    return before,after,helper


def client_candidate():
    builder=module('finite_audio_client','prepare_audio_only_demo.py')
    raw=builder.candidate((ROOT/'src/reachy_companion/client.py').read_bytes())
    text=raw.decode()
    old='listen=vision_text is None and not prime_paused'
    if text.count(old)!=1:raise ValueError('Exact paused admission required')
    text=text.replace(old,'listen=False')
    text=text.replace('Live demo starting. Ctrl-C or microphone OFF stops.',
        'ALICE_TRIAL_MIC_GRANTED_CAPTURE_PAUSED; awaiting bound cue and guarded resume.')
    compile(text,'finite-alice-client.py','exec')
    return text.encode()


def build(destination):
    _,after,helper=candidate();client=client_candidate();destination.mkdir(mode=0o700)
    for name,raw in (('agent.py',after),('finite_alice_trial.py',helper),('client.py',client)):
        with (destination/name).open('xb') as file:file.write(raw)
    manifest=dict(kind='one-finite-alice-arithmetic-proposal',original_agent='cf50c54680d8e30fb97090e80d0e687a9dad903159f464d2211414aefcaca069',
        agent=AFTER,helper=HELPER,patch=PATCH,client=hashlib.sha256(client).hexdigest(),proposal=True,devices_modified=False,hardware_accepted=False,
        opt_in='bound /say operator_binding.audio_only=true + alice_trial kind/nonce',
        response_gate='normal capture same-buffer receipt/source-generation TTL2; exact4/четыре before LLM; once',
        response_window_seconds=20,requires_default_capture_pump_off=True,
        requires_pc_speech_address_prefix_verified=True,requires_owner_producer_playback_quiet_before_resume=True,
        speaker_identity='unknown',spoken_vision_motor_false_supported=False,
        restore_original_agent_after_trial=True)
    with (destination/'manifest.json').open('x') as file:file.write(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    print(json.dumps(build(parser.parse_args().destination),indent=2))
