"""Trusted CLI fixture writer; no gateway/model memory-write capability."""
import argparse
import hashlib
from pathlib import Path
from reachy_companion.autonomous.memory import MemoryStore


def fixture(version=0):
    return dict(schema_version='1.1',id='fixture-color',version=version,namespace='fixture',memory_kind='semantic',
                epistemic_type='preference',content='В синтетическом fixture любимый цвет — синий.' if version==0 else 'Correction: в синтетическом fixture любимый цвет — зелёный.',
                valid_from='2020-01-01T00:00:00Z',valid_until=None,created_at='2026-10-10T00:00:00Z',
                evidence_ids=['fixture-color-evidence' if version==0 else 'fixture-color-correction'],
                counterevidence_ids=[] if version==0 else ['fixture-color-evidence'],confidence=None,status='active',
                author='synthetic-fixture-owner',model_version=None,prompt_version='fixture-v1',supersedes=None,
                lineage_ids=['fixture-color-root'],claim=None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['seed','correct','forget','restart-check']);parser.add_argument('--path',type=Path,required=True)
    args=parser.parse_args();store=MemoryStore(args.path,['fixture'])
    try:
        if args.action=='seed':
            store.evidence('fixture-color-evidence',hashlib.sha256(b'synthetic fixture only').hexdigest(),'fixture-color-root','fixture','fixture')
            store.commit(fixture(),None,confirmed=True)
        elif args.action=='correct':
            store.evidence('fixture-color-correction',hashlib.sha256(b'synthetic fixture correction green').hexdigest(),'fixture-color-root','fixture','fixture')
            store.commit(fixture(1),0,confirmed=True)
        elif args.action=='forget':store.forget_lineage('fixture-color-root')
        before=store.recall();store.close();store=MemoryStore(args.path,['fixture'])
        after=store.recall()
        if before!=after:raise RuntimeError('Restart persistence mismatch')
        print({'action':args.action,'store_id':after['store_id'],'revision':after['revision'],
               'versions':[x['version'] for x in after['items']],'restart_equal':True})
    finally:store.close()


if __name__=='__main__':main()
