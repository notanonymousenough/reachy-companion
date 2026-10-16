# S2: bounded recognize-only windows on the loaded recognizer

Source-only, default off. No deployment, model load, device access, configuration
change or partial/acoustic acceptance is performed by this checkpoint. S1 remains
installed with its capture option off. Its next physical measurement/acceptance
is independent of this preparation.

Independent tester and architecture reviews accepted the final frozen source.
All 33 focused checks passed, including real localhost framing/deadline cases,
cooperative cross-process namespace serialization and bounded lock cancellation.
This is SOURCE ACCEPTABLE, not deployment, partial STT/AEC or latency acceptance.

## Exact build and prerequisites

```sh
python deploy/autonomous/prepare_provisional_stt.py /private/tmp/reachy-S2-review-bundle
```

The builder produces separate PC and Robot directories and one manifest; it
refuses an existing destination. Every public input, patch, helper and output is
hash pinned and compiled. It reconstructs the fresh installed recognizer `6211…`
through a public patch from Git `b79a…`, then applies S2. The other exact bases are
the selected reviewed streaming voice `bbdb…` and published S1 Agent `cf50…` /
capture helper `b7b1…`. The PC's currently restored baseline is not claimed to be
that streaming candidate. Keep the selected bundle's brains `020e…`, token helper
`a4aa…`, S1 barge `2883…`, config, microphone, camera and other dependencies at
their reviewed pins. Neither HEAD Agent nor HEAD recognition is a rollout input.
The existing S1 builder remains reproducible without S2.

The shared helpers are a strict provisional contract/client and a small stdlib
owned HTTP transport. The transport body is derived from `a4aa`'s accepted
`owned_response`, with only an explicit resolved-target argument replacing its
registry lookup. The builder checks AST equivalence. Robot imports no LLM token
producer, endpoint registry or model control. Existing a4aa is not changed.

The only new option is `conversation.provisional_stt_enabled`, absent = false,
literal boolean only. Robot requires S1 capture pump opt-in too. PC recognizes
the new request only when its option is true, capture rate is exactly 16 kHz,
and the recognizer records that its already loaded backend is faster_whisper.
No mode changes a backend or loads a model. Fresh installed distribution versions
were read, but private backend/device/rate configuration was not; activation must
verify it rather than infer it from library availability or example settings.

Future activation needs a separately reviewed single-runner installation,
readiness, exact preimages/config preservation and rollback package after S1
actual acceptance. This builder does not install or opt in. Rollback returns to
the preserved S1/selected worker/recognizer source and private options. An unknown
intent marker must survive rollback/reload until its own work is authoritatively
resolved; deleting it is not a routine startup action.

## Authenticated schema and compute admission

The existing authenticated `/transcribe` endpoint gains a strict `recognize_only`
mode. Reserved provisional fields are detected before the legacy transcription
path, so a malformed/missing mode cannot fall through to classification. Its JSON
parser rejects duplicates/nonfinite values and its schema rejects unknown/missing
keys, bool-as-int counters, wrong types, PCM lengths and window bounds. Legacy
ordinary PCM/diagnostics requests retain their existing final path.

Request keys are exactly `mode`, integer `version=1`, `binding`, `pcm_base64`.
Binding contains boot, mic/policy epochs, source generation, utterance ID, revision,
unique request ID, window origin and frame count. PCM is mono S16_LE/16 kHz,
0.4–4 seconds, at most 128000 bytes. Response keys are exactly mode/version/binding,
literal `provisional=true`, recognized/busy status and bounded text (1600 chars).
The binding must match exactly, including request ID. Busy has empty text and
means this request did not invoke recognition; it does not establish that some
older unknown request has completed.

This branch calls only the existing loaded recognizer. It bypasses SoundEvents,
Pipeline.transcribe, intent/classification, LLM, TTS, actions, history and memory.
The recognizer's model decode body and startup/model options are unchanged; both
ordinary final and provisional use the same model object and lock. Provisional
acquisition is nonblocking: busy returns immediately, without a handler queue
behind the recognizer lock. Ordinary final keeps its existing lock path. No
provisional client code ever sends a final request or commits an utterance.

## Robot cadence, final and freshness

S2 is an exact layer on S1, not a replacement reader. The PCM reader offers at
most one rolling window per 0.5 seconds after 0.4 seconds of input. A separate
consumer owns one active HTTP request and one latest pending snapshot. Snapshots
use the same utterance number but their own partial revisions; S1 main/probe/final
mailbox, VAD endpoint and final claim remain unchanged. Final dispatch remains
one ordinary full-utterance request through S1. Partials never drive barge-in,
STOP, visual routing, answer generation or conversation state.

New input, revision, window origin, grant/source generation, endpoint or withdrawal
invalidates old partial results. Stable prefix requires two consecutive accepted
revisions for the same utterance and window origin; a moving window resets it.
This is bounded re-decoding of windows, not native online Whisper. Original read
receipt/deadline stays immutable (at most two seconds); queue/copy/HTTP completion
does not refresh it. There is no Robot/PC clock subtraction and read receipt is
not verified hardware capture time.

