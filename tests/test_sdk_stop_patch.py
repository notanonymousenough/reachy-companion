"""Exercise the reviewed SDK patch through real local FastAPI response validation.

No installed SDK file is changed and no hardware/daemon process is started.
"""
import asyncio
import hashlib
from pathlib import Path
import sys
import types
import unittest
from uuid import uuid4
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:
    FastAPI=TestClient=None

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'deploy/patches/reachy-mini-1.11.0-owned-stop-idempotent.patch'
FIXTURE=ROOT/'tests/fixtures/reachy_sdk_1_11_move_stop.py'
BASE_SHA='ca18dbc85041a49b784b17b0bb09c06a7c6eec82bcd8f1dd2a23d64275a18943'
PATCHED_SHA='8e7d7dae115c50949de0f91dddf71bbf88cb7f354ff5e396b8626d4caec14d76'


def apply_exact_hunks(source):
    hunks=[]
    for line in PATCH.read_text().splitlines(True):
        if line.startswith('@@ '):hunks.append(([],[]))
        elif hunks and line[:1] in (' ','-','+'):
            before,after=hunks[-1]
            if line[0] in (' ','-'):before.append(line[1:])
            if line[0] in (' ','+'):after.append(line[1:])
    for before,after in hunks:
        old=''.join(before);new=''.join(after)
        if source.count(old)!=1:raise ValueError('Patch preimage mismatch; no fuzzy application')
        source=source.replace(old,new,1)
    return source


class SDKStopPatchTests(unittest.TestCase):
    def app(self,patched=True):
        source=FIXTURE.read_text()
        if patched:source=apply_exact_hunks(source)
        name='sdk_stop_fixture_'+uuid4().hex
        module=types.ModuleType(name);sys.modules[name]=module
        self.addCleanup(sys.modules.pop,name,None)
        exec(compile(source,str(FIXTURE),'exec'),module.__dict__)
        app=FastAPI();app.include_router(module.router);self.finished=[]
        @app.post('/fixture/start')
        async def start():
            async def wait(label):
                try:await asyncio.sleep(3600)
                finally:
                    await asyncio.sleep(0)
                    self.finished.append(label)
            target=module.create_move_task(wait('target'))
            foreign=module.create_move_task(wait('foreign'))
            await asyncio.sleep(0)
            return dict(target=str(target.uuid),foreign=str(foreign.uuid))
        @app.post('/fixture/completed')
        async def completed():
            task=module.create_move_task(asyncio.sleep(0))
            while task.uuid in module.move_tasks:await asyncio.sleep(0)
            return dict(uuid=str(task.uuid))
        return app

    def test_unpatched_missing_uuid_reproduces_500_and_patch_returns_typed_exact_uuid(self):
        if TestClient is None:self.skipTest('Optional FastAPI test runtime unavailable; no install performed')
        target=str(uuid4())
        with TestClient(self.app(patched=False),raise_server_exceptions=False) as client:
            self.assertEqual(client.post('/move/stop',json=dict(uuid=target)).status_code,500)
        with TestClient(self.app()) as client:
            response=client.post('/move/stop',json=dict(uuid=target))
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['uuid'],target)
            self.assertIs(response.json()['already_absent'],True)

    def test_completed_uuid_and_repeated_stop_are_idempotent(self):
        if TestClient is None:self.skipTest('Optional FastAPI test runtime unavailable; no install performed')
        with TestClient(self.app()) as client:
            target=client.post('/fixture/completed').json()['uuid']
            for _ in range(2):
                response=client.post('/move/stop',json=dict(uuid=target))
                self.assertEqual(response.status_code,200);self.assertIs(response.json()['already_absent'],True)
            self.assertEqual(client.get('/move/running').json(),[])

    def test_present_stop_awaits_only_target_cancellation_and_preserves_foreign(self):
        if TestClient is None:self.skipTest('Optional FastAPI test runtime unavailable; no install performed')
        with TestClient(self.app()) as client:
            ids=client.post('/fixture/start').json()
            response=client.post('/move/stop',json=dict(uuid=ids['target']))
            self.assertEqual(response.status_code,200);self.assertIs(response.json()['already_absent'],False)
            self.assertEqual(response.json()['uuid'],ids['target'])
            self.assertIn('target',self.finished);self.assertNotIn('foreign',self.finished)
            self.assertEqual(client.get('/move/running').json(),[dict(uuid=ids['foreign'])])
            client.post('/move/stop',json=dict(uuid=str(uuid4())))
            self.assertNotIn('foreign',self.finished)
            self.assertEqual(client.post('/move/stop',json=dict(uuid='bad')).status_code,422)
            self.assertEqual(client.get('/move/running').json(),[dict(uuid=ids['foreign'])])
            client.post('/move/stop',json=dict(uuid=ids['foreign']))

    def test_full_cached_sdk_exact_preimage_and_patched_digest(self):
        path=Path('/private/tmp/reachy-factory-v111-source/extracted/reachy_mini/daemon/app/routers/move.py')
        if not path.exists():self.skipTest('No cached SDK source; no download or install performed')
        original=path.read_bytes();self.assertEqual(hashlib.sha256(original).hexdigest(),BASE_SHA)
        self.assertEqual(hashlib.sha256(apply_exact_hunks(original.decode()).encode()).hexdigest(),PATCHED_SHA)


if __name__=='__main__':unittest.main()
