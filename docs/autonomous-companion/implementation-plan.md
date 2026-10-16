# Живой план реализации companion — v3

Текущий steering 2026-10-17: прямое «продолжай достижение MVP» возобновляет работу
после music incident; OFF не является бессрочной остановкой задачи. Следующий
минимальный cfg delta — один короткий полезный factual question в автономной
беседе с Алисой,3–5 content words плюс автоматическое обращение; не генерировать
музыкальные/media/device/action команды, в том числе в форме вопроса. Explicit
details exception и max_tokens512 сохраняются. Это intent policy, не доказательство
семантической безопасности и не установленная причина прежнего incident.
После exact cfg/source review и fresh guards — один реальный короткий ход,
длительный короткий диалог, затем true streaming/continuous hearing и camera/IMU.
Новый STOP/mute/owner всегда приоритетен; historical OFF/ON receipts ниже не
заменяют свежего чтения. Existing sound classifier проверяется на уже разрешённом
живом input; fallback kind=speech/scores0 не является verified speech.

Factual intent profile уже реально установлен и effective/readiness проверены;
сохранён max512, PC source/image прежние, новая history epoch отражена явно.
Обнаружена отдельная admission race: в installed cf50 pause/resume игнорировали
body, поэтому predispatch guard не являлся server-side binding. Подготовлен
exact cf50→4e2dcafd overlay одного Agent файла: existing operator_binding с boot,
двумя epochs, paired owner и TTL проверяется под microphone/policy locks прямо
перед изменением listening Event. Epochs не меняются, legacy empty manual payload
сохранён. Explicit expected owner null соответствует только двум actual owners
None в штатном ручном режиме; missing owner/TTL недопустимы, grant API не меняются.
Bound say использует тот же locked guard перед очисткой listening и не восстанавливает
старое listening. Независимый source GO и13 focused tests PASS, включая actual HTTP
handler, mixed owners, новый grant перед Event mutation и TTL при ожидании lock;
16 вместе с прежними pause/voice regressions PASS.
Actual установка4e2 выполнена: один Agent restart, новый boot подтверждён,
OFF/100, config/profile/token/unit/shared sources, factory instance и camera IPC
сохранены. Новая baseline receipt отдельная; исторический prefix receipt не менялся.
Caller delta также source-reviewed: say/pause/resume используют один исходный
binding, deadlines не расширены, controller/posthoc/new baseline pins согласованы.
Actual bound CLOUDS завершён native/phase/postnative/topic PASS, cleanup OFF/100,
без interruptions. Краткость FAIL:14 spoken words, два вопроса, sampled span7,180 s
как нижняя граница. Первый целый вопрос сам содержит7 words, поэтому выбор первого
вопроса тоже не удовлетворяет target. Prompt-only изменение недостаточно.

Подготовлен и независимо принят source-only opt-in gate для прежних RAW9B/endpoint:
точные overlays Voice92cf→00330682 и Configc0→e7d3de62, default
`conversation.alice_question_gate=false`. При opt-in и Alice prefix весь complete
model candidate до TTS должен быть одним законченным вопросом3–5 words. Ничего
не выбирается, не обрезается, не ремонтируется и не заменяется ACK. Только после
known-complete invalid candidate разрешена одна regeneration в оставшемся исходном
request budget с теми же user/history. Invalid output не публикуется и не попадает
в history; HTTP/timeout/backend errors не повторяются. STOP/authority/deadline
проверяются до/между/после генераций и перед TTS; ACK branch отключён в Alice mode.
Explicit-details request сохраняет исходный long-answer путь/max512.17 focused
tests PASS, independent source GO. Deadline запрещает позднюю публикацию, но не
доказывает мгновенное прерывание blocking backend I/O; gate проверяет форму,
не семантическую полезность или отсутствие скрытой просьбы выполнить действие.
Runtime ещё не принят. Из-за read-only worker rootfs установка использует прежний
same-image strict-slot overlay с двумя individual read-only binds Voice/Config,
единственным worker на8082, recoverable baseline и exact private-profile restore.
В Alice audio mode отсутствие загруженной SoundEvents session отклоняется до STT
и модели; fallback kind=speech/scores0 не используется как verified speech.
Actual alias audit исключил overwrite прежних файлов: Config имеет8 parked aliases,
оба источника связаны с frozen plans. Pure builder
`prepare_question_gate_container.py` принят independently/8 focused tests: заменить
Source двух уже существующих RO mounts, сохранить mount count5, прочие Config,
HostConfig, restart policy, сеть/security/ports. Сохраняется только ранее принятый
явный Engine typed case OomKillDisable null→false и immutable image pin. Ни Docker,
ни filesystem/network/model операций этот builder не выполняет. Profile activation
добавляет один bool к exact preimage; rollback возвращает исходные bytes/FI прежде
чем запускать старый Config. Исполняющий caller сохраняет прежние SourceFences,
StrictSlot, enrollment до START, exclusive8082, START204 witness и UNKNOWN/no retry.
Source algorithm review выполнен по operational-independent копии; значения
проверяются локально sole runner. Actual установка gate и короткий runtime turn
ещё не приняты.

**HARD DEPLOY BLOCKER:** после начала create-stopped не получен достоверный
CREATE completion/NoSubmission witness; StrictSlot сохраняет mutation_pending UNKNOWN.
Read-only exact-plan проверка: кандидат отсутствует, исходный worker работает тем
же процессом, профиль не изменён. Отсутствие кандидата не разрешает clear/retry.
Прежние transport/preflight failures сохранены отдельно. Recovery refusal не
является причиной исходного CREATE failure; первичная причина UNKNOWN, поскольку
secondary recovery exception заменила её telemetry. Future-only исправление
сохраняет primary fixed class/function/line до recovery и secondary отдельно;
оно не выполняет повторную операцию и не разрешает очистку текущего UNKNOWN.
Существующего reviewed CREATE-only reconciliation механизма не найдено. До
reviewable maintenance decision не выполнять новые PC mutations/live trials,
не создавать второй slot namespace и не переигрывать CREATE. Baseline сохранён,
gate0033/e7d source-frozen, actual gate/long dialogue/streaming PASS отсутствуют.
Это не доказательство длительного диалога или meaningful streaming.

Подготовлено [публичное предложение explicit maintenance recovery](docker-maintenance-recovery-proposal.md)
после RO impact inventory: Docker17/1running/16stopped, running только Reachy
worker, live-restore=false, Docker Desktop/WSL. Native model continuity и полное
исключение будущих submitters пока UNKNOWN. Документ не разрешает исполнение:
нужны reviewed Docker-only boundary, same-slot manual supersession с сохранением
истории UNKNOWN и конкретное согласование disruptive scope координатором.
Последующий finite audit уточнил managed scope: одна enabled startup task с3
retries и heartbeat координатора требуют явного pause/disable с точным restore.
Архитектор rev21 принял SAME-pipe WSL2/unique target runtime inference и конечный
HOLD contract. Отдельный `maintenance_supersession.py` получил independent
SOURCE GO/8tests PASS: same existing mutex/provider, durable original UNKNOWN
intent и supersession до sole save(None), marker/approval recheck до freshstart,
никакого autoretry. Это abstract core; concrete provider/effects composition,
maintenance approval и фактическое восстановление ещё не приняты.
Последующий writer source composition review exact manifest089d6f35 — GO:
10source/4test pins match; provider4/adapters9/assembly1/JS2+UTF8 syntheticPASS.
Actual canonical factory/native namespace и durable managed-HOLD evidence
согласованы; HOST bridge использует existing finite READY/own receipts.
Это fake-native source checks, не runtime acceptance. Independent reviewer rev131
также выдал SOURCE COMPOSITION GO и повторил focused checks PASS. Fresh private
context и конкретное maintenance approval ещё нужны; mutations0.

