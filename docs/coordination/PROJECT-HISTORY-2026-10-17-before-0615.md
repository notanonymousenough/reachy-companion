# Reachy: управление проектом

Дата старта управления: 17 октября 2026, время пользователя Europe/Moscow.
Координатор: чат `01a14730-3182-71a0-a4d4-fccb2c7b4b16`.

## Цель и порядок приоритетов

Цель — автономный компаньон по пользовательскому дизайну: непрерывные восприятие и решения, инициативность, речь, штатные движения, память и ограниченные ресурсы. Разговорный smoke test сам по себе не означает готовность автономного компаньона.

1. Ранний воспроизводимый живой цикл на настоящем стенде.
2. Устойчивая работа восприятия, решений, речи и движений одновременно.
3. Память и инициативность согласно дизайну, затем дальнейшее развитие.

Пользователь не задал календарного дедлайна. Первый результат выпускаем кратчайшим проверяемым шагом; оценки сроков появятся после обследования. Целевую функциональность не вычёркиваем ради первого выпуска.

## Активные задачи и границы

| Чат | Результат | Разрешённые изменения |
|---|---|---|
| `01a14732-dacd-7d40-88f4-5350b5f9c957` — аудит, завершён | `state-audit-2026-10-17.md` | Результат принят; изменений больше нет |
| `01a14732-e6ec-7943-b726-6338f1796762` — исследование, завершено | `design-2026-10-17.md`, `design-review-2026-10-17.md` | Результат принят; исходный дизайн сохранён |
| `01a14732-f696-7dd0-9003-c2868120dd62` — baseline, завершён | `live-baseline-2026-10-17.md` | Владение устройствами освобождено |
| `01a14736-68cf-76f0-8cb9-f5b40033f6d4` — планирование, завершено | `DELIVERY-PLAN.md` | Принят с поправкой приоритета ниже |
| `01a14739-bfac-74e1-a6f3-2fe66cdf23ec` — R0, завершена | `R0-voice-failure.md`, переносимый patch, launcher | 33 offline проверки пройдены; стенд и старый runner не изменены |
| `01a1473a-bc53-7001-9e55-879245b077d3` — C0, завершена | README вводный статус, START-HERE, исторические предупреждения, `C0-cleanup.md` | Проверена 41 ссылка; код и устройства не менялись |
| `01a14742-6820-7201-b686-6f3b26348959` — R1, завершена | `R1-voice-runtime.md`, `runtime-baseline.md` | Реальный ответный ход завершён, listening ON; владение освобождено |
| `01a14750-1148-79d2-887c-a2d98cef1c82` — Q1, завершена | `Q1-voice-baseline.md` | Voice и listening ON приняты в пределах receipts; аппаратное владение освобождено |
| `01a14750-1d74-7971-9923-8aa8a943a333` — M0, завершена | `M0-camera-coexist.md`, camera producer patch | Source-ready, 44 offline проверки; hardware PASS не заявлен |
| `01a1475d-ec23-7db2-a961-0b01726b44ba` — M1, завершена | `M1-camera-live.md`, дополнение runtime-baseline | 94 разных кадра при mic ON; владение освобождено, listening ON |
| `01a1475d-f91e-7bf3-a237-93adb450e3a4` — A0, завершена | `A0-continuous-capture.md`, exact audio candidate | Source-ready к installed 4e2d baseline; 89 offline проверок, без hardware PASS |
| `01a1476b-c451-7361-a82d-c25202dce0dd` — A1, завершена | `A1-continuous-live.md`, runtime-baseline update | Exact A0+opt-in оставлен в работе; PCM43,55s/STT/main/APLAY без gaps/overflow; владение освобождено |
| `01a1476b-cfa7-7fd2-b818-472147effaab` — N0, завершена | `N0-normal-session.md`, camera context normal wiring | Первая source-ready вертикаль, 51 offline проверка; полный loop открыт из-за AudioPeer/native Agent mismatch |
| `01a14779-9158-7313-9f80-6039bc804491` — N1, завершена | `N1-native-adapter.md`, native autonomous adapter | Source-ready native Agent bridge/один stock settle; 64 offline проверки; без live PASS |
| `01a14779-9d8a-78e2-b63d-695c02ec3a1b` — Q2, завершена | `Q2-continuous-baseline.md` | PCM43,552s независимо принят в границах evidence; свежие snapshots ON; владение освобождено |
| `01a14786-f0b0-7f52-bdb9-f8116fa83137` — P0, завершена | `P0-fast-readiness.md` | Fast CPU0.8B готов, 3/3 contract probes;2s cadence не подтверждена; владение освобождено |
| `01a14795-019c-73a0-88c9-81e700e3684f` — N2, завершена с blocker | `N2-native-live.md`, runtime-baseline update | Native status expired,0accepted/1actual response; normal listening ON, владение освобождено |
| `01a14795-0cbf-7db2-8d94-92ab1de30a46` — S0, завершена | `S0-alice-short-replies.md`, exact worker phrase gate | Source-ready,10offline checks, не установлен; live shortness UNKNOWN |
| `01a147a2-aa60-7160-96cb-0f190bcfb65c` — N3, завершена с blocker | `N3-status-native-live.md`, runtime-baseline update | Hub/QUICKACK улучшили polls, стартовый aggregate /status timeout;0decisions, listening ON, владение освобождено |
| `01a147b1-39c0-7122-999b-c1230961c203` — N4, завершена с runtime blocker | `N4-bootstrap-native-live.md`, runtime-baseline update | Deployment одобрен, bootstrap прошёл; runtime status expiry303,6ms,0decisions; listening ON, владение освобождено |
| `01a147b1-45fe-7f63-b68c-e415dca1447e` — R3, завершена | `R3-observer-resilience.md` | Read-only proposal bounded transient-unavailable/effect-closed polling; server epoch ABA prerequisite открыт |
| `01a147be-41af-7f53-b1f9-fa178e0c7453` — R4, завершена | `R4-authority-epoch-contract.md` | Durable STOP/privacy/owner epochs PASS; pause/resume same-epoch ABA найден, source-generation proof нужен |
| `01a147cc-0094-7931-8c79-fbdf817c6209` — R5, выполняется | `R5-observer-recovery.md`, native observer recovery diff | Только офлайн native source/tests; explicit UNKNOWN/effect-closed transient policy, без source/hardware соседнего worker |
| `01a147cc-0ea8-7b42-94fb-4ba9e08cb5e7` — S1, выполняется | `S1-alice-short-live.md`, runtime-baseline update | Единственный аппаратный владелец; exact S0 worker deployment+короткий Alice обмен; без autonomous/audio/camera source |

