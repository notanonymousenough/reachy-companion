# Finite opt-in voice streaming acceptance

This is the next implemented candidate after review-only `b90d40b`. The actual
current 9B SSE contract has now passed one PC request: stop + DONE, exact configured
identity/object/id/index, 75 nonempty chunks, two semantic segments. First token
was observed at 0.4917 s, first segment at 1.19314 s and last text delta at
1.44435 s. These are PC **READ** timings; there was no TTS, camera or real voice
overlap in that test. Current effective prefix properties (balanced, closed
think region) were also verified without exporting prompt values. There is no
need to repeat those capability probes before the next voice increment.

The exact legacy preimages remain those in
[content-token-stream-source.md](content-token-stream-source.md). Brains still
maps `9c69…` → `020e435…`; the current worker maps `92cf…` → `bbdb7be…`, adding
opt-in startup resolution, the stream hook and an optional first-segment audio observer. The new
runtime helper contains the implemented reader/owned HTTP transport. Do not replace the whole package,
build a HEAD worker image, repair old container/spec drift, change the model,
Agent or camera helper. Final helper hash/public pin must match the handoff.

Current exact three-file bundle (these are not the repository HEAD brains/voice):

| File | SHA256 |
|---|---|
| brains.py | `020e435e37602271d2d40160b055650f781b60a8ee9fc601e3b28d82444bdae6` |
| voice.py | `bbdb7be523946396cedd16a2f629caabdb54bf3d9979bfd5e7403f2730995764` |
| token_stream.py | `a4aa26d375b46cfd0348f6cb42df6adb1f82a0f1b4252afb11df571f4edc539d` |

The first real attempt produced meaningful speech and owned STOP, but its short
response completed before playback: overlap NOT met. The next stream-only
first-sentence refinement and FIRST-segment telemetry require the matching
shared private-consumer contract, not the old handwritten metadata allowlist:
[content-first-sentence-iteration.md](content-first-sentence-iteration.md).
Producer/consumer pins must be reviewed together before any new activation.

Generate it reproducibly on the Mac from public local Git preimages and frozen
patch/helper hashes; this command does not contact devices or change config:

```sh
python3 deploy/autonomous/prepare_content_stream.py /private/tmp/reachy-content-stream-bundle
```

The destination must be new. The builder rejects source drift before creating
it and emits exactly the three files and a source-only manifest. Do not copy
`src/reachy_companion/brains.py` or `voice.py` from HEAD into the current worker.

## Implemented reader and cancellation policy

One producer thread continuously parses the **same** SSE response independently
of Piper. The queue is bounded by 8192 events and 1 MiB, the parser's full finite
envelope. It never waits on a full queue: overflow is a sticky withdrawal,
atomically purges pending text and switches the same request to DISCARD. A
late return from running Piper is checked before emitting motion/PCM, so a
withdrawn attempt cannot publish the returned chunks. There is no second POST.

The explicit acceptance override is `streaming.content_request_seconds=40`,
chosen before the one model POST. It uses one absolute deadline; it is not
2 + 40 seconds. Without this override the source uses the configured LLM timeout
(currently 240 seconds), which is not silently changed for production. The
owned socket is registered before TCP CONNECT, POST or response HEADERS. Its
absolute watchdog covers CONNECT/HEADERS/BODY, handles trickled headers/lines
and is joined on exit. Address resolution happens once in opt-in worker startup
readiness, before any model request or background reader exists; a DNS failure
keeps the candidate unready and the runner's finite startup method handles it.
Only the actual POST attempt marks the model permit submitted. A connect failure
before POST therefore does not falsely claim submitted model work.

Consumer close stops forwarding and purges pending text. Hardware STOP is still
the existing Agent/microphone/epoch path and does not wait for PC drain. After
the two-second fast grace, the reader continues DISCARD under the **original**
request deadline. It keeps the response open; it does not close/reset it merely
to free admission. The next worker model POST must wait for both verified finish
+ DONE and consumer/Piper cleanup. Producer join completes before successful
worker done/known cleanup. Next-turn handoff can therefore wait for old request
completion; this is not instant fluent interruption or continuous listening.

Transport error or deadline without terminal stays UNKNOWN and rejects the
next same-backend worker request. It is not timer-cleared and must not be called
recovered. If the reader cannot quiesce, the attempt reports failure, never known
cleanup. Stop the finite run and retain evidence; no blind model unload, foreign
restart, guessed cancel endpoint or overlap POST is an allowed recovery. A healthy
slow tail now has a concrete finite path to verified terminal and next admission;
unprovable network/model failures remain explicit failure outcomes.

The model permit is process-local to this worker and shared with its ordinary
and classifier calls. The existing Robot native camera API caller is outside
this guard. This acceptance window has the runner as sole model caller, with no
camera or competing model task until terminal/quiescence is established.

One bounded metadata record per attempt contains generated attempt ID, PC
monotonic/wall start anchors, first/last text-delta READ, terminal READ, semantic
and PCM-yield timings, queue peaks/overflow/backpressure, discard count and
producer quiescence. It contains no prompt, transcript, caption, image, model ID
or token values. Generation clock, cross-host clock and acoustic consumption
are explicitly unverified. PCM yield is not audible consumption. Further timely
nonempty delta receipts after independently observed meaningful speech are the
intended next evidence; a buffered/lazy last-read timestamp is insufficient.