Обновлено 2026-10-17. Владелец плана — координатор Reachy Mini; writer ведёт код,
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
| Prime-paused diagnostic | `73c241b`: Hub client обновлён без restart; в одном исправленном реальном прогоне cue выполнен при закрытом capture, затем подтверждены resume и свежий захват | **NOT_EXERCISED для камеры:** точный visual intent в STT отсутствовал, child не запускался. Один completed turn не доказывает vision/context. Следующая camera проверка отдельным этапом после длительного normal dialogue |
| Состояние после сбоя | После разрешённого повтора baseline/config/исходные worker-модули восстановлены и idle, content_tokens false, candidate parked, slot пустой; Robot OFF/unowned/free/100%, no camera/aplay; принятый camera bind сохранён | Это независимый конечный PASS восстановления данного повтора; не заменяет audible overlap, acoustic onset, E2E latency или длительный recovery soak |
| Потоковый диалог | Последний human-прогон на cf50: оба ответа слышны, strict Agent21 + PC31 unique join прошёл; STOP озвучивания model response и следующий turn в том же процессе приняты, baseline независимо восстановлен | Measured timeline completion gate = 0,926774 s. Producer PCM/token overlap есть, meaningful audible overlap **NOT DEMONSTRATED**, acoustic consumption и speech-end E2E неизвестны. S1 установлен OFF; S2 source принят, не установлен. Человек затем явно разрешил вернуть штатные движения; incident остаётся наблюдаемым, не блокирует working MVP |
| Задержка vision | Два реальных image inference заняли около 11,03 и 10,35 s | Уже один inference превышает цель 10 s; полный speech-end → meaningful audio не измерен. Не объявлять цель достигнутой |
| Память | Обычная RAM session history существует | Snapshot `/say` не добавляет visual question/answer в worker history; долговременная память и continuity через restart не приняты |
| Антенны | Человек уточнил: быстрое дрожание только при ответе/движениях; конечное чтение API: 23 GET за 2,93772 s, изменений сообщаемых углов нет, task lists пусты, control mode ENABLED | Причина **UNKNOWN**. Freshness/caching/resolution и реальные targets неизвестны; короткое чтение примерно 7 Hz не исключает быстрый/периодический тремор и не доказывает физическую остановку. Штатные движения снова разрешены человеком; torque/limits/UART не меняются, причина дрожи остаётся UNKNOWN |
| Датчики | Реальный bounded SDK inventory: IMU REST возвращает accelerometer/gyroscope/quaternion/temperature, timestamp поля доступны; штатный API не требует нового reader/UART | Cache/physical freshness пока UNKNOWN. Target antenna query объявлен, но поле отсутствовало в реальном ответе — не считать targets измеренными. Полезный typed sensor → speech/context путь ещё не интегрирован; следующий этап после рабочей длинной сессии |
| Полная автономность | Есть реализованные contracts, guards, fixtures и отдельные реальные checkpoints | Непрерывное восприятие/решения, память, полезные интеграции, recovery и длительная реальная приёмка ещё не завершены |

Реальные receipts и операционные идентификаторы хранятся в приватном runner
каталоге. В Git идут код, публичные runbook, тесты и этот план; без конфигов,
секретов, raw audio/images и приватного operational handoff. Текущая рабочая
громкость — 100%, сохраняется стартовое операторское значение, не старые 50%.

## Очередь поставки и владельцы

Актуальный scope задан прямым поручением человека 2026-10-16: short useful speech →
long Alice dialogue → true streaming/continuous hearing → camera/sensors. Эта
очередь имеет приоритет над прежними полными product goals и историческими
критериями ниже. Долговременная память, интеграции и перенос **вне MVP**.

| Порядок | Статус | Минимальный результат | Владелец | Реальная приёмка и доказательство |
|---|---|---|---|---|
| P0.1 | Активно: короткий полезный голос | Одна короткая законченная фраза/вопрос по умолчанию и в Alice dialogue; подробный ответ только по явной просьбе | writer: минимальная response policy; runner: реальные короткие ходы | Содержательная речь, не ACK; не обрезать PCM. Временные96 токенов Alice-профиля не должны ограничивать explicit long request в общем режиме |
| P0.2 | Следом: длительная беседа с Алисой | >=20 минут, >=10 реальных коротких ходов в текущей conversation epoch | runner: единственный hardware owner; reviewer: source/evidence | Runtime stability, тематическая уместность и длина речи считаются отдельно. Каждый intentional вопрос начинается «Алиса»; STOP/owner/epoch fences сохраняются |
| P0.3 | Затем: настоящее streaming и continuous hearing | Meaningful speech до завершения model generation; endpointing, AEC, barge-in и STOP | writer: существующие audio seams; runner: actual overlap | Chunking уже готового целого ответа не считается streaming. Producer overlap и0,926774 s completion gate не заменяют meaningful audible overlap. S1 OFF/S2 source не hardware PASS |
| P0.4 | Затем: камера и другие доступные датчики | Сохранить принятый spoken camera путь, добавить один полезный typed sensor readout | writer: минимальная интеграция; runner: actual sensor → speech | Camera accuracy/свежесть и sensor units/provenance/TTL проверяются отдельно; нет данных → UNKNOWN |
| P0.C | Лёгкая проверка контекста | Проверить существующую session history и оставить её, если работает | writer + runner | Контекст не превращается в большой rewrite/blocker. Restart worker начинает новую history epoch; память через restart не обещается |
| P0.O | Постоянная работа служб | Reachy/PC/Hub продолжают работать после тестов | runner: existing supervisor/services; writer: узкие исправления | Finite test освобождает только свой permit; сервис остаётся idle или listening при живом valid grant. STOP/manual OFF, ownership, epochs, TTL и fail-closed сохраняются; watchdog вслепую не отключать |
| После MVP | Отложено пользователем | Долговременная память, интеграции, перенос | координатор определяет следующий scope | Не включать в текущую MVP-приёмку и не задерживать ими голос/Alice/streaming/sensors |
| Поддержка | Наблюдение антенн и recovery | Штатные expressive движения разрешены, причина дрожи UNKNOWN; воспроизводимые delivery/rollback/resources | runner + writer + reviewer | Не менять torque/limits/UART. Сохранять mute/volume, source pins, STOP, no stale replay и один hardware owner |

