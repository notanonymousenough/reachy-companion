# R14 — один finite R13 goal/clock trial, model wait; accepted settle отсутствует

17 октября 2026, финал **08:50 MSK**. **Один запуск exact R13 `finite_goal_clock`, actual scheduler interval 15.025004s. Модель вернула пять `wait`; reducer: 5 `decision_stale`, 0 accepted. Proposal/effect POST/stock dispatch: 0. Finite settle acceptance FAIL, physical settle execution UNKNOWN / не испытывалась. Cleanup PASS.** Выбор не заменялся ручным действием; повторного arm/restart/replay не было.

**Аппаратное владение Reachy/Hub/PC явно освобождено. Normal listening/capture ON, durable motor policy OFF, owners absent, Hub free/stock known/unowned, worker/fast idle. Observer OFF.** R8 Agent/A1 pump/S2 и существующие модели сохранены. PROJECT не редактировался; чаты/подагенты не создавались.

## Exact stage, preflight и новая authority

Входы: [R13](R13-goal-clock-stock.md), [Q4](Q4-goal-clock-stock-review.md), [D4](D4-terminal-503-diagnosis.md), explicit [D3 handoff](D3-observer-health-live.md). Q4 150 offline+timing приняты; source review/tests не повторялись. R11 не устанавливался. R13 уже materialized: overlay взят из совпавших candidate bytes, patch повторно не применялся.

Secret-free temporary stage `/home/deploy/reachy-shadow/r14-goal-clock`: frozen D3 dependency closure с exact R13 тремя runtime files, public finite template и bounded passive witness. Архив **138243B / 40 manifest entries**, SHA256 `5586d57caf088606e00d43780a54f67028a97dbfa68d9d07a53c90c3b1cf2b0d`. Без private configs/tokens/keys/media; token создан только на Hub и затем удалён. SCP/install/trial прошли automatic review, unresolved rejection нет. Production source/config/service не заменялись.

| Effective staged source | SHA256 |
| --- | --- |
| native_agent.py | `b284f55b1afb4a7a8ac050fd5473de46359b01fc6164480b6595cc1e5ba4e004` |
| native_agent_session.py | `3900f61d01b655daa815f21c70b1ce1e34fd6be82c2f9a1246725777d661575c` |
| autonomous/config.py | `c7193c6a62e140ca34cb2a5a6e821d86dcdb5621897ad3d1b2acb72d30202f9d` |
| client.py | `adc324fc93ec4dfc1d88249deaa4a7925e8d44e92dc15946877cef574fac1c4f` |
| autonomous/gateway.py | `8f75faaf4ec4636a800b1c170cf44220dbefbc6e4c4d0207e2a7744502379fbc` |
| autonomous/runtime.py | `feadc9588682490269a02533e9dfc7f68c11958b015efff00eef2e2c48b8f0f1` |
| autonomous/state.py | `6294b232587853d4aba026aeaeae8ebee1163fc06d88f63461210605f0ce3141` |

Imports проверены на Hub из собственного stage. Exact entrypoint вызван через `runpy`; `sys.setprofile/threading.setprofile` только копировали allowlisted call/return metadata в capped128 memory list (actual20). Source methods/returns не подменялись. Witness overhead и отдельный telemetry reader влияют на timing; это один инструментированный trial, не hard realtime guarantee. Config/entrypoint import validation PASS, новые regression tests не запускались.

Свежий preflight подтвердил R8 Agent `001be4ec…`, A1 pump `5fe20c69…`, robot config `a6171f68…`, Hub `008be03f…`/client `adc324fc…`, Hub config `7f11d114…`; Agent216026/factory150625/Hub78887, NRestarts0. PC fast **7736**, creation/exe/command/weights неизменны; exe SHA `0bbac3a55d4a005772ce8a16c4c222163f683119bbbca13b42f6af788faaa4e6`, weight SHA `37ae482d336108d23516fa35e8e0c4126688d81018b87178a18d752a1357814f`. S2 voice `cfd55a2e…`, config module `97732830…`, private config hash `b864d375…`, short opt-in=true; container/image/start/restart/LM Studio process pins совпали before/final. Main9B/Whisper/Piper не запускались/не дублировались; новая независимая аттестация всех их weights не заявляется.

