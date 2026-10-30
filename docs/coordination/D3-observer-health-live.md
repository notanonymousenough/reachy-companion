# D3 — bounded bridge health; новый native terminal blocker

17 октября 2026, финал после **08:27 MSK**. **Один service interval430.958639s:136fast requests,84accepted/51discarded; ≥30min FAIL.** Session148115 завершилась `native_withdrawn=ValueError`, при production Agent `phase=error`/`last_error=HTTP Error503: Service Unavailable`. **Sentinel не останавливал session:** собственные sentinel/gateway/SSH identities сохранились, bounded health timeouts восстанавливались. Нового arm/restart/replay после terminal не было.

**Cleanup завершён после отдельного known-idle reconciliation. Normal listening/capture ON, motorOFF/owners absent/Hubfree/workeridle. D3 явно освобождает аппаратное/инженерное владение Reachy/Hub/PC. ObserverOFF; own units/stage/token/archive/bridge удалены.**

Входы: [D2](D2-observer-mac-bridge-live.md), [D0](D0-observer-service.md), [baseline](runtime-baseline.md), [PROJECT](PROJECT.md). Подагенты/чаты не создавались. R13/current native checkout не использовался; Agent/worker/models/factory/native D0 runtime/SSH auth/trust не менялись. Это route с зависимостью от работающего Mac; standalone/boot24×7 не заявляется.

## Диагностика и точечный sentinel fix

Историческая D2 actual HTTP/socket exception остаётся UNKNOWN: stderr=null не позволяет восстановить её. Утверждений «SSH упал»/«модель зависла» нет. Начальный D3 bounded diagnostic через тот же existing-auth bridge:250 GET `/health`, timeout0.4s/poll0.2s,55.984265s,250ok/0failures; reverse sshd-session146479/inode975372 до/после один. Ошибка не воспроизвелась в этом diagnostic. Collector сохраняет failure class/cause class/status/latency/UTC/elapsed и suffix16, без messages/body; failures0 означает отсутствие failure receipts, а per-success latency тогда не записывалась. Один `/props`:9742B/hash239d8d20…, только size/hash/keys retained. Own diagnostic masters56879/56882 были сняты после idle до первоначального handoff.

Исправлены только `deploy/autonomous/mac_bridge_sentinel.py`, конкретный existing-Mac unit variant `deploy/autonomous/bridge/reachy-observer-forward.service`, targeted `tests/test_mac_bridge_sentinel.py`. Exact diff к D2 — `D3-evidence/sentinel.patch`.

- READY только после fresh `{status:ok}` и заранее pinned Hub boot+reverse socket inode. Owner пишет pin до запуска; recovery не выбирает новый listener.
- Единичный HTTP/socket read failure → `HEALTH_UNAVAILABLE`, не доказательство SSH loss. Прежние read timeout0.4s/poll0.2s; unavailable budget3s, checked на completed read. Один bounded read/poll и scheduling могут добавить задержку к3s; hard3.000s wall-clock guarantee не заявляется.
- Fresh health до budget и same listener разрешает recovery. Late success после budget не возобновляет lifecycle. Missing pinned listener→`LinkLost`, changed boot/inode→`IdentityMismatch`, terminal; permanent HTTP unavailable→`health_unavailable_budget`, terminal без выдуманной transport cause.
- Atomic metadata0600/≤16384B, recent16, scalar last_failure, total counters/duration/max latency/UTC/elapsed; periodic5s+transitions, один temporary. Exception messages/body не сохраняются. stderr=journal вместо null. Restart=no/no enable/no reconnect/rearm/model session; прежняя BindsTo chain сохранена.

Pin — **kernel Hub reverse socket**, не PC model instance ID. Rawfast health содержит только status; замена PC backend теми же props за тем же listener не различается этим API. Поэтому independent PC process/exe/weights pins обязательны. Недоступный backend при живом listener ограничен unavailable budget; прежние D0 compute-health/boot/slots/300ms/effect/terminal guards неизменны. Новый identity daemon/supervisor framework не добавлен.

## Review resolution, frozen pins, установка и arm

