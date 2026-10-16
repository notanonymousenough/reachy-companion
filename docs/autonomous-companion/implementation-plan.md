# Живой план реализации companion — v3

Обновлено 2026-10-16. Владелец плана — координатор Reachy Mini; writer ведёт код,
проверки и этот документ; единственный runner выполняет изменения и проверки на
Reachy, Hub, PC и VPS. Независимый reviewer проверяет исходники и доказательства.
Это план доведения продукта до конечной цели, а не отчёт о завершённом demo.
После каждого реального результата обновляются статус, доказательство и следующий
шаг. Неизвестное остаётся неизвестным; счётчик turns и успешный HTTP не заменяют
содержательную, физическую или акустическую приёмку.

## Фактическое состояние

| Область | Подтверждено | Открыто / следующее доказательство |
|---|---|---|
| Обычный голос | Реальные STT → локальная модель → TTS/owned aplay работают; реальные фразы получают ответы | Полная приёмка контекста с точным распознаванием факта и последующей ссылкой на него ещё открыта; два turns в неудачном vision-прогоне этого не доказывают |
| Explicit snapshot | `d47f361`: свежий снимок → локальная 9B → полный spoken FINAL; человек подтвердил верность описания; наблюдались owned aplay, SDK tasks и движение антенн | Это отдельный командный путь `--vision`, не успешный голосовой запрос и не визуальная память |
| STOP и cleanup explicit snapshot | Отдельный реальный STOP во время owned aplay: наблюдаемый cleanup 0,216848 s; три последующих проверки за 2 s без возобновления; известные OFF, factory empty, no aplay, 100% | Это одно наблюдение конкретного пути, не P95, не полная физическая/акустическая задержка остановки |
| Spoken snapshot | **РЕАЛЬНО РАБОТАЕТ:** после socket-only fix `7799e89` один human visual-запрос завершился успешно; человек подтвердил верность названия и описания. Exact visual STT, один turn без ошибки, CLI rc0 и независимый cleanup подтверждены | Это приёмка голосового camera → spoken description пути. Visual memory, latency target, streaming, отдельный STOP/motion прогон этим результатом не приняты; observer не дал terminal returned |
| Prime-paused diagnostic | `73c241b`: Hub client обновлён без restart; в одном исправленном реальном прогоне cue выполнен при закрытом capture, затем подтверждены resume и свежий захват | **NOT_EXERCISED для камеры:** точный visual intent в STT отсутствовал, child не запускался. Один completed turn не доказывает vision/context. Повтора Alice vision не планируется |
| Состояние после сбоя | Для предыдущих принятых окон подтверждены OFF/factory free/no aplay/100%; последний `1e2d91c` CLI сообщил cleanup true | Текущий PC baseline ещё не восстановлен; единственный runner классифицирует исход и выполняет scoped recovery. Не переносить подтверждения прошлых окон на текущий результат |
| Потоковый диалог | В предыдущем прогоне подтверждены содержательное начало ответа и owned STOP/cleanup; overlap condition не выполнен. Source `1e2d91c` прошёл 40 проверок и paired consumer fixtures | **Новый единственный `1e2d91c` trial: hardware voice NOT EXERCISED — человек подтвердил, что не успел произнести запрос.** EXIT2/completed0/CLI cleanup true; schema error нет, PC recovery ещё не завершён. Runner выполняет classification и scoped recovery, новых trial/runtime patches нет |
| Задержка vision | Два реальных image inference заняли около 11,03 и 10,35 s | Уже один inference превышает цель 10 s; полный speech-end → meaningful audio не измерен. Не объявлять цель достигнутой |
| Память | Обычная RAM session history существует | Snapshot `/say` не добавляет visual question/answer в worker history; долговременная память и continuity через restart не приняты |
| Полная автономность | Есть реализованные contracts, guards, fixtures и отдельные реальные checkpoints | Непрерывное восприятие/решения, память, полезные интеграции, recovery и длительная реальная приёмка ещё не завершены |

Реальные receipts и операционные идентификаторы хранятся в приватном runner
каталоге. В Git идут код, публичные runbook, тесты и этот план; без конфигов,
секретов, raw audio/images и приватного operational handoff. Текущая рабочая
громкость — 100%, сохраняется стартовое операторское значение, не старые 50%.

