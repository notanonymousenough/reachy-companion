# R18 — один fresh R17 goal.text trial: actual wait, wire PASS, motion FAIL

17 октября 2026, финальный аппаратный receipt **10:17:47 MSK**. **Единственный finite trial завершён: actual 15.019024s, 5 настоящих model outputs `wait`, 4 accepted reducer decisions, последний ответ drained без reducer outcome. Proposal/effect POST0; fixed settle не наблюдался.** Original aggregate report `accepted=false` сохранён. R17 text-only candidate действительно дошёл до actual constructed request; actual tokenizer admission и связь request→response→reducer доказаны для двух полных captured requests. Это не доказательство physical execution.

**Явный hardware handoff root: R18 завершён, эксклюзивное владение Reachy/Hub/PC освобождено. Normal listening/capture ON, durable motorOFF, observerOFF, owners absent, Hubfree/stockknown-unowned/workeridle/PCfastidle.** Собственный stage/gateway/transport сняты после verified idle. PROJECT пишет root. Новые чаты/подагенты не создавались; S6 source-only не использовала стенд.

## Scope, exact pins и preflight

Прочитаны PROJECT/runtime-baseline, D6 explicit handoff, R17/Q7, R16/R13 и соответствующие Q4/Q5 guard contracts. Q7 PASS/0 findings/5 construction checks принят без нового runtime fix. R17 template SHA **a39c1ddc3e0ded6edb2b4fc81d23884b706bb932b009d049096f151f46107020** independently checked. Historical template не использован как authority: fresh metadata и новый arm созданы непосредственно перед запуском.

Fresh before/final совпали: R15 Agent **1f4e52a6…**/ExpressionPlayer **4b2ea103…**, A1 pump **5fe20c69…**, microphone d35ef6d3…/policy d224385e…, robot config a6171f68…; Agent**240868**/boot**1e697e8a-271c-4764-bb44-bc8b617d0d58**/NRestarts0, factory**150625**; Hub**78887**/NRestarts0/import008be03f…/clientadc324fc…/config7f11d114…/kernelboot27d5c08c…/stockboot5a2502a1… unchanged. PC fast**7736**, creation/exe/command/weights pinned: exe0bbac3a55d4a005772ce8a16c4c222163f683119bbbca13b42f6af788faaa4e6/weights37ae482d336108d23516fa35e8e0c4126688d81018b87178a18d752a1357814f. S4 effective site-packages voice **4ec7cfe56f7ee5a4b37ac9906a2c467b70983a6437a7840c25416695a5dfd4fd**, configmodule97732830…/PID1configb864d375…/shortoptintrue/containerc46d…/image0e42…/StartedAt**2026-10-17T06:46:23.968192569Z**/RestartCount0 unchanged. LM Studio process identities unchanged. Main9B/Whisper/Piper/worker/Agent/factory/Hub не рестартовали и не изменялись; независимые новые hashes всех main/STT/TTS weights не заявляются.

Initial fresh normal mic261/policy129OFF/source6/turns5/errorsnull, Hubfree/stockknown-unowned/workeridle/PCfastidle/ownersnull/quietprivacyfalse; observer3unitsnot-found/no nativeprocess/ports absent/cameraOFF. Затем штатные guarded durable MicOFF261→262 и same-value motorOFF129→130; paused/no capture/idle подтверждены. 4 paused operator receipts за3.455032s имеют одинаковую authority/expression_version17. Единственный scheduler/poll/fast/effect owner — собственный finite session; observation service не запускался.

Secret-free archive **139661B / SHA9f176ebd8be4cd4bb888fb7a0a63e4d8b7043cec3890ee21b254bd1760380236**,41 manifest entries:38 unchanged frozen R16 runtime/dependency entries, exact reviewed template, passive witness и новый passive wire recorder. Production runtime source не заменялся; manifest всех bytes и8 effective staged imports проверен на Hub. Staged native b284f55b…/session3900f61d…/autonomousconfigc7193c6a…/gateway8f75faaf…/runtimefeadc958…/state6294b232… совпали R16/R13. README/private config/token/media в transfer отсутствуют. Дополнительная local recorder probe: actual post→Request bytes и exception unchanged, incomplete capture помечен failed; сетевых вызовов0. Это проверка recorder plumbing, не model/tokenizer fixture acceptance.

