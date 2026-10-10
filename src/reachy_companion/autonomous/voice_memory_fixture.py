"""Trusted-owner disposable acceptance using the existing PC MemoryStore.

Finished receipts are runner-trusted files, not signed hardware attestations.
Only fixed neutral fixture content is writable; unknown speech never confirms.
"""
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from .audio_session_control import cleanup_receipts
from .contracts import Authority,decode,uid
from .memory import MemoryStore,MemoryConflict
from .state import State

CONTENTS=('Disposable arithmetic fixture marker: four.','Disposable arithmetic fixture marker: six.')
FILES={'memory.sqlite','memory.sqlite-wal','memory.sqlite-shm','binding.json','operator.lock'}


class CleanupOwnershipConflict(MemoryConflict):
    def __init__(self,message,preserved_path=None):
        super().__init__(message);self.preserved_path=preserved_path


class OwnedCleanup:
    """Pin identities, detach names, verify moved objects before any deletion.

    Requires exclusive filesystem authority over the source during SQLite use
    and close, and over a fresh private quarantine. SQLite journal cleanup and
    privileged/same-UID access to the quarantine are outside the race guarantee.
    Unsupported anchored-directory operations fail closed (including Windows).
    """
    @staticmethod
    def platform_check():
        required=(os.open,os.stat,os.rename,os.unlink,os.mkdir,os.rmdir)
        if (os.name!='posix' or any(fn not in os.supports_dir_fd for fn in required)
                or not hasattr(os,'O_NOFOLLOW')):raise ValueError('Anchored cleanup unavailable on this platform')
    def __init__(self,directory):
        self.platform_check()
        self.path=Path(directory).absolute();self.parent=self.directory=None;self.files={};self.detached=False;self.quarantine=None
        try:
            flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
            self.parent=os.open(self.path.parent,flags)
            self.directory=os.open(self.path.name,flags,dir_fd=self.parent)
            self.directory_id=self.identity(os.fstat(self.directory))
            for name in os.listdir(self.directory):
                if name not in FILES:raise CleanupOwnershipConflict('Unexpected cleanup entry')
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.directory)
                self.files[name]=fd
                if not stat.S_ISREG(os.fstat(fd).st_mode):raise CleanupOwnershipConflict('Regular owned file required')
        except BaseException:self.close();raise
    @staticmethod
    def identity(value):return value.st_dev,value.st_ino
    def verify(self,source_name=False,allow_journals=False):
        if source_name and self.identity(os.stat(self.path.name,dir_fd=self.parent,follow_symlinks=False))!=self.directory_id:
            raise CleanupOwnershipConflict('Fixture directory replaced')
        names=set(os.listdir(self.directory))
        required=set(self.files)-{'memory.sqlite-wal','memory.sqlite-shm'}
        allowed=set(self.files)|({'memory.sqlite-wal','memory.sqlite-shm'} if allow_journals else set())
        if not required<=names or not names<=allowed:raise CleanupOwnershipConflict('Fixture entries changed')
        for name in names:
            if name not in self.files:continue
            current=os.stat(name,dir_fd=self.directory,follow_symlinks=False)
            if self.identity(current)!=self.identity(os.fstat(self.files[name])):
                raise CleanupOwnershipConflict('Fixture file replaced')
        return names
    def pin_journals(self):
        names=self.verify(source_name=True,allow_journals=True)
        for name in names-set(self.files):
            self.files[name]=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.directory)
        self.verify(source_name=True)
    def remove(self):
        self.verify(source_name=True)
        scratch='.voice-cleanup-'+uid();os.mkdir(scratch,0o700,dir_fd=self.parent)
        self.quarantine=self.path.parent/scratch
        qfd=os.open(scratch,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.parent)
        try:
            os.rename(self.path.name,'fixture',src_dir_fd=self.parent,dst_dir_fd=qfd);self.detached=True
            moved=os.stat('fixture',dir_fd=qfd,follow_symlinks=False)
            if self.identity(moved)!=self.directory_id:raise CleanupOwnershipConflict('Moved directory is foreign')
            names=self.verify();tokens=[]
            for name in sorted(names):
                token='owned-'+uid()
                os.rename(name,token,src_dir_fd=self.directory,dst_dir_fd=qfd)
                current=os.stat(token,dir_fd=qfd,follow_symlinks=False)
                if self.identity(current)!=self.identity(os.fstat(self.files[name])):
                    raise CleanupOwnershipConflict('Moved file is foreign')
                tokens.append(token)
            if os.listdir(self.directory):raise CleanupOwnershipConflict('New entries after detachment')
            # All moved objects are verified. Only the exclusive private
            # quarantine is now unlinked; original path racers cannot name them.
            for token in tokens:os.unlink(token,dir_fd=qfd)
            os.rmdir('fixture',dir_fd=qfd)
        except BaseException as exc:
            raise CleanupOwnershipConflict('Cleanup preserved quarantine',str(self.quarantine)) from exc
        finally:os.close(qfd)
        os.rmdir(scratch,dir_fd=self.parent)
        return dict(owned_files_removed=True,cleanup_contract='exclusive_private_quarantine',
            adversarial_same_uid_race_safe=False,original_path_reused=self.path.exists())
    def release_lock(self,lock_fd):
        # Successful cleanup already removed the pinned lock. On failure retain
        # it with the source/quarantine; never unlink a source name after a check.
        return
    def close(self):
        for fd in self.files.values():os.close(fd)
        self.files.clear()
        for name in ('directory','parent'):
            fd=getattr(self,name,None)
            if fd is not None:os.close(fd);setattr(self,name,None)


