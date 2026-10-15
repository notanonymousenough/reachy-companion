# Stock factory motion MVP

The optional stock route uses the running factory REST daemon. It does not take
over UART or require the native motion service. Native remains the default;
neither route falls back to the other. This document describes source behavior,
not a completed hardware acceptance run.

## Configuration

On both Hub and Agent, preserve the existing private configuration and change
only these settings for an explicitly supervised stock run:

```json
{
  "guarded_motion": {
    "enabled": true,
    "transport": "stock",
    "socket_path": "data/native-motion.sock",
    "policy_path": "data/motion-policy.json"
  },
  "conversation": {
    "wake_on_start": false
  }
}
```

This is a merge fragment, not a replacement configuration. Keep existing socket
and policy paths if different. `network.robot_url` addresses the factory daemon;
`network.agent_url` addresses the authenticated Agent. No new dependencies are
required. The Agent's native actor reports `stock_factory_api_not_native_actor`
and does not open native IPC in this mode.

Configuration alone does not grant motor permission. The existing authenticated
Agent `/motion-policy` (or Hub `/control/motion-policy`) must contain the actual
explicit operator decision `motor_enabled=true`, `quiet=false`,
`privacy_all=false`. Preserve the existing owner/epoch CAS when a runtime owns
that policy. Do not enable the microphone for a movement test. Hub captures the
Agent boot, microphone epoch/state and policy epoch, requiring the same binding
before each write and movement poll. A changed epoch or unavailable operator
withdraws that plan; later restored permission does not continue its return step.

## Installed API gate and finite run

Before a device run, the sole device runner must inspect the installed OpenAPI
schema and handler implementation. Confirm the existing daemon/status,
robot-app-lock-status, move/goto, move/running, move/stop and state endpoints;
canonical UUID receipts and running-list entries; radians and duration units.
Specifically confirm that explicit `body_yaw: null` and `head_pose: null` mean
preserve those axes, and that goto forwards these nulls without substituting a
zero/default pose. Source always sends `body_yaw: null`; antenna-only hello also
sends `head_pose: null`. A schema mismatch blocks the device run until corrected.
Wake/sleep are explicit whole-robot actions and do not preserve all axes.

Keep factory running and ready, the cooperative app lock free, and other movement
producers inactive. The Hub lock permits one coordinated command lane, not global
kernel exclusion of unrelated factory clients. Do not remove service fences or
change daemon ownership as part of this source rollout.

For the first finite run use a single bounded expression or the reviewed finite
hello scenario with already enabled motors. Review the scenario's actual offsets
and return step first. The expression endpoint is authenticated
`POST /actions/expression`; existing head/antenna/duration/count limits apply.
Expressions include an explicit head target. An antenna-only hello uses current
antenna positions plus configured offsets and leaves head/body targets null.
There is no automatic sleep in a stock action's `finally` block. Any explicit
return step requires the original operator binding and current readiness again.

Movement UUID disappearance yields `completion_observed=true`,
`pose_verified=false`, `hard_stop_certified=false`. An expression response uses
`steps_observed`, not a claim that each target was physically reached. Hello
additionally checks actual antenna positions against the existing configured
tolerance and reports `antenna_pose_verified`; `pose_verified` remains false
for full pose. Device acceptance must
record actual state/tolerance and independent observations. A UUID disappearance
or stop acknowledgement alone proves neither target attainment nor a certified
hard stop or 500 ms stopping bound.

## Withdrawal and unknown completion

On timeout, operator withdrawal, polling failure or a foreign move appearing,
Hub independently requests `/api/move/stop` for only its recorded UUID. It does
not stop foreign UUIDs or use a global stop. UUID absence after that request is
reported as `stop_observed` in `/status` under `stock_motion`.

Before that stop POST, Hub checks fresh (within 300 ms from read-window start)
factory readiness, free app lock and canonical running UUIDs. If the list is
empty, the owned UUID is already absent: it records absence and avoids the
factory's non-idempotent stop of a completed UUID (`stop_request=null`). This
never clears a pre-existing UNKNOWN. An active, foreign, malformed, unready or
slow/failed precheck falls through to the existing best-effort stop of only the
owned UUID, independently of withdrawn operator permission. A completion race
after that precheck can still make the POST fail; its existing sticky UNKNOWN
and explicit reconciliation requirements remain unchanged. UUID absence is an
observation, not target attainment or a physical hard-stop certificate.

