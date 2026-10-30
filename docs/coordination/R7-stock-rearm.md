# R7 — stock rearm: один воспроизводимый authority gap

17 октября 2026, Europe/Moscow. **OFFLINE: physical rearm не включён.** Найден контрпример на exact A1 Agent/pump: legacy manual `/say` или `/ask` допускает listening clear→resume **до** своего pump retire. В этом окне полный свежий same-authority/same-source receipt проходит существующий native observer. Следовательно, доказательство всех допустимых pause/manual interleavings отсутствует; R5 permanent physical closure остаётся обязательным. Работа закончена на разрешённой ветке «один воспроизводимый server/API gap», а не на implementation rearm.

Изменены только один целевой test и этот отчёт. Native runtime/stock admission, Agent/server epochs/audio/camera/worker/shared client не изменялись. SSH/HTTP/deploy/model/hardware не использовались; устройства принадлежат S3, frozen evidence Q3 не менялись. Чаты и подагенты не создавались. Чужие изменения checkout сохранены. Live PASS и продолжительное движение не заявляются.

## Exact source и допустимая модель

Входы: [R5](R5-observer-recovery.md), [R4](R4-authority-epoch-contract.md), [R6](R6-observer-native-live.md), exact builder `deploy/autonomous/prepare_continuous_capture.py`. Builder восстановил всю hash-checked цепочку historical Git preimages/patches, не HEAD Agent. Exact bytes сохранены в [exact-A1](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147e8-3beb-79b2-b915-28b1541b4aba/R7-evidence/exact-A1/manifest.json).

| Source | SHA256 |
| --- | --- |
| Exact A1 Agent | `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b` |
| Exact A1 capture pump | `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6` |
| Agent builder input | `4e2dcafdde29ba667ae40c240723954d48b8462f9641e50ffb32e56fe0ce575a` |
| Pump builder input | `b7b1ffa551d8b3ad4346cc2920f0e17d04e37c2300d8583abf336ea90fb9e5b0` |

Модель — единственный штатный Agent и его capture owner; существующие authenticated concurrent API requests через `ThreadingHTTPServer` (exact Agent:20,1221), обычный reader thread, без произвольной записи private state/второго writer. `/resume` с пустым binding разрешён Handler:1170–1176 и `set_listening`; для него нет требования phase=paused/capture=false. Source не задаёт максимального времени, за которое другой request thread обязан дойти от clear до retire. Поэтому рассмотренный instruction-boundary interleaving допустим без нового owner или API.

R4 durable STOP/privacy/quiet/owner epoch result переиспользован. Его semantic listening gap сужен по actual pump source, а не по client equality:

| Путь | Exact A1 source boundary | Результат |
| --- | --- | --- |
| `/pause`, bound или `{}` | `set_listening`:1040–1054: clear и `retired.set()` внутри microphone→policy locks; close после locks. `status`/`operator_status`:278–319 берут microphone lock. | Resume до pause означает последующий clear/retire; resume после locked mutation не снимает retire; read между clear и retire не проходит тот же lock. R5 exact pause/restart test переиспользован без изменения: новый active pump generation2 отвергается terminal. |
| Bound manual `/say` | `manual`:1074–1083 требует paused/capture=false/listening=false, затем `set_listening(False, ..., require_paused=True)` повторно проверяет binding под обоими locks. | Сам mutator оставляет тот же retire fence. Это не доказательство legacy branch. |
| Legacy manual `/say` и `/ask` | `manual`:1084–1089: was_listening → **bare clear вне authority locks** → load pump → `_capture_retire()` → close. | **FAIL:** concurrent legacy resume и полный read могут закончиться после clear, но до retire. Это единственный найденный gap, на котором работа остановлена. |

`_capture_get`:375–386 увеличивает generation при создании replacement; retired Event прежнего pump не очищается. Эти свойства ловят уже retired/replaced source, но не устраняют окно **до** retire в legacy manual. Полный universal proof опровергнут одним допустимым interleaving; остальные варианты не объявлены доказанными по одному pause test.

