# Finite factory head guard: capability checkpoint

This checkpoint **does not admit a physical head movement**. It contains a
protocol core, temporary transport fence, read-only sampler using an already-open
factory controller, and a reproducible native safety patch. It is not a production
rollout, factory startup adapter, complete scheduler/private-IPC implementation, or hardware proof.
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
`1.5.6+finite.head.2`. Keep the original upstream license and lockfile with the
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
pending commands on withdrawal, then attempts torque-off outside that queue BEFORE bounded purge (at most 100 entries per pass). New ordinary reads after withdrawal are rejected; finite enqueues use nonblocking try_send.
Finite close also drops pending commands instead of executing them.

Native `.2` adds owned `finite_enable` and `finite_goals` with exact owner,
generation zero and unique action IDs. Up to 256 actual receipt slots are retained
for this single-use session; a timed-out caller cannot reuse its action. Actual
receipts remain pending until execution returns or the queued command is discarded.
Enable requires measured all-nine disabled torque and position mode 3, pins the
measured joint positions BEFORE torque, and rechecks the owner between I/O. Goals
preserve body/antennas to 0.0001rad and bound Stewart deltas to 0.06rad; these native
joint bounds supplement the Cartesian guard and bounded IK, not replace them.

Stop measurements read actual positions and all-nine torque with source BEGIN and
END times, increasing native sequence, group age at most 100ms, and at least three
stationary joint samples spanning 100ms. The status returns withdrawn/busy/known,
source age, measured positions/torque and sequence. `stop_known` requires a fresh
sample, drained native action/execution slots and completion within 500ms of the
ORIGINAL native policy expiry/revoke. A delayed revoke request does not move an
already-expired policy clock forward. It is deliberately false after that deadline;
late physical recovery cannot retrospectively pass the SLA.

**Limits of this build:** no target ARM artifact, complete factory scheduler or
private IPC, bounded-I/O hardware attestation, or hardware acceptance. A serial
library call or host scheduling stall can exceed its nominal timeout. The native
latch runs independently of Python and polls at 5ms even with a slow read interval;
its physical effect waits for the current serial operation to return. Do not infer
a hard 500ms guarantee from compilation or synthetic I/O tests. The old unarmed
path remains upstream behavior and is not the finite test mode.

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
Actual admission also rechecks measured sample age after IK; a fresh Agent poll cannot refresh an old pose. Unknown samples invalidate prior stop proof. Cleanup needs drained slots and fresh stationary all-nine torque-off observations
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

## Prepared factory bridge and process wiring

`NativeHeadBridge` arms the remaining finite budgets, refreshes only from actual
fresh Agent observations, submits owned native operations and retains actual
pending receipts. Its stop path consumes native source age/sequence and includes
shared FK elapsed time in the 100ms budget. Repeated/unknown native status clears
prior proof. It does not create listeners or run an interpolator. Queued success
is not a native completion, and native completion is not measured head movement.

`prepare_factory_app` verifies the installed main/abstract/robot/daemon source
hashes and the actual imported native class/artifact identity plus reviewed target
binary hash before modifying classes or creating the app. It suppresses startup
apps in process memory, disables wake/sleep/media/datasets, binds HTTP to loopback,
and replaces robot `_update` with cached read/FK state updates under the shared
kinematics lock. That path publishes readiness; it is not fresh guard evidence.
Use the returned sealed ASGI wrapper; the installed console `main` also has
wireless/audio-config hooks and is not this entry path. Vendor files and saved
configuration are not edited. The function does not start the app lifespan, open
a controller or certify all producers. A ready backend and the private scheduler
still need actual verification before motion admission.

## Remaining admission work and runner evidence

1. Review the exact `.2` source and build, then build the ARM artifact with original
   upstream license/lockfile and record its actual ABI/hash. Validate queued,
   continuous producer, serial retry/block, GIL, foreign owner, expired policy and
   late-reply behavior on the target while motors are verified disabled. A Mac
   compile is source/build validation only.
2. Complete the private operator-only IPC and finite 1–2s minjerk scheduler using
   the source-pinned factory preparation/bridge. Bound every FK/IK interval and
   interpolation command, sample before actual admission, refresh from actual
   Agent request BEGIN, and retain pending native outcomes across client timeout.
   Revalidate ready backend/media/tracking/startup/internal producer suppression.
   Keep motion admission false until every capability is measured/verified.
3. Only then run one finite relative lift/turn, return to measured baseline,
   disable, and record actual Cartesian pose plus all-nine torque/slot evidence.
   Never use an unscoped REST stop fallback or restore changed human policy from
   an older snapshot. Replace the finite process with the verified original
   factory only after measured physical cleanup; if stop is unknown keep
   admission closed and report the unresolved state. Process kill or a restarted
   status page is not torque-off evidence. Late physical recovery must remain
   distinct from passing the 500ms acceptance gate.

Local wheel/ABI validation: `1.5.6+finite.head.2`, CPython 3.13, macOS ARM64,
Maturin 1.9.4, Rust 1.99.0. The wheel was imported in an isolated directory and
all seven finite methods were present; no controller was constructed. Wheel SHA256
`896ff72f595372b9fe5c0c6ac8f3299a023d6803ee183541effc5ce69a3b8cfc`;
native extension SHA256
`3ec7c4afd3760682cb23c9cd3bf86fa95a435d62066de1aebf0932feffb344dc`.
These hashes identify the Mac check artifact only; the target needs its own build.
The compatible Cargo/Python local version was verified by a real wheel build.

Local validation for `.2`: full 309 Python tests and 28 unique Python protocol/fence/sampler/bridge/process
traces and eleven Rust tests in the generated full crate, including a never-empty
producer and delayed serial read. No hardware session, installation, physical
head movement, acoustic acceptance or full factory execution is implied.
