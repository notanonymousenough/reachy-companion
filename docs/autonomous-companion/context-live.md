# Persistent memory и latest-only camera в canonical L0/L1

2026-10-10. Opt-in `context.enabled` подключает PC-owned SQLite memory и независимый video poller к настоящему `State`/`Scheduler`, а не только к диагностическим probes. Production entrypoints и службы пока не переключены. `context` выключен в example config; physical speech/motion остаются simulated.

## Поток данных и границы

Robot `deploy/autonomous/video_server.py` — конечный video-only producer (5–60s): установленный SDK camera IPC reader, один latest frame в RAM, localhost HTTP, отдельный token, максимум два клиента и socket timeout1s. Никаких raw-файлов, audio backend или motor client. Доступ требует local opt-in camera policy, actual mic=false/capture=false и refreshed remote scope `(hub_boot_id, compute_boot_id, operator_epoch)` с возрастающим seq/lease1.5s. Старые epochs/owners отвергаются; privacy-all и потеря lease убирают выдачу frame. Изменение scope между capture и publish не позволяет опубликовать старый frame.

PC `ContextProvider` каждые0.5s обновляет producer policy и принимает не более1MiB по отдельному authenticated SSH-loopback transport. Проверяет packet/header/PPM bounds, SHA256, scope, producer boot/sequence, отсутствие audio initialization. После pixel metrics raw bytes освобождаются; в RAM остаются только metadata и измерения одного sample. Это не semantic vision и не модель presence/person/object. Последовательность/gaps не заменяют freshness.