## Конкретный воспроизводимый trace

Добавлен [test_legacy_manual_resume_can_recover_same_source_before_pending_retire](/Users/notanonenough/reachy-companion/tests/test_continuous_capture.py:361), два subcases `/say` и `/ask`. Используются actual reconstructed `Agent.manual`, `set_listening`, `operator_status`, `status`, actual A1 pump и existing deterministic subprocess PCM writer. Application methods не переписаны/не AST-extracted. Fixture `Event.clear` gate останавливает manual сразу после actual clear; отдельный policy-snapshot gate паркует reader на первом binding check после capture_active=true, вне pump condition. После resume он продолжает actual check через real policy RLock; короткий false ему не подставляется. После actual resume lock освобождён, reader продолжает читать **до** recovery. Gate моделирует scheduling boundary, не задержку HTTP/PCM. Hub proxy в тесте — in-process exact operator projection, hardware guards не симулируются как live success.

1. Начало: boot=fixture, mic1, policy3, оба owners=null, expression1, listening/capture=true, pump generation1/retired=false. Native stock opt-in до gap допускает admission.
2. Observer gap увеличивает только local observation generation 0→1, оставляя старые решения invalidated по R5.
3. Actual legacy manual снимает listening и останавливается перед чтением `_capture_pump`/retire. Epochs/owner/pump generation пока прежние.
4. Actual `set_listening(True,{})` завершается; reader с тем же pump читает реальные pipe bytes. Затем actual native chain `/operator` → `/status` → proxy `/control/operator` возвращает полный typed fresh receipt; counters без регрессии, turns0, listening/capture=true, retired=false, source_generation1, вся operator projection равна исходной.
5. Native consume восстанавливает FRESH, recoveries1, local generation1, withdrawn=null. **Physical admission остаётся false только благодаря сохранённому R5 `physical_closed_after_gap=true`** (opt-in=true, motor=true, slot unused, receipt свежий).
6. Release manual: actual `_capture_retire`/close делает pump retired и capture=false. Занятый fixture audio_lock даёт штатный отказ до voice; lock-failure branch восстанавливает listening=true. Voice/model/POST calls этого boundary test:0.

В обоих subcases actual PCM `read_bytes 0→960`, frames `0→480`, calls `0→1`, gap_events/overflow0. Полные fixture BEGIN/operator/counters и final state: [authority-gap-receipts.json](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147e8-3beb-79b2-b915-28b1541b4aba/R7-evidence/authority-gap-receipts.json). BEGIN — исходный `time.monotonic`, без widening/backdate; recovery остаётся внутри прежних300ms.

Это counterexample для вывода «fresh same source доказывает отсутствие скрытой listening withdrawal», не демонстрация live движения. Server может задержать manual перед retire дольше fixture gate: в status/API нет pending-manual fence или bound, который обязывает retire завершиться до следующего actual model decision. Даже новый decision с новым local binding/deadline и повторный свежий read могут попасть в то же окно. Fresh Hub boot/free/known/unowned/expression guard не сообщает о pending Agent manual. R5 запрет поэтому не снят; ни старый proposal, ни single-use slot не восстанавливались.

## Изменения, hashes и проверки

Git HEAD: `59bc59a6433dee432371319ba48ad0aeab0985f4`. Native/test inputs были untracked; base — exact R5 bytes, а не diff к HEAD. [Manifest](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147e8-3beb-79b2-b915-28b1541b4aba/R7-evidence/source-manifest.json) содержит base/output hashes11 файлов и exact A1 pins.

