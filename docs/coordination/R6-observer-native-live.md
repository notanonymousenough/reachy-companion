# R6 — real native observer recovery completed

17 октября 2026, Europe/Moscow. **Одна finite90s observation-only session завершилась по duration:29 requested/29 actual completed fast responses,23 accepted silent `wait` IDs,6 discarded,8 gaps/8 recoveries. Цель ≥10 реальных silent decisions — PASS. Sustained full acceptance — НЕ принята: оригинальный R5 `accepted=false` сохранён.** Cleanup verified, occupied jobs/compute idle. **Финал06:20:26 MSK: normal listening/capture ON mic239/source_generation14, motor OFF policy124; R6 завершён и явно освобождает исключительное аппаратное/инженерное владение Reachy/Hub/PC.**

Входы: [R5](R5-observer-recovery.md), [N4](N4-bootstrap-native-live.md), [P0](P0-fast-readiness.md), [S1](S1-alice-short-live.md) и baseline. Новых чатов/подагентов не создавалось. Production source/config/services не менялись; Agent/worker/models/Docker/factory не перезапускались. Capture/reply продолжали принадлежать одному обычному Agent. No manual say/Алиса stimulus, новых AudioPeer/camera/capture/effect owners нет.

## Exact staging и запуск

Current checkout уже содержит R5 output: все4 source/test hashes и6 unchanged dependencies совпали с R5 manifest. Повторный patch **не** накладывался. Передача на user-owned Hub192.168.2.181 прошла с явным secret-free manifest **47files/166785B**, archive SHA256 `4a84b8c9d02a2bb78096cf75cbe168b1ecdf067e8e5276a6a4350cfb6103f425`. Без README/credentials/config.local/tokens/logs/raw media. Fresh hostname reachy-hub/Hub78887/NRestarts0 и исходное direct human authorization00:10:43.924UTC из N4 проверены; approval blocker/reviewer refusal в R6 нет. Installed private companion config читался только на Hub, не доставлялся и не экспортировался.

Hub stage `/tmp/reachy-R6-01a147da`, existing Python `/home/deploy/reachy-shadow/.venv/bin/python`, effective imports **из stage**, все47 hashes повторно совпали после run и непосредственно перед removal. Production installed Hub не заменялся. В таблице — фактические resolved modules, полный manifest/paths в evidence.

| Effective module | SHA256 |
| --- | --- |
| `config` | `8433bdac7a3ef6f23e7ba24685d21a7f970a8df90e44163f95fe1e8cb6fe1e6d` |
| `client` | `adc324fc93ec4dfc1d88249deaa4a7925e8d44e92dc15946877cef574fac1c4f` |
| `autonomous.native_agent` | `c8fb477feffaaf86f5e5e339ed015d9d38a304769552d3d8ed6da6d2f668c615` |
| `autonomous.native_agent_session` | `3931c0e4f90ca1ffc2911eebc59820ca77b6b8b60e06c527f115f9cd774ef2b0` |
| `autonomous.config` | `3a1b09d4554946e954f5033a44e8e52ce94d319c588f3e27e9aad5712590c107` |
| `autonomous.gateway` | `8f75faaf4ec4636a800b1c170cf44220dbefbc6e4c4d0207e2a7744502379fbc` |
| `autonomous.runtime` | `feadc9588682490269a02533e9dfc7f68c11958b015efff00eef2e2c48b8f0f1` |
| `autonomous.state` | `6294b232587853d4aba026aeaeae8ebee1163fc06d88f63461210605f0ce3141` |

Локально **23/23 native tests PASS2,758s**, Hub **23/23 PASS6,200s**, без установки dependencies. Первый Hub test pass был невозможен из-за отсутствующего public `config.autonomous.native-agent.example.json`; hash-identical fixture добавлен до live, отказ сохранён отдельно. Это packaging correction, не startup/runtime policy fix. Native startup сразу прошёл: N4 setup-only Hub `/status` **57,288ms** при разрешённом socket2s/body65536; обязательный следующий fresh native read **41,045ms** до scheduler. Runtime300ms/BEGIN/typed authority/QUICKACK unchanged. Адресная integration source правка и подтверждающий второй run не потребовались.

