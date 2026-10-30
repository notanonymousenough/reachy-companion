# N0 — normal session: первая вертикаль camera context, source-ready

17 октября 2026, Europe/Moscow. **Source-ready; полный normal loop задачи №4 ещё НЕ завершён. Live/model/hardware acceptance отсутствует.** У A1 остаётся эксклюзивный аппаратный доступ. SSH, HTTP (включая loopback), устройства, deploy, model load и private configs в N0 не использовались; чаты/подагенты не создавались.

Входы: `design-2026-10-17.md` v4, `DELIVERY-PLAN.md` №4, `PROJECT.md`, `runtime-baseline.md`, `A0-continuous-capture.md`, `M1-camera-live.md`. Область N0 ограничена существующим autonomous session/context wiring. A0 Agent/capture candidate, camera/video producer, worker, launcher, factory SSH и README оставлены их владельцам.

## Найденный gap и сделанное изменение

В существующем `companion_session.run_session` уже есть normal lifecycle, finite/lease lifetime, независимые peer status / compute health / operator refresh, `Scheduler` и его раздельные fast/main/context jobs. `State.tasks` — существующий bounded task registry этого пути; новый scheduler/registry не добавлен. Успешный `wait` не останавливает clock ticks; занятой main не удерживает fast slot. Результаты проверяются по request/attempt IDs, boot/epochs и deadlines.

Конкретное препятствие camera integration было в `companion_session.main`: любой включённый context требовал `mode=memory_only` и live-source memory readback. Это исключало уже существующий gateway `ContextProvider(camera_memory)` из normal entrypoint, хотя scheduler умел получать его snapshots.

В одном runtime-файле добавлены:

- `--allow-camera-context` и `session_context`: camera_memory с явно выбранным `video_url` допускается в normal session; camera opt-in вместе с memory-only readback отвергается до создания ресурсов. Прежний memory_only whitelist/hash gate сохранён. На session host не создаётся camera reader: используется существующий `/context` gateway adapter.
- `report.decisions`: bounded suffix из существующего ledger, только `request_id`, `activity`, UTC `at`. Это принятые reducer decisions, а не просто HTTP submissions. Размер ограничен `ledger_cap`; все decisions за длинный runtime этим полем не гарантируются. Reasoning/dialogue/memory сюда не копируются; существующий speech report не менялся.

Новый `config.autonomous.normal.example.json` выбирает 2 s period/deadline, **кандидат** Qwen3.5-0.8B Q8 fast, существующую 9B main, camera_memory и отдельный пустой namespace/store. Fast/main model audit=false и model endpoints не заполнены; запуск inference должен отказать до подготовки действительных pins. Это не заявление о cadence/latency или установленной модели. `speech.enabled=false` означает отсутствие локального ALSA backend: normal session использует уже существующий `RemotePCM`/`SpeechAdapter`/`HttpTTS`. `motion.enabled=false`, actuators=simulated: этот пример не разрешает моторы. Export/workflows выключены.

Gateway и session должны читать одну согласованную конфигурацию. `data/n0-normal-context.sqlite3` — отдельный новый пустой store, необходимый существующему camera_memory provider; не подключать прежнюю пользовательскую память. N0 не пишет facts, не меняет memory schema/evolution и не включает S3.

## Честное состояние камеры и ownership

Переиспользованы без правок `ContextProvider` → `decode_packet` → `LatestFrameProcessor` → `LatestVideo` → `State.update_context`. Poll/processing находятся вне inference lanes. Raw pending slot максимум один, выполняющийся buffer удерживается до возврата; generation/admission/owner TTL и terminal revoke сохранены. Смена boot/epochs не становится автоматическим reconnect.

M1 показал разные frame IDs/pixels при PTS=0, но физический возраст неизвестен. Поэтому normal fast snapshot получает существующий `camera.pixel_quality` с `state=unknown` (либо stale/no_data/disabled), пустым summary, `age_ms=null`, `age_bounds_ms.upper=null`, lineage/source IDs. Это metadata наблюдения, не свежая scene. Нулевые PTS не исправлялись и не превращались в timestamp; unknown camera не включается в main observations, где State требует fresh и известный upper bound ≤2 s.

