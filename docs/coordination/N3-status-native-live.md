# N3 — Hub status placement candidate; live blocked before scheduler

17 октября 2026, Europe/Moscow. **Live НЕ принят: 0 actual accepted decisions, 0 inference requests.** Выполнен один запуск finite session с duration90s/period3s/deadline6s. Наблюдаемое окно процесса2,039s; отказ произошёл **до создания NativeAgent/Scheduler**: `native_agent_session.main → hardware = hub.get('/status') → TimeoutError`, ожидание HTTP status line с socket timeout300ms. Это другой участок того же transport/setup пути, не N2 `native_status_expired` во время polls и не fast6s deadline. Второго live запуска не было. **N3 завершён; normal listening ON, аппаратное/инженерное владение освобождено.**

Входы: N2 actual timestamps/source hashes, N1, P0, runtime-baseline, текущие PROJECT gates и адресные camera receipts A1/M1. Полные истории/чаты не читались; чаты/подагенты не создавались.9B/Whisper/Piper/Docker/factory/A1 Agent не изменялись/не перезапускались, fast7736 повторно не запускался. S0 не устанавливался. Manual say, spoken snapshot, AudioPeer, второй recorder отсутствуют.

## Минимальный fix и фактическое размещение

Session и отдельный native gateway перенесены с Mac на **Hub192.168.2.181**, во временный `/tmp/reachy-N3-01a147a2`. Использован существующий `/home/deploy/reachy-shadow/.venv/bin/python`, Python3.13.5/jsonschema4.26.0; attrs26.1.0/referencing0.37.0/rpds2026.9.1/specifications2025.9.1. Установки зависимостей не было. Production Hub PID78887 и installed Hub/client source не менялись.

Узкая правка только `autonomous/native_agent.py`, `native_agent_session.py` и одного адресного теста:

- Явный `--allow-configured-agent-url` разрешает **только exact `companion.network.agent_url`**, здесь `http://192.168.2.158:8090`; произвольные remote URLs, credentials/query/fragment/path отвергаются. По умолчанию остаётся прежний loopback transport. Тот же production bearer, Agent boot/mic/policy/owners и typed authority checks; это существующий Hub→Agent LAN endpoint, уже используемый production Hub.
- В этом opt-in Linux client отправляет `TCP_QUICKACK` после получения response headers, перед bounded body read. Используется CPython HTTPResponse socket, проверенный на actual3.13.5. Нет timestamp correction, cache, reconnect или POST retry. Неподдерживаемая платформа/ошибка socket — отказ.
- **Три последовательных GET сохранены:** Agent `/operator` → Agent `/status` → локальный Hub `/control/operator`; размеры65536, whole-sandwich300ms, received=BEGIN, expiry300ms, poll ceiling10Hz/один slot и stock fail-closed guards неизменны. Hub boot/ownership/stock guards не обходились.

Gateway18098/session8791 — на Hub; main disabled, Agent sole conversation owner. Raw fast18097 оставался на PC. Для него один SSH forward Mac→PC и loopback reverse Hub→Mac; inference placement остался cpu_pc, Mac не исполнял reducer/status. Один конечный Hub→Reachy SSH обслуживал только camera8772→Hub18772 и read-only receipts. Host keys и factory credential path сохранены, секреты не были argv/log. Родители transports жили в одном конечном orchestration lifetime.

| Effective source на Hub | N2 SHA256 → N3 SHA256 |
| --- | --- |
| native_agent.py | cd1a18879b7ac983a87a4ef8f7c4e0f6580093ffc218d53d69ec387e479b790f → 35bb8a658c8cc35f21a043dcad2bc14d05b54c74ca06e07735d9703cc51189a8 |
| native_agent_session.py | 431c668bfca4cda8bf637b7830ab4b36948fa96effc63f5b793d4e65a5cf04dd → 77942bb3786e12ca0f80110fdc5ac18ce4665377dda4c7615a089673a8e02368 |
| config.py, unchanged N2 operator_goal delta | 3a1b09d4554946e954f5033a44e8e52ce94d319c588f3e27e9aad5712590c107 |
| gateway.py, unchanged | 8f75faaf4ec4636a800b1c170cf44220dbefbc6e4c4d0207e2a7744502379fbc |

