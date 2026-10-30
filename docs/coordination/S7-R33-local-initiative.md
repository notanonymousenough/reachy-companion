# S7 R33 — safe opt-in installed; question not yet tested

17 October2026, Europe/Moscow. **ROOT accepted partial admission/cancellation and directed KEEP the known-safe opt-in installed. Voice/camera/+2dB ON, motor142OFF. No active initiative: generation4/cancelled/frameNULL. Actual new-frame→model→spoken-question capability remains UNTESTED, not mechanical or semantic PASS.** No human QA was required or awaited; the early asynchronous local-review question was explicitly withdrawn in chat as answer-not-needed.

Scope16:19:07–16:44:07, source+review≤16:27:07, proof≤16:39:07. S7 sole physical owner; sourceR21, independent gateTech. No further arms, models, frames, diagnostics or source variants after terminal.

## One exact installation

Actual16:20:29 public pin/metadata verification matched all R31 exact production preimages and initiative.pyABSENT, Robotconfiga6171f68… unchanged. [Live preimages](../../S7-evidence/R33/live-preimages.json). [Frozen manifest](../../R33-evidence/transfer-manifest.json), [Tech gate](../../TECH-evidence/R33/source-gate.json):17source+5independent groupsPASS. Only initiative differs from frozen R31; Agent/snapshot/purpose/old operator and spoken route unchanged.

Installed AgentSHA `7bd09093c4193af54e72bc5e95934f3c4f30f4d0a1b08a329f2670e531bd57d2`, snapshot `04e63d85d9ce458248d78ef029076878e556f111bfa46a2e8597366721e78e06`, initiative `0823f632fe998c2801cb2abd986129752958e90b06d5f06e20d02c466528bb6b`. The new initiative removes full remote Hub/status/factory-running/motor-readiness reads from its admission/child path and retains exact typed local authority with300ms bound, boot/mic/policy/owner/privacy/listening/generation, actual new-PCM quiet and frame/model/audio/STOP fences. Old Hub/motor300ms/CAS/UNKNOWN/owned cleanup unchanged. **The existing Agent global Hub preflight remains; full Agent independence from Hub is not claimed.**

Fresh Mic309→310OFF/drain/workeridle/Hubknownfree; one stopped-Agent atomic3-file installation preserving uid1000/gid1000/mode0664, syntax compile only. New protected exact source backup `/var/tmp/reachy-S7-R33-20261017` (directory0700, preimages/metadata0600), independent ofR31 backup. Agent-only restart: PID279838/newboot `c7770b79-c87d-476f-abbe-770873659383`, firstverifiedmic310OFF/motor142OFF/knownidle. Factory150625/Hub/PCworker/models/config unchanged. [Install](../../S7-evidence/R33/install.json), [newboot](../../S7-evidence/R33/new-boot-off.json).

## Pending STOP — same-event reconciliation PASS

Fresh Mic311ON, documented local arm accepted generation1. Actual Agent receipts: `/initiative`200 at16:23:40.346863, `/microphone`200 at16:23:40.682773: **0.335910s**, before3s minimum real quiet/newPCM admission. Mic312OFF, generation2cancelled/frameNULL/noaudio/camera child/arecord; known paused/Hubfree/actionfalse/stockknownunowned/workeridle/errorsabsent. [Receipts and local state](../../S7-evidence/R33/pending-reconciled.json), [same-event proof](../../S7-evidence/R33/pending-stop.json), [known readiness](../../S7-evidence/R33/pending-ready.json).

The first collector failed **after the accepted arm/OFF** on its unrelated GETworker/status transport timeout1s. It did not fail or retry initiative control. Existing accepted receipts and current state reconstructed the original event; no re-arm or model/frame was used for this reconciliation. Observer metadata reads then used existing configuredHTTP10s timeout; actual local authority/control300ms bounds and all production source stayed unchanged.

## Accepted useful arm — correct natural-input cancellation

Fresh Mic313ON at16:25:46.380988; one useful `/initiative`200 at16:25:47.232555, generation3armed. A real2.0s PCM utterance was delivered at16:25:49.520252; the exact Agent executes `initiative.cancel('speech')` **before** this fixed-duration log. Thus cancellation occurred by **2.287697s** after acceptance (still<3s even allowing300ms control-response slack), observed as generation4cancelled by16:25:49.980838. No control POST followed the arm. Boot/mic313/policy142/listening binding unchanged, voice/expression errors0. This is a PCM-utterance event; its contents/speaker/STT semantics were not inspected or invented.

