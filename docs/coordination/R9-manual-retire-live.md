# R9 — exact R8 Agent installed / finite live acceptance

17 октября 2026, Europe/Moscow. **PASS: exact Agent-only install, один legacy manual seed, один normal voice turn, continuous PCM после manual и штатный STOP/reap.** R8 оставлен установленным; normal listening **ON**, S2 short replies **ON**. **Live concurrent ABA proof UNKNOWN**, source/barrier proof отдельно **PASS**. R9 завершён и явно освобождает аппаратное/инженерное владение Reachy/Hub/PC.

Входы: [R8 exact patch/source proof](R8-manual-retire-fix.md), [S3 handoff](S3-alice-format-live.md), [baseline](runtime-baseline.md), [PROJECT](PROJECT.md). S3 явно освободила стенд; её принятый seed+два ответа6/9/7слов и opt-in=true сохранены как предыдущий результат. На hardware работал только R9, без чатов/подагентов. Scope — одна установка и одно functional window; technical fix/retry/повторного seed не было.

## Установка и effective pins

Свежий preflight: старые Agent205817/boot`f2a66c3b-dc89-4a2f-961d-ab738696b950`, mic245/PCM generation18, normal listening/capture ON, один arecord215381, policy124 motor=false/quiet=false/privacy=false, оба owner=null; Hub free/stock known-unowned/action=false; worker ok/idle. PC actual routes повторно проверены: local faster_whisper и LM Studio`host.docker.internal:1234`, без внешнего STT/LLM сервиса.

| Компонент | Effective SHA256 / состояние |
| --- | --- |
| Agent preimage → установленный R8 | `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b` → **`001be4ec456141b41d0146b49d06e737ced5383dcba2201c288fa3ed35b667f6`** |
| Перенесённый exact patch | `f42426d28c94b592ab6213b85d89450b03c810215b61c290e964d823932c8c0e` |
| Pump, сохранён | `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6` |
| Reachy private config, сохранён | `a6171f68e6fc20feebb48475991517f61412afc693f0c58f999f077f0eedd0d5` |
| Effective PC voice S2 | `cfd55a2e930869a6d82b77325fab913d18dae2f42a888ca1e670775edf532681` |
| Effective PC config module | `9773283044a22b2abefdebb885f1711592e6a22facd22988c4847ee815b1c703` |
| Effective PC recognition | `6211a01e8d4ecf515636d4407856fddcf6e5deec4ddbd5639ae977770111f15f` |
| PID1 `/config/config.worker.local.json` | `b864d375b128c49dfa6aacc9caa52ef34c0dd7d5f2a4a32f2d7bcdd4193676e7`, alice_short_replies=true |
| Hub private config | `7f11d114873cc20de66e4789166ed5bbbd32109f708f82991aeb5ab3217d3b5e` |

До и после установки проверены реально разрешаемые импорты в Reachy venv из `/home/pollen/reachy-companion/src/reachy_companion/`: Agent/pump и все A0 required_unchanged pins: barge_in`28831114…`, microphone`d35ef6d3…`, motion_policy`d224385e…`, config`c0b0e7a8…`, sound_monitor`89e7f782…`, spoken_vision`486cfb8f…`; также snapshot_vision`d43a70cc…`. Полные hashes в `dependencies.json`; до установки они совпали с A0 manifest. Диагностический первый subprocess потерял PYTHONPATH при sudo; read-only probe исправлен через `sudo … env PYTHONPATH=…`, это не runtime fix.

Существующий builder восстановил exact A1 и R8. **130/130 offline tests PASS**, 7,294s, failures/errors/skips0: manual_retire_fix, continuous_capture, native_agent_session, capture_pump, bound_listening, agent_stream_timing. Новых dependencies не устанавливалось.

Reachy protected rollback создан до OFF: `/var/tmp/reachy-R9-rollback-01a14803/` root0700; Agent/config preimages root0600 с сохранёнными исходными metadata в private manifest. Persisted ON state не копировался/не восстанавливался. Через existing Hub ProxyJump/factory transport перенесены только patch1602B и manifest911B, без README/credentials/privateconfig/tokens/media. Stage `/var/tmp/reachy-R8-reviewed/` сохранён root0755, patch/manifest root0644; exact hashes перепроверены. Auto-review все escalated действия одобрил; unresolved reviewer blocker отсутствует.

Guarded OFF245→246, fresh paused/no capture/worker idle и18process samples без arecord/APLAY; затем controlled stop только `reachy-voice-agent.service`. Exact R8 command проверила inactive, Agent/patch/pump hashes, применила patch без fuzz, проверила output hash и compile; controlled start07:01:11MSK. Agent права664/uid1000/gid1000 сохранены. **Новый boot`eea946cc-b050-40e5-b5c5-a91e578439aa`, Agent216026/NRestarts0**; OFF246/paused/no capture и20process samples без PCM children подтверждены до ON. Factory150625, Hub78887/NRestarts0 и worker не перезапускались.

## Одно functional window — 07:01:48–07:02:04 MSK