N1 patch повторно не применялся. N2 operator_goal сохранён дословно, без нового utterance, подсказки/replay или подмены model wait движением. Reviewed config изменён только под новый пустой Hub SQLite path; temperature0/output192/context4096/full projection и model/runtime/tokenizer/template pins прежние. Config SHA `dfbf3adf2fced92370183467b4aa59058ef8503ee2ee03b254673862af6f9f2f`; actual `placement-fix.patch` SHA `982e924cbfd42b8245d2f3e58a611a60cb38b13191e692cab5d36181c1477544`. Полные effective imports и source manifests сохранены. **14/14 native offline tests PASS**, socket/process/device guards сохранены; это fixtures, не live decisions.

## Реальные измерения перед единственным запуском

Все значения ниже — actual wall monotonic receipts на Hub, не fixtures. Errors включают исключения; total≥300ms отдельно может быть больше socket timeout, потому что socket timeout не является whole-request deadline.

| Путь / этап | Reads | min / median / max, ms | Whole ≥300ms / errors |
| --- | --- | --- | --- |
| Hub-local SSH, прежние GET |20|231 /241 /565|2 /0|
| Existing direct LAN, прежние GET |20|235 /253 /615|2 /0|
| Direct LAN + immediate ACK, HTTP probe |40|51 /67 /138|0 /0|
| Первый exact NativeAgent candidate check |2|78 /219 /361|1 /1|
| Exact NativeAgent per-leg audit, cadence≥100ms |40|46 /63 /126|0 /0|
| После fresh grant/ON, exact NativeAgent |3|54 /63 /116|0 /0|

Отдельный ACK probe через local SSH имел два cold transport timeouts и не стал выбранным status path. Сам по себе перенос на Hub не решал N2 gap. Улучшение после direct route/ACK измерено; объяснение через delayed ACK/Nagle согласуется с результатами, **packet trace не снимался, единственная корневая причина всех jitter не установлена**. Ранний exact361ms отказ сохранён, guard его отверг; устойчивость/SLO не заявляются.

В последнем40-read audit максимальный возраст предыдущего BEGIN при завершении следующего чтения **225,928ms**, ниже300ms. Generation7:32729088→32856064B (+126976B), read_calls15894→15956, gaps0/overflow0. Это основание для одной bounded попытки, не гарантия последующих network reads.

## Fresh grant, exact отказ и отсутствие effects

Перед положительными control POST: owners absent, quiet/privacy clear, Hub free, action idle, stock selected/known/unowned, worker idle/ok. Guarded OFF227→228; дождались paused/capture=false и штатного reap. Motor120→121=true через прежний paused guarded path, ON228→229. После штатного Agent neutral были только read-only ожидания, затем **все восемь fresh predicates true** перед gateway и повторно перед session; `expression_version`410→411 не подменялся. Исторический отклонённый ownership bypass N2 не повторялся. Для STOP/отзыва positive idle predicates не требовались.

Post-grant binding: Agent boot `f2a66c3b-dc89-4a2f-961d-ab738696b950`, mic229/policy121; Hub boot `5a2502a1-8b6f-49ff-9390-e6fdd213e24a`. Три actual native reads: generation8,57344→63488→69632B (+12288B/+6144frames), calls27→30→33, gaps0/overflow0; phase listening/turns3.

Gateway118594 boot `7e7dda91-8dc0-4ed9-9d1e-f403e6424b1b` проверен native_agent/fast+main idle. Единственный session PID118601 с exact argv в `live-events.json`: duration90/period3/deadline6/stock opt-in/direct status opt-in. Он прошёл initial operator GET и упал в **следующем setup-only aggregate Hub `/status`**, до NativeAgent construction. Socket timeout300ms возник при чтении HTTP status line; **отдельного actual duration этого failed GET нет**,2,039s — наблюдаемое parent окно процесса с imports/setup. `session-terminal.txt` содержит полный traceback. `session-report.json`, runtime poll journal, `/decision` journal и control listener не создавались; их отсутствие сохранено, synthetic session report не сочинялся.

Hub `/status` последовательно собирает factory `/api/daemon/status`, `/api/daemon/robot-app-lock-status`, `/api/state/full`. В отличие от маленького authority receipt это aggregate read. После завершения попытки16 read-only checks:8 native300ms reads **62–74ms/0errors**,8 diagnostic2s reads **120–139ms/0errors**. Diagnostic timeout2s не участвовал в admission. Повторный network timeout этими checks не воспроизведён; связь с camera startup/нагрузкой **не установлена**. Называть bootstrap fix принятым или network failure детерминированным было бы неверно.

