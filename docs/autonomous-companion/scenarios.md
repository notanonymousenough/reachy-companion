# Временные сценарии и наблюдаемые результаты

Время ниже — иллюстративное при fast period 1 s, не фактический замер. Сенсоры и safety продолжаются между tиками. Модель может выбрать другую уместную реакцию; приёмка проверяет инварианты, а не обязательную фразу. fixtures не обозначают реальный шум, температуру или событие установки.

## Тишина и чувство непрерывности

| Время | Кэш и фон | Новый LLM-запрос | Внешний результат |
|---|---|---|---|
| 0 s | Свежие audio RMS/scene, muted=false | observe, camera describe task | Спокойная поза, возможно короткий взгляд |
| 1 s | VLM pending, очереди/возраст изменились | wait + hold activity | Не перезапускает взгляд, не говорит |
| 2 s | Scene ready; часы/idle/attention age | focus на старом интересе | Может остаться неподвижным |
| 3–60 s | Реальные RMS/RTT updates, habituation, simulated arousal decay | Новый запрос каждый tick; summary wait interval | Косметика по lease с низкой частотой либо покой |
| 10 min | Незавершённый интерес, quiet=false, initiative budget ready | Иногда короткая инициатива по содержанию | Один вопрос; отсутствие ответа закрывает попытку до нового основания |

Успех: нет fabricated events, fast attempts продолжаются, лог не растёт полной копией snapshot каждый tick, внешний покой допустим. Quiet hours блокируют инициативную речь, но не запросы.

## Разговор и незаконченная медленная задача

0,0 s: capture/VAD видит речь, speaker idle. 0,2 s: partial STT job идёт, старый final помечен предыдущим turn. 1 s: L0 выбирает listen/focus, не отвечает на partial вопрос как на полный. 1,8 s: final «Почему радуга круглая?» получает utterance revision. 2 s: L0 запускает L1 answer, без обязательного «хмм». 3 s: L1 ещё pending, L0 wait/focus, внимание удерживается. 3,5 s: main proposal готов по тому же turn и попадает в ready_proposals. 4 s: новый L0 выбирает speech.commit; после guard TTS CPU начинает первый законченный сегмент. 5 s: L0 converse/hold, видит playback cursor и своё speech evidence. В конце PCM ledger отмечает завершение; речь не повторяется новым fast tick.

Если задаче нужна web-проверка, L0 продолжает запросы весь tool run. Optional одна фраза «Проверю точнее» допустима только по новым social conditions, intent cooldown и перед реальным запуском инструмента. Ни один тик не ждёт готовности ответа в task pool.

## Шум / возможное падение: четыре итерации

| Tick | Получено | Асинхронная работа | Решение |
|---|---|---|---|
| I1, 0 s | Тишина, кадр F1 | Запущена VLM F1 | observe, спокойный взгляд |
| I2, 1 s | Резкий шум S1, class unknown | Audio A1 queued/running; VLM ещё pending | focus/observe, небольшая ориентировка, без утверждения «падение» |
| I3, 2 s | Новый звук S2 | A1 active; A2 queued; CPU classifier независим | hold реакцию, новый LLM-запрос; не второй испуг |
| I4, 3 s | A1 ready: удар/предмет, confidence средняя | A2 ещё pending; новый relevant camera frame | Может сказать «Что-то стукнуло»; «кто-то упал» только гипотеза при подтверждающей сцене |

Если человек уже объяснил «это я положил книгу», позднее A1 не инициирует тревогу: hypothesis superseded, result archived или update evidence того же эпизода. Фраза «ой, кто-то упал» допустима лишь с дополнительным evidence и актуальностью; акустический classifier сам по себе этого не устанавливает. Без DOA неизвестно направление шума: робот может сделать исследовательский осмотр, но не притворяться точной локализацией.

## Музыка, вокал, несколько людей

