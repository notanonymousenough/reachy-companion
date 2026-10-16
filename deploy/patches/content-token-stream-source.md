# True content streaming: original source checkpoint b90d40b

This page records the original review-only checkpoint and its helper hash.
The actual PC SSE/prefix contract has since passed. The implemented timely
reader and the current finite lifecycle are in
[content-token-stream-rollout.md](content-token-stream-rollout.md); use that
page's bundle/helper pin, not this historical helper pin. The two exact legacy
brains/voice overlay outputs remain unchanged. Real voice acceptance is open.

This is an independent source increment while the spoken camera failure remains
P0. It changes no deployed service, Agent or camera helper. It is not a full HEAD
worker migration, streaming acceptance or a latency claim.

Exact installed source preimages (source-file proof, not mapped-code attestation):

| File | Preimage SHA256 | Public source | Candidate SHA256 |
|---|---|---|---|
| brains.py | `9c69d27979dce500148c06ee8d1dc58e90aabae3e5a2b1d3fc8edfb9e754642d` | `39dffa0f1b4d3201765f851be4a932b0a0e079aa` | `020e435e37602271d2d40160b055650f781b60a8ee9fc601e3b28d82444bdae6` |
| voice.py | `92cf69096fd6f08551a13a9c44d85fbbfc0470ca2f17315616691044018ab865` | `2865db30e92fcb069c241c34bae4419ad65ed594` | `d97656e8d76b0802e4d177654369a31775ac0b74507c11718480f2d58e081a65` |

The two preimages have different Git pins. Do not attribute brains to the worker
pin. Both patches require exact source/zero fuzz, never guessed live paths or
replacement with HEAD worker/brains. The only new runtime file is
`src/reachy_companion/token_stream.py`; the code identity registry addition is
repository provenance for future package builds, not a current worker update.

Reviewed candidate file pins:

- `token_stream.py`: `7bd12db960dffb3778e594136ada94f219767683ffc742c06f1b060136048c4a`.
- `reachy-brains-9c69-content-stream.patch`: `b5dd1591b7005b859534c1b2f79fe50313d260fff7eccbf5c8b3715908b50fd7`.
- `reachy-worker-92cf-content-stream.patch`: `8e7e97d639226c64249e9fd775730ba29a2bd612813ad99a3a1cc41521783018`.

## Existing API and source delta

