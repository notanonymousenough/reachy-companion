# R4 — server authority epochs: граница ABA

17 октября 2026, Europe/Moscow. Ограниченный offline source review; runtime/source/config не изменены. SSH/HTTP, устройства, deploy, другие чаты и подагенты не использовались. N4 adapter/session не редактировались. Это prerequisite review [R3](R3-observer-resilience.md), не разрешение implementation/policy/live.

**Вывод:** свежий полный same-binding status исключает скрытый **durable microphone STOP/OFF, policy privacy/quiet/motor и owner round-trip через проверенные server API**: каждый принятый переход увеличивает соответствующий epoch даже при прежних значениях. **Он не исключает listening pause→resume**. Поэтому narrow authority ABA — **PASS**, утверждение «никакой остановки слушания внутри gap» — **FAIL**. Эти утверждения нельзя смешивать.

## Exact evidence

Цель — [A1](A1-continuous-live.md) / [runtime baseline](runtime-baseline.md), не HEAD Agent/microphone. `PYTHONDONTWRITEBYTECODE=1 python3 deploy/autonomous/prepare_continuous_capture.py /private/tmp/reachy-r4-authority-exact-20261017` восстановил candidate, проверив цепочку preimage/patch/output hashes; application/device code не импортировался.

| Метка / точный source | Проверенный SHA-256 |
| --- | --- |
| A: восстановленный `agent.py` | `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b` |
| M: `microphone.py` из локального Git `2865db30e92fcb069c241c34bae4419ad65ed594:src/reachy_companion/microphone.py` | `d35ef6d3e0cc289e8043a0da68480ecd110ef3fff98afb81da0afad25e416129` |
| P: `src/reachy_companion/motion_policy.py` | `d224385e999a0c6056db42e1fc3a3c90afaa2009336eaf1ef364037dc98a8466` |
| C: восстановленный `capture_pump.py` | `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6` |
| B: `barge_in.py`, `prepare_capture_pump.candidate()` | `28831114f2cf0f60f47d3bdd77c4f8d120b6447101ff5adc56df46204eb247bf` |

Остальные A1 pins сверены: config `c0b0e7a…` извлечён из того же Git commit; sound_monitor `89e7f782…`, spoken_vision `486cfb8f…`, snapshot_vision = deployment-copy `deploy/autonomous/demo_vision.py` `d43a70cc…` совпадают с полными hashes A1. Эти helpers не пишут перечисленные authority fields; spoken child читает `/operator`. Client `adc324fc…` совпадает с baseline, но его сравнение **не** использовано как доказательство server increments. Номера строк ниже относятся к exact A/M/P/C/B, не HEAD.

## Все relevant mutation paths

