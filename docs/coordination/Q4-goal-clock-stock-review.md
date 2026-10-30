# Q4 — review finite R13 goal/clock stock

17 октября 2026, Europe/Moscow. **PASS source review для одного отдельно согласованного finite trial; actual model/motor acceptance — UNKNOWN. Blockers не найдены.** Это не разрешение установки: D3 — единственный аппаратный владелец, его текущий scope остаётся frozen D0 observation-only. В R13 исторически указан D2; этот текст не меняет текущего владельца и его полномочий.

Проверены [R13](R13-goal-clock-stock.md), его exact manifest/patch/candidate/preimages и [R12](R12-motor-authority-boundary.md). Из R6/Q3 использованы только actual latency ranges. Review офлайн: без SSH, HTTP, моделей, устройств, deployment, source edits и других чатов. Единственный сохраняемый результат — этот документ.

## Exact candidate и проверка

Все четыре current файла совпали с candidate и `after` manifest; три runtime preimages совпали с `before`. Patch SHA256 `8acde90d65819e5cfcec14177964eb9b6482e76626d2ded6548b4cc2e401747b` подтверждён. Все `unchanged` hashes совпали. Scope patch — только `native_agent.py`, `native_agent_session.py`, `autonomous/config.py` и существующий R13 test file. Это source attestation, не attestation исполняемых imports на стенде.

Повторён exact R13 `run_offline.py` с `PYTHONPATH=src:tests`, Python `-B`: **150/150 PASS, 11,014 s**, включая 24 R13 checks. Runner запрещает реальные sockets и исключает восемь loopback HTTP fixtures. Дополнительные проверки выполнены через stdin на actual R13 methods с существующими fixtures; новые tests/source файлы не добавлены.

## Claims

| Claim | Verdict | Основание |
| --- | --- | --- |
| R5 default и `--service` observation-only сохранены | PASS | `config.load`: default `r5_pcm`; `validate_lifecycle` (`native_agent_session.py:38–49`) и `main:216–225` отвергают finite profile без нового matching CLI arm, с service/camera/context до создания клиентов. Example config и D0 unit hashes неизменны. |
| PCM/audio не являются authority; FastView clock/goal-only | PASS | `motor_identity` (`native_agent.py:61–64`) вызывает полный typed `control_authority`, исключая observation fields из identity. `GoalClockState.snapshot:686–698` очищает dialogue/memory/prev/pending/ready/candidates/evidence; остаются operator goal, clock, durable operator projection и capability, audio — пустой `no_data`. Content events запрещены `ingest:677–684`; model-supplied `basis` не проходит schema. |
| Durable mic/policy/owner/boot/STOP/privacy fences сохранены | PASS, source/fixtures | `GoalClockNativeAgent.check_operator:389–399` сравнивает полную durable identity, требует motor=true, отвергает exhaustion/error/stopped. Base arm требует unowned owners и quiet/privacy=false. Exact R8/pinned microphone и actual MotionPolicy fixtures подтверждают persisted STOP→ON, owner/policy ABA и terminal closure. Event `/stop` немедленно закрывает predicate через `grant_current:401–409`; durable OFF всё равно требует server CAS/save/fsync, local Event его не доказывает. |
| Initial motor=false никогда не действует; `allow_stock` явный | PASS | Constructor `363–376` принимает только literal `True`, проверяет initial motor policy; `stock_allowed:542–543`, `admit_stock:545–558` и base `dispatch:300–304` повторно проверяют opt-in. Дополнительно вызваны actual constructor с false/0/1/None и initial motor=false: отказ; после `allow_stock=False` dispatch=false. |
| Goal expiry/version/changed_at не продлевают arm | PASS | `goal_expires=clock()+TTL` фиксируется при arm (`378–380`), TTL 1..180 s. `grant_current:404` сравнивает goal целиком с pinned copy; scheduler читает текущий config (`744`). Изменение id/version/changed_at отвергнуто actual admission терминально. `changed_at` — validated UTC metadata, не receipt timestamp и не основание freshness; expiry определяется monotonic TTL от arm. |
| `wait/observe` не подменяется settle | PASS | `NativeState.apply:657–666` создаёт proposal только при явном `motion='settle'` и accepted reducer result. Actual apply обоих choices без motion оставил proposal=None. Нет автоматического settle из текста goal. |
| Старый fast через gap отвергается; discontinuity означает sensor UNKNOWN | PASS | `notice_sensor/sensor_gap:484–504` увеличивают generation при pause/retirement/replacement/regression; `GoalClockState.apply:706–720` проверяет generation до и после reducer. `NativeScheduler.advance:757–781` сохраняет occupied fast/poll slots, очищает pending proposal, не создаёт replacement/catch-up. Exact R10 composite fixture: старые fast/proposal POST0, только новый binding может действовать; report `sensor_state=UNKNOWN`, `pcm_continuity=false`. |
| Свежие Hub ownership/readiness/expression guards сохранены | PASS, source/fixtures | `read_motor_receipt:411–446`: fresh status+typed operator, pinned Hub boot, selected/known/unowned stock, free/idle, daemon ready, motors enabled, BEGIN-age<300ms. Known negative публикуется до позднего timeout; pending busy не выдаёт receipt. `execute_stock:560–570` повторяет effect preflight; `guarded_control:110–118` после preconnect проверяет typed identity/expression. Actual Hub `expression`, `stock_check`, `robot` сохраняют guards перед обоими targets. |
| Single-use/send barriers/no replay/UNKNOWN сохранены | PASS, source/fixtures | `dispatch:302` резервирует slot до Job; отказ до send его не освобождает. `guarded_control:95–107` проверяет локальный predicate/deadline перед headers/body/каждым partial send. Attempted send/lost response дают UNKNOWN, без POST retry; collector `506–515` не теряет outcome после revoke. Fixture interleavings STOP/policy/expression/gap, partial/body/lost response прошли. |
| Correct effect и completion semantics | PASS, source/fixtures | `send_settle:332–351`: только roll 1°→neutral, остальные head coordinates/antennas=0, два шага по .5s/minjerk. Требуются `ok is True`, steps_observed=2, pose_verified/hard_stop_certified `is False`; результат означает observed commands, не сертифицированную позу/остановку. |

