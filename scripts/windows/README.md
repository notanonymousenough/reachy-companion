# Stop Reachy on the PC

Double-click `stop-reachy.cmd` or run it without arguments to STOP the confirmed
Reachy PC inventory. It does not start anything. The CMD launcher keeps an
interactive console summary visible; redirected, SSH and CI calls do not pause.

```powershell
.\scripts\windows\stop-reachy.ps1 -WhatIf
.\scripts\windows\stop-reachy.ps1 -DryRun -InventoryPath C:\private\stop-inventory.local.json
.\scripts\windows\stop-reachy.ps1 -InventoryPath C:\private\stop-inventory.local.json
# Optional existing Python interpreter, per-command and total stop budgets:
.\scripts\windows\stop-reachy.ps1 -PythonExecutable C:\Python312\python.exe -TimeoutSeconds 15 -TotalTimeoutSeconds 90
```

PowerShell 5.1 and existing Python 3.11+ are sufficient. The helper is standalone
stdlib; it does not import the production package, autonomous runtime or models.
Run as the same Windows user as the Reachy launchers; another account has a
different per-user latch and is not an interchangeable stop context.
Default inventory is `%LOCALAPPDATA%\ReachyCompanion\stop-inventory.local.json`.
The tracked example is deliberately empty and is **not** an approved inventory.
Ordinary `start.ps1`/`start-worker.ps1` now delegate only read-only verification
through a pinned external adapter; empty integration settings deny, without a
build/model/container fallback. The previous created-worker enrollment recipe
is preserved in `bootstrap-worker.ps1`, disabled at its top pending separately
reviewed shared-operation integration; see the [clean-PC guide](../../docs/windows-clean-pc.md).
Other existing resources still require audited local enrollment from current
observations before acceptance. A current custom kit inventory is not silently
migrated or overwritten. No real device IDs, credentials or private inventory belong
in Git. Use an operator-controlled local directory/ACL; a manifest is an explicit
ownership assertion checked against current identities, not cryptographic proof
against a malicious same-user/admin writer.

Cloning Git on another PC does not transfer ownership. Do not copy a previous
machine's stop inventory, PID/FILETIME, engine/container IDs, loaded instance IDs,
task XML fingerprints, UNKNOWN receipts or per-user manual-stop marker as new
authority. Collect and review local identities and enroll the new launch. An
existing marker on the target account still blocks START until explicit review;
bootstrap never deletes it. A reviewed immutable image can be transferred as an
independent artifact, but its content identity does not transfer process/container
ownership. See the clean-PC guide for source-build compatibility and preflight
limits; Git contains the recipe, not a previous PC's frozen dependency image.

## Manual stop wins

Plain run first durably creates
`%LOCALAPPDATA%\ReachyCompanion\manual-stop.json`, before inventory reads, Python
launch or resource operations. This also works when Python/inventory is missing.
Existing marker presence, even malformed, blocks startup. Both launcher and
helper use schema 1, kind `reachy_manual_stop`, a UUID `request_id` and ISO UTC
`requested_utc`; the marker has no automatic expiry and is never cleared here.
DryRun/WhatIf perform no latch, config or resource writes.

The repo's `start.ps1`, `start-worker.ps1`, `install-startup.ps1` and
`apply-character.ps1` check this shared per-user marker before writes/launches and
at startup acceptance points. Separate test/deployment launchers must check the
SAME path before every START and acceptance; the runner must install that check
before resuming device tests. A stop request does not wait for or reset another
operation's busy/UNKNOWN slot. In-flight starts can be UNKNOWN: retain their
receipts, reconcile exact resources, and do not call partial results complete.
This is a cooperative launch fence, not a global Windows/Docker exclusion lock.
The public START seam does not implement or prove the private shared STT
OperationSlot protocol. Adapter/selector integration must independently reuse
that exact existing namespace, pinned enrollment and known state, without
initialization, reset or a second lock. Legacy explicit lifecycle helpers are not
an accepted-runtime migration just because they check the manual-stop marker.

The total operation budget defaults to 90 seconds (5–300 configurable), with a
15-second per-command budget (3–60 configurable). Remaining commands use the
smaller remaining budget. Once expired, remaining targets are marked
`not_attempted_deadline`; current timeouts are `timeout_unknown`. No timeout,
denied identity or command error clears the marker or an existing UNKNOWN owner.
Independent targets are attempted within the remaining budget. Exit 0 means only
the approved inventory was stopped/already stopped (or would stop in dry run);
exit 2 means incomplete. It never means all PC software or all GPU memory is free.

## Private inventory contract