Предыдущие чаты — источник опыта и доказательств. Новые исполнительские задачи туда параллельно не направлять. У каждой следующей задачи один владелец, небольшой scope, список файлов/ресурсов, входы, проверяемый результат и условие завершения. Пересечение владения требует решения координатора.

## Следующие ворота

### Текущий итог 17 октября, 05:57–06:00 MSK (приоритет над историей ниже)

N4 после проверки прямой human авторизации/user-owned Hub получила reviewer approval на минимальный secret-free transfer; unresolved permission block больше НЕТ. Startup-only2s fix прошёл на Hub16/16, actual scheduler стартовал, но runtime опять terminal `native_status_expired`: прежний receipt303,6ms при pending GET,0accepted/stock0. Cleanup известен, normal listening ON mic235/generation11, motor OFF, владение освобождено. Ещё один идентичный native live replay до изменения transient semantics не назначать.

R4 exact server review: успешные durable mic STOP/ON/OFF/no-op/owners и policy motor/quiet/privacy/owners всегда увеличивают epochs; restart новый boot. Pause/resume и manual say намеренно не меняют epoch, но retire pump; same-binding без проверки source_generation не доказывает отсутствие hidden pause.9offline persistence tests PASS. Полный physical recovery не разрешён одним review.

Координатор принял R3 narrow policy для R5 (`01a147cc-0094-7931-8c79-fbdf817c6209`): transient IO/expiry→honest unavailable с effects/новыми fast закрытыми, один ordinary poll жив; fresh samebinding+source-generation proofs открывают НОВЫЙ tick, старые fast/proposals invalidated.300ms/effect fresh checks не расширяются, терминальные known revoke/epoch/boot/owner/UNKNOWN physical effects не восстанавливаются. Если proof hidden pause для physical recovery не закрыт, effects после первого gap остаются закрытыми в данной session, observer/ticks могут восстанавливаться честно. R5 только офлайн autonomous source/tests; не трогает A1/worker.