Параллельно допустимы только независимые локальные source review и подготовка.
На устройствах — один runner и один согласованный этап; не накладывать latency
patch, новый dispatcher и model/runtime migration на активный acceptance run.
Общие разрешения пользователя на устройства уже получены; не создавать новые
общие approval-пакеты. Текущие STOP/mute/quiet/privacy и более новый owner имеют
приоритет над любым планом. Точечная диагностика не должна запускать новый снимок
или inference автоматически.

## Текущий приоритет: рабочий MVP и длительные разговоры

Новое прямое поручение человека: ускорить рабочий MVP, регулярно обкатывать его
длительными разговорами с Алисой, добавлять камеру и доступные датчики. Человек
явно разрешил вернуть штатные движения; прежний antenna hold отменён. Постоянные
разрешения на устройства и передачу данных действуют, STOP/mute/privacy остаются
приоритетными. Циклы конечные, последовательные, с единственным runner; новый
параллельный hardware owner или отдельный монитор не создаётся.

Кратчайший путь — текущий normal baseline с prime-paused mic grant, paired
motorTrue claim, protected own cue и подтверждённым terminal/quiet перед resume.
Старый late-last_transcript observer не управляет admission/следующим cue.
Проверка распознанного ответа выполняется posthoc как functional evidence; это
не строгий arithmetic pre-LLM whitelist и не speaker identity. Source-accepted
Agent5174/audio-only/gate proposals сохраняются отдельно и **не установлены**;
они не являются условием рабочего normal-path прогона. Временный PC short-profile
96 — только текущая Alice обкатка, не универсальная политика explicit long request.
Службы остаются запущенными после finite cleanup; возобновление listening допустимо
только при живом valid grant, без обхода manual OFF/TTL/ownership. Исправлять только реальные blockers
самым маленьким изменением, сохраняя воспроизводимую working команду.

**Первый normal-path Alice smoke: functional route checkpoint принят; playback witness позже пересмотрен.** Исходные Agentcf50, clientadc,
launcher052 и watch4cd сохранены; установлен только reviewed profile delta:
`conversation.speech_address_prefix='Алиса, '`, `greet_on_start=False`,
`wake_on_start=False`, один guarded restart Agent. PC/source/camera/ALSA100
не менялись. Exact profile и его backup/FI journal сохранены privately.
Protected cue «Алиса, сколько будет два плюс два?» завершил собственный stream;
после terminal/quiet подтверждён свежий захват. Posthoc STT4/четыре сопоставлен
с Agent и реальным worker9B; nonempty ответ prefixedAlice, legacy APLAY flag
после resume true, stock task наблюдался. После обнаружения ALSA alias этот
APLAY flag признан capture-ambiguous, не отдельным доказательством playback.
CLI rc0, controller acceptedTrue,
один completed turn и independent-watch cleanup verified. Speaker UNKNOWN;
acoustic onset и физическая выразительность этим не измерены. Проверенный
конечный launch command/pins хранятся с private operational receipt; public
product acceptance длительного разговора и publishable command ещё открыты.

**Первый related FACT не принят.** Собственный cue завершился, fresh capture,
real APLAY, nonempty model reply, prefix и Agent/worker match подтверждены.
Однако posthoc required-word check не нашёл exact «кедр» (и «мой»); «корабль» и
«называется» присутствовали. RECALL не запускался, цепочка остановлена без retry;
final OFF/unowned/100/tasks-empty/noAPLAY verified. Это mismatch ожидаемого входа,
не доказанный отказ голоса/LLM и не установленная причина ASR vs Alice response vs
matcher morphology. Runner затем локально проверил private controlled STT/FINAL:
это lexical matcher false-negative из-за другого написания известного тестового
маркера; локальная semantic reference в ответе соответствует intended marker.
Исходный controller FAIL не переписан. Передача raw text между чатами отклонена
автопроверкой; сводное заключение имеет ограничение отсутствия независимого
cross-chat semantic text review. Обхода передачи нет. После verified OFF разрешён
новый answer-free RECALL как отдельная диагностика уже сохранённого факта, не
blind retry и не автоматическое продолжение RC0-chain. Color variant source
reviewed, но повторный ввод факта не нужен. Длительная 20–30-минутная приёмка и
>=10 связанных ходов пока НЕ выполнены.

**Первый RECALL не принят из-за scope race.** После own cue/quiet fresh capture и
APLAY наблюдались, но Agent успел выполнить два автоматических хода (ожидался
один), а latest worker/Agent text не был joined. Семантика первого RECALL остаётся
UNKNOWN; это не доказанный memory failure. Финальный OFF/unowned/100/tasks-empty
подтверждён. Минимальное исправление — только existing control phase: при первом
APLAY ответа same-owned guarded `/pause` один раз, current voice продолжает работу,
следующий normal input не начинается; final OFF очищает pending/resume. До PASS
нужны unchanged interruptions, no resumable reply, один completed turn и свежий
worker/Agent join. Метод source-reviewed; три exact-cf50 full-stream/pending/mute
regressions PASS. Ни source Agent, ни профиль этим исправлением не менялись.
Один corrected RECALL разрешён как проверка конкретного исправления, не blind retry.

**Исправленный RECALL timeout выявил дефект наблюдения ALSA.** Counter остался
на исходном значении, worker idle/last_turn own cue, interruptions не изменились;
это не доказательство длинного model reply или memory failure. Read-only
проверка подтвердила: `/usr/bin/arecord` — symlink на тот же executable/inode,
что `aplay`. Original watch4cd `playbacks()` проверял exe/parent/cgroup без argv0,
поэтому capture ошибочно считался playback. Новая pause срабатывала до STT.
Нужен минимальный actor-only classifier по argv0 literalaplay и стабильным
parent/cgroup/exe/start identities до/после чтения; arecord/unknown не playback.
Original watch cleanup не меняется: отсутствие всех ALSA children остаётся
консервативной resource проверкой. Старые receipts не переписываются; их legacy
APLAY flags пересмотрены как capture-ambiguous. Независимые human audibility и
Agent positive-write proofs этим не отменяются. Истинный owned playback будет
проверен новым classifier; ещё один RECALL — проверка этого конкретного fix.

**Natural conversation: три реальных runtime/topic PASS.** Уже выполнены sky,
sunset и clouds на текущем cf50/PC baseline. Новая phase-only проверка различает
argv0arecord/aplay, ставит same-owned pause при настоящем playback, затем original
native client 1/180 сам завершает ответ и CAS cleanup. Только после native RC0 и
exact epoch fences read-only postcheck подтверждает один Agent turn, worker join,
model answer route, Alice prefix, no interruptions/resumable, OFF/100 и quiet
resources. SKY: 47,723 s watch, 11 STT words, cue-overlap0; SUNSET: 54,177 s;
CLOUDS: 43,041 s. Все три завершились RC0. Это связанные темы, не controlled
memory-recall PASS и не acoustic onset/physical pose certification. Локальная
semantic проверка первого ответа отметила unrelated old-context reference —
открытая quality limitation, не скрытый PASS памяти.

