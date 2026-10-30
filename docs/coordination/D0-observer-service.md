# D0 — observation-only service lifecycle, source-ready candidate

17 октября 2026, Europe/Moscow. **ОФЛАЙН срез завершён: одна непрерывная native session без finite cap, bounded metadata/history, graceful stop и одноразовый preflight arm. Установка и hardware acceptance НЕ выполнялись.** SSH/HTTP/deploy/models/devices не использовались; socket/process guards в native tests запрещали реальную сеть/устройства. Другие чаты/подагенты не создавались. Аппаратное владение не запрашивалось и не принималось.

Входы: `PROJECT.md`, [R6](R6-observer-native-live.md), [Q3](Q3-native-loop.md), [R5](R5-observer-recovery.md), текущие native modules. Это ранний постоянный observation loop: normal Agent остаётся единственным владельцем capture/STT/main/reply. Camera/context/main/speech/motion/workflows/stock в service режиме закрыты. Motor grant не выдаётся. Agent/server/worker/shared runtime не менялись; параллельный R11 patch не затронут. Sustained R6 FAIL из-за 8 gaps сохраняется; эта работа его не исправляет и не переобъявляет PASS.

## Изменение и границы

`native_agent_session --service --metadata <path>` явно выбирает service lifetime; `--duration` с ним несовместим. Без `--service` остаются default60 и предел1..180s. Service проверяет отсутствие context/main endpoint/speech/motion/workflows и запрещает camera/stock opt-ins. Создаются прежние NativeAgent/NativeScheduler/NativeGateway ровно один раз; periodic session/model restart, reconnect, rebind и catch-up не добавлены.

Runtime сохраняет прежние poll/fast/health slots, deadlines, 300ms BEGIN guard, health/compute-boot/quarantine checks, transient R5 recovery и permanent physical/context closure после gap. Known STOP/privacy/authority/boot/source/counter change остаются terminal. Увиденный revoke не снимается прежними значениями позже. R10 composite-read limitation не исправляется этим срезом: полный новый read должен увидеть retirement, physical lane всё равно закрыта. D0 не даёт physical recovery proof.

SIGTERM/SIGINT и существующий authenticated owner-fenced `/stop` закрывают local admission и проходят общий bounded cleanup: до1.5s drain занятых slots, затем отдельный health receipt до0.5s, без замены занятого health slot. Зависший/UNKNOWN job остаётся busy/uncertified в report; remote inference не объявляется отменённым по завершению local Future. Control listener также закрывается и учитывается. Unit `TimeoutStopSec=10s` — внешний предел процесса, не remote cancellation proof.

В service режиме clean controller stop/known revoke возвращают exit0 **только при cleanup_verified=true и errors=[]**. Это lifecycle result; `accepted` — отдельное качество. Startup/runtime/uncertified cleanup дают nonzero. Running status всегда `accepted=false`; финальный accepted требует observed receipt, ≥10 accepted decisions, verified cleanup, отсутствие любого gap и revoke. `continuous_acceptance=false`/`live_acceptance=false` сохранены. При любом gap sustained acceptance остаётся false, даже после recovery/eviction истории.

## Ограничение памяти и диска

- Gaps: последние256 в deque; `gap_count`, `gaps_omitted`, recoveries/read_failures/late_receipts и суммарная `unavailable_s` сохраняются за всю session. Активный gap входит в сумму; eviction не уменьшает total.
- State ledger уже bounded configured `ledger_cap` (рекомендуемый service256, schema cap4096). Report содержит только suffix accepted IDs из этого ledger, плюс `decisions_total`, `decisions_omitted`, `decision_history_cap`; event counts и elapsed_s сохраняются за всю session. Suffix не объявляется полным журналом IDs.
- Каждые5s metadata заменяется атомарно: `metadata.local.json`, один `.previous`, максимум один незавершённый `.tmp`; каждый snapshot≤1MiB. Финальный snapshot принудительный. Отдельный fresh `report.local.json` один на arm. Unit UMASK0077, snapshots/report0600, core dumps выключены, stdout/stderr не пишут content в journal. Это bounded snapshots, не append-only журнал. Стартовые ошибки видны как unit failure/consumed arm; подробный startup traceback намеренно не сохраняется в service journal.
- Нет PCM, transcripts, bearer values, passwords или private config contents в metadata/arm/units. Native receipt остаётся прежней metadata projection. Authentication — чтение существующих private files; environment file содержит только пути/SSH alias. Перед новым arm оператор архивирует прежний final report/consumed arm в собственное bounded evidence retention, а не накапливает файлы service автоматически.

