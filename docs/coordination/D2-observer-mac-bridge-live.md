# D2 — exact D0 observer через существующий Mac bridge

17 октября 2026, **07:56 MSK**. **Основной interval остановлен через333,154837s: Mac-bridge health sentinel вышел code1, dependency chain корректно закрыла session/gateway. ≥30min service acceptance FAIL; повторного arm после отказа нет.** Cleanup verified, независимый PC fast idle подтверждён; собственные units/stage/token/archive/SSH masters/listeners удалены. **Normal listening ON; D2 завершён и явно освобождает аппаратное/инженерное владение Reachy/Hub/PC.**

Входы: [D0](D0-observer-service.md), [D1](D1-observer-service-live.md), [R6](R6-observer-native-live.md), [baseline](runtime-baseline.md), [PROJECT](PROJECT.md). Direct Hub→PC не использован. Чаты/подагенты не создавались. Normal Agent оставался единственным владельцем capture/STT/main/reply. Это был промежуточный service path с зависимостью от работающего Mac; автономность без Mac, boot persistence и24×7 не заявляются.

## Exact frozen source, transfer и readiness

Stage `/home/deploy/reachy-shadow/observer-service` составлен из сохранённого D0 payload и hash-verified R6 archive `4a84b8c9d02a2bb78096cf75cbe168b1ecdf067e8e5276a6a4350cfb6103f425`, до возможных R13 source mutations. Live checkout не использовался как неизменная база. Production installed Hub не заменялся. Effective imports из stage, Python — существующий `/home/deploy/reachy-shadow/.venv/bin/python`. Все manifest hashes повторно проверялись перед каждым sample и непосредственно перед удалением stage.

| Effective module | Frozen SHA256 |
| --- | --- |
| autonomous.native_agent, D0 | `3cbde7e359d4848faf892b83364c957f9b087cd7537fae88c4e6df188c057c5c` |
| autonomous.native_agent_session, D0 | `6246ac84ff17ae354aefc98f37fde14190084632646afaa6b723d6f6e100a8ca` |
| client | `adc324fc93ec4dfc1d88249deaa4a7925e8d44e92dc15946877cef574fac1c4f` |
| autonomous.runtime | `feadc9588682490269a02533e9dfc7f68c11958b015efff00eef2e2c48b8f0f1` |
| autonomous.state | `6294b232587853d4aba026aeae8ebee1163fc06d88f63461210605f0ce3141` |
| autonomous.config | `3a1b09d4554946e954f5033a44e8e52ce94d319c588f3e27e9aad5712590c107` |
| autonomous.gateway | `8f75faaf4ec4636a800b1c170cf44220dbefbc6e4c4d0207e2a7744502379fbc` |

Secret-free transfer: **51 manifest entries + manifest.json,169755B compressed**, archive SHA `2fadd2187d55adb9a9d355cbaf06ed4d295ba897504b1945eca1ae48718e01f2`. Только source/tests/public config/assets/units/sentinel; без README/private config/credentials/tokens/media. Reviewer одобрил SCP и bridge, unresolved approval/egress отказа нет. Existing Hub private companion config читался только на Hub; новый локальный gateway token не экспортировался. 31 frozen native/service tests PASS9,917s на Hub; дополнительный D0 R10 test не входил в transfer closure. `systemd-analyze verify`:0, без diagnostics. Runtime source не патчился.

Первый config validation отказал до units/arm/session: timestamp имел `+00:00`, контракт требует `Z`; исправлен только новый goal.changed_at. Первый GET gateway до готовности listener получил ConnectionRefused; gateway не перезапускался, после готовности full health/preflight прошёл. Основной goal.changed_at=`2026-10-17T04:48:22.939426Z`, fresh arm=`04:48:23.766306Z`; никаких будущих timestamps.

## Transport, authorization и lifecycle

Только Mac127.0.0.1:18097→PC127.0.0.1:18097 и Hub127.0.0.1:18097→Mac127.0.0.1:18097. Existing pinned Mac→PC `User@192.168.2.134`, Mac→Hub `deploy@192.168.2.181`; BatchMode/StrictHostKeyChecking/ForwardAgent=no. Detached OpenSSH masters `-f -N -T`, собственные control sockets `/private/tmp/reachy-D2-work/{pc,hub}-mux`, PIDs **52850/52864**, пережили setup process. Keepalive10s/count2, ExitOnForwardFailure; нет autossh/auto reconnect. Hub reverse listener фактически принадлежал sshd-session134227. Оба master ещё существовали после sentinel failure, затем закрыты через собственные sockets.