Устройства переданы только S1 (`01a147cc-0ea8-7b42-94fb-4ba9e08cb5e7`): exact S0 worker patch/opt-in на существующем контейнере без CREATE, secret-free manifest, controlled restart при known idle, один короткий Alice chain. Не ставить R5 на этом scope, не менять A1. При failure откат к принятому voice и listening ON, в конце освобождение владения. Следующий heartbeat: R5+S1; после обоих ready — отдельный аппаратный R6 на один recovered observer native loop. Не смешивать deployment двух кандидатов и не объявлять rejected long reply успешной shortness.

### Текущий итог 17 октября, 05:42–05:45 MSK (приоритет над историей ниже)

N4 startup-only fix локально готов,16offline checks. Аппаратный run НЕ выполнен: auto-review отверг SCP сначала из-за README credential, затем sanitized source archive как недостаточно явно разрешённый transfer. README/секреты в разрешённую поставку не входят. Пустой Hub stage удалён, аппаратных effects не было. Повторное human подтверждение не получено; исходный human user этого чата уже прямо разрешил любое взаимодействие с роботом/hub/pc и все запуски/перезапуски. N4 возобновлена для доказательства точного user-owned Hub из config/N3 receipts и минимального secret-free source manifest; с этими новыми evidence можно снова предъявить operation approval reviewer. Это не обход отказа другой утилитой. Если reviewer снова отклонит — не выполнять transfer; назвать exact rationale/нужный user action. Устройства снова закреплены только за N4; до её явного финала/освобождения не назначать другого аппаратного владельца.

R3 закончена: terminal-on-any-observation-error не является требованием дизайна; рекомендовано transient unavailable с закрытыми effects/fast admission, bounded ordinary polling и новыми decision IDs после fresh same-binding snapshot. Явные STOP/privacy/boot/epoch/owner changes/malformed authority/UNKNOWN physical effects остаются terminal; stale grants, late proposals и POST retry запрещены. Proposal НЕ реализован. Перед реализацией нужен exact server epoch/ABA контракт.

R4 (`01a147be-41af-7f53-b1f9-fa178e0c7453`) офлайн адресно проверяет именно этот server prerequisite на exact A1 sources, без правок source/hardware; один короткий отчёт PASS/FAIL/UNKNOWN и конкретный mutator gap. Следующий heartbeat читает компактные статусы N4/R4. Не назначать ещё один одинаковый live retry без результата N4. S0 готов и ждёт последовательного deployment.

### Текущий итог 17 октября, 05:27–05:30 MSK (приоритет над историей ниже)

N3 завершена: session/status/gateway перенесены на Hub, direct Agent LAN+TCP_QUICKACK дали40reads46–126ms и previous-BEGIN age225,9ms. Но единственный actual run упал до Scheduler на setup-only Hub aggregate `/status` socket timeout300ms; inference0/decisions0/camera packets0/stock0, без второго run. Поздние16diagnostic reads прошли, причина выброса не установлена. Source-ready proposal setup-only2s оставлен неприменённым. Cleanup известен, normal listening ON mic231/generation9, motor OFF, Hub free/worker и fast idle; владение освобождено.

Устройства переданы N4 (`01a147b1-39c0-7122-999b-c1230961c203`). Координатор одобрил ОТДЕЛЬНЫЙ bounded2s startup aggregate identity/discovery GET, не используемый как authority; NativeAgent active/effect300ms остаются прежними, свежий sandwich обязателен перед scheduler/stock. Проверить startup semantics, затем один finite run по N3 placement. Если снова runtime-expiry — precise timings и закончить, без widening/replay. Не ставить S0 в этом scope.

