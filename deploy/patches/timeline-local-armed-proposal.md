# Local timeline arming: offline proposal

This is a concrete source proposal, not an installed or accepted latency fix.
All expressive hardware trials remain held for the unresolved antenna incident.
No live configuration, SDK, target, torque, interpolation or limit is changed.
The exact installed ExpressionPlayer remains `7a5…`; Agent remains `cf50…`.

## Build and switch

```sh
python deploy/autonomous/prepare_timeline_armed.py /private/tmp/reachy-local-armed-proposal
```

The builder reads the public Git preimage, verifies exact source/patch/output
hashes, compiles one file and emits a manifest into a new directory. No application,
model or SDK is imported, no endpoint/device is opened, and no deployment method
is shipped. HEAD expression_player.py is unchanged.

The proposed optional setting is `conversation.expressions.timeline_gate`:

| Value | Meaning |
|---|---|
| absent or `completion` | Existing completion gate, unchanged default/fallback |
| `local_armed` | Explicit offline opt-in: current local scheduler ticket armed |

Unknown values fail before the consumer thread starts. Local arming requires the
existing stock transport/binding callback. A future separately reviewed activation
would need current sources, safety evidence and a guarded restart; changing a
dictionary/file alone is not a live switch. No activation is requested here.
Fallback is the preserved absent/`completion` setting or exact original `7a5`.
There is no automatic fallback from a stale/canceled local ticket to "ready".

## What changes in the proposed mode

The measured first-audio → first-write span was 0.931785 s; 0.926774 s was inside
wait_timeline. Exact `7a5` waits for `completed`, updated in finally after the
blocking expression HTTP call, including errors. This never proved SDK admission.
The aggregate can also contain previous processing work; its components are not
separately measured, so the proposal cannot promise to save the entire 0.927 s.

The single existing ExpressionPlayer consumer observes the validated timeline,
captures current binding outside condition, and arms an exact `(clock identity,
version, binding)` ticket under condition. `completed` remains separate and keeps
its old meaning. No second request thread, motion owner or queue is introduced.
The waiter rechecks current binding, permission, version, clock and stop state;
hold, supersession and withdrawal reject the pending ticket. Binding callbacks
never run under condition, preserving microphone-lock ordering.

Arming precedes waiting for a positive first cue timestamp. This allows the audio
SpeechClock to start before an at>0 cue becomes due. It does not send that cue
early. If an old processing HTTP call is still running, this same consumer cannot
arm the new timeline until the call returns: that residual wait remains.

Armed means **local scheduler ready**. It does not mean HTTP submitted, Hub accepted,
SDK task registered, physical movement started, a pose reached or audio consumed.
A subsequent Hub rejection can occur after local arming. Existing Hub operator /
expression-version guards, owned UUID/watchdog, payload and completion/cancel
path are unchanged. Audio and cue timing could change if this proposal is ever
opted in; antenna target generation and SDK behavior are not modified by it.

The waiting budget is computed once from the existing HTTP/max-total bounds.
Condition waits remain bounded polling. Current binding callbacks use existing
synchronization and are not made preemptible by this proposal; no hard physical
STOP/P95 or OS scheduling guarantee is claimed.

## Evidence and next boundary

Offline request stubs test default/fallback payload and operation parity, local
arming before HTTP completion/rejection, separate completed, first tick>0, old
processing work, exact clock identity even for equal clocks, hold/cancel,
boot/mic/policy changes, permission withdrawal, stop, invalid binding/steps and
single-consumer request ownership. They do not send SDK/motor/HTTP requests.

Independent source review is pending. No antenna diagnosis, remote-admission
acceptance, audible overlap or latency improvement follows from these fixtures.
Further implementation/installation/hardware trials require a separate agreed
evidence packet; this proposal does not lift the antenna incident hold.
