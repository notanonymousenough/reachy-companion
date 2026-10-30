# R15 — paused hold без ложной смены expression authority

17 октября 2026, Europe/Moscow. **SOURCE-READY candidate, 22/22 OFFLINE PASS. Не установлен; actual model/motion/live acceptance UNKNOWN.** Воспроизведена причина R14 `decision_stale` и исправлена только периодическая paused maintenance. R14 пять actual `wait` остаются честным независимым model outcome: этот fix не доказывает выбор settle или движение.

Входы: [PROJECT](PROJECT.md), [R14](R14-goal-clock-stock-live.md), [R13](R13-goal-clock-stock.md), [Q4](Q4-goal-clock-stock-review.md). Работы только локальные, без SSH/сети/робота/Hub/PC/bridge/arm/deploy/моделей. D5 remote ownership не затрагивалось. PROJECT, baseline, units/config/models, voice stream/worker/router diagnostics и R11 не менялись; чаты/подагенты не создавались.

## Решение и причина двух файлов

Безусловно делать существующий `hold()` идемпотентным небезопасно: даже при `state=None` он отменяет enqueue, начатый до проверки binding, и служит явным expression fence для native proposals. Поэтому все прежние вызовы `hold()` сохраняют **безусловное увеличение version**, очистку очереди/clock и notification.

Только exact R8 `Agent.run` paused MicOFF ветка теперь вызывает `hold(maintenance=True)`. Под существующим condition lock этот режим всегда увеличивает внутренний `hold_generation`, но при `state is None` не меняет публичную expression version. Если выражение активно, maintenance делает обычный hold с version increment. Сравнение enqueue-ticket `(version, hold_generation)` в `set/timeline/dance` отвергает операцию, начатую до любого hold, включая no-op maintenance. `capture_binding/permitted` остаются вне condition; порядок mic→condition locks не меняется. Player worker использует прежний version fence.

Agent нужен для явного различения штатного STOP/cancellation и paused heartbeat; у исходного `hold()` одинаковая сигнатура для обоих. Изменение Agent — **ровно один keyword в paused участке R8**, вне voice stream/manual/retirement. Остальной Agent byte-identical R8 после удаления этого keyword. Обычный `hold()` совместим со всеми прежними callers. Новый режим использует только paused ветка.

R13 `NativeState.observe()` и expression-change fence не редактировались. Сохраняются STOP/mic/policy/boot/epoch/owner/privacy/quiet, неизвестная authority, goal/version/expiry, original model/proposal deadline, BEGIN/effect <300ms, server CAS перед обоими targets, single-use/no replay/UNKNOWN. Новый counter внутренний и не создаёт grant или remote epoch.

## Exact source и область записи

Runtime payload подготовлен **только в evidence/candidate**, без наложения на checkout. Это необходимо: checkout Agent `0cc3e643…` и capture pump `b7b1ffa5…` отличаются от установленного R8/A1. Его diff нельзя включать в production candidate. Exact R14 frozen sources проверены по полным hashes; native import paths и bytes проверены локально отдельно. Новая remote attestation здесь не заявляется.

| Runtime file | Frozen preimage SHA256 | Candidate SHA256 |
| --- | --- | --- |
| `agent.py` | `001be4ec456141b41d0146b49d06e737ced5383dcba2201c288fa3ed35b667f6` | `1f4e52a6b54b6c12de2bd325e094625ebdf4e2e341df2fa5e2230a51ee660a19` |
| `expression_player.py` | `7a5f7a0019352ecf8ceb2d3b6cf958e206655ab3a58387671c163aa86730bfdb` | `4b2ea1039145da87a381b3da04ea64693842547d159e3afd65e393247c516e66` |

Exact frozen source origin: R14 `frozen-source/R8-agent.py` и `expression_player.py`, подтверждённые R14 installed module pins. Required installed A1 pump остаётся `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6`; это dependency pin из R14, не hash checkout pump. Новых pump/Agent R11 изменений нет.

