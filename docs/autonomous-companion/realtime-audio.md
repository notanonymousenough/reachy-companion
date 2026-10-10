# Finite distributed audio runtime

`device_audio_runtime.py` owns ALSA capture and physical PCM on Reachy. `realtime_audio_session.py` runs the reducer on Hub; STT, fast, main and TTS execute on PC. These entry points require explicit capture/output opt-in, fresh receipt paths and a shared owner-selected controller ID. They do not install an always-on service.

Device activation requires an idle muted Agent, current boot/epoch and a fresh microphone owner nonce. `listen=false` keeps the production automatic listener paused. Cleanup uses the same nonce and epoch; a newer human command wins. Run the device entry point in a transient managed unit with `RuntimeMaxSec`, `KillMode=control-group`, `UMask=0077` and an `ExecStopPost` invocation of the same command with `--cleanup-only`. Private config and owner files stay on their original host.

The default transport is loopback. Direct RFC1918 IPv4 needs `--listen` on Reachy and `--trusted-private-lan` on Hub. URLs, controller IDs and permissions are owner configuration, never model output. The bearer-authenticated server admits four actual request threads before reading requests. Heartbeat uses a separate persistent TCP connection, a 50 ms request timeout, 20 ms renewal interval and a **300 ms non-revivable device lease**. Renewal requires actual Hub loop progress within 100 ms. PCM uses another persistent connection; stop has a separate request path. Timeout never substitutes for a measured stop receipt.

The no-output network probe and finite practice harness also support explicit `--lease-datagram-port` on both hosts. UDP renewal uses HMAC scoped to source boot/controller, an owner-issued 100 ms single-use challenge and strictly increasing sequence. Hello never extends the lease; an expired owner cannot revive. TCP remains the practice runtime default. The initial actual UDP network probe failed after 33 acknowledgements/34 device renewals; it is experimental, not an accepted replacement. Received/accepted/rejection/gap diagnostics were subsequently added for the hardware runner's next pinned test. First withdrawal now freezes local monotonic last-receive/accepted ages, source boot, acknowledged sequence and at most eight rejection labels. Hub reports send/ack ages, worker scheduling gaps, exit/exception and reducer progress age; ages from separate hosts are not synchronized timestamps.

Startup grace allows only status, stop and the authenticated initial renewal handshake. `operator_ready` is separate from output permission. Physical capture is opened and PCM admitted only after the first valid controller lease. Invalid, malformed or failed operator receipts close the peer; watchdog and operator worker occupancy are reported separately. An initial playback policy change can have a real stop job; its completion remains an admission requirement.

Capture uses nonblocking stereo S16LE/16 kHz ALSA and monotonic available-position timestamps. Channel zero feeds a RAM-only VAD endpoint. Unsupported timestamps, regression and xrun close the session. There is no read-time timestamp fallback. Latest-only observations retain source boot, sequence, bounded capture age and the actual preceding device stream reference. Owned playback and a bounded tail are excluded; this is not a calibrated acoustic echo canceller or a trusted negative resume window.

Audio STT has one actual occupied worker and one latest pending item. Boot, generation, operator epoch, lineage and deadline are checked again after completion. A newer admitted capture sequence supersedes the older STT result without releasing its occupied worker. The newest pending utterance starts only after that real worker finishes; obsolete completion cannot create a turn or change interaction epochs. Unknown speech remains an unconfirmed sensor observation. No speaker identity or memory fact is inferred. No raw audio or full transcript is saved by these entry points.

Fast generation prioritizes a ready answer, then a new candidate when no task is pending. Native object/tuple grammars constrain those phases to the corresponding actual aliases; the PC model still produces the choice and rationale. Snapshot text remains data. A finite practice response requires an actual question-stream reference. Unknown `замолчи`/`стоп` can withdraw the practice session without granting authority.

