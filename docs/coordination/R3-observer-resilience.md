# R3 — восстановление наблюдений без восстановления отозванных прав

17 октября 2026, Europe/Moscow. **READ-ONLY source review / proposal, не implementation и не допуск live.** Изменён только этот документ. Устройства, HTTP/SSH, модели, deploy, другие чаты и подагенты не использовались. N4 startup path и hardware run вне scope.

## Вывод и основание

Рекомендован один вариант: отделить **временную недоступность наблюдения** от **terminal withdrawal**. При transient GET failure или истечении receipt закрывать effects и новые fast admissions, сохранять session/control и единственный обычный poll slot; после нового полного свежего receipt с прежним authority binding возобновлять decision lane. Старые решения и proposals через разрыв не переносятся. Это восстанавливает возможность следующей итерации, а не продлевает старый grant.

Terminal-on-any-native-read-error — существующее поведение адаптера, но не найденный обязательный инвариант целевого дизайна. Точный источник: N3 frozen `native_agent.py`, `NativeAgent.advance`, строки 123–127: любой exception записывается в `withdrawn`, expiry также записывается туда; строки 136–139 запрещают следующий poll. `NativeScheduler.advance`, 270–271, вызывает `close`; `run_native_session`, 57, завершает loop, а `Scheduler.close`, 137–143, terminal-revoke-ит context. Таким образом потеря одного read превращается в необратимое закрытие сессии. Это корректно закрывает admission, но смешивает observation freshness с жизненным циклом authority.

Дизайн §1, §4–7, §15–17 требует одновременно регулярных LLM-итераций, независимых sensor/task lanes, честной stale/UNKNOWN информации, bounded admission и приоритета STOP/privacy. Он запрещает повтор UNKNOWN effects; он не требует terminal revoke за каждый observation timeout. Временная пауза fast при неподтверждаемой authority должна быть видимым gap, после которого возвращается обычный cadence. Постоянное завершение session на таком gap мешает continuous lifecycle; назвать паузу непрерывными успешными decisions тоже нельзя. Обычная UNKNOWN camera exposure age, отсутствие semantic vision или временно неизвестная PCM/voice observation сами по себе не создают новую authority.

## Диагноз двух отказов

* **N2:** предыдущий completed receipt имел BEGIN `228988.631225`; следующий GET выполнялся от `228988.735255` до `228988.994917`. Около `228988.931225` предыдущий receipt достиг 300 ms, пока новый job ещё busy. `advance` terminal-latch-ил `native_status_expired`; позже полученный fast response не принят. Новый read длительностью 259.663 ms сам по себе меньше 300 ms, но интервал от предыдущего BEGIN до следующего completion больше этого окна. Ни deadline fast 6 s, ни модель причиной этого latch не были.
* **N3:** `native_agent_session.main → hub.get('/status')`, frozen строка 160, упал до создания NativeAgent/Scheduler. Aggregate bootstrap read — другой участок; это не доказательство runtime expiry. Его исправляет N4. У failed GET нет отдельной measured duration; 2.039 s — parent process window, не длительность этого GET.

Общая архитектурная причина повторяющихся развалов — зависимость допуска всего lifecycle от успеха каждого сетевого observation/setup read без промежуточного состояния unavailable. При этом конкретные transport причины всех выбросов не установлены. Direct route/ACK улучшил N3 audit, но оставил ранний 361 ms выброс. Ни LAN, ни placement, ни серия удачных probes не дают жёсткого real-time SLA. Все исходные timestamps и verdicts N2/N3 остаются неизменными.

## Один предлагаемый переход

Состояния ниже локальны адаптеру; это не новый grant, namespace или framework. `expected`, Hub boot pin, compute boot и реальные control epochs не переписываются при recovery.

| Состояние / событие | Следующее состояние и разрешённая работа |
| --- | --- |
| `OBSERVING`, ещё нет полного receipt | Effects/новый fast закрыты; один обычный read slot |
| `OBSERVING`/`FRESH`, GET transient failure либо age от BEGIN ≥300 ms | `OBSERVATION_UNAVAILABLE`; effects закрыты, начат явный gap; старые requests/proposals лишены admission |
| `OBSERVATION_UNAVAILABLE`, poll ещё выполняется | Сохранить занятый slot; не cancel-and-replace и не считать timeout завершением операции |
| `OBSERVATION_UNAVAILABLE`, poll реально завершён ошибкой/late receipt | Оставаться unavailable; очередной обычный GET не раньше `next_poll`, без burst/особого retry loop |
| `OBSERVATION_UNAVAILABLE`, новый полный typed receipt, age <300 ms, тот же binding, counters не регрессируют | `FRESH`; закрыть gap, следующий разрешённый tick строит новый snapshot/request; старый request не оживает |
| Любое состояние, подтверждённый STOP/privacy/quiet/disable, boot/epoch/owner mismatch, malformed/untrusted authority, counter regression, UNKNOWN physical effect | `TERMINAL_REVOKED`; прежний close/revoke/cleanup. Свежий read сам не выводит отсюда; нужны новая явная authority и требуемое reconciliation |

