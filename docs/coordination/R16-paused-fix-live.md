# R16 — exact R15 pair installed; один R13 trial с четырьмя accepted wait

17 октября 2026, финальный read-only срез **09:34:28 MSK**. **R15 pair install PASS; paused liveness / явный STOP fence PASS. Один exact R13 finite_goal_clock trial:15.013914s,4actual model wait,4accepted,0decision_stale,0proposal/effectPOST/stock dispatch. Finite motor demonstration FAIL; physical settle / effect/server-CAS path UNKNOWN, не exercised. Cleanup PASS.** Модельный wait не заменялся принудительным действием; второго arm/trial/replay не было. Исправную R15 pair оставлена установленной.

**Явный handoff root: R16 завершён, аппаратное владение Reachy/Hub/PC освобождено. Normal listening/capture ON, durable motorOFF, observerOFF, owners absent, Hubfree/stockknown-unowned, worker/PCfastidle.** PROJECT пишет root; здесь изменены только этот отчёт и runtime-baseline, собственные evidence. R11 и S4/Q6 taxonomy не устанавливались. Чаты/подагенты не создавались.

## Установка exact pair и новый boot

Прочитаны PROJECT/R15/Q5/R14/R13/runtime-baseline; D5/R14 handoff принят. Q5 PASS22+4 concurrency/0findings принят без повторного source review/tests. Checkout Agent/pump не использованы для production payload. Fresh remote attestation совпала с обоими R15 preimages и A1 dependency; robot effective imports находятся в `/home/pollen/reachy-companion/src/reachy_companion`.

| Файл | Before SHA256 | Installed/final SHA256 |
| --- | --- | --- |
| agent.py | `001be4ec456141b41d0146b49d06e737ced5383dcba2201c288fa3ed35b667f6` | `1f4e52a6b54b6c12de2bd325e094625ebdf4e2e341df2fa5e2230a51ee660a19` |
| expression_player.py | `7a5f7a0019352ecf8ceb2d3b6cf958e206655ab3a58387671c163aa86730bfdb` | `4b2ea1039145da87a381b3da04ea64693842547d159e3afd65e393247c516e66` |
| capture_pump.py | `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6` | unchanged |
| microphone.py | `d35ef6d3e0cc289e8043a0da68480ecd110ef3fff98afb81da0afad25e416129` | unchanged |
| motion_policy.py | `d224385e999a0c6056db42e1fc3a3c90afaa2009336eaf1ef364037dc98a8466` | unchanged |

Secret-free pair archive33611B/SHA`11a5e0b20e7805a973b63d3443d45f7ec0d944335983aa945a57f744a40e3182`:5manifest entries (два candidate,два preimages,patch), плюс manifest. Он перенесён на existing Hub/robot; README/privateconfigs/tokens/keys/media не передавались. Patch SHA`d5d0f0c6f5e694b7654407dc185115eb6b80b16e8771fc0dfb056beb981dfbd5`. All escalations automatic-review approved, отказов/unresolved approval нет; исходный sandbox network denial устранён обычным reviewed escalation.

09:30:20–21 fresh guarded MicOFF251→252 и motorOFF126→127; paused/retired pump, no Agent arecord/APLAY, Hubfree/workeridle/owners absent. До controlled stop повторно проверены imports/hashes/OFF252/127/factory150625. Protected root-owned0700 rollback `/var/tmp/reachy-R16-rollback-01a1488c/`:оба exact source preimages,metadata,reviewed payload и receipt; durable config/state bytes туда не копировались.

Первый install preflight завершился **до stop/patch** на ImportError: robot-side client не содержит Hub helper control_authority. Agent оставался старым/paused. Исправлен только установочный helper с явной typed validation; повторная проверка разрешила продолжить ту же установку. Это не второй install/arm. Затем остановлен только `reachy-voice-agent.service`; оба preimages→`patch --batch -p0 -F0 --dry-run`→actual patch exit0/no fuzz/no offset→оба after-hash→compile обоих без imports. uid/gid1000/1000,mode0664 сохранены. Robot config SHA`a6171f68…`, durable microphone/policy hash на момент OFF не изменились при source maintenance; epochs не откатывались.

Controlled Agent start09:31:14:PID240868/NRestarts0, новый boot **`1e697e8a-271c-4764-bb44-bc8b617d0d58`**. Fresh new-boot preflight:Mic252OFF/policy127OFF/phasepaused/no capture/APLAY/errornull. Factory150625/Hub78887/NRestarts0 не перезапускались. Старый boot/CAS в trial не переносился. Rollback не потребовался; для будущего rollback применять только pair recipe R15 с новым OFF/drain/stop/hash/compile/newboot, persisted state/epochs не восстанавливать.

## Stage, transport и единственная новая authority

