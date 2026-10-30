# N1 — native Agent observation/ticks + one existing Hub stock action

17 октября 2026, Europe/Moscow. **Source-ready bridge candidate; Live PASS отсутствует.** Работа только офлайн: ни SSH/HTTP (включая loopback), ни устройства, deploy, model load или private configs не использовались. Чаты/подагенты не создавались. Аппаратное владение оставалось у Q2.

Входы: `N0-normal-session.md` (gap/next part), `A1-continuous-live.md`, `runtime-baseline.md`, `PROJECT.md`. Изменены только autonomous native adapter/session, gateway/config mapping, новый config example и адресные тесты. N0 session не переписан; audio pump/lifecycle, camera producer, worker/models, transport/README и A0 artifacts не менялись.

## Конкретный bridge

Новый entrypoint — `python3 -m reachy_companion.autonomous.native_agent_session`. Он использует существующий `Scheduler.advance`, `State.apply/bind`, `Job`, context gateway/provider и bounded ledger. `NativeScheduler` имеет специализированный `NativeState`; отдельного scheduler/framework/registry нет. Создаются один status polling slot, существующие inference/context slots и максимум один single-use stock job. Нет AudioPeer/lease/remote PCM, AudioAdapter/STT, SpeechAdapter/TTS, MotionAdapter/native actor, daemon или device reader.

`NativeAgent.read` читает authenticated **Agent `/operator` → Agent `/status` → Hub `/control/operator`**, сверяет полную typed authority до/после, boot/mic/policy status и A1 actual PCM counters. Agent `/status` нужен напрямую: Hub `/control/status` отфильтровывает A1 counters. Только loopback URLs к уже существующим операторским tunnels; новый transport не создаётся. Каждое чтение ограничено 65 536 bytes/.3 s, весь sandwich <.3 s. Poll запускается не чаще 10 Hz, максимум один реально занятый job; latest receipt заменяет прежний. Ошибка, старение .3 s, смена boot/epochs/owners/privacy/quiet или регресс counters latch-ит withdrawal, закрывает admission и не делает reconnect/ON/retry.

В FastView добавлены три metadata sensors: `native.elapsed` (реальное local monotonic elapsed), `native.pcm` (source_generation/read_bytes/read_frames/read_calls/gap_events/overflow_events), `native.voice` (phase, capture_active, turns, busy, main_stage=UNKNOWN). Polling и counters не ждут fast inference. Counters сравниваются только внутри generation; новая generation начинает собственные значения, continuity через manual `/say` не выдумывается. `processing` не называется доказанным main: это может быть STT. Pending `native-voice` имеет `execution_busy_phase_observed_completion_UNKNOWN`; age — длительность **локального наблюдения busy**, не remote task latency/ID. Переход turns приходит как counter receipt, без transcript, dialogue или второго semantic turn.

Камера проходит прежний ContextProvider/latest frame path. PTS0/неизвестная exposure age остаются `camera.pixel_quality.state=unknown`, summary пуст, age upper=null. Software status sensor ready означает только свежий receipt. Нового camera reader или physical-age estimator нет. Native metadata занимает три из 12 sensor slots; context остаётся bounded/latest.

Конфликт conversational owners исключён кодом: `NativeState.ingest` отвергает utterance/workflow; `apply` отвергает start/commit/say. Нет speech/audio/motion adapters и main task. `NativeGateway` запрещает `/main` и `main()`. На стороне gateway `native_agent.enabled=true` также запрещает main до model/tokenizer вызова. `/health.conversation_owner=native_agent` проверяется при подключении и далее; несовместимый gateway не принимается. Human/Алиса turns продолжает существующий Agent→Hub router→PC worker. Инициативный speech disabled; manual `/say` и synchronous spoken snapshot не используются.

## Один небольшой stock intent

В native profile **`motion=settle`** означает один фиксированный существующий Hub stock expression: head roll=1° → neutral, по .5 s, остальные head axes/antennas=0. Это два finite targets через **один** POST `/actions/expression`; не новый motor owner и не attentive→stock mapping. Legacy `attentive` mapping остаётся прежним вне native profile. Gateway object grammar, tuple grammar и parser переключаются вместе с native config; schema assets не менялись. `actuators=simulated` в example оставляет собственные legacy drivers выключенными; внешний stock effect разрешается только отдельным `--allow-stock-settle` и действующей Agent motor permission.