## Reviewed launch/unit артефакты

Repo paths ниже — все новые; runtime modules изменены только два.

| Артефакт | Назначение / intended Hub path |
| --- | --- |
| `deploy/autonomous/observer_service.py` | launcher → `/home/deploy/reachy-shadow/observer-service/deploy/autonomous/observer_service.py` |
| `deploy/autonomous/reachy-observer-session.service` | `/etc/systemd/system/reachy-observer-session.service`; явный start, один arm |
| `deploy/autonomous/reachy-observer-gateway.service` | `/etc/systemd/system/reachy-observer-gateway.service`; прежний gateway в native profile |
| `deploy/autonomous/reachy-observer-forward.service` | `/etc/systemd/system/reachy-observer-forward.service`; один foreground OpenSSH forward |
| `deploy/autonomous/observer-paths.env.example` | private `/home/deploy/reachy-shadow/observer-service/paths.local.env`, только file references |

Используется существующий Hub Python `/home/deploy/reachy-shadow/.venv/bin/python`; новый пакет/контейнер/autossh/framework не требуется. Stage `src/` должен содержать существующее замыкание R6 dependencies/catalog, а не только два изменённых файла. Все три units: `Restart=no`, без `[Install]`, WantedBy, timers, sockets и boot auto-start. Session требует и BindsTo gateway, gateway требует и BindsTo forward: уход dependency вызывает stop dependent, без reconnect/restart; ordering обратный при общей остановке. Dependencies **не** останавливаются автоматически при выходе session: gateway/forward остаются доступны владельцу для independent idle/UNKNOWN reconciliation, затем владелец явно убирает их. Никаких действий с PC model process units не выполняют.

Launcher до session startup переименовывает `arm.local.json` → `arm.local.json.consumed`. Существующий consumed marker запрещает повторный запуск даже при восстановлении файла с теми же values. Startup failure/SIGKILL также расходует arm. Marker/report не удаляются unit-ом. Новый coordinator сначала делает fresh preflight, сохраняет старый evidence, затем создаёт новый arm; `systemctl restart` без этого не возобновляет session. Epochs/boot не считываются автоматически для нового grant.

## Одна exact deployment dependency

**Нужен подтверждённый постоянный Hub→PC OpenSSH auth/host-pin path для доступа к существующему PC loopback18097.** R6 доказала только temporary Mac→PC + Hub reverse lifetime. Наличие уже подходящего private key/SSH config на Hub офлайн не подтверждено; credentials не копировались, новые keys/accounts не создавались. Поэтому `observer-paths.env.example` содержит явные `REQUIRES_EXISTING_HUB_PC_*` placeholders; forward unit — reviewed candidate, не установленная/проверенная связь. Следующий transport owner должен либо подставить уже существующие разрешённые Hub-local auth/config/known_hosts references и проверить host pin/BatchMode, либо вернуть эту одну dependency координатору. D0 не расширяет срез до auth/platform rewrite.