Producer сохраняет доступные Gst buffer PTS, segment running time, consumer clock/base time и presentation age. Эти поля **не доказывают момент физической экспозиции**, producer/consumer clock mapping или верхнюю границу sensor latency. [GStreamer synchronization](https://gstreamer.freedesktop.org/documentation/additional/design/synchronisation.html) описывает связь clock, running time и timestamps. Canonical sensor честно получает `age_ms=null`, `age_bounds_ms={lower: elapsed_since_PC_receipt, upper:null}`, stateunknown; после lower>2s — stale. Hub увеличивает bounds даже при отсутствии новых context RPC. RPC roundtrip добавляется только к известной upper bound. Никакой fresh label из возраста HTTP response. Source/lineage IDs и gaps доступны каждому L0 snapshot; слот camera резервируется в bounded sensors.

Hub обновляет context отдельным background Future, не занимая fast/main lane. Authenticated read-only `POST /context` принимает query≤1024 и owner epoch/boot/privacy. Старые completions не обновляют новый scope. Every L0 tick получает ≤8 memory aliases/type/summary и camera metadata; L1 получает typed `context-1` DATA envelope с полной обязательной репликой≤1024, ≤8 MemoryItems и ≤1 observation. Envelope≤40960 chars, затем exact tokenizer и прежний admission budget; это не обход token gates. Memory/observations входят в USER data, никогда не SYSTEM policy или authority. Privacy-all скрывает память, dialogue и camera IDs/summary, отзывает текущие proposals; камера закрывает собственный reader.

## Отзыв и privacy checkpoint

Privacy удаляет ранее принятые sensor summaries, provenance и context cache из reducer; выход из privacy требует нового admission. Проверка memory validity повторяется непосредственно перед commit, до speech proposal. Shutdown отправляет отдельный authenticated `POST /context/revoke`, независимо от занятого context slot. PC сохраняет fence по Hub boot/epoch; terminal revoke запрещает все следующие запросы этого Hub boot. Поздний snapshot проверяет fence до lease admission и после recall. Нет eviction fences: исчерпание bounded capacity закрывает provider.

Scheduler допускает context только через transport с revoke API. Shutdown сообщает реальную занятость context/revoke slots; отсутствие подтверждения не означает удалённый stop. Producer policy по-прежнему имеет собственную конечную lease, а доставка отзыва и фактическое закрытие камеры требуют отдельного аппаратного подтверждения. Новый Hub boot может получить новое разрешение после проверки владельца.

## Store, corrections, restart, forget

`MemoryStore` — trusted-owner API, без model tool/HTTP write endpoint. SQLite WAL/FULL, secure_delete, ограничение2048 pages, WAL checkpoint16 pages/size hint1MiB. Бounded store: ≤128 active IDs, ≤512 immutable versions/evidence, ≤4 namespaces, ≤8 recalled items, content≤256 и serialized item≤4096 bytes. Capacity/invalid input отвергаются без truncation/eviction. IDs, evidence SHA256, namespaces и supporting/counterevidence lineages проверяются; NaN/Infinity запрещены.

Owner commit имеет transactional CAS expected version, immutable previous versions, persistent store UUID/revision. Active fact/preference требует явного `confirmed=True`; model proposals не получают этого полномочия. Hypothesis требует expiry. Disputed/retracted/proposed/expired не возвращаются; hub дополнительно проверяет validity при каждом tick и acceptance без ожидания refresh. Recall — bounded lexical selection, не embeddings/automatic consolidation. Повторные evidence с одним root не становятся независимыми эпизодами. Automatic trait/personality/policy writes не реализованы и не разрешены.

Corrections/forget меняют relevant version digests: hub отзывает running/ready results и создаёт retry candidate для той же обязательной реплики; executing Future продолжает занимать lane до известного завершения. Gateway сверяет relevant memory descriptors до/после actual inference; unrelated store revision не отменяет работу. Это observed-version fencing, **не** distributed atomic prepared/apply bundle при произвольном partition. Physical adapter должен добавить собственный acceptance/ownership protocol до действий.

`forget_lineage` удаляет все зависимые IDs и их версии, supporting/counterevidence, checkpoint TRUNCATE; persistent tombstones не дают восстановить их после restart или повторного импорта. ≤256 revoked roots/≤1024 deleted IDs; при исчерпании capacity новые writes замораживаются, deletion продолжает работать без eviction tombstones. Это локальная store deletion; S3/export/backups/automatic profile synthesis отсутствуют. Следующий memory этап — независимые episode roots, controlled consolidation/contradictions и полный transaction protocol из проекта [memory-and-analysis.md](memory-and-analysis.md).

## Реальный конечный прогон

Camera на robot, PC CPU fast Qwen3.5-0.8B Q8 (8 threads/cache0), existing pinned main9B SDK instance и hub Scheduler. Main instance/context32K не перегружались, daemon/motor/audio/services не менялись. Fixtures — **синтетический namespacefixture**, не человеческие предпочтения. `memory_fixture.py` — owner CLI seed/correct/forget/restart-check; `hub_context_probe.py` — canonical acceptance. Private tokens/configs/raw logs вне git.

Первый45s run:15 actual fast requests/14 accepted,176 context updates,14 camera snapshots,0 tick busy gaps; main task failed из-за применения legacy1024 limit к serialized context. Это failure, не успешный L1. Исправлена отдельная bound typed envelope при сохранённом literal-utterance limit и exact token budget; regression test проверяет оба.

Второй31.848s run на периоде3s:11 actual fast requests,9 accepted choices,124 context updates,2 main tasks/ready/simulated commits,8 camera snapshots,0 busy gaps. Два stale fast completions и один context failure отвергнуты на сменах utterance/privacy epochs. Main сначала ответила «В синтетическом fixture любимый цвет — синий», после owner correctionv1 — «Зелёный». Reopen store после correction сохранил UUID/revision2/v1; forget дал revision3/empty и такой же reopen. Последующие unprivate snapshots оставались memoryempty.

| Метрика | Первый turn | После correction |
|---|---:|---:|
| Turn→main start | 5.006s | 2.358s |
| Actual main completion | 1.033s | 0.829s |
| Turn→simulated commit | 11.111s | 8.227s |

Camera lower bounds в snapshots87–716ms, upperunknown; наблюдаемые transport/acquisition gaps3–14. Privacy snapshots скрыли memory и camera; unprivacy получил новый sample. Это не1Hz/P95≤700ms, ≤5s first-audio или semantic camera acceptance; звука не воспроизводилось.

Remote cleanup receipts: robot102 frames/0 capture gaps/capture thread reaped/raw files0/audio or motor commands0; actual mic=false/capture=false/phasepaused. PC90s finite supervisor: fast/mainidle, quarantineempty, CPU processreaped. Local orchestration первоначально завершилась с exit1 из-за producer wait25s, меньшего оставшегося remote TTL; локальные SSH wrappers reaped. Independent remote receipts получены после TTL и подтвердили cleanup. Local wait исправлен45s; это не ретроактивный exit0 исходного macro run.

One-frame `camera_probe.py` отдельно исправлен: outer finally удаляет только свой raw artifact, включая ошибку after-status или output open; preexisting artifact не удаляется. Injected failures покрыты tests.

110 local regression tests и design validator проходят. Tests проверяют provenance/CAS/restart/forget, counterevidence deletion, finite JSON, expiry, relevant fences, typed main bounds, async canonical context, auth/privacy epochs, producer old owner/seq/lease и raw cleanup. Это protocol tests; real runs выше имеют отдельные измерения. Physical sole-writer fence, bounded stop/verified PCM и semantic image token admission остаются следующими воротами.

## Hub → partial GPU с camera и persistent correction

2026-10-10. Тот же pinned main32K и отдельный fast0.8B, actual hybrid8/26layers, threads8/cache0/full/object. Hub period1s; context refresh0.25s/video poll0.5s. За19.518s:20fresh fast requests,15accepted choices,4stale choices отвергнуты при сменах context/operator (последний request drained после final mute),74context updates,2context stale failures,2main/ready/simulated commits, **0busy tick gaps/failures/deadlines**.13snapshots содержали actual camera metadata.

| Метрика | Первый turn | После correction |
|---|---:|---:|
| Turn→main start | 1.634s | 1.442s |
| Main start→ready | 0.765s | 0.890s |
| Turn→simulated commit | 3.489s | 3.434s |

Ответы «Синий.» и «После коррекции в синтетическом fixture указан цвет зелёный.» соответствуют owner fixture transitions. Это новый synthetic dataset `fixture-color-gpu` в **той же** SQLite store UUID; прежний forgotten root не восстановлен. Seedrevision4/v0, correctionrevision5/v1, forgetrevision6/empty; каждый owner CLI reopen equality прошёл. Private/unprivate snapshots после forget не восстановили item;4private snapshots скрыли memory/camera. Camera lower bounds79–747ms, upperunknown; semantic scene inference отсутствует.

PC monitor293samples: minimumfree914MiB, reserve512, no abort; actual placement8/26layers. Main before/after instance/context/load configuration идентичны. PC70s finite supervisor: acceptedtrue, both lanesidle/quarantineempty, private fastreaped. Robot60s producer: 29frames/0capture gaps, camera threadreaped/raw files0/audio or motor commands0; supervisor exit0. Hub exit0 и local SSH processesreaped. Actual operator до/после micfalse/capturefalse/phasepaused; production services и motor/audio clients не изменены. Это ограниченный enriched shadow acceptance1Hz; latency до **simulated** commit не считается physical first-audio.

Исправлен camera owner timeout: PC poller не может бесконечно продлевать старые права hub. Только authenticated `/context` обновляет local monotonic owner lease (default1.5s, configurable1..2s); refresh должен быть≤TTL/2. По expiry PC очищает latest metadata, отправляет producer privacytrue и не публикует late frame. Финальный hub probe сначала drains старые jobs, затем явно отправляет новый private epoch и проверяет empty memory/disabled sensors. Expiry regression проверяет, что самостоятельный poll не возобновляет lease; реальный прогон выше проверил explicit final privacy. HTTP/poll/native scheduling не дают доказанной hard stop bound.

131regression tests и design validator проходят. Физические writer fence/PCM cursor/stop SLA, независимые episode roots и automatic consolidation остаются отдельными этапами; autotraits/policy writes выключены.

## Correlated camera lineage

Producer больше не выдаёт новый lineage root на каждый соседний frame. Один конечный producer run имеет один `capture_lineage_id`; frames сохраняют разные frame IDs, но разделяют этот root даже после reader reopen/privacy/scope transitions. Metadata явно содержит `lineage_scope=producer_capture_session`, `independent_episode_verified=false`. Restart producer создаёт новую capture session, но не доказывает новый независимый социальный эпизод/день/outcome. Trait/consolidation eligibility из количества кадров или producer restarts не вычисляется; automatic personality/policy writes остаются выключены.

15s actual camera-only run через hub, без inference/audio/motor:4different frame IDs/one root, каждый independent_episode_verifiedfalse; SHA256/scope/audio_initialisedfalse проверены на actual packet в RAM. Privacytrue отозвал `/latest` (503), supervisor exit0/local reaped. Новая lineage regression проверяет correlated IDs и неизменный root при privacy/new owner. Это metadata/provenance acceptance, не semantic scene claims.

## Canonical claim duplicate/direct-negation gate

Optional non-null `MemoryItem.claim` нормализуется NFC/outer whitespace; обязательные subject/predicate/scope после normalization не могут быть empty или выходить за schema bounds. Original owner object и immutable old versions не переписываются; normalized body снова проходит schema/item4096-byte budget. Identifier case не меняется, entity merge/synonyms/transcript interpretation не выполняются. Number1 и1.0 совпадают, booleantrue и number1 различаются.

В той же namespace для exact subject/predicate/scope/value и пересекающихся half-open valid intervals новый active ID с такой же polarity отвергается как duplicate; противоположная polarity — direct contradiction. Rejection происходит внутри той же `BEGIN IMMEDIATE` транзакции до version/revision writes. Supporting evidence следует объединять owner CAS на одном item; correction/retraction prior item остаётся явной owner operation. Разные values **не** считаются автоматически несовместимыми: predicate cardinality не задана. Разные scopes/intervals и explicit fiction разделены; proposed/disputed items не получают active recall. Это точная structured-claim проверка, не semantic contradiction detector или automatic consolidation. Existing duplicates не удаляются автоматически.

Finite `claim_probe.py` на actual Windows PC/Python3.12.9:7/7checks — duplicate/direct negation rejected, rejected transactions unchanged, correction survives reopen, forget removes item/versions and survives reopen, revoked root reimport rejected. Только новый synthetic fixture namespace/temporary DB; existing context store не используется. Probe fixtures удалены, models_called0/physical_commands0/traits_or_policy_written0.140local regression tests проверяют CAS, scopes/time boundaries, multivalued predicates, Unicode expansion/empty keys и finite typed values. Model/HTTP memory-write endpoint по-прежнему отсутствует; personality/policy auto-writes выключены.

## Cross-component audio memory fixture

`tests/test_audio_memory_integration.py` joins the actual AudioAdapter admission path, SQLite MemoryStore and State speech fence using explicitly synthetic STT/PCM. An unknown, unconfirmed audio turn supplies only digest/lineage provenance. A proposed note is absent from recall; active preference requires explicit trusted-owner confirmation. Owner CAS correction invalidates a ready answer before its delayed speech commit, and forget prevents replay of the same sensor lineage. No physical capture, model inference, automatic runtime memory write or speaker identity is claimed by this fixture.

```text
PYTHONPATH=src <validation-python> -m unittest discover -s tests -p test_audio_memory_integration.py
```

## Prepared finite voice-to-memory owner acceptance

`deploy/autonomous/voice_memory_acceptance.py` reuses the existing PC `MemoryStore` and canonical `State`; it adds no service, model tool or HTTP write endpoint. The input is a **finished owned voice session**, not an STT string or a speaker's request to remember. Run the reviewed [finite voice profile](realtime-audio.md) first at the same pin, with actual Agent cancellation, accepted network gate and complete device/Hub cleanup. Legacy `voice-working-1` receipts remain supported only by the original trusted-owner fixture actions. They cannot establish the strict live-chain/next-main gate below. Fresh runtime now emits `voice-working-2`; never add fields to old receipts or reuse readiness from an older run.

The actual audio admission exports only source/sequence, PCM SHA256, lineage, the canonical candidate ID/authority and the validated public Agent boot/microphone/policy binding. The runtime records a practice turn only after its canonical `State` accepts the utterance; muted/blocked input cannot become a working-memory receipt. It exports no transcript or microphone owner nonce. The PC acceptance checks exactly two matched unknown turns, increasing sequence/interaction epochs, capture admission age under2s, the final microphone epoch and policy binding, actual-Agent cancellation within500ms, matching session owners, both accepted receipts and drained cleanup. Hashes identify the runner's immutable input files; they are not cryptographic hardware attestations. A forged JSON file cannot independently prove real voice. Runner verification of the pinned processes and authentic finished files remains required.

Copy only the two finished private metadata receipts to a private PC directory through the existing runner transport. Use the existing PC Python/environment and staged source; no production memory database, config, gateway or model changes are required by this CLI. Heavy inference has already occurred on PC during the voice stage; the owner-memory stage performs no inference and makes no physical commands. Each command is a separate finite process (runner limit10s). POSIX artifacts are0600 and the fresh disposable directory0700; on Windows the runner must use its existing operator-only directory ACL. Keep reports **outside** the disposable directory so they survive cleanup.

First prepare one fresh directory and a unique `fixture-voice-*` namespace. The proposed fixed neutral marker “four” is supported by the first admitted unknown turn's digest/lineage. It remains hidden from recall. This is a disposable arithmetic test marker, not a fact about Alice, a human, an identity or a preference:

```text
PYTHONPATH=<stage>/src <existing-PC-python> <stage>/deploy/autonomous/voice_memory_acceptance.py prepare --allow-disposable-voice-fixture --directory <fresh-PC-fixture-dir> --output <fresh-prepare.json> --hub-receipt <finished-hub.json> --device-receipt <finished-device.json> --controller <voice-controller> --session-boot <voice-session-boot> --source-boot <voice-source-boot>
```

Require `accepted=true`, `proposal_version=0`, empty `versions`, `confirmed=false` and unknown speaker. Record the returned **store UUID**, not just version0. An existing directory/store, mismatched owner, malformed/old provenance, busy worker or failed voice receipt is rejected before creating a store. Output reservation occurs before memory writes. Failed preparation can retain partial owned artifacts; treat that directory as failed and inspect it through the runner, rather than adopting it as a successful fixture.

Confirmation and correction are separate trusted local operator actions with explicit `--operator-confirmation`. The audio/STT/model cannot supply that authority. The fixed neutral marker is the only writable content; no free-form content argument exists. Confirmv0→v1, then correctv1→v2 to neutral marker “six”; the correction adds its own operator evidence and counterevidence for the earlier fixture. All sensor evidence remains attributed to an unknown, unconfirmed speaker. No confirmed human fact or private memory is spoken.

```text
voice_memory_acceptance.py confirm --allow-disposable-voice-fixture --directory <fixture-dir> --output <fresh-confirm.json> --expected-store-id <prepared-store-UUID> --expected-version 0 --operator-confirmation
voice_memory_acceptance.py readback --allow-disposable-voice-fixture --directory <fixture-dir> --output <fresh-reopen-v1.json> --expected-store-id <same-UUID> --expected-version 1
voice_memory_acceptance.py correct --allow-disposable-voice-fixture --directory <fixture-dir> --output <fresh-correct.json> --expected-store-id <same-UUID> --expected-version 1 --operator-confirmation
voice_memory_acceptance.py readback --allow-disposable-voice-fixture --directory <fixture-dir> --output <fresh-reopen-v2.json> --expected-store-id <same-UUID> --expected-version 2
```

Use the same staged interpreter/PYTHONPATH prefix for each command. Missing operator confirmation or stale version must fail without promoting the item. Each readback reopens SQLite in a **new process**, checks the unchanged store UUID/revision/version/content whitelist, and admits the recall through canonical `State` to verify the exact versioned alias/type/summary projection. It prints metadata only. This is real PC SQLite restart/readback and State projection when run on PC, not a restart of the robot/model/service, spoken readback or a new LLM answer. Local tests separately hold a synthetic ready task over an actual owner correction and verify its late speech commit is discarded by the existing dependency fence.

Finally revoke both the sensor root and explicit operator root, then reopen empty recall before removing the owned disposable files:

```text
voice_memory_acceptance.py forget --allow-disposable-voice-fixture --directory <fixture-dir> --output <fresh-forget.json> --expected-store-id <same-UUID> --expected-version 2
voice_memory_acceptance.py readback --allow-disposable-voice-fixture --directory <fixture-dir> --output <fresh-empty-reopen.json> --expected-store-id <same-UUID> --expected-version -1
voice_memory_acceptance.py cleanup --exclusive-filesystem-cleanup --allow-disposable-voice-fixture --directory <fixture-dir> --output <fresh-cleanup.json> --expected-store-id <same-UUID> --expected-version -1
```

File cleanup uses anchored POSIX operations or the explicit local fixed NTFS Win32 handle backend described in [Windows fixture cleanup](windows-fixture-cleanup.md). Native Windows proof is still pending: do not mark combined PC acceptance complete from POSIX emulation or skipped Windows tests. Unsupported Windows paths/volumes/identities fail closed before the cleanup lock. `--exclusive-filesystem-cleanup` asserts that the runner has exclusive filesystem authority over the source fixture during SQLite use/close and over the private quarantine. A cooperative lock alone does not establish this: SQLite may remove journals when closing, and an uncooperative same-UID or privileged writer is outside the guarantee.

Cleanup pins directory/file identities before opening SQLite and revalidates after close. POSIX detaches the source directory before moving entries; Windows retains all pins, moves files first into quarantine, verifies every prior token and exact remaining source set between moves, then detaches the EMPTY original directory through its identity-checked handle. Both require complete moved-identity verification before deletion; Windows additionally acquires the full token/directory DELETE handle set before the first disposition. Detected source replacements preserve data and return failure; a failure after detachment reports `preserved_cleanup_directory`. Failure retains the cleanup lock for manual owner recovery. Reports explicitly include `cleanup_contract=exclusive_private_quarantine` and `adversarial_same_uid_race_safe=false`; these are bounded ownership checks, not a general hostile-filesystem guarantee.

Require empty active/versions/evidence, `forgotten_replay_rejected=true` for both roots and finally `owned_files_removed=true`. Tombstones protect reimport inside that store until its explicitly requested file removal; this is not deletion of production stores, copies/backups or a global revoked-root service. Recreated directories get a new UUID/namespace and reject old UUID commands. Cleanup never removes input receipts/reports or adopts an existing directory. Unknown files, symlinks or a live `operator.lock` reject admission; each owner command holds an exclusive actual process slot. A killed command can leave a stale lock: no automatic unlocking or cleanup while another owner may still run; the runner must verify the original process exited before recovery.

Windows noncleanup commands use `WindowsOperationLock`, separate from the explicitly authorized quarantine cleanup backend. It pins canonical local fixed NTFS ancestors and the fixture directory without share-delete, creates a new single-link non-reparse lock with native DELETE access and no sharing, and transfers that exact handle into a CRT descriptor with `open_osfhandle`. After confirmed SQLite close, release rechecks the original FileID/link count, sets `FileDispositionInfo` through that same still-open handle, closes the CRT descriptor once, then releases directory pins. There is no close/reopen or pathname unlink interval. DELETE access is required by the [Win32 disposition API](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle). No delete-on-close flag is set at acquisition: crash/unknown release must preserve a marker for explicit recovery. All finalizers attempt every owned close and preserve a primary exception, recording secondary failures as notes; failed SQLite close skips lock deletion. Failed disposition leaves the marker and admission closed. This does not authorize removal of a stale/foreign marker or repair an already failed fixture.

The causal regression models the former normal `forget` finally failure (unlink while CRT fd open), separately from injected initialization errors. Local descriptor/handle models are not native Windows sharing proof. Native tests in `test_windows_fixture_cleanup.py` additionally require actual cross-process exclusion, blocked directory/lock rename while held, known release followed by successful reacquisition, preserved later foreign marker, failed-disposition fd close, and the existing quarantine identity tests. Run them only in the independently verified operator-only test parent; no ACL mutation or automatic retry of preserved failed fixtures is part of this source change.

CLI `accepted` means this bounded owner-memory action passed. `live_voice_verified=false`, `speaker_identity_confirmed=false` and `input_assurance=trusted_runner_files_not_signed_hardware_attestation` are deliberately retained in all reports. Actual combined acceptance requires the runner's genuine finished voice receipts plus successful separate PC steps and owned cleanup. Local tests use explicitly synthetic voice receipts with real subprocess SQLite persistence and cannot establish that actual acceptance. Automatic memory consolidation, identity inference, traits/policy writes, spoken private recall and export remain outside this stage.


## Finite strict voice chain and next-main context gate

This source endpoint closes a specific missing link: the original `voice-working-1`
metadata did not correlate an admitted STT input to its particular completed main
attempt and consumed reply. The existing neutral fourteen-process CLI workflow
proves SQLite/owner-CAS/cleanup only. It cannot be promoted into live evidence.
No new service, memory-write API, inference executor or driver is added here.

`ModelBackend` emits `model-final-1` metadata only after a successful terminal
model generation. It hashes the logical input, utterance, exact memory projection
and returned output; the configured model ID is exported only as a digest,
not as a model-weight/instance attestation. Scheduler/State check those hashes against the canonical
Task before readiness; the task/attempt/input-ref, immutable authority and original
task/proposal times, store UUID and revision survive the speech commit into the owned speech receipt.
ReplayGateway supplies no such provenance. The realtime harness correlates by
identity, not by speech receipt position, and requires actual HttpSTT admission,
source capture TTL under2s, matching STT/utterance digest, actual main FINAL before
its original deadline, unchanged epochs, valid proposal/producer deadlines,
matching reply output hash and complete `device_consumed_pcm` cursor with known
stop. A simulated cursor, missing/partial/scripted/replay FINAL, stale authority,
reused attempt/stream or ambiguous join rejects the chain. Audit retention is
bounded to two turns and eight main receipts; overflow fails acceptance rather
than silently evicting required evidence. Actual futures remain occupied until
completion; metadata expiry never releases an inference slot.

These are **receipt consistency checks**, not cryptographic hardware/model
attestations. Every CLI report still says `live_voice_verified=false`, unknown
speaker, no model inference by the CLI and
`input_assurance=trusted_runner_files_not_signed_hardware_attestation`. The runtime
HTTP/provider tag cannot prove that a remotely configured endpoint is an actual
model or live capture source. Runner review of fresh pinned runtime/config,
immutable model instance/weights/tokenizer/template, occupied task slots, capture
owner, device output and the authentic finished receipt files remains mandatory.
Synthetic tests construct DTO shapes only and never establish actual acceptance.
Do not relabel a replay/scripted/synthetic receipt, manually add `model-final-1`,
or take `accepted=true` from a fixture action as the runner's live verdict.

One finite reviewable sequence, with no production memory or personal facts:

1. Run a freshly reviewed real two-turn finite voice session at this source pin,
   with context disabled, actual PC STT/main FINAL, consumed device playback,
   actual-Agent cancellation and complete drained cleanup. Existing
   `realtime_audio_session.py` exports `voice-working-2`; source/config transfers,
   microphone/capture and output require the separately approved runner window.
   Old sessions and the neutral synthetic input files are not eligible.
2. On the PC, use the existing CLI and a fresh exclusively owned disposable store.
   Add `--require-live-source` to the existing `prepare` command with the genuine
   finished Hub/device files and exact controller/session/source binding. This
   validates the new chain **before creating** the store and records its input
   hashes, both source lineages and final microphone epoch. Require
   `live_source_chain_validated=true`; the item is still proposed/hidden.
3. Obtain explicit trusted local user confirmation, then use existing `confirm`
   v0→v1 and optional separately confirmed `correct` v1→v2. Nothing said by Alice,
   unknown STT, a model or a receipt grants confirmation. Only the existing public
   neutral four/six fixture content is writable. Reopen with `readback` in a new
   process; compare UUID/revision/version, whitelist and State projection.
4. Prepare/review an isolated test gateway context config bound to exactly this
   fixture's `memory.sqlite` and namespace, with explicit `context.mode=memory_only`,
   no video, production/private memory or extra items. Do not change production configuration. Independently audit the
   real fast/main runtime and resource ownership again; a JSON audit flag or this
   endpoint is not that audit. Freeze the successful confirmed-version CLI
   `readback` report and its raw-file SHA256. Add
   `--memory-readback <frozen-readback.json> --memory-readback-sha256 <reviewed-SHA256>`
   to the existing voice-runtime invocation. Its opt-in guard rejects a changed,
   legacy or unconfirmed artifact, checks the exact whitelist descriptor and
   requires an explicit empty `sensors` list with no extra `observations` BEFORE
   every fast transport/model call, and checks the store/revision/full projection and absence of
   extra observations BEFORE every main call. Thus a wrong DB/namespace cannot
   first send private memory to a model and merely fail the final receipt check.
   An empty/not-ready context also rejects inference until the exact projection
   arrives; no fallback context or model call is substituted. These guards use
   existing gateway slots and add no memory/model API. The ordinary profile's
   camera path is unchanged. A regression uses actual State/FastView,
   AuditedGateway and RemoteGateway with a counting local ModelBackend stub:
   an extra camera sensor or observation causes zero transports/model calls;
   the clean whitelist view passes.
   `context.mode=memory_only` selects the existing ContextProvider's memory-only
   path before resources open: no LatestVideo cache, frame processor, poll thread
   or video fetch/admission is created; actual `sensors=[]` is returned. A non-null
   `video_url` (including an empty string or wrong type) conflicts and rejects
   before opening SQLite. Unknown/non-string modes also reject, including when
   context is disabled. Omitting the mode retains `camera_memory`, whose honest
   camera placeholder remains even without a video URL; it fails this strict
   whitelist guard. No mode is inferred from a missing URL and no fetched sensor
   content is stripped to make the guard pass. The context RPC schema already
   permits an empty sensors array; no endpoint or wire envelope changes.
   Owner TTL, privacy, revoke/retired-owner fences and occupied execution slots
   retain their existing behavior. A revoked/closed owner's delayed recall is
   rejected after the read; a still-running camera worker remains busy at close
   and cannot publish its late result. These are local synchronization checks,
   not actual camera stop or hardware acceptance evidence.
   After independent source review, run the finite voice runtime with context
   enabled in a NEW Hub/control session and a newly granted microphone epoch.
   Both admitted real STT turns must produce completed real main requests whose
   exact memory projection is the current confirmed fixture v1/v2, and consumed
   owned replies. This measures request-context continuity, not semantic proof
   that a model reasoned from memory, speaker identity or personal-fact recall.
5. Validate the finished next session through the existing CLI action below.
   It opens the same fixture with UUID/version CAS, checks the current whitelist,
   both new request store/revision/projection bindings, the pre-inference frozen
   readback binding, new Hub/control session, source lineage
   non-replay, microphone renewal after prior cleanup and all strict chains.
   It performs no new model request, speech or memory promotion.
6. After that validation, explicitly forget/reopen empty as above. Revoke/drain
   the owned test context, close/reap its test gateway/SQLite connections before
   file cleanup, and stop only owned finite processes. Never stop the shared model
   server to make cleanup pass. Unknown jobs/owners keep acceptance closed and
   preserve artifacts. Remove only the exact disposable store through existing
   owned cleanup; keep reports outside it. No automatic retry/recovery is added.

```text
voice_memory_acceptance.py prepare --require-live-source --allow-disposable-voice-fixture --directory <fresh-fixture> --output <fresh-prepare.json> --hub-receipt <actual-first-hub.json> --device-receipt <actual-first-device.json> --controller <first-controller> --session-boot <first-session> --source-boot <first-source>
voice_memory_acceptance.py verify-live-context --allow-disposable-voice-fixture --directory <same-fixture> --output <fresh-next-context.json> --expected-store-id <same-UUID> --expected-version <confirmed-1-or-2> --hub-receipt <actual-next-hub.json> --device-receipt <actual-next-device.json> --controller <next-controller> --session-boot <new-session> --source-boot <next-source>
```

The isolated gateway configuration's context block must be explicit (replace
only these placeholders with the independently reviewed disposable binding):