Transient здесь — узко классифицированные timeout/connection failure read-only status transport и просроченный корректный receipt. HTTP auth/protocol/schema errors, неожиданные exception и `ValueError` не переводятся автоматически в recoverable. Нельзя заменить текущий `except Exception` на «всё игнорировать». Если read уже увидел изменённую authority, последующий timeout не должен скрыть это terminal evidence: проверять каждый полученный authority объект до следующей сетевой операции; terminal evidence имеет приоритет над age check. Неполный sandwich никогда не обновляет latest/freshness.

**Binding:** равенство полного `identity == control_authority` включает Agent boot, mic epoch/enabled/owner, policy epoch/motor/quiet/privacy и motion owner. `expression_version` отдельно остаётся частью signature решения и точного сравнения stock proposal. Текущий sandwich не несёт Hub boot: нельзя объявить его доказательством неизменности Hub. После gap перед первым возобновлённым physical admission обязателен прежний fresh Hub boot/free/known/unowned/idle check; обнаруженный другой boot terminal-revoke-ит старую session. До такой проверки восстановлены только наблюдения/нефизические decisions, а не подтверждение Hub authority. Compute health/boot/quarantine guard остаётся прежним; его timeout recovery этим proposal не вводится.

При unavailable не вызывать `state.observe()` со старым receipt и не выдавать старые `native.pcm/native.voice` как `ready`. Сохранить последнее значение как историческое с исходным BEGIN, текущим age и stale/UNKNOWN; current phase/capture/voice busy outcome неизвестны. Не объявлять ранее running voice завершённым из-за gap и не угадывать непрерывность PCM. Local elapsed и execution_busy остаются актуальными независимо от status. Исторические typed counters нужны для сравнения при recovery, их нельзя сбрасывать ради прохождения regression guard.

Fast admission на время непроверяемой native authority приостановлен: отсутствуют fictitious idle decisions и скрытая очередь. Публикуются `OBSERVATION_UNAVAILABLE`, gap start/end/reason, возраст last receipt, фактические read failures/late receipts и skipped decision opportunities. Это честная временная потеря decision cadence, не полная continuous acceptance. Normal Agent продолжает собственные capture/STT/main/reply по своей control policy; observer не получает новых media прав. Уже занятые compute/stock/context futures остаются учтены, control STOP не ждёт их. Finite cap и controller stop сохраняются; бесконечный background retry/service здесь не вводится.

## Точная граница будущей узкой правки

| Функция | Необходимая семантика |
| --- | --- |
| `NativeAgent.read/advance` | Явная классификация transient/terminal с сохранением увиденного revoke evidence; freshness отдельно от `withdrawn`; один slot и ceiling 10 Hz как сейчас. Recovery только полного нового receipt; BEGIN не менять |
| `NativeScheduler.advance` | `close()` только при terminal. При unavailable обслуживать observer/control/accounting, не запускать новый fast; не прекращать обычный polling |
| `NativeState.observe/snapshot/apply` | Честная stale проекция; локальный монотонный observation generation при входе в gap, независимый от authority epochs. Запомнить generation активного fast request; `apply` отвергает request из прежнего поколения даже после восстановления, до принятия решения/создания proposal |
| `stock_allowed/dispatch/execute_stock` | Проверять доступность и generation; сбросить недоставленные proposals при gap. Deadline proposal ограничить также **исходным receipt BEGIN+300 ms**, не только `now+300 ms`/fast deadline. `stock_used` не сбрасывать; UNKNOWN terminal/reconcile |
| `guarded_control` / его существующий guarded `send` | Для native вызова нужен узкий constant-time admission predicate непосредственно перед каждым send: session не closed/withdrawn/unavailable, generation совпадает. Это дополняет существующие identity и 300 ms deadline проверки; не заменяет их. Без этой границы worker, уже вошедший в `guarded_control`, может отправить POST после gap |
| `run_native_session` | Не завершаться на recoverable unavailable; stage/report отражают gaps и busy. Terminal/final cleanup и health guards сохранить |