Согласованный config/gateway: native_agent, main base_url=null, period3s/deadline6s, context.enabled=false, speech/motion/workflows=false. Operator goal — observation only; камера/stock opt-ins отсутствуют. Gateway boot `645ded74-6236-4c2a-92e2-47956c331eb6`, PID124835; session PID124841. Existing fast7736 endpoint PC loopback18097 доставлялся одним Mac→PC forward и Hub reverse18097. Robot Agent читался exact configured LAN `http://192.168.2.158:8090`; Hub control — loopback8080. Нового backend/main/reply owner нет.

Единственная actual command находится в `events.json/session_started.argv`: `session.py` — read-only telemetry wrapper exact R5 `native_agent_session.main`, duration90/status8791, **только** `--allow-native-observation --allow-configured-agent-url`. Fresh authority: Agent boot `f2a66c3b-dc89-4a2f-961d-ab738696b950`, mic239/policy124/expression830; Hub boot `5a2502a1-8b6f-49ff-9390-e6fdd213e24a`. Исторические epochs не использовались как новые CAS payload; control POST не выполнялись.

## Реальный loop, counters и cadence

Scheduler окно **90,028s**, reason=duration/errors=[], native_withdrawn=null. `accepted=false`, continuous_acceptance=false, live_acceptance=false сохранены byte-for-byte в оригинальном `session-report.json`; exit1 — ожидаемая R5 граница из-за8 gaps. Observation metadata recovery подтверждена отдельно от полного acceptance.

| Метрика | Реальный результат |
| --- | --- |
| Fast requested / completed / accepted | **29 /29 /23**; все responses real gateway→existing0.8B inference |
| Invalidated / discarded | **6 /6**, те же6 IDs; старые bindings не переиспользованы |
| Gaps / recoveries / unavailable duration | **8 /8 /1,857531s** |
| Skipped unavailable ticks / fast_execution_busy events | **1 /0**; не mixed со discarded/compute busy |
| Native scheduled polls / actual reads / valid receipts | **845 /846 /838**; отдельный846-й — startup read |
| Native errors / late receipts | **8**:4URLError timeout+4TimeoutError; late_receipts=0 |
| Successful native read min/median/max | **41,045 /65,126 /155,668ms** |
| Все native reads incl failures min/median/max | **41,045 /65,365 /384,629ms** |
| Poll BEGIN interval min/median/max | **99,459 /103,348 /389,579ms**, без extra retry burst |
| Actual fast completion min/median/max | **2,170 /2,328 /2,505s**, deadline6s сохранён |
| Actual request cadence min/median/max | **2,989 /3,004 /6,000s**, одна skipped3s tick |
| Compute health | **447/447 OK**, latency **3,934 /6,344 /18,022ms**, boot unchanged/quarantine=[] |
| Compute sampled busy | **fast337 samples /main0**; итог fast=false/main=false |
| Session effects | stock_used=false/receipt=null/unknown=false; own stock POST0 по exact disabled path, scheduler main/speech/context/camera0 |

У8 ошибок HTTP legs: Agent `/operator`2, Agent `/status`4, Hub `/control/operator`2. Leg timeout301,531…311,233ms; целые failed chains302,124…384,629ms. Это natural read-only transport timeout, без fault injection. Socket timeout не whole-request SLA. Gaps начинались по expiry **предыдущего BEGIN**, а не объявляли свежим late cache. Compute health guard0,5s не сработал и не расширялся. Непосредственная системная причина LAN/Hub jitter не доказана.

| Gap | Hub BEGIN-expiry start | Recovery consumed at | Duration ms |
| --- | --- | --- | --- |
| 1 | 849214.963533487 | 849215.180250628 | 216.717 |
| 2 | 849227.646006514 | 849227.900635153 | 254.629 |
| 3 | 849241.926686324 | 849242.142598001 | 215.912 |
| 4 | 849245.863940753 | 849246.129157851 | 265.217 |
| 5 | 849264.980758045 | 849265.215838728 | 235.081 |
| 6 | 849277.769869871 | 849278.065119900 | 295.250 |
| 7 | 849287.461654400 | 849287.666582731 | 204.928 |
| 8 | 849288.525174958 | 849288.694972668 | 169.798 |

## Прямое доказательство recovery fence

