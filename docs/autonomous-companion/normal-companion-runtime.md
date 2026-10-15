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
