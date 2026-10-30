# R0: finite Alice failure diagnostics и завершение launcher

17 октября 2026, Europe/Moscow. Работа выполнена офлайн в `/Users/notanonenough/reachy-companion`. Hardware/SSH/HTTP к устройствам, установка на Agent/Hub/PC и новый голосовой прогон не выполнялись. Старый visualization runner не изменён. Временная проверочная копия не является установленным baseline.

Результат: сохранён переносимый patch к существующему конечному сценарию, добавлено наблюдение за отказом controller в локальном launcher. Все guards, voice pipeline, camera/runtime core, конфиги, README и стенд оставлены без правок. Следующий шаг принадлежит единственному владельцу стенда.

## Исходная причина и граница вывода

Baseline receipt `actual-natural-Alice-phase-sky-controller.json` подтверждает `GuardDenied`, `stage=observe_first_true_reply_playback`, `elapsed_seconds=11.764555`, `failure_reason=OTHER`, `cleanup_error_class=GuardDenied`. Полей code/endpoint/operator elapsed/changed keys в нём нет. Восстановить точный runtime blocker по этому receipt нельзя; объявлять причиной freshness, STT либо отсутствие ответа Алисы нельзя.

В исходном controller обработчик заменяет неизвестную строку исключения на OTHER. Запись `controller.done` находится после успешного `m.cleanup`: исключение пропускает её. Исходный launcher блокируется в `subprocess.run(Hub, timeout=190)`, а controller receipt читает только после возврата. Это объясняет потерю причины и ожидание даже после завершения controller.

## Diff scope

- `scripts/companion_demo.py`: необязательный callback `stop_requested`. Finite runner использует Popen/communicate с опросом 0.1 s. При отказе controller локальный Hub SSH child завершается с ограниченным reap (terminate/2 s, kill/2 s), после чего существующий `finally` вызывает штатный guarded `finish`. Без callback сохранён прежний путь запуска.
- `deploy/patches/finite-alice-controller-failure.patch`: три целевых файла исходного `Alice-factual-resume` — `controller.py`, `controller-driver.py`, `run.py`. Это patch исходников, не архив runner и не установленная версия.
- `tests/test_demo_launcher.py`, `tests/test_finite_alice_failure.py`: только офлайн-проверки этого failure/cleanup/termination пути.
- Этот отчёт. Другие изменения/неотслеживаемые документы в рабочем дереве к R0 не относятся.

Controller сохраняет первичную причину отдельно от cleanup: `failure_reason`/`failure_code`, `operator_GET_elapsed` (точное `.elapsed`, включая null, когда guard его не предоставил), `changed_operator_keys` (только имена), `last_endpoint` текущего потока и снимок `last_endpoint_by_thread`. Отдельные `cleanup_failure` и `cleanup_guard_failures` сохраняют в том числе GuardDenied, который существующий watch cleanup поглощает внутри OFF POST. Operator values, exception text вне прежнего фиксированного allowlist, токены, owner/nonces и raw transcript не сохраняются.

Попытка controller cleanup ограничена 4 s через Linux SIGALRM в его собственном главном процессе. `CleanupBudgetExpired` наследует BaseException, чтобы внутренний `except Exception` в существующем watch не поглотил дедлайн. В любом исходе отключается timer, восстанавливается handler/IO.req, отдельно делается запись `controller.done`; неудача записи отражается `controller_done_saved=false`. Маркер сообщает независимому watch о завершении controller, а не об успешном OFF. Диагностика сохраняется в durable public receipt вместе с общим elapsed.

`cleanup_status` — verified только при всех прежних проверках OFF/admission/APLAY/factory/volume/stock; частичный результат — unverified, исключение/дедлайн — unknown. Итоговый finite terminal отдельно показывает `cleanup_verified` по ответу штатного finish и controller cleanup status. Отказ всегда остаётся неуспешным результатом сценария, даже если независимый watch потом успешно очистил ресурсы.

Существующий transport controller-driver сохраняет bounded HTTP/SSH и pin checks: его transfer limit увеличен с 56 до 60 s, общий budget с 61 до 65 s для выдачи failure receipt после cleanup. Локальный launcher прекращает ожидание потерянного driver после 72 s плюс ограниченное завершение child и штатный finish; ручной SIGINT не нужен. Это программные ограничения ожиданий, не аппаратный stop-SLA. Если связь/cleanup не подтверждены, итог остаётся UNKNOWN/false; guards не обходятся.

## Привязка patch к исходникам

Исходный каталог (только читался):

```text
/Users/notanonenough/.codex/visualizations/2026/10/10/01a12596-fe7e-7592-ae4d-27652600c257/runner-20261015/Alice-factual-resume
```

SHA-256 до / после применения patch:

| Файл | Исходный SHA-256 | Исправленный SHA-256 |
| --- | --- | --- |
| controller.py | c8e05779b4ed8e6903281ca9046cd37ae4b4284bc919d2090907098f60f852c4 | c5c521cb7f94a60dc95fa19be4a24043ff37130596ac53355f8f6561d1db97f4 |
| controller-driver.py | 2688e1749d13e919af2c11d2c13b804b53ae892d65cf992dee9fa469e4cee239 | 126147bf7fe98928fafe2405c7b1a2d3f1e7e43e71a1cc1c0f0e4af3f5108cf6 |
| run.py | 50a59b197b1b955a99d2e4c79fc48bca546827e712b0a778d402969049ffe59a | e4d0ff8e18f6cdbda7807c0a6b04c6338f467812b23f9fec20d5eea9cf839731 |
| scripts/companion_demo.py | 052b84b5ba9febb07c7b95dab81e1f5d6591c8de0cbe046fc9f61ba7dd01b376 | 9571b76942ab81e7ea9e3335944926d467480b21b9239ee596ae5077c25dc69e |

