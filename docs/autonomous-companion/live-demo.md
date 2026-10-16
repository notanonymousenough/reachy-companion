# Existing live voice demo

Use the already installed local STT, 9B model, Piper, Agent and stock factory
motion path. No additional models, dependencies, audio owner or memory service
are required. The existing conversation session supplies bounded short history.

The launcher requires this revision's Hub: `/control/microphone` must forward
the Agent's existing boot/epoch/owner fields, and `/control/status` must include
`turns`. Update/reload only the Hub source/service through the sole device runner
before using the command. The Agent and worker interfaces remain unchanged.
There is no downgrade to an unguarded microphone write on an older Hub.
An earlier direct Agent API trial is separate from acceptance of this CLI.

Control comparisons validate the complete typed operator response but compare
boot, microphone epoch/enabled/owner and the full motion policy/owner as authority.
The idle expression counter can change without changing those permissions.
Every ON grant still requires a fresh paused Agent with microphone, capture and
listening OFF and quiet/privacy OFF. OFF cleanup permits normal phase transitions.
ExpressionPlayer's separate motion version checks remain active. Every actual
socket send still requires an operator read younger than 300 ms and server CAS.
Read-only polling tolerates one transient HTTP 503 by issuing at most two fresh
GET attempts. The second attempt has its own read-BEGIN time and must fit the
remaining overall demo deadline, which includes admission. No cached operator
state is used for a write. POST commands are never retried. Repeated 503, invalid
authority, malformed responses and other errors end the run and enter cleanup.

With the existing private configuration available locally:

```sh
./scripts/companion demo --turns 3 --seconds 180
# Explicit configuration, if needed:
./scripts/companion --config /path/to/config.local.json demo --turns 3 --seconds 180
```

Before starting: Agent paused, microphone/capture/listening OFF and unowned;
policy unowned, quiet/privacy OFF; stock selected, known, free and motors enabled.
Set volume to 50 with the existing control page. The launcher requires an audible
volume at most 50 and preserves it. It does not wake sleeping motors or alter
configuration. Admission failures stop before listening is granted.

The sole runner must arm the existing independent device stopwatch before
granting microphone/motor permission. The CLI deadline is a client loop, not a
device lease: killing the client or losing its network can prevent cleanup.
Do not use this launcher unattended without that independent watchdog.
The existing trusted watch launcher may call `demo(config, owner_id=owner, ...)`
after arming and verifying its independent watch for that same canonical nonzero
UUID. The default remains a freshly generated UUID. This internal argument does
not arm a watch or verify readiness by itself; it supplies neither a new CLI flag
nor a file/environment handoff protocol. A self-contained user wrapper must reuse
the actual installed watch launcher's arm/readiness-to-child path.
That launcher must also pass its initial `operator_binding` containing exactly
`agent_boot_id`, `microphone_epoch` and `policy_epoch`. `demo()` validates this
optional internal argument before I/O and compares it with its own first operator
read before any claims. A changed baseline denies admission, so the watch's exact
epoch cleanup cannot silently cover a different run. Subsequent reads and writes
retain the existing fresh authority and CAS checks.

Wait for `Microphone capture active` before speaking. An existing startup greeting
is not a model answer and does not count as a completed turn. Use a harmless
fresh marker in the first question, ask for it in the second, and ask a follow-up
in the third. For example, say “Мой маркер — клён. Повтори его”, then “Какой мой
маркер?”, then request a longer answer and stop it while speech is audible.
Replies must come from the actual configured local 9B. Do not substitute scripted
answers or count a greeting/acknowledgement as the final reply.

STOP: press Ctrl-C in the launcher, or switch microphone OFF in the existing
control page. The latter overrides demo ownership and the launcher exits without
restoring it. Deadline (10–300 seconds) and completed-turn bound (1–3) also end
the run. Cleanup sends microphone OFF/listen false and motor permission OFF only
for the launcher's unchanged boot/epoch/owner claims. It never restores old ON
states or overwrites a newer operator. Mic OFF uses the existing Agent speaker,
capture and expression cancellation path; factory motion retains its existing
owned-task stop checks. This is not a certified physical emergency stop.

The printed summary contains counts and a stock task observation only, without
transcripts, prompts, audio, tokens or private configuration. A new stock UUID
is a task receipt, not proof of physical movement. `physical_motion_verified`
and `context_verified` intentionally remain false: the runner must separately
record actual visible bounded motion, audible final replies, correct second-turn
marker recall, STOP during audible speech, microphone/capture OFF afterward,
policy OFF/released and volume 50. A CLI zero exit means completed-turn count
and cleanup succeeded; it does not certify those physical acceptance gates.
Cleanup reads back microphone/capture/listening OFF and released policy/owners.
Unknown stock-task completion or failed/changed readback produces
`cleanup_unknown=true` and a nonzero exit. A normally completed retained stock
UUID with no explicit absence/stop receipt also remains unknown to this CLI;
the runner must check actual factory running tasks. `cleanup_failed=true` or
`cleanup_unknown=true` requires checking the existing operator control immediately.
