# Второй проход: решения, отказы и готовность плана

2026-10-09. Это журнал рецензии **того же** проекта, не новая параллельная спецификация. Основные разделы и wire schemas обновлены до 1.1. Статус: готов к ограниченному контрактному прототипу после перечисленных ворот; не готов к автономному управлению hardware без измерений.

## Устранённые противоречия

| Проблема первого прохода | Решение и где проверять |
|---|---|
| Полный Decision с ids/time/epochs не помещается в короткий L0 output | FastView/FastChoice, host-bound canonical expansion; contracts и fixtures |
| MainProposal без proposal_id, ready result не в snapshot | proposal/task ids + ready_proposals + one-time speech.commit |
| 500 ms robot lease при 1 Hz LLM | Независимый 100 ms transport heartbeat + finite intention deadline; architecture |
| QUIET и mode, и сохраняемый запрет | Quiet только orthogonal operator flag; overload state machine больше его не сбрасывает |
| Очереди per-worker не ограничивают shared GPU | Один compute permit + residency/RAM budgets + deadline-aware fairness |
| Timeout мог освобождать fast slot при ещё работающем request | Quarantine/result revocation отдельно от actual worker slot release |
| Speech TTFT ≤2,5 s без tick wait/L1/TTS | Baseline target P95≤5 s, stretch отдельно; full vs segment pipeline различены |
| Interrupt мог одновременно поменять epoch и требовать resume | Suspected/confirmed split; resume только до confirmed new utterance |
| Счётчики epochs могли совпасть после restart | hub/compute/robot boot binding + fencing; stale attempt rejected |
| Общая KV формула принята за budget Gemma | HF hybrid config, sliding/full estimates и runtime buffer gate |
| Требование критичных логов без потерь при finite disk | Explicit shedding/loss marker/admission closure, safety independent |
| 10 min initiative cooldown позволял 6 реплик/h при limit2 | И cooldown, и rolling hour budget; минимум инициатив=0 |
| Независимость memory подтверждений не определена | Root lineage и claim DAG, version handshake, no repeated trait impulse |

## Decision records

| ADR | Принято | Отвергнуто/компромисс | Что может изменить решение |
|---|---|---|---|
| D01 | Self-clocked fresh L0 каждый доступный tick, один execution request | Чисто event-driven, cached wait, overlapping stale fast jobs | Только measured period/context/model, не отказ от регулярных LLM calls |
| D02 | Dedicated CPU fast baseline и shared GPU permit=1 | «Async workers значит всё параллельно и быстро» | Mixed-load CPU benchmark; если не проходит, другой профиль на ПК |
| D03 | Compact FastChoice + trusted canonical envelope | Модель генерирует timestamps/epochs/grants | Extension registry/короткая schema, после quality+token gates |
| D04 | Hub единственный semantic owner; robot local revoke watchdog | PC/direct tools управляют robot или safety ждёт LLM | Не снимается; требуется ownership protocol acceptance |
| D05 | Canonical bounded snapshot, stateless model requests, opportunistic prefix reuse | Бесконечный stateful transcript/модельная память как authority | Runtime choice по measured reuse, не формат canonical memory |
| D06 | Baseline full proposal; segment streaming отдельный capability | Озвучивать незавершённые model tokens | Verified semantic segments/PCM cursor; baseline остаётся fallback |
| D07 | Собственный broker; optional Hermes lifecycle executor | Hermes/OpenClaw заменяют robot cognition | Нужные интеграции и actual run/sandbox compatibility matrix |
| D08 | Explicit simulation и claim provenance | Fake perception, personality change из одного распознавания | Калибровка dynamics/traits после longitudinal evaluation |
| D09 | S3/VPS disabled до config, immutable batches, staged version apply | Export из control loop, VPS direct writes на роботе | Настроенный destination/privacy/processor contract; локальный loop не зависит |

## Failure-mode analysis

Severity означает влияние, а не оценку вероятности, которую пока невозможно измерить.

