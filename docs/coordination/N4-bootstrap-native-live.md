# N4 — startup прошёл; native loop снова остановлен freshness guard

17 октября 2026, Europe/Moscow. **Startup-only fix применён и проверен; автономный live НЕ принят.** После короткой реальной bootstrap проверки выполнен **один** planned90s/period3s/deadline6s native run. Scheduler отозвал admission с `native_status_expired`: предыдущий receipt достиг **303,619ms**, пока следующий3GET sandwich ещё выполнялся. Новый sandwich завершился за **234,196ms**, но возраст предыдущего BEGIN к этому моменту был **344,948ms**. **0 accepted decision IDs,1 actual fast response,0 own stock POST.** Лимиты/политика не менялись, второго loop или extra model command не было.

**Финальная read-only сверка05:49:18 MSK:** normal listening/capture **ON mic235/generation11**, PCM2420736→2498560B (+77824B), gaps0/overflow0; прежние Agent205817/factory150625/NRestarts0 и A1 hashes/config. **Motor policy124=false**, quiet/privacy=false, owners absent, Hub free/stock known/unowned, worker idle. Свои producer/gateway/session/transports/tokens/stages убраны. **N4 завершён конкретным runtime blocker и освобождает аппаратное/инженерное владение.**

## Точный startup diff и offline проверки

Исходные входы: N3 status report/proposal/actual pins, P0, runtime-baseline/PROJECT; N2/N1 только необходимые commands/source deltas. Новая resilience policy не менялась. Все source bytes перед запуском сравнены с N3 manifest: отличаются только два адресных startup файла, config/gateway/operator_goal сохранены.

- `NativeClient.get(path, *, setup_hardware=False)`: явный флаг разрешён только для `/status`; socket timeout **2s**, body cap **65536B**, прежние bearer/endpoint/QUICKACK/JSON checks. На прочих paths исключение отвергается до HTTP. Default остаётся **300ms**. Это socket-I/O timeout из N3 proposal, не новая whole-request deadline и не authority receipt.
- Только один стартовый `hardware=hub.get('/status', setup_hardware=True)` в `native_agent_session.main` использует исключение для Hub boot identity.
- После discovery и **до NativeScheduler** требуется `native.latest=native.read()`: новый Agent `/operator` → Agent `/status` → Hub `/control/operator`, прежний whole-sandwich300ms/BEGIN/typed PCM/identity. Startup/fresh-native exception не создаёт scheduler.
- Runtime polls/active freshness/effect admission, `execute_stock` и fresh Hub boot/free/ownership/authority checks не менялись. N1 patch не применялся повторно; model observe/wait не подменялся движением.

N3 proposal SHA256 `c183bda0b8d88772a73b0ce5ca63280275cc3d6b57c9b121fcee57fdd063739f`: `patch --dry-run`, затем реальное применение в отдельной локальной копии **exact N3 preimages**, exit0/0. Итоговый `startup-fix.patch` дополнен обязательным свежим native read перед scheduler. Два новых теста проверяют timeout2s/распространение исключения, сохранение default300ms, запрет setup-флага на authority endpoint,65536B cap и отсутствие scheduler/report при startup либо fresh-native timeout. Прежние14 native tests сохраняют socket/process/device guards, STOP/privacy/late-response/stock checks.

**16/16 offline tests PASS локально2,449s и на Hub4,924s**, без установки зависимостей. Команда: `PYTHONPATH=src <existing-python> -B -m unittest discover -s tests -p test_native_agent_session.py -v`; local venv `/private/tmp/reachy-head-validate-20261015`, Hub `/home/deploy/reachy-shadow/.venv`, Python3.13.5/jsonschema4.26.0. До итогового Hub PASS минимальный stage обнаружил отсутствующий catalog resource; добавлен hash-identical installed `pollen-emotions-v1.json`, source/service не менялись. Системный/bundled local Python ранее не имели jsonschema; validator stub не использовался.

| Effective source в Hub stage | N3 SHA256 → N4 SHA256 |
| --- | --- |
| native_agent.py | 35bb8a658c8cc35f21a043dcad2bc14d05b54c74ca06e07735d9703cc51189a8 → 3880deeac5589e0f63d1568032045f0a684289ac11e76b9f2178d34e7d55d073 |
| native_agent_session.py | 77942bb3786e12ca0f80110fdc5ac18ce4665377dda4c7615a089673a8e02368 → 2dfd03fc39db0fb85f97ae3dcd7de98f80e024cdacc6207585991bfcca62aa02 |
| autonomous/config.py unchanged | 3a1b09d4554946e954f5033a44e8e52ce94d319c588f3e27e9aad5712590c107 |
| autonomous/gateway.py unchanged | 8f75faaf4ec4636a800b1c170cf44220dbefbc6e4c4d0207e2a7744502379fbc |
| test_native_agent_session.py | 585918bafb39b704b47ee20eb4d9224ec5074dfbf3ba2010e3a409f28ef78699 |