A POST failure without a usable UUID, or failure to observe the owned stop,
latches `stock_motion.unknown=true`. No further stock output or blind retry is
allowed in that Hub process. Restart is not evidence that the movement stopped:
the operator must first reconcile actual factory movement/state. No automatic
old-pose restoration, finally-sleep, permission acquisition or retry runs.

Rollback means returning to the previously saved configuration and source pin
after the runner independently confirms actual state. Selecting native does not
start its owner service or establish its separate safety guarantees.

## Ordinary production dialogue

Use the existing Agent service and voice worker/router, without a parallel
`companion_session` process or a private probe. `Agent.run` captures real input,
closes arecord, sends `/stream/turn` when streaming is enabled, and plays worker
audio events. The worker performs STT, `Pipeline.answer` calls the configured
`brains.answer` backend, and Piper produces speech. ExpressionPlayer sends worker
plans/cues through the deployed Hub stock route. It does not require a native
actor. The remote router forwards these endpoints to the existing compute worker.

For the first short service trial, merge these conservative settings on Agent,
Hub and worker, retaining their existing private network/model/audio settings:

```json
{
  "guarded_motion": {"enabled": true, "transport": "stock"},
  "streaming": {"enabled": true},
  "conversation": {
    "wake_on_start": false,
    "greet_on_start": false,
    "expressions": {
      "enabled": true,
      "max_head_degrees": 2,
      "max_antenna_degrees": 2,
      "duration_seconds": 0.5,
      "max_steps": 1,
      "max_total_seconds": 1.0,
      "repeat_seconds": 3.0,
      "library": {"repeat_processing": false}
    },
    "sound_reactions": {"enabled": false},
    "barge_in": {"enabled": false}
  }
}
```

`barge_in=false` is only the initial closed-turn finite acceptance profile; the
desired conversational profile uses `barge_in.enabled=true` after the runner
checks fresh-microphone interruption separately. Preserve its existing threshold,
STT-confirmation and echo settings. With barge-in disabled the Agent closes input
before sending the turn and resumes listening after speech. Expressions are
absolute bounded head/antenna targets, not offsets from the current pose. Already
enabled motors and reviewed actual starting pose are required; no automatic wake.

An active `runtime.profile` overrides local conversation/LLM values. Apply the
trial merge in a reviewed copy of that active profile and select it explicitly,
or verify the final effective values before the trial. Do not assume a local
JSON edit wins over the profile. For example, with `CONFIG` set to the actual
private configuration path, existing commands are:

```sh
companion --config "$CONFIG" config validate
companion --config "$CONFIG" config value guarded_motion
companion --config "$CONFIG" config value conversation.expressions.max_head_degrees
companion --config "$CONFIG" config value conversation.barge_in.enabled
companion --config "$CONFIG" voice status
companion --config "$CONFIG" hub status
companion --config "$CONFIG" voice microphone-on
# Speak a fresh question; verify an actual new transcript, backend response,
# audible answer and stock movement during the runner's finite window.
companion --config "$CONFIG" voice microphone-off
```

These are control commands for the running services. The existing foreground
entrypoints, when needed, are `companion --config "$CONFIG" agent serve`,
`hub serve`, `voice serve` (router when `voice.mode=remote`) and `worker serve`
on their configured hosts. Do not run duplicates alongside installed services.
Microphone-on is an explicit operator decision, never a side effect of rollout.
Retain the initial mute/volume/policy snapshot and perform owned cleanup; an
unconditional microphone-off must not overwrite a newer operator owner.

The runner must verify the installed worker's effective `brains.provider`,
`network.llm_base_url`, `llm.model`, `llm.api_path` and any reply-schema mode
against the intended real model. The source has no synthetic answer fallback in
this path. A successful CLI invocation or local test does not prove the selected
remote model was called. Confirm the new transcript and corresponding actual
model request/terminal response in the finite run; do not publish raw speech or
private configuration. The autonomous scheduler's native-motion profile remains
separate and unchanged.