| Переход | Функция / условие / epoch | Persistence, verdict |
| --- | --- | --- |
| Mic enabled ON/OFF; `listen=true/false`; повтор того же значения; claim/release/смена mic owner | A `set_microphone`, 170–214: после validation и boot/epoch/expected-owner CAS под `microphone_lock` **безусловно** `microphone_epoch += 1` (188), затем owner assignment (190), listening clear (191), `M.save(enabled)` (199); listening set только `enabled and listen` (207). Отклонённый CAS ничего не меняет. | M `save`, 29–57: отдельный persisted epoch `+1` (36), включая no-op; JSON enabled/epoch, file fsync→replace→directory fsync→enabled publish. Owners/listen не сохраняются. **PASS** для успешных вызовов. |
| Spoken STOP / spoken pause | A `run`: recognized stop→`set_microphone(False)` (923–927); response command pause/stop→тот же mutator (990–993). B `trigger`, 41–52, также вызывает его; C `PumpMonitor.capture_stop_parameters`, 379–381, добавляет boot/mic CAS. | Не голый Event.clear: тот же durable epoch path. **PASS**; stale STOP rejection не гарантируется всеми legacy callers, но принятый STOP всегда меняет epoch. |
| Motor/quiet/privacy; policy owner claim/release/смена; no-op | A `set_motion_policy`, 149–168, проверяет supplied boot/CAS и вызывает P `save`. P 44–50: RLock, snapshot, reject unknown/exhausted epoch и stale CAS/owner; **всегда** `after.epoch=before.epoch+1`. | P 56–66: file fsync→replace→directory fsync, затем owner publish; owner RAM-only, omitted owner снимает claim. A privacy clear listening (165), quiet/privacy stop speaker, denial hold expressions уже после save. Round-trip, включая owner away→back, **PASS**. |
| Persistence error / exhaustion | M 32–35,52–55: disabled/error, без wrap; A epoch уже увеличен. P 46,62–64: reject exhausted; write failure latch `failed=True`, owner=None, дальнейший snapshot возвращает epoch=None/privacy=true. | Не успешная прежняя authority. M может пережить ошибку с разными RAM/disk epochs; durability UNKNOWN, rollback epoch в текущем Agent отсутствует. P error owner reset не скрывается valid receipt. **PASS fail-closed**, не доказательство durable OFF при ошибке. |
| Временный `/pause`→`/resume` | A Handler 1170–1176→`set_listening`, 1005–1055: paired locks, supplied binding checks; 1043/1045 Event.set/clear, pause retires pump. Legacy `{}` разрешён. **Epoch/owner не меняются.** | RAM-only. Same-binding listening ABA **FAIL**; это не durable microphone STOP. |
| Manual `/say`/`/ask` | A `manual`, 1081–1109: bound say вызывает `set_listening(False, require_paused=True)`; unbound сохраняет was_listening, clear (1086), restore при lock failure/finally (1094/1109). | Без epochs/persistence. Temporary listening gap возможен; **FAIL** для непрерывности, не owner/privacy ABA. |
| Startup / termination / restart | A `__init__`, 79–100: новый `str(uuid4())` (85), mic epoch из M, mic owner=None, listening из enabled. P ctor owner=None; snapshot читает disk epoch. A signal `stop`, 1225–1229: clear/stopping/SystemExit, без persistence. | Boot namespace **PASS по source**; абсолютная уникальность UUID не математическая гарантия. Listening/owners после restart не восстанавливают старый boot binding. Reboot стенда/Hub persistence **UNKNOWN**, этим review не проверены. |

Контракт предполагает единственный штатный Agent и записи через эти mutators. P `snapshot` (19–33) перечитывает файл: удаление возвращает epoch0, подмена старым valid JSON не fenced RAM high-water. Arbitrary external file rollback/второй writer **UNKNOWN**; source не даёт anti-rollback гарантии. M читает файл только при construction; новый boot отделяет восстановление старого disk state. Private persisted bytes не читались.

## Проверка и точная следующая граница

**9/9 PASS**: существующие `test_microphone` (4) и `test_motion_policy` (5), с exact M под исходным module name и hash-checked P. Только временные fixture files; проверены restart epoch/no-op, fsync, failure, corruption, exhaustion, stale cleanup/owner CAS. Agent/SDK/webrtcvad не импортированы. Это не HTTP integration или power-loss test. Existing `test_bound_listening.test_bound_resume_and_pause_mutate_under_both_locks_without_epoch_change` и `test_continuous_capture.test_same_epoch_pause_retires_and_restart_uses_new_generation` прочитаны, не запускались; прямо подтверждают намеренный same-epoch pause.

**Один конкретный semantic gap:** `Agent.set_listening(False, …)` не оставляет authority epoch следа. Если внешний `/pause` должен считаться terminal withdrawal даже когда он полностью скрыт gap, минимальная следующая server-правка — при таком pause продвигать mic authority epoch с согласованной persistence и сохранением owner; manual already-paused path отдельно сохранить. Затем проверить pause/resume stale-binding rejection. Это предложение границы, не внесённая правка и не новая policy. Для узкого durable STOP/privacy/owner контракта такой gap отсутствует.

Без physical effects допустимы R3 read-only polling recovery, unavailable/gap/stale reporting, сохранение busy slots и invalidation старых decisions/proposals. Это не восстанавливает непрерывность PCM и не очищает terminal known revoke. GET recovery никогда не повторяет action POST; lost POST остаётся UNKNOWN с использованным slot/reconciliation. Physical admission этим документом **не одобрен**: остаются R3 generation/send/deadline guards, fresh отдельная Hub boot/free/idle проверка и явное решение семантики `/pause`. Свежий status не выводит уже terminal-revoked session обратно в работу.