## Очередь поставки и владельцы

| Порядок | Статус | Минимальный результат | Владелец | Реальная приёмка и доказательство |
|---|---|---|---|---|
| P0.1 | **Spoken camera PASS для одного реального human-запроса:** socket-only fix установлен, описание подтверждено человеком, финальный cleanup проверен | Сохранить принятый camera voice path и воспроизводимый `7799e89` fix | writer: public fix/план; runner: единственные device actions; координатор: следующая приёмка | Следующий приоритет — P0.2. Отдельные camera STOP/motion/no-resume и visual follow-up memory остаются открыты; один корректный spoken ответ их не заменяет |
| P0.2 | Source `1e2d91c` принят; actual hardware voice NOT EXERCISED — запрос не прозвучал; EXIT2/completed0, schema error нет; PC recovery в работе | Сначала восстановить baseline; затем синхронизировать начало человеческой фразы с фактическим capture window | runner: единственный активный device owner, read-only classification/scoped recovery; writer: план и fix только по causal evidence; координатор: следующий шаг | Не повторять trial и не менять runtime по догадке. Нужны whole-boot proof, точная причина failed FIRSTSTOP/recovery guard и подтверждённый baseline; затем реальные meaningful overlap/STOP/next-turn критерии |
| P1.1 | Частично, не принято | Обычный контекст, затем visual context с provenance/TTL; долговременные факты и исправления | writer: существующие session/memory seams; runner + человек: смысловая проверка | Факт → vision → местоименная ссылка на прежний факт; отдельно visual follow-up из реально виденного. Restart сохраняет разрешённые факты/mute, correction/deletion работает; vision history не обещать до реализации |
| P1.2 | Не принято | Первая полезная typed integration через существующий broker/worker | writer: маленький adapter/schema; runner: настоящий target; координатор: scope | Реальная полезная задача с intended/attempted/completed receipt; ошибки/timeout/duplicate/cancel различимы. Нет raw shell/секретов/новых grants из текста модели или OCR |
| P1.3 | Частично guards есть, полная приёмка открыта | Recovery, ресурсы, STOP, воспроизводимая доставка Git/transfer | writer + reviewer; runner: actual failures/recovery | Сеть/worker/model/restart/перегрузка не оживляют старые речь/движения. Bounded queues/VRAM/storage, сохранившиеся mute/volume, exact source hashes, конечный deploy/readiness/rollback без конкурирующих владельцев |
| Final | Не принято | Постоянно доступный автономный companion: слышит/видит, отвечает по ходу генерации, помнит, полезно действует и естественно сопровождает речь движениями | координатор сводит результаты; все реальные действия через runner | Длительные реальные silence/mixed/overlap/outage/restart сценарии, все product criteria ниже. Demo или отдельный PASS не заменяют конечную цель |

Параллельно допустимы только независимые локальные source review и подготовка.
На устройствах — один runner и один согласованный этап; не накладывать latency
patch, новый dispatcher и model/runtime migration на активный acceptance run.
Общие разрешения пользователя на устройства уже получены; не создавать новые
общие approval-пакеты. Текущие STOP/mute/quiet/privacy и более новый owner имеют
приоритет над любым планом. Точечная диагностика не должна запускать новый снимок
или inference автоматически.

## P0.1: причина сбоя и принятый spoken camera путь

Ниже сохранена цепочка диагностики; актуальный принятый результат и пределы
доказательства описаны после неё. Старые installation шаги повторно не выполняются.

1. Сохранить known OFF/100 и исходные private receipts. Различать child cause,
   последующий withdrawal authority и wrapper cleanup: это разные события.
2. Минимальная helper-only диагностика: фиксированные phase/error_class до rc,
   без message/trace/body/text/image/token. Исходники Agent и shared camera не
   менять. Один restart Agent нужен для обновления уже импортированного helper;
   копирования файла недостаточно из-за `sys.modules`.
3. После source review установить только exact helper через runner, проверить
   readiness и неизменность config/persisted states/volume/factory. Диагностическая
   установка сама не запускает камеру. Runbook:
   [spoken-vision-child-diagnostics.md](../../deploy/patches/spoken-vision-child-diagnostics.md).
   Этот diagnostic checkpoint `51f3e2c` уже установлен по сообщению координатора;
   причина исходного сбоя по-прежнему неизвестна, новый снимок автоматически не запускается.
