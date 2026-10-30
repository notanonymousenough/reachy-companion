# S3 — exact S2 установлен; один seed → два полных normal replies

17 октября 2026, Europe/Moscow. **PASS для короткой формы и конечного normal диалога: один seed, два последовательных external STT→LLM→полных reply playback, без rejection/rewrite/повторного seed.** Seed/replies имеют один canonical `Алиса, `, одно законченное предложение, **6/9/7 слов** и один validated segment. **Фактическая PCM duration≤5s UNKNOWN:** включённого reply frame meter нет; process span/word count/manual call span не выдаются за акустическую длительность. Полный критерий, включающий≤5s, остаётся частично UNKNOWN.

**Финал06:49:40–06:49:48 MSK:** S2 effective voice`cfd55a2e…`, config module`97732830…`, **opt-in=true**, normal listening/capture **ON mic245/source_generation18**, bytes428032→473088 (+45056B), errors=null/interruptions0/turns6. Motor policy124=false, quiet/privacy=false, owners absent; Hub free/known/unowned, worker healthy/idle. A1 сохранён. **S3 закончен и явно освобождает аппаратное/инженерное владение Reachy/Hub/PC.**

## Установка и pins

Входы: [S2](S2-alice-format.md), [S1](S1-alice-short-live.md), [baseline](runtime-baseline.md), [PROJECT](PROJECT.md), явное освобождение [R6](R6-observer-native-live.md). Новых чатов/подагентов не создавалось; autonomous sources/R5/R6 runtime/services не менялись и не запускались. Frozen builder воспроизвёл exact S2; **24/24 offline tests PASS** (`PYTHONPATH=src:tests python3 -m unittest test_alice_short_replies test_alice_format -v`). Actual inference и playback ниже отделены от fixtures.

| Item | Реально установлено / сохранено |
| --- | --- |
| Existing container | `reachy-alice-two-ro-e589fef15c1d4f85baa7cf48244fdb5d`, ID`c46d9afc583eabd612cebae22ea6609b188769f54eac842010d65ec4ce443fc9` |
| Image | `sha256:0e42c38ae2b0b91873ba3cda454edf2cc3646ed4016a038a3dd12f3214120e3d`; read-only rootfs/binds preserved |
| Effective voice | `/usr/local/lib/python3.13/site-packages/reachy_companion/voice.py`: preimage`b4afda9d2ead77e405612badfea12f5fc8674f4c4e7fc480404f0334d774ddc7` → **`cfd55a2e930869a6d82b77325fab913d18dae2f42a888ca1e670775edf532681`** |
| Config / recognition modules | site-packages/config.py **`9773283044a22b2abefdebb885f1711592e6a22facd22988c4847ee815b1c703`** / recognition.py`6211a01e8d4ecf515636d4407856fddcf6e5deec4ddbd5639ae977770111f15f`, unchanged |
| PID1 config | `--config /config/config.worker.local.json worker serve`; private preimage`7aca57ff6fc0f93ffa821ff8d2686555c86aca6caaade7f9a8de37ffb06b274c` → **`b864d375b128c49dfa6aacc9caa52ef34c0dd7d5f2a4a32f2d7bcdd4193676e7`** |
| Единственный semantic config diff | `conversation.alice_short_replies`: absent→true; private old/current JSON сравнены на PC, bytes не экспортировались |
| Worker generations | prior03:05:06.916878049UTC → defaultfalse **03:45:30.617541661UTC** → active/final **03:46:22.91163366UTC** |
| Source/config ACL | Voice/private config/config module SDDL совпадают с exact backup; `/app/src` overlays из другого host directory сохранены |
| Models/backend | Прежние lm_studio/streaming=true, local faster_whisper `models/whisper-small`, Piper Ruslan; selector/voice/weights не менялись |

Только два controlled stop/start перехода **того же** контейнера: voice install при false и config opt-in. `RestartCount=0` означает отсутствие automatic restart, не отсутствие этих explicit transitions. CREATE/replacement/второй worker/Docker Desktop/Agent/factory restart отсутствуют. Defaultfalse readiness проверена **после** фактического S2 import/hash и **до** opt-in; active imports/flag/readiness проверены повторно. К HEAD/92cf не переходили, source rollback не требовался. Technical deployment fix и второй live run не понадобились.