Forward shape: `ssh -F <existing-config> ... -N -T -L 127.0.0.1:18097:127.0.0.1:18097 <verified-PC-alias>`, strict host checking, BatchMode, ExitOnForwardFailure, finite keepalive failure, без multiplex attach к чужому master и без restart. Destination alias должен разрешаться в прежний PC192.168.2.134/user. Fast7736 остаётся PC127.0.0.1:18097; LAN bind/model launch/download/replace не выполняются. IdentityFile/known_hosts/config **пути**, не credentials, могут присутствовать в argv; secret values отсутствуют.

## Install / stop / rollback — следующему единственному hardware owner

Это recipe, **не выполненные команды**. D0 освобождён; следующий coordinator отдельно передаёт аппаратное владение. До этого units не устанавливать/не запускать.

1. После решения transport dependency создать private Hub stage по указанному пути, перенести только manifest payload + нужные неизменённые R6 dependencies. Сверить source hashes, существующий venv/imports и отсутствие чужих listeners18097/8097/8791. Existing production Hub/Agent/worker не заменять. Нативно проверить три unit-а `systemd-analyze verify`, затем установить без enable и выполнить daemon-reload. На macOS такой verifier отсутствовал: D0 проверила INI sections/ExecStart parsing/Restart=no/no-Install, не заявляет Linux unit acceptance.
2. `paths.local.env` mode0600: подставить exact **существующие** private companion config, gateway token и SSH auth/pin paths. Не переносить private files в source/evidence и не подставлять secret values в Environment/ExecStart. `observer.local.json` — согласованный с gateway R6 native profile: period3/deadline6, fast existing CPU endpoint через Hub127.0.0.1:18097 с прежним verified model/tokenizer/template contract; main.base_url=null, context/speech/motion/workflows=false, ledger_cap256. Если operator_goal используется, changed_at записать как фактическое время подготовки, без R6 timestamp ошибки.
3. Read-only fresh preflight: normal listening/capture ON, unowned, motor OFF, quiet/privacy=false; current boots/epochs/source_generation и increasing PCM; Hub/worker idle, fast actual identity/idle. Никаких ON/stock grants этот launcher не выполняет. Записать mode0600 arm со **свежими** `agent_url`, `hub_url`, `agent_boot`, `microphone_epoch` (int), `policy_epoch` (int), `controller`. Agent URL — exact companion configured URL; Hub — pinned loopback endpoint. Исторические R6 values не payload. Остальных ключей/credentials в arm нет.
4. Убедиться, что прежний report/consumed arm уже разобран и сохранён владельцем; только после fresh preflight убрать эти прежние два файла. Явно `systemctl start reachy-observer-session.service`. Unit dependency ordering не означает readiness: fresh entrypoint reads и health решают admission; startup failure расходует arm и не retry-ится. Если сервис не стартовал, прочитать unit result/consumed arm, завершить свои gateway/forward после idle reconciliation и вернуться к новому preflight.
5. Штатная остановка: `systemctl stop reachy-observer-session.service` (SIGTERM) либо прежний authenticated `/stop` с точным текущим controller/source/session binding; ACK сам по себе не cleanup proof. Проверить final report + separate current compute idle/same identity. При UNKNOWN/busy **не** рестартовать gateway/model и не выдавать новый arm; оставить диагностику/transport под явным владельцем до reconciliation. После verified idle явно остановить `reachy-observer-gateway.service`, затем `reachy-observer-forward.service`; проверить отсутствие своих процессов/listeners. Normal Agent продолжает слушать.
6. Rollback после stop/reconciliation: удалить только эти три не-enabled unit-а и daemon-reload, сохранить evidence, удалить свой stage. В source stage можно reverse exact patch и сверить R5 base hashes. Старый finite entrypoint остаётся доступен; production Agent/worker/models rollback не нужен. Busy remote process не kill-ить ради rollback.

Прямая source entrypoint форма для review: `python -B -m reachy_companion.autonomous.native_agent_session --service --metadata <private-latest-path> ...` с прежними config/companion-config/token-file/output/agent-url/hub-url/boot/epochs/controller и observation/configured-url opt-ins. Для unit recipe используется launcher с consumed arm, без stock/camera flags.

