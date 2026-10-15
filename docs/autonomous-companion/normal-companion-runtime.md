# Normal joined runtime: finite first deployment

`python -m reachy_companion.autonomous.companion_session --mode normal` joins
the existing Scheduler, AudioPolling/AudioAdapter, SpeechAdapter/Playback,
RemoteGateway and optional bounded antenna17 MotionAdapter. It accepts normal
fresh utterances without a scripted wake question or practice echo-reference
requirement. The separate `deploy/autonomous/realtime_audio_session.py` remains
the two-Alice-round diagnostic and still rejects joint motion.

This first normal entrypoint is **finite**, not a continuous-companion completion:
the existing device owner ends after at most 180 seconds and retains at most 32
stream identities. Normal Hub admission stops after 31 cumulative reservation
attempts once current output drains, independently of diagnostic receipt rings.
RemotePCM spends each attempt before transport (including unknown completion)
and rejects a 33rd attempt before reserve; one already pending stream can still
occupy the 32nd slot. No attempt is reclaimed and no stream IDs are evicted. No device
process is restarted, and no expired microphone/source/epoch is reacquired.
Lifetime extension and authenticated terminal stream retirement require a later
separate protocol review. The first integrated device demonstration need not
wait for that extension.

## Source and dependency closure

| Role | Existing entrypoint and responsibility | Required closure |
| --- | --- | --- |
| PC inference | `python -m reachy_companion.autonomous gateway --config <pc-autonomous.json>` | Installed source pin, `[autonomous-pc]` when using SDK (`lmstudio==1.5.0`), actual fast/main model/tokenizer/template/placement audits, configured credentials and exclusive execution ownership. `/health` boot must remain unchanged; quarantine withdraws the session. |
| PC STT/TTS | Existing configured worker `/transcribe` and `/stream/say` | Matching actual worker source/config/model dependencies; companion `network.compute_url` and `network.voice_url` select endpoints. TTS here does not invoke a scripted question or another LLM. |
| Reachy audio | `deploy/autonomous/device_audio_runtime.py` | `[robot]`, reviewed ALSA source/sink and existing Agent with owned `listen=false` microphone support; actual capture/output/stop checks. No inference on Reachy. |
| Hub normal loop | `reachy_companion.autonomous.companion_session` | `[autonomous]`/jsonschema and standard-library transports. Hub opens no ALSA device and constructs no model or serial driver. |
| Optional antenna17 | Existing accepted native owner plus MotionAdapter | Existing independent factory/serial ownership gates remain mandatory. No factory/head/native startup is added here. Full-head `.4` remains separately gated. |
| Optional context | Existing ContextProvider with `mode=memory_only` | Exact disposable whitelist DB/namespace and independently frozen confirmed readback SHA, as in `context-live.md`; existing pre-transport fast/main guards remain unchanged. No memory promotion or private DB selection is automatic. |

