# Bounded diagnostic for the actual spoken snapshot failure

The deployed `02bdaa2` spoken route failed on a real request after launching
its snapshot child. Ordinary speech still worked. This is not a successful
vision/context acceptance. The concrete child cause is **unknown**: the old
child discarded its exception, and the parent checked return code before
reading stdout. A later watch withdrawal/cleanup error is a separate event and
does not establish the original child cause.

This change adds diagnostics only to `src/reachy_companion/spoken_vision.py`.
Agent remains byte-identical SHA256
`9a4269f757bdc90d5da33cd9ccfa1d302c53a21fae4452d9d6bcdc4a5f578840`.
Installed `snapshot_vision.py` remains byte-identical SHA256
`1bd06dec8f941a78f0519e090e3a54cbc5816f5485fbb83ddd348e1830d0ef3f`.
Do not apply any Agent patch, change config/model/worker or rerun an image as
part of installing this diagnostic.

The helper preimage SHA256 is
`7b6589136989652079cdcbb55e774272f59422a05bd3442eca505ce0f8259ded`.
The candidate helper SHA256 is
`242ac03560af18c042ddef39fa2eb0eb343aa4c9dcb13e99a31e5eda3c134c69`;
the runner must verify the exact reviewed bytes before use.

Child failure stdout is one bounded JSON object with exactly `kind`, `phase`
and `error_class`. Phases distinguish import, parent lifetime, packet parsing,
packet validation, model inventory, operator checks before capture/image send
and after inference, camera, image admission, native inference and FINAL parser.
Unknown phases/classes become fixed fallbacks. There is no exception message,
traceback, HTTP body, transcript, caption, image, model ID or token in the new
diagnostic. Stderr remains discarded. Successful snapshot protocol is unchanged.

The parent parses/validates a typed failure **before** checking return code or
current authority: reporting a failure cannot actuate anything, and a later
watch withdrawal must not erase its cause. A successful result still requires
the existing final same-owner/epoch/privacy/deadline check before speech. The
parent includes only allowlisted phase/class in its fixed RuntimeError; malformed
or extra diagnostic fields yield a generic error without reflecting values.
No timeout, image, model, capture, ownership, STOP, volume or retry behavior is
relaxed. There is no new automatic retry or collection of stderr/raw data.

Only the sole runner may install, after ROOT's source review and a fresh known
OFF/unowned/free/no-camera/no-aplay/no-controller check with volume 100%:

1. Verify all three installed source hashes above and preserve the exact private
   helper backup plus config/profile/service/persisted state/volume checks.
2. Atomically replace **only** the helper with the exact reviewed candidate,
   preserving owner/mode. Restart only `reachy-voice-agent.service` once so its
   imported helper is refreshed. Do not replace Agent or shared camera source.
3. Verify exact hashes, readiness/new boot, authenticated capability and denied
   unauthenticated access, microphone/policy OFF/unowned, capture/listening OFF,
   config/profile/unit/persisted states unchanged, factory known/free, no owned
   aplay/camera and volume API/saved/ALSA 100%. On failure retain typed UNKNOWN
   and OFF; rollback only the helper in a verified idle window, preserving a
   newer operator. Do not silently change Agent epochs or restore old volume.

Installation readiness is not permission to retry the camera. First use existing
read-only failure evidence and the diagnostic source review. If one new bounded
attempt is subsequently authorized, capture only the allowlisted failure fields
and existing cleanup evidence; no automatic second attempt. Resolve the proven
cause before claiming spoken vision, human scene accuracy or context acceptance.

Local checks exercise the actual helper entry point in a subprocess with a
synthetic snapshot module, not hardware: capture/import failures produce only
phase/class with rc1 and empty stderr; the parent reports typed errors despite
rc1 or a later authority withdrawal; private strings/extra fields cannot escape.
These checks do not diagnose the actual device failure.
