# Новый Windows-ПК из Git checkout

В репозитории находятся код, Dockerfile, lock-файлы, примеры конфигурации,
профили, скрипты запуска и ручной остановки. Приватный ZIP или файлы из временного
каталога предыдущей установки не нужны. Это воспроизводимый путь для **baseline
Agent voice → Hub/router → PC STT/LM Studio/TTS** после явной настройки окружения.
Он не устанавливает автоматически Hub/Reachy, не включает микрофон/моторы и не
доказывает готовность будущего автономного companion со всеми интеграциями.

Исторические GREEN/голосовые прогоны в других документах относятся к конкретным
старым установкам. Новый ПК требует собственного native smoke ниже; локальные
unit-тесты и `/health` не заменяют проверку настоящего голоса/модели.

## 1. Подготовить ПО и checkout

Нужны Git, Python 3.11+ с `py` launcher (или явный путь к Python), PowerShell 5.1+,
Docker Desktop с Linux engine/WSL2 и LM Studio с работающим `lms`. Для CUDA-STT
нужен совместимый NVIDIA driver/GPU support Docker Desktop; для CPU выбрать
`conversation.recognition.device=cpu`, `compute_type=int8`, а GPU/контекст LLM
настроить по памяти нового ПК. Веса LM Studio, Piper и STT не входят в Git.