`effective-imports.json`, `effective-stage-final.json` подтверждают реально разрешённые imports и неизменность stage source до удаления. Installed Hub source не заменялся. N3 размещение сохранено: session/gateway/status на Hub192.168.2.181, exact configured Agent LAN URL и Linux QUICKACK; fast7736 inference на PC, один Mac→PC forward и Hub loopback reverse. Отдельный конечный Hub→Reachy transport обслуживал camera и read-only receipts; lifetime600s покрывал setup/live/cleanup69,830s. Camera source `6182a6516d93d4ab065c1ba5ba0c3c6fe8ebfb57e28f08d7dea8f83a8139ae56`, SDK `631266c0e53223463cb5a226b12201e4cc263134d016405656d9de9ae35400c6`, producer finite60s — без изменений.

## Реальный bootstrap, authority и runtime trace

Свежие все8predicates проверены до positive controls: owners absent, quiet/privacy clear, Hub free, action idle, stock selected/known/unowned, worker idle. Штатный guarded OFF231→232; paused/capture=false и reap; motor122→123=true через paused path; ON232→233. Штатный Agent neutral дождались read-only; перед session повторно все8true. Ownership bypass не повторялся. STOP/revoke не зависели от idle.

Agent boot `f2a66c3b-dc89-4a2f-961d-ab738696b950`, Hub boot `5a2502a1-8b6f-49ff-9390-e6fdd213e24a`, live mic233/policy123; generation10. Три pre-session native reads дали +12288B/gaps0/overflow0. После старта camera PID211284 короткий discovery `/status` занял **55,089ms**, следующий fresh native read **55,361ms**. В самой session startup setup-only `/status` занял **64,816ms**; fresh native read прошёл и scheduler создан. В этом запуске aggregate latency была ниже300ms: факт успешного startup не доказывает воспроизведение/устранение всех прежних network timeouts.

Gateway PID121395/boot `74690ea0-0edb-46ac-bb27-81d6eac10f87`, session PID121425. Наблюдаемое окно процесса4,448s; runtime report2,119s включает bounded cleanup после отзыва, это не выполненные90s. **6 actual native reads** (первый до scheduler +5scheduled), min/median/max **51,886/74,767/234,196ms**, exceptions0. Все отдельные chains уложились в300ms; этого недостаточно для freshness предыдущего BEGIN.

| Hub monotonic timestamp / участок | Actual |
| --- | --- |
| Предыдущий принятый BEGIN | 847378.857877066 |
| Его полный read / completion |106,697ms /847378.964553700 |
| Следующий read BEGIN |847378.968629887 (receipt-BEGIN847378.968663793) |
| Agent `/operator` |13,180ms |
| Agent `/status` |165,327ms |
| Hub `/control/operator` |53,758ms |
| Withdrawal |847379.161495764; previous age303,619ms; poll in-flight=true |
| In-flight age на withdrawal |192,866ms; завершалась третья leg |
| Следующий read completion |847379.202825443; chain234,196ms; previous age344,948ms |

Журналы пишут actual wall-monotonic BEGIN/end/error/previous receipt без timestamp correction/cache. Дополнительный logging overhead не вычитался. Строгий guard отозвал admission **до завершения новой цепочки**. Это тот же interval-between-receipts blocker N2, теперь после успешного startup на N3 placement/QUICKACK. N3 audit46–126ms не был гарантией отсутствия выбросов; прежний361ms preflight outlier не отменён. Корневая причина всех LAN/Agent jitter не доказана; новый протокол/лимит/policy N4 не вводил.

## Loop / PCM / camera / motion verdicts

| Критерий | Actual verdict |
| --- | --- |
| ≥10 accepted silent decisions | **BLOCKED**, accepted IDs `[]`. Один actual request `e0a24f48-1288-40ba-906e-2c26e381f693`, response2230,833ms,567input/32output tokens; model выбрал `a=observe`, motion отсутствует. Ответ пришёл после withdrawal и не принят. Main requests0; deadline6s не причина отказа. Нет extra command для PASS. |
| PCM | **Короткая metadata progression PASS**, sustained90s не приняты. Generation10:221184→235520B (+14336B) в последних admitted receipts; вместе с последним completed-after-withdrawal243712B (+22528B). Read_calls103→110→114, gaps0/overflow0. Native phase listening→processing observed, turns3 до/после; main-stage/голосовой turn не доказывались. |
| Camera | **Транспорт exercised, joined acceptance не принята**. Producer7frames/gaps0; один decoded packet seq1/frame `d86879ec-aae6-4b13-9da6-2e3d0355632c`, admitted=false, recorded191,488ms после withdrawal. Доказанного accepted frame в действующем loop нет. PTS/running-time0, source_age_upper=null/source_capture_time_verified=false: exposure age UNKNOWN. Late rejected packet не подменяется свежим. |
| Stock/motion | **NOT EXERCISED**. stock_used=false/receipt=null/unknown=false, own stock POST0. Модель выбрала observe; штатный Agent grant-neutral не засчитан как N4 stock. Telemetry сохранена, но сама по себе не доказывает выполнение N4 action. |
| Terminal context revoke | **PASS**: `terminal=true, revoked=true`, request `d337f5e1-129d-4da5-a7dc-0832080e5f6c`; поздний camera packet не admitted. |
| STOP / motor revoke | **PASS в проверенной границе**. OFF233→234 дал10стабильных receipts319488B/capture=false/mic=false; motor123→124=false. Hard motion STOP и точное busy-STT cancel не сертифицировались. |
| Compute reconciliation | Исходный session report **cleanup_verified=false** сохранён: fast ещё busy=true при bounded local cleanup. Поздний actual response затем завершился; отдельный health того же gateway boot подтвердил fast/main idle/quarantine=[] на847385.070530442, **до** shutdown gateway и закрытия fast forwards. PC7736 финально healthy/idle. Replacement не запускался. |

