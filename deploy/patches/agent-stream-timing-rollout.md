# Exact Agent289 first-only streaming timing projection

The preceding real repeat accepted producer PCM/token overlap, owned STOP and a
fresh next turn in the same PC process. Human confirmation established both
answers were heard. Baseline/config/slot and Robot OFF/unowned/100% were restored;
the working camera socket bind remains. Meaningful audible overlap, precise
acoustic onset and speech-end E2E timing remain unverified. A first segment of
two characters does not prove substantive opening speech.

Exact source audit identified a measurable gate: Agent waits for expression
handling before launching APLAY. It does not establish that gate's duration in
the preceding attempt. This increment measures the existing path without changing
motion/audio order, gates, queue sizes, deadlines, cancellation, PCM or model.
No segment threshold/abbreviation fix, ALSA handle/capture, new owner, endpoint,
framework or acoustic claim is added. Repository HEAD Agent is not deployed.

## Exact single-file overlay

Preimage Agent SHA256:
`289469a5de57f01295e6c8ddde3e78ba2804fe2f5e6c603a4789e3d70e6ebeb9`.
Reviewed output SHA256:
`c2fcb832501c55dd56a86abd7b87c71b05c013f968a2482dbfc1a27d3283f2f5`.
Patch `deploy/patches/reachy-agent-289-stream-timing.patch` SHA256:
`f0587b5d4c2d2597ccc26590cd78ce8b445d8204871a338b2ba166374ea01b13`.
Builder/finite consumer `deploy/autonomous/prepare_agent_stream_timing.py` SHA256:
`48bd29e5b4b09630e33f447998f580f4681825eea4a531987a9e05afc4f309e1`.

```sh
python3 deploy/autonomous/prepare_agent_stream_timing.py /private/tmp/agent-stream-timing-review
```

This reconstructs public pinned legacy 0a7 → bound speech 53a → spoken 9a →
route observer 289, checking each exact output, then applies this zero-fuzz
patch. It generates only agent.py and manifest.json, compiles the source and
refuses an existing destination. It neither imports the Agent application nor
contacts any device. No runtime helper installation is needed: the schema and
pure validator are embedded in the one patched Agent file.

## One bounded status record: exact schema v1

Existing authenticated /status gains `stream_timing`; no other endpoint or
/operator/capability shape changes. The field is null initially, on generation
mismatch, and after a new unrelated/nonstream/replay/early-cancelled voice call
clears the previous record. A normal /text or /turn streaming call starts a new
record before opening its response. Until the worker supplies a valid ID the
record is explicitly pending and cannot be joined to PC metadata.

The projection is a copy of exactly **21 flat scalar fields**:

| Field(s) | Required type / bounds |
|---|---|
| version | exact int 1; boolean is rejected |
| agent_boot_id | string length 1..128, same as status envelope |
| microphone_epoch, policy_epoch | exact int 0..2^63-1, same as envelope |
| content_attempt_id | null or lowercase hex string of exactly 32 characters |
| content_binding | pending / bound / invalid fixed enum |
| started_monotonic | finite nonnegative Robot monotonic seconds, ≤10^15 |
| Eleven marks listed below | null or finite elapsed seconds 0..86400 from started_monotonic |
| first_positive_write_bytes | null until the first positive write, then exact int 1..2^31-1 |
| consumption_verified, acoustic_verified | literal false only |

The eleven first-only marks are:

1. response_open_begin / response_open_end: around the existing response-open
   call, including its transport/header wait; an exception leaves end null.
2. first_reply_received: after a valid NDJSON reply is parsed, before processing
   its text. No text is copied to this record.
3. first_motion_enqueued: after the existing timeline call returns. This marks
   the enqueue-call return, not a receipt proving the cue was admitted or moved.
4. first_audio_line_received: the parsed audio event before format validation
   and PCM base64 decoding; not raw network packet receipt or audio consumption.
5. timeline_wait_begin / timeline_wait_end: around the unchanged wait_timeline
   call. A failed/unreturned wait has no manufactured end.
6. aplay_popen_begin / aplay_popen_end: around the unchanged Popen invocation.
7. monitor_start_return: after the existing barge-in monitor start returns, if
   enabled; not proof that its capture device has started.
8. first_positive_write: immediately after the first os.write returning >0,
   before the original clock.feed; the matching count is that write's bytes.
   Pipe acceptance does not prove ALSA or acoustic consumption.

Paired begin/end marks must be consistent, and write timestamp/count must be
present together. Repeated events never overwrite any mark/count. The record
uses copy-on-write scalar snapshots without adding a lock to the audio path;
old probe references cannot modify a successor record. Only one latest record
is retained. Status suppresses it after any boot/mic/policy mismatch rather
than adopting it into a successor generation.

The first valid worker content_attempt_id is retained. A malformed or conflicting
ID makes content_binding invalid permanently for that record; raw invalid values
are never stored. Repeated identical IDs are harmless. pending requires a null
ID; bound requires a valid ID. invalid may retain the previously valid ID solely
to diagnose the conflict and is never eligible for a PC-attempt join.

