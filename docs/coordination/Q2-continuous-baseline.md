# Q2 — независимая проверка continuous baseline

17 октября 2026, Europe/Moscow. Финальный свежий снимок: **04:30:25,388 MSK / 01:30:25,388 UTC**. **Обычный continuous voice путь A1 принят в измеренных пределах; текущий exact A0+opt-in продолжает normal listening ON.** Q2 выполнил только чтение saved metadata и два свежих status/cgroup/import снимка. Нового диалога, finite runner, recorder, camera admission, POST, restart, model load или моторных/GPIO команд не было. Baseline и код не изменялись; чаты/подагенты не создавались.

| Claim | Verdict | Основание и граница |
| --- | --- | --- |
| Одна PCM generation через обычные STT/main/APLAY | **PASS** | A1 generation2, 43,552312 s, +1 390 592 B / +695 296 mono frames, один arecord206483→Agent205817, gaps0/overflow0. Не весь 90 s window. |
| STT byte progression | **PASS, с attribution inference** | Консервативные части второго/третьего STT пути: 0,396322 / 0,640669 s, +12 288 / +20 480 B. Worker recognizing не измерен; точная длительность HTTP STT неизвестна. |
| Main и собственный playback при продолжающемся PCM | **PASS** | Три thinking интервала и три speaking+mask интервала с положительными byte deltas; тот же capture PID/generation. |
| Suppression и отсутствие измеренных потерь | **PASS в окне** | suppressed_frames321600; gaps/overflow/superseded0, max receipt gap0,128935 s; sampled processing episode под own-output mask не начинался. Это не AEC/barge-in acceptance. |
| Обычные завершённые voice turns | **PASS** | После одного manual seed turns0→3. Строгая краткость и speaker/echo identity всего обмена **UNKNOWN / не приняты**. |
| Непрерывность через manual `/say` и synchronous spoken snapshot | **FAIL как общее свойство** | Manual `/say` реально retire-ит generation1; snapshot код также retire/close/suspend. Live snapshot в A1 не запускался. |
| Camera changing pixels одновременно с voice/PCM | **PASS в saved evidence** | 157 разных frame IDs и pixel SHA, один producer boot; 354 published. Это отдельный Mac IPC consumer, не normal PC joined context. |
| Camera privacy fence и STOP | **PASS в наблюдённых пределах** | При privacy и после её снятия со старым admission decoded0; возобновление только с новым admission. STOP остановил Agent reader/counters и старый camera admission; producer reaped. |
| Camera PTS progression / physical freshness | **FAIL / UNKNOWN** | Все 157 pts_ns и buffer_running_time_ns равны0; source_capture_time_verified=false, age upper=null. Software receipt не доказывает экспозицию. |
| STOP во время busy STT / Agent privacy_all round-trip | **UNKNOWN live** | A1 STOP пришёл в listening; camera grant privacy не заменяет Agent privacy. Offline late-STT test не повышает live verdict. |
| Текущее штатное состояние и installed identity | **PASS, два снимка** | Exact hashes/opt-in, mic221/generation3, counters растут, один Agent arecord, Hub free, worker idle/ok. |

## Независимый пересчёт A1