Unchanged actual local R13 imports: native agent `b284f55b…`, session `3900f61d…`, autonomous config `c7193c6a…`, runtime `feadc958…`, state `6294b232…`, gateway `8f75faaf…`; полные значения и пути в manifest совпадают с R14/R13. Payload не содержит их повторных копий/patches. Checkout runtime-файлы оставлены как были.

В repository добавлены только [regression test](../../tests/test_paused_hold_liveness.py) и этот отчёт. Остальные новые файлы — собственный R15 evidence. Чужой diff не включён.

## Offline evidence

**22 tests PASS, failures/errors/skips=0, 0.761s:** 13 новых R15 tests и 9 адресных existing guard checks; полный Q4 review не повторялся. [Log](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14870-e4c6-7233-a575-c78fd3971835/R15-evidence/offline-tests.txt), [machine receipts](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14870-e4c6-7233-a575-c78fd3971835/R15-evidence/offline-receipts.json).

Regression исполняет весь **actual frozen `Agent.run` method** через AST extraction; fake listening Event действительно получает `wait(timeout=1)` и продвигает fake monotonic clock. Constructor не запускается. Настоящий `ExpressionPlayer` из preimage/candidate, actual R13 `read/advance/observe/bind/apply` и отдельные actual `NativeScheduler.advance` trials. Poll receipt каждые100ms, один занятый Future с original request/compute binding, matching completion через2.4s; replacement/catch-up нет. Fixture choices явные, model inference не запускался.

| Проверка | Результат |
| --- | --- |
| Exact old paused1s + fast2.4s | Один stale, accepted0, исходный model deadline106 при apply102.4, epoch1→3; generation1 не менялась. То же через actual scheduler. |
| Candidate с тем же wait | Accepted1/stale0, epoch1→1, expression version1, proposal=null/effect0. То же через actual scheduler, ровно один fast job. |
| Candidate с явным fixture settle | Proposal BEGIN102.4, deadline102.7, model deadline106. No-op maintenance перед effect не закрывает прежний grant; actual dispatch/execute/guarded_control дают ровно один fake socket POST. Socket response fixture, без устройства/physical claim. |
| После102.7 новый receipt | Старый proposal не продлевается; dispatch=false/POST0. |
| Явный hold при idle, set/timeline/dance, hold активного expression | Старая decision stale/no proposal. Hold во время actual plan request отменяет action; worker завершён. |
| No-op maintenance между началом enqueue и binding return | Все три stock enqueue paths отвергнуты, state=None/version0. Следующая новая операция допускается. |
| Явный hold после proposal / expression change после connect | Respectively effect preflight / post-connect reread закрывают send; POST0, used slot остаётся used, повтор запрещён. |
| Existing negative guards | Durable STOP/ON и owner/policy/quiet/privacy ABA на actual exact R8 methods, typed boot/epochs/owners, busy/unknown/foreign, original deadlines, BEGIN age, local stop/send barrier, partial/lost response/no replay и server guards обоих targets PASS. |

Effect fixture не моделирует LAN jitter/реальную длительность четырёх GET legs и не доказывает production запас300ms. Goal-clock sensor state остаётся UNKNOWN/pcm_continuity=false. Accepted fixture settle не является actual model choice. Physical targets/pose/hard stop здесь не испытывались.

Первый запуск system `python3` остановился на отсутствующем `jsonschema` до выполнения checks; использован уже существующий validation venv, ничего не устанавливалось. Initial venv log с5 harness errors сохранён как `offline-initial.txt`: не хватало run-cleanup fake и dance step был вложен лишним списком. Исправлен только harness; runtime candidate bytes с момента сборки те же. Финальный log — отдельный успешный результат.

Воспроизведение из repository root:

```sh
PYTHONPATH=src:tests /private/tmp/reachy-head-validate-20261015/bin/python -B \
  /Users/notanonenough/.codex/visualizations/2026/10/17/01a14870-e4c6-7233-a575-c78fd3971835/R15-evidence/run_offline.py
```

