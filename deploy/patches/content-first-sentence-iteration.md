# First substantive sentence and one shared metadata contract

The preceding real human streaming attempt produced meaningful explanatory
speech and passed the owned STOP guard/cleanup. Its overlap condition was NOT
met: first semantic segment 0.868067 s, first PCM yield 1.193608 s, last token
READ 1.087325 s and DONE READ 1.087982 s on the PC request clock. Independent
APLAY observation was later than model completion. A short fast response can
naturally finish before TTS; this is not proof that streaming never works, and
it is not a streaming voice acceptance PASS. Physical speech-end latency and
acoustic consumption remain unverified.

The private finite consumer also rejected the existing model_post_attempted
boolean because its duplicated allowlist omitted it. That was an orchestration
schema mismatch, not a product worker error. Baseline/config were restored;
this checkpoint does not activate a stale prepared run or its old boot pins.

Safe effective-config evidence showed default brevity AND an explicit detail
exception, with the existing 512-token cap. The recognized eight-sentence
request was not retained, so no hard prompt cap or STT fault is established.
This is a small product refinement, not a claimed fix for a proven hard cap.

Only the content_tokens opt-in message assembly appends a system instruction:
explicit requested detail/count takes precedence over default brevity; begin
with a short complete substantive sentence that answers the question, then the
requested explanation, within existing bounds. That first sentence counts
within the requested total. Ordinary brief answers remain brief. No fixed ACK,
prefilled answer, artificial model delay, question-specific ground truth,
extra model, token-budget change or global/private profile rewrite is added.
History, the actual user request and FINAL/tag filters remain intact.

Piper is already loaded once in the exact worker. It is not reloaded/prewarmed.
The existing per-chunk SoX conversion/pitch/EQ and motion cues are unchanged.
No punctuation split or identity-bypass optimization is part of this change.
Agent and working camera/socket drop-in remain unchanged.

## Exact legacy bundle

Use the existing `prepare_content_stream.py`, not HEAD brains/voice. The same
public preimages remain brains 9c69 (public Git 39dffa0f…) and worker 92cf
(public Git 2865db30…). The worker patch now includes an optional observer in
its existing audio_events method, called only for the first streaming segment.
Default-off and /say behavior retain the original PCM/cues/SoX path.

| Bundle file | Reviewed SHA256 |
|---|---|
| brains.py | `020e435e37602271d2d40160b055650f781b60a8ee9fc601e3b28d82444bdae6` |
| voice.py | `bbdb7be523946396cedd16a2f629caabdb54bf3d9979bfd5e7403f2730995764` |
| token_stream.py | `a4aa26d375b46cfd0348f6cb42df6adb1f82a0f1b4252afb11df571f4edc539d` |

Worker patch SHA256:
`31cb59ad378bc1180d527598e4e8f1b0392be04881c5aa0fa7f4ffef6e4c8b8b`.
The builder rejects drift, compiles all three files and refuses an existing
output directory. Brains output is unchanged. The previous 347 helper/0bc
worker belong to the preceding attempt; do not mix old and new bundle files.

## Bounded first-segment telemetry

The existing single per-attempt metadata record now has exactly 31 fields:
the original 25, including model_post_attempted, plus these six:

- first_segment_chars: nullable integer 1..600, without the optional TTS address.
- first_segment_boundary: nullable fixed enum period/question/exclamation/
  ellipsis/tail. This classifies the emitted segment's final punctuation, not a
  grammatical parser, STT request count or proof of acoustic completion.
- first_piper_wait_seconds: nullable duration before entering the existing Piper
  iterator to its first chunk, including phonemization/synthesis, not model load.
- first_sox_seconds: nullable duration around the first existing SoX call.
- first_cues_seconds: nullable duration around first cue computation/clipping.
- first_segment_prepare_seconds: nullable duration from that Piper entry to the
  first prepared audio event just before yield; includes intermediate motion
  yield/consumer time and event encoding. It is not acoustic playback latency.

All use the same PC monotonic clock. The four durations are first-only; later
chunks/segments cannot overwrite them. If the first transformed PCM is empty,
first-chunk stage measurements remain first-chunk measurements while the total
preparation duration continues to the first actual audio yield. If execution
fails/cancels before that yield, unavailable durations stay null, not zero or
fabricated completion. No text/audio/image/model ID or new endpoint/log stream.
Existing attempt/read/terminal/queue/quiescence fields and consumer cleanup
remain; no permit, cancellation, deadline or next-turn gate is relaxed.

