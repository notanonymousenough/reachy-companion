# R5 — observer recovery, source-ready

17 октября 2026, Europe/Moscow. **OFFLINE implementation завершена; live/deployment не выполнялись и не приняты.** Scope: два native source-файла, два целевых tests и этот отчёт. SSH/HTTP/устройства, Agent/audio/camera/worker/shared transport, server epochs и config не изменялись. Другие чаты/подагенты не создавались. Существующие чужие изменения checkout сохранены.

Реализована узкая policy из [R3](R3-observer-resilience.md), с границей [R4](R4-authority-epoch-contract.md) и сохранением [N4](N4-bootstrap-native-live.md). Transient read-only timeout/connection failure и expiry корректного receipt закрывают effect/fast admission, но сохраняют session, control и единственный обычный poll slot. Следующий полный typed fresh receipt с прежней authority, **той же source_generation**, listening/capture=true, retired=false и без регрессии counters/turns восстанавливает metadata/tick lane. Изменение source_generation здесь консервативно terminal, включая same-epoch restart после pause/manual.

**Physical recovery не одобрена и не включена.** После первого gap `physical_closed_after_gap=true` до конца этой session, даже при успешном observation recovery. Это выбранный разрешённый fallback: R4 durable epochs защищают STOP/privacy/owner ABA, но полного нового доказательства всех physical pause/manual interleavings R5 не заявляет. Fresh current pump/source-generation проверяется, однако наличие этого guard не используется как разрешение восстановить stock. Новый opt-in/config не добавлен.

## Конкретное поведение

- Native read проверяет каждый уже полученный authority/status объект **до следующего GET** и до freshness rejection. Увиденный STOP/quiet/privacy/boot/epoch/owner/malformed authority, stopped listening/capture, retired/source change/counter regression и unexpected/auth/protocol/schema error latch-ят terminal revoke. Same values позже latch не снимают. Recovery классифицируется только в read-only observer path; action POST не повторяется.
- Expiry проверяется перед consumption завершённого poll, чтобы новый fresh result не скрыл разрыв предыдущего BEGIN. BEGIN и 300ms сохранены. Gap увеличивает локальную observation generation; старый fast binding не принимается после recovery. Single actual fast/poll Future не cancel/replaced: busy сохраняется, completion старого request отклоняется, новый request создаётся только на обычном разрешённом tick. Нет catch-up/retry burst.
- Stock proposal привязан к generation, exact operator/expression и `min(fast_deadline, receipt_BEGIN+0.3)`. Reservation `stock_used` остаётся single-use. Для native stock внутри разрешённого `native_agent.py` добавлена узкая версия прежнего guarded send: preconnect → свежий authority reread → прежние identity/deadline guards → local admission непосредственно перед каждым header/body/partial socket send. Shared `client.py` не изменён. Это необходимо для worker, уже вошедшего в guarded call до gap. Predicate проверяет active generation, текущую local authority, freshness, close/revoke и permanent physical closure; I/O в predicate нет. Ошибка после начала send остаётся UNKNOWN/terminal, без replay. До первого gap сохраняются отдельные свежие Hub boot/selected/known/free/unowned/idle проверки.
- При gap context scope отзывается существующим nonterminal revoke; `next_context=inf`, historical context удаляется, outstanding context Future остаётся учтён и его result отбрасывается. Context закрыт до конца session, новые epochs/grants для обхода revoke не выдаются. Terminal cleanup по-прежнему отправляет independent terminal revoke. Возможный уже исполняющийся remote context job не объявляется отменённым; его bounded cleanup/revoke acknowledgement остаётся обязательным.
- В unavailable `observe()` не обновляет State старым receipt; native PCM имеет stale+исходный age, текущие phase/busy/capture UNKNOWN. Последние counters хранятся для сравнения. Reports/status содержат gaps с start/end/reason/duration, unavailable duration, recovery count, transport failures/late receipts, invalidated и discarded decisions, skipped ticks и busy slots. `accepted=false` при любом gap; accepted decision IDs всё равно сохраняются. Continuous/live acceptance остаются false: silence не считается успехом.
- N4 setup-only `/status` timeout=2s/body cap=65536 и обязательный новый `native.read()` **до scheduler** сохранены. Runtime/default timeout=300ms, compute health/boot/quarantine guards и finite 1..180s/STOP cleanup сохранены.

## Exact base / output / patch

Git HEAD при начале: `59bc59a6433dee432371319ba48ad0aeab0985f4`. Native sources/tests уже были untracked: **база — сохранённые bytes N4, не git HEAD diff**. Base/output вместе с patch доступны в [R5 evidence](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147cc-0094-7931-8c79-fbdf817c6209/R5-evidence/source-manifest.json).

| Файл | Base SHA256 | Output SHA256 |
| --- | --- | --- |
| `src/reachy_companion/autonomous/native_agent.py` | `3880deeac5589e0f63d1568032045f0a684289ac11e76b9f2178d34e7d55d073` | `c8fb477feffaaf86f5e5e339ed015d9d38a304769552d3d8ed6da6d2f668c615` |
| `src/reachy_companion/autonomous/native_agent_session.py` | `2dfd03fc39db0fb85f97ae3dcd7de98f80e024cdacc6207585991bfcca62aa02` | `3931c0e4f90ca1ffc2911eebc59820ca77b6b8b60e06c527f115f9cd774ef2b0` |
| `tests/test_native_agent_session.py` | `585918bafb39b704b47ee20eb4d9224ec5074dfbf3ba2010e3a409f28ef78699` | `af8cfd87159c8061741d11e238941f5bec0bba5470d04588b7dd3fd330473751` |
| `tests/test_continuous_capture.py` | `fa043ae3175a925367eddd83a21b79460214d25477995256865a383348b73702` | `2d4c80c0b641e3f2168dafd2cbcfe82845ebc94434dbf09dc6f35bc9e9ebc3fb` |

