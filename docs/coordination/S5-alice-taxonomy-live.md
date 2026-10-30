# S5 — exact S4 installed; one seed and three complete normal replies

17 октября 2026, финал **09:49:18 MSK**. **Install PASS; bounded normal Alice dialogue / short format PASS; actual rejection reason UNKNOWN (rejection не возник).** Единственное окно **09:47:09.654–09:47:49.085 MSK / 39.431103s**, один seed и ровно три полных normal replies. Нового run/seed/rearm после STOP нет. **PCM/acoustic≤5s UNKNOWN; ≥30min acceptance UNKNOWN, прежний D3 ≥30min FAIL не закрыт.** Исправная S4 оставлена installed.

**Явный handoff root: S5 завершена, эксклюзивное аппаратное владение Reachy/Hub/PC освобождено. Normal voice/listening/capture ON, durable motorOFF, observerOFF, owners absent, Hubfree/stockknown-unowned/workeridle.** PROJECT пишет root; здесь изменены только этот report, runtime-baseline и собственный S5-evidence. Чаты/подагенты не создавались.

## Exact install и сохранение стенда

Прочитаны PROJECT, S4, Q6, S3, D5, runtime-baseline и явный R16 handoff. Q6 44+4 probes/0findings принят без повторного source review/tests. Независимо проверены локальные S4 candidate/preimage/patch hashes по Q6. Исторический S4 protected PROJECT hash не использован как production dependency; PROJECT/manifest не менялись для обхода этого check.

| Item | Fresh before → installed/final |
| --- | --- |
| Effective `/usr/local/lib/python3.13/site-packages/reachy_companion/voice.py` | `cfd55a2e930869a6d82b77325fab913d18dae2f42a888ca1e670775edf532681` → **`4ec7cfe56f7ee5a4b37ac9906a2c467b70983a6437a7840c25416695a5dfd4fd`** |
| Required config module | `9773283044a22b2abefdebb885f1711592e6a22facd22988c4847ee815b1c703`, unchanged |
| Recognition | `6211a01e8d4ecf515636d4407856fddcf6e5deec4ddbd5639ae977770111f15f`, unchanged |
| PID1 config | `/config/config.worker.local.json`, **`b864d375b128c49dfa6aacc9caa52ef34c0dd7d5f2a4a32f2d7bcdd4193676e7`**, short opt-in=true, unchanged |
| Container / image | `c46d9afc583eabd612cebae22ea6609b188769f54eac842010d65ec4ce443fc9` / `sha256:0e42c38ae2b0b91873ba3cda454edf2cc3646ed4016a038a3dd12f3214120e3d`, same readonly rootfs |
| Worker generation | `2026-10-17T03:46:22.91163366Z` → **`2026-10-17T06:46:23.968192569Z`**, RestartCount0 |
| Preserved robot pair / pump | R15 Agent `1f4e52a6b54b6c12de2bd325e094625ebdf4e2e341df2fa5e2230a51ee660a19`, expression `4b2ea1039145da87a381b3da04ea64693842547d159e3afd65e393247c516e66`, A1 pump `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6`, unchanged |

Fresh process/model/idle/owners check совпала с R16: Agent240868/boot `1e697e8a-271c-4764-bb44-bc8b617d0d58`, factory150625, Hub78887/NRestarts0, PCfast7736/exe/weights/creation/command и existing LM Studio process identities сохранены. Robot config `a6171f68…`, Hub config `7f11d114…` unchanged. Main9B/Whisper/Piper settings/weights не менялись; обычный worker restart перезагрузил worker-owned recognizer/Piper, независимый новый hash всех main/STT/TTS weights не заявляется.