## Producer and finite consumer are one reviewed contract

The SAME pinned token_stream.py provides validate_metadata(value) and
metadata_rows(raw_bytes). The former requires exactly the 31 known fields,
strict booleans (0/1 are rejected), typed bounded integer counts, finite
nonnegative numbers, fixed punctuation enum and paired optional segment fields.
The latter accepts at most 1 MiB combined raw logs in RAM, selects only the
existing content_stream_metadata marker, rejects duplicate JSON keys and
NaN/infinity, and calls that exact validator. Unknown/missing keys fail closed.
No raw log is returned or persisted.

The runner MUST update its existing private finite executor's metadata method
at the same time as the bundle, before any device activation. Load only this
reviewed helper using the existing source loader/protected source fences; verify
its SHA above. Importing the helper uses standard library modules, not a model
or audio owner. Never instantiate TimelyReader in the finite consumer.
Replace the duplicated allowlist/parsing loop, keeping its existing bounded
Docker logs command, source/container/time-window guards, rc check and budgets:

```python
# self.content_metadata is the exact hash-checked helper loaded once by the
# existing private preparation mechanism, included in protected source fences.
def metadata(self):
    x = subprocess.run(D + ['logs', '--since', str(int(self.started_unix)), self.candidate],
                       capture_output=True, timeout=self.budget(5))
    need(x.returncode == 0)
    return self.content_metadata.metadata_rows(x.stdout + b'\n' + x.stderr)
```

The combined byte bound is now enforced by that shared parser (including the
separator byte). Do not intersect with an old allowlist, ignore unknown fields,
accept arbitrary scalar types or clear UNKNOWN based on a parsed record alone.
Retain separate terminal+producer+Piper quiescence, current ownership/model/source
identity, same-request deadline and idle checks for recovery and READY_NEXT.
model_post_attempted=true marks the send boundary, not GPU acceptance; false in
an unfinished reader is not proof that no POST occurred.

Before device rollout, run the shared schema fixture locally against the exact
bundle/helper AND private consumer integration. The public fixture uses an
actual TimelyReader.metadata record without starting a producer and parses it
through the same metadata_rows function. It covers new/old known fields,
unknown/missing fields, strict boolean/count/enum/numeric types, duplicates and
nonfinite values. The runner also verifies its method delegates to this helper;
source hashes and consumer integration are a single review checkpoint.

## Next finite real acceptance

After coordinator review, the sole runner reuses the existing reviewed finite
candidate lifecycle and strict owned-start receipt comparison/recovery. Require
fresh baseline/source/config/model/publisher identity and Robot OFF/unowned/100%
with working camera bind preserved. Prepare a fresh run against current Agent
boot/epochs. Candidate construction retains all current security, mounts,
ports, environment and instance; no image build, broad install or Agent restart.
Only the reviewed legacy bundle and matching consumer parser change. The
existing opt-in and original 40-second request deadline remain; preserve exact
protected config for restoration.

Use ONE real human request for a substantive longer explanation with an
explicit number of sentences. Verify the actual request locally in the private
owned attempt; emit only bounded safe count/known-request indicators if needed,
not raw STT/prompt. They are evidence for that request, not a new canonical STT
heuristic. Do not seed its expected answer or artificially delay generation.
Require requested content/length, a short complete meaningful opening, actual
human-heard content followed by independently observed further timely nonempty
token READ, then STOP, same-response terminal/quiescence and a fresh next turn
on the same PC process. Distinguish READ clocks, software PCM yield, APLAY
observation and acoustic consumption. Record software speech-end latency only
with proven clock binding; do not invent E2E/P95 or overlap from source order.

End with normal owned cleanup and verified baseline restoration as required by
the accepted lifecycle. A schema failure, missing terminal or unknown producer
remains UNKNOWN; it does not permit a duplicate model POST or timer-based clear.
One short response completing before playback is a missed overlap test condition,
not a reason to slow the model or claim universal pipeline failure.

Local validation: 40 focused checks PASS, including 8 new first-content/contract
checks plus existing exact overlay, parser, reasoning/tag, bounded queue, real
loopback HTTP deadline, STOP discard and next-admission regressions. The new
checks preserve exact old PCM/cues/SoX commands, measure stages on a synthetic
monotonic clock, cover empty first PCM, first-only observer, untouched user/history
and appended stream-only instruction, and round-trip the exact shared schema.
Source tests do not establish improved real latency, requested answer length,
meaningful overlap or actual next-turn acceptance.