0–2 s: YAMNet повышает music score на двух окнах, VAD отдельно отмечает vocal/speech ambiguity. 2 s: L0 может предпочесть слушать, танцевать или продолжить разговор с учётом личности, quiet и goal. Если выбран dance, один конечный motif plan 4–8 s с отдельным transport lease500 ms, head bounds и rhythm confidence. Каждый последующий fast tick решает hold/settle/change, но не запускает новый танец поверх старого. Через 5 s обращение человека получает более высокий attention score; dance мягко затухает. Два человека говорили одновременно → STT uncertain/unassigned, возможен короткий уточняющий вопрос, без выдуманной идентификации.

Музыкальный режим не может полностью запрещать STT: нынешний подход с suppression speech-turns теряет обращения поверх музыки. Новая схема разделяет classification и turn-taking. AEC reference — фактически проигранный PCM с timestamps/cursor; моторные шумы — pose/command correlation, но не автоматическое доказательство отсутствия внешнего звука. Hardware XVF3800 из README — прежнее свидетельство, настройки и эффект проверяются отдельно. Проверки: громкость, distance, self speech, echo, vocal music и overlap. Нельзя глушить всё mic input на время собственного ответа: перебивание остаётся доступно.

## Перебивание и «замолчи»

Во время playback local/PC fast VAD сообщает вероятное обращение → звук приглушается/пауза; STT подтверждает чужую речь. Interaction epoch увеличивается, main answer/TTS/cue старого turn cancel. Если подтверждающий STT завершён empty/self echo до подтверждения нового turn и input не был stop/mute, interaction epoch не увеличивается: buffered PCM продолжается после 3000 ms непрерывной подтверждённой тишины по hub monotonic clock, только с сохранением dependencies и verified cursor. Pending STT задерживает resume даже после 3 s; no_data/offline обнуляют silence coverage. Точные guards и late-final handling заданы в contracts 1.1. После подтверждённой новой реплики auto-resume запрещён; новый текст не генерируется автоматически. Это продолжение отражается в ledger.

«Замолчи» распознаётся ограниченным urgent stop path на ПК (STT/keyphrase), без ожидания основной LLM. После подтверждения hub и robot сохраняют microphone disabled, увеличивают epoch, прекращают capture/PCM, удаляют незавершённые записи и отменяют cue. Ни перегрузка, ни reconnect, ни перезапуск, ни личная goal не включают его обратно. Кнопка включения — явное действие оператора и новый epoch; прошлый ответ не возобновляется.

Кнопка mute может дать исполнение за сотни миллисекунд без модели. Голосовая команда зависит от акустического окна/распознавания; нельзя обещать 100 ms от произнесённого слова. При недоступном ПК кнопка/локальный аппаратный stop остаются, новое понимание речи не обещается. В проекте отдельный будущий urgent STT lane или keyword detector на ПК, не inference на hub.

## Перегрузка и зависшая задача

0–5 s: main/VLM latency растёт, L0 продолжает запросы. 5 s: PRESSURED, main admission ограничен, новые VLM coalesce, fast на CPU с коротким snapshot. 10 s: WITHDRAWN, L0 выбирает think/wait, внешние новые reactions suppressed; optional один раз «Я запутался, дай секунду». 12 s: web результат готов, но уже старый turn → archive. 15 s от входа: drain deadline, cancel все неактуальные jobs, собрать итог по готовому. Через cancel grace незавершённый worker становится quarantined и больше не влияет на мир. RECOVERING требует 3 валидных fast ответа и 10 s нагрузки ниже low thresholds; нельзя возвращаться ACTIVE каждые полсекунды.

Если GPU main завис, CPU fast остаётся. Если fast сама недоступна, mode=MODEL_UNAVAILABLE, gap logged, bounded probes. Нельзя называть cached wait новым вызовом LLM. Кнопки и local watchdog продолжают работать. Температура без реального датчика не фигурирует как аппаратное объяснение.

## Потеря сети

Hub–ПК lost: sender deadlines истекают, remote results не принимаются без текущих epochs. Если fast доступна отдельным сетевым endpoint — цикл продолжается; если единственный ПК недоступен, LLM gap и circuit breaker. Hub удерживает safety и operator state; никакой незаявленной inference на RPi. После reconnect свежий snapshot, flush старых commands, health и RECOVERING. Старую «интересную мысль» можно сохранить как memory proposal, но не озвучить автоматически.

