# S1: continuous input through the existing mono AEC owner

Source-only opt-in checkpoint. Nothing in this checkpoint installs files,
changes a private configuration, restarts a service or opens a device. The
current c2fc timing trial remains the next physical measurement; S1 is independent
preparation and does not replace it. Partial STT is the later S2 increment.

Independent source reviews accepted the frozen candidate after two P1 fixes:
quiet/privacy withdrawal runs before reap even if reap blocks/fails, and both
source-error event outcomes use one bound wake handler. All 38 focused checks
passed (29 S1 checks plus 9 existing timing checks). This is source acceptance;
continuous hardware, AEC, latency and partial STT acceptance remain open.

## Exact bundle and activation boundary

Build locally into a new directory:

```sh
python deploy/autonomous/prepare_capture_pump.py /private/tmp/reachy-S1-review-bundle
```

The builder reconstructs public c2fc through its existing exact overlay chain,
reads the public Git preimage of barge-in, verifies every input/patch/helper/output
hash and compiles three outputs. It refuses an existing destination. It imports
no Agent, STT backend, device SDK or model. `manifest.json` records the hashes and
required unchanged installed dependencies. HEAD Agent is not an installation input.

| File | Installed preimage | Candidate output |
|---|---|---|
| Agent | `c2fcb832501c55dd56a86abd7b87c71b05c013f968a2482dbfc1a27d3283f2f5` | `cf50c54680d8e30fb97090e80d0e687a9dad903159f464d2211414aefcaca069` |
| barge_in.py | `3761dffb2daeee06bb3402618d98a0e8f68d4d67f3b5e77b5fb9a03e5143047f` | `28831114f2cf0f60f47d3bdd77c4f8d120b6447101ff5adc56df46204eb247bf` |
| capture_pump.py | New bounded helper | Builder's frozen `HELPER` pin |

Fresh installed public source receipts verified the preimages and dependencies;
notably installed microphone.py differs from HEAD. Keep installed microphone,
motion policy, config, SoundMonitor and spoken-vision helper unchanged at the
manifest pins. Recognition is untouched: its fresh installed source also differs
from HEAD. Distribution metadata reports faster-whisper 1.2.1, ctranslate2 4.8.2
and vosk 0.3.45; actual configured backend/device/rate were not read. These version
strings are not proof of the active backend or hardware behavior.

The only new switch is optional `conversation.capture_pump_enabled`, default
`false` when absent. It must be a literal boolean. Enabling requires the existing
streaming and barge-in switches and STT confirmation all literal `true`, with the
existing 16 kHz capture format. No example configuration/profile/default is changed.
Preserve the existing capture device and AEC path; the command remains mono
S16_LE arecord, not the stereo autonomous libasound adapter.

Future activation requires separate review of this exact bundle and a fresh
single-runner installation/rollback package. Preserve protected configuration,
mute/volume, owners, unit/camera bindings, factory and current source witnesses.
Default false must first reproduce the old behavior. A guarded activation may
then opt in using the existing private configuration mechanism. No broad HEAD
migration or backend/model switch is part of S1. Rollback restores exact c2fc and
3761 sources and the preserved configuration; an unused helper cannot activate
capture by itself.

## Ownership, freshness and control

One owned arecord and one reader drain PCM across ordinary idle, phrase, STT,
model inference and APLAY. `capture()` is a final-utterance consumer; the original
finite capture body remains unchanged for default false. One assembler owns
calibration, pre-roll, RMS/VAD, probe and final revisions. A final can be claimed
once; one latest event supersedes previous pending work. Returning to idle clears
unconfirmed reply tail. Buffers use the existing maximum recording duration.

The reader does no HTTP, classification, expression action or interruption
callback. It may enqueue through the verified bounded SoundMonitor.feed; that
existing worker owns sound classification. A single barge control consumer starts
before the model HTTP open and uses the existing echo/STT confirmation logic.
Previous still-active control work blocks a new consumer, capture request and
voice attempt; no timeout starts a duplicate unknown STT request. Freshness is
checked before and after blocking confirmation and immediately before effects.
Spoken STOP uses the existing boot/epoch CAS, preventing an old confirmation from
withdrawing a newer microphone grant. Default-false barge behavior is preserved.

Packets carry boot/mic/policy, source generation, utterance number, revision,
original monotonic read receipt and deadline at most two seconds after it.
Final supersedes probe; a newer revision/utterance/grant retires old work. Main
STT results and pending barge PCM are checked against the original binding and
deadline before model dispatch/turn commit. Copying, queuing and a long model
drain never refresh the deadline. The reader fails closed on receipt gaps or a
backlog with unknown age. Restart requires a new source generation.

Read receipt is explicitly **not hardware capture time**. The gap/backlog checks
cannot prove absolute acoustic age. No hardware consumption or latency claim is
made by a read, flag, pipe write or process observation.

OFF/STOP retires the source and clears assembler/mailbox PCM immediately. Reap
occurs outside microphone_lock, including persistence failure. Only the owned
arecord is terminated; no process-name kill or second owner is introduced. A
failed reap remains an error and cannot silently create another reader.
Primed listen=false creates no reader, including while playing a prepared cue.

## Preserve working spoken camera

Before spoken visual dispatch, retire, clear and reap the pump; capture_active
then truthfully becomes false. The unchanged helper486 guard remains authoritative
through its child checks. A current granted voice call after the child has returned,
or the dispatch return path, may resume with a new source generation. Withdrawal,
privacy, STOP or a newer policy/mic epoch prevents resume. There is an explicit
hearing gap during the camera child; no full continuous vision-hearing PASS is
claimed. A failed reap cannot be hidden by changing capture_active.

## Verification and remaining real acceptance

Focused fixtures use synthetic PCM, fake process pipes and bounded waits. They
cover single reader/process through phases, bounded VAD/final once, latest
revision, two-second expiry and a 40-second drain, source/grant invalidation,
gap/backlog retirement, slow STT without reader blocking, stale confirmation,
existing echo rejection, boot/epoch STOP CAS, unknown control exclusion, OFF
reap outside the microphone lock on success/error, camera quiesce/current-grant
resume, default voice/finite-body parity and primed playback without capture.
An actual Agent.run fixture rejects an expired STT result before model/turn commit.
Model-open failure joins the early control subscriber.

Real acceptance remains separate: same owned arecord PID across idle → inference
→ APLAY; fresh near-end input during inference and playback; onboard AEC/no own
speech trigger; STOP/OFF reap and no resurrection; expired queued speech after
drain discarded and a fresh next utterance works; correct spoken camera with
honest quiesce; final known OFF/free/factory empty/100/no APLAY/camera. These are
not established by the fixtures. Partial-before-endpoint is explicitly S2.

S1 changes Agent's source hash and moves monitor start before model open. The
current c2fc-hash-pinned timing consumer must not be used unchanged for this new
candidate: a future paired consumer/observer must pin the exact new source and
accept the true monitor timing order without weakening schema/generation checks.
The existing physical measurement package stays on c2fc until separately reviewed.
