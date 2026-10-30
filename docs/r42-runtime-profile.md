> Локальное обновление 30 октября 2026: manifest **v11**, 34 закреплённых файла,
> включая caption initiative и экспериментальные barge helpers. Исходники сохранены;
> изменена упаковка/фиксация checkout. `hardware_acceptance=false`, без установки.
> Разделы ниже описывают исторические R42/R43, а не текущее состояние робота.
> Актуальные проверки и ограничения — [STATUS](STATUS.md).

# Runtime profile R42: recurring policy v2

Профиль `r42` включён в обычный Python-пакет как `reachy_companion.r42`.
Он содержит подготовленный Agent и автоматические вопросы по свежему кадру,
а также отдельную закреплённую копию их зависимостей и ресурсов. Runtime
не читает каталоги `R*-evidence` и не применяет патчи при запуске.

Версия 2 меняет только допуск автоматической задачи после ожидания тишины.
Живой цикл версии2 принят: самостоятельный кадр, вопрос, полное воспроизведение
и возврат к слушанию. На17октября2026 20:14:30 МСК точный R43 release активен,
расписание оставлено ON (интервал300с), микрофон и захват работают.
[Receipt](../R43-live-evidence/retention-attempt-2/terminal-summary.json).
Версия1 сохранена неактивной.
Основной `agent.py`
с диагностикой задержек сохранён без изменений: полное слияние двух Agent
отложено, поскольку R42 также зависит от предшествующих изменений захвата
и озвучивания. Выбор профиля явный, автоматического fallback нет.

## Сборка и проверка без оборудования

Из корня checkout, с установленным setuptools:

```sh
SOURCE_DATE_EPOCH=1792256374 python3 -m pip wheel \
  --no-deps --no-index --no-build-isolation --wheel-dir dist/r43-local .
python3 -m pip install --no-deps --no-index \
  dist/r43-local/reachy_companion-0.2.0-py3-none-any.whl
companion runtime-profile r42 verify
```

Последняя команда проверяет SHA256 закреплённых модулей и ресурсов; она
не читает конфиг/токен, не открывает аудио/камеру и не обращается в сеть.
Для одинакового дерева исходников и той же версии setuptools фиксированный
`SOURCE_DATE_EPOCH` позволяет повторить wheel с теми же байтами.
Wheel содержит также остальные модули текущего checkout.

## Явный выбор при разрешённом запуске на роботе

Ниже описан конфигурационный способ выбора профиля. Текущий R43 на роботе
выбран отдельным systemd drop-in с PYTHONPATH на immutable release; основной
конфиг и virtualenv не заменялись.

В конфиге робота установить:

```json
{
  "deployment": {"robot": {"agent_runtime_profile": "r42"}},
  "conversation": {"capture_pump_enabled": true}
}
```

Это фрагмент существующего конфига. Остальные поля сохраняются. Нужны
существующие streaming, mono 16 kHz и `barge_in.confirm_with_stt`, которые
проверяет Agent. Сам выбор профиля не включает микрофон и не снимает mute.

Обычные `companion install robot` и `companion update robot` формируют unit
с `agent serve --runtime-profile r42`. Без указанного поля остаётся основной
Agent. Явный запуск и управление на самом роботе:

```sh
companion --config /home/pollen/reachy-companion/config.local.json \
  agent serve --runtime-profile r42
companion --config /home/pollen/reachy-companion/config.local.json \
  initiative auto-status --runtime-profile r42
companion --config /home/pollen/reachy-companion/config.local.json \
  initiative auto-on --runtime-profile r42
companion --config /home/pollen/reachy-companion/config.local.json \
  initiative auto-off --runtime-profile r42
```

`serve` занимает процесс Agent; его запускают через существующий systemd
unit, либо отдельно от команд управления. Не запускайте второй Agent рядом
с работающей службой. CLI управления использует authenticated loopback HTTP
и текущие boot/mic/policy/owner/generation, без переноса токена в аргументы.
Команды `status`, `arm`, `off` управляют прежним once-per-arm сценарием.

При каждом старте автоматический schedule **OFF**. `auto-on` допускается
только при обычном прослушивании, без чужого владельца и отложенного ответа.
Расписание ждёт полного свободного окна: обычный foreground закончен,
нет отложенной записи/реплики, собственный звук и его хвост завершены,
свежий capture подтверждает 3 секунды тишины. До этого дочерней задачи нет,
поэтому ожидание разговора не расходует её срок. Только при допуске создаётся
новая задача со сроком до 60 секунд. Между завершёнными попытками — не меньше 300 секунд.
STOP, mute, privacy, смена boot/epoch/owner или ошибка отзывают schedule;
старые задачи сами не восстанавливаются. Эти свойства проверены локальными
тестами, но ещё не приняты живым тестом на роботе.

## Зависимости и границы поставки

`manifest.json` внутри профиля закрепляет Agent, initiative, capture pump,
snapshot, player, вспомогательные модули и JSON/лицензионные ресурсы.
Emotion assets загружаются из собственного пакета профиля. Agent, capture pump,
snapshot и player сохраняют закреплённые версии R42; версия 2 изменяет
жизненный цикл recurring policy в initiative. Новых моделей или пакетов
профиль не скачивает. Предыдущий wheel хранится отдельно в `dist/r42-local`.

На роботе остаются внешние prerequisites: robot extra
`webrtcvad-wheels==2.0.14.post1`, ALSA, существующий factory interpreter
`/venvs/mini_daemon/bin/python` с Reachy Mini SDK 1.11.0, numpy/GStreamer,
камера, локальный voice worker и выбранная модель LM Studio. Проверка wheel
не подтверждает работоспособность этих устройств и служб. Диагностика
основного Agent не подмешивается в замороженный R42 Agent.

Для фактического deployment ещё нужны штатное разрешение выполнения,
один hardware owner, проверка текущего baseline, остановка/reap старого Agent,
проверка нового boot/default-OFF, свежий MIC grant при допустимой authority,
один живой тест и готовый откат. Старые двухфайловые скрипты R42 нельзя
использовать как installer этого wheel: профиль имеет отдельный namespace
и полный набор файлов. При возврате к основному Agent следует вернуть
`agent_runtime_profile` в `default` и применить unit в разрешённом окне;
это не заменяет восстановление точного прежнего runtime при необходимости.