```json
{
  "context": {
    "enabled": true,
    "mode": "memory_only",
    "memory_path": "<absolute-owned-fixture-directory>/memory.sqlite",
    "namespaces": ["<exact-fixture-voice-UUID-from-binding>"],
    "refresh_s": 0.5,
    "owner_ttl_s": 1.5,
    "video_url": null
  }
}
```

This block belongs in the isolated full autonomous configuration; it does not
replace its independently configured gateway network, model endpoints or resource
audit. Use that same reviewed context binding in the finite Hub config. No
production configuration is edited automatically. Local tests use only newly
created neutral whitelist SQLite fixtures and stub model transports; actual
deployment and voice-to-memory acceptance remain separate closed gates.

Use the same staged interpreter/PYTHONPATH prefix and finite command bound from
the preceding section. `next_main_context_validated=true` is the endpoint result;
`live_voice_verified` deliberately remains false. Required independent review
packet: source/config and runtime/model audit bindings; both genuine finished
voice-working-2 Hub/device receipt pairs and hashes; explicit owner confirmations;
UUID/version/revision/whitelist readback receipts from separate processes; the
next-context check; fresh stop/mute/occupied-slot/terminal-context receipts; final
forget/replay-rejection/known owned cleanup. No raw PCM, transcripts, private
configuration values or actual device identifiers belong in published runbooks.
Until those fresh actual gates pass, real two-turn voice-to-memory continuity
acceptance remains CLOSED even when all local tests or receipt checks pass.
