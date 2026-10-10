# Request-local STT stage diagnostics

This is a two-module overlay for the existing compute worker, not a deployment of
all repository HEAD. The authenticated `/transcribe` handler is in `voice.py`;
`worker_container.py` only launches Docker and is unchanged.

The production path first classifies the last configured YAMNet window (currently
3s) and returns empty on `kind=music`, without invoking Whisper. An ordinary empty
`transcript` cannot distinguish that from an invoked Whisper returning no accepted
text. Opt-in metadata now distinguishes `music_prefilter_skipped_whisper` from
`whisper_empty` for the SAME admitted RAM PCM and the SAME inference pass.

## Exact target/source mapping

The existing worker source was read and its hashes matched this repository before
this patch. Abort the overlay if ANY preimage differs; audit the actual runtime
paths, container/image and launch command rather than assuming an installed HEAD.

| Module under `/app/src/reachy_companion` | Preimage SHA256 | Patched SHA256 |
| --- | --- | --- |
| `voice.py` | `95be315c7ed0af376fd9fc9dd6fb319f90776d10b2df04507b5daa0addd5e3c2` | `46c0343fd47e085098be6ffd7828673986caca0e4bd924d6f2e3178508708c73` |
| `recognition.py` | `6211a01e8d4ecf515636d4407856fddcf6e5deec4ddbd5639ae977770111f15f` | `b79a709bb3167c0fba380aafa687c846db592c8ec0ecdeec88742179ec548344` |
| `sound_events.py`, unchanged | `6e26da0e477ba819f2339ab6b3923bd9742c0495139f958abd078da28d9b7e4a` | unchanged |

Target audit versions: Faster Whisper 1.2.1, CTranslate2 4.8.2, ONNX Runtime 1.30,
NumPy 2.5.3. The patch changes no model, VAD, threshold, decoder/inference argument,
YAMNet window, DSP setting, pitch/tempo, volume, microphone state or Agent policy.

## Two gates and response

Both gates are required:

1. Runtime config `conversation.recognition.diagnostics_enabled` must be the JSON
   boolean `true`. Absent/false is the unchanged production default. Use a private
   temporary config copy for the finite diagnostic container; saved config and
   thresholds remain intact. This does not require a config parser overlay.
2. That authenticated `/transcribe` request must include JSON `diagnostics: true`.
   Missing/false keeps exactly `ok`, `transcript`, `decision`. Nonboolean flags or
   a diagnostic request with the runtime gate disabled are rejected before model
   calls. The ordinary response's transcript/classification semantics are intact.

A requested diagnostic response adds `diagnostics` with the selected finite
numeric scores, prefilter category/skip, recognizer/Whisper invocation flags,
PCM/window frame counts and outcome. An invoked Whisper adds segment counts:
seen, accepted, rejected, rejected log-probability, rejected no-speech, accepted
empty text. Rejection-reason counts may overlap; the combined rejected count
counts each rejected segment once. Existing `avg_logprob >= threshold` and
`no_speech_prob < threshold` boundary behavior is preserved. Returned-generator
segments are consumed once; diagnostics do not rerun YAMNet or Whisper.

No diagnostic state is attached to `Pipeline`, history, `last_turn`, files or
logs. Diagnostics include no transcript, segment text, raw audio, base64, request
credential, model prompt or full sound-model result. Existing transcript fields
are still returned to the admitted caller; the finite harness must select ONLY
`diagnostics` for its report and discard the ordinary text/decision in RAM.
Existing unrelated transcript-logging policy is unchanged.

## Finite runner rollout and rollback

The sole hardware runner owns the actual compute-worker session and rollout.

1. Verify the actual three preimages and save the original two module bytes plus
   their hashes privately. Save the existing container/image/launch/config
   reference without exposing credentials. No raw audio/text in the bundle.
2. Run the read-only guard with the actual installed source directory and isolated patched bundle: `python stt_diagnostics_preflight.py --before-dir /app/src/reachy_companion --patched-dir /absolute/patched/reachy_companion`. It checks all three preimages, both postimages and syntax without imports or model calls. A mismatch exits nonzero; do not deploy. Export ONLY the two patched modules from the pinned reviewed commit into an
   isolated directory, verify the postimages above, and compile them without
   loading models. Reuse the actual existing worker image/dependencies and launch
   command with two read-only file overlays (or a minimal derived image containing
   just those two files); do not replace checkout/config with all HEAD.
3. For the finite diagnostic run, use a private config copy with only the boolean
   gate added, preserving its original config root/model/token resolution. Start
   the reviewed worker replacement under the existing service/ownership procedure.
   Verify authenticated readiness and the actual running module hashes; gates
   disabled and a normal request must still return the original response keys.
4. Use the existing admitted live capture fixture. Send its current RAM PCM once
   to `/transcribe` with diagnostics enabled; do not recapture, save WAV/PCM, emit
   full request/response or bypass the music filter. Select only the metadata in
   the finite receipt. Report whether Whisper was skipped, invoked with no
   segments, or invoked with all segments rejected. An empty result does not
   authorize forwarding room audio to the main model or count as voice acceptance.
5. If readiness/schema/hash/default behavior fails, stop the finite replacement
   through the existing runner procedure and restore the exact original image/
   two modules and original launch/config. Verify original hashes and readiness.
   After the finite run remove the overlays/private diagnostic config from the
   launch and restore the original worker. No Agent mic/policy/volume restore from
   an old snapshot; the current human state remains authoritative.

Local tests use synthetic RAM PCM and fake inference with actual NumPy 2.5.3.
They cover music skip versus Whisper empty on identical PCM, exact threshold
edges and overlapping rejections, identical default text/inference arguments,
single generator consumption, disabled/type gates and request-local privacy.
Dependency-free test runs use a frame-count stand-in only for stage tracing.
No actual target inference, audio capture or deployment has been performed by
this writer; the runner must verify the causal stage on the actual next round.