Source diff не открывает устройства, не создаёт media/motor владельца, не запускает Agent/daemon/recorder и не меняет существующий физический executor. Реальное отсутствие второго physical owner на стенде **не проверено**. Существующие authority checks и executor stop/reap proof остаются обязательными.

## Офлайн-проверки

**51 tests PASS, failures/errors/skips=0:** 7 новых адресных + 44 существующих State/Scheduler/Gateway/causality/context regressions. Из suite явно исключены два теста с authenticated HTTP round-trip. Во время всей suite `socket.socket` и `subprocess.Popen` заменены на немедленный отказ: HTTP/device/model процессы не запускались. Python 3.13.0, jsonschema 4.26.0 из уже существующего `/private/tmp/reachy-head-validate-20261015/bin/python3`; ничего не устанавливалось. Глобальный python без jsonschema не подходит для этих проверок.

Новые тесты вызывают настоящий `run_session`, `Scheduler/State`, `AudioPeer/AudioPolling`, `AudioAdapter`, `SpeechAdapter/Playback/RemotePCM`, SQLite ContextProvider и video decoder/processor/cache. Только transport, lease renewal, PCM source/sink, STT/TTS/model заменены явными in-process fixtures; **это не actual LLM, PCM или camera acceptance**. Synthetic producer не запускает SDK или recorder.

Последний сохранённый прогон:

| Критерий | Офлайн-результат / граница |
| --- | --- |
| Новые решения без реплики | 12 разных fast request IDs, ≥12 принятых decisions; dialogue пуст, new_turn=0. Fixture decisions, не 12 настоящих LLM inference. |
| Main pending, fast продолжает | После silent phase один явно synthetic main input; main удержан Event, 4 fast completions при running main, 5 snapshots с pending task. |
| Сенсоры не стоят при main | 4 разных source frame IDs в pending snapshots; synthetic producer +12 кадров, audio poll +1. Это progression fixture observer и poll, **не** PCM byte progression физического Agent. |
| Fast занят | Пока один fast удержан, synthetic camera +≥10 кадров и audio poll +≥2; второй fast request не стартует. |
| Bounded/latest/unknown | ≤1 raw pending frame, ≤12 sensors, ≤8 pending tasks; camera summary пуст, upper age=null. |
| Literal speech | После main completion ровно исходный fixture текст «Алиса, сколько будет два плюс два?» передан существующему TTS path, без перефразирования. Акустического звука/Алисы не было; произвольный fast `say` по-прежнему запрещён. |
| Revoke/late results | Реальный session shutdown при смене fixture microphone authority; held main после release не вызывает TTS; старый camera admission неактивен, terminal-revoked context owner отвергается. Held fast после STOP не принимается. |
| Второй owner | Новые source lines не создают физических writers/readers; socket/subprocess forbidden во всех тестах. Аппаратный exclusive-owner proof остаётся OPEN. |

`report.accepted` по прежнему означает успешную finite session/cleanup в существующем протоколе, **не** полную приёмку №4. `continuous_acceptance=false` сохранено. Тестовые ускоренные period=15 ms не являются профилем или прогнозом аппаратной производительности.

Воспроизведение 7 адресных проверок:

```sh
PYTHONPATH=src:tests /private/tmp/reachy-head-validate-20261015/bin/python3 -m unittest test_normal_camera_session -v
```

Полный список 51 теста, offline guard runner и machine receipts находятся в evidence ниже. Exact source patch прошёл `patch -p1 --dry-run`, затем применён **только в новом временном каталоге** к сохранённому preimage; все output hashes совпали, Python compile и JSON parse PASS. `git diff --check` PASS. Проверен CLI `--help` без ресурсов.

