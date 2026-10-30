# S7 — direct human R33 frame/question test

17 October2026, 16:39:20–16:40:00 MSK. User explicitly requested a new test and selected **«Да, тест кадра и вопроса R33»** after clarification. This was a direct new request, distinct from the earlier late async QA consent. R34 installation/motion test was deferred before all mutations; its approved frozen source remains uninstalled. [Course change](../../S7-evidence/R34/user-course-change.json).

**One attempt was admitted, then normal incoming PCM cancelled it before frame capture. No question was produced.** Local image-to-spoken-question capability and semantic grounding remain UNTESTED. No image left the LAN; this attempt did not enter the initiative image/model path at all.

Exact installed Agent7bd09093…/initiative0823f632…/snapshot04e63d85… pins verified and configured model endpoint verified private LAN. Existing bootc777…/mic313/motor142OFF/ownersnull/quietprivacyfalse stayed unchanged. No source/config changes, restarts, microphone controls, motor controls, seed, fake STT, prompt variants or retries.

The observer waited for actual listening with an empty assembler and no queued output. At16:39:55.486715, one local CLI arm received HTTP200/generation5. At16:40:00.505721 the Agent logged delivery of a **4.9s PCM utterance**; installed source cancels initiative before that log. No later control POST occurred. Generation6/cancelled was observed at16:40:00.745938. The utterance's content, speaker and whether the VAD classified it correctly were not inspected and are UNKNOWN. This does not establish that the human spoke.

All ten active observations retained **source2/nonretired/arecord280193**, and final PCM still had source2/nonretired. The exact initiative source must retire/reap PCM before camera/model and replace its generation on return. Combined with cancellation and no capture transition, this establishes the image path was not entered; frameNULL alone was not used as proof. Native initiative frame/model/question/playback count0. Ordinary production playback continued independently.

[Attempt and metadata](../../S7-evidence/R33-user-test/test.json), [same-event fixed journal receipts](../../S7-evidence/R33-user-test/cancellation-records.json), [terminal result](../../S7-evidence/R33-user-test/result.json).

**Final16:40:09.439792:** Agent same boot/mic313, ordinary speaking/captureON/listeningtrue, source2/PCM27613184B/gaps0/overflow0/retiredfalse; motor142OFF/ownersnull/privacyquietfalse/current voice+expression errors absent, Hubfree/actionfalse/stockknownunowned/workeridle. Initiative6/cancelled/no pending. Camera publisher/source/config remained untouched; no extra camera read was used for terminal verification. Healthy voice/camera/+2dB retained. All finite observers ended; sole hardware ownership released to TechLead at 2026-10-17T13:40:45.573419+00:00. No automatic rearm or R34 motor activation follows this test.

Human follow-up: **«Я молчал»**. The 4.9s value describes the captured PCM segment, not proof that the user spoke. Background/robot echo/VAD misclassification are possible explanations, none established by these metadata. No repeat or audio recording followed.
