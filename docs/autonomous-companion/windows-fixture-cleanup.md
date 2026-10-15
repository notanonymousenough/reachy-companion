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

Windows cleanup uses FILE-FIRST transfer. Retain every original file pin while
moving individual files through identity-checked DELETE-capable handles into
unique tokens under the retained quarantine directory handle. `FileRenameInfo`
uses the verified original source handle, `RootDirectory=NULL`, a canonical local
absolute UTF-16 destination and no replacement. Each unique token is constructed
under the retained quarantine root; reject relative/CWD, UNC/device/ADS, dot/dotdot
and cross-volume forms. Recheck the target pathname's FileID against that retained
root before calling the API, retaining all existing ancestor/root pins. Source
is never renamed through a pathname. Before/after move inventory checks below
remain required under the existing exclusive parent/quarantine authority.
Before and after EVERY move, verify the original source directory identity,
exact remaining source names, exact quarantine names and ALL previously moved
token identities. A partial transfer, extra entry or substituted token fails
before any delete disposition; preserve every remaining location without rollback.

Only after the source is empty, acquire/verify a DELETE-capable handle against
the ORIGINAL pinned directory ID and rename that empty directory into quarantine
through that handle. Check its post-detach identity and emptiness. Do not close
child pins to make an ancestor rename succeed: Microsoft's [rename rules](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information#remarks)
describe the restriction on directories containing open child files. The finite
native handle matrix supports file-first ordering; it is not complete workflow
acceptance. A separate two-case actual ABI probe found relative destination plus
non-NULL root rejected with WinError87 while NULL root plus absolute destination
succeeded, with the same class3/layout/access and preserved source FileID. That
is why this backend uses the documented absolute form of
[FILE_RENAME_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info).
It is one explicit backend contract, not a retry/fallback after an API failure.
Absolute destination resolution relies on the SAME exclusive parent/quarantine
contract and retained-ID checks; it does not claim atomic handle-relative target
resolution or protection against uncooperative same-user/privileged writers.

Acquire and verify the COMPLETE final DELETE handle set (every token, detached
original directory and quarantine) BEFORE the first delete disposition. Recheck
all transfer identities and directory contents after acquiring the entire set.
Removal uses `SetFileInformationByHandle(FileDispositionInfo)` on those owned
handles, then closes file handles/pins before deleting the empty directories.
There is no pathname unlink or closed-pin workaround. [Microsoft requires DELETE
access](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle)
for disposition; requesting DELETE for a rename is not authorization to delete
early. A conflict retains remaining locations and reports
`preserved_cleanup_directory`. All owned close attempts run even if one fails.

`original_path_reused` requires confirmed original detach and a newly observed
DISTINCT FileID. Only a specific not-found result means absence; permission or
unknown lookup fails. A later distinct source directory is never adopted or
removed. Precommit verification/transfer faults make zero delete calls.
Operational failure AFTER deletion starts can leave some owned files removed and
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

All THIRTEEN `NativeWindowsCleanupTests` cases must execute and pass on actual Windows,
with no skip of those cases. On Windows a missing parent environment is an error,
not native green. The scenarios exercise real SQLite close/delete sharing,
ordinary-operation mutex/process exclusion and release faults, file-first source
and prior-token identity checks, partial transfer, empty-directory rebinding before
and after detach, full final DELETE-set acquisition, unknown source lookup and
truthful distinct source reuse. Two focused cases additionally require empty-directory
source-handle detach with FileID preservation and an occupied sentinel which
refuses replacement while preserving both files' IDs and bytes. Directory replacement injection happens only once
the source is EMPTY with child pins already following their files to quarantine;
an earlier OS refusal cannot substitute for the intended identity test. Every
precommit foreign/fault scenario asserts zero delete calls plus preserved bytes
and original objects, not just an expected error or token count.
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

Local targeted source validation: eighteen POSIX-emulated/Win32-ABI tests
passed; thirteen native Windows cases skipped on Mac, explicitly NOT native proof.
The emulator models denial of ancestor-directory rename with child handles and
original-handle journal delete-pending state. Complete real Win32/NTFS behavior
and the final neutral fixture workflow remain independent runner gates.