The practice harness admits only two owner-whitelisted arithmetic wake questions and at most three short local replies. Success requires both actual answers, measured complete PCM consumption, an eight-second no-response window, verified cancel within 500 ms and drained jobs. The current harness cancel is a local operator event; actual Agent mute/quiet recovery and joint native motion remain separate acceptance gates. Interrupted PCM resume remains disabled.

## Actual device measurements, 10 October 2026

The local capture-only preflight `audio-runtime-live5` passed: 10.001 s, 159728 stereo frames, 468 timestamp samples, maximum capture call 3.585 ms, maximum local status request 8.105 ms and maximum Agent operator request 14.409 ms. Capture closed, physical stop was known and microphone returned to false. There was no inference, PCM output or motion in that preflight.

Distributed `realtime-audio-live1/2/3/5/6/7` did **not** pass the complete voice criterion. Early runs expired the controller lease before playback. Wi-Fi power saving was confirmed on Reachy and Hub and disabled at runtime on both; the network was not restarted. This did not by itself eliminate expiry. The persistent heartbeat in live6 accepted 249 renewals before a 251 ms timeout; maximum Hub step was 13.576 ms. Actual main tasks completed, but no question was played in that run.

Live7 exercised actual PC fast → main → TTS → physical PCM: main 648.932 ms, TTS first PCM 203.054 ms, producer 235.300 ms and 36409 generated frames. Reachy measured at least **7168 consumed frames (0.448 s)** before controller expiry and verified drop. This is partial question playback, not a completed wake question or accepted external answer. Maximum Hub step was 8.033 ms, maximum successful device lease gap 49.976 ms and maximum Agent operator request 12.066 ms. Root closed capture and restored microphone false/epoch30/ownerNone; motor commands were zero. The completed main preserved the existing 9B/context32K instance. Physical consumed frames are never inferred from elapsed time.

The earlier accepted single-question endpoint/fixed acknowledgement remains documented in [native-live.md](native-live.md). It does not establish this distributed main-driven runtime, barge-in, memory correction or joint motion.

Hardware ownership is being transferred to a separate runner through the coordinator. The implementation chat has closed its sessions and opens no new hardware session during that transition. A local handoff document records the clean boundary, private paths and next no-output test; it is kept outside the published code checkpoint.

## Reproduction

Stage public `src/reachy_companion` and `deploy/autonomous` into a fresh directory on the three hosts, leaving private config/token files in place. Start the existing finite PC gateway probe with the previously audited fast placement and preserved loaded main. Wait for that owned gateway's fresh readiness before activating Reachy. Do not reuse readiness from a prior probe on the same port.

On Reachy, use the existing production venv and `PYTHONPATH=<stage>/src`:

```text
device_audio_runtime.py --config <production-config> --output <fresh-device.json> --owner-file <fresh-owner.json> --controller <fresh-id> --duration 100 --capture-device reachymini_audio_src --allow-capture-output --listen 192.168.2.158
```

On Hub, use the staged source and the existing venv:

```text
realtime_audio_session.py --config <audited-finite-gateway-config> --companion-config <production-config> --token-file <private-gateway-token> --peer-url http://192.168.2.158:8780 --trusted-private-lan --controller <same-fresh-id> --duration 70 --output <fresh-hub.json> --allow-capture-output
```

For an explicitly selected UDP experiment, add `--lease-datagram-port 8781` on both Reachy and Hub; the Hub receipt records `lease_transport`. First require the no-output network preflight to pass at the same pinned SHA and route. UDP remains experimental; adding this option does not establish acceptance.

Inspect both receipts, actual operator state and preserved PC main after the unit exits. A false receipt, unknown stop, occupied worker or quarantine must not be published as a completed voice round. Joint motion is rejected by this harness until its separately reviewed ownership/permission profile is integrated and accepted.

The no-output probe accepts `--status-interval`: baseline `0.02` seconds, comparison `0.2` seconds. Only status polling cadence changes; heartbeat interval, reducer progress gate, challenge lifetime and device lease remain identical. Use fresh paths and the same pinned SHA for both finite runs.