Deploy the matched `agent.py`, `expression_player.py` and `hub.py` from the same
checkpoint over the stock baseline, preserving the existing dependency closure.
No new package, model or service is added; worker, router, brains, STT/TTS and
audio binaries remain the existing production dependencies. Stage the matched
files before restarting from a muted baseline and verify their hashes. An older
Hub does not enforce the new optional binding; updating Agent alone is insufficient.

Production stock ExpressionPlayer requests always carry the original Agent boot,
mic epoch/state, policy epoch and expression version captured before scheduling.
Hub rejects stale admission before a factory POST, then checks that expression
version on every write/poll. `hold()` (including barge-in) advances the version
even with unchanged mic epoch; Hub independently stops only the current owned
UUID. It drops the remaining steps. No finally-neutral is scheduled after an
interrupted or withdrawn reply. Explicit manual finite expressions may omit this
binding and still require the current motor policy. Native actor admission and
its audited guarantees are unchanged.

Binding mismatch diagnostics name only changed fields: `boot`, `mic_epoch`,
`policy_epoch`, `mic_enabled`, `expression_version` or `missing_binding`. They
never print actual boot/owner identifiers, epoch values or credentials.

Existing service playback uses an aplay pipe and wall-time estimates, not a
measured hardware consumed-PCM cursor. This checkpoint claims neither exact
consumption nor certified stopping latency. Unverified automatic audio resume
remains blocked. Local regression uses synthetic microphone/model/TTS/PCM IO;
the runner owns actual fresh-mic, audible speech, movement and interruption
acceptance and must report these observations separately.

## Explicit reconciliation of a known owned UUID

A failed stop POST (including 404 for an expired UUID or a timeout) is followed
by bounded independent GET observations. `/status` distinguishes `stop_request`
(`endpoint`, sanitized `error_class`, optional numeric `http_status`) from
`stop_observed`. UUID absence can set `stop_observed=true` while `unknown=true`
and `owned_uuid` remain retained. That observation does not reopen output.
There is no blind retry of the stop POST or movement.

For a future unknown state with a known UUID, the authenticated Hub endpoint
`POST /actions/stock-reconcile` accepts exactly this JSON structure (replace all
example values with the current, explicitly reviewed binding):

```json
{
  "expected_hub_boot_id": "CURRENT_HUB_BOOT_ID",
  "owned_uuid": "00000000-0000-4000-8000-000000000001",
  "operator_binding": {
    "agent_boot_id": "CURRENT_AGENT_BOOT_ID",
    "microphone_epoch": 0,
    "policy_epoch": 0,
    "microphone_enabled": false
  }
}
```

The UUID must equal the exact canonical known `stock_motion.owned_uuid` and the
Hub boot must equal `stock_motion.hub_boot_id`. The operator binding comes from
the current authenticated Agent `/operator` (`policy_epoch` is
`motion_policy.epoch`). `motor_enabled` must already be explicitly false; the
endpoint never changes microphone, quiet/privacy, volume, policy or factory
state. Neither a missing UUID from an unknown movement POST nor a foreign UUID
can be reconciled this way. No additional fields, duplicate JSON keys, nonfinite
numbers or bodies over 4096 bytes are accepted.

The endpoint takes the existing nonblocking Hub command lock, requires a latched
unknown with that same owned UUID, and checks an error-free ready factory,
cooperative app lock free, running list completely empty and actual state with
known enabled/disabled control mode. It reads the typed current operator before
those GETs and again immediately before clearing the latch; Agent boot, mic
epoch/state and policy epoch must match the supplied original binding, with
motors denied. Each operator read and the entire reconciliation observation
window must complete within 300 ms from the beginning of the read/window.
Stale, busy, changed, foreign or unavailable observations retain the latch.

Successful explicit reconciliation returns `reconciled=true`,
`uuid_absence_observed=true`, `pose_verified=false`, `hard_stop_certified=false`.
It clears only this exact local latch/owned UUID and records the observed
absence. Existing stop-request diagnostics remain available. It grants no
permission, emits no motor/mic/factory write, and performs no wake, return,
sleep or automatic retry. Further movement still requires a new current explicit
motor permission and ordinary command admission. Denied HTTP replies use static
error enums and do not return exception bodies or credentials.

