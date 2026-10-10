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
