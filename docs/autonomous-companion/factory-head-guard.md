# Finite factory head guard: capability checkpoint

This checkpoint **does not admit a physical head movement**. It contains a
protocol core, temporary transport fence, read-only sampler using an already-open
factory controller, and a reproducible native safety patch. It is not a production
rollout, factory startup adapter, scoped motion implementation, or hardware proof.
No SDK/controller constructor or second UART is created by these Python modules.

## Existing 1.5.6 limitation

The pinned native `async_read_raw_bytes` PyO3 binding retains the GIL, while the
native call performs `blocking_send` before its one-second response timeout.
`DisableTorque` shares this ordinary queue. A Python thread watchdog, response
timeout, cached motor mode, HTTP assembly timestamp and disappearance of a move
UUID cannot prove independent physical stop within 500ms.

Primary source pins used by `native/factory-head-v156/prepare.py`:

| File at upstream tag v1.5.6 | SHA256 |
| --- | --- |
| `src/control_loop.rs` | `62817fbc0fd13018ba4bfc5628e1a379a822888fcbdd0792dcbe3ff2bf414df4` |
| `src/bindings.rs` | `204106cf20178b518d1bffffe76fea34b2e698a5a8fc8ac767f713e2d611e94c` |
| `src/controller.rs` | `bb618f2743e638944c65ef6839c5484319f1be2c6b74fc4d342c783a722a8843` |

Sources: [control loop](https://github.com/pollen-robotics/reachy-mini-motor-controller/blob/v1.5.6/src/control_loop.rs),
[bindings](https://github.com/pollen-robotics/reachy-mini-motor-controller/blob/v1.5.6/src/bindings.rs),
[controller](https://github.com/pollen-robotics/reachy-mini-motor-controller/blob/v1.5.6/src/controller.rs),
[XL330 decoder](https://github.com/pollen-robotics/rustypot/blob/v1.4.2/src/servo/dynamixel/xl330.rs).

## Prepared native build

Run in an isolated checkout/build directory, with Python, Rust and the original
v1.5.6 source/lockfile available. These commands build source; they do not install
or start a controller:

```sh
python native/factory-head-v156/prepare.py --source /absolute/source-v1.5.6 --output /absolute/new-disposable-build
PYO3_PYTHON=/absolute/python cargo test --manifest-path /absolute/new-disposable-build/Cargo.toml --lib
```

The generator checks all three hashes before writing, leaves the input intact,
rejects existing output directories, and versions the output
`1.5.6-finite-head.1`. Keep the original upstream license and lockfile with the
build. Record the compiler, complete resolved dependency lockfile, build platform
and artifact hash before review; a Mac build is not a Reachy binary.

The source patch adds a process-local, single-use native owner latch with an
absolute 4–12s deadline and policy TTL at most 300ms. `finite_arm` rejects occupied
actual native execution; `finite_refresh` cannot revive expiry or extend the
absolute deadline. `finite_revoke` checks the exact opaque owner and never waits
for space in the ordinary command queue. Arming permanently seals ordinary
mutators at enqueue **and execution**, including pre-arm pending commands. Raw
read bindings release the GIL. Finite reads use one serial attempt, without the
legacy 20ms retry sleep. The existing serial-owner loop checks the latch and drops
pending commands on withdrawal, then attempts torque-off outside that queue.
Finite close also drops pending commands instead of executing them.

**Limits of this build:** it exposes no owned motion/enable API, all-nine measured
stop proof, native snapshot sequence, bounded-I/O attestation, or hardware
acceptance. Torque-off write success alone is not a proof. A serial library call
or host scheduling stall can still exceed its nominal timeout. The revoke latch
is independent of Python; its physical effect still waits for the current native
serial operation to return. Do not infer a hard 500ms guarantee from compilation
or the five latch tests. The old unarmed controller path remains the upstream
behavior and is not the finite test mode.

## Python capability stage

`FiniteHeadGuard` accepts only a reviewed adapter declaring every required
capability. `installed_v156_admission()` deliberately reports false capabilities;
passing it to the core fails before issuing a command. Boolean capabilities and
adapter receipts are trusted integration inputs, not signed hardware attestation.

The plan is relative to a fresh measured, disabled, possibly nonneutral baseline:
lift at most 5mm, yaw/pitch delta at most 3°, duration 1–2s, preserve X/Y/roll,
body yaw and both antennas, then return to that same baseline and disable. No
unconditional factory wake or neutral-pose jump. Admission rechecks the exact
Agent boot, policy epoch/owner and microphone epoch; stale or changed policy
withdraws permanently. A caller timeout cannot release an actual occupied slot.
ACK does not advance the movement phase without fresh held-pose/torque evidence.
Cleanup needs drained slots and fresh stationary all-nine torque-off observations
within 500ms of withdrawal, sampled after withdrawal.

`ExistingFactorySampler` verifies the actual motor-name/ID/model map through the
already-open controller, then reads positions at register 132 and torque at 64
for IDs 10–18. It uses the native signed XL330 decoder. Source age starts BEFORE
first queue admission and includes every read and mutable FK computation. Reads
exceeding 100ms are rejected; this elapsed budget does not interrupt native I/O.
A native exception retains the occupied slot as unknown, without retry/reset.
The FK function must share the SAME lock used by the actual factory update;
contended FK is rejected. Samples are sequential read-group observations, not a
simultaneous hardware snapshot. An unbounded FK solver is not accepted by merely
stamping its completion time.

`FactoryReadOnlyASGI` denies every POST, unknown GET and all WebSockets before
routing or reading bodies. The fresh backend class fence permits only exact
reviewed read-command types, denies RTC including its JSON-RPC app relay, and
suppresses idle-reset callbacks. Neither fence alone certifies every producer.
Factory media, tracking/wobbler, startup apps, preload and internal target writers
must be disabled/fenced before listeners start in a fresh pinned process. Never
adopt a running daemon with pending producers or unseal this process in place.

## Remaining admission work and runner evidence

1. Add owned native enable/goal operations carrying this single-use owner,
   generation and deadline; revalidate at each serial mutation admission. Enable
   must pin fresh measured positions BEFORE torque and reject an enabled/unknown
   baseline. Audit all legacy/native/raw writer bypasses.
2. Add native sample/stop status with source BEGIN/END times, increasing sequence,
   all-nine fresh torque values, actual occupied slots and unknown outcomes.
   Check revoke between bounded serial operations; test blocked serial I/O and
   late replies, not just queue saturation. No automatic rearm or owner transfer.
3. Wire a version-pinned finite factory startup adapter/private operator-only IPC,
   all producer fences, shared bounded FK and exact Agent owner/epoch receipt.
   No public REST fallback for an owner-scoped stop. A changed human policy must
   remain authoritative and must not be restored from an older saved snapshot.
4. Review the exact source/build hash, then the sole hardware runner may test the
   native capability with motors verified disabled. First prove queue/retry/GIL,
   expiry, foreign owner and delayed outcome behavior. Physical motion admission
   remains false until measured stop/hold proof and every fence are verified.
5. Only then run one finite relative lift/turn, return to measured baseline,
   disable, and record actual pose and all-nine torque/slot evidence. Replace the
   finite process with the verified original factory only after measured cleanup;
   if stop is unknown, keep admission closed and report the actual unresolved
   state. Process kill and a restarted status page are not torque-off evidence.

Local validation at this checkpoint: 21 Python protocol/fence/sampler tests and
five Rust latch tests in the generated full native crate. No hardware session,
installation, physical head movement or acoustic acceptance is implied.
