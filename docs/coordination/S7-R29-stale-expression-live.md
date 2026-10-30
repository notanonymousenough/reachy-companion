# S7 R29 — caller repair and actual motion/STOP

17 October 2026, Europe/Moscow. Sole physical owner S7. Scope 15:47:49–16:02:49; required rollback reserve from15:59:49. **One player-only install completed, actual movement/STOP PASS, fresh ordinary local operation resumed with motor ON.** This is a bounded motion repair receipt, not full companion/30min conversation acceptance.

Exact public production preimages were exported before changes: [manifest](../../S7-evidence/R29/preimages/manifest.json). Agent1f4e52a6…, old player4b2ea103…, Hub008be03…; Robot client differs from Hub client and both were exported. Workspace HEAD was not substituted. [Frozen package](../../R29-evidence/transfer-manifest.json), [source handoff](../../R29-evidence/HANDOFF.txt), [independent gate](../../TECH-evidence/R29/source-gate.json): 7 source tests and5 independent boundary groups PASS.

Only production `expression_player.py` changed to SHA256 `1e25036f63ce474fec4932a6e80478b31777eab3d25a5eba06434c5cdc8ca286`. Local invalidation plus exact typed same-route409/error body may report `discarded`, `motor_success=false`, `partial_effect_possible=true` only after fresh known same-Hub cleanup and empty actual factory running list. Prior error remains; failed cleanup/changed Hub boot latches failure. No retry, replay, rewriting old binding/version, TTL/CAS/owner or daemon/SDK/framework change. Other409/HTTP/UNKNOWN remain failures. This cancellation branch was proved offline, **no actual409 was observed or forced in the physical gate**.

Fresh MicOFF299→300 drained capture/worker/Hub with motor138OFF. Exact old player backup retained in Robot `/var/tmp/reachy-S7-R29-20261017` (directory0700, source/metadata0600). Atomic replacement preserved uid1000/gid1000/mode0664, syntax compiled; no runtime import/SDK initialization for installation. One Agent-only stop/start: PID276911, boot `46b5d19c-38e8-4cc1-9b68-26f70c085a18`; factory PID150625 unchanged. New boot verified paused/mic300OFF/motor138OFF before fresh grants. [Install](../../S7-evidence/R29/install.json), [new boot](../../S7-evidence/R29/new-boot-off.json). No stale persisted ON/grant restoration.

## Actual product gate

At15:52:57 fresh motor139ON, then mic301ON. Real Agent capture→ExpressionPlayer neutral and ordinary reaction ran; no direct injected expression, seed, speech fixture, or extra voice acceptance window. [Gate](../../S7-evidence/R29/motion-gate.json), [encoder samples](../../S7-evidence/R29/encoder-gate.json), [HTTP receipts](../../S7-evidence/R29/endpoint-receipts.json), [analysis](../../S7-evidence/R29/gate-analysis.json).

- 224 actual encoder samples, read errors0;11 samples with factory move running. Head range roll0.1034/pitch0.0708/yaw0.0999rad (about6° maximum); antenna ranges0.3252/0.4157rad (about19°/24°). Three actual Hub `/actions/expression` POSTs returned200.
- Full guarded STOP at15:53:05: mic302OFF then motor140OFF. Known paused/captureOFF/workeridle/Hubfree/actionfalse/stockknown/unowned established.18 subsequent status samples remained stopped/error-free.
-161 encoder samples after STOP through15:53:28.717 (22.8s): factory running samples0, audio-process samples0, late Hub expression POSTs0. Small encoder readback variation: head≤0.00255rad, antennas≤0.00154rad. This is operational STOP/no late output evidence, not certified torque-off/emergency-stop proof.
- Voice/expression error samples0. No raw speech, transcripts, camera pixels, private config/token, or journal message bodies exported.

## Fresh resume and retained baseline

Fresh motor141ON then mic303ON at same new boot; no replayed grant. Actual15:54:05: listening/captureON, source2, PCM368640B/gaps0/overflow0/retiredfalse, last_error/expression_error absent, ownersnull, quiet/privacyclear, Hubfree/actionfalse/stockknown/unowned, workeridle. [Resume](../../S7-evidence/R29/fresh-resume.json), [final state](../../S7-evidence/R29/final-after.json).

Camera captured2 different actual frames519901/520312B inRAM; reader closed, raw files/pixels export0, audio init/inference0. Robot configa6171f68… unchanged, Agent1f4…/capturepump5fe…/spokenvision2d7…/snapshotd43… unchanged; one arecord277110→276911, factory unchanged/NRestarts0, volume100%/0dB. PC source224ff…/config2e0a…/profile2ff5… unchanged; effective ordinary short=false/ACKfalse/headroom1.0dB (existing +2dB gain vs3.0), same9B/Whisper/Piper. [Robot preservation](../../S7-evidence/R29/return-final-robot.json), [ordinary preservation](../../S7-evidence/R29/ordinary-after.json), [camera](../../S7-evidence/R29/camera-pixel-check.json).

The prior R28 two useful complete brief Russian replies remain the voice evidence; its missing third reply/continuity limitation stays open. R29 did not run another voice gate or change prompts/models. Persistent semantic vision, broad autonomy, acoustic latency/duration and30min stability remain unaccepted.

Operator STOP remains existing `scripts/companion voice microphone-off` and fresh guarded motor-policyOFF for full operational motion withdrawal; fresh microphone-on is a separate authorized resume. Conditional exact player rollback script and protected backup are retained; no rollback was needed. R25/R26 remain closed. Late direct human approval of the listed R26 CPU startup assets is recorded as authorization only; no new R26 install/server/App/egress was started.

**Terminal release:** 2026-10-17T15:54:52.789383+03:00; sole hardware session released to TechLead, no further probes/inference. R29 work complete within15min, no rollback required. Remaining product limitation is R28 voice continuity (third reply absent; causeUNKNOWN), plus broader unaccepted autonomy. Further diagnostic scope/cost not authorized or consumed by this receipt.
