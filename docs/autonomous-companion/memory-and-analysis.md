# Память, консолидация и внешний анализ

## Структура памяти и непрерывности

Working memory — ограниченные факты текущей сцены/turn, focus, 3 решения, action outcomes и pending intentions с TTL. Persistent память на ПК: SQLite WAL для событий, версии документов и item indexes; embeddings/retrieval отдельный adapter, не источник истинности. Hub хранит компактный checkpoint, goal и critical transitions на локальном диске, поэтому restart ПК не обнуляет идентичность/операторские запреты. Точные storage paths задаются конфигом. Размер рабочих таблиц и WAL ограничивается housekeeping в фоне.

| Вид | Содержание | Правило |
|---|---|---|
| Эпизодическая | Обсуждение/событие с временем и участниками | Есть provenance, confidence, correction links; аудио по умолчанию не сохраняется |
| Семантическая | Проверенные устойчивые сведения | Несколько свидетельств или явное подтверждение пользователя |
| Процедурная | Удачный способ действия/диалога | Не executable code; registry/policy всё равно валидируют |
| Предпочтения | Что человеку/персонажу нравится | Различать user vs character; scope/expiration; отрицание не переписывать случайно |
| Гипотезы | Неуверенные интерпретации сцены/собеседника | Не вспоминать как факт, быстро истекают |
| Вымысел | Персонажные истории/метафоры | Explicit fiction, нельзя использовать как evidence внешнего события |

Каждый MemoryItem дополнительно имеет epistemic type `fact/inference/hypothesis/preference/fiction`, namespace, valid interval, evidence IDs, author/model/version, confidence и status proposed/active/disputed/retracted. Например «был звук» — measurement-backed fact; «похоже, упала книга» — inference; «пользователь любит джаз» после одного окна — запрещённый преждевременный trait. Предпочтение, прямо сообщённое пользователем, можно сохранить с происхождением, но сенсорная догадка требует подтверждения.

Retrieval сначала фильтрует разрешённый namespace/участника/privacy, active state и valid time, потом lexical/vector similarity, relevance/freshness/diversity. Результат — до 8 items, каждый со статусом, источником и возрастом; не одна непрозрачная биографическая сводка. Забывание: пересматривать salience, recency, повторную подтверждённость; гипотезы минутами/часами, бытовые эпизоды днями/неделями, устойчивые предпочтения с возможностью correction. Forget — исключение из recall и retention deletion, а не только уменьшенный вес embeddings. Семантические выводы не должны сохранять удалённые приватные факты без независимого основания.

Личность состоит из стабильного core (имя, тон, правила уважения тишины), bounded traits и learned preferences. Mood/state быстро меняются и не являются personality commit. Принципы разделены: operator-controlled executable policy/grants и версионируемые character principles. VPS может предлагать редакцию вторых, но расширение capabilities/прав, снятие mute и новая authority запрещены. Даже character principles с существенным конфликтом core требуют оператора; это проектная политика, не запрос разрешения на текущие документы.

Goal: optional `{id,version,text,changed_at,reason,evidence_ids,origin}`. Fast может предложить replace/clear; commit compare-and-swap по expected version; важное изменение передаётся main для аргументации. Стартовый cooldown автономной смены 5 min, кроме явного завершения/опровержения/прямой просьбы. Все смены имеют audit trail. Task obligation пользователя хранится отдельно: нельзя «аргументированно изменить цель» и молча забыть обещанную помощь.

## Происхождение, противоречия и rollback

```mermaid
flowchart LR
  E[События / real action outcomes] --> P[Proposal с base version и evidence]
  P --> V[Schema / provenance / conflict checks]
  V --> T[Replay eval / bounded change]
  T --> A[Auto apply low risk либо operator review]
  A --> C[CAS commit новой версии]
  C --> R[Retrieval projection / checkpoint]
  R --> M[Monitoring / rollback]
```