Denied reconciliation replies additionally report only `phase` and `error_class`.
Phases are `decode`, `admission`, `operator_before`, `factory_deps`, `state`,
`operator_after` and `window`. Error classes are `module_missing`, `http_error`,
`timeout`, `validation` and `state_denied`. These fields identify the failing
check without messages, module names, remote bodies, boot/owner IDs or secrets.
Diagnostics are scoped to that request; they do not relax or retry any check.
The endpoint uses a Hub-local strict stdlib JSON decoder. It requires neither
the `autonomous` namespace nor jsonschema. This closes the confirmed deployment
gap where an older production Hub package lacked `reachy_companion.autonomous`:
the prior dynamic decoder import failed before reconciliation checks ran. The
minimal production dependency change is only the matched `hub.py` source file;
no new package or namespace installation is needed. This finding explains that
endpoint import failure, not the separate unproven factory stop HTTP 500 cause.

This endpoint cannot be injected into an older running Hub process. Installing
the source requires an orderly restart; restart alone is not reconciliation.
For a currently latched older process the runner may perform a separately
reviewed one-time external transition: record its exact instance and known UUID,
quiescence, fresh factory ready/free/empty and unchanged operator binding with
motors denied; stop the old Hub and confirm its process is gone; repeat the
factory/operator checks before starting the new Hub. Record the old latch and
new boot, with no physical hard-stop claim. This is a deliberate bounded
reconciliation, not a persistent recovery/reset framework.

`Agent.capture` queues the optional neutral expression without waiting for its
HTTP transport, factory completion or settle delay, then opens arecord under the
existing microphone/epoch checks. The expression worker retains its original
binding and owned-stop controls independently. A local regression holds the
actual ExpressionPlayer-to-Hub HTTP request open and verifies that arecord opens
and synthetic voiced/silent PCM reaches the capture endpoint before that request
is released. Rejected movement also does not prevent capture. Muted capture,
including a stale listening event, is denied; mute/epoch withdrawal after process
open returns no PCM and reaps the process.

The earlier synchronous neutral wait was an avoidable dependency, not a proven
cause of the historical device failure. A completed 409 already advanced the
expression completed version; a hanging request could delay its prior wait.
The Agent.run voice-health and Hub cooperative-ownership checks before capture
remain unchanged readiness gates. Actual capture/phase/last-error/stream evidence
is still needed: `recording` means a loud candidate began, while PCM admission
also requires the existing minimum voiced chunks and silence/max-duration
endpoint. A candidate can be discarded without a completed turn. No VAD,
threshold, endpoint, STT, model, echo or Alice timing settings are changed by this
checkpoint. Do not treat wall-time phase polls as proof of exact first-sample
timing, audible speech, consumed PCM or the historical failure cause.

## Optional per-turn voice latency diagnostics

For a finite diagnostic run, explicitly set `logging.latency_diagnostics=true`
in the Agent's copied local configuration; the optional boolean defaults to
false. Restore that configuration after the run. This flag does not enable the
microphone, grant motion permission, start a model or issue another request.
The existing authenticated voice request carries `latency_diagnostics=true`
and a fresh `latency_request_id` of exactly 32 lowercase hex characters. A
direct authenticated worker caller can opt in with the same two fields.
Invalid types/identities reject before robot checks, STT, LLM or TTS. Caller
payloads/configuration are not mutated; the ID is independent of session/text.

Unary responses and the existing stream `done` event optionally include
`latency`. Agent returns a joined `{request_id, agent, worker}` record and exposes
one latest record as `last_voice_latency` in its authenticated `/status`.
Its 300-second TTL is checked on access; an expired/disabled record is removed,
and no history or durable diagnostic log is created. Worker diagnostics are
response-only, excluded from existing `last_turn` retention and cached replay
results. The fixed schema includes only enums, counts, bounded numeric values
and the random request ID; no transcript, reply, prompt, reasoning, session,
raw audio, config values or error text. Counts and offsets are bounded; there
is no per-chunk event list. Reports with unknown keys/types, invalid ranges,
inconsistent stages/PCM counts or another request ID do not enter Agent status.
Replay gets a new Agent ID and `source="replay"`, with no fresh worker report.

