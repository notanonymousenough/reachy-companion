# Следующий этап: hub как маршрутизатор, вычисления на ПК

## Область готовности

Это описание baseline voice-routing, а не сертификат готовности всех текущих
устройств или будущего autonomous companion. Исторические проверки отдельной
Windows-установки подтверждали health/Bearer и STT → LM Studio → TTS, но не
заменяют acceptance нового ПК. Процедура установки без private ZIP:
[новый Windows-ПК из Git checkout](windows-clean-pc.md). Код и списки версий зависимостей в Git;
локальные адреса, общий токен, веса и ownership IDs создаются/проверяются отдельно.
Mutable Docker base/apt и pip без artifact hashes не гарантируют одинаковую
сборку на другом ПК. Frozen image предыдущего engine — внешний артефакт,
а не восстановимая из Git зависимость публичного START.
Автоматического fallback inference на Hub нет. OpenClaw/Hermes и будущие
интеграции не устанавливаются baseline-скриптом автоматически.

## Распределение задач

```text
Reachy: ALSA + VAD + проигрывание
  ⇅ PCM / события через LAN
Hub: проверка токена + маршрутизация + ограниченные команды роботу
  ⇅ HTTP / поток без накопления полного ответа
PC worker: STT → выбранный текстовый backend → Piper + SoX
                         ⇅
              LM Studio / OpenClaw / Hermes Agent
```

`reachy-voice` на хабе при `voice.mode=remote` запускает `router.py`. Он не импортирует Vosk/Piper/ONNX, не распознаёт речь, не генерирует текст или звук, не меняет высоту голоса и не хранит историю разговора. Dependencies хаба — стандартная библиотека Python. `reachy-hub` оставляет доступ к factory daemon и контроль допустимых hello/wake/sleep: это маршрутизация/проверки, не inference.

Все вычисления worker происходят на ПК. Backend STT/CPU/GPU определяется
эффективным конфигом (пример использует Faster Whisper; Vosk — совместимый
вариант). Piper/SoX и выбранная локальная LLM остаются PC-зависимостями.
Конкретная видеокарта старой установки не является prerequisite нового ПК.

PC не получает прямого доступа к Reachy. Worker проверяет состояние робота через `hub/status`; все команды оператора и поток аудио идут через hub. Действующее ограничение inbound Reachy не меняется.

## Windows: настроенный baseline из публичного checkout

Сначала выполнить prerequisites/config/token шаги из [clean-PC guide](windows-clean-pc.md).
Нужен Python 3.11+ для preflight/enrollment/stop, хотя inference запускается в
Docker. После настройки используется `scripts/start.ps1 -NoPull`; низкоуровневый
`start-worker.ps1` запускает только worker. Первая установка не является одним
кликом из пустого Windows: нужны Docker Linux engine, LM Studio/model key, общий
токен и реальные LAN-настройки. Private ZIP не нужен и не является зависимостью.
Startup регистрирует только свой только что созданный stopped container до
первого старта; чужая коллизия имени не даёт права на удаление/перезапуск.
Worker endpoints требуют Bearer, кроме health; firewall проверяется для нужного
Hub отдельно от широких Docker Desktop rules.

После `Worker ready` проверить доступ с Hub и настоящий голосовой smoke нового
ПК. Строка ready не доказывает полный диалог или освобождение GPU при stop.
Веса сохраняются локально; при ошибках TLS проверять источники, не отключая
проверку сертификатов. Автозапуск/службы устанавливать только после acceptance.

## Запуск worker в Docker на ПК

Ниже — низкоуровневый launcher для ручной Linux-установки. Исторические проверки отдельного образа/Windows health не подтверждают текущую source-build совместимость нового ПК. Нужны Docker и Python 3.11+ для host launcher; worker имеет собственный Python 3.13. Наличие version-only lock не доказывает wheel/CUDA/архитектурную совместимость или битовую воспроизводимость. Для нового Windows ПК использовать `scripts/start.ps1 -NoPull` после [clean-PC prerequisites/preflight](windows-clean-pc.md).

1. Скопировать repo на ПК, вместе с **локальным конфигом и существующим файлом `secrets/token`**. Токен должен совпадать на ПК, хабе и роботе. Docker build исключает токен/конфиг/веса через `.dockerignore`; токен передаётся как файл bind mount при запуске.
2. Проверить в конфиге PC `network.hub_url` и `network.llm_base_url`, `servers.worker`, модель/голос. Если LM Studio доступен внутри контейнера по LAN адресу ПК, дополнительных host aliases не нужно.
3. Выполнить в каталоге repo на ПК:

```sh
./scripts/companion config validate
./scripts/worker-docker build
./scripts/worker-docker prepare
./scripts/worker-docker start
./scripts/worker-docker logs
```