Initial S3 до refusal: штатный guarded OFF239→240, exact backup/private config/ACL на PC, затем отдельный ON240→241. При возобновлении проверены свежие mic241/source15/free/idle/owners и exact preimage/backup/ACL/generation, затем OFF241→242/paused/no capture. Ни один исторический CAS payload не повторялся. Backup остаётся в закрытом `C:\Users\User\reachy-shadow\S3-format-01a147e8\`: `voice.preimage.py`, `config.worker.preimage.json`, `private-backup-meta.json`; ACL User/SYSTEM/Administrators по SID. Соседний `/config/config.local.json` PID1 не использует и S3 не менял.

## Reviewer decisions и минимальный transfer

Первый child scope остановился **до исполнения** двух SCP/deployment попыток: reviewer не принял прочитанную через tools исходную human authorization как trusted user content. Прочитанный original user record00:10:43.924UTC/parent`01a14730-3182-71a0-a4d4-fccb2c7b4b16` и оба отказа сохранены в исходном evidence; тогда стенд был возвращён ON. Этот первоначальный blocker не скрыт (`pre-resume-report.md`).

Возобновление пришло после **одобренного root SCP exit0, chunk90337e**, рассмотренного в parent с прямым human context. Root передал только `S2-voice.py`35378B/hash`cfd55a2e…` и `S2-transfer-manifest.json`191B/hash`e83ac93a1ca379745b140cdad251c5a87ff101b265c3b532135729d516d285ac`. Child **не повторял SCP**: независимо проверил remote hashes/size/closed ACL. README/credentials/private config/tokens/logs/media не переносились. Fresh SSH hostnames reachy-hub/DESKTOP-OMHR8MT и local deployment destinations подтвердили пользовательские Hub192.168.2.181/PC192.168.2.134. Exact existing bind install и activation отдельно получили approval и завершились.

Первую live-команду reviewer также отклонил **до исполнения**, трактуя её как отправку microphone audio во внешний STT/LLM. Новая read-only проверка actual effective routes доказала: local faster_whisper внутри existing PC worker, LM Studio`http://host.docker.internal:1234/v1` на том же PC; только пользовательская LAN Reachy→Hub→PC→Reachy. «External» здесь означает внешний speaker/колонку. **Тот же live script** повторно предъявлен с новым evidence, review одобрена, выполнено ровно одно окно. Другого transport/indirect execution/source workaround не было. Новая human confirmation не запрашивалась; нерешённого reviewer blocker теперь нет.

## Единственное live окно06:47:33.396–06:47:59.537 MSK

Штатный normal Agent и прежние routes/session, без нового recorder/ASR/harness/voice owner. Read-only observer S1 исправлен: helper реально **локальный Mac** `/Users/notanonenough/reachy-companion/scripts/factory_ssh.py`, existing Hub ProxyJump и public host pin из Hub known_hosts. До effects19 актуальных proc samples подтвердили работоспособность; actual finite85s observer завершился returncode0 и сохранил **780 samples**, включая Agent-qualified arecord/APLAY с PID/PPID/start_ticks/cgroup/monotonic/UTC. Factory process не выдавался за Agent playback.

| Фраза / normal input | Фактические receipts |
| --- | --- |
| Seed **«Алиса, сколько будет два плюс два?»** — **6 слов** | Один manual `/robot/say`; started03:47:37.172UTC, `/stream/say`20003:47:38.032, endpoint ok=true03:47:40.939. Один segment; call span3.767s **не PCM duration** |
| Reply1 **«Алиса, что ты имеешь в виду под цифрой четыре?»** — **9 слов** | External STT metadata7chars/1word, `/transcribe`20003:47:44.437 → `/stream/text`20003:47:45.175; decision=answer, один segment, reply body совпадает с exact validator. Agent.turns4→5, matching transcript SHA и listening03:47:48.472 |
| Reply2 **«Алиса, а почему ты считаешь именно так?»** — **7 слов** | Новый external STT metadata34chars/9words, `/transcribe`20003:47:54.591 → `/stream/text`20003:47:55.109; decision=answer, один segment. Agent.turns5→6/matching SHA03:47:58.785; следующий listening/idle03:47:59.038 |
| Bounded STOP | ON242→243, затем после двух completed turns STOP243→24403:47:59.393; worker idle, errors=null, interruptions0; второго seed/третьего normal test turn нет |

Все три **полные** spoken strings повторно прошли exact S2 `validate_alice_phrase`, без ручного обрезания/замены слов. Один canonical prefix,≤11 слов, одно законченное предложение, segment_count1. Accepted worker path даёт **один TTS dispatch на фразу** и **одну main answer generation на normal turn/retries0**; это code-derived по exact effective modules, отдельного live dispatch/total inference counter нет. Piper chunks не считаются новыми dispatches. Raw model style fragments не экспонированы; actual multi-style canonicalization на этом окне отдельно не доказана, её contract покрыт offline tests. Ack отключён short-mode path; rewrite/fallback speech не было.

Role-qualified APLAY: все PPID205817/cgroup`reachy-voice-agent.service`, sink`plug:reachymini_audio_sink`, raw S16_LE/16000/mono:

| Роль / PID | First…last observed UTC | First absent UTC / completion correlation |
| --- | --- | --- |
| Seed **215252** |03:47:38.187…40.448,21samples |03:47:40.550; manual endpoint ok40.939 |
| Reply1 **215281** |03:47:45.293…47.651,23samples |03:47:47.757; Agent turns5/listening48.472 |
| Reply2 **215319** |03:47:55.106…57.840,25samples |03:47:57.956; Agent turns6→listening59.038 |