Один новый explicit camera прогон также completed RC0: кадр 640×360, image
inference13,421 s, receipt age13,726 s, camera closed, raw-pixel files0, прежний
model instance сохранён и cleanup verified. Без человека semantic accuracy и
physical source capture time не подтверждены. Минимальный reported IMU chip
readout `imu_readout.py` прошёл source review/6 fixtures; требует фактического
нового API receipt, protected SAY и исходного TTL20. Invalid/expired → UNKNOWN,
physical/cache freshness и ambient-temperature claims false. В runtime пока
не интегрирован, sensor hardware readout PASS не заявляется.

Thin serial soak подготовлен поверх той же one-turn команды: >=10 accepted
actual turns AND >=1200 s, без искусственного padding; caps60/1500 s start budget
с конечным current command reserve до1800 s. Every next grant требует предыдущие
native/runtime RC0, phase+postnative, OFF/100 и exact+2 epochs; STOP/unknown не
перепрыгиваются. Early cap/STOP не выдают полный soak PASS. Это подготовленная
серия, не завершённая 20-минутная приёмка.

Фактический первый soak остановился после двух accepted ходов (AUTUMN49,586 s,
SEA42,615 s), elapsed109,481 s: третий TIDE завершился runtime FAIL на
`unknown_ALSA_role` до квалифицированного playback. Защитный watch подтвердил
OFF/100; автопродолжения нет. Это не повтор предыдущего RAINBOW policy cleanup
failure: здесь phase controller прервал проход из-за неоднозначного ALSA child.
Пустая cmdline при exec/exit — гипотеза, конкретный guard не был записан.
Отдельный LEAVES recovery перед soak прошёл RC0 за43,692 s; прежние FAIL сохранены.

Pure read-only `alsa_role_observer.py` прошёл независимую source review и семь
fixtures: empty/unknown/disappeared/reused/foreign children не допускаются как
playback и не доказывают отсутствие playback; изменение Agent identity fatal.
Следующий обычный poll допустим только внутри исходного deadline. Pre/post-cue
quiescence требует `absence_verified` плюс прежние capture/owner guards. Это
source acceptance; интеграция в frozen controller и отдельный hardware repeat
ещё требуют проверки. Agent/profile/timeouts этим не меняются.

Последующая интеграция observer прошла две source review: оба quiescence sites
требуют `absence_verified`, positive-playback poll сохраняет исходный deadline,
helper проверяет Agent identity после scan. Отдельный MOON hardware ход завершился
native RC0, phase/postnative true за47,4885 s, OFF/100, без новых interruptions.
Тематический результат false: этот case остаётся semantic FAIL. Точный transient
ALSA guard исходного TIDE этим ретроспективно не установлен.

Следующая длительная серия имеет **отдельный runtime-stability criterion**:
>=10 runtime-accepted ходов AND >=1200 s. Runtime-accepted требует native RC0,
phase/postnative true, известные OFF/100, exact epoch fences и прежние проверки
interrupt/ownership. Semantic false разрешает продолжить только после этих
проверок; semantic FAIL сохраняется, semantic-accepted count ведётся отдельно.
Unknown, native failure, interruption или operator drift по-прежнему останавливают
серии. Это явное изменение критерия следующего прогона, не пересчёт первого
неуспешного soak и не полный MVP/context/coherence PASS. Предел1800 s сохраняется.

### Следующий source путь после разрешения CREATE UNKNOWN

Это dependency plan без нового deploy или live trial. Сначала принять short gate
и длительную короткую Alice беседу. Streaming не является обходом заблокированного
слота или поводом забыть working baseline.

| Шов | Существующий frozen source | Что проверить до будущего применения |
|---|---|---|
| RAW token → Piper | `prepare_content_stream.py`: Brains9c69→020e435e, Voice92cf→bbdb7be5, helper token_stream a4aa26d3 | Прежний overlay не применяется поверх gate Voice0033. Нужен точный совместимый preimage с сохранением whole-candidate gate и explicit-details policy; endpoints/model identity прежние |
| Capture/control | Installed S1 cf50-derived Agent4e2, capture_pump b7b1; flag OFF | Не возвращать прежний cf50 с unbound pause/resume. Сохранять explicit expected owner None/finite paired owners, обе epochs, TTL и новый STOP; один владелец существующего capture |
| Partial STT | `prepare_provisional_stt.py` ожидает cf50, Voicebbdb, Recognition6211 и прежний capture b7b1 | Все несовпадающие preimages перепроверить и rebase source-only. S2 source acceptance не означает partial/continuous hardware PASS; no stale partial after OFF/new epoch |
| Motion/audio admission | Existing Expression7a5 completion gate; local-armed proposal отдельно source-reviewed | Producer PCM/token overlap не доказывает meaningful audio. Local scheduler-ready не означает remote/physical admission; не менять timing/torque/UART вслепую |
| AEC/barge/STOP | Existing VAD/barge thresholds, playback cancellation, SoundMonitor, epoch fences | Пороговая реакция не доказывает AEC. Нужны фактические source/DSP capabilities и near/far/music/own-speech cases на одном owned stream; отсутствие новых слов после STOP и свежий следующий turn |

Whole-candidate Alice gate намеренно ждёт complete model answer до TTS. Нельзя
выключить его и назвать это успешным безопасным Alice streaming. Для будущего
совмещения понадобится отдельно reviewable bounded generation contract; до него
первый proof meaningful speech до model completion допустим только в явно
обозначенном режиме/запросе, например requested detailed human reply. Это не
приёмка streaming для обычной короткой Alice реплики.

Физическая приёмка требует одинакового attempt/boot/epochs и доказательства
meaningful playback до окончания именно его model generation. Сравнивать только
согласованные clocks либо причинную последовательность; не вычитать PC и Robot
timestamps без offset proof. Непустой SDK chunk, queue/PCM yield, ACK, motion task
или sampled APLAY lower bound по отдельности этого не доказывают. Acoustic onset,
полный speech-end E2E и speaker identity остаются отдельными UNKNOWN до измерения.

После smoke runner выполняет 20–30-минутную сессию из последовательных bounded
циклов с >=10 связанными ходами в той же реальной conversation session. Граница
цикла и паузы отражаются честно; это не continuous-capture acceptance. Контекст:
первый факт → уточнение/местоимение → последующий ответ; модельный текст и STT не
подставляются контроллером. STOP при реальной речи и свежий следующий ход должны
быть доказаны отдельно. Сохраняются наблюдаемые delays, ресурсы/VRAM, stalls и
ошибки; route/model/playback/physical evidence различаются.

Затем — уже принятый camera path и небольшой inventory фактически доступных
SDK датчиков (например IMU, если существует). Один полезный sensor path с typed
значением, единицами, provenance и TTL/latest-only; отсутствующая/устаревшая
телеметрия возвращает UNKNOWN. Receipt age не доказывает freshness аппаратного
измерения. Generic sensor framework и покупка оборудования не нужны.

## Последний human measurement и incident антенн