Перед POST: fresh latest admission, free Hub/stock selected/not unknown/no owned UUID, тот же pinned Hub boot и текущий exact operator/expression version. POST идёт существующим `client.guarded_control`: preconnect, fresh operator, full authority compare, per-send .3 s deadline. Payload содержит Agent boot, mic epoch/enabled, policy epoch, expression version. Существующий Hub lock/stock owner повторно проверяет binding перед каждым factory effect и сохраняет own-UUID stop/reconciliation. Adapter не выдаёт motor grant и ничего не меняет в Agent policy.

Slot резервируется один раз **до** dispatch. Повторных POST за сессию нет, включая потерянный ответ. Поздний/revoked preflight возвращает not_dispatched; failure/непроверенный результат — UNKNOWN, cleanup/accepted=false. Успех означает только `steps_observed=2, pose_verified=false, hard_stop_certified=false`, а не физическую позу или сертифицированный STOP. Профиль ограничивает targets, не измеряет фактическое перемещение относительно исходной позы.

Локальный session `/stop`/SIGTERM отзывает собственный admission и context, удерживает ссылки на занятые jobs и ждёт конечные receipts. Это **не** выключение штатного Agent и не подтверждение physical stop уже отправленного Hub действия. Для user STOP/privacy служит существующий Agent authority switch: его epoch fence проверяет сам Hub. Unknown/in-flight job не объявляется свободным, replacement запрещён до reconciliation. По окончании сессии normal Agent продолжает слушать.

`report.accepted` требует ≥10 принятых reducer decisions, cleanup, свежий final compute health с fast/main idle и без quarantine; при stock opt-in также требуется observed dispatch. Одних HTTP/status success недостаточно. `continuous_acceptance=false`, `live_acceptance=false` остаются явными. Bounded decision suffix ограничен ledger_cap; полный счётчик принятых решений отдельно в counts.

## Офлайн-проверки

**64 PASS; failures/errors/skips=0: 12 новых +52 regressions.** Во всём прогоне `socket.socket` и `subprocess.Popen` немедленно отвергаются. Synthetic native GETs/model completion и guarded HTTP transport заменены in-process fixtures; используются настоящие State/Scheduler, ContextProvider/SQLite, decoder/latest processor и Hub.expression/stock executor с fixture factory. Это не actual PCM/model/camera/motor acceptance.

Последний сохранённый прогон:

| Критерий | Offline result |
| --- | --- |
| Silent fast | 23 разных принятых IDs; dialogue/candidates пусты; new_turn=0, main calls=0 |
| Busy voice/capture | Fixture phase=processing; одна generation3, +6400B/+3200frames между fast snapshots; 5 native polls; main stage UNKNOWN |
| Fast occupied | Удержанный fast, status продолжает расти; max actual fast slots=1; tick_busy_gap сохраняется |
| Bounded status | 10 Hz ceiling, один held status slot, .3 s expiry latch; поздний fast после withdrawal не принимается |
| Camera | Changing fixture source IDs через настоящий decoder/cache; physical age upper=null/empty summary, pending raw ≤1 |
| Native turn receipt | turns0→1/phase listening обновляют metadata, не создают utterance/main/reply |
| Stock | Один dispatch, два реальных вызова существующего Hub stock path с fixture factory, ≥10 решений и cleanup; no second motor owner |
| Revoke before effect | Policy epoch изменён внутри fixture POST до Hub.expression: factory writes=0; retry=0. Local close/expression-version revoke до POST: sends=0 |
| Ownership/UNKNOWN | start/commit/say/attentive отвергнуты; main blocked и в gateway; remote quarantine не превращается в cleanup от завершённого local future |

Отдельно исключены два existing authenticated HTTP round-trip теста и весь `test_companion_session.SessionTests`: каждый его setUp открывает настоящий HTTP AudioPeer. При первоначальном выборе этого класса offline socket guard остановил все 14 setUps **до сети**; сохранён `initial-http-guard-rejections.txt`. После явного исключения получен итог выше. Guard не ослаблялся. Legacy joined loop проверен 7 in-process N0 tests; core State/Scheduler/gateway/causality и 17 offline Hub stock regressions включены.

```sh
PYTHONPATH=src:tests /private/tmp/reachy-head-validate-20261015/bin/python3 -m unittest test_native_agent_session -v
/private/tmp/reachy-head-validate-20261015/bin/python3 "$N1_BUNDLE/run-offline.py"
```

