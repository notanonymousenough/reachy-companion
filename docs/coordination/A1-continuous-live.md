# A1 — A0 installed, continuous PCM through normal voice

17 октября 2026, Europe/Moscow. **Exact A0 принят и оставлен в штатной службе с opt-in=true.** Один observed window90s завершён, без повторного live окна. PCM продолжался через обычные STT/main/APLAY в одной source_generation при работающем M0/M1 camera IPC producer. Normal listening восстановлен отдельным свежим guarded ON. Это ограниченная приёмка выбранного audio пути, не полная приёмка автономного компаньона, barge-in или физической свежести камеры.

Финальная проверка **04:25:03,481 MSK / 01:25:03,481 UTC**: Agent boot `f2a66c3b-dc89-4a2f-961d-ab738696b950`, PID205817, mic221 ON/listening/capture, generation3, policy116 motor=false/quiet=false/privacy=false, owners=null, volume100, last_error=null, interruptions0; Hub free/action_running=false/stock unknown=false, worker idle/ok=true. Единственный Agent arecord208199→205817; APLAY отсутствует. Factory PID150625/NRestarts0. Camera producer/listener/stage/grant/token отсутствуют. **A1 освободил аппаратное и инженерное владение.**

Входы: [A0](A0-continuous-capture.md), [M1](M1-camera-live.md), [runtime baseline](runtime-baseline.md), [PROJECT](PROJECT.md). Других чатов/подагентов не создавал. Worker, модели, camera source, автономная session, factory/Docker не изменялись/не перезапускались. Не запускались второй Agent, второй recorder, второй ASR или AEC.

## Exact installed manifest и применение

Свежий preflight подтвердил mic215 ON, policy116, прежний boot/PID199098, Hub free и worker idle. Python resolution через тот же venv/PYTHONPATH systemd показал effective imports из `/home/pollen/reachy-companion/src/reachy_companion/`. Проверены **все** pins A0, не только Agent; mismatch отсутствует. Исторический boot SHA из M1 не использовался как payload: все CAS брали свежий raw boot ID/epochs.

| Effective файл | До | После |
| --- | --- | --- |
| `agent.py` | `4e2dcafdde29ba667ae40c240723954d48b8462f9641e50ffb32e56fe0ce575a` | `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b` |
| `capture_pump.py` | `b7b1ffa551d8b3ad4346cc2920f0e17d04e37c2300d8583abf336ea90fb9e5b0` | `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6` |
| Reachy `config.local.json` | `7f11d114873cc20de66e4789166ed5bbbd32109f708f82991aeb5ab3217d3b5e` | `a6171f68e6fc20feebb48475991517f61412afc693f0c58f999f077f0eedd0d5` |

Config semantic diff **ровно** `conversation.capture_pump_enabled`: absent→true; проверено сравнением JSON после удаления только этого поля. Форматирование JSON изменилось, прочие значения совпадают. Hub config остался прежним. Agent/capture_pump mode0664 uid/gid1000:1000, config0600 uid/gid1000:1000 сохранены.

| Неизменённая dependency | SHA-256 |
| --- | --- |
| barge_in.py | `28831114f2cf0f60f47d3bdd77c4f8d120b6447101ff5adc56df46204eb247bf` |
| microphone.py | `d35ef6d3e0cc289e8043a0da68480ecd110ef3fff98afb81da0afad25e416129` |
| motion_policy.py | `d224385e999a0c6056db42e1fc3a3c90afaa2009336eaf1ef364037dc98a8466` |
| config.py | `c0b0e7a8470401a20b684ada3132784e0805333f9ab56c18b1f8d585d7eb3436` |
| sound_monitor.py | `89e7f782aade878f84fdb0760f95605d97d266c0a476bdb56a213b3d932d7c29` |
| spoken_vision.py | `486cfb8f23c9d9d5797910eab6ebf3143e64f1cfe4a686b4f50fe38db975a025` |
| snapshot_vision.py, дополнительная проверка | `d43a70cc1e3b3846cb163f8b772c9af2b13a08aefac2c4279f6197b68b974c13` |

