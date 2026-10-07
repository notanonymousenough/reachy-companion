# Reachy Companion

> **Живая установка переведена на новую архитектуру:** hub только маршрутизирует, STT/TTS работают в Docker на Windows ПК, LLM — в LM Studio. Включены `voice.mode=remote` и `streaming.enabled=true`; проверены ответ через динамик Reachy и полный STT → LLM → поток PCM через хаб. Инструкция с нуля: [маршрутизатор и worker](docs/router-architecture.md).


Русскоязычный голосовой компаньон для Reachy Mini Wireless. Робот слушает через собственный микрофон и отвечает через динамик голосом обычного молодого парня. Ричи — язвительный приятель: говорит прямо, умеет подколоть и не избегает неудобных разговоров. Текущая архитектура: Raspberry Pi 3B+ (reachy-hub) маршрутизирует запросы и допустимые движения; STT/TTS и бесплатная локальная модель LM Studio работают на ПК с RTX 5070. Первый этап с local voice на хабе и команды перехода сохранены в истории установки; текущий режим описан ниже.

```text
Mac ── HTTP / SSH ── reachy-hub ── REST / SSH ── Reachy Mini
                         │                          │
                         │                          └─ ALSA: микрофон, VAD, динамик
                         └─ Windows Docker worker: Vosk → LM Studio → Piper + SoX
                                  └─ поток PCM через hub обратно в Reachy
```

Входящие подключения к Reachy разрешены только с адреса хаба. Mac управляет роботом через хаб, включая SSH. Это фильтрация источника IP в общей LAN, а не изоляция VLAN: доверие распространяется на хаб и на его адрес. Исходящий доступ робота, ответы на исходящие соединения, loopback, DHCP и необходимые сообщения IPv6 остаются доступны. Другие устройства не могут начать SSH/HTTP-подключение к роботу через IPv4 или IPv6. Уже открытые соединения сохраняются до закрытия.

## Что находится в репозитории

| Файл | Назначение |
|---|---|
| `config.example.json` | Полная схема с переносимыми именами устройств и настройками |
| `config.local.json` | Реальные адреса и настройки данной установки; существует локально, исключён из Git |
| `secrets/token` | Общий Bearer-токен, права 600; исключён из Git |
| `src/reachy_companion/hub.py` | REST-шлюз к daemon, мониторинг, wake/sleep/hello |
| `src/reachy_companion/voice.py` | Worker на ПК: Vosk → текстовый backend → Piper/SoX, история и streaming |
| `src/reachy_companion/router.py` | Hub: маршрутизация без inference и без буферизации полного ответа |
| `src/reachy_companion/brains.py` | Адаптеры LM Studio / OpenClaw / Hermes Agent |
| `worker/Dockerfile`, `scripts/worker-docker` | Запуск вычислений на ПК |
| `src/reachy_companion/agent.py` | Захват речи, VAD, проигрывание, pause/resume |
| `src/reachy_companion/firewall.py` | nftables, постоянная служба и отложенный откат |
| `src/reachy_companion/deployment.py` | SSH через хаб, копирование, установка, systemd, модели |
| `scenarios/hello.json` | Небольшое приветственное движение антеннами |
| `requirements/*.lock` | Версии реально использованных Python-зависимостей |
| `docs/installation-history.md` | Первичная установка, изменения голоса и миграция |
| `tests/test_companion.py` | Проверки конфига, маршрутизации, firewall и шаблона LLM |

В исходниках нет адресов этой LAN, имён установленных моделей или пути к рабочему каталогу конкретного устройства. Параметры находятся в JSON. Модельные веса, аудиозаписи, логи и виртуальные окружения в Git не попадают.

## Настройка с нуля

### 1. Устройства и LM Studio