Python 3.13.0/jsonschema4.26.0 — существующий tmp venv, ничего не устанавливалось. `git diff --check`, source compile/JSON, CLI `--help`, patch dry-run и настоящее применение **только к temporary source preimages** с полным совпадением output hashes PASS. Source verifier post PASS. Tests .015 s cadence — ускоренные fixtures, не hardware latency promise.

## Exact diff / hashes

Source HEAD reference `59bc59a6433dee432371319ba48ad0aeab0985f4`. N0 `companion_session.py` dependency остаётся SHA `8efbe01db5512261a8b4794bfcec3145abcf14e3612450b312b95e3456c6e093`. В payload нет прочих working-tree изменений.

Evidence/bundle root:
`/Users/notanonenough/.codex/visualizations/2026/10/17/01a14779-9158-7313-9f80-6039bc804491/N1-source-ready/`.

`source.patch`: **`98e2351f75b522ff24c89bd4bdfaf7481e852fee92f69ecc915d5a63e099e3ee`**.
`manifest.json`: **`c73b98a0d206130b7a2b4b5bfa9768ba97e6f0e51faaa8fd589180926a1da3a9`**.

| Payload | Preimage SHA-256 → output SHA-256 |
| --- | --- |
| autonomous/config.py | `ae7cc0ebc566630716a4ddf2809f44ba2962d053f8cfb97b04a1c9e75706e306` → `463e21d2518b1e0a238666dfcace2e511efed80430d97393ce5ee1c3059f45f7` |
| autonomous/gateway.py | `7f17c104a22bfe91d54bd26b0643609c79075bacffaf448cd3fe745eaada0cd8` → `8f75faaf4ec4636a800b1c170cf44220dbefbc6e4c4d0207e2a7744502379fbc` |
| autonomous/native_agent.py | новый → `4c1bb7c3edd2d15a960fab11e5aee13301f99a8b13fbaf0da8665929ac4284d6` |
| autonomous/native_agent_session.py | новый → `431c668bfca4cda8bf637b7830ab4b36948fa96effc63f5b793d4e65a5cf04dd` |
| config.autonomous.native-agent.example.json | новый → `4773cb606064f287219b7ea3ec031a26d75261c9c733c4c3a31434eaa61d00db` |
| tests/test_native_agent_session.py | новый → `f6b3f0810f1171921570397b65b85f45e0e43721e087ca6f445f93e9b79888fb` |

В manifest — 24 local dependency pins; это source compatibility lock, не проверка установленных imports. Existing Hub stock implementation SHA `008be03f69d9564c9f476b086ddf9eb3fa8e587682c6791b776234933f8c682d`, client `adc324fc93ec4dfc1d88249deaa4a7925e8d44e92dc15946877cef574fac1c4f`. Для stock оператор проверяет effective Hub/client code и supported bound expression receipts; несовпадение не обходить новым executor.

Agent hooks не нужны: installed A1 `/status.capture_pcm` достаточен. **Нет N1 patch для Agent.** A1 effective Agent должен оставаться `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b`, capture `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6`, existing opt-in=true. A0 frozen manifest не менялся; повторная локальная сверка Agent patch `52913ef59ff3719459c8eba94008c89123917c199db223dd524964993a317d2b` и capture patch `f5f41c4b8a3435de137b1224202a1ded2dcb7c17ec157116d68f4b2d83b9bc08` совпала.

Bundle содержит payload/preimage, manifest, source.patch, build-bundle.py, verify-source.py, run-offline.py, offline tests/results и bundle-check. `SHA256.json` фиксирует bytes всех evidence кроме самого checksum-файла. Этот handoff — отдельный документ, не runtime payload.

## Следующий finite deployment, prerequisites и rollback

Назначенный следующий hardware оператор сначала сверяет Q2/A1 effective imports и свежее normal ON/unowned состояние. Исторические boot/mic221/policy116 **не** являются новым CAS. Нужны готовые finite tunnels Agent+Hub и camera producer lifetime >60 s+cleanup; Agent:8090 прямой authenticated `/status`; Hub stock executor свободен/not unknown. Entry point не создаёт tunnels/producer и не использует `realtime_audio_session`.

Согласованные source session/gateway должны пройти manifest pins, а gateway и session — читать один reviewed **native_agent-enabled** профиль. Для новой копии исходников (не поверх чужих изменений):

