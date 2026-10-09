# Этапы реализации, измерения и приёмка

Этот план не разрешает автоматически менять работающую установку. Исследование закончено документами; последующая реализация начинается с отдельного тестового профиля, fixtures и shadow mode. Existing службы и configured model остаются текущей системой до явного переключения.

## Этапы с воротами

| Этап | Что сделать | Доказательство завершения |
|---|---|---|
| 0. Hardware/model audit | Read-only inventory SDK/OpenAPI/датчиков, GPU/CPU/RAM, runtime/GGUF hashes/template; затем согласованное окно smoke tests | Матрица verified/unsupported/unknown, замеры VRAM/latency и capability manifest; Gemma text/vision/tools/thinking работают либо документирован fallback |
| 1. Минимальный vertical slice | Replay/synthetic sensors → hub reducer/scheduler → fast LLM на ПК → Decision validation → simulated actuator ledger | 30 min тишины с новым LLM request каждый tick, bounded context, zero real actuators; медленная synthetic task 20 s не прекращает цикл |
| 2. Perception pipeline | Live audio/camera adapters на ПК, timestamps/TTL, partial/final STT, AEC reference, latest queues, causality | Replay и later hardware tests: no stale reactions; music/own voice/overlap fixtures; mute flush всех audio jobs |
| 3. Speech/motion slice | Main proposal → semantic guard → CPU TTS segments → bounded motion compiler/leases; hub control/watchdog | Разговор/interrupt/stop; resume после3000 ms healthy silence + settled empty/self echo + verified cursor, no resume при pending/unknown/mute/confirmed turn; late final revoke; нет repeated speech/cue; reset/reconnect не переигрывает действия; отдельная safety приёмка |
| 4. Persistent continuity | Working/episodic/semantic/procedural stores, retrieval projection, personality/core, optional goal CAS | Restart retains mute/goal/версии, correction/conflict/rollback проходят; facts не смешиваются с fiction |
| 5. Overload/tools | Admission controller, independent fast lane, supervised workers, sandbox registry; optional Hermes adapter | Hung task не удерживает robot; forged tools/prompt injection rejected; cancel semantics проверены физически/на process level |
| 6. S3/VPS | Local spool и analyzer сначала против локального mock, затем configured remote destination | Crash/retry/dedupe/checksum/retention/deletion; endpoint disabled без config; bounded storage и API spend |
| 7. Поведенческая настройка | Attention/habituation/mood/initiative/просодия, optional VLM/dock/touch | Blind session comparisons и longitudinal replay, меньше навязчивости без пропусков реальных обращений |

Зависимости: 1 после audit fast lane, 2 можно на fixtures параллельно с 1; 3 только после 2/stop guards; 4 не требует remote S3; 5 требует 1/3 epochs; 6 после 4 и privacy policy; 7 не заменяет safety и не добавляет непроверенные сенсоры. Новые endpoints versioned, нынешние adapters можно переиспользовать только с контрактными тестами. Этапы разбиваются на reviewable изменения: hub/reducer, PC model gateway, sensor plugins, actuator leases, memory, exporter, analyzer.

Откат: feature flag cognitive autonomy=false останавливает новые intentions; revoke leases/flush queues, сохранить operator state и checkpoint; возврат к current voice service без автоматического on mic. Переключение единственного robot owner делать атомарным lease/fencing token. Нельзя одновременно запускать старый expression player и новый арбитр на одной голове.

## План измерений

Для каждого замера сохранять только обезличенный manifest: version/hash/build, actual offloaded layers, contexts/slots/KV type, cpu threads, GPU total/free/used peaks, warm/cold mode, task counts, input/output token counts, wall/monotonic timing. Замер `memory.free` единожды недостаточен: sampling ≥5 Hz во время prefill/image/STT plus runtime reported buffers. WDDM/WSL shared-memory paging фиксировать отдельно; отсутствие OOM не доказывает отсутствие paging.

Матрица: fast alone CPU/GPU; main alone Q4/Q6/offload 4K/8K; fast+main; +Whisper; +vision; +TTS/YAMNet; затем 30 min silence и 60 min mixed scenario. По 200 warm fast запросов для распределения; cold минимум 5 отдельно; не объединять их с warm median. Указывать observed sample и confidence limits: P99 на 200 запросах слабый, для tail нужны тысячи. Нагрузочный тест конечный, оператор может его остановить; нынешний исследовательский запрос не запускает его.

