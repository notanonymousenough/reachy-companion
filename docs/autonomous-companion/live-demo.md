# Existing live voice demo

From the Mac with the existing working SSH access and local private configuration:

```sh
./scripts/companion-demo --turns 3 --seconds 180
# If the existing pinned robot hosts file is outside ~/.ssh/known_hosts:
./scripts/companion-demo --robot-known-hosts /path/to/existing-known-hosts --turns 3 --seconds 180
```

For a reviewed same-owner cue/resume controller, start with Agent capture paused:

```sh
./scripts/companion-demo --prime-paused --turns 1 --seconds 40
```

This optional mode changes only the **first** owned microphone ON grant to
`listen=false`. The same boot/epochs/owners, CAS checks, independent watch and
cleanup remain. The client never resumes automatically or adopts a newer epoch.
After its bounded cue, the existing guarded controller uses the direct Agent
`/resume`, which sets listening without changing the microphone epoch/owner.
Without that controller the mode waits until its deadline, then performs owned
OFF cleanup. The default command still grants `listen=true`. This needs the
matching updated Hub client file and Mac launcher; no service, Agent or worker
restart is required. It fixes the diagnostic admission gap, not the unknown
spoken-camera child cause, and its publication is not a real diagnostic PASS.

The optional exact `53a` spoken-snapshot overlay is described in
`deploy/patches/agent-53a-spoken-vision.md`. Once installed and verified by the
sole runner, the normal demo accepts «Что перед тобой?» / «Что ты видишь?» from
a fresh normal STT turn. It reuses the same camera/native FINAL and speaker
path. Its first real spoken-camera attempt failed inside the snapshot child;
ordinary speech still works. The child cause is unknown; the next helper-only
diagnostic is documented in `deploy/patches/spoken-vision-child-diagnostics.md`.
This dispatcher has not passed real device acceptance; the preceding
explicit snapshot checkpoint has already passed human scene verification,
spoken output, stock motion and STOP. Ordinary session context is retained;
visual question/answer history is not added. The overlay adds a separate STT
request and classification pass to normal fresh turns.

For one explicit camera snapshot and a spoken description:

```sh
./scripts/companion-demo --vision --seconds 180
./scripts/companion-demo --vision 'Что перед тобой? Опиши подробнее.' --seconds 180
```

Show the scene before requesting the snapshot. This is a command-triggered turn;
it does not listen for a spoken camera request. The snapshot caption is
not added to that conversation history in this increment.

This mode requires the separately reviewed exact Agent speech-binding overlay
described in `deploy/patches/agent-0a7-bound-vision-speech.md` and the matching Hub
client. An authenticated read-only capability check rejects an old Agent before
camera access or permission claims; there is no unguarded speech fallback.
Pixels travel only from the Robot's existing camera IPC reader to the configured
local PC native API in RAM. One latest 640×360 PNG is admitted within two seconds
of dequeue; camera closes before inference. There is no raw image file, image
export to the Mac/Hub, new model, new audio owner or new motor controller.

The existing configured loaded 9B instance is selected exactly from native
`/api/v1/models`. The tested `/api/v1/chat` request uses text plus image data URL,
`store=false`, no integrations, no previous response and a 2048 output-token cap.
Only bounded `message` FINAL is eligible for speech; reasoning, tools, empty or
tagged reasoning content, changed instance and reported model loading are denied.
An unknown/failed inference is never automatically retried in the same run.

After inference, the same watch owner enables microphone permission with
`listen=false`, keeping capture/listening OFF, solely to use the existing Agent
`/say` TTS/playback/stock-expression path. The bound speech request checks the
planned boot, microphone/policy epochs, both owners and a Robot monotonic expiry
before and after the audio lock and during playback. Ctrl-C or microphone OFF
revokes it; a late result cannot adopt a new owner's epochs. Exposure age is
unverified: this describes a snapshot, not certified live scene tracking.
Snapshot speech admission expires 60 seconds after dequeue. A cancelled/expired
result is discarded, and final owned cleanup/volume preservation is unchanged.

`--turns` is unused for this single explicit snapshot. Its summary reports
`vision_speech_completed`, meaning the existing speaker RPC completed, not proof
of audible or semantically correct speech. Human scene verification, actual
owned aplay and bounded SDK movement/STOP remain the runner's acceptance gates.
Only frame/timing metadata and sanitized failure phase/class may remain in the
private run directory; neither the caption nor pixels are persisted there.

This wrapper reads the existing local `config.local.json` deployment targets.
It reuses the reviewed foreground SSH mux and documented factory credential
helper (credential in RAM, never logged), strict host key verification and the
existing Mac-to-Hub SSH route. It does not enroll keys or hosts. `--config` can
select an existing private configuration. Hub-to-Robot SSH is not required.