Последняя send-проверка нужна из-за отдельного stock worker: одного `if unavailable` в scheduler недостаточно. Предикат не делает I/O и не держит lock на протяжении HTTP. Уже начавшийся send/POST нельзя объявить отменённым: stock slot остаётся потраченным, результат собирается, недоказанный outcome остаётся UNKNOWN. После gap новые effects отсутствуют до свежей проверки; уже выполняющийся эффект этим observer не превращается в доказанно остановленный. Локальные concurrency границы и конечная Robot-side authority проверка должны быть сохранены.

Не требуется переписывать общий `Scheduler`: его one-fast-slot, no-catch-up и deadlines сохраняются. Нельзя при gap очистить `fast_job`/binding и выдать новый permit: результат инвалидируется, реальное выполнение остаётся busy до завершения/существующего reconciliation. Terminal `Scheduler.close` и terminal context revoke не использовать как recoverable pause: terminal revoke не отматывается назад. Отдельно: текущий `advance`, 131–134, лишь выставляет `stock_unknown`, не `withdrawn`; для предложенного terminal-on-physical-UNKNOWN нужен явный terminal переход, без очистки UNKNOWN. Startup `main`/N4, global socket timeouts, camera/worker owners и control policy не менять.

## Почему нет ABA/replay; предел доказательства

1. `expected` immutable. STOP→ON или owner away→back не восстанавливают старый binding при монотонных mic/policy epochs; boot reset меняет boot ID. Даже если изменения не были прочитаны во время gap, новый полный receipt должен совпасть с исходными epochs/owners, а не только с enabled=true. Увиденный terminal latch не очищается никаким recovery.
2. Локальный gap generation возрастает один раз при входе в unavailable. Старый fast request навсегда связан со старым generation; свежий receipt с тем же внешним binding не позволяет принять его поздний completion. Generation — версия пригодности наблюдения, **не** новая authority. Текущий `State.apply` проверяет authority/deadline/consumed request IDs, но не gap generation; одной паузы scheduler сейчас недостаточно.
3. Новый decision получает новый request ID, реальное время, новый snapshot и исходные deadlines. Нет reapply старого response, backdating, catch-up replay или восстановления старого proposal. Повтор обычного GET после освобождения slot — новое наблюдение, не повтор action POST.
4. Stock single-use reserve до worker start, точное operator/expression binding, исходный receipt deadline и guarded send сохраняют эффект закрытым при stale. Lost response не доказывает отсутствие effect; `stock_used/stock_unknown` не очищаются при recovery.

Это доказательство опирается на непереиспользование boot IDs и обязательный рост server epochs при всех authority-changing переходах, включая owner смены и STOP/privacy round-trip. Frozen client валидирует типы/равенство, но сам не доказывает server persistence/монотонность. В разрешённом source review server mutation paths не проверялись; **перед implementation admission нужно подтвердить этот контракт адресным server-source review/тестом**. Если owner может уйти и вернуться без смены epoch/boot, равенство sandwich не исключает ABA и автоматическое recovery physical admission по этому proposal неприемлемо. Обычная sensor UNKNOWN такого перехода epoch не требует.

## Минимальные meaningful offline tests и открытые случаи

* Fake clock + pending Future воспроизводят N2 timestamps: при age=300 ms effects/fast закрыты, session/control живы, busy poll не заменяется; полный свежий same-binding read затем открывает новый tick. Late/неполный read не закрывает gap; BEGIN остаётся исходным.
* GET timeout/connection error → bounded обычный polling; одновременно STOP/owner/epoch mismatch до последующего timeout → terminal, без возврата на same-value enabled. Параметризовать boot/mic/policy/owners/privacy и malformed receipt, не моделируя их transient IO.
* Fast стартовал до gap, completion приходит во время/после recovery и ещё внутри 6 s: отвергнут по generation; Future сохраняет slot до реального completion, нового concurrent inference нет. Новый request после recovery может быть принят; duplicate request остаётся rejected.
* Поставить barrier в stock worker до guarded send: gap/expiry/close между dispatch и send дают POST=0. Для уже отправленного POST + lost response: POST=1, used=true, UNKNOWN/terminal, subsequent fresh reads не повторяют action. Проверить deadline исходного receipt и fresh Hub boot mismatch.
* Stale snapshot/status/report содержат UNKNOWN, возрастающий age и явный gap; native metadata не `ready`, counters не выдуманы. Recovery с regression terminal. STOP и finite cap завершают unavailable session без ожидания fast; existing occupied/context-terminal cleanup checks проходят.

