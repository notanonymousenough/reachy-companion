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
