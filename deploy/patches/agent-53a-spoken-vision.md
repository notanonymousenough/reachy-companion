# Spoken snapshot overlay on the accepted vision checkpoint

This candidate adds an exact spoken request to the existing owned conversation.
It is not device acceptance. The preceding explicit `--vision` checkpoint has
real scene correctness, spoken output, stock movement and STOP confirmation;
this new STT route still requires the same real checks after deployment.

The exact installed Agent preimage SHA256 is
`53a43647c4744dde3c7b112d12212477943ce22f9f33b90ffbeeb916d28f23c3`.
Apply `reachy-agent-53a-spoken-vision.patch` with zero fuzz only to that source.
Expected Agent output SHA256 is
`9a4269f757bdc90d5da33cd9ccfa1d302c53a21fae4452d9d6bcdc4a5f578840`.

Reviewed file SHA256 pins:

- `deploy/patches/reachy-agent-53a-spoken-vision.patch`: `7502410feaf3f0411bfc660916c4ab5edf70eee159801369af45a666c932bec8`.
- `src/reachy_companion/spoken_vision.py`: `7b6589136989652079cdcbb55e774272f59422a05bd3442eca505ce0f8259ded`.
- `deploy/autonomous/demo_vision.py`: `1bd06dec8f941a78f0519e090e3a54cbc5816f5485fbb83ddd348e1830d0ef3f`.

The patch changes only `Agent.run`. It preserves the installed bound `/say`,
`voice`, authenticated capability, microphone/policy controls and STOP code.
Do not apply the old latency or original 0a7 vision patch over this preimage.
Do not replace it with the newer repository HEAD Agent.

Only the sole runner installs files, in a fresh known OFF/unowned/factory-free
window with no camera/audio/controller session and volume 100%:

1. Retain exact private backups of the installed Agent and any existing helper
   files. Verify the Agent preimage; reject drift. Preserve config, profile,
   credentials, persisted microphone/policy/volume states, service unit and
   ownership/mode. Prepare and hash-check the patched Agent locally.
2. Atomically install three reviewed files in the existing Robot package:
   the patched `src/reachy_companion/agent.py`,
   `src/reachy_companion/spoken_vision.py`, and a byte-for-byte copy of
   `deploy/autonomous/demo_vision.py` named
   `src/reachy_companion/snapshot_vision.py`. The last name is a deployment
   destination, not another maintained camera implementation. Existing
   `/venvs/mini_daemon/bin/python`, SDK 1.11.0 and numpy are reused.
3. Restart only `reachy-voice-agent.service` once. Verify exact installed hashes,
   service readiness/new boot, authenticated capability and unauthenticated
   rejection, microphone/policy still OFF and unowned, capture/listening OFF,
   persisted states/config/profile/unit unchanged, volume API/saved/ALSA 100%,
   factory free/known and no aplay/camera child. No worker/router/Hub restart,
   model change or dependency installation is needed. The accepted Hub client
   stays in place. On failure retain OFF/typed UNKNOWN and exact evidence;
   rollback restores only these file preimages in another verified idle window,
   preserving a newer operator and current volume.

Start the existing finite normal voice demo, using its existing private config
and pinned known-hosts file if needed:

```sh
./scripts/companion-demo --turns 3 --seconds 180
```

In that active owned conversation say **«Что перед тобой?»** or **«Что ты видишь?»**.
An optional leading Алиса/Ричи/Риччи/Reachy and пожалуйста is allowed. There is no
new wake listener or passive camera loop. Quotes, longer requests and appended
instructions do not match. An occurrence of the exact question in the Agent's
last spoken reply suppresses the camera route conservatively until a different
reply replaces it. Existing AEC and echo-tail handling remain in use.

Only a fresh normal captured STT result with first decision `answer` can dispatch.
Barge-in/pending PCM continues through the original interrupted-text/replay/STOP
branch and cannot launch the camera. STOP/pause from the first classification
turns the microphone OFF without speech. Reset uses the existing reset endpoint
and reply, never the camera. Empty transcription does not enter `/text`.

Ordinary fresh turns now use the existing authenticated `/transcribe`, then
`/stream/text` (or nonstream `/text`) with the same session and no interruption
flag. The exact deployed worker source reviewed for this seam is SHA256
`92cf69096fd6f08551a13a9c44d85fbbfc0470ca2f17315616691044018ab865`.
These paths retain the existing prepare/completed session history. They add a
classification pass; when a model classifier is configured its cost and
possible decision variation remain. Do not claim unchanged latency or inference
count. The first STOP/pause/reset result takes priority over vision dispatch.

The parent keeps the existing audio lock and listening permission; capture has
already closed before the camera child starts. It never creates another audio
or motor owner. The binding is captured **before** the microphone phrase, then
must still match boot, microphone/policy epochs and both nonempty owners after
STT, before capture, immediately before pixel admission, after inference and
before existing `/say`. Microphone permission/listening must be ON, capture OFF,
phase processing, motor permitted, quiet/privacy OFF, microphone state known.
Authenticated loopback operator reads expire after 300 ms. No reown/reset/ON
request is issued to make an old frame eligible.

The camera/native code is shared with explicit `--vision`: its original
OFF/unowned/watch authority callback stays unchanged, while this child supplies
the distinct ON/same-owner check. Same 640×360 frame, camera-close-before-inference,
2-second dequeue admission, exact existing native instance, private PC endpoint,
2048 output tokens, message-only FINAL and no reasoning/tool speech or raw files.
Reasoning is disabled only if actually supported; no token truncation or guessed
flags. No transcript, caption, raw image or token is logged/persisted by the new
adapter; visual turns also skip the existing optional transcript/reply logger. Credentials are sent only to the child over stdin, not argv.

The child is bounded to 50 seconds, tied to its parent lifetime, killed/reaped on
timeout and never automatically retried. Native response timeout remains 40
seconds. Speech expires at the earlier of frame dequeue +60 seconds and the
50-second attempt deadline. Existing policy/epoch cancellation and stock
expression binding remain active during playback. Existing barge-in can STOP
speech. Watch cleanup, web microphone OFF and Ctrl-C revoke admission; a late
FINAL is discarded without spontaneous resume. A closed HTTP connection does
not prove remote GPU inference was cancelled. Exposure freshness and physical
end-to-end latency are unverified by software timestamps.

The visual answer uses `/say`, so it does **not** append the question/answer to
worker history. Ordinary preceding context remains, but visual follow-up memory
is not implemented. The explicit `--vision` command remains available with its
original semantics and accepted Hub client; it does not use this STT dispatcher.

Actual acceptance: ordinary context question/answer, spoken camera request with
human correctness confirmation (no ground truth in model input), a following
ordinary context turn proving the prior session survives; separately repeat the
spoken camera request and STOP during owned aplay with paired stock positions,
no resume, final known OFF/factory empty/no aplay and volume 100%. Report actual
STT, inference and playback evidence without treating a software RPC success as
physical acoustic consumption or a latency target PASS.