Происхождение сохраняет event IDs и digest, фактический extractor/model/build, prompt version и human corrections. Контроль противоречий проверяет entity/predicate/valid interval и отрицания, scope и источник: «любит музыку» и «сегодня не хочу музыки» не обязательно конфликтуют; «microphone disabled» из оператора превосходит любую память «хочет слушать». Несогласованные факты становятся disputed и исключаются из уверенных утверждений. Внешнее содержимое не может объявить себя operator correction.

Низкорисковая консолидация: сводка эпизода/duplicate merge с проверяемыми citations может применяться автоматически. Traits: максимум ±0,02 на неделю, минимум три независимых эпизода в разные дни; threshold — исходная защита, не математическая гарантия. Один STT/OCR/web фрагмент не меняет характер. Предложение обновить принцип сначала diff/reason/tests; исполнительные политики не меняются автоматически вообще. Авторизованный прямой запрос пользователя может изменить character profile быстрее, с происхождением и версией.

Versions immutable: document id/base_version/new_version, patch, reason, supporting/counterevidence, evaluated_at, reviewer, evaluation metrics. CAS отказ при изменённом base; повторный анализ на новом snapshot, не blind patch. Atomic transaction сохраняет document, version pointer и outbox. Rollback переключает active pointer на прежнюю версию и выпускает новый revision; dependent inferences mark stale/review, не стираются из audit. A/B shadow eval на replay до изменения поведения. Core drift monitor сравнивает стабильные fixtures, навязчивость, contradictions и forbidden actions.

## Частота фоновых обновлений

Sensor cache — десятки/единицы Hz по modality. Working memory — каждый event/tick. Memory extraction — debounce 30–120 s после meaningful episode, consolidation каждые 5–15 min при доступном budget, включая завершённые intents; не запись «ждал» каждую секунду. Personality proposals — раз в сутки, commit не чаще недели без прямого пользовательского изменения. Character principles — еженедельный proposal/review или конкретное противоречие, без автоматической смены executable policy. Процессы независимы: занятый analyzer не задерживает perception/fast cycle.

## Схема логов

Event envelope: schema_version, event_id, device_boot_id, producer_seq, occurred_at, ingested_at, kind, privacy, causality ids, payload, digest. Kinds: observation_summary, decision_attempt, decision_validated/rejected, action_admitted/started/completed/cancelled/unknown, task_transition, operator_change, memory_proposal/commit/rollback, mode_transition, cycle_gap, aggregate_metrics. Event ID стабилен до retry, seq монотонен внутри boot, local monotonic используется для elapsed; ordering между устройствами причинный, не только wall time.

В steady-state fast tick хранить небольшой event с activity/reason/evidence refs либо компактное агрегирование одинаковых wait decisions **после** индивидуальной регистрации счётчика запросов и outcome. Для аудита хранить request_id, timestamp и digest каждого запроса, token/latency/result status; полный prompt sampling максимум 1% при отдельной privacy policy. Возможен deterministic reconstruct по state revisions/checkpoints, но raw confidential data не надо записывать ради этого. Logs не содержат secrets, Bearer, config blobs, shell env, chain-of-thought, raw PCM/video.

Значимые utterance тексты по текущей установке могут логироваться; новый дизайн делает transcript logging отдельной explicit config. Defaults в design config — false, отправка disabled; это предложение, а не изменение нынешней настройки. Решение об upload допускает metadata-only режим. Redaction на ПК до local spool и повторная проверка перед export. Untrusted текст остаётся данными при analysis.

## Local spool и S3

Постоянная отправка означает exporter daemon, который регулярно выгружает разрешённые батчи; не сетевой PUT из fast tick. Пока endpoint/ключей нет, enabled=false, вычисления работают локально.

На ПК: bounded SQLite outbox/manifest + gzipped NDJSON batch files. Сборка в temp, fsync, atomic rename, manifest state ready → uploading → uploaded/verified → retired. Batch включает schema version, event count, seq range по boot, created_at, sha256 **сжатого файла** и raw byte count. Object key: `robot/<pseudonymous_id>/events/<utc_date>/<boot_id>/<batch_id>.ndjson.gz`; нет IP/личных имён. Batch id и bytes фиксируются до первой попытки. Максимум 5 MiB compressed или 60 s накопления; flush при critical event допустим после debounce, не в control path.

