"""Trusted CLI fixture writer; no gateway/model memory-write capability."""
import argparse
import hashlib
import re
from pathlib import Path
from reachy_companion.autonomous.memory import MemoryStore


def fixture(version=0,fixture_id='fixture-color'):
    return dict(schema_version='1.1',id=fixture_id,version=version,namespace='fixture',memory_kind='semantic',
                epistemic_type='preference',content='В синтетическом fixture любимый цвет — синий.' if version==0 else 'Correction: в синтетическом fixture любимый цвет — зелёный.',
                valid_from='2020-01-01T00:00:00Z',valid_until=None,created_at='2026-10-10T00:00:00Z',
                evidence_ids=[fixture_id+'-evidence' if version==0 else fixture_id+'-correction'],
                counterevidence_ids=[] if version==0 else [fixture_id+'-evidence'],confidence=None,status='active',
                author='synthetic-fixture-owner',model_version=None,prompt_version='fixture-v1',supersedes=None,
                lineage_ids=[fixture_id+'-root'],claim=None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['seed','correct','forget','restart-check']);parser.add_argument('--path',type=Path,required=True)
    parser.add_argument('--fixture-id',default='fixture-color')
    args=parser.parse_args();store=MemoryStore(args.path,['fixture'])
    try:
        if not re.fullmatch(r'fixture-[a-z0-9-]{1,64}',args.fixture_id):parser.error('Bounded synthetic dataset ID required')
        item=args.fixture_id;root=item+'-root'
        if args.action=='seed':
            store.evidence(item+'-evidence',hashlib.sha256((item+': synthetic fixture only').encode()).hexdigest(),root,'fixture','fixture')
            store.commit(fixture(fixture_id=item),None,confirmed=True)
        elif args.action=='correct':
            store.evidence(item+'-correction',hashlib.sha256((item+': synthetic fixture correction green').encode()).hexdigest(),root,'fixture','fixture')
            store.commit(fixture(1,item),0,confirmed=True)
        elif args.action=='forget':store.forget_lineage(root)
        before=store.recall();store.close();store=MemoryStore(args.path,['fixture'])
        after=store.recall()
        if before!=after:raise RuntimeError('Restart persistence mismatch')
        print({'action':args.action,'store_id':after['store_id'],'revision':after['revision'],
               'versions':[x['version'] for x in after['items']],'restart_equal':True})
    finally:store.close()


if __name__=='__main__':main()
