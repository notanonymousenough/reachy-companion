# Reachy Companion

Русскоязычный компаньон для Reachy Mini Wireless: голос, камера, штатные движения,
оперативный контекст и экспериментальная инициатива. Вычисления выполняются на PC,
Hub маршрутизирует запросы, Robot владеет аудио и движениями.

```text
Robot Agent (ALSA / VAD / playback / factory motion)
    ↕ Hub / router
PC worker (Whisper → локальная LM Studio → Piper / SoX)
```

## Состояние проекта

**Локальный срез: 30 октября 2026.** Код и тесты приведены к переносимому checkout.
Это не установка на устройства и не новая аппаратная приёмка.

- Обычный голос и отдельные camera → model → spoken response проходы подтверждены
  историческими проверками. Последний продуктовый журнал 25 октября оставляет
  shared visual mode экспериментальным: точность, связанное уточнение и смена сцены
  ещё не приняты.
- Streaming, непрерывный слух, AEC/barge-in, длительная автономная работа и
  восстановление всего комплекса остаются незавершёнными.
- Основной Agent и явный профиль `r42` сохранены. R42 manifest v11 закрепляет
  полный локальный пакет; он не описывает установленную версию робота.
- Конфиги установки и секреты остаются локальными. Исторические эксперименты и
  rollback-материалы вынесены из рабочей папки в резервный архив.

Актуальные границы и результаты проверок: [статус](docs/STATUS.md).
Полный продуктовый scope: [требования](docs/coordination/REQUIREMENTS.md).
История последних аппаратных результатов: [PROJECT](docs/coordination/PROJECT.md);
даты внутри этого журнала относятся к прошлым проверкам.

## Локальная разработка без устройств

Требуется Python **3.13** для воспроизводимого тестового окружения; пакет поддерживает
Python ≥3.11. Системный Python macOS 3.9 для этого проекта не подходит.

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements/dev.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m reachy_companion runtime-profile r42 verify
.venv/bin/python -m build --no-isolation
```

Если используется `uv`, создание окружения: `uv venv --python 3.13 .venv`,
установка зависимостей: `uv pip sync requirements/dev.lock`, затем
`uv pip install --no-deps -e .`.

Тесты используют синтетические данные, временные каталоги и локальные HTTP-серверы.
Они не требуют SSH, живого робота, GPU, Whisper/Piper или LM Studio.
Аппаратные проверки из `tests/live/` автоматически не запускаются.
Исторические regression fixtures находятся в `tests/fixtures/legacy/`,
а не в персональных каталогах оператора.
Нужен полный Git checkout: часть тестов исторических overlays читает закреплённые
версии через локальный `git show`. Для shallow clone сначала выполните
`git fetch --unshallow`; CI сразу получает полную историю.

## Структура

| Каталог | Назначение |
|---|---|
| `src/reachy_companion/` | Основной Agent, Hub, router, worker, CLI |
| `src/reachy_companion/r42/` | Явный самостоятельный профиль с закреплёнными зависимостями |
| `src/reachy_companion/autonomous/` | Scheduler, контракты, адаптеры и автономные сессии |
| `tests/` | Локальные regression и интеграционные проверки |
| `deploy/`, `scripts/`, `native/`, `worker/` | Установка, исторические overlays, native helpers и Docker |
| `requirements/` | Отдельные lock-файлы разработки и устройств |
| `docs/` | Текущий статус, инструкции и датированная история |
| `profiles/`, `scenarios/` | Persona и штатные сценарии |

## Установка и управление

Для разработки не выполняйте deploy, install, bootstrap или служебные команды:
они могут менять устройства. Существующие установки используют собственные
immutable releases и конфиги; checkout не считается их установленной версией.

- [Топология router / worker](docs/router-architecture.md)
- [Профиль R42](docs/r42-runtime-profile.md)
- [Локальный доступ и firewall](docs/local-security.md)
- [Windows: ограничения startup и восстановления](docs/windows-clean-pc.md)
- [Исторические подробные инструкции](docs/history/README-before-2026-10-30.md)
- [Очистка, резервная копия и восстановление](docs/cleanup-2026-10-30.md)