Before arm: Agent listening/capture ON/error null, motorOFF, owners absent, quiet/privacy false, daemon ready/motors enabled, Hub free/stock selected-known-unowned, worker idle; observer units not-found и native processes absent; PC rawslots idle. Approved existing-auth bridge: Mac local127.0.0.1:18097→PC127.0.0.1:18097, Hub reverse127.0.0.1:18097→Mac, own masters66235/66238. Kernel Hub boot `27d5c08c-9b13-4f4b-b1ac-342f6972e8f9`, listener inode1022613; no LAN listener/auth/trust/key/ACL/firewall edits. Existing D3 `Monitor` used as finite health witness, not observer service; 76/76 health200, terminal=null, max0.316278s, no reconnect.

New guarded controls, fresh CAS at each send:

| MSK | Control / receipt |
| --- | --- |
| 08:47:47.635 | durable Mic OFF: epoch249→250; capture/listening false, затем fresh phase paused |
| 08:47:49.171 | explicit motor grant: policy124→125, quiet/privacy false, owners null |
| 08:47:49.768 | consumed one arm; new goal `r14-single-settle-20261017`, version1, operator origin, evidence_ids[], TTL15s, changed_at actual preparation time |
| 08:47:49.866 | one process launch `--allow-native-observation --allow-goal-clock-stock-settle --allow-configured-agent-url --duration 15`; no service/camera/context/other effects |
| 08:48:08.018 | process exit1 after finite outcome; report reason duration/errors[] |
| 08:48:08.321 | guarded durable motor OFF: policy125→126 |
| 08:48:09.080 | after actual idle reconciliation, Mic ON: epoch250→251; capture/listening confirmed ON |

Agent boot `eea946cc-b050-40e5-b5c5-a91e578439aa`, Hub stock boot `5a2502a1-8b6f-49ff-9390-e6fdd213e24a`, compute boot `9ed8dae9-4381-4739-9e1e-66cd17813903`; stable during trial. Values here are historical receipts, never next CAS payloads. Native arm_id `395ccaec-bfbb-45d1-8eb4-e950c0763026`; goal monotonic expiry858242.552609768, not renewed.

## Actual model outcomes, proposal/effect и telemetry

| Request ID | Model choice | Gateway call latency, s | Reducer |
| --- | --- | ---: | --- |
| `8e830915-4b0a-4816-9ac1-d7f7309f1676` | wait | 2.351525 | decision_stale |
| `19131793-2141-48de-98dc-ef20ca1a1a7a` | wait | 2.379176 | decision_stale |
| `5060ab41-5016-4fd5-b82f-df409e898038` | wait | 2.235862 | decision_stale |
| `2519708d-7ae8-4f35-9ac9-c9ddc1dafb2f` | wait | 2.164514 | decision_stale |
| `e524aaa2-0411-4349-9d55-59cefbd3b058` | wait | 2.143680 | decision_stale |

Все actual outputs от `reachy-shadow-fast-cpu`, по36–39 output tokens,509–513 input tokens. Модель ссылается на отсутствие audio/context и разрешённый wait; это честный model outcome. Output не переписывался/не forcing response. Latency — complete Hub gateway call, не TTFT/чистое inference время. **0 accepted не выдаётся за пять accepted wait IDs.**

`stock_proposal=null` (make_stock_proposal call0), dispatch0/send_settle0, report `stock=null`, `stock_used=false`, `stock_unknown=false`, `stock_dispatch_observed=false`. Effect receipt отсутствует; accepted HTTP не выдаётся за движение. Native97polls,3read failures/0late receipts; начальный audio gap1/generation1 остаётся UNKNOWN из-за durable MicOFF, `pcm_continuity=false`. Ошибок terminal/503/withdrawal в этом trial нет. `continuous_acceptance=false`/`live_acceptance=false` сохранены.

Независимый read-only `/api/state/full` robot reader сохранил **174/174 pose receipts,174 уникальных timestamps,0exceptions**, 08:47:49.867–08:48:07.951MSK (включает startup и выход). Head roll **−4.015933…−3.949054°**, размах0.066879°; body_yaw −0.069029rad, antennas [−0.003068,0.001534]rad. Factory reports real/non-simulation daemon. GET latency0.015062…0.325133s. Эти pose/time receipts — отдельная telemetry, не post acceptance; они **не показывают требуемый +1°→neutral settle**. Independent joint-register/FK calibration, physical exposure age и hard stop certification не выполнялись. Physical settle proof **UNKNOWN / не exercised**, motion criterion **FAIL**.