Exact backup/SDDL/launch-inspect (включая mount/env) сохранены **только на PC** в `C:\Users\User\reachy-shadow\S3-format-01a147e8\S5-taxonomy\`, с наследованием существующего protected parent ACL; ACL/auth/trust/firewall не менялись. Private config bytes не копировались/не экспортировались. Minimal SCP exit0: только candidate `voice.py` **37139B/SHA4ec7…** и secret-free `transfer-manifest.json` **342B/SHA856e5ef81865623fd75d9b26299a12c0517994aaa00ba5b28bb02bb26e40cf8a**. README/keys/tokens/config/log/media не переносились. Все automatic reviews approved; отказов/unresolved approvals нет.

Fresh guarded MicOFF255→256; paused/drained/no Agent arecord/APLAY, motor129OFF, Hubfree/workeridle/ownersabsent. После повторного fresh authority/hash/generation/backup check выполнен **один controlled stop/start того же worker контейнера**, изменён только host bind для effective site-packages voice, не `/app/src`. Source/config/module ACL equality и launch Config/env/HostConfig/sortedMounts equality подтверждены. Agent/factory/Hub/Desktop/fast/LM Studio не рестартовали; CREATE/replacement/новых listeners/keys/auth нет. Первый readiness GET во время загрузки получил RemoteDisconnected; последующий read-only GET подтвердил idle без дополнительного restart. Actual import/hash/config проверены после restart до live. Rollback не потребовался; [recovery recipe](/Users/notanonenough/reachy-companion/S5-evidence/recovery.md) сохранён.

## Единственная normal chain

Normal Agent→Hub router→existing PC worker→Agent playback; local faster_whisper/LM Studio/Piper, соседняя Яндекс Алиса, без человека. Один штатный guarded `/robot/say` seed **«Алиса, сколько будет два плюс два?»**, затем только normal external STT→LLM replies. Synthetic/raw model HTTP/fixtures/recorder/injected transcripts/rewrite/truncate/retry/forcing отсутствуют. Заранее задан лимит78s/3normal replies/первая ошибка; actual STOP после третьего completion,39.431103s.

| Role | Worker UTC / safe metadata | Agent full completion UTC |
| --- | --- | --- |
| Seed | `/stream/say`200 **06:47:14.161**;34chars/**6words**, one canonical prefix/segment | manual endpoint ok, **06:47:17.240** observed |
| Normal reply1 | `/transcribe`200 **21.383** → `/stream/text`200 **22.295**;19chars/**3words**, one canonical prefix/segment; external transcript metadata6chars/1word | turns0→1/listening/workeridle **06:47:25.243** |
| Normal reply2 | `/transcribe`200 **29.914** → `/stream/text`200 **30.596**;77chars/**10words**, one canonical prefix/segment; external metadata17chars/5words | turns1→2/listening/workeridle **06:47:36.234** |
| Normal reply3 | `/transcribe`200 **42.796** → `/stream/text`200 **43.360**;56chars/**10words**, one canonical prefix/segment; external metadata46chars/10words | turns2→3/listening/workeridle **06:47:48.616** |

All normal completions имеют transcript SHA match Agent↔worker, answer decision, last_error absent/interruptions0. Actual accepted S4 path гарантирует прежний whole-sentence/word/character validator/TTS boundary; retries/new model calls отсутствуют в exact production code. Отдельного live inference/TTS dispatch counter нет. Reply/input content не экспортировался, только metadata/hash; raw transcript/audio/video не сохранялись.

Read-only robot observer85s завершён exit0/**781samples**. Role-qualified APLAY PPID240868/cgroup `reachy-voice-agent.service`, plug:reachymini_audio_sink/S16_LE16000mono: seed**241875** first…last14.463…16.728/absent16.845UTC; reply1**241901**22.495…24.013/absent24.118; reply2**241933**30.869…34.940/absent35.046; reply3**241981**43.509…46.827/absent46.943. Каждый исчез до успешного manual/Agent completion после production wait/returncode check; process исчезновение само по себе не выдано за completion. **Процессные spans/rchar/wordcounts не PCM meter: ≤5s UNKNOWN**, stream_timing acoustic_verified=false/consumption_verified=false сохранены. Acoustic identity внешнего speaker отдельным классификатором не измерялась.

ON256→257 создал capture generation2/arecord241830, manual seed штатно retired её. Через три normal STT/LLM/APLAY шла **одна generation3/arecord241884**, observed2048→997376B/gaps0/overflow0; observer one reader PID через17.427…48.812UTC. Непрерывность через manual seed/STOP не заявляется; единственный reader всей factory-системы не доказан.

## Reason records, ограничения и cleanup

[Safe worker collector](/Users/notanonenough/reachy-companion/S5-evidence/collect-worker.py) отфильтровал existing `/config/data/compute.log*` на PC **до вывода** строго в live UTC window: **7records**, one say200+3transcribe200+3text200, omitted0/sizecapfalse. Разрешены только timestamp/role/source/route/status и fixed enum/headers_sent при наличии; arbitrary message/traceback/text/media отсутствуют. **Typed rejection/HTTP422/generic503 не возникли, поэтому actual predicate/reason=UNKNOWN.** Live 422 propagation/post-header branch этим окном не exercised, Q6 source proof остаётся отдельным; новый reason историческому D5 не приписывается. Cross-host exact request-ID correlation UNKNOWN. Known422→Agenterror/D0terminal и generic503 contracts не менялись; восстановления/ослабления validator не добавлено.

Bounded STOP257→258 **06:47:48.884UTC** → paused/no capture/workeridle, затем отдельный fresh normal ON258→259 после idle/free/unowned. Final**09:49:18MSK**: same Agent boot/PID240868/NRestarts0, mic**259ON/listening/capture/source4**, PCM**40960→2119680B**, gaps0/overflow0/retiredfalse, turns3/interruptions0/errornull; один arecord**242013→240868**, APLAY absent. Policy**129motorfalse/quietfalse/privacyfalse**, ownersnull, Hubfree/actionfalse/stockknown-unowned, workeridle/PCfastidle, observerunitsnot-found/nativeprocesses[]/Hubports18097/18098/8791 absent. Installed S4/config/imports/generation/ACL/launch/mount/env и R15/A1 pins повторно подтверждены.

Hash/generation guarded staging voice+manifest удалены после idle, fresh exact source/ACL/launch backup retained; собственный observer/SSH завершены. Persistent stage/service/token/bridge/listener/grants не создавались. **PASS install/short-format/seed+3complete normal chain/cleanup; UNKNOWN actual rejection predicate/422live/PCM≤5s/≥30min. Аппаратное владение явно освобождено root.**

Evidence: [S5-evidence](/Users/notanonenough/reachy-companion/S5-evidence/), `analysis.json`, `live-report.json`/source, `process-observations.json`/source, `worker-records.json`/source, exact transfer manifest, PC before/active/final/backup/install/launch/cleanup, robot before/paused/final, Hub/final state, recovery, `SHA256.json`. PROJECT/S4/Q6 frozen receipts не перезаписывались.