## Sole-runner rollout method

1. Fresh preflight: current unique owned PC worker and exact installed source
   hashes, model instance preserved/idle, no foreign inference, all Robot sessions
   ended/known OFF/unowned/100%, factory known/free, no aplay/camera/controller.
   Identify the current worker from fresh evidence, not a historical container ID.
   A camera request that becomes ready takes priority before this voice window;
   never run both device-owner sessions concurrently.
2. Save exact private preimages of brains.py, voice.py, optional prior helper and
   the protected worker config/profile. Retain service/image/spec/mount/token
   identities, effective model config, original timeout, Robot state and volume
   checks. Build the two exact patches with zero fuzz off-device and verify final
   public pin/helper hashes. Current-worker evidence shows a read-only rootfs,
   brains in the immutable image, an existing read-only voice.py bind and no
   writable package parent for the new helper. Direct copy plus restart is not
   a valid method. Derive a **stopped** candidate from the fresh current immutable
   image/spec: replace only the existing site-packages voice.py bind and add
   read-only site-packages brains.py/token_stream.py binds. Preserve every other
   security option, mount, port, environment and process argument. No image build,
   old-spec replay, package migration or extra dependency/identity module is used.
   Keep the old worker available for rollback. Temporarily set `streaming.content_tokens=true` plus
   `streaming.content_request_seconds=40`. Do not alter global timeout240, model
   token budget512, template, instance, classifier, STT, TTS or motion settings.
3. Review the runner's concrete spec delta/executor before creating or switching
   the candidate. With old worker idle/model terminal and no device session,
   stop only that owned worker, start the reviewed candidate on its same endpoint,
   and retain the old stopped worker. There is one active worker; no PC model/runtime,
   Hub/router, Robot Agent, factory or foreign service restart. Verify exact
   mounted files, current process/readiness and effective opt-in/40-second
   config, model instance/VRAM health and Robot OFF100 preserved. Source + transition
   readiness is not yet proof of executed streaming; the actual attempt/metadata
   must demonstrate that path. Retain config backup for exact restoration after
   terminal/quiescence. No restart between STOP and the next-turn acceptance.
4. Run the existing finite voice/watch path (at most 180 seconds). Prime a normal
   short fact/answer and verify the actual STT/context evidence if context is part
   of the chosen scenario. Ask for a neutral longer explanation with a short
   meaningful first sentence followed by detail, within the unchanged 512-token
   cap. No fixed ACK or prefilled answer is evidence. Record actual owned aplay,
   substantive heard content, stock task/pose evidence, PC reader metadata and
   independently bounded clock alignment. Need meaningful speech followed by
   further timely nonempty delta receipts, no queue overflow/backpressure. Do
   not rename READ receipts as backend generation timestamps.
5. STOP while generation/speech is active. Verify immediate operator OFF/physical
   stop separately from PC cleanup, no stale PCM/cues/resume. Allow the same PC
   reader to reach terminal within its original 40 seconds; require producer
   quiesced and no remaining old producer/Piper work. Only then use a fresh owned
   voice window for the next real question if STOP retired the first watch. The
   same PC process must answer it once, with prior committed context intact;
   an interrupted full assistant reply must not be committed as spoken history.
6. End in known Robot OFF/unowned, factory empty/stock known/no aplay/camera and
   volume 100%, with PC worker idle and model instance preserved. Restore exact
   protected config in the accepted method, without racing an active producer
   or changing a newer operator. If returning to default-off, stop the candidate
   and restore the exact protected config/old worker only after terminal/quiescence
   and all acceptance turns, never as interruption recovery. On failure restore
   only this owned transition in a verified idle window; UNKNOWN is not an
   excuse to restart foreign work or unload the loaded model.

The runner's concrete executor/readiness/rollback is reviewed before execution.
No implementation author performs parallel SSH/device sessions. Local source
checks include slow-terminal recovery beyond two seconds, total-deadline body/header trickle,
real saturated local TCP accept-queue CONNECT abort before POST,
lease held until consumer cleanup, full-queue withdrawal and late Piper output.
Those checks do not replace the real long-answer/STOP/next-turn acceptance.

Continuous hearing, rolling capture, partial STT and improved endpointing are
the next small seam. They remain required by the user and are not implemented
or accepted by this reader increment.

## Repeatable user entry point is part of completion

After actual acceptance, retain the runner's exact guarded executor and provide
the user its concrete one-command launch (or a thin existing `companion-demo`
entry point if needed). It must re-enter this tested finite lifecycle with fresh
guards, run voice, wait for terminal/quiescence and restore the protected baseline
without a new general permission chain. Config restoration alone does not restore
the running baseline process: switching back to the retained old worker is a
separate final event. The raw voice command by itself does not enter the candidate.
Do not claim delivery complete while the user only has source files and OFF mode.
If keeping the working streaming service is preferable after success, describe
and apply that explicit reviewed lifecycle choice then. The first actual
long-answer/STOP/next-turn pass takes priority over adding a launcher framework.
