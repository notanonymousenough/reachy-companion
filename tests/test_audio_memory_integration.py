"""Cross-component fixture: unknown audio evidence, owner CAS, stale speech fence."""
from datetime import datetime,timezone
import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from reachy_companion.autonomous.audio_adapter import AudioAdapter
from reachy_companion.autonomous.memory import MemoryStore,MemoryConflict
from reachy_companion.autonomous.state import State


def proposed_note(audio):
    stamp=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    return dict(schema_version='1.1',id='fixture-audio-note',version=0,namespace='fixture-audio',
        memory_kind='semantic',epistemic_type='preference',content='Synthetic unconfirmed preference',
        valid_from=stamp,valid_until=None,created_at=stamp,evidence_ids=['fixture-audio-evidence'],counterevidence_ids=[],
        confidence=None,status='proposed',author='fixture-owner',model_version=None,prompt_version='fixture-audio-v1',
        supersedes=None,lineage_ids=[audio['lineage_id']],claim=None)


class AudioMemoryTests(unittest.TestCase):
    def test_unknown_audio_proposal_owner_correction_and_late_speech_are_fenced(self):
        class FixtureSTT:
            def transcribe(self,pcm):return 'Synthetic unconfirmed voice turn'
        adapter=AudioAdapter(FixtureSTT());self.addCleanup(adapter.close)
        adapter.bind_source('fixture-capture',0)
        state=State();state.speech_attached=True
        operator=dict(binding=('fixture-agent',1,0),microphone_enabled=True,quiet=False,privacy_all=False,
            valid_until=time.monotonic()+.3)
        adapter.advance(state.authority,operator);pcm=b'\0\0'*320
        self.assertTrue(adapter.submit(pcm,source_boot='fixture-capture',sequence=1,captured_end=time.monotonic(),
            authority=state.authority,operator_binding=operator['binding']))
        adapter.advance(state.authority,operator)
        deadline=time.monotonic()+1
        while adapter.status()['execution_busy'] and time.monotonic()<deadline:time.sleep(.002)
        event=adapter.advance(state.authority,operator);self.assertIsNotNone(event)
        audio=event['audio'];self.assertFalse(audio['confirmed']);self.assertEqual(audio['speaker_identity'],'unknown')
        self.assertEqual(audio['pcm_sha256'],hashlib.sha256(pcm).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            store=MemoryStore(Path(directory)/'fixture.sqlite',['fixture-audio'])
            try:
                # This explicit fixture owner records digest/lineage, never PCM
                # or a speaker identity. Runtime automatic memory writes remain off.
                store.evidence('fixture-audio-evidence',audio['pcm_sha256'],audio['lineage_id'],'fixture-audio','sensor')
                note=proposed_note(audio);store.commit(note,None)
                self.assertFalse(store.recall()['items'])
                active={**note,'version':1,'status':'active','content':'Fixture owner confirmed preference'}
                with self.assertRaises(MemoryConflict):store.commit(active,0)
                store.commit(active,0,confirmed=True)
                state.update_context(dict(memory=store.recall(),sensors=[]),0)
                state.ingest(event,0);ref=next(iter(state.candidates))
                task=state.apply(dict(a='think',why='fixture start',start=dict(type='main',input_ref=ref)),state.bind(0,5),0)
                self.assertEqual(task.prompt['memory'][0]['version'],1)
                state.complete(task.task_id,task.attempt_id,task.authority,'Fixture answer using version one',.1)
                stale_binding=state.bind(.2,5)
                corrected={**active,'version':2,'content':'Fixture owner corrected preference'}
                with self.assertRaises(MemoryConflict):store.commit(corrected,0,confirmed=True)
                store.commit(corrected,1,confirmed=True)
                state.update_context(dict(memory=store.recall(),sensors=[]),.3)
                state.apply(dict(a='converse',why='late fixture commit',commit=task.task_id),stale_binding,.4)
                self.assertEqual(task.status,'discarded');self.assertFalse(state.speech_proposals)
                # Deletion revokes this sensor lineage and cannot be undone by
                # replay of the same audio event, even with owner confirmation.
                store.forget_lineage(audio['lineage_id'])
                self.assertFalse(store.recall()['items'])
                with self.assertRaises(MemoryConflict):
                    store.evidence('fixture-audio-evidence',audio['pcm_sha256'],audio['lineage_id'],'fixture-audio','sensor')
            finally:store.close()
