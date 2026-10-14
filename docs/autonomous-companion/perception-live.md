# Camera-only приём и PC pixel measurements

2026-10-10. `deploy/autonomous/camera_probe.py` — opt-in конечный reader одной camera frame из существующего daemon IPC. Он использует installed SDK1.11.0 `GStreamerCamera` напрямую, не создаёт `ReachyMini`, MediaManager, GStreamerAudio или motor client. Установленный MediaManager LOCAL инициализирует camera и audio вместе; WEBRTC тоже обслуживает обе modality. Поэтому whole-media backend не использовался при operator mute.

Probe требует actual microphone=false/capture=false до старта, затем проверяет те же поля после закрытия reader. Camera child process имеет6s warmup bound/8s parent result timeout; terminate/kill/join при зависании. Native camera settings/resolution, daemon/services, factory audio и motors не изменяются. IPC appsink single-buffer/drop используется existing SDK. Frame artifact содержит bounded stride4 sample (BGR→RGB); это transport preprocessing, не inference на robot. Native1280×720 sample320×180 имеет explicit dimensions/recipe и SHA256 исходного BGR frame и PPM transport. Каждый sample имеет UUID frame/lineage, robot kernel boot ID и SDK version.

Raw sample создаётся exclusive0600, используется только локальным camera→PC processing. Finite camera supervisor удаляет raw файл в течение25s после capture и при SSH termination signals; без отдельного бесконечного GC daemon. PC probe проверяет frame digest и bounds, затем удаляет raw до записи successful receipt. Local orchestration также удаляет Mac sample в finally. Producer/metrics JSON содержат metadata, не image bytes, transcripts или credentials; export disabled. При capture error raw удаляется, PC processing не запускается.

## Реальные результаты

Две первоначальные probes с single immediate `read()` получили no frame за2.631/2.587s; child reaped, mute сохранён, raw removed. Это acquisition failures, не schema success. После bounded warmup polling actual capture прошёл за2.583s: source720×1280×3, transport180×320×3, audio module не инициализировался, before/after mic=false/capture=false/phasepaused. Camera supervisor exit0, child/local SSH reaped.

Sample обычным SSH/scp через hub передан на PC. `autonomous/perception.py` — bounded CPU implementation без ML: P6 RGB parser≤1MiB/640×480, SHA match, actual byte/dimension checks, mean RGB, weighted luminance/std, dark/bright fractions. На реальном PC processing0.016s; mean luminance15.658/255,std0.959,dark fraction0.739306,bright0.0. Это измерения pixels конкретного sample, не вывод «в комнате темно», presence/person/object labels или доказательство live camera freshness. Camera lens/producer состояние из этих чисел не определяется.

Camera SDK frame API не вернул verified source capture time/clock mapping. Записан **received_at**, source_capture_age_msnull, source_capture_time_verifiedfalse. Перенос между узлами занял секунды; timestamps не используются как доказательство clock synchronization. `shadow_event` поэтому показывает camera.pixel_quality с availabilityunknown, summaryempty и agemsnull. Неизвестная свежесть не превращается в ready evidence только потому, что PC закончил обработку недавно. Тест проверяет это через настоящий State snapshot.