4. По bounded evidence установить конкретную причину. Не угадывать IP/model
   alias/SDK flag и не заменять работающий stack. Исправить только доказанный seam.
5. Реальный spoken camera acceptance и ordinary context continuity; затем STOP
   во время ответа и no resume. Лишь после этого статус этого маршрута PASS.

Дополнительный Alice diagnostic был **NOT_EXERCISED**: обычный demo сначала
открывал listening, поэтому concurrent controller получил GuardDenied до pause
и до cue. Это не новая причина исходного camera-child сбоя и не вывод о качестве
Алисы. Минимальный `--prime-paused` оставляет первый same-owner/CAS ON grant с
`listen=false`; существующий guarded cue → direct `/resume` сохраняет исходные
epochs. Hub client `73c241b` уже установлен без Agent/worker/service restart.
По актуальному receipt координатора исправленный конечный прогон действительно
выполнил cue с capture closed и resume со свежим capture. Но STT exact visual
question = false и child = false: это **NOT_EXERCISED**, не новая диагностика
исходного child failure. Completed turn = 1 не является vision/context PASS.
Независимый cleanup подтвердил OFF/100%, factory empty и no aplay. Повтора
Alice vision не будет; следующая причина/правка требует новой реальной evidence.

Новый human camera-запрос на Agent289 **подтвердил маршрутизацию**:
STT непустой, точный visual intent, own echo false, action allowlisted и dispatch
attempted true. Установленная fixed-stage диагностика сузила отказ до
`capture_sample/ValueError` после camera.open. Exact SDK1.11 не содержит фонового
потребителя sample; переход на read() и увеличение ожидания не доказаны как fix.
Read-only actual проверка установила причину: `PrivateTmp=yes`, host/factory видят
один Unix camera IPC socket, а в mount namespace Agent этот путь отсутствует.
Подготовлен минимальный unit/drop-in `BindReadOnlyPaths` только для этого сокета,
с сохранением PrivateTmp и всех прежних ограничений:
[agent-camera-ipc-bind.md](../../deploy/patches/agent-camera-ipc-bind.md).
Fix `7799e89` **установлен и проверен на реальном запросе**. Сохранён
`PrivateTmp=yes`, socket-only bind read-only; host/factory/Agent видят один
текущий socket inode. Выполнен один Agent restart суммарно за установку и её
продолжение. Agent и диагностические helper-исходники остались неизменными.
После этого один bounded human-запрос завершился с CLI rc0 и cleanup true;
человек подтвердил, что предмет назван и описан верно. Независимая конечная
проверка подтвердила exact visual STT, один turn без last_error, OFF/unowned,
громкость 100%, factory running empty и отсутствие camera/aplay. Это реальная
приёмка **spoken camera description**, не только source/readiness PASS.

Ограничение доказательства: observer увидел dispatch, затем завершился с UNKNOWN
по guard; terminal `returned` он не зафиксировал. Не дописывать отсутствующие
булевы признаки или terminal outcome. Причинная цепочка приёмки — успешный CLI/cleanup,
конечные STT/turn/error признаки и непосредственное подтверждение человеком
услышанного корректного описания. Visual memory, ordinary context continuity,
streaming, latency target и отдельные motion/STOP показатели этим не доказаны.
Producer socket replacement требует fail-closed проверки и отдельного guarded
Agent refresh; широкого /tmp bind и auto media acquire нет.

Следующий P0 — настоящая streaming voice приёмка через существующие seams,
без расширения инфраструктуры. В предыдущем, до `1e2d91c`, реальном human-прогоне человек услышал
начало содержательного объяснения; owned STOP и cleanup подтверждены. На одном
PC clock first semantic = 0,868067 s, first PCM = 1,193608 s, last token READ =
1,087325 s, DONE READ = 1,087982 s; 54 chunks, terminal и producer quiesced true,
failed/overflow false. Воспроизведение наблюдалось после завершения модели:
**overlap condition NOT met** на этом коротком ответе, не общий отказ streaming.
STOP guard span 3,0287 s и cleanup 0,4509 s относятся к этому software-наблюдению,
не physical E2E/P95. Следующий turn не был принят: private consumer пропустил
из своего allowlist существующий boolean model_post_attempted. Это schema drift,
а не ошибка worker. После коррекции и quiescence исходный baseline/config
полностью восстановлены, slot пустой, Robot OFF/unowned/100%; камера сохранена.