Не закрыты: server ABA contract; атомарная граница локального send predicate и конкурентного revoke (проверяется barrier-тестом, Robot-side guards обязательны); долгий/зависший GET и общий whole-request deadline (socket timeout не whole-request bound); compute-health transient expiry 500 ms; privacy/context/media lifecycle при потере authority наблюдения; hard physical STOP; фактические camera/motion/≥10 decisions и sustained cadence. Эти gaps не исправляются данным review. При затяжном outage один реальный slot может оставаться занят — replacement не разрешён, здоровье и длительность gap публикуются. Без отдельной проверки privacy/context path proposal не даёт разрешения продолжать выдачу camera grants или admission новых privacy-sensitive задач в unavailable.

## Runtime effect, отклонённая альтернатива и rollback

Ожидаемый effect: короткий status gap перестаёт автоматически уничтожать autonomy session; наблюдатель продолжает bounded reads, затем возобновляет решения по свежему состоянию. Во время gap effects и новый fast закрыты, остальные разрешённые async owners не блокируются observer join. Это не исправление LAN, гарантия cadence, принятие always-on service или одобрение следующего hardware run.

**Отклонённая альтернатива:** grace window с сохранением старой lease/продлением 300 ms и последующим принятием старого fast response. Она скрывает observation gaps и допускает действие на просроченных основаниях, в том числе после незамеченного revoke; поэтому неприемлема даже при лучшем live decision count.

Rollback будущего отдельного candidate: закрыть его admission, собрать busy/UNKNOWN и context-terminal receipts штатным cleanup, затем вернуть hash-проверенные preimages узкой правки. Не перезапускать/не освобождать unresolved physical/backend slot ради rollback. Возврат terminal-on-read-error допустим как прежнее fail-closed поведение с прежней потерей availability; не считать его continuous acceptance. Этот документ runtime не меняет и rollback сейчас не требует.

## Frozen evidence и ссылки

Прочитаны [N2](/Users/notanonenough/reachy-companion/docs/coordination/N2-native-live.md), [N3](/Users/notanonenough/reachy-companion/docs/coordination/N3-status-native-live.md), [дизайн](/Users/notanonenough/reachy-companion/docs/coordination/design-2026-10-17.md). Каталога `reports/source` в checkout нет; использованы сохранённые N3 `preimages` (N2 bytes) и effective `payload`, без реконструкции из текущего N4 source.

* [N2 native preimage](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147a2-aa60-7160-96cb-0f190bcfb65c/N3-evidence/preimages/src/reachy_companion/autonomous/native_agent.py): `cd1a18879b7ac983a87a4ef8f7c4e0f6580093ffc218d53d69ec387e479b790f` по N2/N3 manifest.
* [N3 effective native](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147a2-aa60-7160-96cb-0f190bcfb65c/N3-evidence/payload/src/reachy_companion/autonomous/native_agent.py): SHA256 заново сверён `35bb8a658c8cc35f21a043dcad2bc14d05b54c74ca06e07735d9703cc51189a8`; номера строк выше относятся к этому payload.
* [N3 effective session](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147a2-aa60-7160-96cb-0f190bcfb65c/N3-evidence/payload/src/reachy_companion/autonomous/native_agent_session.py): заново сверён `77942bb3786e12ca0f80110fdc5ac18ce4665377dda4c7615a089673a8e02368`.
* Адресно прочитанные общие [runtime](/Users/notanonenough/reachy-companion/src/reachy_companion/autonomous/runtime.py), [state](/Users/notanonenough/reachy-companion/src/reachy_companion/autonomous/state.py), [client guards](/Users/notanonenough/reachy-companion/src/reachy_companion/client.py) совпали с frozen N3 `source-hashes.json`: соответственно `feadc9588682490269a02533e9dfc7f68c11958b015efff00eef2e2c48b8f0f1`, `6294b232587853d4aba026aeaeae8ebee1163fc06d88f63461210605f0ce3141`, `adc324fc93ec4dfc1d88249deaa4a7925e8d44e92dc15946877cef574fac1c4f`. Client прочитан только для identity и фактической pre-send границы; server/device source не исследовался.

Runtime/tests не запускались. Тесты выше — требования к будущему узкому implementation scope, не новые PASS receipts.