[observer-recovery.patch](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147cc-0094-7931-8c79-fbdf817c6209/R5-evidence/observer-recovery.patch) SHA256: `3d3f4df9b6cb7f1623f97d45f9bc8244c53e905d9f117ec9706ed43b9e09254b`. Только четыре строки scope из таблицы; отчёт не входит в code patch. `preimages/` и `payload/` содержат exact bytes. `runtime.py`, `state.py`, `client.py`, native config/gateway совпадают с R3/N4 pins; hashes unchanged dependencies — в manifest.

## Проверки

**24/24 offline PASS, 2.907s**, Python3.13 existing venv, без установки dependencies. [Полный log](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147cc-0094-7931-8c79-fbdf817c6209/R5-evidence/offline-tests.txt):

```sh
PYTHONPATH=src:tests /private/tmp/reachy-head-validate-20261015/bin/python -B -m unittest test_native_agent_session test_continuous_capture.ContinuousCaptureTests.test_same_epoch_pause_retires_and_restart_uses_new_generation -v
```

23 native tests включают прежние meaningful checks и новые regressions: exact N2 BEGIN228988.631225 / pending read BEGIN228988.735255 / completion228988.994917; expiry закрывает admission и сохраняет оба busy slots, fresh same-binding receipt возвращает tick, старый fast отвергается и следующий fresh request принимается. Проверены узкая transient classification/normal poll cadence/late receipt, terminal evidence до следующего timeout, counter regression, исходный stock deadline, finite controller STOP/cleanup из unavailable без новых context/fast grants. Stock socket barrier проверен **после gap и уже успешного recovery**: 0 POST, used=true, no replay; после фактического отправленного fixture POST+lost response: ровно1 POST, UNKNOWN/terminal, прежние values не возобновляют effect.

Дополнительный exact A1 test использует восстановленные и hash-проверенные Agent `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b` и capture `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6`. Реальные `Agent.set_listening`, `operator_status`, `status`, `_capture_get` и pump snapshot, вместо ALSA — существующий детерминированный subprocess pipe. После same-epoch pause/resume binding совпадает, новый active/not-retired pump имеет generation2 вместо1; NativeAgent отвергает recovery terminal. Никаких audio/network devices. Этот test подтверждает конкретный pause fence, **не** полный physical continuity admission.

Patch dry-run/apply/reverse: exit0/0/0 на отдельных локальных копиях; все4 output hashes совпали после применения, все4 base hashes восстановились после reverse. [Receipt](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147cc-0094-7931-8c79-fbdf817c6209/R5-evidence/patch-check.json).

## Одна следующая finite команда и rollback

Команда ниже **не выполнена**, предназначена для следующего владельца Hub после доставки hash-проверенного stage, offline checks на нём, свежего preflight Agent/Hub/compute и подготовки уже существующих finite transports/gateway. Все env values должны быть получены заново; исторические N4 epochs/boots сюда не подставлять. Fresh output path, normal listening ON, motor OFF; camera и stock opt-in для этой первой observation-only проверки отсутствуют. `R5_NATIVE_CONFIG` должен быть согласован с gateway: native profile, `context.enabled=false`, period3s/deadline6s, прежние main/speech/motion/workflows disabled; исходный example с camera context без этой настройки не подходит. Это требование следующего staged run, repo config в R5 не редактировался. `R5_AGENT_URL` — exact configured Agent URL; `R5_HUB_URL` — pinned Hub endpoint. Lifecycle/reconciliation и уборку существующего gateway/transports выполняет владелец запуска.

```sh
PYTHONPATH="${R5_STAGE:?}/src" /home/deploy/reachy-shadow/.venv/bin/python -B -m reachy_companion.autonomous.native_agent_session \
  --config "${R5_NATIVE_CONFIG:?}" --companion-config "${R5_COMPANION_CONFIG:?}" \
  --token-file "${R5_TOKEN_FILE:?}" --output "${R5_NEW_REPORT:?}" \
  --agent-url "${R5_AGENT_URL:?}" --hub-url "${R5_HUB_URL:?}" \
  --agent-boot "${R5_AGENT_BOOT:?}" --microphone-epoch "${R5_MIC_EPOCH:?}" \
  --policy-epoch "${R5_POLICY_EPOCH:?}" --controller "${R5_CONTROLLER:?}" \
  --duration 60 --status-port 8791 --allow-native-observation --allow-configured-agent-url
```

Цель следующей проверки — actual gaps/recovery/cadence и final busy/cleanup receipts, без live PASS по факту старта. Sustained PCM/camera/stock/physical STOP/≥10 real decisions, LAN latency SLA, server persistence/power loss и recovery физического admission остаются непринятыми. 300ms — прежняя граница; socket timeout не whole-request SLA, зависший read сохраняет единственный slot, compute-health timeout по-прежнему terminal.

Rollback: штатный controller STOP → bounded cleanup и compute/stock UNKNOWN reconciliation; затем в **stage** проверить output hashes manifest и применить `patch -R -p1 -i <absolute observer-recovery.patch>`, сверить base hashes. Не перезапускать/заменять busy backend ради rollback. Reverse возвращает N4 terminal-on-read-error policy вместе с startup2s+fresh-read. Installed Agent/worker не менялись; production rollback в R5 не требуется.
