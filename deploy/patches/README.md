# Review-only SDK 1.11.0 owned stop patch

`reachy-mini-1.11.0-owned-stop-idempotent.patch` is a candidate change to the
official Reachy Mini SDK 1.11.0 `reachy_mini/daemon/app/routers/move.py`.
It has **not** been applied to an installed daemon by this change.

Exact full-file SHA256 before patch:
`ca18dbc85041a49b784b17b0bb09c06a7c6eec82bcd8f1dd2a23d64275a18943`.
Exact full-file SHA256 after patch:
`8e7d7dae115c50949de0f91dddf71bbf88cb7f354ff5e396b8626d4caec14d76`.
Reject any other preimage; do not apply with fuzzy context or silently upgrade
the SDK. Source provenance: `pollen-robotics/reachy_mini`, Python package
`reachy-mini==1.11.0`, Apache 2.0. The retained license is alongside this file.
The small test fixture contains verbatim upstream task/stop functions with a
local import/registry harness; it is never imported by production services.

The original endpoint raises an uncaught `KeyError` if a movement UUID completed
before the stop handler, producing HTTP 500. The patch returns an explicit
already-absent acknowledgement for that exact UUID. It never stops another
UUID or invokes the SDK's global stop command. The present-task branch still
pops, cancels and awaits the same task exactly as before.

`POST /api/move/stop` request remains `{"uuid": "CANONICAL_UUID"}`. Its successful
response retains the legacy `message` and adds `uuid` and a boolean
`already_absent`. `true` means this UUID was absent at handler lookup; `false`
means the existing task cancellation path ran. Both function return annotations
include the boolean so FastAPI response validation preserves its type. Invalid
UUID input still returns 422. This acknowledgement describes the REST task
registry; it is not a measured physical halt or pose certificate.

Hub's separate correction avoids a stop POST based on an expired empty
preflight: one bounded fresh read may establish ready/free absence within the
unchanged 300 ms limit. If that read expires or fails, the Hub retains unknown.
That Hub-only correction cannot eliminate an active-to-completed race between
a fresh GET and the stop handler; the SDK patch addresses that remaining case.
No HTTP 500 is treated as success, no stop POST is retried, and no existing
unknown latch is reset or automatically reconciled.

Before any device use, the sole runner must review this patch, verify the
installed preimage, retain a recoverable original, and perform a separately
reviewed finite apply/restart/readiness/rollback sequence. Actual completed-UUID
and active-to-completed checks, foreign-task preservation, microphone/operator
state and factory recovery remain hardware acceptance gates. Local tests only
check exact patch application and the FastAPI/task response contract without
starting a daemon or connecting to a device.