**Текущий приоритет Alice dialogue: короткие реплики.** Прямое наблюдение
пользователя: Алиса прекращает слушать раньше окончания длинной речи Reachy.
Длительная сессия теперь означает много коротких ходов. Следующая настройка
через существующий профиль/system prompt должна требовать одну законченную
фразу или вопрос с обращением «Алиса», ориентир5–10 content words/~3–5 s речи,
без повторов, объяснений и нескольких вопросов. Это target, не измеренный PASS.
Модельный ответ остаётся содержательным; PCM не обрезается посреди слова.
Прежнее требование длинного spoken FINAL для Alice superseded. Изменение только
после known safe OFF, с сохранением profile pins/restore; следующий фактический
короткий ход проверяет word count, sampled APLAY duration и relevance отдельно.
Длинная серия со старым verbose profile не запускается. Camera, stock motion,
модель и STOP сохраняют прежние контракты.

Фактически первый short-profile установлен через existing PC worker restart:
только system prompt suffix и max_tokens512→96. Первичная readiness-проверка
не уложилась в12 s и осталась FAIL; отдельный read-only reconcile подтвердил
idle/HTTP200, effective profile, прежние source/image и известные OFF. Это один
restart, новая conversation epoch; повторного restart не было.
Первый WIND launch остановился до watch-ready, без нового ON/cue/turn. Отдельный
RAIN прошёл native RC0/phase/cleanup, OFF/100. В локальном posthoc driver был неверный
путь source; original reporting FAIL сохранён, отдельное read-only чтение того же
завершённого run подтвердило postnative PASS. Не считать это новым speech turn.
RAIN:10 spoken words включая Alice, complete/prefix/model-route true, topic false.
Reply sampled process span6,7747 s — нижняя граница, поэтому <=5 s target точно
не выполнен. Cue span2,9311 s. `short_sample_target_met` отражает только sampled
проверку, `physical_duration_target_met` остаётся UNKNOWN; sampled span не верхняя
граница длительности. Следующий шаг — более короткий обычный вопрос и явное
исключение подробного ответа, без универсального96-token ограничения.

Эта коррекция выполнена через existing cfg-only путь: старый short suffix заменён
на default3–5 words с explicit-details exception, max_tokens96→512. После одного
restart этого этапа initial readiness снова истекла; отдельный RO reconcile
подтвердил effective profile/idle200/прежние source/image и OFF. Новая history
epoch отражена явно. Следующий SNOW actual turn прошёл native/phase/postnative,
cleanup OFF/100;6 spoken words/complete true, reply sampled span2,998 s, cue3,134 s.
Topic false сохранён отдельно. Это подтверждает короткую законченную реплику по
word count, не certified <=5 s acoustic duration и не длительную сессию. Настоящий
streaming/continuous hearing/длительная Alice беседа ещё не приняты этим ходом.

**Штатный persistent operator handoff выполнен.** После завершённого finite watch
и known OFF source-reviewed переход использовал только policy CAS ON и microphone
CAS ON с listen=True, затем read-only наблюдение. Actual capture/listening true,
микрофон и разрешение stock motion включены; ownersNone означают существующий
durable human operator mode. Новая служба/бесконечный test actor/фиктивный lease
не создавались, watchdog не отключался, Agent/source не менялись. Seed/say/resume
из handoff исключены: их unbound API не давал server-side epoch CAS. Поэтому
Alice_seed_sent=false, long-dialogue PASS отсутствует. Службы оставлены работать;
не считать legitimate manual ON зависшим finite grant и не arm finite watch
поверх него. STOP/mute/newer epochs приоритетны, автоматического повторного ON нет.
Человеку сообщено только после actual capture proof; предоставлено90 секунд без
тестовых реплик и переключений. Это не подтверждение присутствия человека или
слышимости его ответа. Guarded инициирование следующего Alice dialogue — отдельная
задача; постоянно включённый микрофон ещё не означает simultaneous hearing/AEC.

**Новый incident supersedes текущее listening состояние:** человек сообщил, что
Алиса включила музыку. Автоматические elicitation и длительные Alice тесты
приостановлены. Runner выполнил один штатный microphone OFF CAS: actual mic,
capture и listening false, no ALSA/factory tasks, volume100; службы остаются ON.
Повторный ON/resume/музыкальный repro не выполняется. Cause UNKNOWN; нормальный
счётчик вырос16→21, attribution этих ходов человеку/Alice не подтверждена.
Это не long-dialogue PASS. Пользователю сообщено фактическое OFF состояние.
Existing SoundMonitor использует те же capture chunks и bounded latest queue к
PC SoundEvents; music gate сбрасывает STT frames. Его actual effective enabled/model
состояние ещё требует metadata проверки. sessionNone fallback kind=speech/scores0
не является классификацией речи. При OFF не открывать новый capture ради repro;
speaker identity, источник музыки и intent, запустивший музыку, остаются UNKNOWN.

Последующий actual read-only capability audit подтвердил sound_reactions enabled
на Robot и PC; файл YAMNet существует, hash совпадает с config и known public pin.
Live session_loaded не наблюдался напрямую. Новых classify/model-load/download
вызовов не было. sound_mode=conversation/no error после mute reset не доказывает
музыкальную классификацию во время incident. Current OFF сохраняется; возобновлять
capture или музыку ради repro под текущим steering нельзя. Следующая реальная
проверка требует уже разрешённого живого input; до неё discrimination UNKNOWN.

На cf50/default-off выполнен один согласованный human-цикл. Оба окна объявлены
человеку только после actual capture-active; человек прямо подтвердил, что оба
ответа слышны. Один уникальный content attempt прошёл общий strict Agent21 + PC31
join с текущими boot/mic/policy. STOP применён к bound model-response APLAY после
3,028723 s наблюдения; cleanup 0,404633 s. Это software observation, не physical
P95 и не доказательство STOP во время ещё идущей генерации. После verified DONE /
producer/Piper quiescence второй запрос обработан тем же candidate процессом,
completed turn = 1. Нового дополнительного цикла не было.

| Метрика одного PC POST clock | Первый ответ | Второй ответ |
|---|---|---|
| First semantic, s | 0,622876 | 0,505733 |
| First PCM yield, s | 0,756479 | 0,642915 |
| Last nonempty token READ, s | 1,010910 | 1,742262 |
| DONE READ, s | 1,011371 | 1,742726 |
| First segment chars / boundary | 38 / question | 49 / period |

Это producer PCM/token overlap. Семантическая категория первого сегмента
**UNKNOWN_NOT_RETAINED**: длина и punctuation не доказывают содержательное начало.
Raw text не сохраняется в этом плане.

На одном Robot monotonic clock first audio → first positive pipe write =
0,931785 s, из них timeline wait = **0,926774 s**. Popen занял 0,001101 s,
после Popen до write — 0,003247 s; первая запись 3200 bytes. Response open занял
0,709614 s. Отдельно записанные консервативные clock brackets дают first write
POST+[1,532211; 2,545095] s, позже PC DONE 1,011371 s во всём этом интервале.
Это software-bound результат данного attempt, не глобальная сертификация часов.
Генераторные generation/cross-clock/acoustic flags не переписываются в true.
Actual acoustic onset/consumption, speech-end E2E и второй Agent APLAY onset
не измерены; meaningful audible overlap и полный streaming PASS не объявляются.

