# Minimal bound snapshot speech overlay

`reachy-agent-0a7-bound-vision-speech.patch` targets only the installed Agent from
Git `2865db30e92fcb069c241c34bae4419ad65ed594`, not the current HEAD Agent.

Exact original `agent.py` SHA256:
`0a7c0a3d7cbd542eabf9412291fda052c559db8c6bac123db31676b0137bd908`.
Exact patched SHA256:
`53a43647c4744dde3c7b112d12212477943ce22f9f33b90ffbeeb916d28f23c3`.

This overlay has not been applied to a device by its publication. Reject a
different preimage and do not combine it with the separate latency overlay by
fuzzy application. Default/manual voice behavior and existing ownership,
microphone, privacy, quiet, volume, factory SDK, motion and STOP paths remain.

The only Agent changes are:

- An authenticated read-only `/vision-capabilities` reply with version 1 and
  the current Agent boot. Both snapshot capture and the Hub client require it,
  so an old Agent cannot silently ignore the new speech binding.
- Optional `operator_binding` on the existing `/say` manual request: exact
  boot, microphone epoch, policy epoch, shared owner and Robot monotonic expiry.
  Both owners must still match, microphone permission must be ON with capture
  and listening OFF, policy must allow motion, and quiet/privacy must be OFF.
  Validation runs before and after the existing audio lock. Other fields or
  use on `/ask` are denied; there is no second main inference.
- Optional fixed expected policy epoch/expiry in `voice()`. Existing epoch,
  microphone and quiet/privacy cancellation stays active. The fixed policy
  epoch prevents a late caption from adopting a newer operator's policy.

The finite result's expiry originates on the Robot where the frame was dequeued.
The Mac and Hub transport it unchanged; they never subtract clocks across hosts.
No more than 60 seconds of future snapshot speech validity is accepted. This
does not certify sensor exposure freshness or exact physical stop latency.

Minimal device update, through the sole runner in an idle OFF/unowned window:
retain the exact Agent preimage and apply only this Agent file, then restart only
`reachy-voice-agent.service`. Verify readiness, new boot, microphone/policy OFF,
factory free/known and the current volume (100% is supported and retained).
Replace only `src/reachy_companion/client.py` on the Hub with this feature's
reviewed revision; no Hub service/worker/router restart or config/model change
is needed for that CLI file. Rollback restores those exact preimages; do not
roll volume or a newer operator back. The Mac uses the repository's reviewed
watch/camera source per fresh owned run; it does not import a historical `/run`
trial or require persistent extra robot services.

The command is `scripts/companion-demo --vision --seconds 180`, with the same
existing private config and robot known-hosts option as the regular demo. Normal
voice mode is unchanged. The camera/inference child has a 50-second process
bound and native HTTP response bound of 40 seconds, one request per plan and
Linux [parent-death termination](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html).
It uses installed SDK 1.11.0 camera-only IPC and numpy, already exercised on
the device; nothing is downloaded. The original independent watch remains
responsible for owned OFF cleanup and admission retirement.

Acceptance is a real fresh scene-to-FINAL-to-existing-speaker run, followed by
human correctness confirmation without putting the expected object in the
prompt. A separate longer reply must prove STOP during owned aplay, bounded SDK
motion, no spontaneous resume, known OFF cleanup and volume preservation. Local
tests and a nonempty caption do not establish those physical/semantic gates.