Temporary Hub stage `/home/deploy/reachy-shadow/r16-goal-clock`:40-entry exact R14 dependency closure с неизменённым R13, public finite goal template и bounded passive witness. Archive138309B/SHA`961387f643de32ca97e932ee22abf65cb139913289d9c868b860282a23025f77`; production Hub/native/worker source не заменялись. Effective staged native_agent SHA`b284f55b1afb4a7a8ac050fd5473de46359b01fc6164480b6595cc1e5ba4e004`, session`3900f61d01b655daa815f21c70b1ce1e34fd6be82c2f9a1246725777d661575c`, autonomous config`c7193c6a62e140ca34cb2a5a6e821d86dcdb5621897ad3d1b2acb72d30202f9d`. Client`adc324fc…`, gateway`8f75faaf…`, runtime`feadc958…`, state`6294b232…` совпадают R14/R13; full imports/hashes в evidence.

Approved existing-auth-only bridge:Mac127.0.0.1:18097→PC127.0.0.1:18097 и Hub reverse127.0.0.1:18097→Mac, own mux masters80626/80640. Нет новых auth/keys/trust/ACL/firewall/LANlisteners. Sentinel — finite read-only witness, не service:78/78health200,terminalnull,max0.276964s,no reconnect. PC fast**7736**, exact creation/exe/command/weights before/final одинаковы:exeSHA`0bbac3a55d4a005772ce8a16c4c222163f683119bbbca13b42f6af788faaa4e6`,weightSHA`37ae482d336108d23516fa35e8e0c4126688d81018b87178a18d752a1357814f`. Main9B/Whisper/Piper/models/worker/Docker не рестартовали/не меняли; независимый новый hash всех main/STT/TTS weights не заявляется.

New goal `r16-single-settle-20261017`,version1,operator origin/evidence_ids[],TTL15s,changed_at**09:32:38.954375MSK**; прежний текст R14 без forcing:initial1°roll→neutral,.5s each,waiting permitted,no speech/tasks. Original deadline guards300ms не менялись. `context.enabled=false`,camera/content/voiceeffects/serviceOFF,period3s/fastdeadline6s. Один существующий entrypoint через passive runpy/profile wrapper; methods/returns не подменялись. Witness capped384,actual107events; timing overhead учитывается, hard realtime guarantee не заявляется.

| MSK | Guarded control / finite lifecycle |
| --- | --- |
|09:32:37.692|Fresh same-value durable MicOFF252→253;expression0→1,paused|
|09:32:38.350|Explicit motor grant policy127→128,ownersnull/quietprivacyfalse|
|09:32:38.956|Consumed one new arm;arm_id`03a11292-5955-434a-a93b-d2cd86c7f85f`|
|09:32:39.060|One process:--allow-native-observation --allow-goal-clock-stock-settle --allow-configured-agent-url --duration15|
|09:32:57.203|Exit1;reason duration/errors[];actual scheduler15.013914s|
|09:32:57.503|Durable motorOFF128→129;expression1→2|
|09:33:01.658|After idle/stable paused receipts,explicit MicOFF STOP253→254;expression2→3|
|09:33:03.131|Fresh guarded MicON254→255;listening/capture подтверждены|

Goal monotonic expiry860931.7658865 не продлевалась. Все новые controls получили свежие typed CAS; end-to-end calls0.1945–0.2052s — это full request duration, **не измерение effect send BEGIN-age**. Hub stock boot`5a2502a1-8b6f-49ff-9390-e6fdd213e24a`/kernelboot`27d5c08c…` стабильны; temporary compute boot`23b04974-13f7-49da-a504-d1d2d7e22be1`.

## Actual model/reducer и физические receipts

| Request ID | Actual choice | Gateway call,s | Reducer |
| --- | --- | ---: | --- |
|`de4404a7-636d-4670-a92f-269013c16d75`|wait|2.134938|accepted|
|`011d00f6-958c-4d5d-82b8-92bc7c34db40`|wait|2.349883|accepted|
|`9316c8d7-5c3f-4926-a332-2b8c62081834`|wait|2.210604|accepted|
|`4f0b4a22-dc3e-4b4d-b409-d9e0080d7ee7`|wait|2.374735|accepted|

Все actual outputs от `reachy-shadow-fast-cpu` (37/39/37/39output tokens,518–521input tokens). Model rationale ссылается на отсутствие audio/context и разрешённый wait; output не переписывался/не retry. Четыре requestID есть в original accepted ledger. Все bindings имеют operator_epoch1/revision1/decisiongeneration1; apply до original model deadline с остатком3.5863–3.8203s. **4accepted/0stale** относится к decisions; original aggregate `accepted=false` правильно сохранён, потому что обязательного stock dispatch нет.