`prepare` скачивает веса по URL из JSON; `start` публикует порт из `servers.worker.port`, mount каталога repo делает модели/data доступными worker. Image/name/publish_address/cpu_threads задаются в `container`. Корневая FS контейнера read-only; bind-mounted каталог repo доступен для записи моделей и журналов. Windows startup повторно использует только exact registered ID с теми же image/config; при изменении нужен review и новое свободное имя, не удаление по одному имени.

Generic `worker_container` не выполняет Windows canonical manual-stop проверки
или ownership enrollment. Его `start` не является эквивалентом поддержанного
Windows START, а созданный им контейнер не становится автоматически целью
`stop-reachy.ps1`. Не обходить marker/enrollment этим launcher. На Windows
`scripts/start-worker.ps1` — только worker-часть поддержанного пути, когда LM
Studio уже отдельно настроен/проверен; весь baseline запускает `scripts/start.ps1`.

Порт worker должен быть доступен с хаба. Python launcher также умеет `command`: вывести docker run, не запуская его. Значения API-ключей не входят в командную строку: передаются по имени environment variable.

### Альтернатива: Python на Linux ПК

Это отдельная ручная установка, не Windows bootstrap и не перенос готового
окружения. Перед ней проверить наличие закреплённых зависимостей для выбранных
Python/архитектуры; общий worker lock содержит CUDA packages даже для CPU STT.
Успешный host preflight этого не проверяет.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements/worker.lock
.venv/bin/pip install --no-deps .
# Установить SoX средствами ОС.
./scripts/companion models download
PYTHONPATH=src .venv/bin/python -m reachy_companion worker serve
```

Для постоянной установки через SSH настроить `deployment.worker` (настоящий user/root), затем `./scripts/companion deploy worker`. Install поддерживает apt/systemd на Debian; Windows-установка через этот путь не поддерживается.

## Переключение живого хаба

Сначала проверить worker с хаба:

```sh
COMPUTE_URL=$(./scripts/companion config value network.compute_url)
./scripts/companion ssh hub -- curl --fail --max-time 10 "$COMPUTE_URL/health"
```

Затем на Mac в основном config.local.json установить:

```json
"voice": {"mode": "remote"}
```

И `streaming.enabled=true`, `deployment.hub.venv_dir=".venv-router"`, чтобы создать чистое окружение маршрутизатора. Повторная установка хаба в этом режиме использует пустой hub.lock и не загружает модели. Существующие веса/venv не удаляются; они больше не используются для inference. Сохраняется возможность явного отката на local.

```sh
./scripts/companion deploy hub
./scripts/companion deploy robot
./scripts/companion hub status
./scripts/companion voice status
./scripts/companion voice pause
./scripts/companion voice ask 'Привет! Скажи одну короткую фразу.'
./scripts/companion voice resume
ROBOT_ROOT=$(./scripts/companion config value deployment.robot.root)
./scripts/companion ssh robot -- sudo "$ROBOT_ROOT/scripts/companion" firewall confirm
```

Повторный install robot переустанавливает firewall с таймером отката. Подтверждать только после нового SSH через хаб и проверки состояния.

В remote-статусе отображаются `mode=remote`, worker/provider и состояние агента. Если ПК выключен, health отвечает 503, робот повторяет попытки; скрытого запуска Vosk/Piper на hub нет. Для отката явно вернуть voice.mode=local, streaming.enabled=false и redeploy; в режиме local install использует worker.lock и модели на хабе.

## Задел для OpenClaw и Hermes Agent

Переключатель `brains.provider` принимает `lm_studio`, `openclaw`, `hermes`. URL, endpoint, имя backend и имя переменной API-ключа находятся в `brains.*`; реальные ключи задаются только в окружении worker. Агентные runtime разворачиваются на ПК или отдельном сервере, не на Pi 3B+.

[OpenClaw chat API](https://docs.openclaw.ai/gateway/openai-http-api) включается настройкой `gateway.http.endpoints.chatCompletions.enabled=true`. Адаптер отправляет persona и последнюю реплику, `model=openclaw/default`, стабильный `user` для текущего разговора. Историю держит OpenClaw. Выбор его upstream LLM настраивается отдельно в OpenClaw: переключение нашего provider не настраивает его автоматически на LM Studio.

[Hermes Agent API](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server) принимает `/v1/chat/completions`; API-сервер нужно включить, задать ключ и bind. По умолчанию примеры используют model `hermes-agent`. Наш адаптер передаёт полный ограниченный transcript и `X-Hermes-Session-Id`. `voice reset` меняет conversation ID и очищает локальный transcript; это не удаление долговременной памяти агентного runtime.

Для простого голосового общения остаётся прямой LM Studio. При добавлении памяти, навыков и инструментов Hermes — удобный кандидат для первого эксперимента; при необходимости многих каналов и интеграций можно выбрать OpenClaw. Это инженерная оценка под данную архитектуру, не результат сравнительного теста.

В этом этапе адаптеры возвращают **только текст**. Tool calls не превращаются автоматически в команды моторам. Будущий доступ к действиям робота лучше предоставить отдельными allow-listed tools через hub с ограничениями углов/состояния; SSH и произвольные команды не нужны для этого интерфейса.

## Как устроен streaming сейчас

Поддержаны `/stream/turn`, `/stream/text`, `/stream/say`. Worker отвечает NDJSON событиями:

```text
reply {transcript, reply, command}
audio {format:S16_LE, sample_rate:16000, channels:1, pcm_base64}
audio ...
done {ok:true, transcript, reply, command, elapsed_seconds}
```

Worker синтезирует Piper по предложениям, поднимает высоту SoX на ПК и ресемплирует до 16 kHz. PCM режется по `pcm_chunk_bytes`, router передаёт доступные байты немедленно через read1/flush, агент пишет их в **один непрерывный aplay**, без временных WAV на диске. Есть лимиты длины события/аудио, контроль формата, обработка обрыва потока и завершение процесса проигрывания. При disconnect worker освобождает lock, незавершённый ответ не фиксируется в локальной истории.

Это streaming **выходного TTS-аудио**: воспроизведение начинается после первого синтезированного предложения, до окончания синтеза всего ответа. LLM пока возвращает полный текст; микрофон пока отправляет завершённую фразу. Base64 остаётся в событии, чтобы сохранить простой HTTP-транспорт; он добавляет около трети размера PCM. Это не full-duplex и не WebRTC.

Для следующего этапа:

1. Непрерывная отправка PCM с микрофона через WebSocket; STT partial/final на ПК, конец реплики задаёт VAD.
2. SSE от LLM и накопление законченных предложений для TTS: первый звук до готовности полного текста.
3. Barge-in: одновременно слушать и говорить, отменять текущие LLM/TTS/playback, подавлять акустическое эхо. Просто включить микрофон во время речи недостаточно: робот будет слышать себя.

При PCM mono 16 kHz/16 bit вход требует примерно 32 kB/s без base64. Такая передача не требует inference на hub. Задержка до первого звука определяется концом реплики, временем STT, первым ответом LLM и первым TTS-предложением; hub лишь добавляет небольшой сетевой переход. Новую задержку на ПК ещё нужно измерить после развёртывания.

## Реальная локальная проверка Docker worker

Проверен путь через stdlib-router с настоящими Vosk/Piper и существующей LM Studio на ПК. Тестовый worker работал локально в Docker на Mac, не на Windows и не на хабе; после проверки контейнер удаляется. Синтетическая реплика «Привет! Как тебя зовут?» распознана как «привет как тебя зовут», получен ответ локальной модели и поток 16 kHz PCM.

Замер: первый TTS-audio chunk через 0,501 s для прямого say; первый audio chunk полного STT→LLM→TTS turn через 1,196 s, завершение передачи через 1,558 s. Звук ответа длится примерно 6,50 s, проигрывание в этот замер не входит. Это замер конкретной реплики на локальном тестовом worker, не обещание задержки Windows ПК.

При проверке выявлена отсутствующая `libatomic.so.1` в slim image; добавлен libatomic1, после чего реальный worker успешно запускается. libgomp1 также включён в образ.


## Проверка на Windows worker после включения

Проверены новый SSH к Reachy через hub, factory daemon ready без ошибок, режим remote и состояние agent listening без last_error. Pause → ask → resume успешно завершились: ответ LM Studio прошёл через worker/hub в настоящий ALSA aplay робота. Это проверка успешного воспроизведения программой; субъективную громкость и тембр оценивает пользователь рядом с роботом.

Синтетическая реплика «Привет! Как тебя зовут?» прошла через настоящий Windows Vosk → LM Studio → Piper/SoX по маршруту hub → worker → hub. Распознано «привет как тебя зовут». Первый PCM chunk через 1,099 s, весь поток получен через 1,285 s; длительность звука 6,19 s. Для отдельного say первый chunk через 0,152 s. Замер начинается после отправки готовой реплики и не включает время её записи или полное проигрывание. Это один замер, а не гарантия задержки.

Прямые подключения Mac к Reachy на SSH/daemon/agent заблокированы, SSH через hub доступен; firewall и agent включены в автозапуск, таймер rollback отменён после свежего SSH. Микрофон захватывает фразы; разговор с живым человеком, оценка тембра и отключение/возврат ПК остаются отдельными пользовательскими проверками. Полная перезагрузка устройств не выполнялась.

Обновление всех устройств из Git и запуск Windows LLM+worker одной командой описаны в [README](../README.md#обновление-из-git-и-единый-запуск). Последний профиль — естественный мужской голос без pitch-shift и язвительный приятель; он применяется при чтении runtime.profile.
