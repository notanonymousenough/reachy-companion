"""Finite PC trusted-owner fixture CLI; no audio/model/service/HTTP write endpoint."""
import argparse
import json
import os
from pathlib import Path
from reachy_companion.autonomous.voice_memory_fixture import prepare,operate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','confirm','correct','readback','forget','cleanup'))
    parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-disposable-voice-fixture',action='store_true')
    parser.add_argument('--operator-confirmation',action='store_true')
    parser.add_argument('--expected-store-id');parser.add_argument('--expected-version',type=int)
    for name in ('hub-receipt','device-receipt'):parser.add_argument('--'+name,type=Path)
    for name in ('controller','session-boot','source-boot'):parser.add_argument('--'+name)
    args=parser.parse_args()
    if not args.allow_disposable_voice_fixture:raise ValueError('Explicit disposable fixture opt-in required')
    directory=args.directory.resolve()
    if args.output.resolve()==directory or directory in args.output.resolve().parents:
        raise ValueError('Receipt must remain outside disposable fixture directory')
    if args.action=='prepare':
        if args.hub_receipt is None or args.device_receipt is None or any(not x for x in (args.controller,args.session_boot,args.source_boot)):
            raise ValueError('Explicit finished receipt binding required')
    elif not args.expected_store_id or args.expected_version is None:
        raise ValueError('Explicit expected store UUID and item version required')
    # Reserve the receipt before writes; output failure cannot initiate promotion.
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    report=dict(mode='trusted_runner_voice_receipts_disposable_owner_memory',action=args.action,accepted=False,
        model_inference=False,physical_commands=0,raw_audio_retained=False,transcripts_retained=False,
        input_assurance='trusted_runner_files_not_signed_hardware_attestation',live_voice_verified=False,
        speaker_identity_confirmed=False)
    with os.fdopen(fd,'w') as output:
        try:
            if args.action=='prepare':
                result=prepare(args.directory,args.hub_receipt,args.device_receipt,
                    dict(controller=args.controller,session_boot=args.session_boot,source_boot=args.source_boot))
            else:
                result=operate(args.action,args.directory,args.expected_store_id,args.expected_version,args.operator_confirmation)
            report.update(result,accepted=True)
        except Exception as exc:report['error_kind']=type(exc).__name__
        finally:
            json.dump(report,output,ensure_ascii=False,allow_nan=False,indent=2);output.flush();os.fsync(output.fileno())
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
