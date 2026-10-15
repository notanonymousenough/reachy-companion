"""Read-only clean-PC configuration preflight; no downloads, inference or grants."""
import argparse
import ipaddress
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from reachy_companion.config import Config


def check(config,repo):
    errors=[]
    if sys.version_info<(3,11):errors.append('python_3_11_required')
    if config.root!=Path(repo).resolve():errors.append('config_must_be_in_checkout_root')
    if config['voice']['mode']!='remote':errors.append('remote_voice_mode_required')
    if config['streaming']['enabled'] is not True:errors.append('streaming_required')
    try:ipaddress.IPv4Address(config['security']['robot']['hub_source_ipv4'])
    except ValueError:errors.append('explicit_hub_ipv4_required')
    for key in ('hub_url','voice_url','compute_url','agent_url','robot_url'):
        value=urlsplit(config['network'][key])
        if value.scheme!='http' or not value.hostname or value.username or value.password or value.query or value.fragment:
            errors.append('invalid_'+key)
    desktop=urlsplit(config['container']['desktop_llm_base_url'])
    if (desktop.scheme!='http' or not desktop.hostname or desktop.username or desktop.password
            or desktop.query or desktop.fragment or desktop.path.rstrip('/')!='/v1'):
        errors.append('invalid_desktop_llm_base_url')
    if Path(config['paths']['token_file']).is_absolute():errors.append('relative_shared_token_path_required')
    try:
        token=config.path(config['paths']['token_file']).read_text().strip()
        if len(token)<32 or token!=config.token:errors.append('shared_token_file_or_environment_conflict')
    except OSError:errors.append('shared_token_file_required')
    if not config['runtime']['windows']['model_key'].strip():errors.append('local_model_key_required')
    if config['brains']['provider']!='lm_studio':errors.append('clean_pc_baseline_requires_lm_studio')
    if not 1024<=config['runtime']['windows']['context_length']<=262144:errors.append('context_length_bound')
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True)
    args=parser.parse_args()
    try:
        config=Config(args.config);errors=check(config,Path(__file__).resolve().parents[2])
    except Exception:errors=['config_or_shared_token_invalid']
    print(json.dumps(dict(ok=not errors,errors=errors,read_only=True,models_loaded=False,microphone_enabled_by_preflight=False)))
    return 0 if not errors else 2


if __name__=='__main__':raise SystemExit(main())
