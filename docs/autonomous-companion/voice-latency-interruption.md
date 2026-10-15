# Finite voice latency and interruption evidence

Source baseline: `6ef959475970380761f198e82354429e0eeb91b0`. This audit changes no service, model, prompt, voice, production configuration or microphone state. The sole hardware runner owns actual trials; source work must not start a second device session.

The 2026-10-15 closed-turn trial reported one successful STT/main/reply path: STT 308 ms, a canonical non-special reply of 63 characters, 59,072 consumed PCM frames over 3.711 seconds, source-end to playback 1.57665 seconds, total 10.844 seconds, and known final stop with the microphone off. This is one finite protocol result. It does not establish continuous dialogue, speaker identity, model cancellation, or repeated-run latency statistics.

## What the current clocks measure

The finite client receives `/stream/text`, collects the entire reply PCM through the `done` event, then starts playback. Its source-end to playback measurement therefore includes endpoint handling, STT, request/queue/network overhead, generation, full synthesis, full stream transfer and playback setup. It cannot be labeled LLM-only latency or time to first audible sample.

The worker's `Pipeline.completed()` reports a rounded `elapsed_seconds` after its local pipeline finishes. It does not split queue, generation, TTS or socket-write time, and it does not prove that the robot consumed audio. The worker's monotonic clock and the robot's monotonic clock have different domains; subtracting their absolute timestamps is invalid. An HTTP response or a submitted PCM frame count is not a consumed playback cursor.

## First minimal overlay: client timestamps only

Keep the same single-turn capture/authority/content leases, canonical endpoint, full-PCM guard, wake checks and consumed-frame backend. Do not begin partial reply playback or change the endpoint policy to improve a reported number. Add the following bounded numeric marks in the runner's existing report, using that process's `monotonic_ns()` and a fixed allowlist. Preserve the original sample-source time as a separately labeled source-domain observation. Use unknown/null for unreached stages; zero must never mean an unobserved duration.

| Mark | Exact observation |
| --- | --- |
| `source_end` | Original admitted candidate sample end, with its existing source-clock provenance/envelope; never replace with STT completion. |
| `endpoint_commit` | First completed endpoint accepted, before subsequent work. |
| `capture_closed` | Capture drop/close known, before main and reply. |
| `stt_request` | Immediately before opening the one STT request. |
| `stt_headers` | The client actually receives response headers. |
| `stt_complete` | The entire response is read and its transcript/decision validated. |
| `main_request` | Immediately before opening the one canonical main request. |
| `main_headers` | Canonical response headers received; do not call this first-token time. |
| `canonical_reply` | First validated non-acknowledgement, non-special reply event. |
| `first_pcm` | First validated canonical PCM event received; no playback/consumption claim. |
| `stream_done` | Valid `done` received and full PCM bounds verified. |
| `playback_submit` | First actual accepted frame submission, after existing fresh-authority checks. |
| `first_consumed` | First positive consumed-frame observation from the actual playback backend; retain cursor provenance. |
| `operator_withdrawal` | Watcher actually observes newer operator authority/revocation. This is not the human's unobserved physical action time. |
| `stop_requested` | The owned playback stop operation is invoked. |
| `stop_verified` | Stop/drop/close is known and final consumed cursor is recorded. |

The client report needs at most these sixteen fixed fields. Do not store text, raw PCM, prompts, request headers, secrets or arbitrary event bodies in this timing receipt. If marks originate on both the main thread and authority watcher, protect the small metadata map or marshal observations to the owner; a field is write-once. Duplicate, backward, non-finite or cross-domain marks invalidate the corresponding measurement rather than clamping it to zero. Preserve the existing original candidate deadline and recheck it before main and playback; timing instrumentation does not refresh any lease.

Report only observed, same-domain spans: STT round trip; main request to canonical reply; canonical reply to first PCM; first PCM to full-stream completion; full-stream completion to first submission; and first submission to first confirmed consumption. Source-end spans must retain their sample-clock uncertainty and distinguish sample-end from endpoint-commit time. For interruption, report authority-observed to stop-request and stop-request to verified-stop separately. A missing first-consumed observation remains unknown. Do not mix first-acknowledgement events into canonical reply latency.

This overlay belongs to the already owned, frozen finite runner, not a new daemon or worker API. Freeze/hash the precise changed script before the next authorized run and bind the numeric receipt to it. Test only the new behavior: missing marks remain unknown; incorrect order/domain/duplicates reject; canonical acknowledgement does not populate reply timing; source TTL is unchanged; and operator withdrawal during blocked HTTP cannot permit later PCM submission. The runner's actual stop receipt should determine the next change.

## Cancellation boundaries in the existing source

`Agent.set_microphone()` increments microphone authority, clears capture/resume state, and invokes `stop_speaker()`. `stop_speaker()` sends process termination and attempts socket shutdown on an already registered `voice_response`. These are local output-withdrawal operations. Process termination requested is not process reaped, and socket shutdown is not a model cancellation acknowledgement. The streaming `voice()` finalizer waits/kills/reaps playback; the finite ALSA runner must continue to use its own verified consumed cursor and stop/drop/close receipts.

