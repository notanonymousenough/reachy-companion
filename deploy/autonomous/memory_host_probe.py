"""Finite synthetic durability probe on the memory owner PC; no inference/audio."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from reachy_companion.autonomous.memory import MemoryStore,MemoryConflict


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.database.exists() or args.output.exists():raise FileExistsError('Fresh isolated paths required')
    start=time.monotonic();store=None
    report=dict(mode='actual_host_sqlite_synthetic_provenance',accepted=False,
        private_inputs=0,model_inference=False,physical_commands=0)
    try:
        store=MemoryStore(args.database,['fixture-host'])
        store.evidence('e1',hashlib.sha256(b'public arithmetic fixture').hexdigest(),'root1','fixture-host','fixture')
        item=dict(schema_version='1.1',id='fixture-item',version=0,namespace='fixture-host',memory_kind='semantic',
            epistemic_type='fact',content='Synthetic arithmetic observation: 2 + 2 = 5',
            valid_from='2020-01-01T00:00:00Z',valid_until=None,
            created_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
            evidence_ids=['e1'],counterevidence_ids=[],confidence=None,status='proposed',author='fixture-owner',
            model_version=None,prompt_version='fixture-v1',supersedes=None,lineage_ids=['root1'],claim=None)
        store.commit(item,None)
        assert not store.recall()['items']
        try:store.commit({**item,'version':1,'status':'active'},0)
        except MemoryConflict:report['unconfirmed_promotion_rejected']=True
        else:raise AssertionError('Unconfirmed promotion')
        corrected={**item,'version':1,'status':'active','content':'Synthetic arithmetic observation: 2 + 2 = 4'}
        store.commit(corrected,0,confirmed=True)
        descriptor=dict(alias='fixture-item:1',type='fact',summary=corrected['content'])
        before=store.recall();assert store.supports([descriptor])
        store.close();store=None
        store=MemoryStore(args.database,['fixture-host']);after=store.recall()
        assert before==after and after['items'][0]['version']==1
        report['restart_preserved_version']=True
        try:store.commit({**corrected,'version':2},0,confirmed=True)
        except MemoryConflict:report['stale_correction_rejected']=True
        else:raise AssertionError('Stale correction')
        assert store.forget_lineage('root1')==1 and not store.supports([descriptor])
        store.close();store=None
        store=MemoryStore(args.database,['fixture-host']);assert not store.recall()['items']
        try:store.evidence('e1','a'*64,'root1','fixture-host','fixture')
        except MemoryConflict:report['forgotten_lineage_reimport_rejected']=True
        else:raise AssertionError('Forgotten lineage resurrected')
        report.update(deletion_survived_restart=True,accepted=True)
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)[:128]
    finally:
        if store:store.close()
        report.update(elapsed_s=time.monotonic()-start,database_bytes=args.database.stat().st_size if args.database.exists() else 0)
        with args.output.open('x') as output:json.dump(report,output,indent=2)
    print(json.dumps(report),flush=True)
    if not report['accepted']:raise SystemExit(2)


if __name__=='__main__':main()