Независимые конечные PC/Robot/camera проверки подтвердили восстановленный baseline:
исходные worker/config, content_tokens false, idle, пустой slot, candidate parked,
inventory сохранён. Тот же cf50 Agent, capture pump false, OFF/paused/unowned/free,
100%, no arecord/APLAY/camera; camera bind/helper/unit/persisted state и source
backups/FI journal сохранены. Это конечный recovery PASS данного прогона.

**Следующий audio-only повтор по прямому запросу человека завершён.** Exact-source
RAM-only client `4722db25…` / corrected invocation `d22fc962…` прошли независимый
source review; установленный Agent `cf50…` и Expression `7a5…` не менялись.
Сценарий закрепил disabled-policy claim (motor false), затем mic claim; actual
owned capture/listening подтверждены, человек немедленно уведомлён об окне 90 s.
Зафиксирован один completed turn, RC0 и original-watch cleanup verified.
Независимый конечный RO подтвердил paused/OFF/unowned, volume100, free/known Hub,
пустые factory tasks, отсутствие APLAY/camera и прежний idle PC baseline/config.
Человек затем сообщил: «я не был рядом». Слышимость NOT_OBSERVED_USER_ABSENT,
принадлежность detected turn предполагаемому человеческому запросу UNCONFIRMED.
Счётчик completed доказывает только один обнаруженный Agent turn; intended human
dialogue не принят. Независимый замер APLAY, acoustic onset и meaningful
generation/playback overlap не выполнялись.
Предыдущий host-key отказ произошёл до client/mic grant; его отдельный watch
завершил cleanup. Исправление вернуло original strict trusted-hosts lookup.
Новые expressive движения, camera или source installation не выполнялись.

**Новое поручение: конечные проверки с Алисой, пока человек отсутствует.**
Каждое намеренное обращение начинается с «Алиса»; говорить/слушать и камера
проверяются последовательно, первоначальный expressive hold затем отменён человеком; штатные движения снова разрешены. Это Alice-source system test, не human acceptance.
Установленный cf50 bound `/say` и spoken_vision486 пока требуют motorTrue.
Непроверенный unbound `/say` и старый observer по late last_transcript не применяются.
Подготовлен source-only combined Agent5174/helperf3ce/RAM-client618: явный
bound audio_only=True при literal motorFalse, сначала mic listenFalse, собственный
cue «Алиса, сколько будет два плюс два?», затем guarded resume после собственного
stream-done/cleanup и fresh controlled-exclusive lifecycle proof. Exact4/четыре
допускается до LLM только из нового normal-capture buffer с original receipt TTL2,
source generation и теми же owner/epochs; once/closed, STOP сохраняет приоритет.
Trial answer сохраняет исходный policy epoch/deadline и local Alice prefix;
25 meaningful source checks PASS, independent review исправления P1 принят.
5174 не установлен: рабочий normal Alice smoke выполнен отдельно без него. Следующий отдельный camera
шаг сохраняет принятые TTL/provenance/privacy/latest-only и требует решения
literal-False admission; арифметическая проверка сама это не исправляет.

**Затем человек сообщил о быстром дрожании антенн.** Runner выполнил только
конечное read-only чтение: 23 GET за 2,93772 s (порядка 7 Hz запросов); сообщаемые
углы имели span 0, обе task lists пусты. Control mode оставался **ENABLED**.
Agent paused/OFF/unowned и motor policy false не означают отключённый привод или
физическую остановку. Timestamp/freshness/caching/resolution и goal/target поля
не подтверждены; такой пакет не исключает быстрый или intermittent тремор.
Причина UNKNOWN, аппаратная поломка не установлена. Человек уточнил: симптом
возникает только при ответе/движениях. Это не исключает actuator issue under motion;
idle GET такого вывода не позволяет. Следующий source-only focus — commanded
cue/phase transition step/rate. Первоначальный hold expressive trials затем отменён человеком. Штатные движения
снова разрешены; torque, smoothing, limits и UART не меняются.

Source-only audit exact expression_player `7a5…` / router `f513…` показывает один
expression consumer: явного второго собственного параллельного sender нет.
Публичные planning helpers добавляют processing repeat, speaking/phoneme timeline,
dance и переходы к neutral с разными antenna targets; cues меняют знак по beat, поздние cues
сливаются в текущий target без восстановления пропущенного времени. Конкретные
активные flags/частота/амплитуда private config не читались и не предполагаются.
Конкуренция с SDK idle/holding path и версиям cancellation требует actual source /
bounded state evidence. Пустой REST task list не доказывает отсутствие controller
holding или внутренних SDK задач.

В cached SDK1.11 цепочка GotoMove при antennas=None подставляет present position,
а evaluate возвращает non-None antenna vector; play_move передаёт target на своих
тиках, controller далее удерживает последнюю цель. Это **не гарантия отсутствия
записей оси**. max_antenna_degrees=0 также означает посылку нулевых targets,
а не исключение антенн. Совпадение этих cached файлов с текущей установкой нужно
проверить перед любой правкой; это source finding, не диагноз данного робота.

Минимальный доступный fallback без изменения SDK — после согласованного evidence
packet и штатного own-stop/known-empty временно отключить **весь собственный**
ExpressionPlayer существующим expressions.enabled=false через guarded restart,
сохранив voice, mute/100, SDK и guards. Он отключит и собственные head gestures;
это предложение, не выполненная настройка. Hot flip поля не останавливает уже
созданный thread/in-flight HTTP. Избирательное head-only с настоящим исключением
antenna writes требует проверенной SDK axis-mask/Move semantics; blind None,
новый set_target обход или настройка torque/smoothing не предлагаются как fix.

Измеренный gate не теряется: wait_timeline в `7a5…` ждёт completed, который растёт
в finally **после** synchronous /actions/expression reply/error. Он может включать
остаток предыдущего processing HTTP; доля этого остатка и первого cue пока
не разделена. Это completion wait, а не доказательство remote admission: finally
срабатывает и после отказа. Router read1/flush whole answer не ждёт. SDK task UUID
и move_started означают регистрацию/wrapper start, не физический старт/позу.

После incident review остаётся proposal: bounded typed registration/admission +
terminal события на том же expression HTTP и том же handler/Hub lock/watchdog,
с ticket clock/version/boot/epochs, без второго owner, повторного POST или задержки
модели. Audio gate мог бы ждать регистрацию текущего ticket отдельно от completion;
никакая запись/ACK не считается physical motion. Local timeline-armed ticket был бы
ещё меньшим вариантом: exact clock/version/binding отделены от completed; он
доказывает только готовность локального scheduler, не приём SDK, и сохраняет
возможное ожидание старого processing. Для first cue at>0 arming не должен ждать
продвижения ещё не запущенного SpeechClock; stale/hold не будят чужой ticket.
Оба варианта требуют
fresh Hub/SDK preimages, finite stale/cancel/unknown/watchdog proof и causal review;
новые движения сейчас не выполняются.