Hub–Reachy lost: cognition на hub может продолжаться, observation availability=offline, pose stale, motion rejected, речь не считается произнесённой. Robot local lease истекает и прекращает playback/cosmetic motion. После связи не догонять очередь жестов и фраз. Если local watchdog ещё не реализован, это известный провал safety acceptance, а не обещание мгновенной остановки через разорванную сеть.

## Выключенный микрофон

0 s: persistent mute. Аудиоплагины stop, queued/in-flight audio results от старого epoch rejected, RAM очищена. 1 s, 2 s и далее: новые L0 запросы видят mic=disabled, аудио unknown, не «тишину». Камера/время/очереди/внутренние интересы могут продолжать обновляться, если их отдельная policy допускает. Текущий mute-сценарий останавливает текущую речь; инициативную речь по умолчанию также блокирует, хотя mute и quiet — отдельные понятия. Новая текстовая команда оператора может разрешить отдельный say, не включив mic. Privacy-all режим дополнительно отключает камеру и внешнюю отправку.

После кнопки on создаётся новая audio session, baseline recalibration идёт в фоне, до свежих значений scene содержит empty/pending. Модель не слышит задним числом события mute-интервала.

## Потоковый speech pipeline 1.1 и владение каналами

Аудиовход несёт capture_session_id, producer_boot/seq, sample interval и playback reference. Ring RAM на ПК initial 10–20 s по privacy policy, frames 20–100 ms; сеть отправляет bounded chunks, без Base64 аудио в LLM prompt. При backlog expired partial windows discard, final utterance admission отдельно. Clock mapping задаёт origin sample index → hub time и uncertainty; dropped frames имеют gap event. AEC reference — фактический playback cursor с start/stop/underrun, а не весь синтезированный текст. Повторная передача chunk не значит повтор capture.