Full playback completion опирается совместно на role-qualified process lifecycle и успешный Agent completion после штатного `process.wait`/returncode check, без interruption/error. Само исчезновение PID не считается достаточным. Логи HTTP не выдаются за playback. Акустическая идентичность внешнего speaker отдельным классификатором не измерялась; сценарий использовал соседнюю Алису, без человека, injected transcripts/fixtures/recordings отсутствуют. Raw external transcript/PCM не сохранялись, только metadata/SHA.

## PCM, A1 и отдельные verdicts

ON дал generation16/arecord215182; manual seed штатно retired эту generation, затем normal chain использовал **одну generation17/arecord215265**. Непрерывность через manual seed не заявляется. Generation17 status samples8.134…25.648s: **2048→565248B (+563200B)**, gap/overflow0. Один и тот же Agent arecord наблюдался03:47:41.291…59.379UTC через оба STT/main/APLAY, без replacement между replies; фактический `/proc` wchar0→574336. Это не единственный audio reader всей factory-системы и не acoustic sample-clock proof. STOP финализировал573440B/286720frames, suppressed_frames110400, retired=true; own-output suppression/A1 counters не ломались.

| Критерий | Verdict |
| --- | --- |
| Exact S2 install / defaultfalse readiness / opt-in | **PASS**, effective imports/hash/config/generation/ACL подтверждены |
| Seed +2 consecutive normal STT→LLM→full reply playback | **PASS**, один seed, два200/answer/Agent completion, три role-qualified APLAY |
| Canonical prefix / sentence /≤11 слов / full aggregate | **PASS**,6/9/7 слов, exact validator; ручного сокращения нет |
| Один validated segment / TTS dispatch / main answer retry0 | **PASS**, segment receipts; dispatch/generation count code-derived, не отдельный live counter |
| Actual reply PCM duration≤5.0s / acoustic limit | **UNKNOWN**: reply meter не включён/не доступен в receipts; capture read_frames не reply frames, proc rchar/spans и call span не PCM meter |
| A1 preservation / short same-generation progression | **PASS**, unchanged source/config/PIDs и live deltas; новая90s/full-system continuous qualification не заявляется |
| Cleanup / normal listening handoff | **PASS**, opt-in=true с knownhealthy listening, motor OFF, idle/free/owners absent |

Exact A1 hashes: Agent`de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b`, pump`5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6`, private robot config`a6171f68e6fc20feebb48475991517f61412afc693f0c58f999f077f0eedd0d5`. Agent205817/boot`f2a66c3b-dc89-4a2f-961d-ab738696b950`, factory150625, active/running/NRestarts0; Hub78887/NRestarts0/config`7f11d114873cc20de66e4789166ed5bbbd32109f708f82991aeb5ab3217d3b5e`. 9B/Whisper/Piper weights и Docker Desktop не менялись/не перезапускались; обычный worker startup не называется отсутствием model initialization, fresh loaded-weight attestation S3 не выполнял.

## Cleanup и final handoff

После bounded STOP выполнен **отдельный fresh normal ON244→245**. Final read-only samples06:49:40.569/41.965MSK: generation18,428032→473088B/frames214016→236544/read_calls209→231, robot monotonic613592.703505769→613594.111450562, gaps/overflow/superseded0/retired=false; turns6/interruptions0/errors=null. Final proc06:49:46–48: один Agent arecord215381→205817, APLAY absent. Policy124 motor=false/quiet=false/privacy=false/owners absent; Hub free/action=false/stock known/unowned, worker ok/idle.

Own staged S2 voice+manifest удалены **после hash/generation/ACL guard**; exact backup/private config/SDDL retained. Source/config/module ACL equality=true, required config module unchanged, enabled config hash и семантический diff подтверждены. SSH/helper/85s observer завершены; persistent transports/listeners/grants/remote stage не создавались. Opt-in остаётся true только после принятой короткой формы/полных replies и knownhealthy normal listening. Следующий restart/recovery требует fresh authority/generation, текущие epochs не готовые CAS payload. **Аппаратное владение освобождено.**

Evidence root: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a147e8-2cb2-7391-a38f-37a37f3dd68f/S3-evidence/`; прежняя preparation/refusal сохранена отдельно, финальные actual receipts в **`resumed/`**.40 payload files: `live-report.json`, `process-observations.json`, `live-analysis.json`/`analyze_live.py`, source observer/operations, reviewer-resolution/routes, staged hash/ACL, install/activation/defaultfalse/active/final imports, filtered HTTP, semantic config compare/cleanup/final Agent/robot/Hub. `resumed/SHA256.json` SHA **`e5082f29fa76ed10cfc7039f6c5edeeaa95e6e16df922f84c6ea64588dd175db`**. Private config bytes/tokens/credentials/raw external transcript/audio/video отсутствуют.
