# Finite distributed audio runtime

`device_audio_runtime.py` owns ALSA capture and physical PCM on Reachy. `realtime_audio_session.py` runs the reducer on Hub; STT, fast, main and TTS execute on PC. These entry points require explicit capture/output opt-in, fresh receipt paths and a shared owner-selected controller ID. They do not install an always-on service.

Device activation requires an idle muted Agent, current boot/epoch and a fresh microphone owner nonce. `listen=false` keeps the production automatic listener paused. Cleanup uses the same nonce and epoch; a newer human command wins. Run the device entry point in a transient managed unit with `RuntimeMaxSec`, `KillMode=control-group`, `UMask=0077` and an `ExecStopPost` invocation of the same command with `--cleanup-only`. Private config and owner files stay on their original host.

The default transport is loopback. Direct RFC1918 IPv4 needs `--listen` on Reachy and `--trusted-private-lan` on Hub. URLs, controller IDs and permissions are owner configuration, never model output. The bearer-authenticated server admits four actual request threads before reading requests. Heartbeat uses a separate persistent TCP connection, a 50 ms request timeout, 20 ms renewal interval and a **300 ms non-revivable device lease**. Renewal requires actual Hub loop progress within 100 ms. PCM uses another persistent connection; stop has a separate request path. Timeout never substitutes for a measured stop receipt.

The no-output network probe and finite practice harness also support explicit `--lease-datagram-port` on both hosts. UDP renewal uses HMAC scoped to source boot/controller, an owner-issued 100 ms single-use challenge and strictly increasing sequence. Hello never extends the lease; an expired owner cannot revive. TCP remains the practice runtime default. The initial actual UDP network probe failed after 33 acknowledgements/34 device renewals; it is experimental, not an accepted replacement. Received/accepted/rejection/gap diagnostics were subsequently added for the hardware runner's next pinned test. First withdrawal now freezes local monotonic last-receive/accepted ages, source boot, acknowledged sequence and at most eight rejection labels. Hub reports send/ack ages, worker scheduling gaps, exit/exception and reducer progress age; ages from separate hosts are not synchronized timestamps.

Startup grace allows only status, stop and the authenticated initial renewal handshake. `operator_ready` is separate from output permission. Physical capture is opened and PCM admitted only after the first valid controller lease. Invalid, malformed or failed operator receipts close the peer; watchdog and operator worker occupancy are reported separately. An initial playback policy change can have a real stop job; its completion remains an admission requirement.

Capture uses nonblocking stereo S16LE/16 kHz ALSA and monotonic available-position timestamps. Channel zero feeds a RAM-only VAD endpoint. Unsupported timestamps, regression and xrun close the session. There is no read-time timestamp fallback. Latest-only observations retain source boot, sequence, bounded capture age and the actual preceding device stream reference. Owned playback and a bounded tail are excluded; this is not a calibrated acoustic echo canceller or a trusted negative resume window.

Audio STT has one actual occupied worker and one latest pending item. Boot, generation, operator epoch, lineage and deadline are checked again after completion. A newer admitted capture sequence supersedes the older STT result without releasing its occupied worker. The newest pending utterance starts only after that real worker finishes; obsolete completion cannot create a turn or change interaction epochs. Unknown speech remains an unconfirmed sensor observation. No speaker identity or memory fact is inferred. No raw audio or full transcript is saved by these entry points.

Fast generation prioritizes a ready answer, then a new candidate when no task is pending. Native object/tuple grammars constrain those phases to the corresponding actual aliases; the PC model still produces the choice and rationale. Snapshot text remains data. A finite practice response requires an actual question-stream reference. Unknown `замолчи`/`стоп` can withdraw the practice session without granting authority.

The practice harness admits only two owner-whitelisted arithmetic wake questions and at most three short local replies. Success requires both actual answers, measured complete PCM consumption, an eight-second no-response window, verified cancel within 500 ms and drained jobs. Default cancellation is a local operator event. Explicit device `--allow-agent-mute` plus Hub `--actual-agent-cancel` selects one owner-bound Agent microphone-off operation after measured consumption of at least320 frames of the fifth stream. Actual Agent-mute acceptance remains pending its device run; quiet recovery and joint native motion remain separate gates. Interrupted PCM resume remains disabled.

## Actual device measurements, 10 October 2026

The local capture-only preflight `audio-runtime-live5` passed: 10.001 s, 159728 stereo frames, 468 timestamp samples, maximum capture call 3.585 ms, maximum local status request 8.105 ms and maximum Agent operator request 14.409 ms. Capture closed, physical stop was known and microphone returned to false. There was no inference, PCM output or motion in that preflight.

Distributed `realtime-audio-live1/2/3/5/6/7` did **not** pass the complete voice criterion. Early runs expired the controller lease before playback. Wi-Fi power saving was confirmed on Reachy and Hub and disabled at runtime on both; the network was not restarted. This did not by itself eliminate expiry. The persistent heartbeat in live6 accepted 249 renewals before a 251 ms timeout; maximum Hub step was 13.576 ms. Actual main tasks completed, but no question was played in that run.

