# Capture-step diagnostic on the exact spoken/explicit camera helpers

One real human request on the installed Agent route observer established:
STT nonempty, exact visual match, no own echo, action allowlisted and dispatch
attempted. The child returned typed `phase=capture,error_class=ValueError`.
The STT/intent route is working for that request; spoken camera remains **FAIL**
and scene correctness is untested. This does not establish a specific camera,
SDK or frame failure. The capture phase contains several independent guards and
SDK/NumPy calls that can raise ValueError.

Both paths use the same helper's `caption_checked` and `capture_png`. Explicit
watch and spoken dispatch select the existing `/venvs/mini_daemon/bin/python`.
The spoken packet contains network/llm config only, but capture_png reads no
config. Both bind parent lifetime. Their authority callbacks intentionally
validate different OFF/watch versus ON/same-owner states; the real typed capture
failure occurs after the pre-capture callback passed. None of these source
facts identifies which capture guard failed, or proves identical runtime import
context. Do not remove the audio-import guard or change SDK/camera settings.

This checkpoint adds fixed substage names inside capture_png and adds those
names to the existing spoken helper phase allowlist. No new endpoint, diagnostic
payload field, retry, camera framework, transcript handling or raw data export.
The existing three-field child error and Agent289 status observer carry the new
phase automatically after one helper-refresh restart. No Agent source change.

| Installed source / destination | Exact preimage SHA256 | Reviewed output SHA256 |
|---|---|---|
| `deploy/autonomous/demo_vision.py` copied as existing Robot `snapshot_vision.py` | `1bd06dec8f941a78f0519e090e3a54cbc5816f5485fbb83ddd348e1830d0ef3f` | `d43a70cc1e3b3846cb163f8b772c9af2b13a08aefac2c4279f6197b68b974c13` |
| `src/reachy_companion/spoken_vision.py` | `242ac03560af18c042ddef39fa2eb0eb343aa4c9dcb13e99a31e5eda3c134c69` | `486cfb8f23c9d9d5797910eab6ebf3143e64f1cfe4a686b4f50fe38db975a025` |

Keep installed Agent exactly
`289469a5de57f01295e6c8ddde3e78ba2804fe2f5e6c603a4789e3d70e6ebeb9`.
Do not deploy HEAD Agent, worker/brains, new SDK, model or configuration.

Fixed capture phases identify the failing operation/guard:

- capture_import: NumPy / SDK camera imports, including errors from imports.
- capture_sdk_version: installed SDK metadata/version must equal 1.11.0.
- capture_no_audio: audio_gstreamer must be absent from this child's sys.modules.
- capture_specs / capture_construct / capture_open: existing wireless specs,
  camera constructor and open call.
- capture_sample: existing two-second bounded sample pull, nonnull guard and
  sample buffer retrieval. No extra wait or sample retry is introduced.
- capture_caps: caps access and exact 1280×720 BGR guard.
- capture_buffer: exact existing byte-count guard.
- capture_extract / capture_pixels: byte extraction and NumPy reshape/downsample.
- capture_encode / capture_png_bound: existing PNG construction and 1 MiB cap.
- capture_close / capture_closed: close and existing pipeline-NULL check.

Success restores the old generic capture phase for the remaining payload work.
The first failed capture phase/class survives a second cleanup exception. The
close and NULL checks are still attempted. A cleanup-only failure reports its
own phase/class. If both fail, the original capture error is reported; it does
**not** certify successful cleanup or expose the second error's message. The
child still exits unsuccessfully, and normal runner cleanup remains mandatory.
The camera-close-before-inference rule, fresh-frame admission ≤2 seconds,
operator-read age, 50-second child limit, 40-second native request timeout,
60-second frame speech expiry, parent lifetime, privacy/owner/epoch checks and
FINAL-only filtering all remain. No failed capture can proceed to image POST.

Only the sole runner installs after coordinator source review in a fresh idle
window: known OFF/unowned/free, capture/listening false, no active PC stream,
camera/owned aplay/controller, volume API/saved/ALSA 100%. Verify exact preimages
and retain private two-file backups with owner/mode and config/unit/persisted
state checks. Atomically install only the two reviewed helper files. Restart
only reachy-voice-agent.service once: the parent has already imported the phase
allowlist. Verify exact output hashes, unchanged Agent hash and configuration,
new boot/readiness, authenticated capability/status and denied unauthenticated
access, strict operator shape, initial vision_route null, OFF/unowned/free,
no camera/aplay/controller and unchanged 100% volume. On failure keep OFF and
restore only these helper preimages in a verified idle window, preserving any
newer operator. Worker, model, Hub and factory receive no restart or migration.

Installation does not authorize an automatic image retry or a new human trial.
Coordinator/runner first review the fixed-stage checkpoint. In the next expressly
coordinated bounded attempt, collect only the restricted phase/class and routing
booleans before generation-changing cleanup. If a capture_* stage fails, fix
that proven source before another attempt. If it succeeds, require the actual
fresh image, human-correct spoken FINAL and normal owned cleanup; absence of an
error is not scene acceptance. Do not keep adding general diagnostics after the
specific failing operation is known.

Local validation: 53 focused checks PASS across capture stages, existing explicit
vision, spoken helper and exact Agent observer. Tests cover all guard families,
SDK and NumPy ValueError, unchanged PNG RGB output, first failure surviving a
second cleanup error, cleanup-only failure, real child subprocess phase/class
framing and the installed Agent observer accepting a new phase, with no private
exception text. AST checks prove only capture_png and ERROR_PHASES changed from
exact installed preimages. These are source/stub checks, not a real camera fix
or hardware acceptance.