def read_json(path,cap):
    with Path(path).open('rb') as handle:raw=handle.read(cap+1)
    if len(raw)>cap:raise ValueError('Fixture input cap')
    value=decode(raw)
    if not isinstance(value,dict):raise ValueError('Fixture object required')
    return value,hashlib.sha256(raw).hexdigest()


def private_json(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as handle:
        json.dump(value,handle,ensure_ascii=False,allow_nan=False);handle.flush();os.fsync(handle.fileno())


def voice_provenance(hub,device,binding):
    if (hub.get('mode')!='actual_distributed_realtime_audio_session' or hub.get('stage')!='complete'
            or hub.get('cancel_kind')!='actual_agent' or hub.get('raw_audio_retained') is not False
            or device.get('raw_audio_retained') is not False or device.get('accepted') is not True):
        raise ValueError('Finished owned actual-Agent voice receipts required')
    audit=cleanup_receipts(hub,device,**binding)
    if not audit['receipt_cleanup_verified'] or not audit['voice_acceptance']:raise ValueError('Voice cleanup/acceptance missing')
    turns=hub.get('turns')
    elapsed=hub.get('cancel_to_verified_s')
    if (hub.get('working_memory_receipt_schema')!='voice-working-1' or not isinstance(hub.get('hub_boot_id'),str)
            or not 1<=len(hub['hub_boot_id'])<=128 or type(elapsed) not in (int,float)
            or not math.isfinite(elapsed) or not 0<=elapsed<=.5 or not isinstance(turns,list) or len(turns)!=2):
        raise ValueError('Finished bounded practice receipt required')
    last_sequence=-1;last_interaction=-1
    for turn,expected in zip(turns,('4','6')):
        if not isinstance(turn,dict):raise ValueError('Typed voice turn')
        authority=turn.get('working_authority',{})
        operator=turn.get('working_operator_binding');policy=device['operator_after'].get('motion_policy',{})
        epochs=('operator_epoch','microphone_epoch','interaction_epoch','speech_epoch')
        if (turn.get('source_boot')!=binding['source_boot'] or type(turn.get('sequence')) is not int
                or not last_sequence<turn['sequence']<2**63 or turn.get('lineage_id')!=binding['source_boot']+':'+str(turn['sequence'])
                or not isinstance(turn.get('pcm_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',turn['pcm_sha256'])
                or turn.get('speaker_identity')!='unknown' or turn.get('confirmed') is not False
                or turn.get('working_memory_admitted') is not True or turn.get('expected_answer')!=expected
                or turn.get('expected_answer_matched') is not True or turn.get('echo_reference_matched') is not True
                or type(turn.get('capture_age_ms')) is not int or not 0<=turn['capture_age_ms']<2000
                or not isinstance(turn.get('working_input_ref'),str) or not 1<=len(turn['working_input_ref'])<=128
                or not isinstance(authority,dict) or authority.get('hub_boot_id')!=hub.get('hub_boot_id')
                or set(authority)!=set(Authority.__dataclass_fields__)
                or any(not isinstance(authority.get(name),str) or not 1<=len(authority[name])<=256 for name in ('compute_boot_id','robot_boot_id'))
                or any(type(authority.get(epoch)) is not int or not 0<=authority[epoch]<2**63 for epoch in epochs)
                or not isinstance(operator,list) or len(operator)!=3 or operator[0]!=device['operator_after']['agent_boot_id']
                or any(type(epoch) is not int or not 0<=epoch<2**63 for epoch in operator[1:])
                or operator[1]!=authority['microphone_epoch'] or type(policy.get('epoch')) is not int
                or operator[2]!=policy['epoch'] or policy.get('quiet') is not False or policy.get('privacy_all') is not False
                or authority['microphone_epoch']+1!=device['operator_after']['microphone_epoch']
                or authority['interaction_epoch']<=last_interaction or len(turn['lineage_id'])>128):
            raise ValueError('Admitted unknown voice provenance required')
        last_sequence=turn['sequence'];last_interaction=authority['interaction_epoch']
    first=turns[0]
    return {name:first[name] for name in ('source_boot','sequence','lineage_id','pcm_sha256','working_input_ref','working_authority','working_operator_binding')}


def item(meta,version):
    stamp=meta['created_at'];confirmed=version>0
    return dict(schema_version='1.1',id=meta['item_id'],version=version,namespace=meta['namespace'],
        memory_kind='semantic',epistemic_type='fact',content=CONTENTS[version==2],valid_from=stamp,valid_until=None,
        created_at=stamp,evidence_ids=([meta['item_id']+'-correction'] if version==2 else
            [meta['item_id']+'-voice']+([meta['item_id']+'-owner'] if confirmed else [])),
        counterevidence_ids=[meta['item_id']+'-voice',meta['item_id']+'-owner'] if version==2 else [],
        confidence=None,status='active' if confirmed else 'proposed',author='disposable-fixture-operator',
        model_version=None,prompt_version='voice-fixture-v1',supersedes=None,
        lineage_ids=[meta['voice']['lineage_id']]+([meta['operator_root']] if confirmed else []),claim=None)


def open_fixture(directory,expected_store_id,*,anchor_cleanup=False):
    directory=Path(directory)
    if directory.is_symlink() or not directory.is_dir():raise ValueError('Owned fixture directory required')
    if any(path.name not in FILES or path.is_symlink() or not path.is_file() for path in directory.iterdir()):
        raise ValueError('Unexpected fixture files; do not delete')
    meta,_=read_json(directory/'binding.json',8192)
    if (meta.get('schema')!='voice-fixture-1' or meta.get('directory')!=str(directory.resolve())
            or meta.get('store_id')!=expected_store_id or not isinstance(meta.get('namespace'),str)
            or not re.fullmatch('fixture-voice-[0-9a-f-]{36}',meta['namespace'])
            or not (directory/'memory.sqlite').is_file()):raise ValueError('Exact fixture store binding required')
    cleanup=OwnedCleanup(directory) if anchor_cleanup else None
    lock=directory/'operator.lock';store=None;fd=None
    try:
        fd=os.open('operator.lock' if cleanup else lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,
            **({'dir_fd':cleanup.directory} if cleanup else {}))
        if cleanup:cleanup.files['operator.lock']=os.dup(fd);cleanup.verify(source_name=True)
        current,_=read_json(directory/'binding.json',8192)
        if current!=meta or not (directory/'memory.sqlite').is_file():raise MemoryConflict('Fixture changed during admission')
        store=MemoryStore(directory/'memory.sqlite',[meta['namespace']])
        if store.meta('store_id')!=expected_store_id:raise MemoryConflict('Fixture store replaced')
        if cleanup:cleanup.pin_journals()
        return meta,store,fd,cleanup
    except BaseException:
        if store:store.close()
        if fd is not None:
            if cleanup:cleanup.release_lock(fd)
            else:lock.unlink()
            os.close(fd)
        if cleanup:cleanup.close()
        raise


def projection(store,meta,expected_version):
    value=store.recall();items=value['items']
    expected=[] if expected_version in (0,-1) else [item(meta,expected_version)]
    if items!=expected:raise MemoryConflict('Unexpected fixture readback')
    state=State();state.update_context(dict(memory=value,sensors=[]),0)
    descriptors=[dict(alias=x['id']+':'+str(x['version']),type=x['epistemic_type'],summary=x['content']) for x in expected]
    if state.snapshot(0)['memory']!=descriptors:raise MemoryConflict('State projection mismatch')
    return dict(store_id=value['store_id'],revision=value['revision'],versions=[x['version'] for x in items],
        namespace=meta['namespace'],state_projection_verified=True,content_whitelist_verified=True)


def prepare(directory,hub_path,device_path,binding):
    hub,hub_digest=read_json(hub_path,1048576);device,device_digest=read_json(device_path,1048576)
    voice=voice_provenance(hub,device,binding)
    directory=Path(directory);directory.mkdir(mode=0o700) # exclusive; never adopt an existing store
    identity=uid();store=None
    meta=dict(schema='voice-fixture-1',directory=str(directory.resolve()),namespace='fixture-voice-'+identity,
        item_id='voice-fixture-'+identity,operator_root=identity+'-operator',voice=voice,
        binding=binding,hub_receipt_sha256=hub_digest,device_receipt_sha256=device_digest,
        created_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'))
    try:
        store=MemoryStore(directory/'memory.sqlite',[meta['namespace']]);meta['store_id']=store.meta('store_id')
        store.evidence(meta['item_id']+'-voice',voice['pcm_sha256'],voice['lineage_id'],meta['namespace'],'sensor')
        store.commit(item(meta,0),None)
        private_json(directory/'binding.json',meta)
        return dict(**projection(store,meta,0),proposal_version=0,confirmed=False,speaker_identity='unknown')
    finally:
        if store:store.close()


def operate(action,directory,expected_store_id,expected_version,operator_confirmation=False,*,exclusive_filesystem_cleanup=False):
    if type(expected_version) is not int or expected_version not in (-1,0,1,2):raise ValueError('Explicit fixture CAS version required')
    if action=='cleanup' and exclusive_filesystem_cleanup is not True:raise ValueError('Exclusive private cleanup authority required')
    if action=='cleanup':OwnedCleanup.platform_check()
    meta,store,lock_fd,cleanup=open_fixture(directory,expected_store_id,anchor_cleanup=action=='cleanup')
    try:
        row=store.db.execute('SELECT version FROM active WHERE id=?',(meta['item_id'],)).fetchone()
        if (row[0] if row else -1)!=expected_version:raise MemoryConflict('Fixture CAS changed')
        if action in ('confirm','correct'):
            if operator_confirmation is not True:raise MemoryConflict('Explicit local operator confirmation required')
            required=0 if action=='confirm' else 1
            if expected_version!=required:raise MemoryConflict('Confirmation/correction order')
            if action=='confirm':
                store.evidence(meta['item_id']+'-owner',hashlib.sha256(b'Neutral fixture operator confirmation').hexdigest(),
                    meta['operator_root'],meta['namespace'],'fixture')
            else:
                store.evidence(meta['item_id']+'-correction',hashlib.sha256(b'Neutral fixture operator correction to six').hexdigest(),
                    meta['operator_root'],meta['namespace'],'fixture')
            store.commit(item(meta,required+1),required,confirmed=True)
            return projection(store,meta,required+1)
        if action=='readback':return projection(store,meta,expected_version)
        if action in ('forget','cleanup'):
            if action=='cleanup' and expected_version!=-1:raise MemoryConflict('Forget before file cleanup')
            if action=='forget':
                for root in (meta['voice']['lineage_id'],meta['operator_root']):store.forget_lineage(root)
            if any(store.count(table) for table in ('active','versions','evidence')):raise MemoryConflict('Fixture deletion incomplete')
            for root in (meta['voice']['lineage_id'],meta['operator_root']):
                try:store.evidence('replay-check','a'*64,root,meta['namespace'],'sensor')
                except MemoryConflict:pass
                else:raise MemoryConflict('Forgotten provenance replay accepted')
            result=projection(store,meta,-1);result['forgotten_replay_rejected']=True
            if action=='cleanup':
                store.close();store=None
                result.update(cleanup.remove())
            return result
        raise ValueError('Unknown fixture action')
    finally:
        if store:store.close()
        if lock_fd is not None:
            if cleanup:cleanup.release_lock(lock_fd)
            else:(Path(directory)/'operator.lock').unlink()
            os.close(lock_fd)
        if cleanup:cleanup.close()
