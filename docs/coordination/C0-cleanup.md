# C0: актуальная точка входа

17 октября 2026, Europe/Moscow. Выполнена ограниченная правка документации
без устройств, сервисов и изменений runtime. Входы: [PROJECT](PROJECT.md),
[DELIVERY-PLAN](DELIVERY-PLAN.md), [live baseline](live-baseline-2026-10-17.md)
и [аудит](state-audit-2026-10-17.md).

## Результат

- README получил короткий актуальный статус и ссылку на [START-HERE](../START-HERE.md).
  Длинные инструкции сохранены; их исторические успехи не объявлены текущей
  сквозной приёмкой.
- START-HERE связывает полный дизайн, факты 03:17:24 MSK, установленную цепочку,
  наблюдавшееся восстановление, ограничения запуска и следующие задачи.
- [Live-demo](../autonomous-companion/live-demo.md) помечен историческим;
  unknown-camera утверждения привязаны к прежнему checkpoint и дополнены
  namespace причиной/последующим PASS. Непрерывное зрение этим не объявлено.
- [Maintenance proposal](../autonomous-companion/docker-maintenance-recovery-proposal.md)
  помечен историческим: попытка обслуживания и последующее восстановление
  отделены от прежних «не запускалось»/source GO. CREATE UNKNOWN, bookkeeping
  и disabled startup task остаются незавершёнными.

## Кандидаты последующей очистки исходников

Только два именных кандидата; **удалений сейчас нет**. Проверка ограничена
поиском точных имён через `rg` по локальному репозиторию и чтением найденных
callers/тестов и обычных START entrypoints. Private installed tasks/runner
bindings этим не проверены; отсутствие иных динамических callers не доказано.

| Кандидат | Найденные callers / зависимости | Условие удаления |
|---|---|---|
| `scripts/bootstrap.ps1` | Безусловный `throw` сразу после `param`; ниже сохранён self-relaunch и вызов bootstrap-worker. `start.ps1`/`start-worker.ps1` его не вызывают. `tests/test_windows_startup_verification.py` читает файл и проверяет denial; README, clean-PC guide и maintenance proposal сохраняют ссылки. | После фиксации рабочего baseline подтвердить отсутствие installed task/service/private runner ссылок; сохранить нужные recovery preimages, заменить исторические ссылки и пересмотреть тест denial в рамках принятого нового entrypoint. Не снимать `throw` ради оживления legacy пути. |
| `scripts/bootstrap-worker.ps1` | Безусловный `throw`; единственный найденный прямой source caller — отключённый bootstrap.ps1. `tests/test_windows_clean_pc.py` проверяет сохранённый create/enroll/start порядок, `test_windows_startup_verification.py` — denial; ссылки есть в README, clean-PC guide, Windows README и proposal. | После фиксации baseline и разрешения судьбы bootstrap.ps1 подтвердить отсутствие private/installed callers; убедиться, что нужные ownership/enrollment гарантии сохранены в выбранном пути, затем согласованно обновить зависимые тесты и ссылки. |

Это кандидаты для проверки после задачи №1, не доказанные лишние файлы.
R0 finite Alice controller/launcher и core runtime вне C0; код, patches,
receipts, конфиги и архивы не изменены и не удалены.

## Проверка

Проверена 41 локальная Markdown-ссылка в пяти изменённых/новых документах:
битых ссылок нет. `git diff --check` пройден; факты сверены с финальным live
baseline и решениями PROJECT. Основной текст README после вводного блока сохранён.
Новые тесты не написаны и тестовые/аппаратные запуски не выполнялись.
Существующие чужие изменения оставлены без вмешательства.