## Точная dependency без runtime fix или второго arm

Это узкая причинная локализация actual `decision_stale`, не повтор Q4 review. В exact R8 `run()` paused MicOFF вызывает `expressions.hold()` каждую секунду. Actual installed `expression_player.py` SHA `7a5f7a0019352ecf8ceb2d3b6cf958e206655ab3a58387671c163aa86730bfdb` совпал с сохранённым source; `hold()` каждый раз увеличивает version. При стабильных boots/mic/policy/owners expression_version выросла95→113 внутри grant.

R13 наследует `NativeState.observe()`: signature включает `(identity(operator), expression_version)`; при её смене увеличивается `authority.operator_epoch`. Witness bindings имеют epochs1/5/7/10/14; за inference2.14–2.38s authority успевает смениться. `State.apply()` записывает decision_stale при authority mismatch либо deadline; все пять apply наступили **до своих original model deadlines** (более3.5s оставалось), значит сработало authority mismatch. Goal/motor identity/decision generation оставались pinned; expression fence не обходился. Модельные wait и stale rejection — два отдельных факта; даже принятие wait само по себе не дало бы settle.

Следующий минимальный **source-only** scope root: воспроизвести exact R8 paused1s hold + R13 actual methods при2.4s fast, затем рассмотреть минимальную совместимую коррекцию этого coupling. Сохранить real expression-change invalidation перед effect, STOP/boot/epoch/owner/quiet/privacy, original model deadline, <300ms BEGIN/effect/server CAS, single-use/UNKNOWN/no replay. Не расширять300ms/не удалять guard/не forcing motion. Здесь runtime не переписан и новый live arm не запрошен. Достоверность effect/server guard timing остаётся UNKNOWN: ни один effect path не достигнут. D3≥30minFAIL/503 и observer service остаются отдельными незакрытыми задачами.

## Cleanup, evidence и handoff

Original report **3146B / SHA256 `a13d1c82ce3e06f88f27f306d219aecbccb70afbd7ac830e219ca3b1e94f2851`**, values не исправлялись: `accepted=false`, cleanup_verified=true, все8 execution slots false, compute sameboot idle/quarantine[], control listener/thread/handlers idle, stockunknownfalse. Structured export реконструирован в exact JSON indentation; bytes/SHA независимо совпали с original на Hub до удаления. External drain и повторные snapshots отдельно подтвердили raw fast idle, Hubfree/actionidle/known-unowned и workeridle.

Первое удаление после gateway SIGTERM остановилось на немедленной port-absence assertion (race teardown). Никакого restart/повторного signal/arm не было. Следующий fresh read подтвердил pinned gateway/session absent, ports18098/8791 absent, normalON/motorOFF/rawfastidle; после этого удалены exact own stage/token и hash-matched archive. Затем own `-O check` подтвердил masters66238/66235 и оба `-O exit` вернули0; sockets/Mac18097 absent. Final Hub read08:50:08.954:18097/18098/8791 absent, native processes[], observer unitsnot-found, production Hub78887/R8Agent216026/factory150625 неизменны. Epoch251, policy126OFF, source_generation4, PCM**2048→3823616B** после восстановления, gaps0/overflow0/retiredfalse; новый arecord239921 — ожидаемое последствие durable MicOFF/ON. Turns5/errornull, никакого voice stimulus/duplicate accepted voice test.

**PASS:** exact staging/preflight, один finite lifecycle, честные model outputs, no effect/replay, control cleanup и освобождение оборудования. **FAIL:** accepted motor demonstration/finite report acceptance (0 accepted,0 stock). **UNKNOWN:** effect/serverCAS/physical settle path и long-term autonomy. **Handoff root: R14 закончена, стенд свободен, observerOFF/voiceON/motorOFF; следующая узкая dependency — paused-hold/expression-version coupling, исходники без live rearm.**

Evidence root: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a14863-37b8-77e2-ac09-c48471e55b5a/R14-evidence/`. `live-export/` содержит original report,20event witness,174pose receipts, arm/config/imports,controls/sentinel/externaldrain; `analysis.json`, exact40entry manifest/archive, controller/witness/transport scripts, before/final robot/PC/Hub pins, original cleanup assertion и separate cleanup-finish/transport-cleanup. `SHA256.json` индексирует локальные evidence. Raw media/transcripts/private config/token contents отсутствуют.
