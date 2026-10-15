# Fresh factory no-output preflight: current source sequence

This is the sole runner's invocation contract for a separately reviewed private Phase B harness. It does not add a harness, deploy a service, admit motion or replace the production entry's genuine capability proof. Read the [native checkpoint](factory-head-guard.md) first. Production `factory_head_entry` requires real capability evidence; do not fabricate a true capability file to bootstrap these measurements.

## Prerequisites before stopping anything

1. Rebuild the distinct `1.5.6+finite.head.4` target wheel from the exact upstream1.5.6 pins, current `prepare.py`, `stage2.py`, `stage4.py`, `finite_owner.rs`, `finite_engine.rs`, `finite_startup.rs` and the reviewed lock. Record source pin, compiler, platform, wheel and extracted `.so` hashes. A version string or the old `.3` static probe is insufficient.
2. In an isolated process, load only that candidate extension, verify the eleven API methods and absence of relative arm/refresh, then measure the Linux Python/native/Python `CLOCK_MONOTONIC` static bracket without constructing a controller. It must stay bounded and ordered as specified by `verify_native_clock`.
3. Read actual installed SDK1.11 factory source pins and the additional analytical/geometry hashes. Inspect the actual native Rust kinematics1.0.3 package layout, imported class, compiled-module path and artifact hash. Do not substitute the Python package's `__init__.py` hash for its native `.so` hash or assume that matching versions prove matching code. Preserve private hardware/config hashes without publishing values.
4. Refresh the actual unit InvocationID/cgroup and every relevant PID/start identity, mapped module pathname/inode/disk hash, and all serial FDs. Unit `MainPID` can be a shell; bind the actual UART child and audit the entire cgroup. A previous inventory is not a current owner grant. Recheck Agent boot/policy/mic owner/epochs and current microphone/capture state without changing them.
5. Establish durable exact-generation intent, a scoped restart fence and an independent finite timer before stopping the factory. The timer must preserve unknown physical cleanup and foreign/newer state; it must not blindly start a factory over an unresolved serial owner. Stop the old entire cgroup, verify it is terminal and the UART is owner-free. Never open a second controller beside it.

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

The constructor performs only its fixed read profile, with no actuator-write instructions or automatic reboot. Its receipt is diagnostic; startup `complete=true` does not supply current sensor or stop evidence. Convert native byte vectors to lists only when writing numeric JSON metadata. The profile is specific to the reviewed wireless motors/voltage/temperature bounds; a mismatch rejects rather than silently changing hardware limits or retrying construction.

## Read/FK and scoped stop measurements

Require `ready_factory_backend(prepared)` against the actual current in-memory objects. Record process/runtime/source/launch bindings, constructor read receipt, and real native method/producer identities. Readiness and cached `/api/motors/status` do not establish physical torque-off or sample freshness.

Use the actual `backend.c` and `backend.head_kinematics` under `prepared['kinematics_lock']`. `ExistingFactorySampler` verifies models through that same controller and then reads all-nine positions/torque, with source BEGIN before queue admission through FK return. A reviewed harness may instrument the existing read/FK calls for numeric BEGIN/RETURN/duration and actual completion without changing their slot/quarantine semantics. Obtain the planned finite sample count; reject a group over100ms, lock contention, invalid FK residual, nonfinite/upside-down result, native/model quarantine, wrong motor map or any nonzero torque. Never construct an independent model to make FK appear available or relabel a completion timestamp as source BEGIN.

To measure the native owner/stop latch without granting a head trajectory, the harness uses the low-level scoped primitives directly, not a `FiniteHeadGuard` made admissible by invented capability booleans. Verify current exact operator bindings and withdrawal rules; preserve the current motion/microphone policy. Submit one opaque owner with original Linux monotonic absolute deadlines via `finite_arm_at`; retain the original4–12s end and request-BEGIN-anchored policy TTL≤300ms. The measured source, not a delayed arrival time, supplies those deadlines. No `finite_enable`, `finite_goals`, ordinary torque/mode/PID/raw packet writes or trajectory calls belong to this no-output phase.

Observe queued/native execution outcomes truthfully. A busy/unknown read or receipt stays occupied until actual completion; a timed-out Python wait cannot free it. Then revoke or allow the original finite lease to expire, and measure owner-scoped stop behavior. Torque-OFF cleanup writes are permitted and must be counted separately from read transactions and from forbidden torque-enable/goal writes. Require advancing native status, fresh all-nine torque-off, at least three stationary observations spanning100ms, drained pending/executing slots and completion within500ms of the ORIGINAL native withdrawal anchor. Busy/repeated status does not advance measured hold time. A delayed stop call or late recovery cannot move that anchor or retroactively pass the500ms result.

The Python attempt/elapsed bounds are fail-closed validation after actual native calls return. They do not interrupt a stalled serial or Rust kinematics operation. Actual target bounded-I/O/FK and watchdog behavior therefore remain measurements; neither compilation nor these checks set a capability true.

## Cleanup and next gate

Keep the finite process sealed. Restore no old mic, policy, volume or target pose. Bind every cleanup action to the exact owned launch generation, PID/start/native artifact, config and owner nonce. Before handback, verify actual physical cleanup, close/reap the owned child, prove UART owner-free, and remove only the matching runtime restart fence. Restore the original factory only if those exact conditions and current ownership still hold. Preserve foreign/newer state. Unknown physical stop or I/O leaves admission closed and the factory fenced; process kill/restart is not physical torque-off proof.

Only after independent review of the completed target receipt can the real capability proof for `factory_head_entry` be assembled. It includes both motor-controller and kinematics artifact hashes. The subsequent finite movement additionally needs fresh explicitly granted motion authority, exact original deadlines, measured nonneutral baseline, bounded IK, held-pose/torque evidence and verified return/disable. No-output preflight is not that motion acceptance.

Other stage dependencies remain separate: the finite closed-turn voice/stop/timing receipts do not by themselves satisfy the canonical `voice-working-1` two-turn memory receipt in [context-live.md](context-live.md). Camera admission still needs truthful source age/latency evidence. Follow [implementation-plan.md](implementation-plan.md) gates; do not promote those stages from this native source work.