Whisper Small в существующем коде принимает законченные фразы. Для streaming проектируется адаптер incremental repeated windows + stable-prefix agreement: совпавший prefix двух последовательных декодов marked stable, provisional suffix может меняться. [Первичная реализация Whisper-Streaming](https://github.com/ufal/whisper_streaming) применяет local agreement; это отдельный проект и не обещает заданную задержку/доступность native streaming Faster Whisper на этой установке. Окончательная граница определяется VAD/hangover и речевой пунктуацией как подсказкой, но timestamps исходного окна сохраняются. Пустое window/несогласованная гипотеза не подтверждает новую реплику. Thresholds/final latency измеряются в шуме.

Main streaming не означает озвучивание любого token. Baseline получает полный валидный MainProposal и запускает TTS после speech.commit. Более быстрый профиль использует MainSegment events: каждый законченный сегмент имеет proposal/task/segment ids, causal binding, seq, text, final flag и dependencies. Только полностью провалидированный sentence segment попадает в ready_proposals; L0 один раз выбирает speech.commit, открывая конечный speech plan. Следующие сегменты того же proposal могут поступать в рамках этого plan после guard на **каждом** enqueue, без повторного L0 commit/нового жеста. L0 продолжает решения, может отменить или изменить внимание. Model header/незакрытый JSON/reasoning/tool progress не могут начать TTS.

Если runtime выдаёт только полный JSON, baseline честно ждёт весь proposal; нельзя называть TTFT временем первой слышимой речи. Если безопасный segment protocol не поддержан, adapter может делать отдельные bounded L1 sentence calls с компактным scene/answer plan, но требуется consistency test и дополнительные prefill расходы. Header/segment pipeline не даёт модели исполнения tool до policy check; tool request остаётся отдельным намерением. Разрешённый speech plan ограничен initially 30 s, queue ready PCM ≤2 s, transport buffer target 100–250 ms; длинный ответ требует нового admitted continuation, не unlimited lease.

| Канал | Единственный владелец | Что запрещено |
|---|---|---|
| Mic capture | Robot capture actor под operator microphone epoch | LLM/agent self-enable, чтение после mute |
| Speaker | Robot PCM actor под playback_id/speech_epoch | Два aplay/daemon sound/старый replay одновременно |
| Head/antennas | Hub arbiter + robot guarded motion actor | Старый ExpressionPlayer и новый tracking оба writers |
| Daemon safety | Штатный daemon + hub policy; local watchdog only revoke | LLM torque/raw serial controls |
| Main slot | PC model broker | VLM/main bypass общей очереди |

Daemon wake sounds/media приложения учитываются как other speaker owner. Без observable ownership/PCM reference не гарантировать AEC/interrupt quality; блокировать новый speech admission или тестировать coexistence отдельно. Motion intents отменяются сначала по lease, затем плавный safe halt; gravity/torque disable не считать универсальной безопасной остановкой головы. Без hardware проверки механического поведения ограничить косметику существующими bounds.

Playback clock: segment → sample range → actual consumed samples; cues имеют sample offset, min spacing и expire-after, а не только wall timestamp. При underrun pause motion cues, не проигрывать «кивки» по неозвученной фразе. При pause сохранить consumed cursor с backend uncertainty; если cursor неизвестен, auto-resume запрещён: discard и acknowledge uncertainty после нового запроса. Не обещать sample-exact resume через opaque aplay без фактического cursor API. После restart playback unknown, не resume.

Music/vocal handling: audio classifier labels идут рядом с STT, не отключают его; обращённость речи, stable words, DOA при наличии, speaker confidence и AEC contamination — отдельные evidence. Собственная речь с низким residual SNR снижает confidence STT, но подтверждённое обращение поверх неё не suppress. Severe acoustic overlap даёт «не разобрал» либо wait/refocus, не fabricated content. Метрики по отдельности: self-turn false triggers/min, external speech recall при music, end-to-stop latency, speaker leakage в STT и accidental resume после настоящего interruption.

## Сценарии регрессии второго прохода

| Инъекция | Ожидаемая последовательность |
|---|---|
| Main ready между двумя L0 ticks | Reducer добавляет proposal_id/summary/deadline в ready_proposals → новый FastChoice commit → guard → started; не auto-speech из result handler |
| Main partial, затем final и duplicate segment | Один committed plan; seq dedupe, gap hold и bounded retransmission; duplicate не повторяет слова |
| Suspected interruption, STT empty | Pause PCM, не меняет interaction_epoch; после ≥3000 ms healthy silence resume того же playback при verified cursor и unchanged operator/speech/boot; pending STT ждёт, unknown hearing запрещает resume |
| Нераспознанная внешняя речь продолжается | Каждый свежий speech interval сбрасывает silence timer; empty STT сам по себе не разрешает resume |
| STT pending дольше 3 s / hearing offline | Pause сохраняется; settled empty после 5 s может resume при непрерывной healthy silence, outage требует новых 3 s после восстановления |
| Cursor неизвестен / late final после resume | Без cursor discard; поздний валидный confirmed turn revoke старого playback и epoch++, никаких повторов фразы |
| Confirmed interruption, потом запоздалый old main | interaction_epoch++, old speech/cues revoked; old result archive, fast видит новый turn; no automatic resume |
| Mute, on, старый partial/keyword | microphone_epoch changed дважды; old audio/stop detector result rejected; включение не возвращает старую речь |
| Hub restart, тот же integer interaction epoch | Новый hub_boot/fencing; все старые action bindings rejected до resync, память historical допустима |
| Fast timeout, HTTP закрыт, worker ещё busy | Result lease revoked, execution permit удержан; новые nominal opportunities записывают gap и probe, не второй parallel fast job |
| Network jitter 350 ms + lease500 ms | Отдельный 100 ms heartbeat, bounded retransmit; lease expiry safe halt; L0 1 Hz не является heartbeat |
| Slow VLM capture 0 s / completed7 s / scene moved2 s | Historical scene evidence; нельзя увеличить captured_at до7 s и отвернуть голову к исчезнувшему track |
| 10 min offline S3, reconnect | Те же immutable batch ids/digests; verified uploaded не обязательно processed; analyzer dedupe и receipts отдельно |
| Offline сверх disk retention | Low priority shedding, затем explicit critical loss markers/fail-closed admission; no «без потерь навсегда» |

Все времена/слова этого раздела — synthetic сценарии. Перед live actuator тестами реализуются epochs/fencing и контроль остановки, а не наоборот.