```sh
python3 "$N1_BUNDLE/verify-source.py" --root "$N1_SOURCE_ROOT" --phase pre
patch --dry-run -d "$N1_SOURCE_ROOT" -p1 -i "$N1_BUNDLE/source.patch"
patch -d "$N1_SOURCE_ROOT" -p1 -i "$N1_BUNDLE/source.patch"
python3 "$N1_BUNDLE/verify-source.py" --root "$N1_SOURCE_ROOT" --phase post
```

В текущем working tree source candidate уже материализован: нужен только post check, повторно patch не применять. Два существующих файла имеют сохранённые preimages; четыре новых файла не заменяют установленный Agent/worker. Проверить реальные Python import paths на session/gateway hosts; один локальный HEAD этого не доказывает.

Пример config намеренно **не готов к inference**: fast candidate 0.8B Q8 endpoint=null/audit=false, main audit=false, camera URL только образец. До запуска нужны exact уже доступный fast endpoint, weight/runtime/tokenizer/template/context/device audit pins и измеренная возможность ≥10 completions/60 s. Не менять normal worker/9B и не грузить модели ради обхода failed preflight. В native режиме gateway main disabled. Новый отдельный пустой `data/n1-native-context.sqlite3`/namespace normal; не подключать старую пользовательскую память. Camera admission/token/owner — отдельный existing M1 producer; PTS0 age остаётся unknown. Gateway — прежний `python3 -m reachy_companion.autonomous gateway --config "$N1_REVIEWED_CONFIG"`, только после подготовки audited fast endpoint; его собственный credential env устанавливает существующий supervisor, secret не передаётся в argv.

Stock opt-in требует **уже выданной свежей** motor permission, quiet/privacy=false и unowned authority; baseline motor=false сам по себе недостаточен. Команда ниже ничего не включает и отвергнет отсутствующий grant. Для чистой observation/ticks части можно убрать только `--allow-stock-settle`; это не motion acceptance.

Точная следующая finite session команда после этих prerequisites (не исполнялась N1):

```sh
PYTHONPATH="$N1_SOURCE_ROOT/src" "$N1_PYTHON" -m reachy_companion.autonomous.native_agent_session \
  --config "$N1_REVIEWED_CONFIG" --companion-config "$COMPANION_CONFIG" \
  --token-file "$N1_GATEWAY_TOKEN_FILE" --output "$N1_FRESH_REPORT" \
  --agent-url "$AGENT_LOOPBACK_URL" --hub-url "$HUB_LOOPBACK_URL" \
  --agent-boot "$FRESH_AGENT_BOOT" --microphone-epoch "$FRESH_MIC_EPOCH" \
  --policy-epoch "$FRESH_POLICY_EPOCH" --controller "$N1_CONTROLLER" \
  --duration 60 --status-port 8791 --allow-native-observation \
  --allow-camera-context --allow-stock-settle
```

Значения paths/identity берёт владелец из свежего preflight. Agent/Hub auth читается из existing companion Config/token, gateway/session auth — из отдельного token-file. Значения секретов не логируются. Никакого manual `/say`, spoken snapshot, второго ASR/main или synthetic utterance для подачи инициативы. Initial speech может оставаться disabled.

Rollback: SIGTERM **только собственного** finite session PID и wait; проверить execution_busy, final compute_after, terminal context revoke и stock receipt. При UNKNOWN сохранить ownership/ссылки, не запускать replacement, проверить existing Hub stock owned UUID/stop/reconciliation; не делать blind stop. Session не выключает и не перезапускает normal Agent. Если нужен user STOP — существующий microphone-off из baseline; его epoch fence подавляет поздний output/effect. Возврат ON — отдельный guarded операторский шаг со свежим boot/epochs, не persisted state restore.

После известного cleanup остановить только свой autonomous gateway и camera producer/его grants. Проверить post hashes, выполнить `patch --dry-run -R ...` и `patch -R -d "$N1_SOURCE_ROOT" -p1 -i "$N1_BUNDLE/source.patch"`, затем verifier pre. Reverse удаляет только четыре N1 additions и возвращает два preimages; при несовпадении чужих изменений abort. A1 Agent/capture/normal worker/Hub/factory/private configs rollback этого source slice не затрагивает.

Следующий результат — один finite **actual** native fast loop с ≥10 принятых IDs в тишине, progressing A1 PCM при обычной voice busy и camera metadata, один stock dispatch только при grant. Аппаратные owner proof, model latency, фактическое движение/STOP и акустика ещё не проверены. Source action gap не оставлен: stock bridge реализован; оставшиеся prerequisites — deployment/fast pins/физическая приёмка назначенным оператором.