## Работоспособность при actual fast latency

**PASS: proposal не привязан к 300ms receipt начала inference.** Model binding создаётся через `State.bind` (`state.py:289–294`): deadline=`request_now+fast_deadline_s`; `runtime.py:220–229` сверяет request/compute identity. Затем `GoalClockState.make_stock_proposal` (`native_agent.py:723–729`) берёт **последний полный poll receipt на момент accepted result**, закрепляет его operator/expression/BEGIN и вычисляет `min(binding.deadline, receipt_BEGIN+.3, goal_expires)`. Это новый effect receipt; исходный model deadline сохраняется. Effect preflight и post-connect reread новых deadlines не выдают: `execute_stock` использует прежний proposal, `guarded_control:118` может только сузить deadline.

Проверено на actual `bind/read/advance/apply/dispatch/execute_stock/guarded_control`, с fake monotonic clock и fixture sockets. Использованы R6/Q3 fast **2,169504 и 2,505324 s**, model deadline 6s; periodic polls каждые 100ms, каждый из четырёх read legs занимал явно заданные 15ms (полный poll 60ms; R6/Q3 successful read range 41,045–155,668ms). Незавершённый по времени poll не выдавался за completed, clock назад не двигалась. Effect preflight — ещё 30ms, post-connect typed reread — 15ms.

| Fast, s | Binding / model deadline | Effect receipt BEGIN | Неизменный effect deadline | Fixture socket send | Остаток |
| --- | --- | --- | --- | --- | --- |
| 2,169504 | 100 / 106 | 102,1 | 102,4 | 102,214504 | 185,496ms |
| 2,505324 | 100 / 106 | 102,4 | 102,7 | 102,550324 | 149,676ms |

Оба случая: generation0, ровно один attempted POST, slot used, fixture completion observed. Отдельно proposal с deadline100,3 после нового полного receipt в100,31 остался rejected при fresh motor authority: reread не продлил уже выданное разрешение. Existing min-model/min-goal expiry checks также PASS. Первый диагностический timing прогон имел ошибку harness (на длинном latency completion был поставлен раньше окончания poll); он исключён, выше приведён исправленный монотонный прогон.

**UNKNOWN: реальный запас нового effect chain.** Приведённые задержки — explicit fixtures, а R6/Q3 измеряли другой observation chain. Они не доказывают latency нового Hub status/preflight/connect/send и не гарантируют действие при любом jitter. При исчерпании 300ms корректный исход — POST0/HOLD, без ослабления guards. Source не делает success заведомо невозможным при fast2,17–2,50s.

## Findings и finite-trial verdict

**Actionable source findings: 0; обязательного next source fix нет.** Минимальный R12 contract выполнен; universal proof LAN/device failures не заявляется. Source fixtures не являются actual model/motor PASS.

Кандидат готов к **одному отдельно разрешённому finite15s trial после handoff**, без retry/rearm. Текущий D3 scope frozen D0 этого trial не разрешает. Минимальные criteria будущего окна:

1. Аппаратный владелец подтверждает exact candidate/import/dependency hashes, отдельный конечный arm/goal/TTL и текущие typed boots/epochs/unowned owners; единственный scheduler/poll/fast/effect owner, D0 observation scheduler drained. Durable motor permission выдаётся штатным guarded operator path.
2. Actual model response с matching request/compute/generation и явным settle; журнал содержит binding deadline, effect receipt BEGIN, proposal deadline и send timestamps с age<300ms. `wait/observe` означает отсутствие action и не заменяется fixture choice.
3. Не более одного expression POST и ровно два fixed targets при успешных server step guards; observed completion без pose/hard-stop claims. Reject/expiry/UNKNOWN завершают попытку без повторного action.
4. Закрытый local arm, подтверждённый durable motor OFF, reconciliation фактического Hub ownership/UNKNOWN и idle occupied jobs/compute; сохранённый used slot/report. Возврат frozen D0 observation-only без rollback epochs/persisted ON и без auto-enable. Без этих actual receipts hardware verdict остаётся UNKNOWN.