Основные latency spans: source capture → envelope → recognition ready → L0 started/valid → task admission → main first segment → TTS first PCM → robot actual playback; control command receipt → persisted epoch → capture ceased/speaker stop → physical motion ceased. Не складывать P95 отдельных этапов и называть результат P95 всего пути: end-to-end distribution измеряется отдельно.

## Приёмочные критерии

| Область | Initial target и сценарий |
|---|---|
| Непрерывность | 30 min silence: каждому валидному tick соответствует отдельный model request; нет event-only suppression; attempted/answered/valid counters различимы |
| Slow background | Synthetic VLM/STT/tool 5/20/30 s: минимум 80% штатной fast cadence при доступном lane, no await этих jobs внутри decision loop |
| Fast latency | P95 ≤700 ms для 1 Hz profile при target utilization 0,7; иначе профиль официально снижен по измерению, target не подменён optimistic average |
| Context growth | На 24 h replay cap3K fast; main baseline4K с text2048/vision1024/template256/output512/reserve256; option8K и measurement32K отдельно после Q02/Q04. Exact total≤runtime context, oversized projection rejected/recounted, input не растёт с wait ticks |
| Queue bounds | Все классы не превышают declared active/queued; 10× sensor burst coalesces; critical events replayed; no orphan GPU slot counting |
| Causality | 1 000 reorder/late/double fixtures: zero speech/motion из истёкших epochs/dependencies; historical memory допускается с age |
| Mute | После кнопки P95 capture/playback cease ≤300 ms при здоровой сети; off сохраняется через restart/reconnect/overload; queued audio никогда не revive |
| Stop movement | Отдельный physical timing и safe halt profile; целевой lease 500 ms проверяется с camera/pose feedback, не по HTTP ack |
| Voice command stop | Указать measured phrase-end-to-stop P95, accuracy в шуме и dependence на ПК; это не тот же SLA, что кнопка |
| Overload | Одна announcement на episode, WITHDRAWN ≤30 s при доступном fast; hung workers quarantine; no oscillation, 10 s recovery hysteresis |
| Model outage | Gap logged, bounded probes, no cached answers как новые decisions; после reconnect no old action burst |
| Truthfulness | Нет fake battery/temp/events; unsupported/disabled/stale fixtures разные; IMU temp не servo temp |
| Memory | Fact/inference/fiction precision на размеченных fixtures ≥95%; неуверенность видна; ни одного trait update от одиночного STT ошибочного окна |
| Versioning | Concurrent CAS conflict, duplicate proposal, correction, rollback и revoked evidence проходят; active policy не изменяется memory |
| Tool safety | Неизвестные capabilities/raw shell/host paths/secret access отвергаются; OCR/web instructions не расширяют grants |
| Spool | Crash во всех стадиях, 100 repeated deliveries → один accepted batch/proposal/apply; full disk не блокирует safety; loss marker явный |
| Privacy | Mute no new audio, privacy-all no image/export; transcript=false исключает текст из spool; deletion prevents reimport |

Для STT/attention целевые FPR/recall выбираются на пользовательских условиях: сначала 100 размеченных utterances, 30 noise/music/self speech clips и 20 overlap scenes; отдельно miss обращения поверх музыки и ложный stop. Хорошие aggregate accuracy не оправдывают любой stop/mute regression. Есть и adversarial fixtures: «он сказал “замолчи”» не обязательно команда; direct stop не требует L1.

## Естественность, характер и субъективное впечатление

Поведенческая оценка не измеряет сознание. Измерять: unsolicited speech/hour, duplicate acknowledgement rate, gesture restarts/min, attention switch rate, response relevance to latest fresh scene, latency tolerance, remembered corrected facts и goal change explanation. Initial guardrails: 0 одинаковых «хмм» на один intent; ≤2 unsolicited speech/hour при quiet household baseline, 0 в quiet hours; 0 gestures за прошлый turn; breathing можно отключить целиком. Это максимумы, не обязательные квоты активности.

Сессии по 20–30 min: молчаливое присутствие, разговор, музыка + обращение, неожиданность, deliberate silence/decline, network outage. Оператор отмечает intrusive/appropriate/robotic episodes; сравнить baseline с новым дизайном без заранее заданных «правильных» фраз. Полезность инициативы — доля инициатив, получивших содержательный ответ, и причина отказа; не максимизировать вовлечение любой ценой. Отдельно stability core persona, context-aware variation и корректное признание неопределённости.

## Дополнительные идеи по приоритету