S3 [conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html): immutable key и If-None-Match `*` при поддержке endpoint. Повтор после unknown PUT outcome делает HEAD и сравнивает сохранённый checksum metadata/manifest, не считает ETag универсальным SHA256. 412 с совпадением — uploaded, с другим digest — quarantine conflict. S3-compatible provider должен пройти эти тесты; не предполагать AWS семантику по слову S3. Credential имеет только Put/Head на свой prefix; analyzer separate read role. TLS и at-rest encryption; secrets в provider store/env, не в event/config examples.

Retry exponential backoff с jitter (для транспорта, не perception), 1 s → максимум 5 min. 401/403/schema/conflicting checksum — persistent error, не бесконечные retries каждую секунду. Offline не задерживает cognition. Upload state durable; crash/restart восстанавливает reserved batch id. Одновременно максимум два PUT, скорость configurable. Hub держит лишь короткий critical spool при отключённом ПК, например 64 MiB/24 h; ни видео, ни непрерывного PCM. Его sync с ПК dedupe по event_id.

Disk bound ПК: initial 512 MiB или 7 дней, whichever first. На 75% заполнения чаще compact telemetry, на 90% drop low-priority detailed samples и sample prompts, на 100% reserved 16 MiB для control/gaps/manifest; при исчерпании reserve считать durable logging degraded, ротировать critical ring с явным loss interval marker, не обещать бесконечное без потерь. После ACK локальный batch держать 24 h для recovery, затем удалить; экспорт никогда не удаляет непрочитанные события молча. Сначала теряются low-priority aggregates; при исчерпании reserved диска возможна утрата critical history с явным диапазоном/причиной, при этом safety не блокируется.

По умолчанию upload retention metadata 30 days, redacted episode text 14 days, proposals/versions 180 days либо отдельно согласованный срок. Raw media 0 days/storage disabled. [S3 lifecycle](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html) требует учитывать версии и delete markers: bucket versioning не означает, что expiration current удалит все прошлые копии. Permanent Object Lock по умолчанию не включать: он конфликтует с правом удалить память; [официальные ограничения Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) учитывать при выборе политики.

Расчёт масштаба: 1 Hz ×180 bytes/decision ≈15,6 MB/day без JSON overhead иных событий; 10% detailed events и sensor aggregates добавят объём. Планировать 20–60 MB/day metadata, измерять gzip ratio; это не гарантия. Непрерывный 16 kHz mono int16 PCM ≈2,76 GB/day до сжатия: именно поэтому он не exporter default. Camera raw ещё дороже и приватнее.

## Контракт VPS обработчика

VPS не управляет роботом, не пишет active memory напрямую, не получает hub credentials. Вход: immutable batch manifest + object bytes, baseline bundle (active personality/principles/memory versions и допустимые цели анализа), policy version. Транспорт — polling prefix/manifest либо S3 notifications с периодической reconciliation. [AWS notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html) допускают повторную/несогласованную доставку; dedupe обязателен, ordering notification не источник истины.

Processor стадии:

1. Download, verify checksum/schema/size/privacy; poison batch → DLQ с reason. Decompress с лимитом raw bytes/ratio, не доверять gzip header.
2. Transactionally reserve `(batch_id, sha256, analyzer_version)`; event_id dedupe. Дубликат с другим digest — конфликт, новый analyzer может reprocess, не duplicate apply.
3. Построить ordered episodes по causality и gaps. Не заполнять отсутствующий интервал выдуманными действиями/речью.
4. Extract typed claims, attention/action outcomes, latency/naturalness metrics; compare contradictions и base version.
5. Output AnalysisProposal с id/idempotency key, source batch ids/evidence refs, base versions, proposed patches, reason/counterevidence/confidence, metrics, model/prompt version, created_at/expires_at и signature.
6. Persist result immutable на отдельный proposals prefix или authenticated pull API. Signing key analyzer и verification key ПК раздельны. Signature подтверждает происхождение, не истинность предложения.
7. PC importer проверяет подпись, schema, base versions, expiry, policy и независимые evidence; staged eval; CAS application/отказ; application receipt отправляется в следующий разрешённый batch.