Live7 exercised actual PC fast → main → TTS → physical PCM: main 648.932 ms, TTS first PCM 203.054 ms, producer 235.300 ms and 36409 generated frames. Reachy measured at least **7168 consumed frames (0.448 s)** before controller expiry and verified drop. This is partial question playback, not a completed wake question or accepted external answer. Maximum Hub step was 8.033 ms, maximum successful device lease gap 49.976 ms and maximum Agent operator request 12.066 ms. Root closed capture and restored microphone false/epoch30/ownerNone; motor commands were zero. The completed main preserved the existing 9B/context32K instance. Physical consumed frames are never inferred from elapsed time.

The earlier accepted single-question endpoint/fixed acknowledgement remains documented in [native-live.md](native-live.md). It does not establish this distributed main-driven runtime, barge-in, memory correction or joint motion.

Hardware ownership belongs to the separate runner through the coordinator. The implementation chat opens no hardware sessions. A local handoff document records the boundary, private paths and next no-output test; it is kept outside the published code checkpoint.

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

The no-output probe uses a separate STARTING phase for at most two seconds. Pre-lease `permitted=false` is expected there. ACTIVE requires a successfully acknowledged renewal followed by a new status request reporting operator readiness and permission. After ACTIVE, any withdrawal remains terminal. A closed/expired STARTING phase cannot be revived by a late ACK. This probe admission change leaves physical capture, PCM and publication gated by the device's first lease and preserves all existing lease/challenge/progress/stop limits. Status and device receipts project operator metadata through a whitelist; owner nonces remain only in private owner files.

## Status, stop and a fresh finite restart

On Hub, `realtime_audio_control.py status --config <production-config> --controller <fresh-id>` reads the authenticated loopback session endpoint. It returns `session_boot`, `source_boot` and `controller` even while startup is pending. Copy that exact binding into the stop command:

```text
realtime_audio_control.py stop --config <production-config> --controller <same-id> --session-boot <observed-session-boot> --source-boot <observed-device-source-boot>
```

The stop API accepts only that exact binding. A delayed request for a previous session cannot stop a new one, even if its controller/source were reused. The response means `stop_requested`, never physical `stop_known`. The finite runtime then closes its real adapters, revokes context independently, requests the owned device stop and writes the final receipt. Connection refusal or absence of a listener is not proof of cleanup.

After the managed Root unit and Hub process exit, collect their metadata receipts into private files, then audit:

```text
realtime_audio_control.py check-cleanup --controller <same-id> --session-boot <observed-session-boot> --source-boot <observed-device-source-boot> --hub-receipt <finished-hub.json> --device-receipt <finished-device.json>
```

This check requires matching top-level and nested peer owners, a known lease transport, known physical stop, closed capture, drained Hub context/model/audio jobs, reaped device watchdog/operator/UDP workers (including an enabled UDP listener when Hub selected TCP), and microphone restoration metadata. Unknown or missing proof fails. It reports `receipt_cleanup_verified` separately from voice acceptance and live readiness; it cannot authorize a restart using historical files alone.

For an actual Agent-cancel session it also requires explicitly present, drained Hub `execution_busy.agent_cancel` and device `peer_status.operator_control_execution_busy`. A client timeout never releases the device's actual occupied HTTP control thread. Unknown acknowledgement closes the device peer and prevents Hub voice acceptance; cleanup can still be verified independently after the real worker exits.

## Prepared combined voice run after the network gate

Use one independently reviewed exact Git SHA on PC, Hub and Reachy. Do not switch the pin of an active observer experiment. First pass the finite no-output network gate at that SHA/route/transport: normal terminal stop, at least300 successful renewals, fresh status and complete cleanup. A diagnostic header run or many renewals followed by expiry does not pass this gate.

The runner audits the actual private configs without exporting values: PC gateway/model endpoints and token environment, preserved main model/context, the selected fast model placement and its finite child cleanup, PC STT/TTS URLs, Hub gateway token file and Agent URL, Reachy capture/playback devices, physical and control ports, request/response caps and context policy. Hub and Reachy perform no model inference. Keep motion disabled for this profile. All selected endpoints must have fresh owned readiness; do not add another model gateway, audio owner, service stack or VPS inference process. The existing VPS is optional only for separately accepted context services; a missing context-revoke proof fails an enabled context profile.

Launch the same finite managed device command above with the additional `--allow-agent-mute`, and the same Hub command with `--actual-agent-cancel`. Keep both opt-ins explicit. `/operator-mute` requires bearer authentication, exact controller/device source boot and a currently permitted device owner. The device alone holds the private microphone nonce and sends `enabled=false, listen=false` with its original Agent boot, microphone epoch and owner CAS. It admits only one actual control operation. The response retains only public microphone metadata and verifies an integer next epoch, unchanged Agent boot, microphone/listening/capture false, absent owner and known microphone state. No enable, automatic rearm or resume operation is provided.

