# R29 source release

R29 frozen source handoff — 2026-10-17

Single candidate: candidate/expression_player.py
SHA256: 1e25036f63ce474fec4932a6e80478b31777eab3d25a5eba06434c5cdc8ca286
Exact player preimage: 4b2ea1039145da87a381b3da04ea64693842547d159e3afd65e393247c516e66
Agent remains exact 1f4e52a6b54b6c12de2bd325e094625ebdf4e2e341df2fa5e2230a51ee660a19.
Hub remains exact 008be03f69d9564c9f476b086ddf9eb3fa8e587682c6791b776234933f8c682d.
Full production paths, uid/gid/mode and all dependency preimages: transfer-manifest.json / preimage-manifest.json.

Behavior and source proof
The exact Hub can reject expression_version before dispatch or while polling an already dispatched move. A typed 409 alone therefore proves no absence of effect. This caller discards only an exact typed Hub expression 409, exact one-key JSON error, and its own monotonically advanced local version. It preserves the original payload binding/version and prior last_error. It reports status=discarded, motor_success=false, partial_effect_possible=true, owned_cleanup_verified=true. No automatic retry/replay or binding rewrite occurs. The worker may subsequently build a new plan for the latest valid intent through its unchanged guard.

Discard requires fresh (<300ms total) Hub status and read-only factory /api/move/running: same cached initial Hub boot, action lane idle, ownership free, selected stock transport, unknown=false, owned_uuid=null, daemon running/error-free, backend ready/error-free, and empty running list. Actual Hub.move/stock_stop_owned source is exercised offline for successful cleanup and failed-stop UNKNOWN. An unverified cleanup or changed Hub boot latches the caller UNKNOWN fence and retains failure. Existing guards, TTL/CAS, STOP/hold, voice, microphone and camera paths are unchanged.

Conditional installation — S7 only
1. Independently review candidate/hash/one-file diff and confirm exact live pins against manifest; reject changed preimages. Physical hard deadline 2026-10-17 16:02:49 MSK.
2. Use existing guarded MicOFF/motorOFF, drain and prove known idle/owned terminal. Stop only Agent. Preserve exact deployed player as rollback, verify its hash. Atomically replace only /home/pollen/reachy-companion/src/reachy_companion/expression_player.py with frozen candidate, preserving uid=1000/gid=1000/mode=0664. Syntax-compile without runtime imports. Do not deploy bundled dependency preimages.
3. Restart Agent, independently verify new boot, exact source pins and healthy known idle. Preserve config/Hub/Agent/ordinary voice=false/ACK=false/+2dB/camera settings. Only S7 may grant fresh guarded motorON and run actual movement plus STOP acceptance before deadline. Verify the factory read route and observation budget on the deployed runtime. Offline PASS does not establish physical acceptance.
4. On first unexpected error or UNKNOWN: guarded OFF; reconcile owned job to independently known terminal. Do not clear UNKNOWN via blind restart. Stop Agent, atomically restore only the saved exact player preimage (hash above, uid/gid/mode unchanged), syntax-compile/start and verify pins/healthy idle. Restore authorized normal listening with microphone/camera and +2dB baseline; motorOFF is fallback. Never replay an old grant or payload.

Verification
7 synthetic offline tests PASS, no hardware/network/runtime calls by source specialist. Tests include real worker in-flight invalidation, no replay, STOP before dispatch, prior last_error retention, same-version/ABA refusal, typed error strictness, unknown/owned/busy/foreign/restarted Hub rejection, daemon/backend errors, and exact Hub partial-effect cleanup. Patch forward and reverse verified against exact preimage. Tech independently reported 7 tests plus 5 boundary checks PASS against this exact frozen SHA. Hardware acceptance=false pending S7 evidence.

Artifacts: `R29-evidence/R29-source.tar.gz`, `transfer-manifest.json`, `expression_player.patch`, `offline-tests.txt`.