Before launching the Hub child, it arms and verifies a separate device systemd
watch with the same private owner and current boot/epoch baseline. The watch code
is retained in `deploy/autonomous/demo_watch.py`, using the existing Agent CAS
cleanup, process identity and factory observation functions. Each run gets its
own private source/plan; it never imports an old `/run` trial. The device deadline
is child seconds plus 20 seconds, with a separate systemd lifetime bound. Child
exit, failure or Ctrl-C requests owned cleanup immediately. A lost Mac/SSH leaves
the independent device watch active until its deadline. Cleanup must be verified
OFF with no playback/factory task and the operator's starting volume preserved;
unknown remains a nonzero result.
No new service installation, model, microphone capture process or UART owner is
created. The existing sudo command on the robot arms the transient watch; the
user does not manually arm it. Source review and actual runner acceptance of
this wrapper are required before calling it a working hardware launch path.

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

The lower-level CLI below is for an already supervised run. The Mac wrapper
above invokes `demo()` directly with its watch owner and baseline; it pins the
installed Hub client to this checkout's source hash. With an independent watch
already armed and the existing private configuration available locally:

```sh
./scripts/companion demo --turns 3 --seconds 180
# Explicit configuration, if needed:
./scripts/companion --config /path/to/config.local.json demo --turns 3 --seconds 180
```

Before starting: Agent paused, microphone/capture/listening OFF and unowned;
policy unowned, quiet/privacy OFF; stock selected, known, free and motors enabled.
Set the desired volume with the existing control page; 100% is supported. The
launcher accepts audible volume 1–100 and never sets or restores volume itself.
The watch records the current starting volume and reports `volume_preserved`
after cleanup. A later operator volume change is retained, with a mismatch
reported instead of being overwritten. It does not wake sleeping motors or alter
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
Watch cleanup also retires an unused unchanged baseline with OFF-only CAS writes,
bumping its epochs before exit. Unowned OFF writes omit owner parameters rather
than sending null. Partial claims are released and any remaining unchanged
baseline is fenced. A changed boot, newer epoch or foreign owner is preserved;
an old delayed child then fails its initial binding check instead of starting
after the watch has ended. This path still needs actual runner acceptance.
Each target is retired independently: a lost microphone ACK never prevents an
OFF-only policy CAS against its own unchanged baseline, and neither target's
newer owner is overwritten. Mutation ACK loss remains explicitly unknown; there
is no POST retry or guessed success. The wrapper additionally requires verified
`admission_retired=true` for both old epochs before treating cleanup as healthy.

Wait for `Microphone capture active` before speaking. An existing startup greeting
is not a model answer and does not count as a completed turn. Use a harmless
fresh marker in the first question, ask for it in the second, and ask a follow-up
in the third. For example, say “Мой маркер — клён. Повтори его”, then “Какой мой
маркер?”, then request a longer answer and stop it while speech is audible.
Replies must come from the actual configured local 9B. Do not substitute scripted
answers or count a greeting/acknowledgement as the final reply.

STOP: press Ctrl-C in the launcher, or switch microphone OFF in the existing
control page. The latter overrides demo ownership and the launcher exits without
restoring it. Deadline (10–300 seconds) and observed-turn threshold (1–3) also end
the run. Cleanup sends microphone OFF/listen false and motor permission OFF only
for the launcher's unchanged boot/epoch/owner claims. It never restores old ON
states or overwrites a newer operator. Mic OFF uses the existing Agent speaker,
capture and expression cancellation path; factory motion retains its existing
owned-task stop checks. This is not a certified physical emergency stop.
Observing the completed-turn threshold enters cleanup immediately, including
when the next capture is already recording; it does not wait for a listening
phase. `--turns N` is a client observation threshold, not an Agent admission
budget or a guarantee of exactly N real turns. The Agent may already have
admitted another turn between polls, so an in-flight turn can exceed the
threshold. The duration and independent device watch remain the finite bounds.

The printed summary contains the last observed counter delta and a stock task
observation only, without
transcripts, prompts, audio, tokens or private configuration. A new stock UUID
is a task receipt, not proof of physical movement. `physical_motion_verified`
and `context_verified` intentionally remain false: the runner must separately
record actual visible bounded motion, audible final replies, correct second-turn
marker recall, STOP during audible speech, microphone/capture OFF afterward,
policy OFF/released and the operator-selected volume. Summary `completed_turns` is the last delta
observed by the client, not the final post-cleanup Agent delta or proof of an
exact per-run turn count. A CLI zero exit means the observed threshold was
reached and cleanup succeeded; it does not certify those physical acceptance
gates. The legacy worker's `last_turn` snapshot has no attempt identity,
completion timestamp or cancellation association, so it cannot establish which
Agent turn it belongs to or end-to-end latency. Counter/text disagreement is
not resolved by assuming that this snapshot is the final accepted turn.
Cleanup reads back microphone/capture/listening OFF and released policy/owners.
Unknown stock-task completion or failed/changed readback produces
`cleanup_unknown=true` and a nonzero exit. A normally completed retained stock
UUID with no explicit absence/stop receipt also remains unknown to this CLI;
the runner must check actual factory running tasks. `cleanup_failed=true` or
`cleanup_unknown=true` requires checking the existing operator control immediately.
