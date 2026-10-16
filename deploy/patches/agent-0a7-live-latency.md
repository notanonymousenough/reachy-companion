# Finite metadata overlay for the installed Agent

Review-only `reachy-agent-0a7-live-latency-metadata.patch` changes only the exact
installed `agent.py` from Git `2865db30e92fcb069c241c34bae4419ad65ed594`.
It does not install the current HEAD Agent, change a worker, replace a model,
introduce a playback backend or alter ownership/STOP/motion/volume controls.
Nothing here has been applied to a device by the source change.

Exact preimage SHA256:
`0a7c0a3d7cbd542eabf9412291fda052c559db8c6bac123db31676b0137bd908`.
Exact patched SHA256:
`006c1f5b61553bbb35a0f694be8c084e1b11e1ef3589f2542bc43aa0994ef1b4`.
Reject a different preimage; no fuzzy application or full checkout migration.

The existing installed Config accepts a new optional logging key without a
Config/module migration. Only literal `logging.live_latency_metadata=true`
arms the probe; missing/false remains off. The older `latency_diagnostics`
setting does not accidentally activate it.

For one finite activation, the sole runner uses a reviewed OFF/idle window,
retains the original source/config and checks microphone, policy, volume and
factory state. Apply only the pinned Agent file and temporarily enable that
single logging boolean. Restart only `reachy-voice-agent.service`, verify its
new boot/readiness while still OFF, then restore the exact original config
bytes **before unmuting, without a second restart**. The running Agent already
copied its bounded opt-in to RAM; a later crash/restart reads the restored
default-off config and does not rearm it. Preserve the current operator volume
(including 100%), microphone/quiet/privacy state and existing control guards.
Actual application/rollback is a separate runner action.

The window begins at the first eligible normal live capture after listening
starts. At most three capture attempts are admitted to metadata collection
within 60 seconds. No timer, observer thread or extra audio owner is created.
A slow in-flight attempt may produce its one final record after the window,
but later stage marks/counters are omitted and its outcome is `expired`, so it
is not a fresh latency sample. No additional attempts are armed until a new
explicit activation. Startup greeting, manual speech, replay and pending
barge-in/resume inputs do not receive a fabricated normal-capture trace.

Each attempt has one random local identity and one fixed record (under 2 KiB):
Agent boot/epochs, last VAD-positive chunk **reception**, accepted endpoint
decision, capture return, ACK versus FINAL reply/write marks, cumulative byte
counts and FINAL stream offsets, outcome and exception class only. The first
positive pipe write records before/after times; odd partial writes retain
cumulative bytes before deriving complete frames. Marks are relative to the
same Robot monotonic clock. The first loud chunk is included. No audio, text,
text/audio digest, prompt, token, error body or worker-global `last_turn` is
stored in the new record. Existing logging policy is otherwise unchanged.

The ACK flag already present in the same NDJSON response separates an
acknowledgement from the later FINAL without changing the worker protocol.
First FINAL submission is distinguished from the earlier ACK/aplay process
start. A positive pipe write proves submission only. Existing `SpeechClock`
is a wall-time estimate; the patch explicitly reports
`consumption_verified=false` and `acoustic_e2e_verified=false`.

The result is a software latency proxy from VAD-positive chunk receipt through
endpointing to first FINAL audio submission. arecord buffering means receipt
is not verified acoustic speech end. Playback buffering, resampling and TTS
leading silence mean submission is not verified audible onset. Actual owned
hardware-consumption timing remains unknown until the runner proves a usable
aplay-associated cursor and its frame mapping. This instrumentation does not
block the working human voice/context/motion/STOP path or the next camera step.