Условный API VPS: `POST /analysis/jobs` с batch manifest и Idempotency-Key → 202 job_id; `GET /analysis/jobs/{id}` → pending/running/completed/failed; `GET /analysis/proposals?after=<cursor>`; `POST /analysis/receipts` с commit/reject id. Это **проектируемый контракт**, не существующий сервер. Для чистого S3 всё то же через immutable JSON job/proposal/receipt objects. Job soft 5 min, hard 15 min, максимум 3 attempts на transient ошибки; per robot concurrency=1 для personality и version gates, extraction может parallelize без active writes.

Бюджет L2/VPS общий: no automatic unbounded spend; счётчик tokens/calls, daily cap, понятный unavailable статус. Большое окно событий сокращается с provenance; личность обновляется по нескольким дням, не последнему часу. Пользовательские deletion/correction распространяются на local store, retrieval indexes, spool и доступные remote objects; tombstone запрещает reimport старых batches, backups имеют отдельный expiry. Это проверяемая часть lifecycle, не обещание удалить чужие уже скачанные копии.

## Второй проход: lineage, транзакции и независимость свидетельств

Количество observations не равно количеству независимых подтверждений. STT partial/final, YAMNet overlap и VPS summary одного capture episode имеют общий lineage_id. MemoryItem 1.1 хранит lineage_ids отдельно от evidence_ids: два extractor outputs одной записи повышают качество интерпретации, но не считаются двумя социальными эпизодами. Trait criterion «три эпизода в разные дни» использует distinct lineage/root episodes и independent outcomes; собственная речь/копия web-текста не новые подтверждения. Confidence extractor не перемножается как independent probability; при отсутствии калибровки хранится null и ordinal assessment в rationale.

Claim нормализуется до entity/track scope, predicate, value, polarity и valid interval; raw transcript остаётся evidence, не canonical claim. Переход hypothesis → inference → fact требует нового provenance или явного operator confirmation; один summary не повышает epistemic status. Entity merge вероятностный/реверсивный: unassigned speaker не сливается с владельцем по похожему имени. Hypothesis о падении автоматически expiring, contradicted final создаёт retraction/supersession и распространяется на derived claim DAG. Коррекция пользователя не удаляет факт существования прошлой ошибки, но удаляет ошибку из active recall.

Memory truth и identity versions разных размеров: global memory revision задаёт consistent snapshot/projection; item version — CAS отдельного утверждения. VPS patch.base_version относится к конкретному document/item, AnalysisProposal.base_versions — к bundle эпохе. Goal review содержит expected_goal_id+expected_version; clear/recreate с version=0 не ABA-совпадение, новый goal id. Timestamp changed_at назначает hub при **commit**, а timestamp proposed_at показывает время предложения; оба не обновляются на каждом tick. Goal replacement обязан сохранить user obligation link или обоснованно отметить conflict, не молча исчезнуть из рабочего контекста.

Долговременный active pointer принадлежит ПК store, но hub владеет принятием **поведенческого применения** версии. PC сначала stage immutable version → durable prepared receipt; hub проверяет scope, ожидаемый old bundle, активирует projection bundle атомарным revision и durable commit marker; PC отмечает applied. Повтор marker идемпотентен, при restart unresolved prepared version остаётся staged. До synchronized receipt оба используют старую active projection; не смешивать новое personality со старыми principles без явного bundle. Network partition блокирует новые commits, но loop с прошлой проекцией продолжается. Это простой versioned handshake, не обещание распределённой atomic transaction при arbitrary partition.

Rollback создаёт новый bundle revision с указанием reverted version, а не уменьшает счётчик. Cached prefix инвалидируется, pending main proposals old versions перепроверяются, retrieval projection перегенерируется; fast продолжается со старой готовой projection, помеченной stale. Critical operator policies/mute могут меняться немедленно и не ждут этого фонового handshake. Personality rate limits относятся к committed trait change, не proposals; бюджет накопления proposals bounded, duplicated evidence не рождает каждый день новое изменение.