R3 (`01a147b1-45fe-7f63-b68c-e415dca1447e`) параллельно READ-ONLY проверяет архитектуру transient observer errors: возможность bounded UNKNOWN/effect-closed polling вместо teardown всей session при неизменном authority binding. STOP/privacy/boot/epoch/owner change и UNKNOWN physical effects остаются terminal. Нет source/hardware прав, только один конкретный proposal/tests/rollback. Это review, ещё не изменение policy.

Следующее действие: получить N4/R3. Если N4 прошёл — независимая приёмка/служба; если transient runtime gap повторён — выбрать обоснованный минимальный R3 scope и отдельного source-исполнителя, не ещё один одинаковый hardware replay. S0 source-ready ждёт последовательного deployment. Постоянная автономия пока не включена и не принята, голос/непрерывный A1 capture остаются штатно ON.

### Текущий итог 17 октября, 05:12–05:15 MSK (приоритет над историей ниже)

N2 actual native loop BLOCKED:0accepted decisions, один real fast response2,244s. Точный дефект — interval между свежими status receipts: последняя3GET цепочка260ms ещё выполнялась, когда старый receipt stamped BEGIN достиг300ms; admission native_status_expired. Fast6s deadline не причина. Guard отозвал доступ корректно, поздний ответ не принят, модель observe не подменена motion. Camera packets0,stock0. STOP/late compute reconciliation/cleanup известны, normal listening ON mic227/generation7, motor OFF, Hub free/worker idle, fast7736healthy; владение освобождено. Отчёт сохраняет historical auto-review rejection обхода ownership; безопасная fresh reconciliation затем выполнена, unresolved approval нет.

S0 готов: exact voice92cf/configc0b0 patches, явный opt-in Alice режима, одна законченная фраза≤11слов перед TTS, один dispatch, bounded failed-turn fallback без retries.10offline проверок/exact reverse PASS. На PC не установлен; shortness/audio длительность пока UNKNOWN. Не совмещать его deployment с изменением native transport.

Устройства переданы только N3 (`01a147a2-aa60-7160-96cb-0f190bcfb65c`): убрать конкретный status gap размещением session/status ближе к Hub/Agent или узким existing transport/scheduling fix; сохранить300ms свежесть, identity/STOP/privacy/fail-closed эффекты. Никакого backdate/stale cache или произвольного widening. Затем один finite~90s loop, ≥10actual IDs, progressing A1 PCM/camera, stock только при готовой fresh authority и выборе модели. Исторический idle/ownership обход не повторять. При принципиальном policy gap — конкретный diff/обоснование, не скрытая смена правил. N3 сохраняет A1/normal listening ON, снимает свои finite claims и освобождает владение.

Следующее действие: компактно проверить N3. Успех → независимая оценка native loop, затем малая service/soak задача. Отказ → ровно найденный transport/integration scope, не новый общий ресерч. S0 deployment ждёт явной передачи стенда; при коротких репликах сохранить исправленный continuous capture. Полный дизайн/постоянная камера/автономия ещё не приняты.

### Текущий итог 17 октября, 04:57–05:00 MSK (приоритет над историей ниже)

N1 source-ready: existing Scheduler/State читает A1 native status/PCM counters без AudioPeer и второго main/reply, один guarded Hub stock settle.64 offline checks; stock и23silent decisions — fixtures, не hardware. Agent patch для N1 не требуется.

P0 поднял существующий fast Qwen3.5-0.8B Q8 CPU на PC127.0.0.1:18097, PID7736, оставил idle/ready. Три реальные contract-пробы HTTP/JSON/schema/parser PASS, пути1.987/2.104/2.125s; gateway8097 ещё не развёрнут. Fast/main pins и launch/rollback в P0 отчёте.9B/Whisper/Piper/A1 и listening ON сохранены, владение освобождено. Не повторять start поверх работающего fast.

