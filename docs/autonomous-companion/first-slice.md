# Реализация этапов0/1: shadow/replay

Отдельный opt-in entrypoint `python -m reachy_companion.autonomous`; production entrypoint/services не меняются. Hub-side scheduler/reducer не импортирует inference packages и обращается к PC gateway по HTTP. PC gateway делает реальный `/completions` request на каждом доступном clock tick, включая wait. Replay — явно обозначенный deterministic fixture backend; он не считается модельным тестом.

Реализованы typed Authority/Binding/Sensor/Task, JSON Schema validation FastView/FastChoice, unique request/attempt/boot ids, epoch fencing, свежесть sensor capture, bounded snapshots/history/ledger/tasks и один background main slot. Main result сначала ready; отдельный свежий L0 commit записывает simulated speech ровно один раз. Произвольные tools, direct say/motion, goal mutations и physical actors отклоняются. Input mandatory utterance>1024 chars отвергается, а не молча обрезается. Состояние slice только в RAM: restart меняет boot, durable operator state/actuator handshake остаются воротами этапа3.

Fast/main transport jobs выполняются независимо; deadline отзывает результат, но не освобождает выполняющийся job. Timeout соединения PC→model означает execution unknown: gateway quarantine удерживает permit до операторского подтверждения отсутствия orphan execution. Перезапуск gateway допустим только после такого аудита. PC fast baseline требует CPU placement audit; этот gateway сам не загружает/выгружает модели, не задаёт offload и не переключает runtime.

Main default взят из обоих существующих config: `qwen3.5-9b-uncensored-hauhaucs-aggressive`; теперь identity и production context32768 подтверждены live audit [pc-live.md](pc-live.md). Gemma12B может быть другим явно настроенным backend, обязательной зависимости от неё нет. Baseline4K — budget отдельного prototype request, не урезание production32K: runtime `context_tokens=32768`, отдельный `admission_context_tokens=4096`. Vision disabled в этом slice; main input2048/template256/output512/reserve256, unused vision1024 остаётся запасом. Fast input2744/template256/output192/reserve256≤4096. PC gateway требует exact tokenizer (HTTP или optional LM Studio SDK loaded handle) и manual verified hash/build/context/device manifest; несовместимый endpoint или unknown audit запрещают inference. Для SDK установить `.[autonomous-pc]` только на PC. Не обходить gate оценкой chars/tokens.

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

Дополнение: optional typed workflow adapter подключён отдельным этапом; full suite теперь70tests. Scope и реальные VPS результаты описаны в workflows.md; replay не превращается в сетевой режим.

## Исправление причинности после независимой проверки

Global snapshot revision остаётся audit metadata и не является blanket reject. Binding фиксирует digest только доступных candidate/proposal aliases; start/focus/commit проверяют соответствующие current input/kind/attempt/result/expiry. Unrelated sensor updates не отменяют wait или independent action. Turn/operator/boot epochs и monotonic deadline по-прежнему обязательны. Sensor-dependent capabilities в этом slice не разрешены; их будущие adapters должны добавить конкретные dependency checks.

Compute boot никогда не меняется из completion envelope. Initial boot берётся из authenticated health; subsequent owner reconnect вызывает `Scheduler.handshake_compute(boot, generation)` с возрастающим hub-local generation. Old generations и bounded retired boots отвергаются; every completion обязан совпадать с producer/request authority. При boot mismatch результат отвергается; нужен новый trusted health/reconnect, автоматического доверия result нет. Workflow job сохраняет boot своего исходного task.

5 новых regression tests покрывают pending wait/start/commit + unrelated sensors, changed/removed input/proposal, turn/mute fencing, A→handshakeB→lateA main с pendingB fast и late/wrong-producer fast. На момент этого causality patch полный suite —75tests, LAN/model/hardware проверки ещё не запускались. Актуальные реальные PC/hub model пробы и78tests описаны в [pc-live.md](pc-live.md); physical speech/motion ещё не приняты.

Подготовка local lease/ownership guard,86tests и ограничения hardware integration описаны в [actuator-guard.md](actuator-guard.md). Полный FastView теперь default; актуальная full shadow acceptance — в [pc-live.md](pc-live.md).
