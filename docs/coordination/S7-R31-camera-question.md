# S7 R31 — вопрос не допущен, точный откат завершён

17 октября2026, Europe/Moscow. **Полезный camera-question gate NOT_ADMITTED/UNTESTED; контракт завершён с exact rollback. Голос и камера ON, motor142OFF.** Pending STOP проверен на реальном Agent: PASS. Нового кадра/инициативного image inference/вопроса не было; это не FAIL качества модели или семантики.

Scope15:58:56–16:33:56, source/review≤16:13:56, proof≤16:28:56, rollback reserve≥5min. S7 sole physical owner. Работа закончена раньше deadline после первого actual control failure, без retry/нового arm/перезаписи prompt/моделей/source variants. R30 motionfault остаётся parked.

## Подготовка и один install

Exact production bytes экспортированы в [preimages/manifest](../../S7-evidence/R31/preimages/manifest.json): Agent1f4e52a6…, spokenvision2d7f29…, snapshotd43a70…, schema/client/capture/mic/policy/volume и activeR29player1e25036f…. Snapshot сохранён с исходными CRLF; HEAD не использован. Public source only; privateconfig/token/media не экспортированы.

[Frozen source manifest](../../R31-evidence/transfer-manifest.json), [source handoff](../../R31-evidence/HANDOFF.txt), [Tech gate](../../TECH-evidence/R31/source-gate.json):14source tests+4independent groupsPASS. Exact old/operator AST и старый spoken prompt/guard сохранены. Installed only Agent7bd09093…, snapshot04e63d85…, newinitiative6b5f6815… after guarded Mic303→304OFF/drain, while motor142OFF. Все preimage pins и исходное отсутствие initiative.py проверены, protected backup `/var/tmp/reachy-S7-R31-20261017` (directory0700/preimages+metadata0600), uid1000/gid1000/mode0664 сохранены; atomic per-file rename при остановленном Agent, syntax compile без runtime imports. Только Agent stop/start; newPID278781/boot3a3a988f…, initialmic304OFF/motor142OFF/knownidle. [Install](../../S7-evidence/R31/install.json), [newboot](../../S7-evidence/R31/new-boot-off.json).

## Actual pending STOP PASS

Fresh Mic305ON. Реальная документированная CLI `/usr/bin/python3 -B -m reachy_companion.initiative arm` из production CWD с тем же существующим config и PYTHONPATH принята как generation1/armed. Затем exact existing Hub guarded-control implementation (SHAadc324fc…, вRAM, не установлен заново) выполнила fresh MicOFF306.

CLI-start→STOP response **0.794969s**, меньше обязательных3s/newPCMquiet перед кадром. Generation2/cancelled/frameNULL; после минимального срока8actualsamples: paused/micOFF/captureOFF/workeridle/Hubfree/actionfalse/stockknown/unowned, no child/arecord/APLAY, errorsabsent. По actual timing/state и frozen controlflow image/model admission0. Нет ручного speech/STT/say/seed. [Pending STOP receipt](../../S7-evidence/R31/pending-stop.json). Offline in-flight child/stream cancellation tests дополняют это finite доказательство; spoken/acoustic STOP не принят.

## Useful arm rejected before frame

Fresh Mic307ON at16:08:59.723375. Единственная полезная CLI arm попытка дала **POST `/initiative` HTTP409 at16:09:01.192890**, fixed public reason **`Initiative Hub unavailable`**. Две matched journal lines с одним timestamp относятся к одному failure, не двум попыткам. [Reason/HTTP receipt](../../S7-evidence/R31/arm-failure-classification.json).

Source `hub_idle()` проверяет total read duration<0.3s, empty typed factory running list, free/idle Hub, stockselected/known/unowned/sameboot, ready/error-free daemon/backend. **Какой именно subpredicate отказал, UNKNOWN**: runtime snapshot/timing для этой проверки не сохранены. Последующий healthy/free read не доказывает, что те же условия выполнялись в момент arm. Нельзя объявлять network/model cause, ослаблять guards или автоматически повторять arm. Нет доказанного deterministic operator cause для разрешённого ROOT исключения/retry; исключение не использовано.

Generation осталась2/cancelled/frameNULL; no useful accepted arm/no new frame/no initiative image inference/no question/TTS. [Proof result](../../S7-evidence/R31/proof.json), [current after rejection](../../S7-evidence/R31/proof-current.json). **Question quality, canonical spoken question, scene grounding and full question playback UNTESTED.**

Passive80s observer733samples зафиксировал production APLAY279076 и arecord279050 при Agent278781. Это существующее production playback, не инициативный вопрос: полезный arm не был принят. Содержимое/качество этого audio не проверялись и не считается acceptance. Полный playback observer дождался своего finite конца перед возвратом CLI exception; это задержка получения сообщения об ошибке, не новая попытка/model call. [Process metadata](../../S7-evidence/R31/proof-processes.json). Raw audio/pixels/transcripts/question text0.

## Exact rollback and current useful baseline

Fresh Mic307→308OFF/drain/knownidle. Только Agent остановлен; exact Agent1f4e52a6… и snapshotd43a70… восстановлены, owned newinitiative.py удалён после SHA-match, исходное отсутствие восстановлено, uid/gid/mode сохранены. R29player1e25036f… не менялся. Protected backup/candidate source retained. Второй controlled Agent start — PID279280/boot `ffae5ace-f7d8-475e-bcb7-76f3ccae385d`, сначала mic308OFF/motor142OFF/Hubknownidle, затем separate fresh Mic309ON. Старые ON/grants/epochs не восстанавливались. [Rollback](../../S7-evidence/R31/rollback.json), [rollbackboot](../../S7-evidence/R31/rollback-boot-off.json), [freshON](../../S7-evidence/R31/rollback-on.json).

**Final actual16:12:31.909145:** listening/captureON/mic309/source1/PCM819200B/gaps0/overflow0/retiredfalse; errorsabsent/ownersnull/quietprivacyfalse/volume100/motor142OFF; Hubfree/actionfalse/stockknown/unowned/workeridle. Onearecord279326→279280, factory150625 active/NRestarts0 unchanged. Actual sourcepins restored, configa6171f68… unchanged, canonicalAlice config retained, hardware100%/0dB/no mixer change. Camera2differentRAMframes525810/526302B/readerclosed/rawfiles0/pixelsexport0/audioinit0/inference0. [Final state](../../S7-evidence/R31/final-after.json), [Robot/source preservation](../../S7-evidence/R31/final-robot.json), [camera](../../S7-evidence/R31/camera-pixel-check.json).

PC ordinaryfalse/ACKfalse/+2dB/9BWhisperPiper/worker unchanged byR31. Agent controlled restarts2 (install+rollback), mic controls6 (OFF304/ON305/OFF306/ON307/OFF308/ON309), motorcontrols0, factory/Hub/PCworker/models restarts0, new initiative image/model requests0, paidexpense0. No second useful arm or source/prompt/model variant. R31 feature is currently absent; frozen CLI is an archival recipe, not an installed capability. R28 two useful normal replies remain prior voice evidence, fullcompanion/autonomy/30min notaccepted.

**One remaining blocker:** the initiative Hub-admission guard rejects the useful arm; exact rejecting predicate stillUNKNOWN. Further causal work/repair cost requires separate ROOT/Tech decision; unused35min budget is not automatically spent. Preserve ordinary voice/cameraON/motorOFF. Explicit listening STOP remains `scripts/companion voice microphone-off`. No further probes/inference after this terminal handoff.

**Hardware explicitly released to TechLead:** 2026-10-17T16:13:41.759557+03:00. Actualscope elapsed 886s; no extension or further probes.