Новые authorization grants, keys, authorized_keys/ACL/firewall/host trust, agent forwarding/key copy отсутствуют; Mac private keys не покидали Mac. Mac known_hosts bytes/hash/mtime неизменны, последний mtime9октября17:24:18UTC. Before/final PC hashes+mtime совпали: User authorized_keys и ProgramData administrators_authorized_keys SHA `10adf12e…`/112B, mtime7октября; sshd_config SHA `f6bbb077…`/2292B, mtime7октября. Читались только hashes/mtime, содержимое authorization/keys не экспортировалось. Subsequent short probes явно UpdateHostKeys=no; первоначальные bridge connections тоже не изменили known_hosts, что подтверждено before/final hash и старым mtime. D1 direct-path auth/pin dependency не provisioned.

Разрешённая local lifecycle замена: `reachy-observer-forward.service` запускала реальный health sentinel вместо недоступного direct Hub SSH. Type=notify; READY только после HTTP/status=ok от существующего fast через bridge; затем GET каждые0,2s, timeout0,4s; ошибка завершает sentinel без restart. Sentinel не создаёт listener/новый daemon framework и не выдаёт dummy active. Gateway BindsTo/After forward, session BindsTo/After gateway. Все units static/no Install/Restart=no; enable не выполнялся. Loopback-only listeners:18097 transport,18098 D0 gateway,8791 D0 session control; новых LAN listeners нет. Main/context/speech/motion/stock/workflows OFF; period3s/deadline6s/ledger256. Fresh full normal-listening/owners/privacy/freeHub/stock-known/worker+fast-idle/native300ms preflight прошёл перед обоими разрешёнными arms. Runtime health0,5s/BEGIN300ms/terminal guards неизменны.

## Начальный STOP и один основной interval

Один разрешённый initial controlled SIGTERM после known compute idle: session134895 **26,702855s**,9requested/5accepted/4discarded,5gaps/5recoveries/0,886011s unavailable. Reason=controller_stop/errors=[], cleanup_verified=true; все occupied=false, control listener=false/handlers0, same compute boot idle/quarantine=[]. Independent subsequent health idle PASS; normal listening ON. Original accepted=false сохранён. Initial evidence/consumed arm архивированы один раз до нового fresh preflight; UNKNOWN/busy/revoke не rearm.

Основной start **07:48:23MSK**, один session **PID135773**, gateway**134796**, sentinel**134773**, compute boot `8968362d-8c6b-457e-90ca-417c52feed9e`. Нет finite cap, session/model restart0. Service пересёк прежний180s предел. В **07:53:58MSK** sentinel process134773 вышел status1/exit-code; systemd начал ordered stop session, затем gateway. В07:53:59 оба deactivated successfully. **Это fail-closed dependency stop, не successful30min soak.**

| Метрика основного interval | Факт |
| --- | --- |
| Scheduler lifetime incl bounded cleanup | **333,154837s** |
| Fast requested | **105** |
| Reduced real responses | **104:67accepted +37discarded**; ещё1request был drained при stop, reducer outcome отдельно не записан |
| Invalidated / unavailable ticks | **38 /6**; invalidation не равна discard count |
| Native polls | **3055** |
| Gaps / recoveries / unavailable | **66 /66 /13,780551s** |
| Read failures / late receipts | **42 /15** |
| Effects | stock_used=false/stock=null/stock_unknown=false; main/speech/context/camera/motion/workflows disabled |
| Final lifecycle | reason=controller_stop, errors=[], cleanup_verified=true; native_withdrawn=null |
| Final quality | accepted=false, continuous_acceptance=false, live_acceptance=false |
| Control cleanup | all8occupied=false, listener thread=false/handlers0; same compute boot fast=false/main=false/quarantine=[] |

Конкретный blocker: **bridge-health sentinel runtime exit1 до30min**. Точная HTTP/socket exception class/status/latency не сохранена, потому что unit stderr=null; утверждать конкретный timeout или реальную потерю SSH нельзя. Journal подтверждает dependency stop ordering. После failure оба SSH master живы, independent Hub→bridge `/health`={status:ok}, `/slots` idle; PC7736 exact identity/weights/exe сохраняются. Это последующее восстановленное чтение, не доказательство здоровья в момент failure. Guards/таймауты не расширялись, transport не заменялся, новый arm не выдавался. Следующему scope сначала нужны bounded secret-free sentinel diagnostics для установления причины; новый auth grant из этих evidence не следует.