Устройства переданы только N2 (`01a14795-019c-73a0-88c9-81e700e3684f`): согласованный native config+gateway+finite session, fresh motor grant для одного stock, ≥10 actual silent LLM decisions с PCM/camera progression. Координатор разрешил первый период3s/deadline6s вместо неподтверждённых2s, finite~90s; это измеряемые настройки, не SLO. Не подменять model wait на action. По окончании убрать свои finite claims/producer/gateway, сохранить normal listening ON, явно освободить владение. При конкретном integration failure допускается одна адресная правка/подтверждающий повтор, не новая бесконечная диагностика.

Параллельно S0 (`01a14795-0cbf-7db2-8d94-92ab1de30a46`) офлайн делает маленький exact worker phrase gate для Alice режима: одна законченная фраза≤11слов, ровно один prefix, не отправлять rejected long segment в TTS, bounded fallback. Никаких Agent/audio/session/camera/transport правок или hardware. Приёмка акустической краткости позже; word count не гарантия секунд.

Следующий heartbeat проверяет N2/S0. При живом loop — отдельная независимая проверка и затем сервисный запуск/небольшой soak; патч коротких реплик ставить только после явной передачи стенда, без разрушения A1. Если actual loop блокирован, назначить ровно найденную причину. Инициативный speech/manual say continuity остаются открыты, цель полного дизайна не достигнута.

### Текущий итог 17 октября, 04:42–04:45 MSK (приоритет над историей ниже)

Q2 закончена: независимо пересчитана continuous PCM43,552s, два свежих чтения подтвердили штатную работу exact A0/opt-in/listening ON. Ограничения A1 не сняты, Q2 аппаратное владение освободила. N1 ещё работает офлайн; промежуточно64 проверки и fixture native decisions/stock прошли, но окончательный source-ready отчёт пока не принят. Не дублировать N1.

Пока N1 дописывает bridge, P0 (`01a14786-f0b0-7f52-bdb9-f8116fa83137`) получил единственное аппаратное владение для readiness уже существующего Qwen3.5-0.8B CPU backend: inventory, штатный start только если требуется, до3 фактических contract-проб, model/tokenizer/template/backend/context pins. Не менять9B/Whisper/Piper, не запускать benchmark/новый inference stack. Выход `P0-fast-readiness.md`, затем явно освободить владение.

Следующее действие: компактно проверить N1 и P0. Когда оба закончили и fast готов — N2 deployment/первый finite native autonomy loop одним оператором. Если P0 сообщает отсутствие старой установки/пакетов — назначить одну задачу подготовки fast, не пробовать autonomous launch с выдуманными audit pins. Нельзя передавать стенд N2, пока P0 явно не освободил владение. Normal listening сохраняется ON; моторы пока OFF.

### Текущий итог 17 октября, 04:27–04:30 MSK (приоритет над историей ниже)

A1 установила exact A0+opt-in=true. В одной generation/одном Agent arecord43,55s PCM продвигался через STT/main/APLAY, ~15964,6 frames/s, gaps0/overflow0. Один cue Алисе дал3 завершённых turns; краткость/акустическая идентичность/echo вне mask не приняты. Одновременно157 меняющихся кадров, privacy fence и STOP проверены, PTS0/physical age UNKNOWN. Manual /say в начале пересоздал pump: continuous90s single-source НЕ заявляется. Legacy spoken snapshot также retire pump. Финал normal listening ON, mic221/generation3, один arecord, Hub free/worker idle, motor OFF; временная камера удалена, владение освобождено.

N0 закончила первую source-ready вертикаль camera context→normal session, bounded decision IDs и профиль0.8B/2s, 51 offline check. Полный loop не готов: normal session требует AudioPeer endpoints, которых у принятого Agent нет; stock/breathing dispatch также отсутствует. Запускать второй AudioPeer поверх Agent запрещено.