Semantic visual LLM admission остаётся закрытым. [LM Studio tokenization](https://lmstudio.ai/docs/python/tokenization) документирует string tokenization; эта проверка сама по себе не считает image embeddings/crops. Нужно подтвердить actual visual tokenizer/admission budget и provenance/timestamp pipeline до main vision invocation. Main9B, loaded instance и32K context здесь не менялись и inference на ней не выполнялся.

90/90 regression tests прошли: pixel channel order/measurements, digest и malformed/oversized frame rejection, unknown capture time→unknown sensor. Это не physical stop SLA, camera quality/latency P95 или semantic perception acceptance. Следующий шаг — producer capture timestamps/clock mapping и asynchronous latest-only video stream→PC cache; inference остаётся на PC, hardware actors проходят отдельный ownership/watchdog/PCM gate.

## Async adapter continuation, 15 October

Existing camera-only `video_server.py`, `ContextProvider`, `LatestVideo`, pixel
measurements and State are reused. No camera/audio/motor/model service is started
by this source change, and no VLM request/token-budget gate is opened.

The PC now has one actual pixel worker plus at most one replaceable pending RAM
frame. Fetch remains independent of CPU processing. A newer admitted frame fences
the older result; pending middle frames coalesce. Invalidation, timeout or close
never frees an executing function's slot. Pending bytes are dropped immediately;
the running function retains its owned buffer until its REAL return. Close reports
`execution_busy` / `running_buffer_owned_until_return`, including blocked work. This
is bounded queue occupancy (two admitted frame buffers, each at most 1MiB plus
bounded parsing copies), not a hard erasure claim for an unreturned Python/native
function. No raw file, persistent image cache or unbounded processing queue is
created. `context.video_processing_ttl_s` is configurable in 0.1–2s, default 2s;
a late result never publishes. Terminating a stalled process and verifying reaping
is a separate runner lifecycle action, not an invented cancellation completion.

Protocol v2 adds an admission nonce to the existing authenticated private video
policy/packet. Scope/epoch change, observed privacy true→false (even same scope),
owner expiry and close rotate the PC generation/nonce and clear pending/cache
content. The producer echoes the nonce, resets its reader on generation change,
and rechecks the read-BEGIN generation before publishing. PC tickets are captured
before policy/read I/O and checked again at dequeue and result publication. Old
packets/replies cannot acquire a new nonce merely because owner scope is equal.
Legacy finite producer clients may still obtain their diagnostic frames; the new
PC adapter refuses non-v2/unbound packets. Upgrade the isolated producer and PC
adapter together; no silent legacy fallback.

Producer/PC sequence high-water marks survive content clear and privacy. Retired
producer/owner fences stop at a bounded capacity and fail closed instead of
evicting a tombstone and admitting an old boot (ABA). A producer restart drops old
cache content at ingress, not after slow processing finishes. Metadata validation
retains only selected IDs, scope/nonce, digest and bounded clock observations;
arbitrary source-header content is discarded. Camera reader UUID can change,
but a single producer's capture lineage still remains correlated, not independent
new episodes.

### Capture time remains unknown

[GStreamer buffer PTS](https://gstreamer.freedesktop.org/documentation/gstreamer/gstbuffer.html)
indicates presentation timing and can be absent/nonmonotonic. The
[clock/running-time model](https://gstreamer.freedesktop.org/documentation/application-development/advanced/clocks.html)
does not by itself attest physical sensor exposure time across a unixfd consumer
pipeline or synchronize robot and PC clocks. This adapter preserves PTS, running
time and consumer clock/base observations as diagnostics only. A future/missing
presentation mapping is not converted to zero capture age.

The producer stamps local buffer DEQUEUE (receipt, not exposure) with monotonic
time and adds measured RAM residence to a conservative age LOWER bound when
serving. Cached raw is discarded after 2s or privacy/policy withdrawal. The PC
adds elapsed time AFTER response completion, including processing/queue residence.
Request BEGIN is a freshness/deadline control point, not a valid age lower bound
for a frame that could be captured later during that request. Network/sensor
latency remains unbounded above. `source_capture_time_verified=false`, upper=null,
State unknown/stale and empty summary remain explicit; unknown observations are
not passed as main-model evidence. Fresh PC extraction cannot make an image fresh.
No raw visual input is admitted to an LLM until actual image-token admission and
capture provenance have independently passed.

### One actual camera check, sole runner

After independent source review, the sole runner may use a NEW isolated finite
camera-only sidecar and the actual existing factory video IPC. Require the current
operator mic=false/capture=false and explicit camera policy, preserve current
mute/epochs/config/volume, and record source/SDK hashes. Do not construct the SDK
`ReachyMini`, MediaManager, GStreamerAudio or a motor client. No service replacement
or direct device capture is part of this check. Camera-only imports reject an
unexpected SDK audio module; sampling remains bounded stride-four BGR→RGB, not
robot/Hub ML inference.

Run the existing `video_server.py` with its configurable production root, private
policy/token/output paths, port and finite duration (5–60s). Expose it only by the
reviewed private loopback SSH path. Then on PC:

```sh
python deploy/autonomous/video_adapter_probe.py \
  --video-url http://127.0.0.1:CONFIGURED_FORWARDED_PORT \
  --token-env REACHY_VIDEO_TOKEN --operator-epoch CURRENT_EPOCH \
  --duration 6 --output /absolute/private/FRESH-camera-adapter-receipt.json
```

The probe reserves a new output, sends only its isolated sidecar policy, receives
and processes one matching v2 frame in RAM, and records metadata/pixel aggregates
plus worker completion. It issues no Agent/audio/motor/model command. Cleanup
requests privacy only for its exact sidecar scope/nonce/sequence; changed/retired
ownership must reject that request, and an unknown close is reported. Never
force-stop/restore a newer owner or overwrite a current config. Remove only the
owned isolated trial artifacts after checking current process/launch ownership.
The result is an adapter observation, NOT capture-freshness/semantic/hardware
acceptance; `hardware_camera_acceptance=false` stays explicit.

Local tests include a genuinely blocked worker with replacement/coalescing,
actual slot retention after close, privacy ABA/epoch/expiry delayed-result
rejection, processing-age TTL, sequence fences across clear/restart/exhaustion,
producer read-generation checks, truthful age lower/unknown upper and State/main
model exclusion. No new actual camera session has been run by the writer.
