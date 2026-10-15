# Fresh factory no-output preflight: current source sequence

This is the sole runner's invocation contract for a separately reviewed private Phase B harness. It does not add a harness, deploy a service, admit motion or replace the production entry's genuine capability proof. Read the [native checkpoint](factory-head-guard.md) first. Production `factory_head_entry` requires real capability evidence; do not fabricate a true capability file to bootstrap these measurements.

## Prerequisites before stopping anything

1. Rebuild the distinct `1.5.6+finite.head.4` target wheel from the exact upstream1.5.6 pins, current `prepare.py`, `stage2.py`, `stage4.py`, `finite_owner.rs`, `finite_engine.rs`, `finite_startup.rs` and the reviewed lock. Record source pin, compiler, platform, wheel and extracted `.so` hashes. A version string or the old `.3` static probe is insufficient.
2. In an isolated process, load only that candidate extension, verify the eleven API methods and absence of relative arm/refresh, then measure the Linux Python/native/Python `CLOCK_MONOTONIC` static bracket without constructing a controller. It must stay bounded and ordered as specified by `verify_native_clock`.
3. Read actual installed SDK1.11 factory source pins and the additional analytical/geometry hashes. Inspect the actual native Rust kinematics1.0.3 package layout, imported class, compiled-module path and artifact hash. Do not substitute the Python package's `__init__.py` hash for its native `.so` hash or assume that matching versions prove matching code. Preserve private hardware/config hashes without publishing values.
4. Refresh the actual unit InvocationID/cgroup and every relevant PID/start identity, mapped module pathname/inode/disk hash, and all serial FDs. Unit `MainPID` can be a shell; bind the actual UART child and audit the entire cgroup. A previous inventory is not a current owner grant. Recheck Agent boot/policy/mic owner/epochs and current microphone/capture state without changing them.
5. Before any freeze or kill, establish the matching runtime `Restart=no` drop-in, a start-blocking fence and an independently armed finite recovery timer outside both factory and candidate cgroups. Freeze their paths/device/inode/hashes, nonce, timer InvocationID, entry and definition hashes, original Linux monotonic deadline and reviewed recovery semantics. The timer may terminate only the exact owned candidate generation and must keep the factory fenced on unknown results. It must never start a factory, restore an operator snapshot or resolve unknown physical state by restarting.
6. Audit effective unit/drop-ins, `ExecStop`, `ExecStopPost`, `OnFailure`, `OnSuccess`, `RestartForceExitStatus`, action/watchdog settings, dependencies/triggers and external restart sources. Unknown or nonempty hooks/sources deny this plan. In particular, `Restart=no` alone is insufficient: systemd can run exit hooks after unexpected termination and forced-restart settings override normal restart policy. See the [systemd service specification](https://raw.githubusercontent.com/systemd/systemd/v257/man/systemd.service.xml).
7. Do not reuse `native_actor_rollback.sh` or the legacy `native_actor_probe.py` supervisor for Phase B. Their ordinary stop path can run legacy `goto_sleep`. No ordinary `systemctl stop`, SIGTERM or old factory `Daemon.stop` is admitted. The reviewed private executor must retain the exact domain cgroup v2 directory FD, verify device/inode, InvocationID, every PID/start tick and the actual UART child, and exclude foreign descendants/migration/restart authorities. Only a fresh freeze intent followed by observed `cgroup.events frozen=1` can precede an exact retained-cgroup `cgroup.kill` intent. Freeze is asynchronous; `cgroup.kill` uses SIGKILL for the group subtree. See the [kernel cgroup v2 documentation](https://docs.kernel.org/admin-guide/cgroup-v2.html). Do not re-resolve a unit name or PID to execute an old intent.
8. Kernel termination proves no physical torque-off. Confirm the entire original generation has exited, its pinned cgroup is unpopulated, no newer unit generation appeared and the exact UART device has no owners before candidate admission. Never open a second controller beside an old or unknown owner.

## Pure plan and admission contract

`reachy_companion.autonomous.factory_head_handoff` adds metadata validation only; it never reads private files, opens UART, imports a candidate extension, controls units or executes returned intents. The runner must independently implement and review the retained-FD executor and finite recovery before invoking it. A hash or a `True` metadata field is not hardware attestation or proof that no other privileged actor can mutate a cgroup. Exclusive operation authority and complete source/runtime inventory remain trusted runner prerequisites.

Use `freeze_plan(spec, expected_sha256=independently_reviewed_digest)` with kind `factory-head-phase-b-nooutput-1`. Freeze a canonical strict JSON DTO: original clock proof and lifetime (at most30s), nonce, full factory scope, stat-only UART identity, operator epochs/state, fence, recovery and candidate profile. Scope includes unit/MainPID and actual UART child separately, InvocationID, cgroup device/inode/type, complete PID/start inventory, executable/native mappings and config identities, and hook-audit hash. Candidate binds exact `.4` and kinematics1.0.3 native artifacts plus source/analytical/assets pins; version strings alone do not suffice. `READ_ONLY_ARGS` and `SAFE_HOOKS` are closed typed profiles. See the synthetic DTOs in `tests/test_factory_head_handoff.py`; all IDs and paths there are fixtures. Keep operational IDs/settings and secret configuration values outside published source.

Call `authorize_takeover(plan, observation, now_ns=..., action='freeze')`, then independently observe actual frozen state and call it again with `action='kill'`. Every observation must retain its original source BEGIN, finish within100ms, match the original Linux monotonic domain and unchanged operator/fence/recovery/UART/config identities, and precede recovery due time. The returned intent expires at the earliest of original BEGIN+100ms, recovery due or plan deadline. It carries exact cgroup pin and members, never a shell command. The executor must reject expired intents and any identity change immediately before acting; Python metadata checks alone cannot close that execution boundary. Unknown hooks, ownership, inventory or clock deny admission.

`authorize_candidate` requires exact original exited members, unchanged original config, no current MainPID/new InvocationID, original cgroup empty or gone and UART owner-free. Its only intent is `prepare_factory_app_unarmed`: arm, enable, goals, automatic restart and operator restore are false. A declined or failed decision does not authorize cleanup of foreign state.

The Phase B DTO maps `motion_owner` from the actual Agent top-level `motion_policy_owner_id`, not from a guessed nested policy field. A truthful `null` owner is valid only with the existing capture/listen/motor-off baseline. Freeze that exact null: a new owner, Agent boot or policy/microphone epoch denies subsequent admission. Do not invent an owner or change policy to make planning pass. This nullable no-output binding does not change the movement guard or grant motion.

## Fresh process preparation

Load the process-local candidate motor-controller package before importing the factory Robot module. The Robot module's `ReachyMiniPyControlLoop` must be exactly the candidate class. A stale already-imported legacy class rejects before lifespan. Never execute the installed console main, which has wireless/audio configuration hooks.

The reviewed harness can invoke the existing preparation with its real imported objects:

```python
prepared = prepare_factory_app(
    factory_main, Backend, RobotBackend, Daemon,
    {name: getattr(abstract_module, name)
     for name in ('GetStateCmd', 'GetMotorModeCmd', 'GetVersionCmd')},
    native_module=candidate_extension,
    native_sha256=reviewed_target_motor_sha256,
    args=actual_factory_args, numpy=np,
    analytical_class=analytical_module.AnalyticalKinematics,
    kinematics_module=actual_native_kinematics_extension,
    kinematics_sha256=reviewed_target_kinematics_sha256,
)
verify_native_clock(candidate_extension.ReachyMiniPyControlLoop)
```

This function checks source/class/artifact identities and absence of existing factory/model instances before patching. It irreversibly chooses native readonly startup, installs bounded shared analytical methods, clears only the in-memory PID-config path, and seals HTTP/WS/SDK/RTC/internal producers. No saved configuration or installed file is rewritten. Only the returned sealed ASGI app may enter the factory's normal lifespan, which constructs the one controller and one model. No separate `ReachyMini`, native controller or kinematics object is allowed.

Before `create_app` or lifespan, `prepare_factory_app` now fences the vendor
pre-controller reflash path through `factory_head_startup`. The original installed
daemon whole-file pin remains mandatory. Independently pin the exact public
`Daemon._setup_backend` AST source segment SHA256
`206f03c2cad77a82faa2be11d3a5b8db0a3fca1d7418bc1ef7404c609bdb370e`,
verify the runtime function's compiled code/defaults/globals and its exact
`RobotBackend` alias. The equivalent public method is in the [official daemon
source](https://raw.githubusercontent.com/pollen-robotics/reachy_mini/main/src/reachy_mini/daemon/daemon.py)
(whole public file SHA256
`646ddfc085bb035ff57d251cb9b9e1cfb90142b9491a597db849dd467ec0f98f`).
Method equality does not assert equality of the whole public and installed files.
Unknown source/signature/runtime globals reject before native preparation.

Supply an explicit canonical `/dev/...` `args.serialport` bound to the runner's
frozen UART device; no `auto`, null or port discovery is admitted. The process-local
setup wrapper validates the readonly real-backend profile, forces
`reflash_motors_on_start=False` for omitted/positional/keyword flags, and traps
both daemon and tools-module raw reflash globals before lifespan. It admits one
setup attempt only; an exception or unknown constructor result cannot authorize
a retry or a second controller. Readiness checks retain these exact fence bindings.
No installed source or saved config is modified. This closes one concrete startup
write path, not all daemon/lifespan paths: `all_mutation_paths_fenced` and hardware
acceptance remain false. The runner must still independently review the exact
installed startup/producer/network closure; do not infer new listeners, mDNS
suppression or whole-lifespan safety from this wrapper.

The common no-output argument profile also sets process-local
`wireless_version=False` BEFORE `create_app`/Daemon construction, and the startup
wrapper requires exact false before entering the vendor setup method. This closes
the wireless IP-getter branch and `BMI088(i2c_bus=4)` construction (which
`no_media=True` alone does not suppress). Exact pinned daemon/robot/abstract/main
review found no alternate motor/native profile selected by this flag when the
explicit frozen serial path is used and sim/mockup are false; the only serial
selection branch is `serialport == "auto"`, already forbidden. Native constructor
parameters, motor IDs and readonly all-nine voltage/read limits are unchanged.
This is a finite-process peripheral fence, not a claim that the physical robot
is a Lite or permission to rewrite its installed SKU/configuration. It does not
suppress the independent hardware-ID getter or unconditional mDNS registration;
those still need the runner's separately reviewed candidate closure. No new
all-paths/zero-I/O/hardware capability follows from this flag.

The constructor performs only its fixed read profile, with no actuator-write instructions or automatic reboot. Its receipt is diagnostic; startup `complete=true` does not supply current sensor or stop evidence. Convert native byte vectors to lists only when writing numeric JSON metadata. The profile is specific to the reviewed wireless motors/voltage/temperature bounds; a mismatch rejects rather than silently changing hardware limits or retrying construction.

## Unarmed read/FK measurements

Require `ready_factory_backend(prepared)` against the actual current in-memory objects. Record process/runtime/source/launch bindings, constructor read receipt, and real native method/producer identities. Readiness and cached `/api/motors/status` do not establish physical torque-off or sample freshness.

Use the actual `backend.c` and `backend.head_kinematics` under `prepared['kinematics_lock']`. `ExistingFactorySampler` verifies models through that same controller and then reads all-nine positions/torque, with source BEGIN before queue admission through FK return. A reviewed harness may instrument the existing read/FK calls for numeric BEGIN/RETURN/duration and actual completion without changing their slot/quarantine semantics. Obtain the planned finite sample count; reject a group over100ms, lock contention, invalid FK residual, nonfinite/upside-down result, native/model quarantine, wrong motor map or any nonzero torque. Never construct an independent model to make FK appear available or relabel a completion timestamp as source BEGIN.

Phase B forbids `finite_arm_at`, refresh, torque-enable, torque-OFF writes, goals, ordinary mode/PID/raw writes, reboot and sleep trajectories. Record zero actual counts for every `FORBIDDEN` operation plus a trace hash; readonly all-nine torque observations are evidence, not cleanup writes. Never fabricate capability booleans or arm an owner to obtain a stop receipt in this phase. An unknown read remains occupied until its actual completion; a Python wait timeout cannot free it.

`assess_readonly` accepts only the planned3–16 actual samples, the completed readonly constructor receipt with exactly63 reads, nine typed health values and nine torque-off values, all-nine finite positions and torque-off for each source-BEGIN/FK-return span≤100ms, bounded residual≤0.002rad, upright finite FK, no quarantine/busy/unknown native work, mapped candidate/kinematics artifacts and known exact candidate exit. Record sample runtime identities, original monotonic timestamps and exit completion; finish with a fresh inventory proving all owned members exited and UART owner-free. Cached status and static API checks cannot replace these receipts.

The Python attempt/elapsed bounds are fail-closed validation after actual native calls return. They do not interrupt a stalled serial or Rust kinematics operation. Actual target bounded-I/O/FK and watchdog behavior therefore remain measurements; neither compilation nor these checks set a capability true.

## Cleanup and next gate

Keep the candidate sealed. Bind recovery and exit checks to the exact owned generation, PID/start/native/config identities and nonce. Do not replay microphone, policy, volume or pose snapshots. Unknown exit, I/O, physical state, foreign ownership or changed human epochs leaves admission closed and the factory fenced, without automatic restart.

Even successful `assess_readonly` returns `keep_fence=true`, `automatic_restart=false`, `restore_operator=false`, `head_hardware_acceptance=false` and `movement_admission=false`. Only `eligible_for_separate_handback_review` becomes true. Removing the exact owned fence and starting the original factory requires a separate fresh ownership/policy review and review of its startup behavior: a legacy start may wake motors. This helper provides no restore/start action.

Native owner-latch/withdrawal/stop measurements belong to a separately authorized later gate, including actual bounded stop and all-nine torque-off evidence from the original withdrawal anchor. Readonly Phase B cannot establish those capabilities. Only the full independently reviewed target evidence can supply genuine `factory_head_entry` capability proof for both motor-controller and kinematics artifacts. Subsequent movement additionally needs fresh motion authority, original deadlines, a measured nonneutral baseline, bounded IK, held-pose/torque evidence and verified return/disable.

Other stage dependencies remain separate: the finite closed-turn voice/stop/timing receipts do not by themselves satisfy the canonical `voice-working-1` two-turn memory receipt in [context-live.md](context-live.md). Camera admission still needs truthful source age/latency evidence. Follow [implementation-plan.md](implementation-plan.md) gates; do not promote those stages from this native source work.