The finite order remains two arithmetic wake questions and two admitted unknown external answers, an eight-second no-new-turn window, then the short owner-selected cancel utterance. After at least320 measured consumed frames of its separate stream, the Hub starts the asynchronous Agent-mute job while continuing reducer progress. Its 500ms cancel criterion includes both actual known stop/drained speech and the verified Agent acknowledgement, never elapsed-time inferred consumption. No-response here is absence of a newly admitted turn during the window; it does not prove the room was acoustically silent. A user stop, quiet/privacy change, unknown RPC result, lease expiry or extra admitted response prevents acceptance; no new question is generated to recover.

Collect both finished receipts and run the cleanup audit above. Require Hub `cancel_kind=actual_agent`, its scoped verified `agent_cancel`, `cancel_to_verified_s<=0.5`, exactly two matched unknown answers and complete consumption of the four earlier streams. Require device `accepted=true` as well: it checks the final microphone boot/epoch against its actual mute acknowledgement, unchanged policy epoch/quiet/privacy, closed capture, known physical stop and drained watcher/operator/control/UDP slots. A newer human command wins CAS and cleanup; a changed final baseline cannot be relabelled as this experiment's successful cancellation. Then inspect current Agent/factory readiness, previous owned listeners/processes and preserved PC main before any fresh explicit finite restart. Do not automatically re-enable the microphone.

Memory evidence is separate: the committed `test_audio_memory_integration.py` exercises unknown audio through an unconfirmed SQLite proposal, explicit owner confirmation/CAS correction, late speech fencing and forget/replay rejection using synthetic input. Run it locally against the pin before this voice stage. The finite voice entry points do not write confirmed long-term facts or save transcripts. This combined voice run cannot establish live memory confirmation/correction, camera perception, quiet recovery or joint motion; those require subsequent separately bounded integration and actual evidence. Neither synthetic memory success nor this prepared runbook is physical acceptance.

For a fresh finite restart, the hardware runner must additionally read current Agent/factory readiness, confirm no previous owned process/listener remains and verify the preserved PC main/gateway. Use a fresh controller, stage, output paths and private owner file; launch the managed device and Hub commands above with the same reviewed pin. Do not resume interrupted PCM or automatically reset quarantine. The control helper launches no service and introduces no always-on worker, camera or motion permission. Actual stop/restart acceptance still requires the runner's device test.

After ACTIVE, the no-output probe withdraws on a failed status request or 300 ms without a valid status receipt. STARTING still uses its separate two-second deadline. The probe freezes the first observed failure with renewal/reducer timing, closes its renewal slot and stops new work; a later success cannot re-admit that run. This is a Hub test lifecycle rule, not a change to device lease/heartbeat/challenge limits. The UDP client reports at most 16 metadata events (exchange phase, sequence, local age and exception type), with no token, nonce, MAC or payload. Root first-close metadata also states controller and operator time remaining. The earlier multi-second device expiry remains unexplained until the runner compares these new records.

Root additionally freezes a 16-entry tail for verified hello/renew handling, challenge/ACK sends, duration and bounded error label. `max_worker_loop_gap_ms` includes the socket receive wait; it is not a pure CPU scheduling measurement. Successful `sendto` records kernel submission, not delivery or a received Hub acknowledgement. Tail events use local monotonic ages; hosts are not clock synchronized.

## Transport candidates pending wire evidence

The client uses one connected IPv4 UDP socket and a single 40 ms receive for each challenge and ACK. The kernel filters the remote endpoint; HMAC/source boot and the current hello echo bind a challenge, and exact sequence binds the ACK. Each new attempt drains at most eight queued packets, then sends a fresh hello. A lost ACK does not cause replay of its renewal: the next complete exchange uses a new challenge and increasing sequence. Local fault tests cover that recovery and rejection of a previous ACK arriving during a new challenge wait.

The first failed attempt is now retained separately from the 16-event tail: attempt number, phase, sequence, last acknowledged sequence, elapsed/local send/receive/ACK ages and exception type. Repeated hello timeouts cannot erase this initial failure. No packet contents or authentication values are retained.

A `challenge_wait` timeout means no reply reached this receive within its bound; it does not identify loss on the wire versus kernel routing/filtering or process delivery. A `ValueError` in that phase can indicate an authenticated but mismatched reply or invalid authentication/freshness; it is not evidence of a timeout. Bounded matching of late replies within the existing receive deadline is a candidate only if metadata/wire observations show that case. Challenge retransmission is likewise only a candidate: any change must retain the single-use device challenge, exact reply binding, source/owner fences, occupied slot and all existing lease/receive deadlines. No matching, retransmission, timeout or protocol change is included in this diagnostic checkpoint.
