"""Build an opt-in bound-speech proposal against exact installed Agent cf50."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BEFORE='cf50c54680d8e30fb97090e80d0e687a9dad903159f464d2211414aefcaca069'
AFTER='2abad7df2fa327227cd0b1ff3fbd6956eeabcc2c1116e9d81389c9c760266fed'
PATCH='3af4c96f6781748f766ac6d6eb4b169172444bfcb46b666dcd385620720e1aec'


def module(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'deploy/autonomous'/filename)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def candidate():
    _,data=module('audio_bound_base','prepare_capture_pump.py').candidate()
    raw=data['agent.py']
    patch=(ROOT/'deploy/patches/reachy-agent-cf50-bound-audio-only.patch').read_bytes()
    digest=lambda value:hashlib.sha256(value).hexdigest()
    if digest(raw)!=BEFORE or digest(patch)!=PATCH:raise ValueError('Exact audio-only preimage required')
    output=module('audio_bound_patch','prepare_content_stream.py').apply_exact(raw.decode(),patch.decode()).encode()
    if digest(output)!=AFTER:raise ValueError('Exact audio-only output required')
    compile(output,'agent-bound-audio-only.py','exec')
    return raw,output


def build(destination):
    _,output=candidate()
    destination.mkdir(mode=0o700)
    with (destination/'agent.py').open('xb') as file:file.write(output)
    manifest=dict(kind='bound-audio-only-speech-proposal',before=BEFORE,after=AFTER,patch=PATCH,
        opt_in='operator_binding.audio_only=true',default='legacy literal motor True',
        policy_mode='explicit audio_only requires literal motor False; same paired owner/epochs',
        proposal=True,devices_modified=False,hardware_accepted=False,
        alice_input_gate_implemented=False,spoken_vision_motor_false_supported=False,
        expression_guards_modified=False,source_installation_required=True)
    with (destination/'manifest.json').open('x') as file:file.write(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',type=Path)
    print(json.dumps(build(parser.parse_args().destination),indent=2))