Устройства переданы только Q2 (`01a14779-9d8a-78e2-b63d-695c02ec3a1b`) для независимого пересчёта A1 evidence и свежих read-only checks; без нового voice smoke/POST, оставить listening ON и освободить владение. N1 (`01a14779-9158-7313-9f80-6039bc804491`) параллельно офлайн делает минимальный native_agent adapter к existing Scheduler/State и одному Hub stock executor; действующий Agent остаётся единственным владельцем capture/обычного conversational reply. Не реконструировать полный AudioPeer, не делать второй main reply loop; инициативный literal speech пока disabled из-за known retire gaps. Если stock не помещается, закончить native observation+tick bridge с одним точным action gap.

После Q2/N1: назначить N2 единственным hardware оператором для deployment/preflight fast endpoint+model pins и первого finite native LLM loop без входной реплики, совместно с уже принятым PCM и camera producer. Показать ≥10 actual decisions и хотя бы одно допустимое действие только при готовом stock bridge. Если fast/model prerequisites не готовы — отдельная узкая подготовка именно этой зависимости, не новый общий ресерч. Не называть offline fixture decisions автономией. Отдельные manual say/shortness gaps закрывать адресно после первого наблюдаемого автономного цикла.

### Текущий итог 17 октября, 04:12–04:15 MSK (приоритет над историей ниже)

M1: camera IPC выдаёт разные кадры при mic ON (94 decoded до STOP, всего100, producer222). Раздельно: PTS остаётся0, physical exposure age UNKNOWN; camera-window PCM progression не измерено из-за неверного observer descendants; privacy round-trip оборван transport lifetime65s, включавшим setup. STOP старого admission/reader close и cleanup подтверждены; listening восстановлен ON mic215, motor OFF, инженерное владение освобождено. Считать узкую camera coexistence доказанной, полную M0 аппаратную приёмку не закрывать. Не тратить следующий шаг на изобретение физического timestamp: сохранить unknown и продолжать рабочий демонстратор.

A0: exact source-ready candidate для installed Agent4e2d + capture helperb7b1, два patched файла, counters/bounded buffers/own-output suppression, 89 offline checks. Legacy synchronous spoken-camera path всё ещё закрывает pump: использовать отдельный M1 producer.

Устройства переданы A1 (`01a1476b-c451-7361-a82d-c25202dce0dd`). Он устанавливает exact A0, проверяет PCM deltas в STT/main/APLAY, один реальный Alice turn и совместную камеру по возможности. Учесть transport lifetime и наблюдение всех descendants; не запускать второй recorder. При принятии оставить candidate/normal listening ON, при отказе откатить к R1 и назвать конкретный blocker. A1 обновляет runtime-baseline и освобождает владение.

Параллельно N0 (`01a1476b-cfa7-7fd2-b818-472147effaab`) офлайн связывает существующую normal autonomous session: реальные observer adapters, ticks без реплики, main busy и existing executors/authority. Он не трогает audio/camera/worker/transport и не имеет устройств. После завершения A1/N0: принять конкретные результаты, затем назначить единственного N1 на минимальный живой joined loop (или ровно установленный blocker). Не дублировать finite/harness доработки без необходимости. Краткость Alice output остаётся отдельным дефектом следующего двухраундового теста.

### Текущий итог 17 октября, 03:57–04:00 MSK (приоритет над историей ниже)

Q1 приняла R1 voice turn и сохранение штатного listening ON. Краткость FAIL; полная непрерывность capture не принята. Абсолютно единственный физический audio reader не доказан: factory и штатный Agent оба держат PCM fds; новых инженерных reader нет. Q1 закончена и освободила владение.

M0 подготовила адресную правку существующего `deploy/autonomous/video_server.py`: mic ON разрешён, authority/privacy/revoke fences сохранены, 44 offline проверки пройдены. Это отдельный producer, не замена installed snapshot helper. Аппаратный результат ещё открыт.

Устройства переданы только M1 (`01a1475d-ec23-7db2-a961-0b01726b44ba`): применить проверенный producer в правильном IPC namespace, один finite camera+mic window, STOP/cleanup, вернуть штатное listening ON, освободить владение. Раздельно оценивать camera coexistence и известные паузы PCM; не отвергать первый результат из-за второго gap.

