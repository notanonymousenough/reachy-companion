# Reachy — текущий курс

Обновлено: 19.10.2026, 17:20 МСК. TL — единственный оператор Robot/Hub/PC; PM определяет приоритеты и бюджет. [История 18 октября](TECH-STATUS-NEXT.history-2026-10-18-2230.md). Вчерашние GO и сроки автоматически не возобновляются.

## Текущее фактическое состояние

- **PC:** production voice R76 `df12ce…`, config `c0199c…`; память R73 ready, её runtime и DB не менялись. LMStudio **восстановлен**: версия 0.4.16, build2, порт1234, точный прежний `qwen3.5-9b-uncensored-hauhaucs-aggressive`, Q6_K, 8280963456B. Подтверждены прежние context32768 / eval2048 / physical512 / parallel4 / flash / KV offload. Других loaded instances до загрузки не было. Новых весов и генераций в этом срезе0.
- **SDK:** официальный1.5.0 установлен отдельно в `/config/r80-lmstudio-client-v1`; 12 version/hash-verified wheels, offline install + pipcheck PASS, production dependencies/voice/config не менялись. Actual **PASS_METADATA_ONLY**: greeting, app version, WS list_loaded, точный instance, client closed. Upload/generation0. Это не cancel/terminal/camera PASS. [Acceptance](../../R80-lmstudio-client/ACCEPTANCE.json).
- **Server lifecycle:** первые wrapper-попытки не дали устойчивого API. Один согласованный operational pivot с удержанным .NET Process handle дал native exit0 и HTTP после завершения SSH/task. Загрузилась только прежняя модель, load config совпал полностью. Обе owned one-shot task удалены; при успешном cleanup сервер сохранён, process stop0. Ранее созданные failed-попыткой5 процессов удалены только по PID/birth/exe hash. Startup policy не менялась.
- **Hub:** actual R52 `148bf944…`, config `7f11d114…`, selector `367150e4…`; не менялся. Его `/status` не подтверждает Robot ownership, пока Robot недоступен.
- **Robot:** свежая связь отсутствует. Старый `.158`: No route / neighbor FAILED; ограниченные mDNS, known factory hardware identity и known public SSH key discovery результата не дали. Питание, текущие selector/controls/ownership **UNKNOWN**, не «OFF». Сегодня Robot controls/restarts/motion/vision0. Пользователю уже задан единственный вопрос о питании/домашнем Wi-Fi; дополнительных QA/сканов не делать. [STATE](../../R80-fresh-handoff/STATE.json).

## P0: обращение/фон и озвучиваемый текст — R81

PM GO: **≤60 active total**, из них source25 + immutable2rolepack10 до **17:35**, actual10 + fallback15 резерв. Actual/selection только после свежего Robot authority и прежнего model service. Сервер восстановлен; Robot пока блокирует. [Согласованный proposal](../../NEXT-spoken-dialogue-PROPOSAL.md).

Один admission → spoken projection путь normal/AUTO. Явное обращение или связный свежий reciprocal ответ допускают диалог без имени каждой реплики. Неопределённый фон → WAIT/world event, без repair/ACK/history/memory. Самостоятельные world/goal SAY и деятельность не требуют human lease. URL, единицы, wholequote и R73 privacy/forget/completion guards сохраняются. Точная причина новой услышанной «косой черты» и источник repair (ordinary/AUTO) пока неизвестны; U18 без акустической проверки не закрываем.

R81 sourceowner работает; default flag OFF. Сохраняется успешный R76 raw completions/closed-think контракт; R71 nativechat/JSON wrapper/model hop не повторяется. Known-terminal malformed content не должен становиться постоянным AUTO latch. Независимый [RO review](../../R81-dialogue-surface/sourcehandoff/INDEPENDENT-RO-REVIEW-2026-10-19.md) нашёл5 P1 snapshot-проблем: permanent quality latch, неполная reciprocal union/resolve, captured/manual и tail provenance, lease plain-output bypass, URL/TTS/history mismatch. Они переданы sourceowner; до freeze нужны исправления/честный NO-GO, а не число тестов. Robot parent R68 — последний известный18Oct, не свежая authority; при расхождении родителей требуется fresh CAS/fallback.

## U19: зрение и общий текущий контекст — R82