Effective-config witness подтвердил default brevity и explicit detail exception;
распознанная просьба именно о восьми предложениях не сохранилась. Hard cap или
ошибка STT не доказаны. Подготовлен конкретный следующий opt-in инкремент: просьба
о подробности/числе предложений имеет приоритет над обычной краткостью, первое
предложение короткое, законченное и содержательное; затем запрошенное объяснение.
FIRST-segment timings отделяют Piper wait, SoX, cues и подготовку первого audio
события на одном PC clock; producer и private consumer используют один pinned
строгий parser/schema вместо отдельных allowlists:
[content-first-sentence-iteration.md](../../deploy/patches/content-first-sentence-iteration.md).
Это source checkpoint, не улучшенная реальная latency/overlap/next-turn приёмка.
Нет Agent/profile/model/budget изменений, нового owner или искусственного delay.
Старые stream boot/epoch pins не активируются.

После этого проведён **один реальный trial `1e2d91c`**, завершившийся EXIT2:
READY через 27,747 s, затем 75-секундное окно, completed=0, CLI cleanup true.
Это readiness/window длительности, не speech-end latency. Исходная проверка
FIRSTSTOP receipt не прошла; речь и STOP в этом trial не доказаны. Recovery guard
отклонил пустые metadata после advance epoch. Shared 31-field schema при этом
не дала ошибки: переносить на этот исход прежний allowlist bug нельзя.

Человек прямо подтвердил, что не успел произнести запрос. Классификация этого
окна: **hardware voice acceptance NOT EXERCISED**, запрос не прозвучал. Это не
новый доказанный producer/STT/prompt defect. Whole-boot proof остаётся частью
runner classification; отсутствующие telemetry/terminal признаки не дописываются.
Распознанная просьба о подробностях/числе предложений не установлена; не делать
из этого вывод об ошибке STT или качестве prompt.
40 public source checks и восемь paired consumer fixtures остаются source-only,
не реальной приёмкой streaming. Камера и Agent в этом trial не менялись;
принятый spoken camera результат сохраняется отдельно.

**Текущее состояние:** PC baseline ещё не восстановлен. Runner — единственный
активный device owner — выполняет read-only classification и scoped recovery.
Нового runtime patch и повторного trial нет. После recovery следующий
поведенческий шаг — синхронизация начала человеческой фразы с фактическим capture
window. Нового runtime source fix без evidence нет. Не объявлять restoration,
quiescence, READY_NEXT или product PASS заранее.

Реальный streaming rollout под `ad7c59b` завершился **lifecycle failure**, а не
голосовой приёмкой. На Docker Engine 29.7.2 / API 1.55 собственный candidate был
создан с `HostConfig.OomKillDisable=false`; после запуска inspect вернул `null`.
Остальные Config/HostConfig/mount/network поля совпали. Сырое сравнение HostConfig
отклонило candidate и мешало штатному recovery тем же способом. Причина
подтверждена actual receipts; это не ошибка token parser или наблюдение early audio.

Для того более раннего lifecycle failure отдельное восстановление исходного
worker и точного protected config было подтверждено; это не текущий recovery `1e2d91c`:
worker running/idle, исходные brains/voice загружены, `content_tokens=false`,
сохранён исходный inventory, candidate припаркован, pending slot пустой, OOM нет.
Robot сохранил текущий Agent, OFF/unowned, factory free и громкость 100%.
Нового streaming voice PASS нет. Public source fix `e86e54b` подготовил один
typed comparator для candidate validation и failure recovery, с исключением только literal
false→null после подтверждённого собственного старта на указанном Engine/API;
initial never-started creation требует raw false. Все остальные проверки остаются
точными. Public seam и issuer contract:
[content-stream-engine-oom-comparison.md](../../deploy/patches/content-stream-engine-oom-comparison.md).
После review и runner installation нужен новый конечный voice run.
Continuous hearing/partial STT остаётся следующим невыполненным seam.

## P0.2: source audit и настоящий потоковый диалог