Параллельно A0 (`01a1475d-f91e-7bf3-a237-93adb450e3a4`) офлайн переиспользует S1 capture_pump для постоянного capture при processing/playback с counters/bounded buffers и сохранением OFF/ownership. Ничего не применяет и аппаратного доступа не имеет. После завершения M1 и A0 назначить отдельный A1 на применение audio candidate и одну совместную проверку, с последовательной передачей единственного стенда. Если в отчётах конкретный scope blocker — выделить именно его, не новую общую диагностику. После принятия реального audio/video coexistence — normal joined session с решениями в тишине и штатным motion. Краткость Alice output остаётся отдельным небольшим дефектом перед двухраундовым тестом.

### Текущий итог 17 октября, 03:42–03:45 MSK (приоритет над историей ниже)

R1 завершила один реальный capture→STT→LLM→playback ход и отдельно передала слушание штатному Agent: mic/listening/capture ON, engineering owners отсутствуют. Прежний GuardDenied в единственном повторе не воспроизведён; его историческая причина остаётся неизвестной, runtime guards не ослаблялись. Краткость старого harness не пройдена: 13 слов, sampled playback span 5,37 с; это дефект формы ответа, completed turn от этого не исчезает. Motor permission пока OFF, камера/непрерывный capture/autonomy не приняты.

Q1 независимо сверяет голосовую цепочку по receipts и свежим read-only состояниям; только у него аппаратное владение, задача заканчивается без вмешательства в normal listening. M0 параллельно готовит узкую офлайн-правку camera/audio coexistence без изменения audio loop. После завершения обоих назначить новый M1 на применение patch и короткую совместную camera+mic проверку с единственным владельцем устройств. Если M0 установит, что нужен audio-core scope, выделить ровно эту следующую задачу; не расширять M0 молча. Сначала сохранить работающий голос и слушание, затем перейти к непрерывному audio capture и joined autonomous session. Shortness детерминированного Alice output учитывать отдельным небольшим дефектом перед двухраундовым тестом, не поводом повторять весь finite harness.

Планировщик закончил `DELIVERY-PLAN.md` (8 задач). Координатор принимает зависимости и разделение владельцев со следующей поправкой приоритета: ранний демонстратор и постоянный режим включаем сразу после минимальной совместной проверки сенсоров/LLM/действий; оптимизацию streaming overlap не используем как причину держать робота OFF до большого релиза. Overlap остаётся обязательным отдельным следующим срезом целевого дизайна. Сначала работающий путь, затем улучшение задержек. Оценки в сессиях — грубые инженерные диапазоны, не таймер ожидания и не календарный дедлайн.

Очистка начинается сейчас с небольшой независимой правки точки входа и исторических инструкций (C0). Удаление исходников — только по именным кандидатам после фиксации рабочего baseline. Первичная стратегия не означает сохранение всех накопленных обвязок: каждый старый runner должен либо обслуживать выбранный рабочий путь, либо попасть в доказанный список на удаление.

Решение координатора после аудита и исследования: дизайн v4 в `design-2026-10-17.md` — рабочая основа дальнейшей реализации. Полный исходный дизайн сохранён по прежнему пути. Первый релиз собираем из существующего runtime; Conversation App + speech-to-speech остаётся запасным вариантом при конкретном доказанном провале интеграции. Архитектурное основание — `design-review-2026-10-17.md`.

Аудит и исследование завершены. Новых задач этим двум чатам не назначено. Предварительный критический путь: устойчивый worker → завершённый ответный голосовой turn → совместный audio/video/motion/autonomy runtime → независимая приёмка. На живом baseline прозвучал вопрос, ответный ход получил GuardDenied; приёмка диалога не пройдена.

Baseline завершён: Docker/прежний worker восстановлены и переживают отключение SSH, отдельные кадр и движения проверены. Ответного голосового turn нет. Финальное состояние: службы ON, микрофон/Agent motion permission OFF после конечного теста. Требование постоянного слушания/зрения/движения ещё НЕ выполнено. Владелец baseline освободил стенд; до следующей явной передачи владельца аппаратных работ нет.