## Exact diff, hashes и offline evidence

База двух modules и исходного native test **точно R5/R6**, а не Git HEAD: они уже были untracked. Чужие checkout changes сохранены. Minimal code/test/deploy patch включает9files; этот отчёт отдельно. Exact [manifest](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-5907-7b62-9f8d-651bf9d22b1a/D0-evidence/source-manifest.json), [patch](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-5907-7b62-9f8d-651bf9d22b1a/D0-evidence/observer-service.patch), preimages/payload в том же D0-evidence.

Patch SHA256: `1f50d518900259b251b0aeaf080ca245ef680309720426c84f5a1ec5ef2abcc9`.

| Module | R5/R6 base SHA256 | D0 output SHA256 |
| --- | --- | --- |
| native_agent.py | `c8fb477feffaaf86f5e5e339ed015d9d38a304769552d3d8ed6da6d2f668c615` | `3cbde7e359d4848faf892b83364c957f9b087cd7537fae88c4e6df188c057c5c` |
| native_agent_session.py | `3931c0e4f90ca1ffc2911eebc59820ca77b6b8b60e06c527f115f9cd774ef2b0` | `6246ac84ff17ae354aefc98f37fde14190084632646afaa6b723d6f6e100a8ca` |

**32/32 offline PASS,3.304s**, existing Python3.13 venv, без установки dependencies. [Полный последний test log](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-5907-7b62-9f8d-651bf9d22b1a/D0-evidence/offline-tests.txt), [validation/patch receipt](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-5907-7b62-9f8d-651bf9d22b1a/D0-evidence/validation.json).

```sh
PYTHONPATH=src:tests /private/tmp/reachy-head-validate-20261015/bin/python -B -m unittest \
  test_native_agent_session test_observer_service test_native_stock_rearm_gap -v
```

Meaningful checks: один scheduler >190s fake monotonic без сети/models, >50 accepted synthetic silent decisions и bounded ledger suffix; privacy revoke clean exit и отсутствие новых calls после прежних values;600 gaps →256 suffix/600total/60s total, active gap добавляет2s; service STOP с занятым poll; **реальный SIGTERM** через main signal handler при занятых fast+poll, cleanup/listener drain и restoration signal handler; malformed/single-use arm/failed-start no retry; snapshot rotation/cap/private modes; default finite guards и прежние R5/N4/stock UNKNOWN/ownership tests. Дополнительно прежний R10 exact composite-read negative trace PASS; server dependency не обойдена. Первые новые fixture runs выявили race при чтении ещё не присвоенного Job и неполные main mocks; fixtures исправлены. Два ранних signal test processes завершились143 до установки handler из-за startup fixture error; последний test проверяет, что signal посылается только после готовности jobs/handler. Реальной сети guard не допустил.

Patch dry-run/apply/reverse на отдельной локальной копии:0/0/0, output/base hashes сверены. Payload Python AST parse PASS. Runtime/state/client/config/gateway не изменены D0; точные dependency hashes — в manifest. Никаких live decisions/soak/24×7/systemd service acceptance эти tests не доказывают.

## Один следующий hardware soak критерий

Отдельный sole owner после fresh handoff запускает **одну ≥30min observation-only service session** с тем же Agent/compute/source binding, без session/model restarts и effects; metadata suffixes/размер файлов остаются bounded, total counters/durations монотонны, реальные accepted/discarded IDs считаются раздельно. Затем owner-fenced STOP или deliberate privacy revoke должен завершить session с проверенными occupied=false/remote idle/listener cleanup и без automatic resume; новые значения требуют отдельного fresh preflight. Каждый естественный gap остаётся в totals и удерживает sustained acceptance=false. Это критерий lifecycle soak, не требование скрыть gaps и не приёмка полной автономии/physical recovery.
