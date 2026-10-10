"""Synthetic receipts and actual subprocess SQLite persistence, never live voice."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from reachy_companion.autonomous import voice_memory_fixture as fixture
from reachy_companion.autonomous.state import State
from reachy_companion.autonomous.voice_memory_fixture import prepare,operate
from reachy_companion.autonomous.memory import MemoryStore,MemoryConflict

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('voice_memory_realtime_fixture',ROOT/'deploy/autonomous/realtime_audio_session.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


def receipts():
    state=State();state.set_speech_operator(dict(binding=('agent',1,0),microphone_enabled=True,quiet=False,privacy_all=False))
    turns=[]
    for sequence,expected in ((1,'4'),(2,'6')):
        event=dict(type='utterance',text='Synthetic neutral practice response',audio=dict(source_boot='source',
            sequence=sequence,lineage_id='source:'+str(sequence),origin='unknown',pcm_sha256=str(sequence)*64,capture_age_ms=10,
            operator_binding=['agent',1,0]))
        working=runtime.admit_working_audio(lambda event,now:state.ingest(event,0),state,event)
        turns.append(dict(**working,lineage_id=event['audio']['lineage_id'],speaker_identity='unknown',confirmed=False,
            expected_answer=expected,expected_answer_matched=True,echo_reference_matched=True,capture_age_ms=10))
    hub=dict(mode='actual_distributed_realtime_audio_session',stage='complete',cancel_kind='actual_agent',
        raw_audio_retained=False,working_memory_receipt_schema='voice-working-1',cancel_to_verified_s=.49,
        controller='controller',session_boot='session',source_boot='source',hub_boot_id=state.authority.hub_boot_id,
        context_enabled=False,accepted=True,lease_transport='tcp',peer_stop_execution_busy=False,
        peer_stop=dict(stop_known=True,execution_busy=False),turns=turns,
        execution_busy={name:False for name in ('fast','main','audio','speech','peer_poll','lease','context','context_revoke','context_terminal_revoke','agent_cancel')})
    device=dict(controller='controller',source_boot='source',accepted=True,raw_audio_retained=False,capture_closed=True,
        microphone_restored=True,playback=dict(stop_known=True,execution_busy=False),
        peer_status=dict(source_boot='source',closed=True,watch_execution_busy=False,operator_execution_busy=False,
            operator_control_execution_busy=False),operator_after=dict(agent_boot_id='agent',microphone_epoch=2,
            microphone_enabled=False,capture_active=False,phase='paused',microphone_state_error=None,microphone_owner_present=False,
            motion_policy=dict(epoch=0,quiet=False,privacy_all=False)))
    return hub,device


class VoiceMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.directory=self.root/'disposable';self.hub_path=self.root/'hub.json';self.device_path=self.root/'device.json'
        hub,device=receipts();self.hub_path.write_text(json.dumps(hub));self.device_path.write_text(json.dumps(device))
        self.binding=dict(controller='controller',session_boot='session',source_boot='source');self.number=0

    def prepared(self):return prepare(self.directory,self.hub_path,self.device_path,self.binding)

    def cli(self,action,store=None,version=None,confirm=False,accepted=True):
        self.number+=1;output=self.root/('result-'+str(self.number)+'.json')
        command=[sys.executable,str(ROOT/'deploy/autonomous/voice_memory_acceptance.py'),action,
            '--directory',str(self.directory),'--output',str(output),'--allow-disposable-voice-fixture']
        if action=='prepare':
            command+=['--hub-receipt',str(self.hub_path),'--device-receipt',str(self.device_path),
                '--controller','controller','--session-boot','session','--source-boot','source']
        else:command+=['--expected-store-id',store,'--expected-version',str(version)]
        if confirm:command+=['--operator-confirmation']
        if action=='cleanup':command+=['--exclusive-filesystem-cleanup']
        process=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=8)
        self.assertEqual(process.returncode,0 if accepted else 2,process.stderr+process.stdout)
        result=json.loads(output.read_text());self.assertEqual(result['accepted'],accepted)
        self.assertEqual(output.stat().st_mode & 0o777,0o600)
        self.assertFalse(result['live_voice_verified']);self.assertFalse(result['speaker_identity_confirmed'])
        self.assertFalse(result['model_inference']);return result

    def test_separate_processes_confirmation_correction_restart_forget_and_owned_cleanup(self):
        initial=self.cli('prepare');store=initial['store_id']
        self.assertEqual(initial['versions'],[]);self.assertEqual(initial['proposal_version'],0)
        self.cli('confirm',store,0,accepted=False)
        confirmed=self.cli('confirm',store,0,confirm=True);self.assertEqual(confirmed['versions'],[1])
        self.assertEqual(self.cli('readback',store,1)['revision'],confirmed['revision'])
        self.cli('correct',store,0,confirm=True,accepted=False)
        corrected=self.cli('correct',store,1,confirm=True);self.assertEqual(corrected['versions'],[2])
        reopened=self.cli('readback',store,2);self.assertEqual(reopened['revision'],corrected['revision'])
        self.assertTrue(reopened['state_projection_verified']);self.assertTrue(reopened['content_whitelist_verified'])
        forgotten=self.cli('forget',store,2);self.assertEqual(forgotten['versions'],[])
        self.assertTrue(forgotten['forgotten_replay_rejected']);self.cli('readback',store,-1)
        self.cli('confirm',store,0,confirm=True,accepted=False)
        cleaned=self.cli('cleanup',store,-1);self.assertTrue(cleaned['owned_files_removed'])
        self.assertFalse(self.directory.exists());self.assertTrue(self.hub_path.exists())

    def test_invalid_or_unfinished_provenance_never_creates_store(self):
        for name in ('busy','failed','foreign','identity','unadmitted','epoch','digest','expired','sequence','legacy','late_cancel'):
            hub,device=receipts()
            if name=='busy':hub['execution_busy']['main']=True
            elif name=='failed':device['accepted']=False
            elif name=='foreign':hub['turns'][0]['source_boot']='foreign'
            elif name=='identity':hub['turns'][0]['speaker_identity']='owner'
            elif name=='unadmitted':hub['turns'][0]['working_memory_admitted']=False
            elif name=='epoch':hub['turns'][0]['working_authority']['microphone_epoch']=True
            elif name=='digest':hub['turns'][0]['pcm_sha256']='invalid'
            elif name=='expired':hub['turns'][0]['capture_age_ms']=2000
            elif name=='sequence':hub['turns'][1]['sequence']=hub['turns'][0]['sequence']
            elif name=='legacy':hub.pop('working_memory_receipt_schema')
            else:hub['cancel_to_verified_s']=.500001
            self.hub_path.write_text(json.dumps(hub));self.device_path.write_text(json.dumps(device))
            with self.subTest(name=name),self.assertRaises(ValueError):self.prepared()
            self.assertFalse(self.directory.exists())

    def test_foreign_store_files_locks_and_symlinks_are_preserved(self):
        store=self.prepared()['store_id']
        with self.assertRaises(ValueError):operate('confirm',self.directory,'foreign',0,True)
        with self.assertRaises(MemoryConflict):operate('confirm',self.directory,store,0)
        with self.assertRaises(ValueError):operate('readback',self.directory,store,True)
        lock=self.directory/'operator.lock';lock.write_text('occupied')
        with self.assertRaises(FileExistsError):operate('readback',self.directory,store,0)
        self.assertEqual(lock.read_text(),'occupied');lock.unlink()
        operate('forget',self.directory,store,0)
        foreign=self.directory/'foreign.txt';foreign.write_text('preserve')
        with self.assertRaises(ValueError):operate('cleanup',self.directory,store,-1,exclusive_filesystem_cleanup=True)
        self.assertEqual(foreign.read_text(),'preserve');foreign.unlink()
        target=self.root/'private.txt';target.write_text('preserve')
        link=self.directory/'memory.sqlite-wal';link.symlink_to(target)
        with self.assertRaises(ValueError):operate('cleanup',self.directory,store,-1,exclusive_filesystem_cleanup=True)
        self.assertEqual(target.read_text(),'preserve');link.unlink()
        self.assertTrue(operate('cleanup',self.directory,store,-1,exclusive_filesystem_cleanup=True)['owned_files_removed'])

    def test_owner_correction_fences_ready_speech_and_new_store_rejects_old_uuid(self):
        store_id=self.prepared()['store_id'];operate('confirm',self.directory,store_id,0,True)
        meta=json.loads((self.directory/'binding.json').read_text())
        reader=MemoryStore(self.directory/'memory.sqlite',[meta['namespace']])
        try:
            state=State();state.speech_attached=True
            state.update_context(dict(memory=reader.recall(),sensors=[]),0)
            state.ingest(dict(type='utterance',text='Neutral fixture readback'),0)
            ref=next(iter(state.candidates))
            task=state.apply(dict(a='think',why='synthetic fixture',start=dict(type='main',input_ref=ref)),state.bind(0,5),0)
            state.complete(task.task_id,task.attempt_id,task.authority,'Synthetic reply depending on old marker',.1)
            stale=state.bind(.2,5)
            operate('correct',self.directory,store_id,1,True)
            state.update_context(dict(memory=reader.recall(),sensors=[]),.3)
            state.apply(dict(a='converse',why='late synthetic result',commit=task.task_id),stale,.4)
            self.assertEqual(task.status,'discarded');self.assertFalse(state.speech_proposals)
            self.assertEqual(reader.recall()['items'][0]['version'],2)
        finally:reader.close()
        operate('forget',self.directory,store_id,2);operate('cleanup',self.directory,store_id,-1,exclusive_filesystem_cleanup=True)
        replacement=self.prepared();self.assertNotEqual(replacement['store_id'],store_id)
        with self.assertRaises(ValueError):operate('confirm',self.directory,store_id,0,True)
        operate('forget',self.directory,replacement['store_id'],0)
        operate('cleanup',self.directory,replacement['store_id'],-1,exclusive_filesystem_cleanup=True)

    def test_cleanup_requires_exclusive_authority_and_supported_anchored_operations(self):
        store=self.prepared()['store_id'];operate('forget',self.directory,store,0)
        with self.assertRaises(ValueError):operate('cleanup',self.directory,store,-1)
        with patch.object(fixture.OwnedCleanup,'platform_check',side_effect=ValueError('Unsupported anchored operations')):
            with self.assertRaises(ValueError):operate('cleanup',self.directory,store,-1,exclusive_filesystem_cleanup=True)
        self.assertTrue((self.directory/'memory.sqlite').exists());self.assertFalse((self.directory/'operator.lock').exists())
        operate('cleanup',self.directory,store,-1,exclusive_filesystem_cleanup=True)

    def test_mid_cleanup_file_and_directory_replacements_are_preserved(self):
        for replacement in ('file','directory'):
            with self.subTest(replacement=replacement):
                self.directory=self.root/('replace-'+replacement)
                store=self.prepared()['store_id'];operate('forget',self.directory,store,0)
                saved=self.root/('saved-'+replacement);original=fixture.projection
                def replace(*args):
                    result=original(*args)
                    if replacement=='file':(self.directory/'memory.sqlite').rename(saved)
                    else:
                        self.directory.rename(saved);self.directory.mkdir();(self.directory/'operator.lock').write_bytes(b'foreign lock')
                    (self.directory/'memory.sqlite').write_bytes(b'foreign sentinel')
                    return result
                with patch.object(fixture,'projection',side_effect=replace):
                    with self.assertRaises(fixture.CleanupOwnershipConflict):
                        operate('cleanup',self.directory,store,-1,exclusive_filesystem_cleanup=True)
                self.assertEqual((self.directory/'memory.sqlite').read_bytes(),b'foreign sentinel')
                self.assertTrue(saved.exists())
                if replacement=='directory':self.assertEqual((self.directory/'operator.lock').read_bytes(),b'foreign lock')

    def test_replacement_after_last_check_is_atomically_moved_and_preserved_not_unlinked(self):
        for after_detach in (False,True):
            with self.subTest(after_detach=after_detach):
                self.directory=self.root/('race-'+str(after_detach));store=self.prepared()['store_id']
                operate('forget',self.directory,store,0);armed=[False]
                projection=fixture.projection;verify=fixture.OwnedCleanup.verify
                def arm(*args):result=projection(*args);armed[0]=True;return result
                def race(owner,source_name=False,allow_journals=False):
                    names=verify(owner,source_name,allow_journals)
                    if armed[0] and source_name is not after_detach:
                        armed[0]=False
                        saved=self.root/('race-saved-'+str(after_detach))
                        fixture.os.rename('memory.sqlite',saved,src_dir_fd=owner.directory)
                        fd=fixture.os.open('memory.sqlite',fixture.os.O_WRONLY|fixture.os.O_CREAT|fixture.os.O_EXCL,
                            0o600,dir_fd=owner.directory)
                        fixture.os.write(fd,b'foreign after check');fixture.os.close(fd)
                    return names
                with patch.object(fixture,'projection',side_effect=arm),patch.object(fixture.OwnedCleanup,'verify',race):
                    with self.assertRaises(fixture.CleanupOwnershipConflict) as error:
                        operate('cleanup',self.directory,store,-1,exclusive_filesystem_cleanup=True)
                self.assertIsNotNone(error.exception.preserved_path)
                preserved=Path(error.exception.preserved_path)
                self.assertTrue(any(path.is_file() and path.read_bytes()==b'foreign after check' for path in preserved.rglob('*')))
                self.assertTrue((self.root/('race-saved-'+str(after_detach))).exists())


if __name__=='__main__':unittest.main()
