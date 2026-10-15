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
