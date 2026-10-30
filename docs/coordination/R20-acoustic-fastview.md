# R20 — bounded acoustic facts → normal FastView

17 октября 2026, Europe/Moscow. **SOURCE-READY, 51/51 offline PASS.** Контракт 1 R19 завершён: exact existing reader → R15 read-only status → normal NativeState → actual fast request construction. Useful measured descriptor facts доступны модели; physical reaction authority остаётся UNKNOWN. Live hearing/model choice/physical effect не доказаны. Runtime checkout не менялся, bundle не переносился и не устанавливался. Сеть/Hub/PC/robot/model calls/arm/deploy не использовались; S7 остаётся единственным hardware owner. PROJECT/baseline не редактировались, новых чатов/подагентов нет.

Прочитаны R19/PROJECT/runtime-baseline и R15/R16/R18 pins. A1/R15 source взяты из frozen evidence, **не из checkout Agent/pump**. Native/State/config сверены с exact R18 transfer manifest: Native `b284f55b…`, State `6294b232…`, config `c7193c6a…`. Это source сверка, не новая remote attestation.

## Актуальный working outcome для TechLead

По организационному handoff технический руководитель — `01a148d9-f558-7151-93c5-016d77b24489`; дальнейшие назначения и технический путь определяет он по [OPERATING-MODE](OPERATING-MODE.md). Описанный ниже camera handoff — готовый source artifact, а не самостоятельно назначенное продолжение R20. S7 сохраняет единственное hardware ownership до явной передачи.

Реально готов переносимый source-only путь measured acoustic descriptors до normal fast request: synthetic reader/status/construction и защитные регрессии подтверждены 51/51 tests. Пользовательская runtime-функция этим срезом ещё не включена; рабочий voice baseline не затронут, полезных deployed функций не потеряно. Время итогового test run — 2.467s; полное wall-clock время работы отдельно не измерялось.

Точный blocker только для physical reaction от acoustic evidence: существующий reader не даёт обоснованной верхней границы capture→read latency. Minimal required dependency — такая граница, связанная с той же generation/window. Measured descriptor observation от этого не блокируется. Решение R20: frozen candidate завершён, source ownership освобождено, новых исследований/проверок/remote действий не назначать. Следующий пользовательский outcome и способ joined integration выбирает TechLead; apply/rollback доступны в bundle.

## Готовый payload и handoff

Bundle: [R20-source.tar.gz](../../R20-evidence/R20-source.tar.gz), 74307 bytes, SHA256 `4fd2d99987eabed063198b8019727e3ed2f9819cfd29bafb147a529c4013bf07`. 11 source-only entries: три candidate, три preimages, targeted regression, manifest/patch/patch verification/README. Config/state/credentials/media отсутствуют.

[Manifest](../../R20-evidence/source-manifest.json) содержит все full before/after/dependency hashes; [transfer index](../../R20-evidence/transfer-manifest.json) — каждый entry. Единственные runtime-файлы:

| Файл | Exact preimage | Candidate SHA256 |
| --- | --- | --- |
| `capture_pump.py` | A1 `5fe20c69…` | `cd377513d83559b7fc63e70576f14a299b4cf04b3f8c785ce4d784e756c7d54a` |
| `agent.py` | R15 `1f4e52a6…` | `89cf4f3eb442f7d606d8ce4e8aede95fa27fee904040ced574667e7cc5acd325` |
| `autonomous/native_agent.py` | R13 `b284f55b…` | `3d4c3b0976079cae2aeb9e9f252a194ed9e0565a4641ebe36605d7e134c07a16` |

**Shared native source ownership освобождено.** Camera-контракту 2 передан [candidate native_agent.py](../../R20-evidence/candidate/autonomous/native_agent.py), full hash выше. Его нужно взять следующим preimage и соединить manifest; checkout Native по-прежнему R13. Повторного изменения R15 pair или pump в camera-срезе не требуется.

[Patch](../../R20-evidence/r20-acoustic-fastview.patch), SHA256 `72264aed3dcf853ef1eaed9db2be7bb04e3bc81fe04c28c32128f6ea8b2ab77c`; `-p0` из package directory. [Forward/reverse verification](../../R20-evidence/patch-verification.json): dry-run/apply/reverse dry-run/reverse на disposable copies, `-F0`, без fuzz/offset, exact bytes и compile без imports PASS. [README](../../R20-evidence/README.txt) содержит future authorized apply/rollback с OFF/drain/stop/new boot, без отката persisted state/epochs. Никакой transfer или live action этим отчётом не разрешён.

## Изменение

Assembler отдаёт уже вычисленные RMS/VAD/loud; вторых расчётов VAD, recorder/STT/main/reply нет. Pump хранит один latest descriptor текущего чанка ≤1s и один scalar predecessor для delta/onset. Никаких PCM/transcript exports, направления, identity/music inference или reader HTTP/callback. При calibration нет descriptor. Если чанк собран несколькими `os.read`, сохраняются первый/последний contributing read receipts, а не выдуманное время capture. Sequence, source generation, Agent boot, mic/policy epochs, read-call ID, mask generation идут до request без переименования значений.