Heartbeat разрешил только offline реализацию меньшего candidate: подготовлены
exact-7a5 patch/builder и request-stub fixtures, current installed source и HEAD
не изменены. [Local timeline_armed proposal](../../deploy/patches/timeline-local-armed-proposal.md)
использует отдельный exact clock/version/binding ticket; completed и все Hub/SDK
права/owned watchdog остаются прежними. Default/fallback — completion, explicit
local_armed opt-in не применён. 12 focused offline checks прошли; независимое
source review пока pending, hardware/latency/remote admission не приняты.
Это reviewable proposal, он не меняет runtime и не доказывает экономию .927 s.

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

**Состояние в конце того первого, NOT EXERCISED окна:** PC baseline ещё не был восстановлен. Runner — единственный
активный device owner — выполняет read-only classification и scoped recovery.
Нового runtime patch и повторного trial нет. После recovery следующий
поведенческий шаг — синхронизация начала человеческой фразы с фактическим capture
window. Нового runtime source fix без evidence нет. Не объявлять restoration,
quiescence, READY_NEXT или product PASS заранее.


Затем по прямой просьбе человека baseline восстановлен и выполнен **один повтор**
сообщая о фактическом capture active в его текущем чате для обоих окон. Человек
подтвердил, что оба ответа были слышны. Приняты owned STOP после наблюдения APLAY
3,054525 s и cleanup 0,399767 s; это software guard/cleanup span, не физический
E2E/P95. До следующего окна подтверждены terminal, producer/Piper quiescence.
Второй запрос обработан тем же candidate PC процессом, completed turn = 1.

На едином PC request clock получена **producer PCM/token overlap** в обоих случаях:

| Метрика | Первый ответ | Второй ответ |
|---|---|---|
| First semantic, s | 0,522609 | 0,602126 |
| First PCM yield, s | 0,630313 | 0,731289 |
| Last nonempty token READ, s | 0,928876 | 1,106271 |
| DONE READ, s | 0,929183 | 1,110466 |
| First segment chars / punctuation class | 2 / period | 61 / question |
| First Piper wait, s | 0,102501 | 0,118607 |
| First SoX, s | 0,004061 | 0,009230 |
| First cues, s | 0,000080 | 0,000201 |
| First segment prepare to audio yield, s | 0,106887 | 0,128304 |

Оба record прошли общий строгий 31-field parser: model POST attempted, terminal
и producer quiesced true; failed/overflow false. Это реальная проверка paired
schema и ранней выдачи PCM, не только 40 source checks/восемь fixture cases.
Но первый сегмент длиной два символа не доказывает содержательное начало речи.
Первый **наблюдавшийся** APLAY имеет bound POST+[1,265793; 2,273196] s, позже DONE.
Это не измерение точного acoustic onset и не доказательство, что onset был после
DONE: начало могло предшествовать обнаружению процесса. Второй acoustic/APLAY
onset и E2E speech-end timing не измерены. Поэтому meaningful **AUDIBLE overlap
NOT DEMONSTRATED**, полного streaming voice PASS пока нет.

**Независимо подтверждённое состояние после того повтора:** baseline running/
idle, точный protected config восстановлен, исходные brains/voice загружены,
content_tokens false, candidate parked, inventory сохранён, slot пустой. Robot
OFF/unowned/free, громкость 100%, factory running empty, no camera/aplay.
Camera socket-only read-only bind сохранён, Agent и camera helpers не менялись.
Тогда следующим source-only шагом был выбран exact Agent289 путь
first reply → expression.wait_timeline → first audio → APLAY start/write и
отсутствующее доказательство actual consumption; отдельно полнота первого
2-char сегмента в существующем parser. Нужны конкретные blocking gates и bounded
same-clock timestamps, без экспорта приватного ответа, нового framework,
искусственного delay или ACK. Continuous capture/partial STT — обязательный
последующий seamless этап; он не считается готовым по этому повтору.


Source audit exact Agent289 и установленных expression_player/speech_clock/router
подтвердил: перед APLAY есть wait_timeline gate до завершения обработки expression
HTTP-запроса; router read1/flush не ждёт целого ответа; SpeechClock остаётся wall-time
оценкой после pipe write, не actual consumption. Синтетически существующий parser
выдаёт 2-char segment для сокращения/номера списка, но реальная приватная категория
первого сегмента неизвестна. Удалять gate или менять сегментацию по догадке нельзя.

Подготовлен и затем установлен узкий измерительный checkpoint `2cacfbf` — exact Agent289
single-file overlay с одним first-only 21-field status record и общей схемой,
извлекаемой finite consumer из того же hash-pinned Agent без app imports:
[agent-stream-timing-rollout.md](../../deploy/patches/agent-stream-timing-rollout.md).
Он измеряет response open/reply/motion/audio line, timeline wait, APLAY Popen,
monitor start return и первую положительную запись в pipe; bind по PC content ID
и boot/mic/policy, nullable отсутствующие этапы, без текста/PCM/ошибок. Порядок
motion/audio/cancel/queue и все guards сохранены. 50 focused source checks прошли.

**Реальная установка `2cacfbf` независимо принята:** установлен exact Agent output
`c2fc…`, сервис имеет новый boot, начальный stream_timing null. Подтверждены
OFF/paused/unowned/free, громкость API/saved/ALSA 100%, отсутствие APLAY/camera.
Spoken/snapshot helpers, unit/config/profile/token/persisted state и factory
не менялись. Camera socket bind сохранён: PrivateTmp=yes, read-only mount и тот
же текущий socket inode в Agent/factory/host. PC baseline/config/исходные модули,
content_tokens false, idle, пустой slot и inventory сохранены. Это installation/
readiness PASS; **не feature/latency/overlap acceptance**. Старые boot-bound trial
pins не используются для нового запуска.

**Последний реальный measurement на c2fc:** человеку немедленно сообщили о
подтверждённом capture active в проверенном 75-секундном окне. Наблюдался один
`/stream/say` и ни одного model reply route; строгих PC model metadata нет.
Это **NOT EXERCISED для генерации ответа/LLM streaming**, а не установленный
дефект telemetry. При owned APLAY observer выполнил STOP: hold 3,0708 s,
cleanup около 0,390 s. Это STOP подготовленной речи, не STOP во время LLM-ответа.
После STOP read-only обращение к Hub завершилось transport error, второе окно
не открылось; guard восстановления сначала отклонил отсутствие model metadata.
Missing timing и отсутствие второго turn не превращаются в latency/overlap PASS.

**Scoped recovery полностью принят независимыми проверками PC, Robot и камеры:**
исходный процесс running/idle, protected config и исходные модули восстановлены,
content_tokens false, slot пустой, candidate parked, inventory сохранён.
Agent c2fc сохранён; OFF/paused/unowned/free, 100%, no APLAY/camera, factory empty.
Camera bind read-only, PrivateTmp и прежний socket сохранены. Recovery не вызывал
модель и не открывал новое окно. Ранее принятые producer PCM/token overlap,
реальный STOP LLM-ответа и следующий turn в том же процессе остаются отдельными
доказательствами предыдущего успешного цикла; содержательный acoustic overlap и
speech-end E2E по-прежнему не измерены.