Проверен exact установленный worker `voice.py` SHA256
`92cf69096fd6f08551a13a9c44d85fbbfc0470ca2f17315616691044018ab865`.
`Pipeline.stream()` запускает `answer` в future, может озвучить короткий ACK,
затем вызывает `future.result()` и только после полного результата передаёт
`prepare()` → semantic segments → `audio_events()`. Без ACK `prepare()` также
получает целый ответ. `brains.answer()` запрашивает `stream=False`. Поэтому
существующий NDJSON/PCM stream — поток аудиотранспорта после готового ответа,
а не streaming токенов локальной 9B. Это source finding, не latency measurement.

Подготовлен source checkpoint и следующий implemented reader:
[content-token-stream-source.md](../../deploy/patches/content-token-stream-source.md).
Текущий конечный rollout:
[content-token-stream-rollout.md](../../deploy/patches/content-token-stream-rollout.md).
Он накладывается на exact installed worker `92cf…` и brains `9c69…`, не на
полный HEAD worker. Brains preimage соответствует публичному `39dffa0f…`,
worker preimage — `2865db30…`; это разные pins. Добавляется общий для обычного
и streaming запроса admission guard только при явном opt-in.
Один PC-запрос подтвердил actual SSE schema/identity/stop+DONE и два смысловых
сегмента: first token READ 0,4917 s, first segment 1,19314 s, last delta READ
1,44435 s. Это не TTS и не real voice overlap. Новый reader не зависит от TTS:
на отмене очищает очередь и продолжает DISCARD того же response до исходного
deadline; для первого прогона явно 40 s, не 2 + 40 и не скрытая замена default240.
Общий guard снимается лишь после finish + DONE и consumer/Piper cleanup.
Transport error/deadline без terminal остаётся UNKNOWN, не timer reset.
Read-only effective-config witness от runner уже
подтвердил balanced/closed-think assistant prefix без экспорта prompt values;
это не гарантия отсутствия немаркированного reasoning. Локальный порядок генераторов не доказывает actual
generation/audio overlap. Agent и camera-helper этот source-инкремент не меняет.

Ближайший реальный P0.2 прогон — implemented token-reader/TTS на длинном ответе,
STOP и следующий turn. Список ниже описывает полное требование, а не gate на
начало реализации: continuous hearing/partial STT следует отдельным малым seam
после этого голосового инкремента. Когда готов camera diagnostic, его tiny fix
сохраняет приоритет; аппаратные окна не конкурируют.

Оставшиеся составляющие потокового диалога:

1. Переиспользовать текущий audio owner/capture/AEC и STT backend. Проверить
   реальные возможности partial STT и endpointing установленного backend;
   держать ограниченные rolling buffers/latest queues. Continuous listening
   означает продолжающееся восприятие во время inference и ответа; не второй
   конкурирующий ALSA capture и не ожидание нового полностью записанного WAV.
2. В существующем `brains` seam добавить bounded iterator FINAL-токенов от уже
   загруженной локальной 9B. Сначала проверить фактическую stream schema runtime;
   не выдумывать native events, reasoning-off или private flags. Reasoning/tool
   output не озвучивать, новый model load не нужен. Token/context budgets менять
   только по измерениям; 2048 vision tokens нельзя слепо уменьшать — ранее budget
   требовался для появления FINAL после reasoning.
3. В текущем worker собирать ограниченные завершённые смысловые сегменты по мере
   FINAL-токенов и сразу отправлять их существующему TTS/PCM transport. Очередь
   text/PCM bounded, backpressure и cancellation сквозные. Нельзя сначала ждать
   whole answer, а затем назвать его chunking потоковым ответом. Обращение,
   emotion/gesture markers и границы сегментов не должны дублироваться/озвучиваться.
4. Existing Agent playback, barge-in, STOP, stock speech-motion sync переиспользовать
   с тем же owner и boot/epochs. Отзыв отменяет старые tokens, text segments, PCM
   и cues; поздние chunks не восстанавливают действие. Echo собственного голоса
   и шум моторов не создают новый запрос. Interrupted/unknown consumption не
   превращать в «полностью услышанный ответ» или полную spoken memory.
5. На реальных Reachy/Hub/PC провести длинный ответ: meaningful playback начинается
   до last model token; затем перебивание и STOP в процессе генерации/озвучивания.
   Проверить отсутствие старого хвоста, лишних cues и самовозобновления, контекст
   следующего обращения, финальные OFF/100/factory known. Полный framework rewrite
   и новая инфраструктура для этого не нужны.