Первый SCP172719B/SHA70d8b271… отклонён automatic review как internal source egress на Hub, доверие/authorization которого не принято из delegated context. Обхода/повторного transfer в D3 не было; original rejected bytes сохранены. Root затем предъявил **тот же SCP transport/destination** с прямым trusted human-контекстом: approved, выполнен root chunkd68d4a/exit0. Final archive после offline завершения counters/tests: **172946B/SHA`8e2a0d1d19210d215d15ca306afedfb223889dc27ca01bc3627d3eea022d9126`**,52manifest entries+manifest; без README/private config/credentials/tokens/keys/media. D3 не повторяла SCP, независимо сверила remote size/hash и отсутствие старого stage/units/listeners. **Unresolved reviewer approval нет.**

Frozen source из D2 archive SHA`2fadd2187d55adb9a9d355cbaf06ed4d295ba897504b1945eca1ae48718e01f2`; все entries проверены до sentinel edits. Effective imports из `/home/deploy/reachy-shadow/observer-service/src`, существующий `/home/deploy/reachy-shadow/.venv/bin/python`. Native/D0/shared dependencies не менялись:

| Effective source | SHA256 |
| --- | --- |
| native_agent.py | `3cbde7e359d4848faf892b83364c957f9b087cd7537fae88c4e6df188c057c5c` |
| native_agent_session.py | `6246ac84ff17ae354aefc98f37fde14190084632646afaa6b723d6f6e100a8ca` |
| client.py | `adc324fc93ec4dfc1d88249deaa4a7925e8d44e92dc15946877cef574fac1c4f` |
| autonomous.runtime | `feadc9588682490269a02533e9dfc7f68c11958b015efff00eef2e2c48b8f0f1` |
| autonomous.state | `6294b232587853d4aba026aeae8ebee1163fc06d88f63461210605f0ce3141` |
| autonomous.config | `3a1b09d4554946e954f5033a44e8e52ce94d319c588f3e27e9aad5712590c107` |
| autonomous.gateway | `8f75faaf4ec4636a800b1c170cf44220dbefbc6e4c4d0207e2a7744502379fbc` |
| D3 sentinel | `b3d34577f208e772efee4842327e2bb8de8a8bf12496ae65739b1a3e663eeb6d` |
| D3 bridge unit | `105af9e96629dbacdcbf9f1b4571e66d1f630ef1463d88c028e9de198da7552e` |
| D3 sentinel tests | `cafd7fb0febb1f6050c2ce918df4e56896814ab8c35ec09a8b01ac7c5bb8f4f3` |

**41/41 offline PASS:** local existing validation venv3.105s; Hub actual9.821s. Frozen native/service31 + sentinel10: transient read→fresh same identity; dead reverse listener; replacement/during-response identity change; permanent unavailable bounded shutdown; late success denied; kernel listener parser fixtures;2000-step counters/suffix/write bound;0600 atomic cleanup/no tmp; sanitized URLError; HTTP failure not LinkLost. Это controlled offline traces, не live tunnel-kill proof. Initial default system Python lacked jsonschema, preserved separately; dependency install не выполнялся. Linux `systemd-analyze verify` exit0/no diagnostics. All3units static/Restart=no, no enable.

Fresh preflight: owners absent, normal microphone/listening/capture ON, privacy/quiet clear, motorOFF, Hubfree/actionidle/selected-known-unowned stock, workeridle, gatewayfast/mainidle/quarantine[], rawfastslotsidle, native300ms read. PCM same source3 **140380160→141725696B** between install baseline/preflight. Goal changed_at actual preparation time, no future timestamp. Single arm **05:16:38.077482UTC/08:16:38MSK**, controller`D3-mac-bridge`, source Agent boot`eea946cc-b050-40e5-b5c5-a91e578439aa`, mic249/policy124. Arm consumed once. period3s/deadline6s/ledger256; effects/main/context/camera/speech/motion/stock/workflowsOFF.

Live own Mac masters **60319PC/60323Hub**, sockets `/private/tmp/reachy-D3-work/{pc,hub}-mux`, pinned existing auth/StrictHostKeyChecking/UpdateHostKeys=no/BatchMode/ForwardAgent=no/keepalive10s/count2; only Mac127.0.0.1:18097→PC127.0.0.1:18097 and reverse Hub127.0.0.1:18097. No reconnect. Hub boot`27d5c08c-9b13-4f4b-b1ac-342f6972e8f9`, reverse inode**982465**. Units **sentinel148044/gateway148046/session148115**, gateway compute boot`e316fd6f-ba1f-487d-b5b3-3bbe4f1ff68e`; source/import/own identities checked each finite sample.

## Реальный interval и точный предел диагностики terminal