Source audit и синтетический exact-c2fc fixture подтвердили: одинаковый audio
stream даёт timing для `/text` и `/turn`, а `/say` намеренно не создаёт model
probe. Конкретная причина выбора `/say` по одному route count не установлена;
приватный текст не нужен и не публикуется. Доказана ложная eligibility тестового
STOP observer: один APLAY допускал остановку до model reply. Узкий observer fix
SOURCE ACCEPTABLE после шести fixtures: перед началом прежнего 3-секундного hold
нужны current owned generation, валидный bound content ID, first audio и positive
write. Null/pending/invalid/noncontent игнорируются внутри прежнего окна.
User STOP и Agent не меняются; итоговая приёмка всё ещё требует строгого PC join.
Offline join и measurement method также SOURCE ACCEPTABLE; это не actual join.
Следующий реальный запуск ждёт свежего human ready и согласованного одного окна.
Нового runtime patch или автоматического повтора нет.

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

Ближайший обязательный continuous input инкремент разделён на два подэтапа.
S1 был заморожен на тогда установленном c2fc; текущий установленный default-off
Agent — cf50, не HEAD. Для S2 использованы свежие public installed preimages
recognition6211/barge-in и выбранный reviewed workerbbdb. S2 не меняет устройства
и не предполагает, что выбранный streaming bundle уже активен на PC.

**S1 SOURCE ACCEPTABLE и установлен с выключенной опцией; readiness независимо PASS:**
[builder/runbook](../../deploy/patches/capture-pump-S1.md). Exact c2fc Agent,
установленный barge-in и новый bounded helper собираются с frozen hashes;
свежие public preimages проверены, installed microphone/recognition отличаются
от HEAD и не заменяются. Focused fixtures включают реальный Agent.run с просроченным
STT без model dispatch/turn commit; один fake owned pipe через фазы; early monitor
до model open, default parity, primed playback без capture, TTL/revisions/STOP/CAS
и честный camera quiesce. Финальные PC/Robot/camera read-only проверки подтвердили default-off установку:
Agent cf50, OFF/paused/unowned/free/100%, arecord/APLAY/camera отсутствуют,
прежние config/helpers/unit/state/factory и camera bind сохранены; PC baseline
и пустой slot сохранены. Это installation/readiness, не real continuous hearing.
Старые c2fc boot/source/consumer pins устарели. Узкое обновление bound-LLM
measurement на текущие boot/source и canonical 21-field schema прошло review;
один такой human-прогон уже выполнен, его joined timings и recovery описаны выше;
прежний expressive hold позднее снят человеком, штатные движения снова разрешены.
38 focused checks прошли; два P1 закрыты: quiet/privacy withdrawal до reap и
общий bound source-error wake для return/exception. Это source evidence, не
continuous hardware/AEC/partial STT PASS.
Reviewed bound-LLM measurement уже дал actual timing evidence; source S1
не подменяет его и не считается принятой continuous hardware функцией. Будущий S1 acceptance
потребует отдельной paired consumer привязки к новому hash/порядку monitor timing.

**S1 — один capture pump текущего audio owner.** Сохранить существующий mono AEC
`arecord` через обычные idle → capture → STT/inference → playback: один reader,
один VAD/utterance assembler, один final claim для main/barge-in. `capture()`
становится consumer facade; barge-in подписывается на тот же поток уже во время
inference. Reader только читает/собирает bounded PCM и события; STT, classify HTTP
и синхронный `BargeIn.trigger` выполняет bounded control worker с прежними
AEC/echo/STT confirmation/permit guards. Active STT 1, pending latest 1; original
receipt/end/deadline, source generation, utterance/revision и boot/mic/policy
сохраняются без переомоложения копированием или завершением модели. Старый PCM
после длительного drain истекает; неизвестная continuity сбрасывает generation.
Receipt clock `arecord` не доказывает hardware capture time. OFF/STOP сразу
отзывает очередь и очищает PCM, затем reap reader вне удерживаемого mic lock;
listen=false не открывает capture. Stereo autonomous ALSA backend, второй PCM
owner и новый framework сюда не импортируются.

Принятый spoken camera guard требует честного capture_active=false: перед visual
child bounded quiesce/reap/clear pump, после child resume только по текущему grant
с новой capture generation. Это явный временный пробел слышимости во время vision.
Не скрывать reader флагом, не убирать guard и не переписывать helper ради pump.
Source fixtures проверяют one claim/TTL/generation/late result/STOP ordering.
Реальная S1 приёмка отдельно требует того же owned arecord PID через inference и
APLAY, near-end при inference/playback без self-echo, STOP reap/no resurrection,
отбрасывания late PCM после drain, свежего следующего turn и сохранённого spoken
camera через честный quiesce. Это ещё не partial STT PASS.

**S2 SOURCE ACCEPTABLE по независимым tester/architecture review; на устройствах не установлен:**
[точный builder и контракт](../../deploy/patches/provisional-stt-S2.md). PC overlay
на fresh recognition6211 и выбранный reviewed voicebbdb; Robot layer на S1cf50/b7b1,
HEAD и принятый S1 builder не меняются. Strict authenticated mode проходит до
любого sound/classify/LLM/history; один loaded recognizer/lock, failfast busy.
Robot — cadence/latest-only consumer, stable prefix по двум принятым revisions,
только RAM и status counts; VAD final остаётся прежним единственным dispatch.
Owned HTTP helper выведен из accepted a4aa pure transport без LLM/registry на Robot.
Durable metadata-only own intent до POST сохраняет unknown через reload; только
same-request authoritative completion/no-POST proof снимает собственный FI/digest
marker. Reader/STOP не ждут fsync/HTTP. Это source acceptance, не partial/AEC/
latency/continuous hardware acceptance и не новая причина отложить measurement.
33 focused checks прошли. Закрыты HTTP framing и namespace race: только полный
Content-Length/естественный EOF; весь Transfer-Encoding отклоняется. Кооперативный
fixed-directory flock с original deadline/cancel сериализует begin/complete;
неопределённость не создаёт новый бюджет или waiting workers в новых generations.
Ограничение против произвольного same-UID filesystem writer и OS fsync явно
описано в runbook; это не обещание атомарного CAS или реального latency PASS.

**S2 — recognize-only provisional STT.** Source opt-in в существующем authenticated
transcribe seam отделяет preliminary decode от LLM/classification/history/actions,
сохраняя тот же recognizer/model lock. Установленный wrapper fasterWhisper принимает
полное PCM окно: bounded
rolling snapshots с cadence, active 1/latest 1, stable prefix по двум revisions;
это повторное декодирование окон, не native online backend. Полный bounded final
после VAD endpoint проходит normal STT/intent ровно один раз с прежней session и
interruption semantics. Partials привязаны к utterance/revision/generations,
устаревшие partial/final отбрасываются, память и actions не коммитятся.
Timed-out STT с неизвестным состоянием не запускает дублирующий GPU request.
Source fixtures проверяют supersession/final once/no history и bounded admission;
реальная S2 приёмка дополнительно требует partial до VAD endpoint. Ни fixtures,
ни S1 не заменяют continuous/partial/acoustic hardware acceptance.

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