Builder `prepare_continuous_capture.py` создал exact bundle в новом `/private/tmp/reachy-A1-bundle`; HEAD runtime не переносился. Полные preimages/config, stat metadata и manifest сохранены **на Reachy** в root-only0700 `/var/tmp/reachy-A1-rollback-01a1476b/`; private config/token в публичные evidence не копировались. Persisted microphone-state не заменялся.

Последовательность: backup → fresh guarded OFF215→216 → paused/no Agent PCM child → stop Agent → заменить только два source файла → compile/hash → controlled start с прежним default false. Default-false ON217 подтвердил finite capture/capture_pcm=null, затем fresh OFF218. После paused/no capture добавлен только opt-in, второй controlled restart, новый boot `f2a66c3b…`, OFF218. Worker/factory не перезапускались. Boot transition ON не отправлялся до paused: client guard отверг раннюю попытку до POST.

Технические поправки **до live**: большой exact payload передан SSH stdin вместо превышения argv limit; Hub `/control/status` фильтрует новые counters, поэтому authenticated Agent `/status` читался через собственный loopback SSH forward. Никаких source fixes кандидата по ходу установки не было.

В [factory_ssh.py](../../scripts/factory_ssh.py) добавлен только конечный env parameter `REACHY_FACTORY_SSH_LIFETIME_SECONDS`, default65, допустимо10…600. Setup transport закрыт отдельно; live использовал240s. Внутри90s window transport не оборвался. После окна его конечный lifetime закончился до поздней выгрузки producer report; для cleanup открыт отдельный конечный transport, затем явно закрыт. Это не повтор live окна. Все свои SSH transport закрыты; служба Agent продолжает работать независимо.

## Измерения одного окна

Окно примерно **04:17:33–04:19:03 MSK**; UTC привязан к local file receipt, не к физическому capture timestamp. Точные интервалы ниже — local monotonic elapsed.900 status observations (~100ms), полный `/proc` scan Agent cgroup (~200ms), а не children только main thread. Одна совместная status/worker строка получила URLError на64,796s; это пропуск наблюдения, не доказательство PCM gap. Audio counters во всех полученных строках gaps=0/overflow=0.

Свежий normal ON218→219. Generation1/arecord205935 читала до initial manual speech. Единственный намеренный стимул — штатный `/robot/say`: **«Алиса, сколько будет два плюс два?»**, started32,55s/completed36,41s. Этот существующий manual endpoint retire-ит pump; generation1 закончилась1 040 384B, затем создана generation2/arecord206483. **Поэтому90s единого непрерывного source и непрерывность через manual `/say` не заявляются.** Никакого synchronous spoken snapshot не было.

После seed одна generation2 охватила реальные ответы Алисы и все три автоматических STT→main→APLAY хода; turns0→3. Новых инженерных стимулов не было. Первый external STT имел1 слово/6 chars; raw transcript/PCM не сохранены. Первое playback заняло около3s, последующие7,64/8,50s: строгая краткость всего обмена не принята. Акустический speaker identity каждого последующего input не измерялся; отсутствие own-echo после bounded tail **UNKNOWN**, новые inputs вне mask не доказывают AEC. Effective speech prefix `Алиса, ` сохранён, установленный TTS нормализует уже начинающуюся с Алиса фразу без удвоения prefix. PC `/status.last_turn` оказался старым/некоррелированным для streamed output: его длины в `voice-metadata.json` **не являются** A1 shortness evidence.