После SDK metadata PASS PM разрешил **≤25 active preparation**, это первые25 из уже оценённых40;15 остаются на actual/fallback. Отдельная SDK/helper область R82, без изменений P0 voice/turn. Owner architecture_route, **artifact deadline17:43**. Один request-owned generation channel, cancel + matched server terminal/доказуемое освобождение lane; image handle ownership/retirement явно проверяются по официальному SDK. TCP close/helper kill не доказывают backend terminal. Не предполагать RAM upload/release; при пробеле API — конкретный source NO-GO.

До fresh Robot authority кадров/архивных замен/upload/генераций нет. После artifact нужен один актуальный price/fallback check у PM; actual затем. Полный shared image/context → одно prediction → связанная речь/stock motion — следующий отдельный согласованный срез **60–75 active**.

## Движение и оставшиеся продуктовые границы

U17 same-package finishing20 имел внешний17:10; завершён **NO-GO до selection** из-за offline Robot, не physical FAIL. Ранее R79 дал actual body≈4.75°/возврат/two UUID terminal, но repertoire откачен и не оставлен; withdrawal NOT_EXERCISED из-за observer no-catch, не STOP FAIL. Последний достоверный fallback18Oct22:29 вернул R68/R76/HubR52 + MIC/AUTO/motor ON; это исторический факт, не current Robot status.

U08 full duplex и U19 shared camera context открыты. Робот, по датированному сообщению владельца, один в закрытой комнате; владелец в другой смотрит фильм. Вероятная Алиса — world context, не установленная speaker identity. Автономный sensory→world/goals→activity/motion/SAY/WAIT цикл остаётся целью. Latest user STOP/OFF/privacy имеют приоритет.

##17:33 P0 source завершён в бюджете

R81 v1 остался immutable NO-GO: финальный TL review нашёл сохранённый reciprocal admission при failed memory union. В **V2** это закрыто до model call двумя строками failclosed WAIT. TL независимо повторил16 tests PASS и проверил artifact hashes. [Root source review](../../R81-dialogue-surface/v2/sourcehandoff/ROOT-SOURCE-REVIEW.json), [immutable package](../../R81-dialogue-surface/v2/deploy/package-manifest.json). Manifest `11d73d72…`, PC `3d807f85…`, Robot wheel `dda600b6…`. Пять исходных P1 закрыты на source уровне с указанными ограничениями. Source+pack закончены до17:35; расширения бюджета не было. Feature flag по умолчанию OFF, production selection0. Actual10+fallback15 остаются резервом до fresh Robot authority; source PASS не акустическая приёмка U18/U20.

##17:43 R82 preparation завершён

[Immutable source manifest](../../R82-visual-lifecycle/sourcehandoff/source-manifest.json) `adaec421…`, version2;17 focused source tests + compile PASS. [TL operator manifest](../../R82-visual-lifecycle/operator/operator-manifest.json): finite NDJSON/authority heartbeat/metadata witness libraries; synthetic transport checks, без камеры/модели. В реально установленном SDK отдельно PASS offline constructors (client/socket0) и read-only selected handle metadata (точный9B, vision=true,32768, instance reference получен). Generation/upload0.

Terminal identity основана на exact instanceReference request → matching SDK channel + observed terminal model_key; instanceReference в official LlmInfo terminal body не выдумывается. Public typed getLocalFileAbsolutePath даёт путь только owned local handle; before/after witness отдельно от backend terminal. Закрытие TCP/client не равно backend cancel proof. Если штатный disconnect оставляет временный файл, допустим обычный exact-owned-path metadata CAS cleanup оператором внутри15; global model unload не доказывает image deletion. PM уточнил: локальный ограниченный временный файл разрешён задачей, RAM-only ограничения здесь нет.

Source preparation STOP,25/40 израсходованы. Remaining15 на один actual: только после fresh Robot authority и одного price/fallback check у PM; finite lane admission/bridge, один свежий shared IPC frame, owned cancel+matched terminal, exact file retirement, обычный ответ и known fallback. No upload, если это не укладывается. Сейчас Robot недоступен, actual/camera/upload/generation0; архивные кадры не подставляются. P0 V2 actual reserve25 также не расходуется. Сервер модели сохранён включённым; Robot power/control остаются UNKNOWN.

Уточнение времени R82 по filesystem receipt: последний product source SDKtrial17:42:57; immutable source manifest17:43:19, TL operator manifest17:43:21. Финальная metadata фиксация на19–21с позже17:43, без последующего продолжения source/actual. Числа observed_utc в operator manifest описывают последнее наблюдение/проверку, а не filesystem timestamp упаковки.