Use the existing local raw-prompt `/v1/completions`, same configured model,
template, stop strings, temperature and token cap; only `stream:true` changes.
No native-chat event names, reasoning flags, paid API, new model or SDK are
introduced. LM Studio documents continued support and explicit raw-prompt
handling for [legacy completions](https://lmstudio.ai/docs/developer/openai-compat/completions).
The linked [completion specification](https://developers.openai.com/api/reference/resources/completions/methods/create)
defines data-only SSE text choices and terminal `[DONE]`. These are documented
contracts, not proof that the current installed runtime returns exactly this
model namespace, identity or event shape. That actual contract is still open.

The parser bounds lines/events/total bytes to 32768/8192/1048576, checks the exact
configured model, one index-zero choice and unchanged response ID, and denies
duplicate JSON keys, nonfinite numbers, chat/tool/reasoning fields, early EOF,
unknown terminal reasons and extra data after terminal. Completion success
requires `finish_reason=stop` and `[DONE]`. Length/filter termination fails the
answer; if DONE is verified it can still prove the backend attempt has ended.

A character-incremental scanner retains split tags, suppresses complete think
regions, and rejects unfinished/unknown tags and alternative analysis markers.
Allowed emotion/gesture tags affect the bounded segment style and are not spoken.
It emits a completed sentence as soon as its boundary is available, or a bounded
final phrase only after verified stream completion. Limits are 600 characters
per segment, 32 segments and the existing whole speech cap; raw text is capped
at 131072 characters. Untagged reasoning cannot be distinguished from prose by
this legacy API. Initial FINAL state requires actual proof that the configured
assistant prefix ends in the reviewed closed think region. The sole runner's
read-only effective-config witness confirms open/close/balanced/end-closed-think
properties without exporting prompt values. This specific initial-state gate
is satisfied; it is not a guarantee about untagged reasoning. Actual model
FINAL behavior and stream schema still require verification.

Each ready segment immediately enters the existing `audio_events`/Piper/SoX
path. The server can continue generating tokens while CPU TTS/PCM transport
handles that segment. No whole-answer future or ACK is awaited. There is no
new producer thread, unbounded text/PCM queue, audio device or motor owner.
Total PCM offsets/duration/characters and motion cue count are tracked across
segments; address prefix is applied once. Existing speech clock/playback and
motion consumption limits remain, without claiming actual acoustic consumption.

Only `Pipeline.stream` changes in the worker overlay. The public opt-in setting
is `streaming.content_tokens=true`; it is **not enabled** by this source change.
Absent/false retains the exact old stream branch, including manual `/say`.
The hook uses the real Config mapping facade (`config['streaming']`), which has
no `.get()` method. Both default-off and opt-in are checked with that facade.
Streaming applies only to `/text` and `/turn`; structured reply constraints are
rejected by this candidate rather than silently ignored. Existing session
history, interrupted-reply notice, control commands and completed-history commit
are retained. Errors or early close never commit a complete assistant reply or
yield successful done. Existing pipeline lock/idle cleanup precedes done.

The additive brains overlay reuses the already tested process-local model permit,
raw-prompt helper and bounded HTTP identity check from this repository. Under the
explicit mode, ordinary and streaming local requests share **one** model permit;
there is no separate streaming guard that ordinary/classifier calls can bypass.
Default-off ordinary brains behavior is preserved. No HEAD structured-reply,
SDK, logging or other backend migration is included.

## Cancellation and the remaining activation blocker

Early stream/audio close propagates through semantic and model iterators. The
same old HTTP response is drained without emitting tokens/audio for at most two
seconds using remaining socket timeout. Only verified finish plus DONE marks
the attempt terminal and releases the permit. This is observed protocol
completion, not a claim that closing the socket cancels GPU work. EOF, timeout,
malformed stream or an unavailable socket boundary leaves the permit UNKNOWN.
An owned deadline timer shuts down only this response socket if a trickled line
keeps the idle timeout alive; it is cancelled/joined before exit. Deadline is
also checked after every read before a late DONE can mark terminal. This is a
bounded cancellation watchdog, not a model producer/observer thread.
Ordinary as well as streaming next requests then fail closed; no elapsed timer
clears the state and no automatic new inference/retry is made.

That failure outcome is deliberately blocked, **not an accepted recovery path**.
Before enabling, the sole runner/architect must establish a finite targeted
method to prove termination/reconcile this owned attempt when discard-drain
fails. It must identify the owned request/instance, preserve foreign work and
the loaded model, and prove the next turn can proceed. No guessed native cancel
endpoint, unload-all, blind worker reset, unverified idle timer or second model
request is a substitute. Until that method and the actual SSE identity/schema
are verified, this source candidate must not be activated on devices.

## Source checks and future real acceptance

Local tests run the exact legacy worker overlay with synthetic model/TTS:
first reply/PCM is yielded before the model tail is requested, one address and
global PCM/cue limits are retained, the same session survives, cancellation/error
does not commit history, and done follows lock release. Split-at-every-character
reasoning/style tests, wrong identities, EOF/length/duplicate/oversized SSE,
same admission for ordinary requests, terminal discard-drain and UNKNOWN are
also exercised. A real local HTTP/SSE server trickles a partial line below the
idle timeout; cancellation still ends near two seconds and retains UNKNOWN.
Valid choices accompanied by an error or incompatible top-level channel are
rejected before any TTS call. These establish source order and bounds, not real generation,
playback, overlap, GPU cancellation or timing.

In particular, first PCM before the last **read** SSE delta does not prove it
precedes the last **generated** model token: HTTP buffers can retain an already
generated tail. Real acceptance needs a timely independent model-side observer
or verified generation timestamps and clock binding; this candidate's lazy
iterator test must never be labelled generation/audio overlap PASS.

After source review, actual runtime contract/recovery proof and a separate finite
rollout proposal, runner acceptance must show a real long answer with first
substantive playback before last model token, software stage timings plus honest
actual-consumption unknowns, STOP while generating/speaking, no stale PCM/cues,
then a working next turn and preserved ordinary context/final OFF100. Camera fix
has priority. Continuous hearing/rolling capture/partial STT/endpointing is the
next separate seam, still unimplemented; this increment does not satisfy that
part of the user's streaming request.