Status получает counters и summary одним pump snapshot; Agent меняет **только `status()`**. Own playback + прежний tail очищают descriptor/predecessor; окончание tail не возвращает старые данные, требуется новый чистый чанк. STOP/privacy/quiet/retire/error/binding mismatch, overflow/receipt gap убирают summary; rejected late publish его не восстанавливает. Capture source с gap/overflow остаётся непригодным для acoustic export в этой generation, его voice lifecycle не меняется.

Native принимает только typed bounded metadata. Local BEGIN + remote measured read-receipt age дают консервативный local receipt deadline; clocks разных машин не вычитаются. Same-seq polls не продлевают deadline; counter/seq/mask regression, same-seq mutation, binding/source mismatch отбрасываются. В FastView три capped поля `native.acoustic{,.binding,.receipt}` с общим seq, `state=read_receipt_only`, `age_ms=null`, `capture_age_upper_ms=null`, `reaction=UNKNOWN`. Invalid/stale — пустой UNKNOWN. Всего ≤12 sensors, каждый summary ≤256; schema/system/token caps прежние.

**Model observation и physical effect разделены:** RMS/VAD/delta/onset — измеренные факты, они проходят actual request и после восстановления poll-наблюдения на новом чистом окне. Read receipts не доказывают физическую свежесть звука. Поэтому normal sensor-derived invitation отсутствует (`op.motion_allowed=false`), навязанное fixture `motion` не создаёт proposal. Единственная конкретная dependency для acoustic physical reaction — **измеренная верхняя граница capture→read latency от существующего audio owner, связанная с этой generation/window**. Нового audio consumer для этого не требуется. Сам descriptor path этой dependency не ждёт и готов к joined integration.

R5 physical/context closure после первого observation gap не переоткрывается. ExpressionPlayer `4b2ea103…`, worker/router/S6/S7, State/config/schema/system, motion executor/server guards, service admission и camera/context modules не изменялись. `GoalClockNativeAgent/Binding/State` и `NativeScheduler` AST byte-for-byte equivalent; normal `stock_allowed/dispatch/admit_stock/execute_stock/send_settle` и guarded transport также unchanged. Existing boot/epoch/owner/error/expression fences, original deadlines, BEGIN/effect <300ms/server CAS, single-use/no retry и occupied/UNKNOWN slots сохранены.

## Meaningful offline acceptance

[Log](../../R20-evidence/offline-tests.txt): **51 tests, failures/errors/skips=0, 2.467s**. [Receipts](../../R20-evidence/offline-receipts.json). 16 R20 tests, 22 existing goal-clock guards, 12 paused/STOP/expression regressions, один exact R8 retirement/rearm-gap counterexample — все на candidate Native. Старый R15 checkout-import-location assertion исключён: он требует именно R13 checkout path; new R20 pin/scope check проверяет frozen candidate. Начальные harness ошибки/это path expectation сохранены в initial logs, runtime guard не ослаблялся.

- Actual `CapturePump._read` читает synthetic pipe через прежний selector/os.read, с одним injected process object без subprocess/device. Split chunk подтверждает настоящий read interval, один reader и реальные byte/call counters. Exact candidate Agent `status/operator_status`, normal NativeAgent/NativeState и actual `ModelBackend.generate_loaded` construction сохраняют measured значения и provenance. Transport/tokenizer — явные fixtures; sockets/model/device запрещены.
- Quiet→loud даёт RMS1000/delta1000/onset=true/VAD3/window30ms/seq2, те же boot/epochs/source/mask/read IDs в actual prompt. No raw content/second main/reply; normal motion schema не приглашает effect. Request3447B в отдельном fixture receipt; cap не расширялся. Fixture token count не объявляется production tokenizer measurement.
- Mask/tail/new clean window, calibration, ≤1s, stale/re-age, seq/source/mask/epoch ABA, malformed/late receipt, STOP/privacy/quiet/owner/error и old in-flight completion PASS. Overflow/gap не дают пригодного invitation. Новые descriptors после poll recovery не восстанавливают R5 physical/context grants.
- Existing target-server CAS, original model/effect deadline, explicit STOP/expression fence, single-use/no replay и UNKNOWN occupancy PASS. Fixture socket attempts в старых goal-clock tests не являются сетью/движением.

Воспроизведение из repository root:

```sh
PYTHONPATH=src:tests /private/tmp/reachy-head-validate-20261015/bin/python -B R20-evidence/run_offline.py
```

Runner bounded45s; candidate можно переместить и указать `R20_BUNDLE=/absolute/bundle` для R20 regression. Synthetic acceptance доказывает source plumbing, не живой слух, модельный выбор или движение. Следующий source handoff — camera-контракт 2 на переданном Native preimage; нового general review/prompt/model trial R20 не назначает.
