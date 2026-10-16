# Finite audio-only human repeat

Source proposal for one human turn, not hardware acceptance. No Robot or Hub
source installation. Sole runner owns all device actions; antenna incident hold
remains active. No expressive greeting, wake/reset, vision or motion request is
authorized by this method.

Build using `deploy/autonomous/prepare_audio_only_demo.py OUTPUT`. Input client
SHA256 is `adc324fc93ec4dfc1d88249deaa4a7925e8d44e92dc15946877cef574fac1c4f`;
output SHA256 is `4722db25ffc1d0b83a866d6a408ec26a673782d501339bdb05ddad15b8102655`.
The builder refuses a different preimage and refuses overwriting output.

The ephemeral client grants a **disabled** policy claim (False, own epoch/owner),
then the microphone claim. Policy remains False before mic grant and throughout
polling; same owner/epochs and quiet/privacy checks remain required. This is the
paired ownership contract, not an unowned policy contract. Both owned claims are
cleaned up by original CAS logic, including a lost grant response. A changed
operator is preserved. STOP and independent watchdog retain priority.

Use the unchanged `demo_watch.py` SHA256
`4cd31192df4b1b360d55f63348a23df9c269a8b5f097e30f190a02177ecfae03` with
arm seconds=180. Its deadline is arm+200; systemd RuntimeMaxSec=220. Launch exactly
one RAM-only copy of the candidate on Hub using existing Config/transport and
the watch's owner/operator binding: `demo(..., turns=1, seconds=180)`; no vision,
prime-paused, old native actor, timing controller or second cycle. Start the child
immediately after watch readiness, with a finite outer timeout <=190 seconds.
If transport/preflight consumes the independent budget, abort instead of rearm.

Before any grant, runner must verify actual installed Agent cf50 and expression
7a5 gates, no in-flight/queued custom motion, free known stock state, baseline
services, volume100, OFF, quiet/privacyFalse, and no other owner/actor. Confirm
all greeting/processing/speaking/reset/vision expression paths are gated by
motor_permitted False; never infer installed behavior from HEAD. This source
proposal cannot supply that device verification.

Client starts with a 180-second hard deadline, requires >=100 seconds remaining
before the disabled policy claim, and shortens the deadline to observed capture
+90 only if a full90 seconds still fits. Actual announcement requires owned mic,
capture_active and listening and the unchanged disabled policy claim. Startup
failure and late capture never announce LISTENING. A completed counter cannot
succeed before LISTENING. Relay `AUDIO_ONLY_LISTENING` immediately to the human;
the90 seconds starts at that observation, not from permission ON or an old status.
Finish earlier only after the requested turn completes or operator STOP/error.

Always call original watch finish with original plan/run hashes. Require final
OFF/captureFalse/listeningFalse, both claims retired, no own APLAY, stock tasks
empty and known, baseline config/services restored and volume100. Unknown cleanup
is a failure, never an excuse to grant again. Record actual causal turn/playback
and cleanup separately; source fixtures do not prove speech or physical halt.

Nine focused tests cover no motorTrue, both claim cleanup, changed policy,
capture-relative window, late capture, wrong preimage, invalid modes before I/O,
lost mic grant response and foreign owner preservation. No hardware ran in tests.