Для каждого attempt различать speech end, partial/final STT, first FINAL token,
first complete semantic segment, first TTS PCM, first actual meaningful playback,
last model token, stream done и STOP. Записывать только разрешённые метаданные,
count/versions и clocks. ACK, HTTP headers, первая запись в pipe и наличие aplay
не являются доказательством первого содержательного акустического воспроизведения.
Если доступна только software proxy — так её и назвать; actual consumption и E2E
остаются unknown. Часы разных хостов не вычитать без проверенной привязки.

Главные показатели: speech-end → first meaningful audio и соотношение first
meaningful playback < last model token на том же реальном attempt. Честно
разделять STT, model prefill/generation, TTS и transport; не складывать отдельные
P95 и не выдавать сумму за E2E P95. Цель задержки не подменять ACK или средним
только по успешным быстрым запросам.

## Память, интеграции и непрерывная работа

Обычная RAM history должна переживать vision-turn без reset. Visual memory
добавляется отдельно с источником, age/TTL, confidence и различием «видел тогда» /
«вижу сейчас». Долговременная память различает факт, inference и fiction,
поддерживает correction/deletion/provenance/rollback; политика/mute/owner не
меняются из memory. Core persona и инициативность настраиваются после стабильной
речи и памяти, без фиктивных ощущений, батареи или температуры.

Useful integrations вводятся по одной через существующие typed capabilities,
конечные budgets/timeouts и receipts. Длительная задача не блокирует восприятие,
STOP и новые обращения. Retry/dedupe/cancel не выполняют действие повторно.
Внешние сообщения/платные API/экспорт приватных данных требуют соответствующего
пользовательского scope; общий доступ к устройствам не публикует их секреты.
S3/VPS export — отдельная configured capability с retention/deletion, а не
предусловие для голоса, памяти или автономности.

Непрерывная decision/perception loop остаётся частью конечной цели: bounded
контекст и active/queued jobs, свежие sensor snapshots, явные gaps при недоступной
модели, отсутствие cached answer как нового decision. Медленный vision/tool не
должен останавливать perception/STOP/доступный decision lane. Ресурсные модели и
cadence допускаются только после actual CPU/GPU/VRAM/context измерения, без
непроверенной миграции уже работающей локальной 9B.

## Приёмка конечной цели

- На реальных устройствах непрерывные silence и mixed conversation/music/vision/
  tool сценарии; первоначальные длительности 30 и 60 минут конечны и отдельно
  отмечаются как planned/attempted/passed. Естественный покой без повторных ACK,
  случайных жестов и self conversation; отказ человека/quiet прекращает инициативу.
- Нормальный контекст, действительно виденная сцена, исправленный факт и continuity
  через restart; никакого обещания visual follow-up по отсутствующей history.
- Substantive streaming до завершения model generation, overlap/interruption,
  AEC/no echo и STOP на реальном длинном ответе. Синхронизация stock motion
  со speech и consumption подтверждена доступным физическим наблюдением;
  неподтверждённые cursor/pose/acoustic интервалы явно unknown.
- Mute/privacy-all/quiet, epoch fencing и единственный owner соблюдаются при
  outage, reconnect, restart и overload. Нет старого audio/action burst,
  spontaneous resume или fake factory restoration. STOP измеряется отдельно
  для кнопки, голоса, звука и движения; единичный cleanup не выдаётся за SLA.
- Реальная полезная integration, bounded память/очереди/VRAM/storage, доступность
  safety при hung task. Sensor disabled/stale/unsupported различимы; fake events
  и hallucinated tool success недопустимы.
- Доставленный Git checkpoint соответствует installed source hashes; config и
  секреты вне Git; конечный rollout/readiness/rollback воспроизводим. Финальное
  состояние и нерешённые ограничения отражены в этом плане и private receipts.

После каждого прогона координатор передаёт writer один конкретный outcome;
writer обновляет эту таблицу и следующий шаг. При сбое возвращаемся к доказанной
причине, сохраняя работающий checkpoint; не перезапускаем весь проект с research
или fixtures и не объявляем конечную цель выполненной по отдельному demo.