| Файл | Base SHA256 | Output SHA256 |
| --- | --- | --- |
| `tests/test_continuous_capture.py` | `2d4c80c0b641e3f2168dafd2cbcfe82845ebc94434dbf09dc6f35bc9e9ebc3fb` | `1a5a92de66699738eecd38d62c274a65386e38543c58765c1997c15efc4f95f8` |
| `autonomous/native_agent.py` | `c8fb477feffaaf86f5e5e339ed015d9d38a304769552d3d8ed6da6d2f668c615` | unchanged |
| `autonomous/native_agent_session.py` | `3931c0e4f90ca1ffc2911eebc59820ca77b6b8b60e06c527f115f9cd774ef2b0` | unchanged |

[manual-retire-boundary.patch](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147e8-3beb-79b2-b915-28b1541b4aba/R7-evidence/manual-retire-boundary.patch) SHA256 `d3cf54ea241bfab7f50b667f20ff8a2823c27fdf6521ee459afad6684eed7eb4`. Code patch содержит только один test-file (+116 lines); этот отчёт отдельно. Exact `preimages/` и `payload/` сохранены. Dry-run/apply/reverse exit0/0/0 на отдельной временной копии, output/base hashes совпали: [patch-check.json](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147e8-3beb-79b2-b915-28b1541b4aba/R7-evidence/patch-check.json).

**25/25 offline tests PASS,2.918s**, включая23 существующих native tests, прежний exact pause test и новый boundary test (2subcases). [Log](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147e8-3beb-79b2-b915-28b1541b4aba/R7-evidence/offline-tests.txt), [runner с экспортом fixture receipts](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147e8-3beb-79b2-b915-28b1541b4aba/R7-evidence/run_offline.py). Existing venv, dependencies не устанавливались.

```sh
PYTHONPATH=src:tests /private/tmp/reachy-head-validate-20261015/bin/python -B -m unittest \
  test_native_agent_session \
  test_continuous_capture.ContinuousCaptureTests.test_same_epoch_pause_retires_and_restart_uses_new_generation \
  test_continuous_capture.ContinuousCaptureTests.test_legacy_manual_resume_can_recover_same_source_before_pending_retire -v
```

Существующие regressions подтверждают reject old fast после recovery, original receipt deadline, gap после guarded reread до socket send →0POST с used=true/no replay, sent+lost response →1POST/UNKNOWN/terminal, terminal STOP/privacy/source/counter fences, finite unavailable cleanup. Положительный «новый model stock после gap» не заявлен: rearm намеренно не реализован. No idle slot reset, retry0,300ms и preconnect/reread/header/body/partial-send barriers остаются exact R5. Context/camera recovery остаются закрытыми.

## Одна минимальная следующая правка / deployment gate / rollback

**Единственная следующая server-правка:** в legacy `Agent.manual` заменить последовательность bare `listening.clear()` → late `_capture_retire()` → close на уже существующий `self.set_listening(False, {})`, сохранив was_listening и прежний restoration path. Тогда clear+`retired.set()` выполняются в одной microphone→policy critical section; close остаётся вне locks. Это закрывает именно показанное окно: resume после clear увидит уже retired pump; replacement даст новую generation. Agent/server patch здесь **не вносился**, поскольку вне scope R7; epoch change для исправления этого окна не требуется.

Следующий finite шаг — эта одна source-правка на exact A1 с новым hash pin и тот же bounded boundary test, у которого recovery внутри окна должен стать невозможен (terminal retired/capture/source rejection). Затем требуется завершить конкретное source proof pause/manual boundary перед rearm. Нельзя просто удалить новый test, расширить300ms, очистить slot либо включить native flag.

**Deployment R7 physical ветки не разрешён результатом:** portable patch test-only, выкладывать runtime на устройства нечего. S3 не получает команды hardware/model запуска из этого gap report. Вместо фиктивной finite live команды оставлен воспроизводимый finite offline вызов выше. Live physical deployment/rollback определяется после server fix/proof, не текущими historical R6 bindings.

Rollback локального/staged R7 test patch: при совпадении output SHA применить `patch -R -p1 -i <absolute manual-retire-boundary.patch>` и проверить base SHA из таблицы. Существующий R5 native runtime и installed Agent/Hub этим rollback не меняются; production rollback не требуется.
