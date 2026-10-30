# R54 camera context: receipt-only pivot

Accepted source scope: opt-in shared-camera semantic cache for outgoing `/turn` and `/text`; no autonomous camera actions. Sound fallback persists independently: `conversation.sensory_loop.sound_decisions_enabled=false` keeps real classifier observations while decision callback returns WAIT. New `camera_enabled` defaults false; global `sensory_loop.enabled` must also be true. TL sets both explicit opt-ins and sound fallback in Robot config; source does not restore OFF or enable motors.

## Actual evidence and single pivot

`R54-camera/presentation-proof.txt` failed the strict nonzero advancing PTS contract. `pts-diagnostic-result.txt` then proved 21 received IPC samples at 10fps, 1280×720 BGR, PLAYING, clean close, **all 21 PTS and running times zero**. This proves delivery progress, not source presentation time or exposure age. The theoretical unixfd source-presentation mapping is therefore withdrawn for this integration. No third PTS guess/probe, producer modification or daemon restart is proposed.

Selected path uses the already-working R43 shared SDK IPC consumer and native VLM pathway. The child requires two separately received samples within a bounded read window, records both local receipt times and observed PTS metadata, closes the SDK consumer before requesting inference, and never calls this source/exposure progress. It does not own/reopen the physical camera or import audio. Physical exposure and source presentation age remain unknown. Freshness/TTL now explicitly concern **local IPC receipt only**. This gives useful scene context with a stated limit, rather than claiming the scene was exposed recently.

## Exact transport contract

Agent takes one cache snapshot immediately before outgoing `/turn` or `/text` dispatch, after obtaining the common local-model slot. It removes any caller-supplied `visual_context`. `/say` and replay are not new visual answer generation routes.

```json
{"summary":"caption, max 400 characters","source":"shared-camera-ipc-receipt","frame_id":"32 lowercase hex chars","receipt_age_s":5.0,"ttl_remaining_s":24.9,"exposure_age_unknown":true}
```

`receipt_age_s` is recomputed at dispatch from Robot monotonic receipt time. Receipt age is in `[0,30)`, remaining TTL is positive and at most `30-age`; a microsecond margin avoids floating point boundary rejection. PC must preserve receipt-only wording; it cannot infer source presentation/exposure age or compare its monotonic clock with Robot. Frame ID hashes real PNG bytes plus local receipt identity; it is not a semantic identity or a proof of scene change. Pixels remain in child RAM only. Agent status includes `freshness_basis=ipc_receipt_only_source_and_exposure_unknown`, observed zero-PTS metadata and explicit unverified source/exposure flags in the last accepted frame.

## Model and lifecycle

Child interpreter is `/venvs/mini_daemon/bin/python` because Agent venv lacks the SDK. `PYTHONPATH` selects this installed wheel's actual package root. Existing `snapshot_vision` helpers verify a local native endpoint, configured model and already-loaded vision instance; there is no model load or new dependency. Camera request uses the proven R43 native shape, `max_output_tokens=2048`, timeout 15s, total receipt job TTL at most 30s. Reasoning off is requested only if inventory advertises support.

A single common slot coordinates sound model calls, camera GO and Agent voice dispatch. Camera model admission requires actual listening phase/current authority and no active/unknown model job or foreground waiter. A known terminal sound schema failure does **not** occupy the backend. Foreground has priority before camera GO; after submission it waits for actual terminal/reap (at most the 30s job bound plus margin), which can add latency to a question. A killed client or socket timeout does not prove backend stopped: unknown retains the slot and blocks new same-backend requests with an explicit error. It requires a known-idle recovery outside this scope, with no automatic retry/reset.

Complete bounded HTTP response emits terminal metadata before JSON/final-message validation. Known HTTP/parse/config/capture faults latch separately from model uncertainty and do not spam repeated requests. Pre-grant failure/expected cancellation never pretends an unknown inference. STOP, privacy, epoch or mode withdrawal cancels the child, clears cache, and keeps the lane until reap. Expected pre-grant withdrawal does not permanently fault the observer; submitted unknown does. Cache expiry and authority changes also remove context without waiting for a voice request. Ordinary new PCM withdraws sound/action proposals while preserving current-authority visual cache and submitted caption; it is not a camera authority revocation, and therefore does not manufacture unknown inference on every question.

## Verification and limits

Local synthetic tests exercise zero-PTS delivery capture, exact receipt-only envelope, dispatch age/TTL/epoch/privacy clearing, default opt-ins, persisted sound fallback, common slot contention/unknown, terminal-before-parse, pre/post-GO cancellation and terminal process reaping. Regression command:

```
PYTHONPATH=src python3 -m unittest tests.test_r54_visual_context tests.test_semantic_observer tests.test_r53_sensory_bridge tests.test_conversation_mode tests.test_sensory_loop -q
```

These are source contracts, not a live camera/model/voice proof. TL owns frozen wheel/config/install and one actual camera context attempt. Previous source-presentation note in `SEMANTIC-OBSERVER-2026-10-18.md` is superseded by this explicit receipt-only outcome. No further sound decision variant is introduced; retained speech/movement and observation-only fallback remain accepted.