Each host uses its own monotonic clock, with offsets from that host's turn
entry. Join by the identical request ID only; never subtract Worker and Agent
timestamps. `elapsed_seconds` is an envelope, while each stage has first start,
last end, sum of active call durations, and a bounded call count:

| Record | Measurement | Interpretation |
| --- | --- | --- |
| Worker | `stt`, `classification`, `answer_call` | Existing calls only. `answer_call` spans `Pipeline.answer`, including backend queue/HTTP/SDK/local work; it is not isolated GPU inference. Classification can invoke its existing backend. |
| Worker | `tts` | Active `synthesize_wav` call, or each streaming generator `next()` including terminal iteration. Consumer backpressure between chunks is excluded from the active sum, but can lie inside the first-start/last-end envelope. |
| Worker | `audio_convert` | Existing SoX calls, separate from TTS advancement. |
| Worker | `first_raw_pcm`, `first_output_pcm` | First actual Piper chunk bytes and first converted PCM. Acknowledgement and final speech share the same record. Unary WAV uses `wav_ready`; unavailable first-PCM marks remain null. |
| Agent | `first_write`, `stream_done` | First successful positive `os.write` to the owned aplay pipe, and received valid stream completion. Neither proves audible output or DAC consumption. |
| Agent | `aplay_wait`, `aplay_cancel` | Existing explicit owned-process drain wait or terminate/kill/wait cleanup; no new process operations or longer deadlines. |
| Agent | `aplay_communicate` | Unary blocking communication/write/wait envelope. First successful write is unavailable in that API and remains null. |
| Agent | `worker_request` | Unary full HTTP request; for streaming, opening the response headers only. Body receive/feed time is inside the Agent total, not this stage. |

`main_first_token_seconds` remains null: the current non-streaming model
boundaries expose no actual first-token observation. Streaming `pcm_frames`
and `pcm_seconds` count generated (Worker) or validated received (Agent) mono
16 kHz frames; Agent also counts frames actually accepted by pipe writes.
Unary frame counts remain unavailable. An early close before TTS produces no
invented PCM mark or TTS call. Worker failure/cancel before `done` yields no
completed Worker report; Agent can still retain its own typed error/cancel
record, without exception text. Existing epochs, mute/quiet/privacy checks,
stream cleanup, barge-in, replay TTL and playback deadlines remain in force.

These measurements start at `Agent.voice`/Worker request entry: capture time,
earlier listening/queue time, implicit OS/audio buffering and first-audible time
are not measured. Use Agent-local first-write/stream-done/drain intervals and
PCM duration alongside Worker-local active stage sums to investigate playback
versus compute. Do not turn an unexplained remainder into an inference claim,
subtract overlapping stage sums, infer P95 from one turn, or replace/truncate
the real model reply. This is source instrumentation; real timing acceptance
requires a new authorized physical run with the matched effective code closure.

The runtime source closure is Worker `voice.py` + `logging_utils.py`, Agent
`agent.py` + `logging_utils.py`, and `config.py` for strict validation of the
optional boolean. `config.example.json` documents the false default; older
private configs need no new key. Prove effective import origins/hashes, not
dormant mounted source. New manifest-guarded images require a reviewed rebuild
with matching expected source; never disable the guard or regenerate expectations
from observed overlays to make diagnostics pass. No dependency or endpoint is added.

## Explicit Alice conversation address

For an intentional conversation with the Alice speaker, merge this option into
a separate copy of the active Agent conversation profile:

```json
{"conversation": {"speech_address_prefix": "Алиса, "}}
```

The default is `""`; only `""` and exactly `"Алиса, "` are accepted. Verify the
effective Agent value with `companion --config "$CONFIG" config value
conversation.speech_address_prefix`. Do not change the ordinary human profile;
restore the exact original profile/configuration after the finite Alice run.
An active profile overrides local JSON values. Copy and merge the existing
profile rather than replacing its model, voice and safety settings with this
fragment. This option does not grant microphone or motor permission, wake the
robot, start a conversation, extend the allowed exchange count/TTL, or create
an automatic Alice loop.