## Exact source manifest / diff

Source HEAD reference: `59bc59a6433dee432371319ba48ad0aeab0985f4`. Другие изменения рабочего дерева не включены в bundle.

| Файл | Preimage SHA-256 → output SHA-256 |
| --- | --- |
| `src/reachy_companion/autonomous/companion_session.py` | `a490281382de8c5e0199b8b38260c747188ae952af2f1c778e344e7d7a47c433` → `8efbe01db5512261a8b4794bfcec3145abcf14e3612450b312b95e3456c6e093` |
| `config.autonomous.normal.example.json` | новый → `b047536c278c61368a889f06c7e3441e4d7d90839791aae191dab6709dc261a9` |
| `tests/test_normal_camera_session.py` | новый → `d293441462c5bd03d6fc90c81feafc8a38dff72c673e25d2c97c5b198764e350` |

Evidence root:
`/Users/notanonenough/.codex/visualizations/2026/10/17/01a1476b-cfa7-7fd2-b818-472147effaab/N0-source-ready/`.

- `source.patch`: **`40c3fb5756455e3a0b5a9613d7d868d17343cc4b91f82993aeafaa8a5966fc23`**; один runtime diff (+31/−9 lines), два новых файла. Документ N0 — отдельный handoff, не runtime payload.
- `manifest.json`: **`e4caadf8cfd61f9fc37a5907345c52011a227105e159e7a02756165159157e63`**; exact preimage/output hashes, 25 source dependency pins (включая State/gateway/contracts/context/adapters/Hub/config/schema/pyproject). Это локальная source compatibility lock, **не проверка установленных imports** и не готовый image/package lock.
- `payload/`, `companion_session.preimage.py`, `offline-tests.txt`, `offline-results.json`, `offline-bundle-check.json`, `run-offline.py`; `SHA256.json` фиксирует все payload/evidence bytes, кроме самого checksum-файла.

A0 frozen manifest остаётся `c75e964a6f58352421005ec1c513aa053eca653034add1a178e774df8cebe303`; N0 его не менял. Повторно хешированы только два A0 patch файла: Agent `52913ef59ff3719459c8eba94008c89123917c199db223dd524964993a317d2b`, capture `f5f41c4b8a3435de137b1224202a1ded2dcb7c17ec157116d68f4b2d83b9bc08` — совпали. Installed Agent/capture imports в N0 не проверялись.

## Почему полный loop не закрыт и ровно одна следующая часть

Рабочий R1/Q1/A0 baseline — normal **Agent→Hub router→PC worker**, не `AudioPeer` protocol. `companion_session` требует уже существующий `/status` с `source_boot/closed/permitted/operator_ready`, `/observation`, lease и remote PCM endpoints. Обычный Agent:8090 этих контрактов не предоставляет. Включить новую AudioPeer capture session поверх A0 ON означало бы добавить capture/semantic owner; N0 этого не делает. A1 continuous-capture acceptance сама по себе не доказывает совместимость с AudioPeer.

Motor gap отдельным набором новых capability names здесь не маскируется: normal `MotionAdapter` допускает только bounded native antenna17; он требует ready/exclusive actor и physical hold proof. Baseline использует существующий Hub stock/factory executor. `stock`/`breathing` нет в normal FastChoice dispatch, arbitrary `say` отвергается State; менять профиль на motor=true или подменять attentive→stock нельзя. Существующий main commit уже умеет literal speech, но инициативный speech без входного candidate этим N0 не добавлен.

**Следующая одна часть — N1: native-owner adapter для этого же normal session на принятом A1 baseline.** Связать Scheduler с authority/status/turn receipts существующего Agent и Hub stock executor, сохранив единственного semantic/media owner, bounded slots и revoke/unknown rules; разрешить один малый stock/breathing intent и literal speech через действующих executors. Не создавать второй recorder/daemon и не переносить hardware в autonomous ядро. Scope требует явной передачи session wiring и baseline owner hooks после A1; это следующий source slice, затем отдельный аппаратный оператор. До него полный №4 и stock acceptance OPEN.