Existing-auth-only Mac→PC local и Mac→Hub reverse **loopback18097**, собственные pinned mux96537/96540; новые keys/auth/trust/ACL/firewall/LANlisteners не создавались. Gateway только loopback18098, собственный PID**172040**, compute boot**647130e2-3a8e-4ad9-bc7d-49de80007e8c**. Finite read-only bridge monitor 78/78health200/terminalnull/max0.334806s/no reconnect. Начальный sandbox read-only SSH `Operation not permitted` прошёл тем же sanctioned escalation; auto-review denial/unresolved approval отсутствует.

## Одна новая authority и неизменные fences

Fresh goal **`r18-single-settle-0f262d8964b84ac7`**, explicit version**1**,originoperator/evidence_ids[],TTL**15s**,actual changed_at**2026-10-17T07:16:43.297737Z /10:16:43.297737MSK**. Reason и все остальные public config fields сохранены; reviewed task text exact R17. SHA фактического launch config **0b512e44f509094ffb1a3f1fbb0e838547fdfec9e29058e61f5a870d181506c3** воспроизведён из exact candidate плюс отдельные fresh metadata и совпал с remote receipt. Version1 задан явно для нового ID. Это не глобальная anti-replay гарантия changed_at; freshness обеспечена данной подготовкой.

| MSK | Guarded lifecycle |
|---|---|
|10:16:42.043|Fresh same-value MicOFF262→263,paused,expression17→18|
|10:16:42.703|Explicit motor grant policy130→131; свежие boots/epochs/owners/Hub/worker/compute idle checked|
|10:16:43.298|Fresh goal prepared; единственный consumed arm; actual arm_id `f61c52ec-d8ff-4b10-bf5b-f696028d7a17`|
|10:16:43…10:17:01.631|Один entrypoint `--allow-native-observation --allow-goal-clock-stock-settle --allow-configured-agent-url --duration 15`; scheduler actual15.019024s,exit1/duration/errors[]|
|10:17:01.959|Guarded durable motorOFF131→132;expression18→19|
|10:17:06.135|После sameboot drain/pausedstable явный MicOFF STOP263→264;expression19→20|
|10:17:07.597|Отдельный normal MicON264→265; listening/capture confirmed|

Context/camera/content/service/speech effects OFF; period3s/fastdeadline6s/TTL15 остались прежними. Goal expiry **863576.098364499** monotonic от arm, не продлевалась. Model generation/revision/operator_epoch1 стабильны. Original model/proposal min-deadline, <300ms BEGIN/effect и оба server step CAS, real expression change, STOP/mic/policy/boot/owner/quiet/privacy/goalversion/expiry, single-use/no POSTretry/replay/UNKNOWN сохранены unchanged source. Proposal0 означает, что effect deadlines/server CAS в этом окне **не exercised**. Во время inference motor receipts expression18 стабильны; после motorOFF3 paused receipts за2.331167s version19, явный STOP version20 и ещё1.1s stable. R11 не установлен/не prerequisite.

## Actual request bytes, tokenizer и model choices

Passive `sys.setprofile` observer в собственном gateway записывал **actual urllib Request.data прямо перед transport**; payload/schema/returns/исключения/порядок вызовов runtime не менял. Сверены exact serializer bytes `json.dumps(payload,ensure_ascii=False).encode()`, body SHA, system/content и templated prompt из actual body. Token/env/headers/endpoints/private config/rawmedia не сохранялись. Recorder overhead входит в реальные deadlines.