Session стартовала08:16:38MSK, systemd exit1 **08:23:51MSK**, original report lifetime incl bounded cleanup **430.958639177s**. В08:23:02 sample session ещё ACTIVE/380.296849s/76accepted. Следующий snapshot увидел sessionPID0/failed, **sentinel/gateway по-прежнему active**; collector остановился без mutation/rearm. Runtime reason=`native_withdrawn`, `native_withdrawn=ValueError`, errors=[]; compute authority не менялась.

Последний accepted native receipt: Agent phase`processing`, turns4/expression90/source3/PCM155541504. Первый postexit independent snapshot08:23:54.826UTC+3: Agent **phase`error`**, listening/capturetrue/mic249/source3, expression91, **last_error=`HTTP Error503: Service Unavailable`**. Frozen `NativeAgent.check_operator` явно отзывает admission при phase`error`; `_read` не разрешает error phase и сохраняет terminal revoke. Source/boot/epochs/owners/counters в subsequent receipt не изменились/не регрессировали. Это **наблюдённая terminal error phase и source guard, согласующийся с ValueError withdrawal**.

**Сам exception message/failed poll projection runtime не сохранил: report схлопывает non-transient exception до class. Поэтому точная строка/шаг отказавшего read UNKNOWN.** Нельзя выдавать последующий snapshot за сохранённый failed poll. HTTP503 доказан только как Agent.last_error в postexit snapshot; **его producer/endpoint, STT vs LLM vs streaming/Hub/worker stage и backend cause UNKNOWN**. Bounded on-robot journal filter08:23:30..08:24:20 вернул0 matching rows, дополнительного trace нет. Это не доказательство падения PC fast/SSH/модели. Нового diagnostic model request/voice stimulus/Agent restart не выполнялось.

Agent позже сам вернулся в ordinary listening/last_errornull, затем turns5. Это existing normal retry lifecycle, **не основание переоткрывать уже terminal native session**. D3 arm2 отсутствует. Соседний R13 finite motor patch не устанавливался, grant не выдавался.

| Метрика | Original факт |
| --- | --- |
| Fast requested |136 |
| Reduced real outcomes |135 = **84accepted +51discarded**;1fast in-flight при stop/drain, reducer outcome не записан |
| Native polls |3932 |
| Native gaps/recoveries/unavailable |**95/95/18.220436773s** |
| Native read failures/late receipts |52/16 |
| Invalidation/unavailable ticks/busy tick |51/7/1; invalidation не считать отдельным response |
| Effects |stocknull/stock_usedfalse/stock_unknownfalse; остальные lanes disabled |
| Quality |acceptedfalse/continuous_acceptancefalse/live_acceptancefalse; sustained FAIL сохранён |
| Original cleanup |**cleanup_verified=false**, fast busytrue, sameboot compute_after.fasttrue; прочие8slot flagsfalse, errors[] |
| Control cleanup |listenerthreadfalse/transportbusyfalse/handlers0 |

Original report SHA **`df1c76c8de6782aece6192f42b374bc1c2cec71c705f7fda5f755f43c781b9ee`**, не менялся. После bounded local drain remote fast ещё работал; его не объявляли отменённым. Позднее две независимые sameboot gateway+rawfast health/slotsidle reads и sessionPID0 дали **отдельное external reconciliation**, не переписанный PASS исходного report.

## Sentinel result отдельно от service FAIL

