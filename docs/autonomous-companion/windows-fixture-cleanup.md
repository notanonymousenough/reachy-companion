# Disposable fixture cleanup on local Windows NTFS

This backend extends the existing explicit disposable memory-fixture CLI. It is
not a production-memory cleanup command and does not claim native Windows proof
from POSIX emulation. Real PC acceptance remains pending until the runner's
actual Win32 tests and complete finite workflow pass.

`--allow-disposable-voice-fixture`, exact store UUID/CAS version `-1` after forget,
and `--exclusive-filesystem-cleanup` remain required. The last flag asserts
exclusive authority over SOURCE throughout SQLite use/close, its parent, and the
private quarantine. A cooperative lock or ordinary `chmod` on Windows does not
prove this: the runner must audit inherited operator-only ACLs. Privileged and
uncooperative same-user filesystem writers are outside this contract. The backend
does not modify ACLs or claim adversarial same-UID safety.

Only a plain local fixed NTFS drive is supported. UNC/network/device/ADS paths,
reparse/junction ancestors, multiple-link files, unknown entries, unsupported file
IDs and sharing/access failures reject without a path-unlink fallback. There is
no automatic stale-lock deletion or recovery of a foreign directory/store.

## Native handle lifecycle

Attribute-only handles pin the original directory, ancestors and fixture files
before SQLite opens. They request `FILE_READ_ATTRIBUTES`, share read/write/delete,
and reject reparse points and nonunique file links. They do not request DELETE
while SQLite or the CRT operator lock remains open. Identity uses the native
volume plus 128-bit file ID, never just a current pathname.

After actual SQLite close and CRT-lock close, the backend queries
`FILE_STANDARD_INFO.DeletePending` on ORIGINAL journal handles. SQLite can mark
WAL/SHM for deletion while our attribute handles keep them alive; trying to reopen
such a path may fail. Only those owned pending journal pins are released, then
remaining path identities are revalidated. A new/foreign journal at that name is
not silently adopted. See Microsoft's [FILE_STANDARD_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_standard_info)
and [CreateFileW sharing/delete behavior](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).

The owned source is renamed into a fresh private same-parent quarantine, entries
are detached to unique names, every moved identity is checked, and ALL matching
DELETE handles are acquired before any delete disposition is set. Removal uses
`SetFileInformationByHandle(FileDispositionInfo)` on identity-matched handles,
then closes owned pins/DELETE handles. It never calls path-only unlink to remove
a substituted SQLite file. [Microsoft requires DELETE access for this disposition](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle).
Empty directories also use checked deletion handles. A conflict retains the lock
and/or remaining quarantine, reporting `preserved_cleanup_directory` when detached.
Operational failure after deletion starts can leave some owned files removed and
others preserved; this is not a filesystem transaction. Never rebuild or overwrite
a foreign object from a saved snapshot to hide that failure.

## Runner's finite native check

No microphone, model, service, motor or network session is needed. Use only neutral
synthetic receipts and disposable SQLite data. The sole runner chooses an existing
operator-only local fixed NTFS parent and audits its ACLs; do not use a production
memory directory or a shared/cloud-synced/network workspace.

```powershell
$env:PYTHONPATH = 'src'
$env:REACHY_WINDOWS_CLEANUP_TEST_PARENT = 'C:\PRIVATE_OPERATOR_ONLY_TEST_PARENT'
python -m unittest discover -s tests -p test_windows_fixture_cleanup.py -v
python -m unittest discover -s tests -p test_voice_memory_acceptance.py -v
```

All FOUR `NativeWindowsCleanupTests` cases must execute and pass on actual Windows,
with no skip of those cases. On Windows a missing parent environment is an error,
not native green. The scenarios exercise real SQLite close/delete sharing,
post-close foreign DB/directory replacement, post-detach foreign replacement, and
DELETE-handle identity mismatch. Replacement injection happens AFTER SQLite/CRT
close so Win32 sharing refusal does not substitute for the intended identity test.
Capture aggregate test counts/platform/backend/error types only, with no raw audio,
real transcript, production config values or credentials.

The unchanged fixture command is:

```text
voice_memory_acceptance.py cleanup --exclusive-filesystem-cleanup --allow-disposable-voice-fixture --directory <owned-fixture> --output <fresh-receipt-OUTSIDE-fixture> --expected-store-id <exact-UUID> --expected-version -1
```

Receipts remain outside the disposable directory. Success reports backend
`win32_local_ntfs_file_id_delete_handle`, `owned_files_removed: true`, contract
`exclusive_private_quarantine`, and `adversarial_same_uid_race_safe: false`.
`live_voice_verified` and `speaker_identity_confirmed` remain false in this trusted
runner fixture; native cleanup success cannot turn synthetic/unfinished voice
receipts into actual live-voice acceptance.

On failure preserve unknown/foreign data and the reported quarantine/lock. Inspect
actual identities/ownership before manual recovery; no blanket recursive deletion,
stale-lock removal, pathname fallback or ACL weakening. An original pre-cleanup
snapshot never authorizes overwriting newer data. The code performs no deployment
or automatic retry against a failed native filesystem capability.

Local source validation: ten POSIX-emulated/Win32-ABI tests passed; four actual
Windows cases skipped on Mac, explicitly NOT native proof. Existing seven POSIX
memory-fixture cases passed. Emulator coverage includes original-handle journal
pending deletion and complete identity validation before deletion, plus foreign
source/quarantine substitutions. Real Win32/NTFS behavior remains a runner gate.