Fast `0d8b3aad-fccb-413b-bec9-d0696a6cdae9` requested849214.162035205 в local observation generation0. Gap start849214.963533487, invalidated849214.968583006; текущий poll оставался единственным occupied slot. Fresh receipt прежних boot/mic239/policy124/source14 был consumed849215.180250628. Старый реальный fast response завершился после gap и **discarded849216.436088697 уже при unavailable=false/generation1** — recovery не воскресил прежний binding.

Следующий обычный tick `9d11a209-0957-4cc5-86ec-e6942aaac6ca` requested849217.162237947, generation1, принят849219.334145561 как `wait`. Fresh same-authority/source_generation admission восстановился. То же invalidation/discard behavior наблюдалось для ещё5 fast IDs. Actions после первого gap до конца session оставались **physical_closed_after_gap=true**; context_closed_after_gap=true и context не включался. STOP/epoch/boot/owner/malformed/source change terminal guards сохранены exact R5, но намеренные live interleavings в этом scope не exercised.

23 accepted decision IDs (все `wait`, полные UTC acceptance timestamps — оригинальный report):

```text
de94517b-8ed6-48e5-9254-b0d0467ec887
9d11a209-0957-4cc5-86ec-e6942aaac6ca
67ec8a90-3561-431c-9e08-44cdab18554b
21d60b95-69ae-4065-9ae0-ecf86db21dd8
25068b04-3bff-4732-b39e-9b627944a69e
9659d255-d527-4c5a-a865-74b5a34a1b2e
1c533bf7-a270-425f-810a-c57070f7a5fe
6e313a26-e468-4ff1-a547-42820bd85ea6
7449f0ea-5b6a-4ef2-9f74-0b5555b4126f
44a4c2fa-cb3b-45b3-b113-7483d0253cab
8d8483ab-94b1-4dfd-ab61-c32d2db61564
efe04365-3700-43b2-a134-2d7109e171ce
b1267a72-1327-4f67-8c43-54f8f13de34f
969438e6-fb54-4225-bcd6-079822cb3ce2
683978f1-f5e2-47da-a18a-2a367b08f340
a2a92e3e-d0a9-41a9-b1e0-9cdde6336372
ae0d0caf-9550-4b2a-a714-b788925045a1
6e56f439-c8d8-4d79-9c56-d2faa6a4015b
47b13e5c-a308-4327-8877-a14063ae262f
d67fa60f-7e49-45ff-b9cd-bfd802dd7a94
9e7d0738-7735-4114-9a17-a934e91e8239
9eae5db3-7ab9-46ed-8546-9bef0362af43
6e5157eb-52be-4b4b-8295-8466ff8e561c
```

6 discarded IDs:

```text
0d8b3aad-fccb-413b-bec9-d0696a6cdae9
34c4d4f4-e7ad-4982-8ee7-d0b5cdc63f80
e7aed64a-d4cf-481a-a8d5-5cf117a77c54
b7573fc4-370a-4d69-8cdc-90cf66a1e933
1a2d1713-e65c-4cea-937d-d92dcc1ed770
f954c6b6-3685-428b-9e3b-f69aa175319c
```

## PCM и installed baseline

838 valid native receipts — **одна source_generation14**, mic239/policy124/expression830, turns4 throughout. Первое/последнее native PCM **22818816→25702400B (+2883584B)**, read_calls11084→12475; gaps/overflow0. Это actual read receipt metadata, не exposure/sample-clock proof, не новый STT/main/APLAY continuous qualification. Начальное baseline before **22718464B**, после finite cleanup **25720832→25763840B**; capture active/listening=true/retired=false, last_error/state_error=null.

Последняя отдельная read-only handoff сверка **06:20:24,994–06:20:26,345 MSK**: generation14 **28227584→28270592B (+43008B)**, actual robot `last_read_monotonic` **611836.965164996→611838.309067077**. Robot и Hub monotonic clocks не смешивались; timestamps не backdated/скорректированы. `goal.changed_at=03:20Z` в exact stage config — статическое scaffold metadata впереди начала run, **не measured authority/receipt freshness timestamp**; исходные bytes сохранены, temporal success из этого поля не выводился.