The normal profile uses the remote audio peer. Keep `speech.enabled=false` (the
other CLI's local ALSA profile); only `speech.tts_gain` is reused. Enabling that
local ALSA profile rejects rather than silently ignoring a second output path.
Gateway endpoint, both model settings and token environment remain in the
autonomous config. STT/TTS/Agent URLs and their token file remain in the explicitly
selected companion config. With motion enabled, `motion.hub_config_path` must
resolve to that same companion config; `motion.agent_url` may select the reviewed
native proxy. Speaker and motor must report the same actual Agent boot.

No production config, installed source, saved volume, microphone state or service
is changed by these instructions automatically. The device runner owns deployment
and supplies reviewed real paths, interfaces, ports, hashes and process identities.
Only one Hub runtime may use a given controller/source window. Starting another
copy or changing ports is not ownership recovery.

## Reviewable start order

1. Freeze source/config/model/runtime/ownership checks before opening the finite
   device window. PC gateway health must be ready and idle, with no unknown model
   completions. The real PC worker STT/TTS endpoint is a separate dependency;
   successful legacy worker generation alone is not acceptance of autonomous
   Gateway fast/main wiring.
2. If motion is selected, establish the separately accepted antenna17 owner
   first. Normal mode cannot construct, restart or take over that owner. Its
   preflight requires a current verified hold with zero trajectory updates after
   hold, plus actual ready/owner_verified/kernel_exclusive and enabled policy.
   `--allow-bounded-motion` must match explicit `motion.enabled=true` and
   `actuators=bounded_native_antenna17`. No head profile is inferred.
3. Start the existing device audio owner with fresh private receipt/owner paths
   and one chosen controller. It explicitly acquires the microphone once from
   an idle baseline; normal Hub mode never does so. The device first-lease window
   is 10 seconds: start the reviewed Hub promptly, otherwise let ownership expire
   and audit cleanup before a new explicit window. Never retry microphone enable
   or reuse an old source to conceal a failed start.

```text
<device-python> deploy/autonomous/device_audio_runtime.py --config <device-companion.json> --output <new-device-receipt.json> --owner-file <new-private-owner.json> --controller <controller> --duration 180 --allow-capture-output --listen <reviewed-device-interface> --port <media-port> --stop-port <separate-stop-port>
```

Read the authenticated existing peer `/status` using the runner's existing
transport and freeze its actual `source_boot`. A foreign, closed or changed source
is not admitted. Dedicated stop and media ports must differ. Optional UDP renewal
requires the same explicit `--lease-datagram-port` on device and Hub, after its
independent actual transport checks; it is not silently selected.

```text
<hub-python> -m reachy_companion.autonomous.companion_session --mode normal --config <isolated-hub-autonomous.json> --companion-config <reviewed-hub-companion.json> --token-file <gateway-token-file> --peer-url <reviewed-peer-url> --peer-stop-port <separate-stop-port> --controller <controller> --source-boot <actual-source-boot> --duration 60 --status-port <local-normal-control-port> --allow-capture-output
```

Add `--trusted-private-lan` only for the explicitly reviewed private peer
interface; otherwise use the existing loopback/SSH transport. Add
`--allow-bounded-motion` only for the accepted antenna profile above. Context
requires both `--memory-readback <confirmed-readback.json>` and
`--memory-readback-sha256 <independently-reviewed-file-SHA256>` with the isolated
memory-only config. Missing readiness never substitutes replay, synthetic
observations, a practice question, another model, source or DB.

## Health, stop and rollback

```text
<hub-python> deploy/autonomous/realtime_audio_control.py status --config <reviewed-hub-companion.json> --url <local-normal-control-url> --controller <controller>
<hub-python> deploy/autonomous/realtime_audio_control.py stop --config <reviewed-hub-companion.json> --url <local-normal-control-url> --controller <controller> --session-boot <actual-session-boot-from-status> --source-boot <actual-source-boot>
<hub-python> deploy/autonomous/realtime_audio_control.py check-cleanup --controller <controller> --session-boot <actual-session-boot> --source-boot <actual-source-boot> --hub-receipt <finished-normal-receipt.json> --device-receipt <finished-device-receipt.json>
```

`listening_ready` reports actual local operator/capture admission, rather than
merely a listening HTTP socket. Status/stop use the existing independent loopback
control server. Stop's ACK means admission withdrawn, not physical stop. SIGINT
and SIGTERM request the same owned shutdown; exceptions attempt all finalizers.
The reducer stops renewal and new inputs, closes adapters, requests exact
source-bound device stop on the dedicated listener, and waits at most one second
for actual slots to drain. Unknown STT/model/HTTP/native completion remains busy
in the finished receipt; it never becomes cancelled because a timeout elapsed.

Compute boot change, quarantined model completion, expired health/operator status,
device source closure, physical operator change or motor-owner change withdraw
this window. There is no automatic reconnect, microphone activation, unmute,
resume of old PCM, factory restart or epoch restoration. The existing device
owner's cleanup turns off only its owned microphone. If startup partially fails,
the normal receipt records attempted cleanup, exact owned peer stop and remaining
busy jobs; it is not an accepted session.

Rollback means stop this exact normal session and owned device window, retain
unknown jobs/artifacts, and independently verify final muted/idle operator,
consumed PCM stop, native hold and original factory handback through the already
accepted owner procedure. Do not kill or unload shared model services to make
cleanup green. A stopped Hub process alone is insufficient. Do not install an
unbounded/restarting service unit from this finite checkpoint.

The normal receipt contains bounded metadata/counts, TTS/PCM lineage and stop
receipts, optional motor receipts and actual busy slots, without transcripts or
raw PCM. `accepted` describes this finite lifecycle and known cleanup; it is not
speaker identity, acoustic audibility, actual model/hardware attestation, a
voice-to-memory acceptance verdict or continuous-operation proof. The runner's
first real integrated demonstration must independently establish actual STT,
fast/main FINAL, consumed reply, bounded movement and final owned cleanup.

## Separate opt-in lease lifetime and sequenced retirement

This source extension adds `--lifetime lease` to the existing device and normal
Hub entrypoints. Omitting it preserves finite durations/cumulative stream budget.
The lease mode rejects `--duration`: its authority consists of the existing
300 ms operator/controller leases and fresh reducer validation, not an increased
absolute timeout. Per-stream PCM/deadline limits remain unchanged. Selecting the
mode is not actual continuous acceptance; reports keep
`continuous_acceptance=false` until independent real-device review.

| Existing file | Lease-only dependency |
| --- | --- |
| `device_audio_runtime.py` | Consume one already explicitly granted exact Agent owner from a private file; pinned FD/flock, one-shot fsynced source claim, no microphone-enable call. |
| `audio_peer.py` | Current typed owner binding on TCP lease; sequenced source-derived wire IDs, high-water before reserve, per-stream/handler refs, exact retirement; sticky PeerLease withdrawal. |
| `lease_datagram.py` | The same owner binding in authenticated hello/renew; unknown exchange latches the lease client. |
| `playback.py` | One bounded terminal receipt; full measured consumption for normal completion or verified cancelled prefix, actual worker/stop return before cache retirement. |
| `speech_adapter.py` | Hold a fresh proposal while terminal retirement blocks admission; do not label pending metadata as a physically executing job. |
| `companion_session.py` | Validate fresh authenticated peer/operator authority before renewal; one accounted retirement Job; no reconnect/reacquire after withdrawal. |

The private owner file must already contain the reviewed `agent_boot_id`,
`initial_microphone_epoch`, `owned_microphone_epoch=initial+1`, `owner_id` and
`policy_epoch` from an **explicit separate operator grant**. It must be a regular
single-link file owned by the device user, mode 0600. The runtime never creates
this grant or enables the microphone in lease mode. The actual Agent must still
match that owner, boot, epochs, paused/listen=false state and allowed policy.
The runtime holds the file lock and adds `lease_source_claim` with the chosen
controller/source boot before capture starts. This marker is never automatically
cleared, including after successful shutdown: a crash, process exit or free flock
does not authorize adopting the old grant into a new source boot. A new window
requires a new explicit grant/epoch/owner and fresh private file. Do not copy or
reset an old owner file to recover ownership.

Automatic cleanup uses the frozen admitted owner rather than rereading a possibly
replaced pathname. It can only mute that exact boot/owned epoch/owner ID. It does
not use the finite path's initial-epoch fallback, restore the original enabled
state, modify a replacement owner, or turn the microphone on again.

```text
<device-python> deploy/autonomous/device_audio_runtime.py --lifetime lease --config <reviewed-device-companion.json> --output <new-device-receipt.json> --owner-file <already-granted-private-owner.json> --controller <controller> --allow-capture-output --listen <reviewed-device-interface> --port <media-port> --stop-port <separate-stop-port>
<hub-python> -m reachy_companion.autonomous.companion_session --mode normal --lifetime lease --config <reviewed-hub-autonomous.json> --companion-config <reviewed-hub-companion.json> --token-file <gateway-token-file> --peer-url <reviewed-peer-url> --peer-stop-port <separate-stop-port> --controller <controller> --source-boot <actual-claimed-source-boot> --status-port <local-normal-control-port> --allow-capture-output
```

The earlier independent motion/context/transport gates and status/stop/cleanup
commands still apply. Device and Hub must both explicitly select lease mode;
mixed protocols reject. TCP renew includes source boot plus typed Agent boot,
microphone/policy epochs and a hash of the owner ID. UDP checks the same binding
within its signed challenge/renew protocol. The raw owner nonce is not sent in
status/renewal. First renewal waits for verified authority; subsequent ticks
require fresh peer/operator receipts, not just loop activity. Unknown renewal,
expired reducer freshness, source/owner changes and stop latch withdrawal.
Late ACKs or ticks cannot rearm it and no reconnect/retry resets the latch.

Wire stream IDs are exactly `<source_boot>:<stream_sequence>`; sequence is a
bounded monotonic integer without wrap/reset. The device spends high-water before
the potentially unknown reserve operation. One live/unknown record blocks the
next reservation. Internal Playback UUIDs remain behind that bounded mapping.
Deleting a terminal mapping never makes an old ID reusable.

`/finish` remains an input-queue ACK. New `/retire` requires exact stream,
sequence and device generation. Ordinary HTTP stream handlers hold refs through
response completion; backend dispatch refs use the same lock. Retirement waits
for input completion/full measured consumption, or a cancelled stream's measured
prefix, plus verified backend stop and returned worker/stop/reservation jobs.
It cannot run while another handler still references the stream. Its own ACK
contains terminal metadata only, with no later backend access. A known busy
reply retains metadata and permits only another accounted retirement attempt;
unknown/error results preserve the record and withdraw output admission.

On the Hub, a retirement ACK alone does not reopen admission: the actual TTS,
cancel and PCM jobs must have returned, and local terminal/cache retirement must
commit first under the Playback lock. Both maps and completed Playback caches
then clear; scalar high-water and bounded diagnostic tails remain. Unknown stop
cursor or a held backend cannot be discarded to free capacity. No PCM resume,
blind tombstone eviction or new owner boot is substituted for this proof.
Successful retirement also closes its drained media connection on the retirement
worker. Final shutdown uses a separate accounted media-close Job that waits for
actual producer/cancel/PCM return before closing the transport; it remains busy
if a remote progress call is still held. Dedicated stop never waits for or closes
the media lock, and socket closure is not evidence of remote execution stop.

Local tests cover 40 completed worker/HTTP streams with bounded empty retired
caches, replay/foreign generation/overflow denial, held progress/stop refs,
cancelled prefix, unknown reserve/cursor, late ACK/tick, owner-file alias/reuse,
normal reducer integration and unchanged finite mode. These synthetic fixtures
do not establish hardware consumption or elapsed continuous operation. Actual
acceptance separately requires **more than 180 seconds and more than 32 real
streams**, stable current owner/epochs, measured consumed PCM/known stop, bounded
metadata and mute/network-loss tests without authority recovery. No service is
installed or restarted by this source checkpoint.