Patch SHA-256: `26000ae7dca9114915b492ec739f5dcd65b3489594b7f541c2799497954d27f9`.

Все controller/driver/launcher pins согласованы patch-ем. Watch остался `4cd31192df4b1b360d55f63348a23df9c269a8b5f097e30f190a02177ecfae03`. Pins Agent/client/helper/posthoc не ослаблялись. Driver выбирает соседний `controller.py`, а не скрытую другую копию из старого абсолютного пути.

У существующего runner остаются явные зависимости: родительский `runner-20261015` с прежними `factory_ssh.py`, `reachy-known-hosts`, `actual-bound-listening-Agent-baseline.json`; соседние неизменённые `posthoc.py`, `posthoc-driver.py`; рабочий репозиторий `/Users/notanonenough/reachy-companion` с локальным config. Полный runner/credentials в репозиторий не копировались. Patch и таблица pins позволяют следующему владельцу проверить и применить изменение без истории чужого чата; перенос всего runner в другое место этим R0 не заявляется.

## Офлайн-проверки

Выполнено **33 теста, OK, без skipped** (0.594 s):

```sh
cd /Users/notanonenough/reachy-companion
FINITE_ALICE_BASELINE=/Users/notanonenough/.codex/visualizations/2026/10/10/01a12596-fe7e-7592-ae4d-27652600c257/runner-20261015/Alice-factual-resume \
PYTHONPATH=src:tests python3 -m unittest test_demo_launcher test_finite_alice_failure -q
```

Тесты проверяют исходные три SHA-256, применяют repository patch только во временном каталоге, затем выполняют изменённый controller/runner. Без FINITE_ALICE_BASELINE десять специальных regression-тестов явно skipped: это не считается доказательством их прохождения. Постоянные launcher-тесты независимы от старого runner.

Проверены:

- Реальные ветки существующего watch IO: freshness expiry после разрешённого retry, HTTP_503, authority_changed с epoch/owner; отказ происходит до отправки запрещённого POST.
- Полный main controller на этапе `observe_first_true_reply_playback`: все три первичных GuardDenied и отдельный cleanup HTTP_409 сохраняются в stdout и durable receipt, `controller.done` записан; секретные sentinel values не экспортируются.
- GuardDenied, поглощённый OFF POST cleanup, сохраняется отдельно; частичный cleanup не становится verified. Ошибка записи done отражается честно.
- Реальный signal deadline прерывает cleanup, несмотря на его `except Exception`, восстанавливает handler/timer и передаёт завершение watch.
- Отказ/повреждённый receipt/lost driver, корректный run_id на success, согласование всех новых pins и source-only prepare без запуска процессов.
- Интеграция finite runner callback с настоящими локальными Python-процессами: failure controller останавливает спящий Hub substitute и вызывает finish без SIGINT; cleanup=false остаётся false. Отдельно проверены normal child exit, terminate→kill с ограниченным reap, прежние launcher guards и cleanup.

`git diff --check` — OK. Проверки не заменяют новый живой прогон и не устанавливают реальную причину прежнего GuardDenied.

## Передача единственному владельцу стенда

Следующая отдельная live-задача: сохранить исходные три файла, сверить таблицу SHA-256 и применить repository patch в исходном runner. Здесь эти команды **не выполнялись**:

```sh
finite_runner=/Users/notanonenough/.codex/visualizations/2026/10/10/01a12596-fe7e-7592-ae4d-27652600c257/runner-20261015/Alice-factual-resume
finite_patch=/Users/notanonenough/reachy-companion/deploy/patches/finite-alice-controller-failure.patch
patch --dry-run --batch --fuzz=0 -p1 -d "$finite_runner" < "$finite_patch"
patch --batch --fuzz=0 -p1 -d "$finite_runner" < "$finite_patch"
python3 "$finite_runner/run.py" --case sky --expected-mic 210 --expected-policy 114
```

Последняя команда — только source selfcheck, без `--execute`. До live требуется свежий read-only preflight boot/Agent PID, microphone/policy epochs, OFF/owners, worker readiness и прежнего Alice prefix. По финалу baseline ожидаются epochs 210/114; если свежие значения отличаются, владелец использует подтверждённые новые значения в аргументах, не редактирует pins/guards для обхода отказа. Boot должен соответствовать сохранённому проверенному prefix baseline; иначе остановка и отдельное выяснение.

Точная команда **одного** следующего живого прогона, если preflight подтвердил те же boot и epochs 210/114:

```sh
python3 /Users/notanonenough/.codex/visualizations/2026/10/10/01a12596-fe7e-7592-ae4d-27652600c257/runner-20261015/Alice-factual-resume/run.py --execute --case sky --expected-mic 210 --expected-policy 114
```

Сохранить свежие phase/controller/terminal/watch receipts, прежде всего `failure_code`, `operator_GET_elapsed`, `changed_operator_keys`, endpoint и отдельный cleanup status. Для приёмки реального ответа дополнительно нужны capture energy/frames, STT→worker join и ответный playback: этот R0 их измерение не добавляет. Автоматического retry, аппаратного запуска, снятия guards и постоянного listening handoff в этой задаче нет.
