# R10 — exact R8: составной receipt пересекает retire/resume

17 октября 2026, Europe/Moscow. **OFFLINE: один воспроизводимый authority gap; stock physical rearm НЕ включён.** R8 закрывает конкретное окно R7 clear→retire, но полного доказательства same-active-source admission ещё нет: новый native read, начатый после transient gap, может прочитать `/status` до retire, а завершающий Hub `/control/operator` после resume. Receipt проходит и восстанавливает observer, хотя его source уже retired. R5 permanent physical closure удерживает безопасность.

Изменения R10: один новый regression test, его переносимый patch и этот отчёт. Native runtime/session/state, frozen R8/Agent/pump, server, shared client, audio/worker/camera/context и config не изменялись. SSH/HTTP/deploy/models/devices не использовались; новые чаты/подагенты не создавались. Source fixtures не являются live evidence. R6 `accepted=false` и исходные reports не переписывались.

## Exact source и предел proof

| Source / artifact | SHA256 |
| --- | --- |
| Reconstructed exact R8 Agent | `001be4ec456141b41d0146b49d06e737ced5383dcba2201c288fa3ed35b667f6` |
| A1 pump, unchanged | `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6` |
| Native runtime, unchanged R5/R6 | `c8fb477feffaaf86f5e5e339ed015d9d38a304769552d3d8ed6da6d2f668c615` |
| Native session, unchanged R5/R6 | `3931c0e4f90ca1ffc2911eebc59820ca77b6b8b60e06c527f115f9cd774ef2b0` |
| Current Hub source used for actual operator proxy | `008be03f69d9564c9f476b086ddf9eb3fa8e587682c6791b776234933f8c682d` |
| [New negative regression](../../tests/test_native_stock_rearm_gap.py) | `d82b49bd928d46eeee36012c94537d69a563a390a9d570b146122a0707329ab4` |
| [Portable test-only patch](../../deploy/patches/native-r10-composite-receipt-negative.patch) | `55d31e36aad14d1630391fcbcc16658a15c72648701b92900f2b3fc05fc75df2` |

R8 reconstructed через его неизменный hash-checked builder; HEAD Agent не использован. Native preimages сохранены и byte-for-byte сверены после tests. Полные dependency pins — [manifest](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14803-7376-78e2-89db-f845ac585fdf/R10-evidence/source-manifest.json). Hub pin описывает локально испытанный source, не attestation установленного Hub.

Модель — единственный штатный Agent/API и его reader, concurrent authenticated requests, без внешних writers/file rollback/power loss. Ни universal proof, ни аппаратная непрерывность не заявляются.

R8 source proof исходного R7 окна (номера относятся к exact R8):

* `manual`: legacy `/say|/ask` вызывает `set_listening(False,{})`; bound manual требует paused/capture=false/listening=false и повторяет guard в setter. Вызов начинается с 1057.
* `set_listening`:1005–1054 удерживает mic→policy от binding validation через `listening.clear()` и `pump.retired.set()`. Close/reap выполняется после освобождения locks. Resume до critical section перекрывается clear/retire; resume/operator во время неё ждут mic-lock; resume после неё не очищает retired Event.
* `operator_status`:307 и `status`:278 берут mic-lock; replacement `_capture_get`:375 создаёт новую generation после close. Поэтому **полный status, действительно снятый после retire**, отвергается native retired/source-generation fence.
* Existing R8 deterministic test снова PASS: actual clear gate, blocked resume/operator, затем actual resumed active/processing receipt с retired=true отвергается. R7 negative `/say|/ask` исправлен. Bound listening/manual guards и pause/replacement regression также PASS.

Это доказывает отдельную critical section и её исходный R7 negative case. Native read состоит из нескольких отдельных critical sections; между ними тот же source может быть retired.

## Один counterexample, три входа в тот же mutator

[Test](../../tests/test_native_stock_rearm_gap.py) исполняет полные exact R8 `Agent` methods и actual A1 pump с существующим deterministic subprocess PCM writer вместо ALSA; application methods не AST-extracted/replaced. Hub leg исполняет actual `Hub.operator_proxy`, только его HTTP dependency заменена непосредственным вызовом actual Agent operator method. Socket creation запрещён. Reader остановлен перед actual policy check после `capture_active=true`, вне pump condition. Mutator останавливается на входе actual close, после clear+retire и освобождения authority locks. Это допустимые scheduling boundaries, без изменения application state напрямую.

| Порядок | Наблюдение |
| --- | --- |
| 1. Есть первоначальный receipt, затем transient read gap | local observation generation 0→1; physical fence=true |
| 2. **Новый** `native.read()` BEGIN после gap | Agent `/operator` valid; `/status` — processing, listening=true, capture_active=true, source1, retired=false |
| 3. Перед финальным Hub operator leg выполняется bound `/pause` либо legacy `/say`/`/ask` | Actual setter clear+retire под обоими locks; close parked вне locks; source1 retired=true |
| 4. Existing legacy `/resume` (`set_listening(True,{})`) завершается | Reader ещё parked: phase/capture прежние; listening=true; boot/mic1/policy3/owners/expression1 прежние; retired Event остаётся true |
| 5. Actual Hub operator proxy завершается | Typed operator **точно равен** исходному; retired/source-generation в `/operator` отсутствуют |
| 6. `NativeAgent._read`:198–229 и `advance`:231–247 | PCM взят из шага 2; финальный operator из шага 5; BEGIN-age <300ms; same generation/counters; recovery=1, unavailable=false, FRESH |
| 7. Следующий отдельный полный native read | Видит retired=true и terminal-revokes session; это происходит уже после ошибочного recovery receipt |