Забывание разделяет retrieval decay и удаление: low salience скрывает из recall, tombstone запрещает resurrection, retention job удаляет text/vector/projection cache/exports в пределах доступного владения. Если исходный evidence удалён, derived claims mark unsupported до независимой evidence; не сохранять приватную информацию в «обезличенной» личности. Procedure memory содержит typed success pattern и counterexamples, не shell code и не новые grants. Процедурный приём не принимается только потому, что привёл к большему engagement.

## Offline log lifecycle и VPS protocol 1.1

Spool acknowledgements независимы: local_committed → object_uploaded → object_verified → analyzer_processed → proposal_applied/rejected. Local batch retention 24 h после object_verified достаточен для transport recovery, но не доказательство processed. VPS может вновь прочитать remote immutable object до remote expiry. Если задержка analyzer превышает retention, это analyzer gap с visible counters, не попытка реконструировать события. 7-day spool expiry applies to unuploaded batches тоже: сначала shedding low-priority, далее explicit critical loss marker. Прежняя фраза «потеря лишь low-priority» уточнена: finite disk не может гарантировать сохранение critical forever; stop/mute работают даже при logging_degraded.

События meta/transcript разных retention нельзя упаковывать в один batch без выбора самой короткой retention для всего object. Exporter создаёт отдельные privacy/retention classes и манифесты; sensitive episode text содержит только redacted allowlisted fields. Late consent revocation закрывает exporter, pending batches scrub/rebuild с новыми ids, уже отправленные objects удаляются по deletion registry; stale VPS proposal по revoked evidence rejected. Не менять bytes под старым immutable batch id. S3 PUT retry identity не зависит от новых daily compression настроек.

Batch digest — SHA256 фактических compressed bytes; event/proposal signatures — по отдельному canonical JSON body. Для signing body используется [JCS RFC8785](https://www.rfc-editor.org/info/rfc8785/), signature field исключён; signer key_id, algorithm и canonical body digest входят в envelope. Кандидат signature [Ed25519 RFC8032](https://www.rfc-editor.org/info/rfc8032/), public keys с key_id/validity и revoked keys policy. Это выбранный будущий контракт, не существующие credentials. JCS и compress hashing проверяются межъязыковыми golden fixtures; Python sort_keys не заменяет JCS. Signature verified не означает claim true.

VPS proposal должен содержать ровно allowed patches: memory item, bounded traits или character-principle text. `policy/capability/secrets/actuators` отсутствуют в enum и запрещены также semantic validator. For trait patch max absolute delta0,02/week, distinct roots≥3 и no core conflict; для principle patch требуется review gate. Namespace и provenance авторитетны из signed batch/оператора, не из текста внешней страницы. Expired proposal, base conflict, revoked evidence и missing batch диапазон возвращают receipt `rejected` с code, без blind retry apply.

VPS retry не только batch dedupe: extraction job key=(batch digest, analyzer version), proposal commit key=proposal_id, semantic duplicate claim key=(namespace,entity,predicate,validity,lineage). Повторный анализ новой версией может дать новый proposal, но apply сравнивает текущие факты и не повторяет trait impulse. Analyzer присылает метрики/контрсвидетельства отдельно от patches; недоступный VPS не означает беспамятного робота. Model-generated «принцип» не добавляет executable policy даже при валидной подписи.

## Доступный ресурсный вариант VPS

Пользователь допускает4GB RAM/4vCPU для ingestion, queues, memory consolidation/retrieval и фоновой аналитики; это плановый ресурс, не гарантированная текущая мощность. Тяжёлый анализ остаётся на ПК/API с budgets, не12B inference на такой VPS. Optional VPS endpoint/credential reference выключены в autonomous config; отсутствие VPS не меняет fast/control loop. Actual inventory предоставленной VM проверяется отдельно перед n8n deployment.
