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
| Spoken snapshot | `02bdaa2` установлен: минимальный Agent overlay и два helper-файла, один restart; readiness/source/config/state проверки прошли | **FAIL на реальном запросе:** child запущен, затем generic snapshot child failed; обычные фразы работают. Причина неизвестна, vision/context PASS не заявлен |
| Состояние после сбоя | Независимый watch подтвердил OFF, admission retired, factory empty, no aplay, stock known, volume 100%; активные сессии завершены | Поздний wrapper/client cleanup error после отзыва authority учитывать отдельно от исходного child failure |
| Потоковый диалог | Есть NDJSON transport, PCM chunks, TTS сегменты, barge-in/AEC и STOP | **Не реализован настоящий token streaming ответа:** содержательный ответ ожидается целиком до TTS. ACK не является первым содержательным ответом |
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
| P0.1 | В работе: диагностика `51f3e2c` установлена по подтверждению координатора; child cause UNKNOWN | Диагностировать и исправить selective STT-camera failure, сохранив рабочие explicit vision и ordinary voice | writer: helper diagnostic/точечный fix; reviewer + координатор: review; runner: единственные device actions | Ожидается реальный allowlisted phase/error_class, затем доказанная причина и минимальный fix. После этого real spoken intent → fresh frame → human-correct spoken FINAL, owned aplay/stock motion; отдельный STOP/no resume/final OFF100 |
| P0.2 | Actual PC SSE/prefix PASS; timely-reader реализован локально, voice rollout готовится | Настоящее потоковое слушание и содержательный ответ до полной генерации | writer: existing capture/STT/brains/voice seams; runner: реальная запись timings и STOP; координатор: критерии | Один timely reader, bounded queue, DISCARD того же запроса до исходного deadline, общий lease до terminal + consumer cleanup. Предстоит реальный длинный ответ/STOP/следующий turn и повторяемая команда входа в проверенный режим. Continuous perception/partial STT/endpointing — отдельный следующий seam, ещё не реализован |
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

## P0.1: ближайший шаг после фактического сбоя

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
epochs. Нужен только matching Hub client file, без Agent/worker restart. После
source review runner выполняет один исправленный конечный метод с новым fresh
watch; publication/source checks не заменяют реально выполненный diagnostic.

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