## Deployment prerequisites и следующий finite запуск

Ниже **команда существующего N0 entrypoint**, а не разрешение применить её к Agent:8090. Она пригодна только после N1 либо отдельно подтверждённого уже существующего совместимого AudioPeer owner с единственным capture/output; отсутствие такого owner сейчас — blocker. Не запускать `realtime_audio_session`/device runtime ради обхода этого prerequisite.

Перед передачей аппаратному оператору нужны: завершённый A1 с exact effective pins и continuous PCM receipts; один согласованный native-owner/peer bridge без второго normal reply loop; подготовленный отдельный gateway с N0 source pins, audited **уже загруженными** fast/main models/tokenizer/template/context/backend pins и доступными endpoint/credentials; один M1 camera IPC producer с отдельным video token/owner lease и без synchronous spoken snapshot; fresh boot/epochs, peer/controller/source identity, worker idle/free Hub, known cleanup и разрешения privacy/quiet/output. Не использовать исторические mic215/policy116 как новый CAS. Транспорт обязан жить дольше всего окна и cleanup: прежний factory SSH lifetime 65 s для этого недостаточен. PTS/physical age остаются unknown.

Примерный finite window — 60 s; 2 s период даёт место для ≥10 **actual** LLM completions только при измеренной достаточной производительности. Timeout/UNKNOWN не исправлять model reload или вторым inference owner. Live manifest обязан отдельно указать effective source/config/import/model hashes и факт owner transfer; N0 не знает установленных autonomous pins, не заменять их локальным HEAD.

```sh
python3 -m reachy_companion.autonomous.companion_session --mode normal \
  --config "$N0_REVIEWED_CONFIG" --companion-config "$COMPANION_CONFIG" \
  --token-file "$GATEWAY_TOKEN_FILE" --output "$N0_FRESH_REPORT" \
  --peer-url "$EXISTING_PEER_URL" --peer-stop-port "$EXISTING_PEER_STOP_PORT" \
  --controller "$EXISTING_CONTROLLER" --source-boot "$FRESH_SOURCE_BOOT" \
  --lifetime finite --duration 60 --allow-capture-output --allow-camera-context
```

Environment paths/identity здесь заполняет назначенный владелец из свежего preflight; token value в argv не передаётся. Пример конфига требует сначала заполнить endpoints/audit pins и отдельный пустой store. Команда не открывает motor grant и не доказывает stock/breathing. После N1 его допустимый stock opt-in должен быть указан его собственным точным manifest, без использования antenna17 flag как замены. Локальный status endpoint по прежнему `127.0.0.1:8791`; собственный `/stop` связан с session/controller/source. Никакая команда выше не исполнялась в N0.

Rollback собственного finite процесса: `kill -TERM "$OWNED_N0_SESSION_PID"` и `wait "$OWNED_N0_SESSION_PID"` из того же supervisor shell; проверить report cleanup, terminal context revoke, actual occupied jobs и media/peer stop. UNKNOWN — удержать ownership и остановить rollout, не запускать replacement. После подтверждённого cleanup остановить только собственный gateway/producer, отозвать их grants и восстановить exact preimage session/config из сохранённого bundle. Agent/factory/worker/models не перезапускать. Возврат normal listening — отдельный существующий guarded ON со свежими boot/epochs после подтверждённого OFF/unowned; persisted microphone state из backup не восстанавливать. Это план будущего оператора, не выполненный rollback.

Неподтверждённые критерии: ≥10 actual LLM decisions в физической тишине; actual main pending с fast inference и PCM/frame progression; отсутствие второго физического owner; малое stock/breathing действие; реальный literal playback и акустическое поведение/Alice; live STOP/privacy latency и late-result suppression; устойчивый 2 s cadence/ресурсы; полная combined/continuous acceptance. Fixtures ни один из этих live критериев не закрывают.