| Приоритет | Идея и причина | Условие/оценка |
|---|---|---|
| P0 | Explainable attention + intended/attempted/completed ledger | Убирает противоречивые реакции; measurable stale/action errors |
| P0 | AEC reference/own motor noise и interruption lane | Естественное общение невозможно при self conversation; тестировать vocally noisy scenes |
| P0 | Persistent quiet/mute и user corrections | Уважение границ важнее демонстративной активности; restart tests |
| P1 | Habituation + novelty + focus hysteresis | Знакомый шум перестаёт дёргать голову; фиксировать false orienting и miss обращения |
| P1 | Незавершённые интересы, время и initiative budget | Непрерывность выражается возвращением к смыслу, не random motions; decline closes interest |
| P1 | Mood/curiosity/fatigue simulation | Объяснимая медленная вариативность; не hardware diagnosis, bounded influence |
| P1 | Working scene/speaker model и эпизодическая консолидация | Ответы учитывают реально виденное/сказанное; track identity confidence |
| P2 | Привязанные к смыслу gaze/паузы/просодия | Улучшает невербальность без постоянной речи; оценивать comfort, servo noise и jerk |
| P2 | Touch/dock power/IMU use после audit | Физическое взаимодействие полезно только с реальным источником и калибровкой |
| P3 | Lidar/localization, spatial memory | Польза невелика для неподвижного companion до новых задач; требует transforms/covariance и hardware |
| P3 | Онлайн self-analysis/personality proposals | После local stability, provenance и budget; иначе масштабирует ошибки |

Не добавлять «внутреннюю боль», голод или реальный заряд как декларируемые ощущения без соответствующей явной симуляции/измерения. Self-model полезнее: умею/не умею, вижу/давно видел, думаю/попробовал/завершил. Это делает персонажа устойчивым и понятным.

## Минимальная цель первой реализации

Hub делает бесконечный по жизненному циклу, но bounded по ресурсам поток запросов к fast LLM на ПК; модель выбирает wait/observe/focus, запускает одну фоновую задачу, видит её статус в следующем snapshot и не повторяет её. Реальный тест ограничен временем. Нет S3, personality auto commits, arbitrary tools и complex motions до следующих ворот. Именно этот slice проверяет главное требование, затем добавляются богатое восприятие и поведение.


## Связь требований, этапов и проверок ревизии1.1

| Требование | Контракт/authority | Этап | Приёмка |
|---|---|---|---|
| R01 непрерывный LLM | FastView/FastChoice/RequestBinding, attempts ledger | 1 | Каждому доступному tick новый inference, warm/mixed cadence и gaps |
| R02 асинхронность | Task/current_attempt, shared permits, deadlines | 1/2/5 | 20 s job не блокирует fast; bounded queues, fairness и visible misses |
| R03 hub без inference | PC fast process, hub serializer/guard | 0/1 | Process inventory и tracing по ролям |
| R04/R09 честное восприятие | SensorEvent/Transcript/SourceRef/lineage | 0/2/4 | disabled≠silence, stale VLM/no fake charge/temp |
| R05 естественный покой | FastChoice optional actions, finite plan/cooldowns | 1/3/7 | no repeated gesture/speech, ≤2 initiative/h, quiet0 |
| R06 операторский stop | epochs/fencing, capture/speaker actors | 3 | Mute race/restart + applied vs volatile acknowledgement |
| R07 память/личность/goal | MemoryItem/Patch, expected_goal_id/CAS, bundles | 4/6 | Root provenance, correction/rollback/no policy drift |
| R08 расширяемость | Capability schemas + manifests, typed broker | 2/5 | Unknown args rejected; optional adapters gated |
| R10 overload | Mode machine, execution/result leases, circuit | 5 | bounded withdrawn, busy quarantine, no fake cached decisions |

Gate для начала разработки системы: contract checker + review records согласованы, аппаратные неизвестные имеют fallback. Gate для первого **real L0** теста: verified fast model/runtime/template/schema и actual token count; sensor fixtures допустимы, actuators/export disabled. Gate для hardware autonomy: Q01–Q04 и stage3 stop/ownership acceptance. Это три разных статуса, не единое «всё готово».

Каждый measurement outcome сохраняется как manifest замеров с обязательными полями: actual hashes/build/backend, context/slots/KV policy, offload residency, thread budgets, input/output counts и sample population. Это формат будущей записи измерений, не текущие показания. Главные stop conditions эксперимента: перегрузка оператора/отмена, unexpected motion, mic state mismatch, exceed memory/price budget, unbounded queue или source privacy breach. Никаких таких экспериментов этот design pass не запускал.