There is a startup interval: `voice()` waits in `http.open()` before assigning `voice_response`. An operator stop can revoke authority during that interval, but the abort helper has no registered stream socket yet. The first worker reply is yielded only after `answer()` returns. While the worker is blocked in generation, closing a client socket does not automatically interrupt that call; disconnect is normally detected at a later socket write. The HTTP handler's eventual `iterator.close()` cannot retroactively cancel a blocked `next(iterator)`.

For the acknowledgement path, `Pipeline.stream()` uses `executor.shutdown(wait=True)` in its finalizer. That correctly keeps the local pipeline lock until the actual answer future returns. A caller timeout or `Future.cancel()` does not prove the thread stopped. Conversely, a legacy HTTP prediction transport timeout can return locally without proving that remote inference terminated. Worker `phase=idle` alone is insufficient evidence of backend completion after such a failure. Optional SDK `6ef9594` tracks its own actual/unknown operation slot; it does not establish a universal distributed lock or retrofit remote completion evidence into legacy HTTP inference.

Keep these separate observations in a stop result:

1. New operator authority observed; all later output admissions reject the previous authority.
2. No additional PCM submitted after withdrawal; final consumption/cursor and stop/drop/close are known.
3. Capture is closed, microphone remains in the current operator-owned state, and cleanup preserves newer/foreign owners.
4. The actual local worker/future returned, or is still running/unknown. Closing the client or abandoning a Python wait cannot turn unknown into returned.
5. Remote inference reached a real terminal result or a verified cancellation acknowledgement, or remains unknown. No timer, idle phase, closed connection or process restart substitutes for this evidence.

A successful physical output stop can be reported even while model execution remains unknown. It must not authorize an overlapping same-model inference on the pretense that cancellation completed. Never resume stale PCM, retry the abandoned prompt, fabricate an empty successful response, or overwrite a newer operator state during cleanup.

## Conditional next source changes

First read the actual operator-stop receipt. If withdrawal-to-output-stop is slow, locate the delay using the client marks before changing playback or capture. If the client is stuck before headers, a narrowly owned request-abort registration may be warranted, but it still cannot claim backend cancellation. If the existing legacy HTTP path can admit another inference after a transport-unknown result, prepare a separate same-backend operation-ownership fix and tests; do not silently treat the optional SDK slot as proof for HTTP. If client spans cannot isolate an actual remaining bottleneck, then consider request-local worker elapsed stage counters in the existing pipeline, default-off and without new content retention. No worker overlay or additional generation is needed merely to obtain the first client-side stage receipt.

The subsequent [HTTP execution ownership source fix](http-execution-ownership.md) closes the reproduced same-process admission gap after a transport-unknown result. Its actual response-model identity prerequisite and one-file overlay review remain separate from the baseline stop/timing observations above.

## Successful stream terminal follows producer cleanup

The exact `Pipeline.stream` AST reproduced a narrower ordering issue: the client could receive `done.ok=true` while the generator still held the pipeline lock; only advancing or closing the generator ran its finalizer. That proof used stubs without model or device access and did not establish concurrent runtime inference.

The stream now constructs its successful terminal value while holding the lock, exhausts audio production, joins its optional acknowledgement executor, returns the phase to idle and releases the pipeline lock, then yields `done`. A consumer may stop reading immediately after that event. An audio error, early generator close or executor-cleanup error produces no successful terminal; the lock still releases if executor cleanup raises. Real `Pipeline.stream` tests hold an actual executor worker in a completion callback and verify that no `done` is yielded until it exits, then check idle phase, released lock and reaped executor threads before generator exhaustion.

This terminal event certifies that local producer cleanup passed. It does not certify handler/socket thread exit, robot consumption, physical stop, or remote model cancellation. The separate HTTP/SDK execution-ownership checks and hardware receipts remain required.

For a later, separately frozen legacy deployment, run `python3 deploy/autonomous/prepare_stream_cleanup.py NEW_PRIVATE_DIRECTORY`. It verifies legacy `voice.py` SHA256 `95be315c7ed0af376fd9fc9dd6fb319f90776d10b2df04507b5daa0addd5e3c2` from Git pin `94fd73d906e75d90829562f58a7f62c83d7e4ff8`, and the exact cleanup source at `086d1598ca48c472e7cf931f528adfe45c038055`. It creates only `voice.py` and a manifest with source pins, preimage and output hashes. Only the terminal/finally block changes; all other bytes, imports, handlers, request payloads and audio production stay at the legacy preimage. It adds no configuration, dependencies, spoken constraints, SDK route, STT diagnostics, schema or autonomous imports. Existing output directories are rejected.

The four cleanup regressions also execute the actual old Pipeline class loaded from that generated file. Additional comparisons against the exact preimage cover `/say`, `/text`, `/turn`, reply/audio/done events, PCM conversion commands and bytes, default answer arguments, committed history and authenticated/unauthenticated request bytes. These tests use synthetic audio/model functions and run no model, SoX process or device. The manifest leaves model capability and hardware acceptance false. Deploy this one-file candidate only after independent review and a fresh owned baseline/rollback check by the sole runner; do not add it to an already frozen HTTP-ownership trial. The existing multi-feature spoken-reply overlay is a separate artifact and is not the minimal DONE-only proof.