Первый postexit audit: sentinel тот жеPID148044, HEALTHY, terminalnull, reads1847/ok1844/**3TimeoutError/3recoveries** since sentinel start; gateway148046/samecomputeboot, ownSSH masters живы. Последний из этих failure receipts: elapsed302.867330s от sentinel start, **latency0.436047068s, statusnull (HTTP status не получен), cause null**. Ранее snapshot сохранил actual timeout elapsed55.160364s/latency0.427881635s и следом200/latency0.386608071s; recovery с прежним listener. Оба находятся после arm по monotonic receipts. Это реальные health observation timeouts, восстановленные без dependency stop, не выдуманная link loss.

Перед cleanup final export: sentinel **2456reads/2452ok/4TimeoutError/4recoveries**, terminalnull;4-й timeout уже после session terminal, elapsed526.481432s/latency0.431302624/statusnull. maxlatency0.436047068s, total unavailable3.760902978s за несколько отдельных outages, не один непрерывный outage>3s. Sentinel прожил629.818450s до этого export, затем controlled stop. **Narrow transient semantics live подтверждены; ≥30min service и long-term bound не приняты.**

## PCM / bounded state / memory

Preflight→last native **141725696→155541504B (+13815808B)**, source3/gaps0/overflow0. Это PCM read metadata, не acoustic proof. Native95gaps — freshness observation gaps, не PCM capture gaps.8active snapshots10.017…380.297s +1postexit:

- Session RSS35116…35808kB; gateway33276…33400kB; sentinel24632…28508kB (последнее postexit). Никаких30min memory bounds из7min data не выводится.
- Atomic metadata874…20662B; previous251…12316B; report27394B; sentinel2129…2143B; armconsumed210B, all0600. Final audits tmp отсутствует. No append PCM/transcripts/media logs.
- Final ledger cap256, accepted total84/**suffix41IDs/43omitted**; все retained activitieswait. Это suffix event ledger, не полный IDs журнал. Gaps95retained/cap256/omitted0; gap eviction live не достигнут. Totals monotonic в active samples.

## Cleanup, current state и явный handoff

После preserved report/export и two independent sameboot knownidle: повторно idle непосредственно передcleanup; stop own gateway148046, затем sentinel148044; всеPID0. Удалены только exact byte-matched installed3units, собственный stage/token и hash-matched D3 archive; reset только ownfailedsession, daemon-reload. Agent/worker/models/factory не reload/restart. Затем own sockets `-O check` с ожидаемыми60323/60319 → Hub/PC `-O exit`, оба0. OwnPIDs/sockets/Mac18097/Hub18097/18098/8791 absent;3units LoadState=not-found/ActiveState=inactive/MainPID0.

Independent final: **normal listening/captureON mic249/source3**, PCM**161624064→161669120B (+45056B)**, gaps0/overflow0/retiredfalse, turns5/last_errornull; ownersabsent/policy124motorfalse/quietfalse/privacyfalse, Hubfree/actionfalse/stockselected-known-unowned, workerok/idle. Agent216026/boot eea946cc…/arecord216286/factory150625/Hub78887/NRestarts0 unchanged. Exact R8 Agent001be4ec…/pump5fe20c69…/A1configa617…/Hubconfig7f11…; S2voicecfd55a2e…/config97732830…/recognition6211…/privateconfigb864…/shortopt-intrue; existing containerc46d…/image0e42…/StartedAt03:46:22.91163366Z/RestartCount0; PCfast7736 creation/command/exe/weights/LMStudio process identities before/final совпали. New9B/Whisper/Piper weights attestation не заявляется. Known_hosts and PC authboundary hashes+mtime unchanged, newauth/trust/keys/ACL/firewall0.

**ObserverOFF, production voiceON. D3 завершён с concrete native terminal blocker, ≥30min FAIL; аппаратное владение освобождено.** Normal operator STOP — `scripts/companion voice microphone-off`, D3 не вызывала. Native STOP recipe для будущего отдельно разрешённого run: sessionSIGTERM→original report/allslots+independent sameboot backendidle→gateway→sentinel→ownmux. UNKNOWN/knownrevoke не rearm; текущий cleanup уже выполнен.

## Минимальный следующий source-only diagnostic scope

Не исправлять policy и не запускать ещё один soak в этом scope. На **frozen D0 copy** добавить bounded sanitized terminal diagnostic: failure step enum (`operator_before`, `status`, `operator_after`, validation), safe reason code/class и observed phase/boot/epoch consistency; один last terminal receipt без body/transcript/token. Tests: valid same-binding operator phaseerror→terminal; последующая healthy phase не снимает revoke; transient read timeout остаётся transient; diagnostics bounded. Это позволит различить actual failed guard без ослабления300ms/error/owner/compute/terminal guards. HTTP503 producer/stage пока UNKNOWN; следующий отдельный producer diagnostic может только использовать bounded structured route/status fields, не угадывать модель и не включать retries/restart/rearm.

Frozen evidence root: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a1483a-5026-7f70-b475-08a633a3df05/D3-evidence/`. **Final export `live-export-082626/`**: original report/metadata/sentinel, effective imports/units/tests/preflight/arm, separate failure-external-reconcile; live-soak00…08+summary; analysis.json; final-after-live-cleanup.json; cleanup-hub-live/transport-cleanup-live/mac-final-live-cleanup; before/final process/auth pins; exact52entry payload/manifest/diff; SHA256.json. `before-root-review/` и D3-before-final-report.md — historical blocked phase, больше не unresolved approval. Credentials/privateconfig contents/rawmedia отсутствуют.
