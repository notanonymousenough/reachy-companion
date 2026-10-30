# S7 R32 — measured readiness expiration, read-only

17 October2026, Europe/Moscow. One ROOT scope16:13:47–16:23:47; S7 sole read/physical owner. **Exact R31 read path reproduced one elapsed-only rejection out of12, with every readiness flag healthy. R30 operator freshness rejection was not reproduced.** No implementation or new product feature. Useful ordinary local voice/camera/+2dB remain ON, motor142OFF.

## Bounded measurement and result

[Analysis](../../S7-evidence/R32/analysis.json), [Robot samples](../../S7-evidence/R32/robot.json), [Hub samples](../../S7-evidence/R32/hub.json), [single runner](../../S7-evidence/R32/run.py). Twelve samples per origin,2s start-to-start spacing, Robot then Hub sequentially, no parallel high-rate observer. Natural production calls continued independently. Actual methods came from pinned production Agent1f4e52a6… and Hub008be03…; `__init__`, SDK/media/session constructors, Hub server and stock_begin were never invoked. Existing config/auth/no-proxy openers/default configured timeouts used (HTTP10s, factory5s). Clocks surround the real request methods through JSON decode; SSH/auth/startup are separately recorded in origin files, outside these durations.

Robot samples16:15:50.461–16:16:12.463, final body/metadata after its1.09s read:

| Read | Min ms | Median ms | Max ms |
| --- | ---: | ---: | ---: |
| loopback Agent/operator | 3.740 | 4.968 | 11.873 |
| configured Hub/status | 58.045 | 77.447 | 1087.187 |
| configured factory/api/move/running | 3.581 | 6.650 | 7.811 |
| exact R31 sequential Hub/status→running | 65.853 | 83.694 | 1094.553 |

**Sample12 at16:16:12.462609:** exact two-read R31 total1094.553ms>300ms, of which Hub/status1087.187ms and factoryrunning7.367ms. The thirteen other reject flags were allfalse: correctly typed data/running list, runningcount0, actionfalse, ownershipfree, stockselected/known/unowned, daemonrunning/errornull, backendready/errornull and valid same Hubboot5a2502a1…. Agent was naturally speaking; local operator read5.561ms, sameffae…boot/mic309/policy142/motorOFF. No read/HTTP error. **A current mechanical cause is proven: a healthy but late full Hub/status receipt alone expires the R31 admission window.** This does not identify the original R31 event's subpredicate retrospectively.

Hub samples16:16:15.616–16:16:37.617:

| Exact production GET | Min ms | Median ms | Max ms |
| --- | ---: | ---: | ---: |
| Hub.agent('/operator'), default timeout/decode | 18.517 | 24.844 | 34.754 |
| factory daemon/status | 11.476 | 17.650 | 37.142 |
| factory robot-app-lock-status | 11.905 | 15.195 | 113.972 |
| factory state/full | 10.301 | 16.959 | 39.419 |
| same three sequential factory reads used by Hub/status | 40.425 | 50.816 | 190.533 |

All12 operator bodies passed exact typed validation;0freshness rejects. MotorOFF is intentional and not counted as a permission fault. Factory responses were typed/running/ready/error-free/free. **Historical R30 `Fresh stock operator required` remains not reproduced in this motorOFF sample set; it is not declared fixed or explained.** The Hub component series followed the Robot series, so it cannot attribute the earlier1087ms outlier to one inner endpoint, serialization, TCP/DNS/network/server queue or microphone lock. No further sample wave was run.

## Counts and retained operation

Actual initiated client reads: Robot48GET (12each loopbackoperator, Hubstatus, factoryrunning, Agentstatus metadata) + Hub48GET (12operator +36factory component reads) = **96GET**, all successful. The12existing Hub/status calls also execute36transitive factoryGETs by exact production code. POST/control/model/seed/speech/motor/frames/restart/source/config changes0. No raw response bodies, poses, utterances, camera pixels, privateconfig or token persisted/exported.

Robot sampled natural phases processing2/speaking5/listening5. Same Agentbootffae…/mic309/policy142/source1; PCM7174144→7911424B, gaps0/overflow0/retiredfalse/captureON, voice/expression errors absent. Agentturncounter7→8 is metadata, not new semantic/fullplayback/conversation acceptance. Latest Hub-origin operator was naturally speaking; ending the diagnostic did not force STOP or idle.

Full known-ready fallback receipt **16:12:31.909** from R31 is reused as authorized, without repeating a full hardware/model test: Agent279280/bootffae5ace-f7d8-475e-bcb7-76f3ccae385d/mic309/listeningcaptureON, motor142OFF/ownersnull/privacyclear/Hubfree/stockknownunowned/workeridle/errorsabsent, onearecord279326/factory150625 unchanged, originalAgent/snapshot restored and initiative.pyABSENT. Camera2changingframes/readerclosed/pixelsexport0, hardware100%0dB/canonicalAlice and existing ordinaryfalse/ACKfalse/+2dB retained. R32's own samples add sameboot/currentPCM/readiness evidence, **not a newly measured final worker-idle or camera-frame receipt**. [R31 final](../../S7-evidence/R31/final-after.json), [camera](../../S7-evidence/R31/camera-pixel-check.json), [pins/gain](../../S7-evidence/R31/final-robot.json).

## One proposal, not implementation

Decouple the **new independent camera/speech initiative** from full remote Hub/status. Use existing local typed Agent boot/mic/policy/owner/privacy/generation, fresh real PCM/frame and sole audio-owner fences; motor staysOFF and initiative cannot grant or write motion. Keep existing Hub/motor300ms, STOP/CAS/privacy/owner/UNKNOWN and owned-cleanup rules unchanged, with no cached permission or automatic retry. Review independence and existing worker guards before implementation. This removes the measured unrelated full-motion/status dependency; it is not a claim that the unlocalized HTTP tail is repaired.

Remaining conditional cost **15–25min total** for source/review, meaningful cancellation/authority checks, one actual useful proof and rollback reserve. New ROOT/Tech scope required. Fallback is unchanged ordinary local voice/cameraON/motorOFF with R31 feature absent. No cost beyond this bounded diagnostic was consumed; no further tracing, source patch, install, arm or proof started.

**Hardware/read ownership explicitly released to TechLead:** 2026-10-17T16:19:01.741129+03:00. No further probes.