| Критерий | Actual verdict |
| --- | --- |
| ≥10 silent accepted decisions | **BLOCKED**. IDs `[]`; fast requests0, main0, native loop polls0. Planned90s не выполнены. |
| PCM | **PASS только для read-only/preflight metadata windows**, включая generation8 +12288B;90s continuous acceptance отсутствует. Agent turns3 до/после, input не подавался. |
| Camera | **NOT EXERCISED / NOT ACCEPTED**. Exact M0/A1 producer210813 finite60s, source6182a651…/SDK631266c0…; frames0/gaps0/operator_last=null. Session не создал context owner/admission, IPC reader не открылся. Поэтому0packets здесь не доказывают camera integration defect. Exposure age UNKNOWN сохранена, synthetic freshness нет. |
| Stock | **NOT EXERCISED**. Own stock POST0, slot/NativeAgent не создавались, model choice отсутствует. Штатный grant neutral не засчитан как N3 settle.8 actual telemetry snapshots не являются доказательством N3 motion. |
| Compute reconciliation | **PASS в границе отсутствия requests**. Тот же gateway boot, fast/main idle, quarantine=[] до shutdown; PC7736 final healthy/slot idle, replacement не запускался. |
| STOP | **PASS для штатного listening OFF229→230**:10 rows capture=false/mic=false/read_bytes198656 без роста, затем motor121→122=false. Motion hard STOP, busy-STT cancel и privacy round-trip не тестировались. Context terminal revoke не выдавался: owner/scope не возникли. |

## Cleanup, финал и конкретный следующий scope

Gateway/session118594/118601 absent; Hub-local robot forward, Mac→PC и reverse forward завершены, transport control exit0. SSH child return255 при штатном control-master exit сохранён, отсутствие listeners проверено отдельно. Producer210813 absent,8772 absent, capture_thread_reaped=true/reader_shutdown_unknown=false; его token/grant/stage удалены. Installed camera source `80199eb7…` неизменен. Все свои Hub18090/18772/18097/18098/8791 и local18097 отсутствуют. Temporary Hub source/context/README полностью удалены **после** экспорта receipts; local source candidate сохранён для review, service не создана.

Отдельный fresh paused/free/idle ON230→231 восстановил production. **Финальная read-only сверка05:24:58–05:25:05 MSK:** прежние Agent205817/factory150625/NRestarts0/Agent boot и A1 hashes/config unchanged; mic231 ON/listening/capture=true, generation9,2635776→2719744B (+83968B), один arecord210872→Agent205817, gaps0/overflow0, volume100/errors=null/turns3. Policy122 motor=false/quiet=false/privacy=false, owners absent; Hub free/action=false/stock known/unowned; worker idle/ok. PCfast7736 PID/exe/creation/command совпали до/после, weights/runtime hashes сверены с P0; container/image/StartedAt/restart0/read-only/config SHA ae0535ca… сохранены.9B full instance attestation заново не делалась; действий load/unload/restart не было. **N3 явно освобождает владение Reachy/Hub/PC.** Исторические epochs здесь не готовые CAS payload.

Следующий scope — **startup-only hardware bootstrap**, не общий transport rewrite: разделить identity read aggregate Hub `/status` и300ms authority/effect reads; перед scheduler всё равно обязателен свежий native sandwich, перед stock — прежний fresh Hub boot/free/ownership/authority check. Для конкретного review оставлен `startup-only-PROPOSAL-NOT-APPLIED.patch` SHA `c183bda0b8d88772a73b0ce5ca63280275cc3d6b57c9b121fcee57fdd063739f`: bounded65536B/setup-only2s только для одного `/status` в main; default300ms и execute_stock неизменны. **Это отдельное предложение, не применено, не протестировано и не live accepted.** Сначала проверить его startup semantics/диагностику отказа с camera startup, затем новый явно выделенный finite run. Простое глобальное widening300ms, backdating и replay остаются недопустимыми. Нынешний candidate не доказал sustained freshness из-за сохранённого361ms preflight выброса. Постоянная служба и S0 — следующие отдельные задачи.

Evidence root: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a147a2-aa60-7160-96cb-0f190bcfb65c/N3-evidence/`. `analysis.json`/`analyze.py`, exact source/preimages/pins/patch/config, route/ACK/per-leg/native measurements, live-events/traceback, STOP/PCM/telemetry/camera/PC/final cleanup receipts. `SHA256.json` фиксирует bytes. Raw audio/images и transcripts не сохраняются; baseline worker projection оставлена только ok/phase. Source rollback — обратный `placement-fix.patch` после hash compare, вне hardware session; production A1 rollback не требуется.