`make_stock_proposal` calls0,dispatch0,execute_stock0,send_settle0,guarded effectPOST0;stocknull/usedfalse/unknownfalse/dispatchobservedfalse. Поэтому original proposal/effect deadline/передача POST/server CAS обоих targets/physical execution остаются UNKNOWN/unexercised. Успешный source fix/receipt не является accepted motion. Single-use/no POSTretry/replay/UNKNOWN contract не менялся; R11 не требовался.

Native90polls,4readfailures/3latereceipts и1native_tick_unavailable_gap сохранены. Motor witness:87successful receipts,4null returns;BEGIN→profile-return0.072785–0.137051s,каждый успешный receipt expression_version1. Это observed receipt timing; worst-case failed/late path не превращён в success. Sensor/PCM UNKNOWN/pcm_continuityfalse,начальный muted audio gap1,continuous/live_acceptancefalse. Стенд не объявляется устойчивой/постоянной автономией.

Independent GET robot `/api/state/full`:**170/170pose receipts,170unique timestamps,0exceptions**,09:32:39.066–09:32:57.170MSK. Roll**−4.014773…−3.949040°**,span0.065734°;bodyyaw−0.069029rad/antennas[−0.003068,0.001534]rad. GET latency0.014469–0.323060s. Требуемый +1°→neutral settle не наблюдался; HTTPaccept за physicalmotion не выдаётся. Register/FK calibration/physicalexposureage/hardstopcertification UNKNOWN.

## Paused liveness, явный fence и cleanup

New-boot MicOFF/motorOFF:4typed operator receipts через3.476386s имеют полностью одинаковую authority/expression_version**0**. После trial motorOFF3paused receipts через2.330518s стабильно version**2**. Явный fresh same-value durable MicOFF STOP изменил mic253→254/expression**2→3**; ещё через1.1s оператор полностью тот же/version3. Это ограниченный live proof отсутствия maintenance churn и сохранённого явного STOP fence. Real expression-change race после proposal в live не exercised (proposal0); Q5 source concurrency proof остаётся отдельным evidence, повторно не объявляется live. Второго arm нет.

Original report**3751B/SHA`27b7d3786e8fccbbefe1467d8eef127157f07b1427360ad720a1f52e26a23671`** byte-exact восстановлен из exported JSON и совпал с remote SHA; все exported localJSON также SHA-verified. Initial local reconstruction ожидала newline, остановилась на reporthash; выбран exact original JSON indentation/newline по remotehash, original report не изменялся. Cleanup_verifiedtrue/all8execution slotsfalse/controlhandlers0/computeidle/quarantine[]. Externaldrain отдельно подтвердил sameboot actualrawslotsidle,Hubfree/actionidle/knownunowned,workeridle перед ON/teardown.

Temporary gateway167868/session/stage/token/trialarchive удалены; собственные masters80640/80626 закрыты по pinned mux identities,свои sockets/Mac18097 отсутствуют. Hubfinal18097/18098/8791 absent/nativeprocesses[]/observerunitsnot-found. Hash-matched pair staging archives на Hub/robot удалены,protectedpairrollback0700 сохранён. Установленная R15 pair проверена финально и оставлена. Никакого voice stimulus/повторного generaltest не было.

Final09:34:28MSK:Agent240868/boot1e697e8a…/NRestarts0,onearecord**241306→240868**,noAPLAY;mic**255ON/listening/capture/source1**,PCM**1304576→2701312B**,gaps0/overflow0/retiredfalse/errornull/turns0. Policy**129motorfalse/quietfalse/privacyfalse**,ownersnull,Hubfree/stockknownunowned,workeridle. Factory150625/Hub78887/config/A1pump/S2worker`cfd55a2e…`/configmodule`97732830…`/effectiveconfig`b864d375…`/shortoptintrue/containerimage/start/restart0/PCfast7736/exe/weights/LMStudioprocesses beforefinalсовпали. Reboot/crosshost power loss/новый voice dialogue не проверялись.

**PASS:**exact pair install/newboot,paused liveness/STOPfence,4actual acceptedwaitIDs,onefinite lifecycle,cleanup/handoff. **FAIL:**finite motor demonstration/aggregate report acceptance. **UNKNOWN:**model settle choice,proposal/effect/serverCAS/physicalsettle path,continuous service. Root может планировать следующую узкую задачу по actual model policy/goal semantics отдельно; этот результат не разрешает forcing/rearm/runtime/prompt/guards edits или blind повтор.

Evidence root: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a1488c-6d93-7202-8427-5b542b17baef/R16-evidence/`. `pair-transfer-manifest.json`, `trial-transfer-manifest.json`, pair-install-final/robot/hub/PC snapshots, exact scripts/archives, `analysis.json`, `final-attestation.json`, `live-export/`(originalreport/modelwitness/motorreceipts/pose/controls/paused/STOPfence/arm/sentinel/drain),cleanup/transports и SHA256index. Rawmedia/transcripts/privateconfig/tokencontents отсутствуют.