| Installed item | Реальный final pin / состояние |
| --- | --- |
| Agent / capture_pump / private config | `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b` / `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6` / `a6171f68e6fc20feebb48475991517f61412afc693f0c58f999f077f0eedd0d5` |
| Agent / factory |205817 /150625, active/running/NRestarts0; один arecord211737→205817, APLAY absent на final |
| Hub |78887/NRestarts0, config `7f11d114873cc20de66e4789166ed5bbbd32109f708f82991aeb5ab3217d3b5e`; installed hub/client hashes в removal receipt |
| PC existing fast |7736/start01:44:58.758UTC/exe/command exact frozen identity; один llama-server, slot idle |
| Fast GGUF / exe |`37ae482d336108d23516fa35e8e0c4126688d81018b87178a18d752a1357814f` / `0bbac3a55d4a005772ce8a16c4c222163f683119bbbca13b42f6af788faaa4e6` |
| S1 worker container |`c46d9afc583eabd612cebae22ea6609b188769f54eac842010d65ec4ce443fc9`, image0e42c38…, StartedAt03:05:06.916878049UTC, running/read-only/RestartCount0 |
| Effective S0 voice/config/recognition |`b4afda9d2ead77e405612badfea12f5fc8674f4c4e7fc480404f0334d774ddc7` / `9773283044a22b2abefdebb885f1711592e6a22facd22988c4847ee815b1c703` / `6211a01e8d4ecf515636d4407856fddcf6e5deec4ddbd5639ae977770111f15f` |
| Worker PID1 config |`/config/config.worker.local.json`, SHA `7aca57ff6fc0f93ffa821ff8d2686555c86aca6caaade7f9a8de37ffb06b274c`, **short opt-in=false**; source не откатывался к92cf |

PC during/final actual process/creation/exe snapshots совпали, включая существующий LM Studio24060/Electron children; нового main backend не появилось. Это process identity evidence, полного свежего9B weights/loaded-instance attestation R6 не заявляет. Worker final ok/idle. Normal Agent.turns4 без реплики в этом окне, speech0 по native session control path; акустического microphone meter для доказательства абсолютной окружающей тишины нет.

## Cleanup, ограничения и освобождение

Оригинальный session report **cleanup_verified=true**, все8 occupied flags=false, control listener thread/execution busy=false, compute_after same boot/native_agent/fast=false/main=false/quarantined=[]. Дополнительный independent gateway health idle подтвердился **до** gateway termination. Только после этого закрыты own Hub reverse/Mac PC forwards; SSH control exits0, child255 при штатном master exit сохранён и дополнен actual listeners absent. Token удалён, session124841/gateway124835 absent; Hub18097/18098/8791/18090/18772 absent, Mac18097/mux/own SSH absent. Export выполнен **до** удаления own Hub stage/archive; final removal проверил source hashes и известные jobs/compute receipts.

Read-only measurement corrections сохранены: первый Windows worker-pin probe имел argv quoting SyntaxError, его worker={} не принят; corrected stdin during/final подтвердили S1 pins. Прямой Mac→robot SSH timeout не менял runtime, read-only final check через pinned Hub ProxyJump прошёл. Первая stdin попытка через factory PTY не читала код и закончилась bounded30s subprocess timeout; исправленный quoted read-only source/process check прошёл. Final process audit не нашёл own lingering SSH. Ни один из этих probes не создавал capture/Agent/effect owner.

**Принято:** real recovered observation/tick loop, ≥10 silent IDs (23), reject old fast after gap, fresh next binding accepted, same-generation PCM deltas, finite duration и cleanup/handoff. **Не принято:** sustained full acceptance (`accepted=false`), physical admission/recovery, camera/stock/full multimodal loop, новых STOP/source-generation live interleavings, LAN300ms SLA, reboot/power-loss persistence. R5 terminal/physical policy не ослаблялась; repeated full loops не запускались.

**Normal listening ON, motor OFF, owners absent, Hub free/stock selected-known-unowned, worker healthy/idle. R6 больше не удерживает стенд и явно освобождает аппаратное/инженерное владение.**

Evidence: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a147da-18bb-7631-b833-c814732a30f0/R6-evidence/`. Полные47-file manifest/source archive, exact effective imports/final hashes, local+Hub tests (первоначальный missing fixture log отдельно), original session report/decision IDs, native per-leg/poll/transition/ledger journals, health/fast transport metadata, same-generation timestamps, installed PC/robot/Hub and cleanup receipts, `analysis.json`/`analyze.py`, `measurement-notes.json`, `SHA256.json`. Private config bytes/tokens/credentials/raw transcript/audio/video отсутствуют.