[Original wire receipt](/Users/notanonenough/reachy-companion/R18-evidence/live-export/wire.local.json): **12533B / SHAf367df9a461144901d6086dc217d23e7134304e98ee8feea70f235f5970b6f86**, **2 полных requests**,cap16KiB/4requests,3 дополнительных requests не сохранены целиком из-за byte budget; failures[]. Ни один сохранённый prompt не усечён. Для остальных3 полных historical wire bytes proof не заявляется. Это предусмотренный Q7 вариант «сохранить меньше полных requests в пределах cap», не повышение caps или второй arm.

| Request ID | Actual body bytes / SHA256 | Prompt bytes / SHA256 |
|---|---|---|
|`d2170062-fb95-4137-8218-89ad1e272221`|2958 / eb2cc9daabafdff8eba6ec13c1a4b8e93f3aede7f30cea29abf3900486ee6232|2170 / 618723dfcc65cb488d65fc437bc08aa57b22fe2b5f89e0472f0aaa447f51f6f1|
|`304b1ed5-aa66-48ca-8af9-e6172af5f52d`|2961 / 3f21d0179725db9dea29a6a10923c766eafc94f2eade5b6bbc73e018f8f2775a|2173 / 63bc007324d8d35e3271d68148fadf40ed63dbad82c429b47a6829fa4c5e6603|

Оба captured requests содержат exact fresh goal/text/version/origin,actual elapsed clock/goal_remaining_ms,op.motion_allowed=true/MicOFF/quietprivacyfalse, native.audio=no_data/age null/summaryempty. Memory/prev/evidence_aliases/candidates/ready/pending=[] и dialogue="". Native generic system byte-exact прежний. Schema совпала actual unchanged `fast_schema(...,'settle')`: wait разрешён, только прежний optional explore/motion=settle. Personality/sim.origin=simulated и прочие static FastView fields сохранены; их влияние на выбор не установлено.

Actual counts **text555/input572/template17** и **558/575/17** относятся к тем же request IDs/compute boot и совпали с actual response usage; admission PASS при unchanged text2744/template256/output192/reserve256/context4096. Полный prompt/system/content/body сохранён, не reconstructed fixture. Сумма input+outputreserve+contextreserve1020/1023≤4096. Для остальных model outputs фактический usage есть в original witness, без full body claim.

| Request ID | Actual choice | Gateway call,s | Actual tokens text/input/template | Reducer |
|---|---|---:|---|---|
|`d2170062-fb95-4137-8218-89ad1e272221`|wait|2.471095|555/572/17|accepted|
|`304b1ed5-aa66-48ca-8af9-e6172af5f52d`|wait|2.517862|558/575/17|accepted|
|`86242730-e567-4e89-a261-acf2456c3e47`|wait|2.495954|557/574/17|accepted|
|`43a1f076-17f6-45f2-8fc9-65ff14707f30`|wait|2.483784|557/574/17|accepted|
|`712c600f-4040-4380-8dbd-b880f962cf8a`|wait|2.799172|558/575/17|drained; reducer outcome absent|

Первые4 request IDs совпали original accepted ledger/GoalClockState.apply bindings и returns; apply раньше original model deadlines с остатком3.440…3.476s; stale0. Пятый request был создан обычным scheduler внутри того же arm, завершился при duration drain после goal expiry; apply/reducer outcome ему не приписан, stale/accepted для него не выдуманы. Всего fast_requested5/actualwait5/accepted4; новый inference ради recorder не добавлялся.

Brief why ограничены96символами. Четвёртый actual why содержит `op.motion_allowed=true, but no audio or camera evidence triggers the settle. Waiting is the only` — сохранён без продолжения/переписывания. Можно установить лишь, что **модель снова не выбрала settle при явной operator goal/clock задаче и UNKNOWN**. Внутренняя причина UNKNOWN; запретwait/forcing/mock/rewrite/manualaction/prompttuning/повторный trial отсутствуют.

## Physical evidence и cleanup

