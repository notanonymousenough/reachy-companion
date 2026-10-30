# S7 R30 — retention stopped at first motion fault

17 October2026, Europe/Moscow. **R30 early FAIL; no30min availability/conversation proof. Useful ordinary local voice and camera remain ON, motor policy142OFF.** S7 sole physical operator; no new seed/inference/model API, motion provocation, source/config/prompt/framework install or restart. Normal production calls continued independently.

Requested interval15:55:23–16:25:23. First actual receipt15:56:01.627832: same R29 boot46b5d19c…/mic303/motor141ON/captureON/source2, speaking/Agentturncounter2/errorsabsent/workeridle; normal in-flight Hub-owned motion was not classified as a fault. Two changing camera frames523008/523244B captured inRAM/readerclosed/noaudioinit/inference0. [Start](../../S7-evidence/R30/start.json), [camera start](../../S7-evidence/R30/camera-start.json).

The first periodic sample at **15:56:47.891153** found actual expression_error/HTTP409 while voice_errorfalse/Agentlistening/captureON/workerokidle/Hubfree/actionfalse/stockunknownfalse/unowned. Agentturncounter5, PCMsource2/read5560320B/gaps0/overflow0/retiredfalse, same Agent276911/factory150625 active/NRestarts0, arecord277110→276911. Monitor stopped immediately at firstfault; only one periodic sample, not continuous coverage. The requested30min window was not silently extended. [First fault](../../S7-evidence/R30/first-fault.json), [progress](../../S7-evidence/R30/progress.json), [monitor end](../../S7-evidence/R30/monitor-end.json).

## One exact causal classification

Existing Agent journal, allowlisted public error text only: **7 retained expression_unavailable records match `Fresh stock operator required`**, HTTP409, PID276911, timeline/neutral. This differs from R29's intended `expression_version_changed` cancellation and remains a real error. Agent request still preserves typed Hub body; exact Agent SHA1f4e52a6… confirmed. [Classification](../../S7-evidence/R30/classified-409.json). No arbitrary body/transcript/token/private config exported. Hub HTTP aggregate since15:55:23:46expressionPOST200 and12POST409. The remaining5 HTTP409s were not individually classified; no inference that they were successful cancellations.

In the exact deployed Hub008be03… source, `stock_operator()` raises this fixed error when its current operator result is not a dict **or** the read takes more than0.3s. Runtime per-call timing/type was not separately captured, so the narrower cause of failing that predicate remains UNKNOWN; no unmeasured latency claim. It is not justified to widen freshness/TTL/CAS/ownership limits or treat this rejection as success. No repair or retry was attempted in R30.

## Selective STOP and terminal fallback

One fresh boot/epoch-bound **motor policy141→142OFF**, quiet/privacyfalse preserved. No microphone control command. Three sampled Hubfree/actionfalse/stockknown/unowned observations established motion known terminal by **15:57:16.639871**; noUNKNOWN reconciliation waiver, source rollback or blind restart. [Selective withdrawal](../../S7-evidence/R30/motion-fault-off.json). Existing capture retired/reopened as expected from policy control; newsource3/read45056B then827392B, gaps0/overflow0/retiredfalse. Source2 is not stitched to source3 as a continuous-byte counter.

Subsequent60actualencoder samples/readerrors0/runningmoves0; no Hub expression POST after known terminal through15:58:11.367. [Post-fault encoders](../../S7-evidence/R30/post-fault-pose.json), [late-post receipt](../../S7-evidence/R30/late-posts.json). Operational motor withdrawal is not certified physical torque-off.

**Final actual15:57:41.039864:** sameboot/mic303/listeningcaptureON/source3/PCM827392B/gaps0overflow0/retiredfalse, motor142OFF/ownersnull/quietprivacyfalse, voice/expression errors absent in stopped motion lane, Hubfree/actionfalse/stockknownunowned/workeridle, volume100. Agentturncounter6. End camera2differentframes522375/522490B inRAM/readerclosed/pixelsexport0/audioinit0/inference0. [Final](../../S7-evidence/R30/final.json), [camera end](../../S7-evidence/R30/camera-end.json). Ordinaryshort=false/ACKfalse/+2dB remain unchanged by R30; installed R29 player1e25036f… retained, factory/Agent/Hub/PC models/worker not restarted. Voice benefit is preserved; absence of current error after disabling motion does not repair motion availability.

Natural counter2→5→6 is reported only as Agentmetadata. No new spoken-content/semantic/fullplayback/acoustic acceptance was performed; sparse APLAY sampling does not count full replies. R28 two useful replies remain prior voice evidence. Missing nonemptySTT alone was not treated as a model hang; here actual PCM and natural turn counter continued.

**One remaining motion blocker:** Hub stock operator freshness/type guard rejects normal production expression work. R30 consumed only the early-fault/knowncleanup/terminal work; the unused30min interval was not used for repair. Further repair scope/cost requires ROOT/Tech decision; no follow-on task/R31/probe/modelcall is launched by this handoff. Preserve voice/cameraON and motorOFF. Existing `scripts/companion voice microphone-off` remains explicit listening STOP; motion is already withdrawn.

**Hardware explicitly released to TechLead:** 2026-10-17T15:58:42.883307+03:00. No further probes/inference.