## Cleanup, финал и разрешения

Producer211284/listener8772/stage/grant/token отсутствуют, `capture_thread_reaped=true`, `reader_shutdown_unknown=false`; installed camera SHA80199eb7… неизменен. Gateway121395/session121425 absent; Hub18090/18772/18097/18098/8791 и local18097/18098/8791 отсутствуют. SSH control exits0; child255 при штатном master exit сохранён и дополнен проверкой отсутствия listeners. Tokens удалены. Временный Hub `/tmp/reachy-N4-01a147b1` полностью удалён **после экспорта** на05:49:47 MSK. Claims/scope сняты, finite service не создана.

Свежий guarded ON234→235 вернул production. Финальная read-only сверка **05:49:15–05:49:18 MSK**: прежний Agent boot/PID205817, factory150625/NRestarts0, один arecord211411→205817; mic235/listening/capture=true, generation11,2420736→2498560B (+77824B), gaps0/overflow0, turns3/volume100/errors=null. Policy124 motor=false/quiet=false/privacy=false, owners absent; Hub free/action=false/stock selected/known/unowned, worker idle/ok. Initial final observer ошибочно сравнил весь operator с меняющимся phase listening/processing; эти receipts сохранены отдельно. Повторная **read-only** проверка сравнила persistent `control_authority` и PCM, не меняя runtime policy или аппаратное состояние.

Installed A1 agent SHA `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b`, capture SHA `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6`, config `a6171f68e6fc20feebb48475991517f61412afc693f0c58f999f077f0eedd0d5` сохранены. Hub78887/NRestarts0, installed client/hub source и config7f11d114… unchanged. PC7736 PID/creation/exe/command совпали с N3 до/после; weights SHA37ae482d…/exe0bbac3a5… проверены свежо; прежние Docker container/image/StartedAt/restart0/read-only/configae0535ca… совпали.9B/Whisper/Piper/Agent/factory/Docker не изменялись/не перезапускались; полного нового9B attestation не делалось. S0 не установлен; manual say/spoken snapshot/AudioPeer/второй recorder/semantic main отсутствовали.

Первоначальный transfer был отклонён auto-review: README содержал factory credential; затем архив без README — как недостаточно явно разрешённый private-source egress. Обхода не было. После сообщения координатора **проверено само исходное human message**00:10:43.924UTC в parent rollout: постоянное разрешение на доступные инструменты/взаимодействие с robot/Hub/PC. Это существующая авторизация, **не новый ответ на вопрос**. Config deployment.hub и свежий hostname reachy-hub/Hub78887, prior N3 receipts доказали user-owned destination. Явный manifest39files/133313B и один дополнительный несовпадающий dependency logging_utils.py предъявлены reviewer с новыми доказательствами; **SCP одобрен**, README/secrets/config.local/tokens/SSH credentials/logs/raw media не передавались. Credential helper использовал уже установленный Hub README через local symlink; public host pin — existing known_hosts. Final read-only script также явно manifest/одобрен. Нерешённого approval blocker нет.

Следующий scope — отдельная explicit observer resilience policy по read-only review R3 либо иной адресный runtime fix; **не повторный startup fix/полный loop с прежней политикой**. N4 не реализовывал policy proposal и не расширял300ms. Rollback local candidate: reverse `startup-fix.patch` после hash compare; production A1 rollback не требуется. **Normal listening ON, motor OFF, аппаратное владение освобождено.** Исторические epochs выше описывают receipts, не готовые новые CAS payload.

Evidence root: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a147b1-39c0-7122-999b-c1230961c203/N4-evidence/`. `analysis.json`/`analyze.py`, exact preimages/diff/proposal application, local+Hub tests/effective imports/manifests, human authorization/transfer proof, bootstrap/per-leg/poll/withdrawal journals, actual decision/context/camera metadata, telemetry, STOP/PCM/compute/final source+PC/cleanup receipts. `SHA256.json` фиксирует bytes. Raw audio/images/transcripts не сохранялись.