The existing worker adds the address immediately before TTS, once per logical
utterance. Emotion segments, Piper chunks and PCM chunks do not receive repeated
prefixes. An acknowledgement and the final answer are separate utterances, each
addressed once. Initial `Алиса` is detected with Unicode NFKC/casefold comparison
and a word boundary; an already addressed question is not doubled. Only the
comparison is normalized. The model reply body, requests, history and decisions
are unchanged. Existing speech character and PCM/duration bounds include the
added address; empty/stopped/cancelled-before-audio replies produce no prefix
sound. Existing voice cleanup remains unchanged; no reasoning extraction or
scripted replacement answer is introduced.

Authenticated `/say`, `/text`, `/turn` and their `/stream/...` variants accept an
optional top-level `speech_address_prefix` with exactly the same two allowed
strings. Agent explicitly copies its selected profile value into each new voice
request. The worker captures that value locally for the request, including its
acknowledgement, final speech, metadata and all TTS chunks. It never updates
shared config, a pipeline prefix field or session defaults. A missing field uses
the worker's existing global default; an explicit empty string clears that
default for this request only. `null`, booleans and unknown strings reject before
STT/LLM/TTS or a first stream event. This is speech formatting, not model input.

For example, `POST /say` with
`{"text":"Вопрос к колонке.","speech_address_prefix":"Алиса, "}` requests one
addressed utterance; the next omitted-field request uses its ordinary default.
The same local binding is preserved across emotion segments/acknowledgements;
it cannot leak into another or the next request. Raw reply validation/constraints
and history still see the unchanged model reply. Final character/duration bounds
include the formatted address. Cached replay PCM is not resynthesized/prefixed.

Alice-mode worker metadata exposes `speech_address_prefix`,
`speech_address_scope="tts_utterance"` and formatted `spoken_text` separately
from the unprefixed `reply`. This reports TTS input formatting, not proof of
audibility or consumed PCM. Agent uses a bounded, nonempty string `spoken_text`
for its own-speech echo reference, falling back to `reply` for absent/malformed
metadata. It rechecks current microphone/policy epochs after reading the event,
so a late withdrawn reply cannot update that reference. This includes the
address word when checking a short own utterance such as `Алиса, да` for echo.
No self-speech source admission or automatic microphone activation is added.

The initial Alice configuration closure is worker `voice.py` + `config.py`, and robot Agent
`agent.py` (plus `config.py` if its selected profile contains this key). The
request-scoped extension needs only matched worker `voice.py` and Agent
`agent.py` over that existing Config baseline; no Config/schema package change.
`config.example.json` documents the empty default; Config also fills that default
without a newer example file. Keep the Agent metadata consumer and worker
producer matched for the Alice trial. No new package, inference endpoint, model,
router, hardware controller or service is required. The runner owns the finite
real-model/Alice/mute/epoch/echo acceptance; local tests use synthetic TTS/PCM.

## Read-only operator preflight through Hub

An authenticated `GET /control/operator` on the existing Hub forwards only the
fixed Agent `GET /operator` using the current token. It returns the complete
typed operator object, including Agent boot, microphone and policy epochs,
microphone/capture/listening state, policy booleans, both owner IDs, error state
and expression version. Owner `null` remains distinct from an absent field.
Valid motor/quiet/privacy values are reported unchanged, not granted or altered.
The proxy does not use `/control/status`, cache a previous receipt, accept a URL
or path parameter, or fall back to another source.

Authorization is checked before upstream access. The read uses a 300 ms HTTP
timeout, an 8192-byte JSON response bound and strict duplicate/nonfinite JSON
decoding. Hub measures elapsed time from immediately before upstream access,
checks the full typed result within 300 ms, and checks freshness again after
serialization before sending the response. Malformed, missing, erroneous or
expired operator state fails closed with sanitized `503 operator_unavailable`;
no exception messages or upstream bodies are returned. All responses on this
route carry `Cache-Control: no-store`.

This is a Hub-only source change using stdlib and its existing authenticated
Agent client. No Agent rollout, bind/firewall/configuration change or new
namespace/dependency is required. PC preflight must independently measure its
total request duration from its own BEGIN and compare the exact expected current
boot/epochs and operator OFF state. A successful proxy read is an observation,
not permission, ownership acquisition, a state write or a readiness grant.