Официальные инструкции: [Docker Desktop Windows](https://docs.docker.com/desktop/setup/install/windows-install/),
[Docker GPU](https://docs.docker.com/desktop/features/gpu/), [LM Studio CLI](https://lmstudio.ai/docs/cli).
Сначала открыть Docker Desktop и LM Studio, проверить Linux engine, скачать в
LM Studio выбранную модель и узнать её **точный** локальный key через `lms ls --json`.

```powershell
git clone --branch codex/autonomous-shadow https://github.com/notanonymousenough/reachy-companion.git C:\Reachy\reachy-companion
Set-Location C:\Reachy\reachy-companion
git rev-parse HEAD
py -3 --version
docker info --format '{{.OSType}}'
lms --help
lms ls --json
```

Эта ветка содержит текущие stock/stop изменения; для повторяемого развёртывания
записать и использовать reviewed commit, а не предполагать, что старый `main`
содержит их. Ничего не устанавливать поверх активного чужого checkout без review.

## 2. Локальная конфигурация и общий токен

Для подключения к существующим Hub/Reachy **безопасно скопировать их существующий
общий `secrets/token`**, не его значение в чат/Git. Затем инициализировать конфиг:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
# Существующий общий secrets/token должен быть на месте ДО init.
py -3 -m reachy_companion config init
notepad .\config.local.json
```

`init` не перезаписывает существующие config/token. Для совершенно нового
комплекта он может создать токен один раз; на всех узлах должен использоваться
тот же токен. Не запускать независимую генерацию на каждом устройстве. Файлы
конфига должны быть UTF-8 без BOM; PowerShell 5.1 `Set-Content -Encoding UTF8`
добавляет BOM — использовать редактор или `.NET UTF8Encoding($false)`.

Проверить/задать следующие **локальные** значения, сохранив остальные поля:

| Поле | Что задаётся на новом ПК |
|---|---|
| `network.hub_url`, `voice_url` | Реальные адреса Hub; не оставлять несуществующие DNS-примеры. |
| `network.compute_url` | Новый PC адрес и worker port; соответствующий адрес нужен в конфиге Hub. |
| `network.agent_url`, `robot_url` | Текущие адреса робота; PC не требует прямого доступа к ним для voice routing. |
| `security.robot.hub_source_ipv4` | Точный IPv4 Hub для worker firewall. |
| `voice.mode`, `streaming.enabled` | `remote`, `true`. |
| `brains.provider` | Для этого baseline — `lm_studio`; OpenClaw/Hermes отдельно не устанавливаются. |
| `runtime.windows.model_key` | Точный скачанный key из локального `lms ls --json`. |
| `llm.model`, `runtime.windows.context_length`, `gpu` | Идентификатор обслуживаемой модели, поддерживаемый контекст/VRAM; учесть override из профиля. |
| `runtime.windows.lms_command`, `docker_desktop_path` | Реальные локальные пути, если defaults/PATH не подходят. |
| `container.desktop_llm_base_url` | Адрес LM Studio из контейнера, обычно `http://host.docker.internal:1234/v1`. |
| `container.name` | Свободное имя, не имя чужого/незарегистрированного контейнера. |
| `runtime.profile`, `runtime.git.branch` | Явный профиль и нужная ветка. Для pinned запуска ниже используется `-NoPull`. |

`runtime.profile` переопределяет llm/tts/conversation. Не копировать чужие PID,
container IDs, ownership manifests или device receipts с другого ПК. Общий токен
передаётся приватно; реальные адреса и пути заполняются локально, не в Git.
Baseline использует локальную модель, не платный API. Прочие backend env secrets
не загружаются из репозитория. Docker bind mount содержит существующий token-файл,
а Docker build исключает конфиги, токен, модели и приватные inventory.

`deployment.hub.root`, `deployment.robot.root`, `deployment.worker.root` — пути
удалённых Linux-узлов для SSH/apt/systemd, например `/home/deploy/reachy-companion`.
На Windows PC они также остаются абсолютными Linux-путями; не заменять их на
`C:\...`, UNC или путь локального checkout. Валидация не зависит от ОС оператора
и не нормализует значения: относительные пути, `.`/`..`, пробелы, управляющие и
shell/systemd-метасимволы отклоняются. Локальный Windows checkout задаётся отдельно
параметрами запуска и Docker mount. Для повторной проверки блокера Config нужен
только обновлённый `src/reachy_companion/config.py`; затем повторить read-only
`check-pc.ps1` на реальном PC. Локальный тест с Windows-семантикой путей не заменяет
этот native preflight.

## 3. Preflight, запуск и локальное enrollment

```powershell
.\scripts\windows\check-pc.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -NoPull
# Для нестандартного Python: добавить -PythonExecutable C:\Python312\python.exe
```

Preflight только читает конфиг/токен, проверяет Python, CLI и Linux engine; он не
скачивает веса, не запускает inference/службы и не выдаёт разрешений роботу.
`start.ps1` делает уже существующие LM Studio daemon/model/server + реальную
короткую completion-проверку, затем Docker build/prepare/worker. Первая загрузка
весов требует сети и времени. Ошибки загрузки/TLS устранять по источникам из
конфига, не отключая проверку сертификатов.

Worker сначала создаётся **остановленным** с новым UUID launch label. Публичный
`enroll_worker.py` проверяет full container ID, engine, image, worker command,
mount и свежие labels; записывает local ownership в единственный canonical
inventory. Источник mount отдельно сверяется с запрошенным `scope_root`, а не
принимается из inspect как собственное доказательство. Поддержаны Windows drive
paths (case/separator эквивалентность) и явные Docker Desktop mappings
`/run/desktop/mnt/host/<drive>/...`, `/host_mnt/<drive>/...`; неизвестные mappings,
traversal и несовпадающий Source отклоняются до записи inventory. Если inspect
содержит `HostConfig.Mounts`, его `/config` Source также должен совпадать.
Только после этих проверок запись сохраняется в canonical файл
`%LOCALAPPDATA%\ReachyCompanion\stop-inventory.local.json`, **до** `docker start`
по этому точному ID. Существующие независимые зарегистрированные цели сохраняются.
Busy/UNKNOWN/неизвестный inventory/другой engine не перезаписываются автоматически.
Приватный custom inventory старого kit не мигрируется и не заменяется молча.
Если manual stop появляется во время первого start, выполняется ограниченная
попытка остановки только этого exact registered ID; marker и UNKNOWN не очищаются.
Это не атомарный запрет всех сторонних Docker writers.

Повторный запуск может использовать только зарегистрированный ID с теми же
образом и hash worker-конфига. Name lookup служит лишь поиском коллизии: чужой
или старый незарегистрированный контейнер не принимается и не удаляется.
Если image/config изменились, скрипт отказывает; после review остановить прежние
owned ресурсы и выбрать новое свободное `container.name`. `rm -f` по имени нет.
Enrollment не делает shared LM Studio или все загруженные модели Reachy-owned:
их dedicated ownership пока требует отдельного доказательства/manifest записи.
Поэтому «worker зарегистрирован» не равно «stop освободит всю GPU».

Первую установку выполнять интерактивно под тем Windows user, который будет
запускать/останавливать стек. Автозапуск Task Scheduler и SSH-ветка — отдельный
проверяемый шаг после smoke; задача должна ссылаться на этот checkout/Python,
соблюдать canonical manual-stop marker и иметь собственную reviewed stop identity.
Нельзя считать стороннюю существующую задачу своей только по имени.

## 4. Native smoke на новом ПК

1. Записать commit, версии Python/Docker/lms, локальный model key и эффективные
   настройки. `check-pc.ps1` должен пройти без изменения конфига/токена.
2. Запустить baseline. Сопоставить текущий полный container ID/labels/engine и
   canonical inventory. `/health` worker должен стать ready. С Hub проверить
   доступ к `network.compute_url/health` и Bearer-защиту; на Windows разрешать
   worker port только нужному Hub. Правило создаётся существующим startup при
   запуске с требуемыми правами; Docker Desktop wide rules требуют своего review.
3. Проверить существующую Hub/router/Agent установку и общий токен. Явно включить
   микрофон оператором на короткое окно, произнести **новую живую** реплику и
   проверить STT → реальный configured model → TTS → слышимый ответ. Factory
   motion — отдельный opt-in, не требование первого audio smoke.
4. `stop-reachy.ps1 -WhatIf`: состояние ресурсов и marker не меняются. Затем
   согласованно выполнить plain stop; только зарегистрированные ресурсы должны
   остановиться, контейнеры/веса/данные сохраниться. Неподтверждённые shared
   приложения/модели сохраняются и явно не считаются освобождённой GPU.
5. Попытка обычного start при marker должна отказать. После review UNKNOWN и
   явного удаления marker повторно запустить неизменённый registered baseline;
   проверить текущий ID/health, без чужих stop/remove и без старых PC IDs.

Команды stop/resume и ownership schema: [Windows stop README](../scripts/windows/README.md).
Запуск/проверки на реальном ПК не заменяются локальными mocks. Не включать
автозапуск и не объявлять новый ПК готовым до native smoke.

## Что не разворачивается этой инструкцией

Будущий autonomous scheduler, fast/main gateway, memory/camera integrations,
lease audio peer и экспериментальные private probes не становятся постоянной
службой от `start.ps1`. Их source/runbooks есть в `docs/autonomous-companion`,
но их отдельные pinned acceptance и owner/epoch/cleanup границы сохраняются.
Текущий baseline и планируемый полный companion — разные уровни готовности.