Only internal RAM holds provisional text. Optional Agent status exposes bounded
counts/timestamps and boot/mic/policy/source-generation binding, not text or PCM.
It separately reports provisional unknown state. Old status rows must not be
joined to a different generation. Endpoint, rejection, mode change and retirement
clear pending/results; unknown completion prevents resubmission across utterances,
source generations and Agent reload.

## Durable unknown and STOP boundary

Before POST, the partial consumer exclusively creates a fixed intent marker under
the existing data directory. It contains only bounded binding/request ID, target
classification and original receipt/deadline, no URL/token/audio/text. Parent and
file opens use nofollow, ownership/mode checks; the file is 0600, fsynced with its
directory. Identity, digest and request ID witness that exact owned intent.
Preexisting, partial, symlink or replaced markers are never adopted/cleared.

Only a strict response for this same request, or authoritative local proof that
the POST was not made, removes its own exact marker and fsyncs the directory.
Late completion cannot delete a replacement published through the supported namespace protocol. Timeout, unknown transport,
bad schema/binding or write failure retains unknown and never triggers a retry.
Reload sees the marker and remains blocked; no timer or new source clears it.
Recovery is a separate operation requiring authoritative resolution of the old
work, not a busy response for a different request.

All supported intent begin/complete operations hold an exclusive flock on the
fixed, nofollow-validated data-directory inode. Future separately reviewed recovery
must use this same namespace guard and its own authoritative old-work proof.
Acquisition uses nonblocking flock attempts bounded by the original item deadline
and a cancellation capability; it never starts a fresh two-second budget. Begin
uses current input authority. Completion uses the original stored deadline and
its owned request-ID cleanup capability, which does not grant new input authority.
If completion cannot acquire within that budget, the marker stays unknown.
There is no named lockfile to unlink/recreate or split across workers/restarts.
A new intent either exists before old completion takes the guard (old FI/digest
is rejected), or waits until that completion has removed only its own marker.
The protected data-directory inode must not be replaced while work exists.

This is a cooperative protocol, not an atomic conditional unlink against an
arbitrary same-UID filesystem writer. Direct rm/os.replace that ignores the guard
or replaces the protected parent is outside the contract; it cannot be made safe
by advisory flock. No such recovery operation is exposed or performed here.

Retiring an unresolved active consumer immediately blocks new-generation consumer
startup. Only its authoritative own completion/no-POST cleanup can resolve that
block; canceled lock wait does not create further waiting workers.

The reader and STOP never fsync or wait on HTTP or the namespace flock. Kernel
filesystem calls such as fsync cannot be preempted by this Python deadline; that
OS limitation is kept in the consumer and is not a new request budget. Withdrawal clears the mailbox
immediately and S1 reaps its reader independently. A departing partial consumer
can finish its already owned request under the original deadline; an authoritative
same-request completion may retire its own marker, but cannot publish a stale
result. The copied socket watchdog bounds connect/headers/body, caps response
bytes and closes on cancellation. Acceptance also requires full HTTP framing:
exact Content-Length consumption or natural EOF for a close-delimited body.
All Transfer-Encoding is unsupported and rejected, including valid chunked and
zero-chunk responses missing the final trailer CRLF. The selected worker emits
explicit Content-Length; no permissive stdlib chunk parser is used for acceptance. Truncated framing, even with a valid JSON prefix before
deadline, retains unknown. Deadline is checked again after body read and JSON
parsing; neither truncation nor trickle extends the original budget.

## Evidence and remaining acceptance

Fixtures cover strict schema and binding, loaded-backend/default-off rejection,
no classify/LLM/sound/history changes, failfast busy/shared model lock, unchanged
decode/startup code, cadence/latest queue/revision/origin, original TTL, final
once, marker exclusivity/fsync/reload/symlink/FI/digest/partial write, timeout
without new-generation retries and S1 default voice/status parity. A synthetic
pump produces a partial before VAD endpoint; a real Agent.run fixture still
dispatches one ordinary final. Loopback verifies authentication/binding and
absolute header/body trickle/cancellation behavior, real truncated Content-Length
and rejected transfer-coded framing (missing zero chunk, missing final trailer
CRLF and complete chunked), each preserving unknown/no new POST, and supported
namespace serialization at the last-stat checkpoint plus a separate process
sharing the same directory-inode lock. Additional fixtures bound competing
lock acquisition by the original deadline, preserve a contended completion marker,
and cancel a retired waiter without starting workers in ten newer generations. These are source tests.

Actual partial before endpoint, AEC/no own echo, resource/latency bounds alongside
the reply model, STOP/no resurrection, context continuity and acoustic/E2E targets
remain unaccepted. No latency improvement or hardware streaming PASS follows
from this checkpoint. It must not block the current physical measurement.
