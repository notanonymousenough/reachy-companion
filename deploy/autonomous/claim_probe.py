"""Finite synthetic owner-claim transaction probe; no models or hardware."""
import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
import tempfile
from memory_fixture import fixture
from reachy_companion.autonomous.memory import MemoryStore,MemoryConflict


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    checks={};args.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='claim-fixture-',dir=args.directory) as directory:
        path=Path(directory)/'fixture.sqlite3';store=MemoryStore(path,['fixture']);source='fixture-claims-probe'
        root=source+'-root';first=fixture(fixture_id=source)
        first.update(content='Synthetic claim fixture: likes jazz.',claim=dict(subject='fixture-user',predicate='likes',value='jazz',polarity='positive',scope='fixture-only'))
        try:
            store.evidence(source+'-evidence',hashlib.sha256(b'new synthetic claim transaction dataset').hexdigest(),root,'fixture','fixture')
            store.commit(first,None,confirmed=True);before=store.recall()
            for label,polarity in [('duplicate','positive'),('negation','negative')]:
                candidate={**first,'id':source+'-'+label,'claim':{**first['claim'],'polarity':polarity}}
                try:store.commit(candidate,None,confirmed=True)
                except MemoryConflict:checks[label+'_rejected']=True
                else:checks[label+'_rejected']=False
            checks['rejected_transactions_unchanged']=before==store.recall() and store.count('versions')==1
            correction=source+'-correction'
            store.evidence(correction,hashlib.sha256(b'synthetic owner correction: does not like jazz').hexdigest(),root,'fixture','fixture')
            store.commit({**first,'version':1,'content':'Synthetic owner correction: does not like jazz.',
                'evidence_ids':[correction],'counterevidence_ids':first['evidence_ids'],
                'claim':{**first['claim'],'polarity':'negative'}},0,confirmed=True)
            corrected=store.recall();store.close();store=MemoryStore(path,['fixture'])
            checks['correction_survives_restart']=corrected==store.recall() and corrected['items'][0]['claim']['polarity']=='negative'
            checks['forget_removed_item']=store.forget_lineage(root)==1
            forgotten=store.recall();store.close();store=MemoryStore(path,['fixture'])
            checks['forget_survives_restart']=forgotten==store.recall() and not forgotten['items']
            try:store.evidence(source+'-evidence','a'*64,root,'fixture','fixture')
            except MemoryConflict:checks['revoked_root_reimport_rejected']=True
            else:checks['revoked_root_reimport_rejected']=False
        finally:store.close()
    report=dict(mode='sqlite_synthetic_claims',checks=checks,accepted=all(checks.values()),
                environment=dict(platform=sys.platform,python=platform.python_version(),machine=platform.machine()),
                fixture_files_removed=True,models_called=0,physical_commands=0,traits_or_policy_written=0)
    with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps(report))
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