Top-level keys are exactly `schema=1`, `owner="reachy-companion"`,
`scope_roots`, `docker`, `processes`, `services`, `tasks`, `models`. Bound 64
targets and 128 KiB JSON; duplicate keys/nonfinite JSON reject. Every target has
`confirmed_reachy_owned=true`, `scope_root` equal to an approved local Windows
directory, and `evidence_sha256` of the runner's reviewed ownership receipt.
Empty/unverified inventory fails closed after setting the manual-stop marker.

| Target | Required exact identity (in addition to ownership fields) |
|---|---|
| Docker | Top-level docker: absolute `executable`, local npipe `endpoint`, actual `engine_id`, `containers` list. Each container: full 64-hex `id`, immutable `image_id`, `command_sha256`, exact `mount_source` + `mount_destination`. |
| Process | `pid`, native integer `creation_filetime`, absolute `executable`, `command_sha256`, `role=launcher` or `lm_studio_dedicated`. LM Studio additionally requires `dedicated_to_reachy=true`. |
| Service | Exact `name`, current `binary_path`, `start_name`. No wildcard/bulk/dependent-service force stop. |
| Scheduled task | Exact `name`, `path`, SHA256 of raw exported XML as UTF-8 in `xml_sha256`. No task removal/disable. |
| Model | `dedicated_to_reachy=true`, loopback `url`, exact `model_key`, loaded `instance_id`, `config_sha256`, `token_env` (null or environment variable NAME only), and `server` process identity (`pid`, `creation_filetime`, `executable`, `command_sha256`). |

`command_sha256` for a process is SHA256 of its exact CIM `CommandLine` UTF-8.
The native pinned process handle must match creation FILETIME and executable,
and the process snapshot must match full-precision .NET `Process.StartTime`
FILETIME plus CIM command/path (CIM `CreationDate` alone may truncate precision).
A launcher command must contain a
path below its reviewed scope root. Termination uses that ORIGINAL process
handle; PID reuse cannot select a new process. LM Studio/shared runtimes are
never selected by process name or port. Process stop is force termination of
that exact approved process; include only disposable/owned Reachy launchers.

For Docker command identity, hash canonical JSON
`{"entrypoint": <Config.Entrypoint>, "cmd": <Config.Cmd>}` with sorted keys,
UTF-8, no ASCII escaping, and separators `,` / `:` without whitespace. The helper's
pure `digest()` implements this. Mounted daemon paths can differ from Windows
host paths; record the exact observed source/destination and audit the mapping
to `scope_root`. Match engine, immutable full ID, image, command and mount before
stop; do not substitute a name, port or ID prefix. AutoRemove containers are
preserved because stopping them would destroy the container. No `rm`, prune,
docker stop-all, data/config deletion or restart-policy change is performed.

Model unload is OPTIONAL and requires the installed LM Studio API to support
[`GET /api/v1/models`](https://lmstudio.ai/docs/developer/rest/list) and
[`POST /api/v1/models/unload`](https://lmstudio.ai/docs/developer/rest/unload).
The runner must verify the installed version/schema first. Require the exact
server process creation/path/command and TCP endpoint owner, model key, instance
ID and canonical hash of that instance's `config`. Recheck before unloading ONLY
that instance; verify absence afterwards. Missing/changed/unsupported observations
preserve the target with an incomplete result, with no CLI/all-model fallback.
Credentials stay in the named environment variable, never inventory/arguments.
Shared LM Studio and nonallowlisted models are intentionally preserved; summary
reports that and always leaves `gpu_freed_verified=false`. Only an explicitly
dedicated, identity-verified LM Studio process may itself be terminated.

## Explicit resume

After the operator has reconciled every timeout/UNKNOWN and reviewed the current
inventory, an explicit manual action may remove ONLY this shared stop marker:

```powershell
$manualStop = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ReachyCompanion\manual-stop.json'
Get-Content -LiteralPath $manualStop
# Only after checking the request and outstanding ownership/UNKNOWN receipts:
Remove-Item -LiteralPath $manualStop
```

This starts nothing. Ordinary autostart must never clear the marker itself.
Microphone, motor policy, quiet/privacy and their ownership epochs are separate;
PC stop does not enable, restore or overwrite those controls on the robot.

Local tests use synthetic Docker/service/model observations and a mocked Win32
kernel. No native PowerShell/Win32 acceptance is claimed on macOS. Runner install
requires syntax/dependency checks, an actual read-only dry run against the reviewed
inventory, and then a coordinated manual-stop acceptance separate from active
hardware tests. Keep the canonical marker contract in those test launchers.