| Наблюдаемый интервал generation2 | elapsed, s | Реальный delta bytes / frames | Agent capture / playback PID |
| --- | --- | --- | --- |
| STT второго хода, консервативная часть |51,024…51,420 (0,396s)|12 288B /6 144 frames|arecord206483, APLAY отсутствует|
| STT третьего хода, консервативная часть |69,099…69,740 (0,641s)|20 480B /10 240 frames|тот же arecord206483|
| main первого хода, worker thinking |39,549…40,253 (0,704s)|22 528B /11 264 frames|тот же arecord206483|
| main второго хода |51,628…52,465 (0,837s)|28 672B /14 336 frames|тот же arecord206483|
| main третьего хода |69,877…70,831 (0,954s)|30 720B /15 360 frames|тот же arecord206483|
| Own APLAY1 + mask |40,445…43,444 (2,999s)|98 304B /49 152 frames|arecord206483 /aplay206608|
| Own APLAY2 + mask |52,879…60,519 (7,639s)|243 712B /121 856 frames|arecord206483 /aplay207011|
| Own APLAY3 + mask |70,831…79,330 (8,499s)|268 288B /134 144 frames|arecord206483 /aplay207570|

STT attribution — **вывод из exact Agent control flow и наблюдений**, не новая worker метрика: installed `/transcribe` не устанавливает worker.phase=recognizing. Выбраны только Agent.processing/worker.idle строки **до появления нового `stream_timing.started_monotonic`** этого хода; время HTTP call само по себе не измерялось. Первая такая часть0,252s короче критерия300ms и отдельно его не закрывает. Второй/третий интервалы закрывают byte progression во время ожидающего STT пути в той же generation; packet acquisition/STT result/main не подменены одним capture_active.

Generation2: от36,536 до80,089s (43,552s) +1 390 592B/+695 296 frames ≈**15 964,6 frames/s** (−0,22% к16k при sampled boundaries). Финальный drain перед STOP дал1 398 784B/699 392 frames; вычитание между generation не делалось. Generation1 sampled32,524s ≈15 962,7frames/s. Short interval rates имеют polling/chunk quantization, не используются как акустический rate meter.

В generation2 `suppressed_frames=321600`, own-output mask виден при всех APLAY; новый processing episode не начинался под маской. Максимум raw staging6784B <discard threshold12800B <capacity28799B; sampled pending_events=0 (код ограничивает slot одним), assembler max230400B, gap_events=overflow_events=superseded_events=0, max read receipt gap0,128935s. Максимум одновременно Agent arecord=1. Один synthetic/offline набор89 tests также PASS; это отдельно от live.

## Camera coexistence, privacy и STOP

Exact M0 producer SHA `6182a6516d93d4ab065c1ba5ba0c3c6fe8ebfb57e28f08d7dea8f83a8139ae56` временно stage в `/tmp/a1-camera-01a1476b`, `/venvs/mini_daemon/bin/python`, прежний factory IPC socket/namespace. SDK camera SHA `631266c0e53223463cb5a226b12201e4cc263134d016405656d9de9ae35400c6` совпал с M1. Installed producer `80199eb7…` не заменялся. Producer duration60s, consumer55s, начаты27…28s общего окна; конец camera admission охватывает все три голосовых хода и audio STOP80s.

Прежний M1 `video_adapter_probe` использовал настоящий decoder/LatestFrameProcessor/LatestVideo на Mac через loopback18772→8772. Только конечные timings/privacy phases адаптированы; source/scheduler/context session не менялись. Remote scope epoch219 был свежим и до STOP не менялся. После STOP нового admission **не было**.