Runner запрещает реальные sockets, имеет45s watchdog, tests запрещают subprocess/device I/O во время fixtures. Existing exact-source setup использует локальный `git show`, без remote. Для переноса bundle regression принимает `R15_BUNDLE=/absolute/new/bundle`.

## Bundle, apply и rollback recipe

Evidence root: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a14870-e4c6-7233-a575-c78fd3971835/R15-evidence/`.

- [Manifest](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14870-e4c6-7233-a575-c78fd3971835/R15-evidence/source-manifest.json) содержит full before/after/dependency/test hashes.
- [Patch](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14870-e4c6-7233-a575-c78fd3971835/R15-evidence/r15-paused-hold.patch), SHA256 `d5d0f0c6f5e694b7654407dc185115eb6b80b16e8771fc0dfb056beb981dfbd5`; два leaf paths, `-p0` из package directory.
- `candidate/{agent.py,expression_player.py}` и `preimages/{agent.py,expression_player.py}` — полный exact payload и rollback bytes; `regression/` хранит exact test copy.
- [Builder](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14870-e4c6-7233-a575-c78fd3971835/R15-evidence/build.py) восстанавливает candidate из pinned R14 source без checkout Agent.
- [Patch verification](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14870-e4c6-7233-a575-c78fd3971835/R15-evidence/patch-verification.json): dry-run/apply/reverse dry-run/reverse на disposable copies, `-F0`, без fuzz/offset, compile и before/after byte hashes PASS. Rollback — тот же patch с `-R`, полный возврат к frozen R8/7a5.

**Будущий production apply, здесь не выполнялся:**

1. После явного hardware handoff от единственного remote owner заново прочитать effective imports и hashes. Допустимы только оба manifest preimage hashes и required installed dependency pins; при любом другом Agent/expression source остановить применение и подготовить новый адресный rebase. R11 не prerequisite и автоматически не ставится.
2. Подготовить secret-free review bundle из этих двух runtime files, patch и manifest, protected rollback source copies и metadata. Fresh guarded MicOFF/motorOFF, подтверждённые idle/reap/owners absent, controlled stop `reachy-voice-agent.service`. Persisted mic/policy/config state не копировать и не откатывать.
3. В установленном package directory `/home/pollen/reachy-companion/src/reachy_companion` сверить before hashes и SHA patch. Сначала `patch --batch -p0 -F0 --dry-run -i /absolute/reviewed/r15-paused-hold.patch`, затем та же команда без `--dry-run`; требуются exit0, отсутствие fuzz/offset, оба полных after hashes и compile обоих `.py` без исполнения imports. Preserve file owner/mode. Agent запускается только после успешной проверки **обоих** файлов. Agent-only install несовместим со старой сигнатурой player; произвольное смешивание запрещено.
4. Controlled start только Agent, затем новый boot preflight/OFF/no capture/no APLAY, неизменные dependency/config/Hub/worker pins. Возврат normal listening через свежий guarded control. Новый finite motor trial — отдельное решение/новый single-use arm и goal; этот отчёт его не запускает и результат не предсказывает.
5. Для rollback снова fresh OFF/drain/controlled stop, проверить оба candidate hashes, применить тот же patch `-R` с теми же dry-run/no-fuzz/hash/compile условиями и подтвердить **оба** original hashes. Затем controlled start/new boot preflight. При partial apply/compile/hash failure держать Agent stopped до восстановления exact source pair. Persisted ON/старые epochs не восстанавливать; чужие services не перезапускать.

**Handoff:** source blocker R14 paused-version coupling устранён в reviewable candidate. Production остаётся без этого fix; фактическая готовность модели выбрать движение, effect-chain latency и physical settle — UNKNOWN. D5 продолжает свой отдельный diagnostics scope; стенд здесь не использовался.