Empty, failed or cancelled paths retain only operations actually observed;
missing marks stay null. There is deliberately no new terminal/success outcome
field. An early cancellation before streaming starts leaves the projection null.
The schema never asserts acoustic/consumption verification. Legacy status still
contains its original text/error fields; do not publish or persist the entire
status body as this diagnostic.

## Same producer/finite-consumer contract, paired before activation

`validate_stream_timing` in the exact Agent is the sole schema definition used
by its projection AND the finite consumer. The builder's load_contract reads
only exact output bytes matching the output SHA above, selects the two schema
constants and that pure function by AST and compiles only those three nodes
with math supplied. It does not import/execute Agent, webrtcvad, audio, motion,
HTTP server or application initialization.

The private observer uses the reviewed builder through its existing protected
source-loader/fences and calls this exact parser/projection on its existing
bounded authenticated status read:

```python
validator = timing_builder.load_contract(reviewed_agent_bytes)
# Existing HTTP rc/auth/time/namespace/owner/source guards remain outside.
# For an already decoded status: timing_builder.project_status(...).
row = timing_builder.parse_status(status_body, validator, expected_attempt=pc_attempt_id)
```

parse_status accepts ≤16000 bytes, rejects duplicate JSON keys and nonfinite
numbers, then calls project_status with the SAME extracted validator. The latter
returns only the 21 fields, verifies the current status boot/mic/policy envelope,
and, when the expected PC ID is supplied, requires bound plus that exact ID.
Null means no available current-generation record; it is not completion/failure
proof. Unknown/missing fields or wrong types fail closed. No manual copied
allowlist or scalar coercion is permitted. The existing PC 31-field token-stream
metadata parser remains unchanged; these are separate linked clock records.

The observer may first collect a pending projection without an expected PC ID,
then retain the latest bound projection privately for the intended attempt and
join it only after a verified exact ID match. Collect it **before** owned STOP
or cleanup changes the generation. A later null does not erase an already
recorded correctly bound historical receipt, and that receipt must never be
re-labelled as current. Retain only the existing finite number of intended
attempts, not an unbounded poll history. No raw status/text/PCM is returned.

Review and run producer+consumer fixtures together before device installation.
The test invokes actual patched status/voice and this same AST-extracted consumer,
including current-generation validation and expected-ID joins; it covers all
nullable paths, reset/old-probe/no-overwrite and strict malformed/unknown JSON.
The private observer's source must visibly delegate to these functions and be
protected by the same reviewed source pins; a public fixture alone does not
prove that private integration has been applied.

## Finite sole-runner deployment and rollback

1. After coordinator review, require fresh known OFF/unowned/free, no capture,
   listening, camera, APLAY/controller or PC stream, volume API/saved/ALSA 100%,
   verified restored baseline/config/slot. Save private Agent preimage and
   config/profile/unit/drop-in/persisted-state identities; verify Agent289 hash.
2. Prepare the exact output off-device and review its paired private observer
   integration/schema fixture. Atomically replace ONLY Agent with the reviewed
   output, preserving owner/mode. Restart only reachy-voice-agent.service once.
   No helper, model, worker, factory, unit or camera binding changes.
3. Verify exact installed Agent output/new boot/readiness, authenticated status
   stream_timing null and existing capability, unauthenticated denial and unchanged
   strict operator shape. Preserve spoken helper
   `486cfb8f23c9d9d5797910eab6ebf3143e64f1cfe4a686b4f50fe38db975a025`,
   snapshot helper
   `d43a70cc1e3b3846cb163f8b772c9af2b13a08aefac2c4279f6197b68b974c13`,
   camera drop-in
   `4735915767426d67e8ffe66e2c85d0acd4931ba3a10e123d1513fd4eefb1780e`
   and PrivateTmp/read-only same current socket inode in Agent/factory/host.
   Check config/unit/persisted state unchanged, OFF/unowned/free/no APLAY/camera
   and 100%. Installation is not audio/latency acceptance or a new trial.
4. On failure remain OFF and preserve typed evidence. In a verified idle window
   restore only the exact backed-up Agent289, with a separately recorded rollback
   restart, preserving any newer operator/config/unit and current volume. Verify
   the previous baseline/camera/readiness; no blanket rollback or epoch restore.

Any subsequent real attempt is separately coordinated by ROOT/sole runner with
fresh boot/epoch bindings and the already reviewed finite lifecycle. This writer
checkpoint starts none. Match PC attempt ID and independently bound PC/Robot
clocks; do not subtract raw clocks across hosts. The marks can separate response
wait, timeline gate and process/pipe startup. They do not by themselves establish
meaningful acoustic onset, consumed PCM, full heard history, E2E/P95, continuous
capture or partial STT. No existing guard/gate is removed for a benchmark.

Validation: 50 focused local checks PASS, including nine new exact-Agent/contract
checks plus existing spoken/route/bound speech regressions. They compare legacy
and patched HTTP body, APLAY arguments, operation order and PCM; exercise partial
writes, nullable empty/open-failure/cancel cases, first-only marks/counts,
generation/reset/late old probe, sticky invalid IDs, status copies, exact schema,
duplicate/nonfinite JSON, paired consumer and exact reproducible bundle. No
real device/model/audio session occurred and no hardware acceptance is claimed.