- Producer **354 published**, gaps1 (camera acquisition/start/reopen gap counter, не audio counter), capture_thread_reaped=true, reader_shutdown_unknown=false, raw_files_created=0, audio_or_motor_commands=0.
- Consumer **157** разных frame IDs и157 pixel SHA, один producer boot,104 до privacy и53 с новым admission после privacy. Реальные changing pixels одновременно с mic ON и generation2 PCM; это consumer code на Mac, не новая интеграция в PC normal context/session.
- Remote video privacy=true в consumer32…34s:12 HTTP503 observations, decoded0. Затем privacy=false со **старым** admission34…36s:11 HTTP503 и один timeout, decoded0. Только свежий admission после36s снова дал53 packets; конечный owned-policy close подтверждён (`owned_policy_close_unknown=false`). Одна camera poll timeout также есть в coexistence/fresh phases; непрерывность каждого кадра не заявляется.
- Audio STOP fresh CAS219→220 отправлен80,133s, ответ80,282s, capture_active=false/listening=false. После него101 sampled rows имеют неизменные1 398 784B, capture=false, turns3; полные cgroup observations после перехода пусты, cleanup повторно подтвердил отсутствие Agent arecord/APLAY. Старый camera admission после STOP получает503; его последний decoded packet пришёл до STOP. После этого камера не возобновлялась.
- STOP пришёл в listening, **не внутри STT**. Live late-STT cancellation race **UNKNOWN**, его offline A0 test PASS отдельно. Agent privacy_all round-trip в этом окне не выполнялся; camera privacy — отдельный grant и не доказывает Agent privacy round-trip.
- Все157 camera packets: **pts_ns=0, buffer_running_time_ns=0**. PTS progression FAIL остаётся прежним. `source_capture_time_verified=false`, exposure mapping/age upper **UNKNOWN/null**; новые software receipt timestamps не названы physical freshness.

## Раздельные verdicts и эксплуатация

| Область | Вердикт |
| --- | --- |
| PCM через обычный STT/main/APLAY | **PASS в измеренной generation2/43,55s**, counters и один PID, gaps0/overflow0.90s single-source и manual `/say` continuity не приняты. |
| Voice | **PASS для реального ответа и завершения turn**, три автоматических хода после одного seed. Строгая краткость всего обмена не принята; full barge-in/AEC не заявлены. |
| Camera coexistence | **PASS для changing-pixel IPC consumer при PCM/voice**, privacy old-admission fence и STOP. PTS progression FAIL; physical freshness UNKNOWN; PC context integration не сделана. |
| STOP | **PASS для reader reap/counters stop/no late observed APLAY/turn и camera old admission**, live busy-STT race UNKNOWN. |
| Normal listening handoff | **PASS**, новый ON220→221 только после cleanup/fresh paused/free/idle preflight; generation3, read bytes36864→51200, в финале1 267 712B, один arecord208199. |

Решение: сохранить exact A0+opt-in как работающий audio candidate. Следующий scope — normal joined context/session; известные manual `/say`/spoken snapshot retire gaps и camera PTS0 не скрывать. Никакого бесконечного повтора или buffer widening по результатам этого окна не было.

Rollback при необходимости: fresh guarded OFF, дождаться paused/reader reap; при UNKNOWN не создавать replacement. Убедиться, что оба runtime hashes равны A0 outputs, config равен `a6171f68…` (чужие изменения не затирать). Остановить только `reachy-voice-agent`, восстановить `agent.py`, `capture_pump.py`, `config.local.json` из `/var/tmp/reachy-A1-rollback-01a1476b/` с сохранёнными mode/uid/gid, проверить hashes/compile, controlled start. **Не восстанавливать старый persisted ON state.** После нового boot/OFF/free/idle preflight отдельный свежий guarded ON возвращает принятый R1 finite listening. Factory/Hub/PC/Docker для этого не останавливать. Rollback в A1 не потребовался.

Evidence: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a1476b-c451-7361-a82d-c25202dce0dd/A1-evidence/`. Основные receipts: `preflight-robot.json`, `rollback-manifest.json`, `install-false.json`, `default-false-*.json`, `activation-config.json`, `pcm-status-observations.json`, `pcm-process-observations.json`, `live-events.json`, `analysis.json`, `consumer-report.json`, `cleanup-installed.json`, `normal-ON*.json`, `final-http.json`, `final-robot.json`. `analyze.py` воспроизводит таблицы офлайн, не загружает Config/credentials. `SHA256.json` фиксирует payload files; PCM/images/private config/token в evidence отсутствуют.

Evidence manifest:35 payload files, `SHA256.json` SHA-256 `86a30a2eefb69e4efcbb6c4762271e65904f678d1c943871a716299c5fb474ef`. Local `git diff --check` прошёл; чужие/параллельные изменения working tree не откатывались.