1. Собрать и подключить Wireless к Wi-Fi по [официальной инструкции Reachy](https://huggingface.co/docs/reachy_mini/platforms/reachy_mini/get_started). USB к хабу не нужен. Существующий daemon должен работать и иметь REST API. Проверенная установленная версия — 1.11.0.
2. На хабе установить Debian 13 arm64, обеспечить SSH для пользователя из `deployment.hub.user` и sudo для установки. Проверенная система: Python 3.13.5, Raspberry Pi 3B+, около 905 MiB RAM.
3. На ПК загрузить модель из `llm.model` в LM Studio, запустить OpenAI-совместимый сервер с доступом из LAN. Указать его адрес, порт и суффикс `/v1` в `network.llm_base_url`. У модели должен работать raw endpoint `/completions`.
4. Закрепить адреса хаба, робота и ПК в DHCP маршрутизатора. Для firewall важен именно IPv4, с которого хаб обращается к роботу: `security.robot.hub_source_ipv4`.
5. Проверить SSH к хабу. Wireless предоставляет пользователя `pollen` и заводской пароль `root`, согласно официальной инструкции выше. Пароль нигде в проекте не сохраняется; SSH спросит его интерактивно. Для обычной эксплуатации можно добавить свой публичный SSH-ключ.

### 2. Локальная конфигурация на Mac

```sh
cd /path/to/reachy-companion
./scripts/companion config init
# Отредактировать config.local.json в любом редакторе.
./scripts/companion config validate
```

В уже подготовленной локальной копии `config.local.json` и общий токен созданы: повторять `init` не нужно. Команда init отказывается перезаписывать существующий конфиг. Новый клон требует настройки адресов вручную; Git их не содержит.

Заполнить `network`, `deployment.*.host/user/root` и `security.robot.hub_source_ipv4`. Пути `paths.*` и `models.*.path` разрешаются относительно файла конфигурации; удалённые каталоги установки задаются в `deployment`. `identity_file` пустой означает обычный выбор SSH-ключа/OpenSSH agent. Для нестандартного ключа хаба при ProxyJump можно задать Host в `~/.ssh/config`: параметры `-i` целевого робота не заменяют конфигурацию jump-host.

### 3. Проверка сети

```sh
./scripts/companion ssh hub -- hostname
./scripts/companion ssh robot -- hostname
LLM_URL=$(./scripts/companion config value network.llm_base_url)
./scripts/companion ssh hub -- curl --fail --max-time 10 "$LLM_URL/models"
```

`ssh robot` всегда использует `ssh -J` через хаб. Если DNS `.lan` не работает, вписать IP в локальный конфиг. Worker должен быть доступен с хаба по `network.compute_url`; LM Studio должна быть доступна из контейнера worker. PowerShell использует `container.desktop_llm_base_url` (host.docker.internal). Адрес виртуального адаптера ПК не подходит для входящих LAN-запросов.

### 4. Установка

Для новой архитектуры сначала запустить worker на ПК по [инструкции](docs/router-architecture.md), проверить health с хаба, затем установить режим remote. Следующие команды устанавливают hub/robot; вычислительный worker устанавливается отдельно.

```sh
./scripts/companion deploy both --dry-run
./scripts/companion deploy hub
./scripts/companion deploy robot
```

Deploy копирует код, сценарии, зависимости, конфиг и токен. На устройстве выполняется `sudo ./scripts/companion install ROLE`. SSH и sudo могут запросить пароль. Требуются Python 3.11+ на Mac и устройствах, сетевой доступ к apt/PyPI/Hugging Face при первой установке.

Проверенные lock-файлы собраны на Debian 13 / Python 3.13 arm64; на другой версии Python доступность всех закреплённых wheel нужно проверить.

Команды установщика:

```sh
# На соответствующем устройстве, в deployment.ROLE.root:
sudo ./scripts/companion install hub
# либо
sudo ./scripts/companion install robot
```

Он выполняет `apt-get update`, `apt-get install -y` пакетов из `deployment.ROLE.apt_packages`, `python3 -m venv` по `venv_dir`, `pip install -r requirements/ROLE.lock`, `pip install --no-deps .`. На worker (или на хабе только при явном legacy `voice.mode=local`) скачивает Vosk ZIP и Piper ONNX + JSON по URL из конфига; распаковывает с проверкой путей. Необязательные SHA256 задаются в `models.*.sha256`; пустые значения означают загрузку без закреплённой контрольной суммы. Затем создаёт data, назначает владельца, генерирует systemd units, выполняет daemon-reload, enable и restart. Код unit-файлов формируется в `deployment.service_unit`; все имена служб задаются в JSON.

На хабе запускаются `reachy-hub` и `reachy-voice`; на роботе — `reachy-voice-agent`. Службы выполняются от пользователей из конфига, с отдельными venv, автоперезапуском, закрытыми правами создаваемых файлов и ограничением записи каталогом data. В режиме remote хаб использует только stdlib router; CPU-потоки ONNX используются worker на ПК и задаются конфигом. Factory daemon, его Python-окружение и `.asoundrc` не заменяются.

На роботе установщик также включает firewall, если `restrict_to_hub=true`. **После установки автоматически запущен таймер отката.** Пока он не истёк, открыть новое соединение и проверить:

```sh
./scripts/companion ssh robot -- hostname
./scripts/companion hub status
./scripts/companion voice status
# Только после успешных проверок:
ROBOT_ROOT=$(./scripts/companion config value deployment.robot.root)
./scripts/companion ssh robot -- sudo "$ROBOT_ROOT/scripts/companion" firewall confirm
```

Если путь через хаб не работает, ничего не подтверждать: через `rollback_seconds` правило удалится и firewall-служба отключится. Повторная установка также перезапускает firewall-службу под защитой нового таймера отката.

### 5. Разговор и управление

```sh
./scripts/companion voice status
./scripts/companion voice pause
./scripts/companion voice resume
./scripts/companion voice reset
./scripts/companion voice ask 'Почему небо голубое?'
./scripts/companion voice say 'Привет! Я твой маленький компаньон.'
./scripts/companion hub hello
./scripts/companion hub wake
./scripts/companion hub sleep
```

При запуске агент будит робота, приветствует и слушает, если это разрешено в `conversation`. Для сна сначала поставить разговор на паузу; sleep управляет моторами, pause управляет прослушиванием. Произнесённые точные фразы «забудь разговор», «начни новый разговор», «сбрось разговор» очищают историю. «Перестань слушать», «не слушай», «выключи микрофон» ставят прослушивание на паузу после ответа; возобновление — командой CLI.

## Конфиг и голос

| Раздел | Что менять |
|---|---|
| `network` | URL хаба, голосовой службы, агента, daemon, LM Studio, compute worker |
| `voice.mode` | remote: маршрутизатор; local: явная совместимость с первым этапом |
| `brains`, `streaming`, `container` | Backend текста, параметры PCM-потока и Docker worker |
| `servers` | Bind-адреса и порты трёх HTTP-серверов |
| `deployment` | SSH hosts/users/keys, root, venv, apt-пакеты, имена units |
| `security.robot` | Разрешённые адреса хаба, имя таблицы/службы, DHCP, таймер |
| `models` | Пути, URL скачивания, SHA256, имя корня Vosk ZIP |
| `llm` | Модель, endpoint, шаблон, stop tokens, температура, лимит, persona, история |
| `tts` | Pitch и параметры синтеза Piper |
| `audio` | ALSA устройства, VAD, калибровка, тишина, длительность фразы |
| `conversation` | Приветствие, автозапуск, session, команды reset/pause |
| `motion` | Поллинг, допустимые движения антенн, длительности шагов |
| `timeouts`, `limits`, `logging`, `paths` | Таймауты, размеры запросов, журналы и каталоги |

Текущий голос — Piper Ruslan medium, поднятый SoX на 150 cents (1,5 полутона). `volume=0.65`, `length_scale=1.0`, `noise_scale=0.35`, `noise_w_scale=0.65`, нормализация включена. Это настройка для обычного молодого мужского тембра; субъективное звучание оценивается по аудиопробе. Чтобы сделать его взрослее, уменьшить `tts.pitch_cents`; темп регулируется `length_scale` (больше — медленнее). Новую модель менять вместе с её ONNX JSON. [Карточка Ruslan](https://huggingface.co/rhasspy/piper-voices/blob/main/ru/ru_RU/ruslan/medium/MODEL_CARD) указывает русский голос 22 050 Hz и лицензию корпуса CC BY-NC-SA 4.0; учитывать условия при дальнейшем использовании.

Persona задаётся в `llm.system_prompt`: маленький любознательный компаньон, короткие точные ответы по-русски, дружелюбный тон без сюсюканья. Голос и persona — отдельные настройки.

### Быстрые ответы без reasoning

В живом тесте `chat_template_kwargs.enable_thinking=false` не отключал reasoning у загруженной Qwen. Используем `/v1/completions` и явный Qwen-шаблон: каждое сообщение обёрнуто в `<|im_start|>…<|im_end|>`, assistant_prefix заканчивается пустым закрытым `<think>`. Модель начинает сразу ответ. Параметры шаблона и stop находятся в JSON, включая имя модели. Это модельно-зависимый способ: при смене LLM нужно проверить шаблон. Сейчас поддержан режим raw completion; `llm.mode` должен быть `completion`.

При первичной настройке короткий LLM-запрос без reasoning занял около 0,62 s против примерно 18 s с reasoning. Это замер конкретной реплики, не гарантия задержки. Полный проверочный путь STT → LLM → TTS на Pi 3B+ занял около 15,56 s для развёрнутого ответа; после генерации WAV ещё нужно проиграть его.

## Что сделано на Reachy

Добавлены отдельный агент, venv с `webrtcvad-wheels`, systemd-служба и nftables. Используются уже существующие shared ALSA устройства `plug:reachymini_audio_src` и `plug:reachymini_audio_sink`; настройки dmix/dsnoop и daemon сохранены. Захват — mono S16_LE 16 kHz, chunks 100 ms, VAD по 20 ms. Начальная калибровка шума задаёт порог `max(rms_floor, median(noise) * noise_multiplier)`. После паузы около 1 секунды записанная фраза отправляется через хаб на worker. Ответ возвращается как NDJSON с PCM S16_LE mono 16 kHz и проигрывается одним aplay; временный полный WAV не нужен. В legacy-режиме без streaming сохраняется WAV API.

Микрофон освобождается перед обработкой/ответом, чтобы робот не разговаривал сам с собой. Аудио передаётся внутри LAN, сырые записи на диск не сохраняются. По умолчанию распознанные фразы и ответы попадают в логи; `logging.log_transcripts=false` отключает запись текста.

Движение hello проходит проверку состояния daemon, режима моторов, занятости приложением и текущего движения. Ограничены углы и длительности шагов, проверяется достижение цели, антенны возвращаются в исходную позицию. Это не резервирует SDK-lock на всё время сценария: конкурирующие приложения по-прежнему требуют координации. LLM не управляет моторами или камерой.

## Firewall и доступ только через хаб

Используется собственная `inet`-таблица nftables из `security.robot.nft_table`, input policy drop. Существующие таблицы не очищаются. Разрешены loopback, established/related, IPv4 хаба, явно перечисленные IPv6 хаба; DHCP и служебный ICMPv6. IPv6 приложения не имеют общего разрешения. Allow-list IPv4 должен совпадать с фактическим source IP хаба.

На роботе доступны команды:

```sh
sudo ./scripts/companion firewall render
sudo ./scripts/companion firewall arm
sudo ./scripts/companion firewall apply
# С Mac проверить НОВОЕ ssh robot и hub status, затем на роботе:
sudo ./scripts/companion firewall confirm
# Снять ограничение и отключить восстановление при загрузке:
sudo systemctl disable --now reachy-companion-firewall.service
```

`firewall install` создаёт и включает отдельный systemd unit, перед этим запускает rollback timer. При загрузке unit упорядочен перед network-pre.target, чтобы применить правило до настройки сети. Изменённые правила сначала проверяются `nft --check`, затем заменяются одной транзакцией; меняется только собственная таблица. При изменении адреса хаба сначала arm, затем apply; подтвердить с нового разрешённого адреса. Откат снимает эту таблицу целиком, включая предыдущее ограничение.

Reachy Mini Control на Mac больше не сможет напрямую найти/управлять закрытым роботом. Для ручного просмотра REST UI можно открыть SSH-туннель через хаб:

```sh
HUB_HOST=$(./scripts/companion config value deployment.hub.host)
HUB_USER=$(./scripts/companion config value deployment.hub.user)
ROBOT_HOST=$(./scripts/companion config value deployment.robot.host)
ROBOT_PORT=$(python3 -c 'import json, urllib.parse; c=json.load(open("config.local.json")); print(urllib.parse.urlsplit(c["network"]["robot_url"]).port)')
ssh -L "18000:$ROBOT_HOST:$ROBOT_PORT" "$HUB_USER@$HUB_HOST"
# В браузере: http://localhost:18000/docs
```

Ограничение не закрывает хаб от LAN. Команды и голосовые endpoints защищены общим Bearer-токеном; `/health` и статус базового hub доступны без токена. HTTP в доверенной LAN не шифрует данные; SSH управление шифруется.

## API

| Служба | Endpoint |
|---|---|
| hub | GET `/health`, `/status`; POST `/actions/hello`, `/actions/wake`, `/actions/sleep` |
| voice | GET `/health`, `/status`; POST `/turn`, `/text`, `/say`, `/reset`, `/pause`, `/resume` |
| voice, для оператора | POST `/robot/ask`, `/robot/say` — прокси к агенту, ответ произносится роботом |
| agent, только через хаб | GET `/status`; POST `/pause`, `/resume`, `/ask`, `/say` |

`/turn` принимает JSON `pcm_base64` (mono S16_LE, 16 kHz) и `session`, возвращает `transcript`, `reply`, WAV `audio_base64`, `elapsed_seconds`, необязательную команду pause. `/text` получает текст и генерирует ответ с WAV; `/say` только синтезирует заданный текст. `/robot/*` играет его на роботе. Bearer читается из файла token; альтернативно `REACHY_COMPANION_TOKEN`. Для другого конфига — `--config PATH` или `REACHY_COMPANION_CONFIG`.

## Диагностика, обновление и ограничения

```sh
./scripts/companion ssh hub -- systemctl status reachy-hub reachy-voice --no-pager
./scripts/companion ssh robot -- systemctl status reachy-voice-agent reachy-companion-firewall --no-pager
./scripts/companion ssh hub -- journalctl -u reachy-voice -n 50 --no-pager
./scripts/companion ssh robot -- journalctl -u reachy-voice-agent -n 50 --no-pager
./scripts/companion ssh robot -- sudo nft list table inet reachy_companion
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Имена в этих примерах соответствуют example config; при изменении имён использовать `deployment.*.services` и `security.robot.service/nft_table`. Hub пишет ротируемые events.log и voice.log в `paths.data_dir`; агент пишет journal. Для обновления запустить deploy; существующие модели сохраняются. Конфиг передаётся с Mac, поэтому редактировать его там и затем redeploy. Если нужно убрать ограничение надолго, кроме disable firewall установить `restrict_to_hub=false` перед следующим deploy.

Выходной TTS-поток включён. Поток микрофона, поток токенов LLM и перебивание ещё не реализованы: STT получает законченную фразу, Piper начинает синтез после полного текстового ответа. Активация по wake word пока не реализована. Во время обработки и речи микрофон не слушает; pause не обрывает уже начавшееся проигрывание и не выключает моторы. Калибровка происходит один раз при запуске; после изменения окружающего шума перезапустить agent, если порог стал неподходящим. STT/TTS работают на CPU ПК, LLM — на RTX 5070; хаб не выполняет inference. При падении LM Studio агент записывает ошибку и повторяет попытку. История хранится только в RAM, ограничена по времени и количеству сообщений; перезапуск worker её очищает (для LM Studio backend); `voice reset` очищает разговор без перезапуска.

Детали прежних путей, команд и отката миграции: [история установки](docs/installation-history.md).


## Персонаж Ричи

Профиль `profiles/friend.json` задаёт остроумного, язвительного приятеля с собственным мнением. Он общается на «ты», может подколоть, огрызнуться или выругаться по ситуации, не льстит и прямо говорит о противоречиях. Не избегает сложных и чувствительных тем, различает факты и догадки. Грубость не обязательна в каждом ответе; при настоящем переживании человека он умеет убрать колкости. Профиль описывает манеру общения, а не гарантирует каждую реплику модели.

Голос остаётся Piper Ruslan; pitch уменьшен с детских +650 до +300 cents, темп length_scale=1.0. Это изменение существующего голоса, а не новая обученная модель. Персонаж задаётся `llm.system_prompt`, звук — `tts`, служебные фразы — `conversation`.

Чтобы применить профиль к уже работающему Windows worker, из каталога repo выполнить:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\apply-character.ps1
```

Скрипт читает profiles/friend.json, делает резервные копии, обновляет config.local.json и config.worker.local.json и перезапускает только контейнер worker. LM Studio, модели и токен не меняются. Перезапуск worker очищает прежний контекст разговора LM Studio backend. Если config.worker.local.json ещё отсутствует, сначала применить профиль, затем start-worker.ps1.


## Обновление из Git и единый запуск

Основной репозиторий: https://github.com/notanonymousenough/reachy-companion, ветка main. На всех устройствах сохраняется настоящий Git checkout. Токен, локальные IP, модели, данные и venv исключены из Git. `runtime.profile` подключает версионируемый profiles/friend.json при загрузке конфигурации; поэтому pull меняет персонажа/голос, сохраняя сеть и секреты. Чтобы отключить профиль и использовать собственные локальные llm/tts/conversation, задать runtime.profile пустой строкой.

Windows, PowerShell из каталога repo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Это одна команда: git pull --ff-only → Docker Desktop/Linux engine → lms daemon up → загрузка модели, если нужный identifier ещё не загружен → HTTP server LM Studio → проверочная генерация → Docker build/prepare/start worker → health. Повторный запуск безопасен: используются уже загруженная модель и веса, контейнер worker заменяется. Профиль применится автоматически. Для запуска без сети и pull добавить -NoPull; первая загрузка зависимостей/моделей всё равно требует интернета. Модель/CLI/путь Docker/context/GPU/bind/timeouts задаются runtime.windows, API identifier — llm.model, порт — container.desktop_llm_base_url. Скрипт не выгружает чужие модели.

Для запуска при входе пользователя Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-startup.ps1
```

Задача запускает тот же start.ps1 с -NoPull. Требуется вход пользователя и работающий Docker Desktop; это не служба до входа в Windows. Снять автозапуск: `Unregister-ScheduledTask -TaskName` со значением runtime.windows.startup_task. Если регистрация требует повышения прав, выполнить установку задачи из PowerShell администратора.

На хабе / Reachy, из каталога checkout:

```sh
./scripts/update.sh hub
./scripts/update.sh robot
```

Выбрать только роль данного устройства. update.sh делает fast-forward pull, проверяет конфиг и перезапускает systemd через sudo. Зависимости устанавливаются только при изменении lock-файла; код берётся из src через PYTHONPATH, без повторной сборки wheel. Firewall при обычном update не переустанавливается, таймер rollback не запускается. Для новых apt-пакетов или первой установки использовать install. Если pull не удался или есть изменения tracked-файлов, скрипт остановится до restart. Уже выполненный pull не откатывается при ошибке запуска; для отката выбрать прежний commit и update.sh ROLE --no-pull.

Локальный config.local.json и общий secrets/token выдаются при первоначальной настройке, а не скачиваются из Git. На Linux настройка systemd производится install; затем можно просто git pull --ff-only и update.sh ROLE --no-pull. Автозапуск hub/robot — существующие systemd units.

Команды lms проверены по локальному --help и [официальной CLI-документации](https://lmstudio.ai/docs/cli). Сервер запускается с [явным bind и port](https://lmstudio.ai/docs/cli/serve/server-start).

Docker CLI worker использует собственный data/docker-client/config.json без credential helper и фактический endpoint текущего Docker context. Это позволяет собирать публичный базовый образ через SSH Windows, где Desktop helper не имеет доступа к Windows Credential Manager. Пользовательский ~/.docker/config.json не изменяется.
