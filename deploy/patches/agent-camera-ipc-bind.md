# Fix the proven Agent camera IPC namespace mismatch

A real human visual request passed exact STT, own-echo and action checks, then
failed at capture_sample/ValueError after camera.open returned. Read-only
inspection established the concrete mismatch: the running Agent has
PrivateTmp=yes and no bind paths; the factory and host see the same listening
Unix camera socket, while the Agent's /proc/PID/root/tmp view has no such socket.
Its spoken child inherits that mount namespace. A healthy publisher and socket
on the host cannot make the SDK unixfdsrc path visible inside private /tmp.

Installed SDK sources were checked against exact public 1.11.0 sources. There is
no background frame consumer or latest-frame cache: open starts a bus thread
and synchronously consumes its warm-up sample; read also pulls from appsink.
Changing read APIs or extending waits would not make the missing socket visible.
The fix changes only service mount visibility. No SDK/camera/helper/intent/STT,
timeout, model or ownership changes are part of this checkpoint.

`service_unit(config,'robot','agent')` now adds exactly:

```ini
BindReadOnlyPaths=/tmp/reachymini_camera_socket
```

PrivateTmp=yes and every other original unit byte are preserved. Hub, voice and
worker units receive no bind. The source is mandatory (no optional '-' prefix),
with no wildcard, directory bind, extra writable path or environment setting.
The standalone compatibility drop-in for the current installed Agent is exactly:

```ini
[Service]
BindReadOnlyPaths=/tmp/reachymini_camera_socket
```

Public file `deploy/systemd/reachy-voice-agent.service.d/30-camera-ipc.conf`:
SHA256 `4735915767426d67e8ffe66e2c85d0acd4931ba3a10e123d1513fd4eefb1780e`.
Generator `src/reachy_companion/deployment.py`:
SHA256 `40b2fac9510e55d8d68bac6e0a38878466154253fc6a0692165cd2ff7c2bafb3`.
The full generated unit depends on existing private config; do not replace the
installed unit with an example, regenerate the whole production installation,
or publish private paths/settings to deliver this two-line change. The official
[systemd execution documentation](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml)
describes mount namespace and bind-path settings; target systemd verification
and the actual post-restart inode comparison remain required.

## One finite sole-runner installation

After coordinator source review, the sole hardware runner applies only the
reviewed drop-in in a fresh idle window:

1. Require Robot known OFF/unowned/free, no capture/listening/camera/aplay or
   controller, volume API/saved/ALSA 100%, and no active PC stream/model task.
   Retain fresh Agent/factory PID/start identities and private unit/drop-in,
   config/profile/persisted mic/policy/volume identities. Verify PrivateTmp=yes,
   current bind arrays empty, current factory publisher declared available and
   its host socket is a Unix socket with the same dev/inode visible in factory's
   root. Reject symlinks, missing/replaced socket or changed publisher identity.
   Preserve the pre-install namespace mismatch receipt. No camera is opened.
2. Stage the exact two-line file. Require the destination
   `/etc/systemd/system/reachy-voice-agent.service.d/30-camera-ipc.conf` absent;
   if anything already exists there, stop and review its identity rather than
   overwrite unknown configuration. Retain all existing unit/drop-in files.
   Atomically install this file only, root-owned mode 0644, rejecting symlinked
   parent/destination paths. Run the target's systemd-analyze verify on the
   resulting unit and inspect its merged settings before activation. Keep the
   exact publisher/socket identity stable through this operation.
3. Run systemctl daemon-reload, then ONE controlled restart of
   reachy-voice-agent.service. No factory/worker/Hub/model restart, media acquire,
   SDK import change, mount namespace entry or package update. A mandatory source
   that disappears is a failed installation, not permission to widen /tmp.
4. Check the exact drop-in hash and unchanged main unit/config/profile/persisted
   state. Keep Agent source
   `289469a5de57f01295e6c8ddde3e78ba2804fe2f5e6c603a4789e3d70e6ebeb9`,
   spoken helper
   `486cfb8f23c9d9d5797910eab6ebf3143e64f1cfe4a686b4f50fe38db975a025`,
   and snapshot helper
   `d43a70cc1e3b3846cb163f8b772c9af2b13a08aefac2c4279f6197b68b974c13`.
   Verify new boot/readiness, authenticated capability/status and no-auth denial,
   strict operator shape, initial vision_route null, OFF/unowned/100%/factory
   free and no camera/aplay. Require merged PrivateTmp=yes and exactly the one
   read-only socket bind; main /tmp remains private. Compare Unix socket type,
   dev and inode across host, current factory root and fresh Agent root: all
   three must now match. Check the target mount read-only flag and revalidate
   publisher/Agent start identities. Namespace visibility is a readiness gate,
   not proof of a frame, inference or human scene correctness.
5. If any installation check fails, remain OFF and retain evidence. In a fresh
   idle window remove only this exact owned drop-in, daemon-reload and restore
   the previous Agent service state with a separately recorded rollback restart.
   Do not replace a newer unit/drop-in/operator or erase unrelated files. Report
   the failed attempt and any rollback restart explicitly, not as one success.

The runner/coordinator then owns ONE bounded real human query in the existing
voice/watch path. Verify exact visual STT and routing, a fresh frame/local model
FINAL, actual spoken scene description with human correctness confirmation,
then normal owned cleanup OFF/unowned/100%/factory free/no camera/aplay. Preserve
existing TTL≤2-second image admission, parent lifetime, STOP/privacy/owner epochs
and no retry. Read restricted routing/phase evidence before mic/policy cleanup.
No inference or camera success is claimed from source tests or mount readiness.

## Publisher replacement and failure behavior

An individual socket bind retains that inode. If the factory recreates its
socket, the old Agent bind does not retarget to the new inode. Before this finite
camera acceptance, require all three socket identities to match the current
publisher. On producer restart/replacement or mismatch, keep camera work closed,
retire the active owned turn normally and verify idle/OFF before a separately
controlled Agent restart refreshes the same exact bind. Recheck namespace/inodes
and readiness afterward. Do not use a broader /tmp bind, optional-source bypass,
auto media acquire (it starts audio too), cached/re-aged frame or changed TTL to
make a stale path appear ready. Continuous producer-restart recovery remains a
separate unaccepted product criterion; this checkpoint adds no restart monitor.

Local checks: 58 focused tests PASS across generated unit/drop-in constraints,
existing capture diagnostics, explicit vision, spoken route and exact Agent
observer. The generator is compared byte-for-byte with the previous version:
only the Robot Agent socket line changes; other units remain identical. Tests
also enforce no optional/wildcard/writable/broad bind and unchanged sandbox/root
validation. These are source checks on macOS; the runner must verify the actual
Linux unit/mount and real human image/voice result.