Прочитаны [A1](A1-continuous-live.md), [runtime baseline](runtime-baseline.md) и соответствующие A1 evidence/analysis; спора, требующего перечитывать A0/истории, не возникло. Источник: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a1476b-c451-7361-a82d-c25202dce0dd/A1-evidence/`. Проверены все **35/35** SHA payload files без mismatch; SHA256.json=`86a30a2eefb69e4efcbb6c4762271e65904f678d1c943871a716299c5fb474ef`. `analysis.json` не использован вместо исходных observations и не перезаписывался.

Из `pcm-status-observations.json`: первые/последние **non-retired generation2** rows имеют elapsed36,536260083→80,088572250, read_bytes0→1390592, read_frames0→695296. Поэтому Δt=43,552312167 s, rate=695296/Δt=**15 964,617 frames/s** (−0,221% от16k при polling/chunk boundaries). Это mono S16_LE frames=bytes/2, реальные `os.read` counters; clock=`monotonic_read_receipt`, не аппаратные sample/exposure timestamps. Финальные после STOP1398784 B нельзя подставлять в этот active interval или вычитать между generation.

| Saved interval, elapsed s | Δt, s | ΔB / Δframes | Связь |
| --- | --- | --- | --- |
| STT 51,024133→51,420455 | 0,396322 | 12288 / 6144 | processing + worker idle до нового stream attempt |
| STT 69,099464→69,740133 | 0,640669 | 20480 / 10240 | тот же критерий |
| Main 39,548566→40,252979 | 0,704413 | 22528 / 11264 | worker thinking |
| Main 51,627730→52,464849 | 0,837119 | 28672 / 14336 | worker thinking |
| Main 69,877104→70,831223 | 0,954119 | 30720 / 15360 | worker thinking; последняя граница пересекает mask |
| APLAY1+mask 40,445225→43,443738 | 2,998512 | 98304 / 49152 | aplay206608 |
| APLAY2+mask 52,879048→60,518531 | 7,639483 | 243712 / 121856 | aplay207011 |
| APLAY3+mask 70,831223→79,330088 | 8,498865 | 268288 / 134144 | aplay207570 |

Весь этот участок связан с **arecord206483, PPID205817, start_ticks60450187** по полному Agent cgroup scan в `pcm-process-observations.json`; максимум одновременных Agent arecord во всём saved окне=1. Process/status polling асинхронен (~200/~100 ms); PID attribution использует соседние observations, не точную границу syscalls. Первая STT часть0,251740 s/+6144 B не закрывает критерий300 ms. STT вывод основан на hash-pinned `agent.py`: processing устанавливается перед синхронным `/transcribe`, новый stream timing начинается затем в `voice('/text')`; installed `/transcribe` не выставляет worker recognizing. Main attribution использует worker thinking; playback — Agent speaking/output_suppressed и отдельные cgroup APLAY. Ни capture_active, ни старый PC last_turn не подменяют byte evidence/shortness.

Пересчитанные maxima generation2: gap_events=overflow_events=overflow_bytes=overflow_frames=superseded_events=0, max_read_gap_seconds0,128934877; raw_buffer_peak6784 B <discard threshold12800 B <capacity28799 B, assembler max230400 B, sampled pending_events0. `suppressed_frames`0→321600: PCM читается и отбрасывается для STT под own-output mask; это не потеря capture. Gap counter ловит software receipt gaps свыше `max(0.25, 4*chunk_ms/1000)`, а нулевой counter не доказывает каждый аппаратный sample. Один URLError на64,796 s — пропуск status observation, не установленный PCM gap.

Из `live-events.json`: manual seed начат32,548148 s, завершён36,408692 s; generation1→2 — реальный retire gap. STOP отправлен80,133233 s, ответ80,282229 s, mic219→220/capture=false. После response+0,5 s **101** status rows: read_bytes1398784 неизменны, capture=false, turns3; поздних PCM/APLAY в Agent cgroup нет. Это подтверждает наблюдённый STOP в listening, не live cancellation race при STT.

Camera пересчитана из `consumer-report.json`: 104 coexistence +53 fresh_after_privacy packets, 157 уникальных IDs/pixel hashes, один boot. privacy_true:12 HTTP503/decoded0; privacy_false_old_admission:11 HTTP503 +1 timeout/decoded0. Producer receipt в `cleanup-installed.json`:354 frames, camera gaps1, capture_thread_reaped=true, reader_shutdown_unknown=false, raw_files_created0, audio_or_motor_commands0; stage/producer/listener удалены. Последний decoded packet предшествует STOP; последующий старый admission получает503, нового admission после STOP нет. Processor reaped=true, owned policy close не UNKNOWN. PTS0/physical freshness verdict не улучшен; единичные poll timeouts и camera acquisition gap не названы audio gaps.

## Два свежих read-only снимка Q2

Снимки получены отдельными конечными SSH командами через Hub с существующим pinned robot known-hosts и GET `/status` Agent, `/control/operator` и `/status` Hub, `/status` worker. Начальные попытки до успешных снимков остановились на network sandbox/отсутствующем robot key в стандартном known_hosts; использован существующий `/private/tmp/reachy-live-baseline-20261017/robot-known-hosts`, strict checking сохранён. Никаких управляющих запросов не отправлено.

| Поле | Снимок1 | Снимок2 |
| --- | --- | --- |
| Robot UTC / MSK | 01:30:11,424473 / 04:30:11,424473 | 01:30:25,103148 / 04:30:25,103148 |
| Общий request bracket UTC | 01:30:07,454771…01:30:12,029074 | 01:30:21,528512…01:30:25,387777 |
| Agent boot / PID / generation | f2a66c3b-dc89-4a2f-961d-ab738696b950 /205817 /3 | те же |
| read_bytes / read_frames / read_calls | 11122688 /5561344 /5394 | 11558912 /5779456 /5604 |
| last_read_monotonic | 605223,600330144 | 605237,232403774 |
| arecord PID / PPID / start_ticks | 208199 /205817 /60487598 | те же |
| arecord wchar / syscw | 11118592 /5429 | 11556864 /5643 |

Δread=**436224 B /218112 frames**, snapshot monotonic Δ13,678766120 s (номинально15945,30 frames/s); между last-read receipts Δ13,632073630 s ≈15999,91 frames/s. `/proc` и status читаются последовательно, поэтому Δwchar438272 B не обязан совпасть с Δread_bytes. Это два снимка, не новый непрерывный soak и не повтор live STT/playback.

В обоих: microphone_enabled/listening/capture_active=true, phase=listening, mic221, policy116 motor=false/quiet=false/privacy=false, owners=null; turns3, interruptions0, volume100, last_error/microphone_state_error=null. Generation3 retired=false, suppressed0, gaps/overflow/superseded0, max receipt gap0,129034150 s, raw peak7168 B, pending0. Во всём `/proc` scan только один arecord, он в `/system.slice/reachy-voice-agent.service`, stdout=`pipe:[1367780]`; APLAY отсутствует. Agent205817/factory150625 active/running, NRestarts0. Hub free/action_running=false/stock unknown=false; worker idle/ok=true. Camera stage отсутствует, совпадающих A1/demo/camera observer процессов на роботе не найдено; после завершения обоих transport локальный process snapshot показал **0 SSH процессов**. Соседние чаты не подключались к этой проверке; это ограниченная process-проверка, не аудит любого возможного клиента сети.

Оба import-resolution снимка выполнены установленным `/home/pollen/reachy-companion/.venv/bin/python` с PYTHONPATH `/home/pollen/reachy-companion/src`; они совпали с `/proc/205817` cwd/cmdline/PYTHONPATH и systemd ExecStart. Все9 modules разрешаются из `/home/pollen/reachy-companion/src/reachy_companion/` и совпадают с A1 manifest/dependencies (включая дополнительный snapshot_vision); это проверка файлов/resolution, не чтение Python module objects из памяти Agent. Ключевые SHA:

- agent.py: `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b`.
- capture_pump.py: `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6`.
- Reachy config: `a6171f68e6fc20feebb48475991517f61412afc693f0c58f999f077f0eedd0d5`, effective capture_pump_enabled=true.

Временные sanitized receipts: `/private/tmp/q2-fresh-1.json` SHA256 `542383883634a60b478b9a3254a784bac1a4a91597b666e77fc9e60090de2a4d`, `/private/tmp/q2-fresh-2.json` SHA256 `8b372b98834c370be988245447932114be0925db3bacc3f26f0d07feb39b5635`. Секреты/config/PCM/images не выгружались; существенные результаты приведены здесь, единственный итоговый workspace artifact — этот документ.

## Незакрытые дефекты и пригодность

1. **Retire gaps:** manual `/say` подтверждён live; synchronous spoken snapshot подтверждён установленным `_capture_visual` retire/close/suspend, live не проверен. Они исключают обещание общей бесшовности любых voice/vision операций.
2. **Conversation acceptance:** строгая краткость всего обмена не принята (playback ~3,00/7,64/8,50 s); raw transcript/акустической speaker identity нет. Own echo после bounded tail/AEC остаётся UNKNOWN, хотя mask и обычные завершённые voice turns доказаны.
3. **Camera time/context:** PTS/running-time0, physical freshness/age upper UNKNOWN; отдельный IPC consumer ещё не normal joined context/session. Changing pixels/privacy fence этого ограничения не снимают.

**Пригодность:** exact A0+opt-in пригоден как подтверждённый audio baseline для следующего ограниченного finite native autonomous loop с обычным STT→main→playback. Приёмка полного автономного loop, бесшовного spoken snapshot, акустического echo rejection и физической свежести камеры остаётся отдельной; Q2 такой loop не запускал и разрешения на него не расширял. Перед следующим запуском нужны свежие authority/ownership checks, исторические epochs из этого документа не являются payload.

**Q2 завершён, аппаратное и инженерное владение явно освобождено. Собственных SSH/observer процессов не осталось. Normal listening оставлено ON**, mic221/generation3 на последнем свежем снимке; фонового soak нет.