Model/frame0 proof is **not inferred solely from frameNULL**: all7actualproofsamples retained source2/nonretired/advancingPCM; the80s observer retained a single arecord280193 with no capture replacement. Frozen `_capture_visual` must retire/reap that source before any camera/model child and create a new generation afterward when binding stays current. Combined with pre3s cancellation receipts, the initiative camera/model path was not entered. [Original useful proof](../../S7-evidence/R33/proof.json), [same-event records](../../S7-evidence/R33/cancellation-records.json), [analysis](../../S7-evidence/R33/cancellation-analysis.json), [process metadata](../../S7-evidence/R33/proof-processes.json).

Observed APLAY280230/280235/280239 and later playback are ordinary production, not an initiative question. Their content/quality is not a new voice acceptance. No seed/manualspeech/fakeSTT/prewritten question/mic muting was used.

## Last conditional fresh arm — not sent

ROOT explicitly allowed **one last fresh arm only after input resolved and a real quiet receipt**; no source/purpose/model change, no microphone muting, and no automatic retry. The bounded eligibility check at16:29:30.886–16:30:05.490 gathered76metadata samples. Only2isolated samples were eligible; no3s interval with advancing freshPCM and sufficient new samples met all criteria. Phases:35speaking/34listening/7processing;33assembler-nonempty,36output-suppressed,1pending-event samples; same source2. Worker idle71/thinking4/speaking1.

**Last arm NOT SENT, no controls/frames/models in this opportunity check.** No extra window was run. Root/Tech directed terminal safe partial retention rather than rollback solely for correct foreground-input priority. [Opportunity result](../../S7-evidence/R33/last-arm-opportunity.json), [conditional caller report](../../S7-evidence/R33/last-proof.json), [finite passive process observer](../../S7-evidence/R33/last-proof-processes.json).

## Installed operation and final handoff

The feature stays opt-in and once-per-arm. It is not armed at startup and does not re-arm after speech/STOP/cancellation/completion. Existing normal capture/voice continues. Installed operator command on Robot from `/home/pollen/reachy-companion` with the existing config selected:

```
PYTHONPATH=/home/pollen/reachy-companion/src /usr/bin/python3 -B -m reachy_companion.initiative arm
PYTHONPATH=/home/pollen/reachy-companion/src /usr/bin/python3 -B -m reachy_companion.initiative off
```

These are opt-in/cancel commands, not permission to run more tests now. A fresh arm needs current local authority and actual listening without queued output; new PCM speech may consume/cancel it before the opportunity. Existing listening STOP is `scripts/companion voice microphone-off`; fresh microphone-on does not arm initiative. Old epochs are receipts, never replay payloads.

**Final actual16:31:52.690168:** samebootc777…/Agent279838/mic313/listeningcaptureON/source2/PCM11716608B/gaps0/overflow0/retiredfalse; ownersnull/quietprivacyfalse/motor142OFF/volume100/errorsabsent/Hubfree/actionfalse/stockknownunowned/workeridle. Initiativegeneration4/cancelled/frameNULL, no pending job. Onearecord280193; factory150625 active/NRestarts0 unchanged. Frozen3sourcepins/player1e25036f…/capture5fe…/spoken2d7…/Robotconfiga617… verified, hardware100%/0dB/canonicalAlice config retained. Existing mediaavailabletrue/releasedfalse/no_mediafalse and cameraIPC socket present; no new image/frame capture for finalcheck. [Final state](../../S7-evidence/R33/final-after.json), [pins/media/gain](../../S7-evidence/R33/final-robot.json).

Ordinaryfalse/ACKfalse/+2dB/9BWhisperPiper/PCworker unchanged. R33 controlled Agent restart1, miccontrols4 (OFF310/ON311/OFF312/ON313), motorcontrols0, other service/model/worker restarts0; source/frame/model/purpose variants0, native initiative image/model requests0, initiative question/playback0, raw media/transcript/privateconfig/token exports0. Candidate kept; rollback not used. Exact protected rollback preimages and original initiative absence remain available if a later authorized rollback is needed; never restore old grants/ON state.

**Accepted partial verdict:** local admission and safe pending/natural-input cancellation demonstrated, useful opt-in code installed. **Question delivery, image-to-spoken-question mechanical chain and visual grounding/accuracy UNTESTED** (no actual frame/model), full companion/permanent initiative/30min dialogue notaccepted. No artificial PASS from fixtures, text alone or unrelated APLAY. One remaining product blocker is absence of a qualifying quiet opportunity under ongoing normal input; no source/threshold/model change or further arm is authorized by this terminal. All finite observers ended, no owned camera/inference/speaker job pending; keep normal voice/cameraON/motorOFF.

**Hardware explicitly released to TechLead:** 2026-10-17T16:33:35.256462+03:00. Scope elapsed 868s; no extension or further work.
