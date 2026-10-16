# Exact Agent9a visual-route observation overlay

The last real human turn completed owned cleanup, but its final STT did not
establish the exact visual intent and no child or typed failure was observed.
Camera acceptance remains **UNKNOWN / NOT PASS**. This evidence does not
establish what the human said or why recognition/routing differed.

Apply only `reachy-agent-9a-vision-route-observation.patch` to installed Agent
SHA256 `9a4269f757bdc90d5da33cd9ccfa1d302c53a21fae4452d9d6bcdc4a5f578840`.
Output SHA256:
`289469a5de57f01295e6c8ddde3e78ba2804fe2f5e6c603a4789e3d70e6ebeb9`.
Do not migrate HEAD Agent. Preserve helper
`242ac03560af18c042ddef39fa2eb0eb343aa4c9dcb13e99a31e5eda3c134c69`,
shared camera
`1bd06dec8f941a78f0519e090e3a54cbc5816f5485fbb83ddd348e1830d0ef3f`,
and Hub client
`adc324fc93ec4dfc1d88249deaa4a7925e8d44e92dc15946877cef574fac1c4f`.

Existing authenticated `/status` gains optional `vision_route`. No endpoint,
`/operator` field, grant, intent rule, child protocol or deployment framework is
added. The observation is replaced after each nonempty accepted capture, before STT,
including pending interruption input. While waiting for the next phrase, the
previous completed observation remains available in its original generation. A fresh normal STT turn records five booleans before dispatch:
`stt_nonempty`, `normalized_exact_visual`, `own_echo_match`,
`action_allowlisted`, `route_attempted`. Exact visual means the **existing**
bounded `matches(text)` policy, including its quote/length/prefix restrictions;
it is not a substring match. Own echo compares that result with the existing
`matches(text,current_reply_text)` gate. Action allowlisted means one of
answer/stop/pause/reset; only answer can enter the visual route.

Fixed `stage` values are capture/stt/action/route/dispatch/interrupted. Fixed
`result` values are pending/empty_stt/nonmatching_stt/action_rejected/
echo_rejected/eligible/returned/typed_child_failure/untyped_failure/
existing_interruption_path. `route_attempted` means dispatch was entered;
it does **not** prove that a child launched, an image was taken or speech played.
`returned` means dispatch returned, not independent camera/speech acceptance.
Pending means that stage has not produced an observed result, including errors
before classification; false flags at a pending stage do not prove rejection.
Interrupted input retains its existing route and is explicitly identified;
the fresh visual matching flags are not evaluated for that branch.

Typed child failure fields `child_phase` and `child_error_class` are copied only
when the exception is exactly RuntimeError with exactly the existing helper's
complete allowlisted phase/class message. Otherwise they remain null and result
is untyped_failure. No exception message, transcript, reply, classifier value,
image, HTTP body, model identity or secret enters the new record. Legacy status
fields retain their prior behavior; this does not make the whole status payload
safe to publish. No new logging is introduced.

The record is internally bound to the captured boot/microphone/policy generation.
Status returns a copy only while all three match its current envelope; otherwise
null. It also returns null before the first turn. Read the restricted diagnostic
**before** mic/policy withdrawal/cleanup if the current generation's evidence is
needed. Do not restore an old generation to expose it. No old turn is adopted
into a successor generation. Only the latest turn is retained, with constant
field count and bounded allowlisted values.

Reproduce the exact output locally from pinned public Git sources and all three
sequential overlays (no fetch, device access or HEAD Agent copy):

```sh
PYTHONPATH=src:tests python3 -B -c 'from pathlib import Path; from test_agent_vision_route_observation import candidate; Path("/private/tmp/Agent-vision-route-reviewed.py").write_text(candidate()[1])'
shasum -a 256 /private/tmp/Agent-vision-route-reviewed.py
```

Only the sole hardware runner installs in a fresh verified idle window, after
coordinator review and without overlapping a PC stream or another device owner:

1. Verify the exact installed preimages above. Preserve the private Agent backup,
   configuration, service, persisted mic/policy state and volume checks. Require
   known OFF/unowned, no capture/listening/camera/owned aplay/controller, factory
   known/free and volume 100%. Do not change epochs to match historical values.
2. Verify generated output hash, atomically replace **only Agent**, preserving
   owner/mode, and perform one guarded `reachy-voice-agent.service` restart.
3. Verify the new exact Agent hash, retained helper/camera/client hashes,
   readiness/new boot, authenticated capability and status, unauthenticated
   denial, unchanged strict `/operator` shape, and `vision_route:null` before a
   turn. Verify config/unit/persisted states unchanged, OFF/unowned/free,
   capture/listening false, no aplay/camera and volume API/saved/ALSA 100%.
   On failure remain OFF and report UNKNOWN; restore only the backed-up Agent in
   an idle window without overwriting a newer operator, then check readiness.
4. The runner/coordinator owns any subsequent bounded human turn. Collect only
   the new record with the corresponding generation privately before cleanup;
   distinguish nonmatching STT, action/echo rejection, dispatch attempt and typed
   failure. Do not infer human wording, child launch or camera success from a
   boolean. Preserve normal owned cleanup and do not automatically retry.

Local validation: 41 focused tests pass across this overlay, spoken helper and
bound speech overlay. These exercise real legacy run/status methods, rejection
and successful routes, interrupted input, exceptions before last_transcript is
assigned, exact typed vs forged/private errors, per-turn reset, generation
invalidation, copied status and unchanged code outside the allowed methods.
This is source validation; installation and human camera acceptance are pending.
