# Реализация этапов0/1: shadow/replay

Отдельный opt-in entrypoint `python -m reachy_companion.autonomous`; production entrypoint/services не меняются. Hub-side scheduler/reducer не импортирует inference packages и обращается к PC gateway по HTTP. PC gateway делает реальный `/completions` request на каждом доступном clock tick, включая wait. Replay — явно обозначенный deterministic fixture backend; он не считается модельным тестом.

Реализованы typed Authority/Binding/Sensor/Task, JSON Schema validation FastView/FastChoice, unique request/attempt/boot ids, epoch fencing, свежесть sensor capture, bounded snapshots/history/ledger/tasks и один background main slot. Main result сначала ready; отдельный свежий L0 commit записывает simulated speech ровно один раз. Произвольные tools, direct say/motion, goal mutations и physical actors отклоняются. Input mandatory utterance>1024 chars отвергается, а не молча обрезается. Состояние slice только в RAM: restart меняет boot, durable operator state/actuator handshake остаются воротами этапа3.

Fast/main transport jobs выполняются независимо; deadline отзывает результат, но не освобождает выполняющийся job. Timeout соединения PC→model означает execution unknown: gateway quarantine удерживает permit до операторского подтверждения отсутствия orphan execution. Перезапуск gateway допустим только после такого аудита. PC fast baseline требует CPU placement audit; этот gateway сам не загружает/выгружает модели, не задаёт offload и не переключает runtime.

Main default взят из обоих существующих config: `qwen3.5-9b-uncensored-hauhaucs-aggressive`. Это configured identity, не live inventory. Gemma12B может быть другим явно настроенным backend, обязательной зависимости от неё нет. Baseline4K — budget отдельного prototype request, не урезание production32K. Vision disabled в этом slice; main input2048/template256/output512/reserve256, unused vision1024 остаётся запасом. Fast input2744/template256/output192/reserve256≤4096. PC gateway требует exact tokenizer endpoint и manual verified hash/build/context/device manifest; несовместимый endpoint или unknown audit запрещают inference. Текущий LM Studio tokenizer API не подтверждён. Не обходить gate оценкой chars/tokens.

## Воспроизводимые команды

Из корня repo, Python3.11+:

```sh
python3 -m venv .venv-shadow
.venv-shadow/bin/pip install -e '.[autonomous]'
.venv-shadow/bin/python -m reachy_companion.autonomous validate
.venv-shadow/bin/python -m reachy_companion.autonomous replay --duration 5 --events scenarios/autonomous-shadow.json --output data/shadow-report.json
.venv-shadow/bin/python -m unittest discover -s tests -p test_autonomous.py -v
```

Создать каталог `data` перед записью; output exclusive-create и может содержать текст (хранить локально, не в git). `config.autonomous.example.json` не обращается к сети в replay. Для отдельного PC gateway скопировать его в ignored `config.autonomous.local.json`; задать проверенные model id/endpoint/template/tokenize_path/audit, gateway bind/client_url и отдельный `REACHY_SHADOW_TOKEN` через environment. Token не печатается и не хранится в JSON. За пределами localhost обеспечить защищённый private transport/SSH tunnel: gateway token поверх публичного HTTP не допускается.

На ПК:

```sh
python -m reachy_companion.autonomous gateway --config config.autonomous.local.json
```

На hub/операторском узле (без inference):

```sh
python -m reachy_companion.autonomous shadow --config config.autonomous.local.json --duration 30
```

Команда shadow не подключает робот, microphones, TTS, S3 или платные API. Ошибки gateway дают gaps, новые доступные ticks не используют cached decisions. Gateway completion response требует finish_reason=stop; malformed/truncated choices отвергаются целиком. HTTP job client может завершиться раньше backend: PC execution lock сохраняется независимо от клиента.

## Проверка 2026-10-09

17 новых adversarial tests прошли, полный regression suite:62 tests. Проверены loopback HTTP mock model/tokenizer/auth, непрерывность при background task, busy/deadline accounting, mute/unmute и stale boot/attempt/turn, late/duplicate commit, неизвестные aliases/tools, bounded silence projection на2000ticks, sensor age/unknown и oversized mandatory input. Это protocol/mock tests, не качество LLM или hardware.

Finite replay5s:5 fresh fixture requests, один main task/ready/commit, operator mute/unmute. Finite replay23s с main delay20s:23 fresh requests, одна main task, цикл не останавливался. Отчёты находятся вне git. Read-only HTTP inventory ПК: один network attempt timeout после2s; SSH не повторялся. Fast model/CPU, actual tokenizer/template и GPU identity/VRAM остаются unknown. Следующий допуск: Q01/Q02/Q04 audit и finite real-model shadow; hardware только после stage3 ownership/stop tests.