## PCM, bounded state и память

Main preflight→последний native receipt: **87523328→98240512B (+10717184B)**, source_generation3, gap_events0/overflow_events0. Первый counter — independent preflight непосредственно перед arm, не первый session poll. Agent boot/mic249/policy124/turns2/expression87 совпали в main receipts; normal Agent владел capture/reply весь interval. Это PCM read metadata, не acoustic/exposure proof и не новый voice stimulus/diалог.

Шесть finite soak snapshots40,06…305,29s: session RSS **35308…35780kB**, gateway33388…33420kB, sentinel21988kB. Это≈5,5min observed memory, долгосрочный bound30min не доказан. Snapshot sizes2463…9319B; after final bounded write metadata18437B, previous10032B, report24075B, consumed arm210B, modes0600. Нет append-only content log, PCM/transcripts/raw media не сохранялись. Metadata `.tmp` отсутствовал на audit.

Configured/effective ledger deque maxlen256; final report **67total accepted /58suffix IDs /9omitted** — это suffix event-ledger, не весь accepted-ID журнал. Все58 retained activities=`wait`. Gaps66 retained из66total, cap256, omitted0; gap eviction live не был достигнут. Original reports не изменялись. Source bounded deque/snapshot tests PASS;30min saturation/долгосрочная memory acceptance остаются OPEN.

## Cleanup, current state и handoff

Сначала exported/hash-verified secret-free evidence, original final cleanup+independent actual backend slot idle. Затем удалены только D2 три unit files, stage/token/transfer archive; собственный failed state сброшен, daemon-reload без reload/restart Agent/worker/models/factory. Все3units **LoadState=not-found/ActiveState=inactive/MainPID0**. Own masters закрыты Hub→PC порядком через exact sockets, exits0; PIDs52850/52864 и sockets отсутствуют, Hub/Mac18097/Hub18098/8791 absent. Local frozen source archive/evidence сохранены; production observer не оставлен ON из-за failure.

Независимый final read после cleanup≈**07:56:20MSK**: normal listening/capture **ON mic249/source3**, PCM**102772736→102817792B (+45056B)**, gaps0/overflow0/retired=false/turns2/last_error=null; owners absent, policy124 motor=false/quiet=false/privacy=false; Hub free/stock selected-known-unowned/action=false, worker ok/idle. Exact Agent216026/boot`eea946cc-b050-40e5-b5c5-a91e578439aa`, factory150625, arecord216286; NRestarts0. Hub78887/NRestarts0/config7f11…; R8 Agent001be4ec…/pump5fe20c69…/A1configa617… unchanged. S2 effective cfd55a2e…/config97732830…/recognition6211…/worker private b864d375…/opt-inTRUE, existing containerc46d…/image0e42…/StartedAt03:46:22.91163366UTC/RestartCount0 unchanged. PCfast7736 exact process/exe/weights/idle; existing9B LM Studio process identities unchanged, Whisper/Piper selection не менялась. Не выдаётся новое weights attestation для9B/Whisper/Piper.

Stop recipe для сохранённого source candidate: stop session SIGTERM → original report/all slots/independent same-boot gateway+backend idle → stop gateway+sentinel → own Hub/PC mux `-O exit`; UNKNOWN не rearm. Полный rollback уже выполнен: own units/stage/token/archive удалены. Штатный production STOP остаётся `scripts/companion voice microphone-off`, восстановление — отдельный fresh guarded `microphone-on`; D2 их не вызывала. Новое service испытание требует отдельного sole owner/full preflight/fresh arm. Старые epochs здесь — receipts, не новые CAS payload.

**D2 завершён с runtime transport-sentinel blocker; ≥30min acceptance и sustained acceptance FAIL. Production voice ON, observer OFF, инженерное/аппаратное владение явно освобождено.**

Evidence: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a1482d-07cc-7520-8160-2673b352e287/D2-evidence/`. Frozen/transfer manifests+exact payload archive, D0 manifest, scripts/source, effective imports/units/test logs, initial/main original reports, bounded soak snapshots/counts/RSS/PCM, systemd journal/failure audit, independent PC/robot pins/auth hashes, final listener/process/stage cleanup receipts, analysis.json, SHA256.json. Private keys/tokens/private config contents/raw media отсутствуют.