В сохранённом run возраст принятого receipt: bound pause **0,585ms**, say **0,437ms**, ask **0,416ms**. Все BEGIN после gap (2,7–4,6µs после отметки gap), без widening 300ms или backdating. PCM bytes0 допустимы существующим typed contract, source_generation1; retired меняется false→true. Счётчики и epochs не регрессируют. Это не поздний старый receipt, начатый до gap.

R5 physical fence всё время true; `stock_allowed=false`, POST0, voice/model0. **Контрпример опровергает достаточность recovery receipt для rearm, а не утверждает фактический physical dispatch.** Снятие только permanent fence позволило бы показать новому model snapshot прежнюю stock capability при уже retired source, пока следующий poll ещё не consumed. Fresh Hub/free/known/unowned/expression сами по себе retirement не содержат. Дополнительный такой же GET лишь переносит последнюю границу; доказательства terminal pause/manual скрытого между status и operator не появляется.

## Tests и evidence

**131/131 offline tests PASS, failures/errors/skips=0, 7,684s.** Новый negative test — 3 subcases одного порядка. Остальные 130 — неизменный R8 suite, включая fixed R7 negative, bound guards, no second child, STOP/privacy/quiet, source/counter terminal checks, old-fast discard/fresh silent decision, guarded-read→send gap POST0, lost-sent-response UNKNOWN + used-slot/no replay. Положительный fresh-model-stock-after-gap test не заявляется: rearm не реализован по разрешённой negative ветке задания.

```sh
PYTHONPATH=src:tests /private/tmp/reachy-head-validate-20261015/bin/python -B -m unittest \
  test_native_stock_rearm_gap test_manual_retire_fix test_continuous_capture \
  test_native_agent_session test_capture_pump test_bound_listening test_agent_stream_timing -v
```

Evidence: [negative receipts](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14803-7376-78e2-89db-f845ac585fdf/R10-evidence/negative-receipts.json), [test log](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14803-7376-78e2-89db-f845ac585fdf/R10-evidence/offline-tests.txt), [runner](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14803-7376-78e2-89db-f845ac585fdf/R10-evidence/run_offline.py), [exact R8 manifest](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14803-7376-78e2-89db-f845ac585fdf/R10-evidence/exact-R8/manifest.json), [standard patch apply/reverse check](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14803-7376-78e2-89db-f845ac585fdf/R10-evidence/patch-check.json).

## Одна адресная server-правка для следующего review

**Предложение, не реализовано и не является reviewed-compatible Agent:** при первом retirement живого pump в `set_listening(False,…)` продвигать существующий microphone authority epoch под теми же mic→policy locks, с существующей durable/fail-closed discipline и сохранением microphone enabled/owner. Уже retired/already-paused bound manual не должен повторно менять epoch; binding после активного pause нужно получить заново. Тогда финальный `/operator` и существующие stock epoch checks видят retirement как authority change даже после resume/replacement; скрытый порядок выше не может восстановить прежний binding. Это требует отдельного review server CAS/persistence/manual contracts и exact builder/tests; импровизированный in-memory increment или новый native grant не предлагается. Frozen R8 не переписывался.

До этого изменения source-proof недостаточен даже при установленном exact R8. **R9 handoff обязателен перед любой аппаратной работой; подтверждение применения R8 оператором необходимо, но для rearm после найденного gap уже недостаточно.** Следующий reviewed-compatible runtime pin должен иметь proof retirement authority и затем быть подтверждён оператором на hardware до enable. R9 установка самого R8 manual fix и source-only R10 negative evidence не разрешают physical rearm.

Unchanged invariants: old requests/proposals invalidated по local observation generation; новый model decision/snapshot/request обязателен; used/sent/UNKNOWN slot не очищается; POST retry0; known STOP/privacy/quiet/boot/epoch/owner/counter/source changes terminal; BEGIN/effect/preconnect/read/header/body/partial-send 300ms barriers не расширяются. Context/camera остаётся R5 closed. Нет второго motor owner/framework.

## Конечная source-review установка / rollback

Runtime deployment/enable candidate отсутствует из-за authority gap; R10 runtime rollback не нужен. Ниже только перенос regression в **отдельный review checkout с R8 tests/dependencies**, не команда для устройств. Patch содержит ровно один test. Для обратного действия заменить `install` на `rollback`; apply/reverse с `--fuzz=0` проверены.

```sh
sh -s install <<'SH'
set -eu
mode=$1
cd "${R10_REVIEW_CHECKOUT:?}"
review_patch=${R10_REVIEW_PATCH:?}
python3 - "$review_patch" <<'PY'
import hashlib, pathlib, sys
assert hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest() == '55d31e36aad14d1630391fcbcc16658a15c72648701b92900f2b3fc05fc75df2'
PY
case "$mode" in
  install) test ! -e tests/test_native_stock_rearm_gap.py; set -- ;;
  rollback) set -- -R ;;
  *) exit 2 ;;
esac
patch "$@" --batch --fuzz=0 -p1 --dry-run -i "$review_patch"
patch "$@" --batch --fuzz=0 -p1 -i "$review_patch"
if test "$mode" = install; then
  PYTHONPATH=src:tests "${R10_PYTHON:?}" -B -m unittest test_native_stock_rearm_gap -v
fi
SH
```