`make_stock_proposal`/dispatch/execute_stock/send_settle/guarded effect call0; effect POST attempts0/stocknull/usedfalse/unknownfalse/stock_dispatch_observedfalse. Потому actual basis/proposal deadline/sendBEGINage/оба server target guards/physical execution **UNKNOWN/unexercised**. HTTPaccept/report latency не используются как physical proof. Единственный разрешённый effect cap оставался roll1°→neutral/.5s+.5s и не сработал.

Независимый robot GET `/api/state/full`: **177/177 pose receipts,177unique timestamps,exceptions0**,10:16:43.412–10:17:01.666MSK. Roll**-4.016055…-3.948532°**,span**0.067523°**; требуемый settle не наблюдался. GETlatency0.010946…0.304369s. Register/FK calibration/exposure age/hardstop certification UNKNOWN. Native97polls/readfailures2/latereceipts2 сохранены; passive motor receipts95nonnull/3null,successful BEGIN→profile-return0.068218…0.138885s/expression18. Это receipt timing, не effect-send timing. Muted audio UNKNOWN/pcm_continuityfalse/один initial gap; continuous/live_acceptancefalse, D3≥30minFAIL сохранён.

Original report **3716B/SHA3ef953c3c9a4fe4d58842b7ec772032abe4d8b665e32b4c639bce23c9af45ab1** сохранён byte-exact по remote SHA. `cleanup_verified=true`,all8execution slotsfalse/controlhandlers0/computeidle/quarantine[]; independent external drain подтвердил actual fast slotsidle/same computeboot/Hubfree/actionidle/stockknown-unowned/workeridle до normalON и teardown. Last wait reconciled без job kill/replay; UNKNOWN effect не возникал.

После export/hash verification/idle снят только PID-pinned gateway172040; собственный `/home/deploy/reachy-shadow/r18-goal-clock`/token/archive удалён. Masters96540/96537 закрыты через exact own mux, sockets и Mac18097 absent; Hub18097/18098/8791 absent/nativeprocesses[]/observerunitsnot-found. Production и protected historical rollback backups сохранены. Удаление/restart модели или чужого job для PASS не применялось.

Final **10:17:47.389798MSK**: Agent240868/sameboot, mic**265ON/listening/capture/source7**,PCM**2048→1259520B**,gaps0/overflow0/retiredfalse/turns5/last_errornull; один arecord**243094→240868**,APLAYabsent. Policy**132motorfalse/quietfalse/privacyfalse**,ownersnull,Hubfree/stockknown-unowned/workeridle/PCfastidle. Expressionversion21 после normalON — normal lifecycle, arm уже закрыт; старые bindings не переиспользовались. Epochs здесь historical receipts, не будущие CAS payload.

**PASS:** exactR17 actual wire и tokenizer admission для2полныхrequests,4acceptedwait/0stale,один finite lifecycle/unchangedinstalledpins/verifiedcleanup. **FAIL:** finite motor demonstration. **UNKNOWN/unexercised:** model settle selection/proposal/effect/serverCAS/physicalsettle; постоянная автономия не проверялась. R18 работу закончила и явно освободила hardware root; последующее решение отдельное, без разрешения на дополнительный arm/tuning в этом чате.

Evidence: [analysis](/Users/notanonenough/reachy-companion/R18-evidence/analysis.json), [original report](/Users/notanonenough/reachy-companion/R18-evidence/live-export/report.local.json), [model/binding/motor witness](/Users/notanonenough/reachy-companion/R18-evidence/live-export/witness.local.json), [pose](/Users/notanonenough/reachy-companion/R18-evidence/live-export/telemetry.local.json), [controls](/Users/notanonenough/reachy-companion/R18-evidence/live-export/controls.local.json), [fresh goal/config attestation](/Users/notanonenough/reachy-companion/R18-evidence/live-export/launch-config-attestation.local.json), [transfer manifest](/Users/notanonenough/reachy-companion/R18-evidence/transfer-manifest.json). Все собственные scripts/receipts/archive/SHA index — [R18-evidence](/Users/notanonenough/reachy-companion/R18-evidence/).
