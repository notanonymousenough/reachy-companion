"""Inspect the existing pinned model's image capability; no image/inference/load."""
import argparse
import json
from pathlib import Path
from compute_probe import main_identity
from reachy_companion.autonomous.config import load


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    model=load(args.config)['models']['main'];before=main_identity(model)
    import lmstudio
    from urllib.parse import urlsplit
    with lmstudio.Client(urlsplit(model['base_url']).netloc) as client:
        handles=[handle for handle in client.llm.list_loaded() if handle.get_info().identifier==model['id']]
        if len(handles)!=1:raise RuntimeError('Existing single main required')
        info=handles[0].get_info();fields=[name for name in dir(info) if not name.startswith('_')]
        capabilities={key:getattr(info,key) for key in ('vision','supports_vision','is_vision_model') if hasattr(info,key) and type(getattr(info,key)) is bool}
    after=main_identity(model)
    report=dict(mode='existing_main_capability_read_only',main_before=before,main_after=after,main_preserved=before==after,
        info_field_names=fields,boolean_capabilities=capabilities,image_requests=0,model_load_calls=0,physical_commands=0)
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps(report))
    if not report['main_preserved']:raise SystemExit(2)


if __name__=='__main__':main()