Fresh guarded ON246→247. Через3s выполнен ровно один normal legacy `/robot/say`→Agent`/say` seed: **«Алиса, сколько будет два плюс два?»**,6слов. Manual ok; затем ровно один обычный external-speaker capture→STT→LLM→полный playback ход: **«Алиса, почему повторяешь только число вместо объяснения?»**,7слов. Оба полных spoken strings прошли exact S2 validator: один canonical prefix, одно полное предложение, один segment,≤11слов. Agent.turns0→1, interruptions0/last_error=null, status errors0, rejection/reseed/rewrite/retry отсутствуют. Соответствие transcript проверено SHA, raw external transcript/audio не сохранены.

В bounded worker log: `/stream/say`200, `/transcribe`200, `/stream/text`200, по одному. Agent-qualified APLAY216194(seed) и216221(normal reply), оба child216026; первый absent до manual ok, второй absent до Agent completion/listening. Proc spans2,543/3,059s и manual call4,321s **не PCM duration**; full reply acoustic≤5s остаётся UNKNOWN. Суммарный live model-inference counter отсутствует; dispatch/retry0 следует из exact code/отсутствия повторного API dispatch, не из нового inference meter.

| Граница | Реальное evidence / вердикт |
| --- | --- |
| Manual retire | Generation1 retired=true наблюдалась на elapsed4,521s,112640B; затем114688B и стабильна через speaking. Старый arecord216145 исчез до replacement216206. **PASS retire/reap**. Возможен поздний read уже начатого permitted(), как разрешено R8 proof; «нулевые поздние bytes» не заявляются. |
| Manual restoration/new generation | После manual ok generation2, другой child216206, listening восстановлен; generation1→2. **PASS**. |
| Один Agent capture child | **583** read-only process samples, максимум1 Agent arecord одновременно; PID/PPID/start_ticks/cgroup сохранены. **PASS для Agent**; factory audio fds/единственный reader всей системы не утверждаются. |
| Normal continuous capture после manual | Generation2 одна через STT/main/APLAY:0→241664B в functional samples, processing92160→114688B, speaking124928→233472B; gaps0/overflow0/superseded0. Child216206 один. **PASS finite continuous progression**, непрерывность через manual и90s sustained не заявляются. |
| STOP247→248 | Guarded OFF после завершённого normal turn; paused/listening=false/capture=false, generation2 retired=true,251904B.10поздних snapshots одинаковы,19process samples без arecord/APLAY. **PASS child reap / stable counters**; STOP во время busy-STT не проверялся. |
| Concurrent ABA / bound manual | Подходящий resume/status interleaving на hardware не наблюдался и не инъецировался. **Live UNKNOWN; source/barrier proof PASS** по exact R8/130tests. Hardware bound manual/pause internals отдельно не заявляются. |

Observer был только read-only `/proc`/status, завершился returncode0; новый recorder/ASR/daemon/instrumentation/physicalrearm/nativeLLMloop/camera/motorgrant не создавались.

## Финал, rollback и передача

После STOP выполнен отдельный fresh guarded ON248→249. **07:02:49–07:02:56MSK:** boot`eea946cc…`, mic249, generation3, normal listening/capture ON,38912→83968B/frames19456→41984 за1,408robot-monotonic seconds; gaps0/overflow0/retired=false, turns1/interruptions0/errors=null. Один arecord216286→Agent216026, no APLAY; policy124 motor=false/quiet=false/privacy=false, owners absent, Hub free/stock known-unowned/action=false, worker ok/idle.

Final effective Agent/pump/config и PC worker hashes совпали с таблицей. Existing container`c46d9afc…`, image`0e42c38a…`, read-only binds, RestartCount0, StartedAt`2026-10-17T03:46:22.91163366Z` сохранены. Factory150625/Hub78887 прежние. PC/worker/Docker/models не перезапускались/не менялись; native R5 source/protocol и physical closure не менялись.

**Rollback не требовался.** Exact reverse patch из R8 остаётся применим: fresh guarded OFF+reap+controlled stop Agent, затем та же [R8 команда](R8-manual-retire-fix.md) с аргументом `rollback`, hash001be4…→de362b…/compile/controlled start. Только Agent; protected config preimage не восстанавливать автоматически, persisted ON backup отсутствует. После любого start нужен новый boot preflight и отдельный fresh ON. Дополнительный независимый Agent preimage сохранён на Reachy root0600. Rollback на live не выполнялся.

Evidence: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a14803-656b-7f91-8c7d-58e323ea7c32/R9-evidence/`, 42payload files, `SHA256.json` SHA`3e0275ed0a07dd6aef13180525910c05f46f7e715cda18d1fd2f6933ad41c074`: imports/permissions/backups, exact source manifest/install command+receipt, offline summary receipt, actual live/status/process observations, analysis, filtered HTTP, STOP/final receipts. Summary receipts явно помечены как summaries tool output, не full captured logs. Private config bytes/credential values/tokens/raw audio/video/external transcripts отсутствуют. SSH/helper/observer завершены; постоянных transports/listeners/claims/grants не создано. **R9 завершён, исправленный normal service слушает; аппаратное владение явно освобождено.** Текущие epochs — receipts, не готовые CAS payload.