| Failure | Severity / обнаружение | Ограничение и восстановление | Проверка |
|---|---|---|---|
| Fast CUDA/CPU stall | High; hard deadline + actual busy slot | Revoke outputs, quarantine, no new parallel request; bounded probe/supervised isolated process | Late completion после timeout не меняет pose/speech |
| GPU long non-preemptive VLM | Medium/High; deadline slack, STT age | Global admission, small inputs; urgent CPU STT если budget feasible; L0 CPU продолжает | Main/VLM/STT mixed load tail, честные misses |
| CPU fallback overload/paging | High; per-process timings/RAM/queue | Reserve fast threads, limit BLAS/ONNX/offload; slower measured period | Fast cadence под CPU STT, не только idle |
| Mute race with main/TTS/keyword | Critical; epoch checks в enqueue и actor | Sticky desired mute, revoke capture/speaker leases, old result archive | 1 000 reorder fixtures + hardware stop gate |
| Hub restart/replayed commands | Critical; boot/fencing/seq | Robot hold stopped до handshake, no replay unknown action | Restart at admitted/started/ACK loss boundaries |
| Two motion/speaker writers | Critical; owner lease/app lock | Refuse admission, single actor; revoke prior writer | Legacy/new conflict injected до live switch |
| STT hallucination/music+self speech | High; stable prefix/AEC confidence/corrections | No claim-as-fact, ambiguous utterance clarification, direct stop separate | Self voice/music/quoted stop/overlap dataset |
| Stale scene misleading movement | High; capture age/track revision | Archive old VLM, fresh view request, no synthetic direction | Completion after disappearance/new pose |
| Partial JSON/output truncated | High; schema/finish_reason | Whole choice rejected, next fresh tick; no regex salvage | Truncation every token boundary |
| S3 duplicate/unknown PUT result | Medium; digest/HEAD/immutable key | Same bytes/id retry, conflict quarantine; uploader independent | Crash after upload before manifest ACK |
| Disk full/private consent revoked | High; disk/consent epoch | Critical loss marker/admission closure; scrub/delete; safety still applies | Full disk + mute + remote late proposal |
| Poisoned memory/web/trait feedback loop | High; provenance/namespace/core checks | Staged proposal, independent roots, no policy updates, rollback | OCR instruction + repeated summary + lineage duplicates |
| VPS base version conflict | Medium; CAS/bundle handshake | Reject/reanalyze current bundle, no blind patch | Concurrent correction and delayed signed proposal |
| Clock jump/skew | High; monotonic+mapping uncertainty | Conservative age, unknown live pose; fresh clock map | ±60 s wall jump, boot reset, offset uncertainty>TTL |

## Открытые вопросы и конкретные ворота

| ID / приоритет | Неизвестное | Как закрыть | До закрытия |
|---|---|---|---|
| Q01 P0 | CPU/RAM и fast performance на ПК | Inventory, 200 warm/5 cold +mixed finite benchmarks; actual tokenized FastView | Period1 Hz — candidate, допустим профиль0,5 Hz; no hardware autonomy |
| Q02 P0 | Local GGUF/projector/runtime identity и support | SHA сравнение с published artifact, metadata/build manifest; separate text/schema/vision/tool/reasoning fixtures | Gemma unverified; existing model/text-only fallback |
| Q03 P0 | Actor ownership/stop/resume cursor/watchdog | Read-only capabilities, затем gated finite hardware tests | No new real autonomous motion/streaming resume promises |
| Q04 P0 | Shared GPU/VRAM residency и deadline tail | 4K/8K Q4/Q6/offload +STT/VLM matrix, memory peaks/paging | Concurrency1, fast CPU; STT fallback admission explicitly tested |
| Q05 P1 | Audio frontend/AEC/DOA/IMU actual availability | SDK/OpenAPI GET +fresh samples и acoustic tests; no new serial writer | Optional signals unknown, direction/thermal inference запрещены |
| Q06 P1 | Пользовательский комфорт инициативы/quiet schedules | Short comparative sessions и явные preferences | Conservative limit2/h, quiet/mute honored, no forced quota |
| Q07 P1 | S3/VPS destination/provider semantics/privacy | Config/credentials отдельно; local mock contract, retention/deletion/idempotency tests | Export disabled, local memory enabled only по prototype stage |
| Q08 P2 | Нужен ли внешний agent executor | Limited Hermes/OpenClaw adapter tests на synthetic tasks | Typed broker без внешнего агента достаточен |

Q01–Q04 — ворота **hardware-ready прототипа**, не причина бесконечно откладывать schema/replay вертикальный slice. Сейчас вопросов пользователю для завершения проекта нет: недостающие данные либо измеряемые, либо имеют безопасный default. S3 адреса нужны только перед remote stage, не до работы над циклом.

## Критерий сходимости и следующий шаг

План готов к реализации, когда все обязательные требования R01–R10 связаны с этапом/контрактом/проверкой, 1.1 schemas+fixtures и finite semantic traces проходят, определения states/epochs/budgets едины, P0 unknown имеют воспроизводимый gate+fallback, и ни один unresolved вопрос не маскируется обещанием hardware behavior. Это **design readiness**, не production acceptance. Не требуется заранее выбирать все будущие датчики/голос/облачного провайдера.

Следующий конечный шаг: этап0 read-only inventory при восстановленной доступности и этап1 shadow/replay slice без actuators/export. Измерить actual FastView tokens/cold/warm latency, выбрать achievable cadence, доказать, что 20 s background job не прекращает fresh L0 calls и mute fencing отбрасывает старые outputs. После этого переходить к perception/actuator gates. Пока этот slice не пройден, не добавлять personality auto commits, тяжёлую VLM cadence или новые интеграции.

## Узкое закрытие двух замечаний

Interruption resume уточнён до3000 ms непрерывной healthy silence по hub monotonic clock; fresh external speech/unknown coverage сбрасывают timer. Settled empty/self echo, verified cursor, live plan и current authority обязательны; pending STT после3 s ждёт, late confirmed final revoke. Main baseline4K теперь имеет полный budget text2048/vision1024/template256/output512/reserve256, option8K и measurement32K — отдельные согласованные profiles. Admission считает реальные template/image tokens и делает reprojection/recount либо reject; production32K этим дизайном не меняется. Добавлены22 finite interruption traces и18 budget checks. Остальные ADR и аппаратные ворота не переоткрывались.