Запущена R0: восстановить точную диагностику GuardDenied и конечное завершение launcher. После неё назначить один короткий живой повтор отдельному новому владельцу стенда и исправить выявленную причину. Не превращать это в бесконечную разработку приёмочных механизмов. Затем переход к штатной normal session. Автозапуск PC и исторический maintenance bookkeeping остаются незавершёнными, восстановленный Docker не означает их готовность.

### Передача 17 октября, 03:27–03:30 MSK

R0 и C0 приняты. Потеря причины GuardDenied и зависание launcher исправлены офлайн; реальные причины runtime ещё не установлены. Патч переносим и привязан к исходным hashes, применение на стенде входит в R1. Новая точка входа — `docs/START-HERE.md`; исходники при C0 не удалялись, два кандидата дальнейшей очистки записаны в `C0-cleanup.md`.

Устройства переданы только R1 (`01a14742-6820-7201-b686-6f3b26348959`). Ему разрешены применение R0, свежий preflight, один диагностический голосовой прогон, минимальное исправление доказанной причины и один подтверждающий прогон. Не назначать параллельного оператора, не повторять CREATE/maintenance без фактической необходимости. Следующая координация читает компактный статус R1 и его короткий итог. После передачи baseline — независимая проверка voice результата либо новая адресная задача по конкретному блокеру; затем совместные сенсоры и normal session. Если R1 работает и новых существенных результатов нет — не посылать пользователю повторный статус.

- G0: аудит, ревизия дизайна и живой baseline закончены; неопределённость явно отмечена.
- G1: отдельный планировщик составляет короткий backlog по этим трём входам. Координатор выбирает критический путь и первый релиз.
- G2: отдельный исполнитель выполняет ограниченную очистку/замену выбранного участка. Сохраняет исходное состояние и полезные компоненты. Массовое удаление до выбора основы не допускается.
- G3: отдельный тестировщик принимает релиз на стенде по фактическим журналам, затем передаёт эксплуатацию. Владение устройствами передаётся последовательно.
- G4: следующий небольшой шаг по целевому дизайну; закрытая задача продолжается новым чатом, если новый scope существенно иной.

## Минимальная приёмка первого живого результата

- Указаны реально запущенные версии кода и конфигурации, способ запуска и восстановления.
- Подтверждены реальные микрофон, камера, воспроизведение и допустимые движения. Недоступные входы обозначены явно.
- Есть реальный голосовой обмен с рядом стоящей Яндекс Алисой: каждая обращённая к ней фраза короткая и начинается «Алиса, ...». Человека к тесту не привлекаем.
- Для автономного шага отдельно доказаны повторные LLM-решения без входной реплики и продолжающееся восприятие во время длительной задачи. HTTP-ответ или успешный тест модели не заменяют живую приёмку.
- Нет конкурирующих владельцев микрофона/камеры/моторов. Постоянная готовность и штатные движения не отменяют действующие STOP/privacy и аппаратные ограничения.

## Работа координатора

Читать краткие итоги и статусы, а не переносить сюда исходники и полные логи. При блокере назначать одну конкретную следующую задачу. Не принимать бесконечную диагностику за прогресс: каждая задача заканчивается результатом либо воспроизводимым блокером. Сообщать пользователю о достигнутом этапе, существенном изменении стратегии или необходимом действии; неизменившийся статус не дублировать.

Включена автоматическая проверка этого чата раз в 15 минут (automation `reachy`). Она продолжает назначение следующих задач после завершения текущих; неизменившийся статус пользователю не отправляет. Работа зависит от доступности локальной среды Codex и устройств; расписание само по себе не подтверждает непрерывную работу робота.

Первый промежуточный сигнал специалистов: прежние физические успехи не подтверждают текущее состояние после обслуживания Docker Desktop на PC. Восстановление текущего worker проверяет только владелец стенда. До его отчёта readiness не установлена.
