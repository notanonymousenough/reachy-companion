# Проверенные источники, модели и бюджеты

Исследование на 2026-10-09. Публичные main/master и модельные репозитории могут изменяться; перед реализацией нужно закрепить commit/revision и hash локальных артефактов. Ни одна опубликованная характеристика не заменяет измерение установленного runtime. Числа производительности ниже — проектные цели/оценки, кроме явно обозначенного исторического замера.

## Что установлено из существующего проекта

| Свидетельство | Факт из исходников/документации | Следствие |
|---|---|---|
| `src/reachy_companion/brains.py` | LM Studio raw completion, модельно-зависимый шаблон, синхронный HTTP; Hermes/OpenClaw adapters текстовые | Новые typed proposals, мультимодальность и cancellation нужно проектировать отдельно |
| `agent.py`, `microphone.py` | Persistent mute с epoch; stop phrases; playback и capture отменяются | Сохранить семантику «замолчи»; расширить epochs на все workers |
| `sound_monitor.py` | bounded latest queue; music hysteresis и прямой dance при music | Queue reuse полезен, правило dance заменить на LLM-выбор |
| `motion_limits.py`, `hub.py` | Ограниченные углы, плавные шаги, app ownership/motor state checks | Safety envelope — полезный старт, не полноценный motion scheduler |
| Контекст пользователя; README, installation-history | Пользователь сообщил Qwen 3.5 9B Q6_K/32K; документация описывает Faster Whisper Small GPU, Piper/SoX и YAMNet ONNX CPU | Сообщённые метаданные и документальный опыт, live-проверка сейчас не прошла |
| Последние записи README | Charge reminder удалён, история RAM; обработка полного utterance и полный текст перед Piper | Требуются persistent memory и новый pipeline; старые записи о таймере не считаются актуальными |

Локальные конфиги/secrets не воспроизводятся. Read-only `git status` перед проектом был чистым. Не запускались deploy, изменение модели, inference, движения, capture или S3 upload.

Попытки live-проверки: запрос `nvidia-smi` по SSH к ПК вернул timeout; чтение установленной версии Python-пакета на Reachy через hub завершилось timeout при установлении соединения. Первоначальное сетевое sandbox-ограничение было обойдено разрешённой read-only проверкой, но сеть всё равно недоступна. Это **не** автоматический отказ в разрешении и не доказательство выключенных устройств. Фактические свободная VRAM, температура, версия SDK и GGUF остаются unknown.

## SDK и аппаратные сигналы

По [официальному backend SDK v1.11.0](https://raw.githubusercontent.com/pollen-robotics/reachy_mini/v1.11.0/src/reachy_mini/daemon/backend/robot/backend.py) есть чтение позиций, hardware errors и BMI088 для Wireless; температура берётся из IMU. Поле target current — команда/цель управления, оно не является измеренным током. Низкоуровневый цикл в этом исходнике задан 50 Hz. Это характеристика исходника версии, не измеренная частота текущего робота.

[REST state routes v1.11.0](https://raw.githubusercontent.com/pollen-robotics/reachy_mini/v1.11.0/src/reachy_mini/daemon/app/routers/state.py) предоставляют pose, joint positions, DOA и IMU, включая единицы. None может означать отсутствие/устаревание IMU, поэтому одного None недостаточно для «датчик отсутствует». В просмотренных state routes нет battery SOC, измеренных servo current/load или температур каждого сервопривода. Это ограниченный аудит публичного API, не утверждение об отсутствии регистров в hardware.

[Текущий protocol SDK](https://raw.githubusercontent.com/pollen-robotics/reachy_mini/main/src/reachy_mini/io/protocol.py) различает статус daemon/backend, позы, IMU и task progress. [SDK class](https://raw.githubusercontent.com/pollen-robotics/reachy_mini/main/src/reachy_mini/reachy_mini.py) позволяет управление движениями и media, но создание SDK клиента может менять настройки. Поэтому hardware audit сначала читает package metadata, OpenAPI и GET состояния, не создаёт новый управляющий клиент и не вызывает wake/goto/torque/media release.

Матрица до live audit:

| Сигнал | Статус | Разрешённое использование |
|---|---|---|
| Camera/audio | Есть по текущему проекту, свежесть не проверена сейчас | После health/permissions/свежего frame или PCM |
| Pose/motor mode/app ownership | Поддержка SDK и текущие вызовы в hub.py | Feedback после live GET; принятая команда не feedback |
| DOA | API найден в указанной версии, локально unknown | Направление только после замера и сверки frame |
| IMU accel/gyro/quaternion/temp | API и Wireless backend найдены, локально unknown | Temp только IMU; не температура моторов/батареи |
| Servo current/load/temp/voltage | Не подтверждены публичным state API/установкой | Плагин disabled до документации единиц и реального чтения |
| Battery SOC/charge | Программный датчик ранее не найден, сейчас не подтверждён | Никаких процентов по таймеру/пингу/напряжению мотора |
| PC GPU/CPU thermals, power | Возможны средствами ОС, сейчас не измерены | Характеристика ПК с source label; не «энергия Reachy» |
| Lidar/touch/dock/localization | Будущие optional plugins | Registry availability=unsupported/unknown, без fake values |

Проверка servo telemetry в этапе 0: изучить версию motor-controller bindings и модели моторов, доступные **read-only** методы/регистры, единицы и частоту; не открывать второй serial controller параллельно daemon. Предпочесть уже имеющиеся daemon telemetry; если нет — отдельная будущая API доработка и тест в безопасном режиме. Ошибка позиции может означать lag/ограничение, но не калиброванную силу сопротивления. Dock power meter измеряет входную мощность дока, не гарантирует SOC.

## Gemma 4 12B: четыре независимых подтверждения

1. [Карточка Google](https://huggingface.co/google/gemma-4-12B-it) описывает Unified 12B, multimodal inputs, thinking и function calling; это подтверждение семейства, а не скачанного файла.
2. [Список GGUF издателя LM Studio](https://huggingface.co/lmstudio-community/gemma-4-12B-it-GGUF/tree/main) содержит Q4_K_M 7,38 GB, Q6_K 9,79 GB, Q8_0 12,7 GB и mmproj BF16 175 MB. Размеры десятичные и округлены сайтом; публичный Q6 не доказывает identity локального Q6.
3. [Конвертер llama.cpp](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/conversion/gemma.py) содержит Gemma4Unified model path, а [парсер Gemma4](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/common/parsers/gemma4.cpp) обрабатывает специальные tool response turns. Наличие кода в master не доказывает, что тот же код вошёл в runtime LM Studio на ПК. [Multimodal docs](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/multimodal.md) объясняют отдельный mmproj и offload; не переносить команды для другой Gemma автоматически.
4. [LM Studio tool use docs](https://lmstudio.ai/docs/developer/openai-compat/tools) связывают native tool use с шаблоном модели **и** поддержкой парсинга runtime; [structured output](https://lmstudio.ai/docs/developer/openai-compat/structured-output) описывает JSON schema output. Нужны тесты именно установленного backend на text, image, thinking off/on, tools и schema. Badge Vision/Tool Use не заменяет их.

До этого проверки модель обозначается `main_candidate=unverified_gemma4_12b`. Не использовать её audio capabilities вместо существующего STT без проверки качества/задержки. Разные форматы thinking и chat template нельзя обслужить нынешним Qwen prefix или просто удалить `<think>` regex во всех случаях.

Read-only локальный audit будущего этапа: inventory файлов в пользовательском каталоге модели без раскрытия других путей; magic GGUF/version, tensor count, `general.architecture`, file_type, quant distribution, tokenizer template, context/train context, block_count, KV heads/dimensions, multimodal metadata; SHA256 всех weight shards/mmproj, publisher revision. Считать hash можно долго, поэтому делать по отдельному плану без нагрузки на разговор. Затем read-only runtime inventory/version/build/backend и модели `/models`. Smoke inference/temporary load уже относятся к прототипу, могут менять нагрузку и требуют согласованного тестового окна; в этом исследовании их не запускали.

## Лёгкая и визуальная модели

[Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B) — конкретный кандидат fast classifier с отключённым thinking. Его способность выдавать русский краткий JSON и надёжно выбирать wait/action должна быть измерена, не следует из размера. Начинать Q8 для CPU; Q4/Q5 возможны после проверки. При плохом качестве — 1–2B на ПК или сохранённый Qwen backend с меньшей частотой. Hub не принимает inference даже при fallback.

Отдельная [SmolVLM-500M-Instruct](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct) — возможный дешёвый описатель, а не источник надёжной идентичности/событий. Первая конфигурация предпочитает vision основной модели только по запросу с latest-frame queue; отдельная VLM добавляется лишь после resource test. Для low-cost scene cache допускаются CPU motion/change detectors на ПК с честным ограниченным содержанием, без обещания понимания картинки.

[Faster Whisper](https://github.com/SYSTRAN/faster-whisper) поддерживает CTranslate2 CUDA/CPU и разные compute types. Их опубликованные benchmarks сделаны на других условиях: они не превращены здесь в latency RTX 5070. [YAMNet](https://www.tensorflow.org/hub/tutorials/yamnet) классифицирует звуковые окна; ONNX-конверсия из текущего проекта — отдельный сторонний артефакт с собственным pinned hash, не официальный Google ONNX. Вероятный music/speech label не устанавливает конкретное бытовое событие.

## VRAM: планирование, а не гарантия

По [NVIDIA](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5070-family/) обычная RTX 5070 имеет номинально 12 GB памяти, Ti — 16 GB. Пользователь указал обычную 5070; доступный объём и Windows/display reservation нужно получить из nvidia-smi и telemetry container. Нельзя рассчитывать как для 16 GB.

Публичный Gemma Q6 файл ≈9,12 GiB, Q4_K_M ≈6,87 GiB (GB/2^30). Это только размер файла: resident VRAM зависит от offload, tensor dtypes, metadata и runtime buffers. Q6 + всё остальное может не поместиться. При planning выделить отдельно: KV, projector/vision activations, compute scratch, driver/display, Whisper, fast модель и reserve 10–15% **из измеренного доступного**.

Для обычного full-attention слоя грубая KV формула: `2 * n_layers * n_kv_heads * head_dim * context_tokens * bytes_per_element * concurrent_slots`. Например **гипотетические**, не Gemma-параметры L=40, Hkv=8, D=128, FP16: 4K ≈0,625 GiB, 8K ≈1,25 GiB, 32K ≈5 GiB на слот. Sliding-window/hybrid/cache implementation меняют это существенно; сначала читать реальный GGUF и замерять. Два server slots могут удвоить allocation либо делить заданный total context — зависит от runtime. Image tokens занимают контекст и buffers, не бесплатны. KV Q8 может снижать память, только если конкретные kernel/model это поддерживают и проходят regression.

| Профиль-кандидат | Резидентность и контекст | Допущение/деградация |
|---|---|---|
| A, первый | 0,6B Q8 CPU ПК; Gemma12B Q4 GPU, context 4K–8K/slot=1; Whisper Small CUDA int8_float16 1 task; YAMNet/Piper CPU | Planning main weights ~6,9 GiB + KV условно 0,6–1,3 + scratch/vision 0,6–1,5 + STT 0,5–1 + display/reserve 1–2. Диапазон суммы ~10–13 GiB: при upper end STT CPU или context 4K; необходим замер. |
| B, сохранение Q6 | 0,6B CPU; 12B Q6 частичный GPU offload, context 4K; STT CPU int8 | Offload 20–30% weights как старт эксперимента, не exact layers; перенос снижает скорость и зависит от RAM/bandwidth ПК. Vision сериализован с main. |
| C, существующая модель | Существующий Qwen9B Q6: отдельные тестовые профили4K/8K и сохранённая измеряемая опция32K; production32K не изменяется; 0,6B CPU; STT GPU/CPU по замеру | Нет подтверждённой vision через current raw adapter; camera description — отдельный bounded CPU/VLM lane после проверки. |
| D, максимум GPU | 0,6B GPU + main Q4 + STT GPU | Только при spare VRAM и p95 fast под mixed load. Два model processes не обеспечивают гарантированное kernel preemption. |
| E, ограничение ресурсов | Fast CPU, main CPU/offload или rare online; VLM по запросу; STT CPU | Цикл живёт медленнее, внешние намерения сдержаны; API cap, без бесконтрольной загрузки моделей |

В A main speech и VLM используют одну residency, выполняются по очереди; fast CPU продолжает цикл во время обеих задач. Hot swapping main weights на каждом кадре неприемлем: холодные задержки/VRAM peaks; смена профиля отдельная управляемая операция. Q8 12B уже сравним с номинальной памятью без KV/прочего, поэтому не основной вариант full GPU.

CPU capacity ПК неизвестна. Fast CPU P95 должен уложиться в budget на реальном процессоре; если нет, использовать bounded GPU fast приоритет с короткими main segments, либо меньшую частоту. Не обещать 1 Hz при любом железе. Main prefill и image encode могут надолго занять GPU: совместная резиденция != низкая latency. Docker Desktop GPU exposure/CUDA совместимость с Blackwell проверить внутри worker, не только на Windows host.

## Частота, latency и контекст

Начальные проектные цели, не измерения:

| Путь | Цель/ограничение |
|---|---|
| Fast L0 | 1 Hz начально; P50 ≤600 ms, P95 ≤700 ms для устойчивого1 Hz при utilization0,7; FastChoice cap 192 tokens, common 32–96 |
| Fast degraded | Новый запрос через 2–5 s; hard timeout 3 s; не запускать catch-up bursts |
| Fast context | Обычно 1,2–2K input, cap 3K; static prefix 400–700, current scene/sensors 250–500, memory/personality 200–350, диалог/decisions/tasks 200–450 |
| Main L1 | Baseline4K: text2048 + vision1024 + template256 + output512 + reserve256; option8K: text6144 при тех же остальных caps; TTFT target ≤2 s, bounded segments для речи |
| Deep L2 | Обычно 4–12K input, output ≤2K; deadline 30–60 s, loop не ждёт |
| STT final | P95 ≤1,5 s после конца окна, hard 5 s; streaming partial отдельный тест |
| First speech | Baseline target P95 ≤5 s после utterance end; stretch ≤2,5 s после замера; складывается VAD tail + STT + fast/main TTFT + TTS + network |
| Control button mute/stop | P95 ≤300 ms до capture/playback cease при здоровой LAN; physical motion cessation измеряется отдельно |
| Robot stale lease | Default 500 ms, плюс торможение/daemon latency; не promise hard realtime |

Декодирование 100 tokens при 100 tok/s уже 1 s без prefill/network; следовательно для 1 Hz fast надо либо очень компактный output, либо выше throughput. Фактическую частоту задавать по `P >= p95(fast_total)/target_utilization`, utilization первоначально ≤0,7, и mixed-load tests. При utilization 0,7 для 1 Hz нужен p95 fast_total ≤700 ms; если получается 1 s, устойчивый период примерно 1,43 s, а не обещанные 1 Hz. Семантические поля можно кодировать короткими ключами на L0 и разворачивать gateway до canonical schema. Маленькая модель не гарантирует достаточный русский tool selection; качество проверяется отдельно.

При 1 Hz за сутки 86 400 requests, при 0,5 Hz — 43 200. Если полный input 1 500 и output 64 tokens, это 129,6M input и 5,53M output/day. Prefix caching снижает prefill, но не число решений или output generation. Не хранить каждый input blob в логах. Fast должна быть локальной, иначе даже небольшая цена множится на сутки.

Исторический README сообщает один короткий Qwen вызов ~0,62 s без reasoning против ~18 s с reasoning. Это однократный старый опыт, не benchmark непрерывного JSON-трафика. Старые замеры STT/TTS на CPU/Pi не применяются к новому mixed workload.

Стоимость online: `sum((input_tokens*P_in + cached_tokens*P_cache + output_tokens*P_out)/1e6) + tool charges`. Пример чисто арифметический, **не тариф провайдера**: 10 вызовов/day × (4K input +1K output), условные $2/$8 за миллион → $0,16/day ≈$4,80/30 days без tools. Начальный cap $0,50/day и 10 calls/day configurable; реальные цены заносятся с provider/model/date до включения. Саморазвитие не может поднять cap. Локальная стоимость: измеренные extra GPU/CPU watts × hours /1000 × тариф электричества; без watt sensor нельзя выдавать фактическую энергию.

## Hermes / OpenClaw / собственный orchestrator

| Критерий | Hermes Agent | OpenClaw | Минимальный собственный |
|---|---|---|---|
| Проверенный проект | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | [openclaw/openclaw](https://github.com/openclaw/openclaw) и официальная документация | Нужно реализовать |
| HTTP | [API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/) chat/completions и sessions | [Gateway Chat Completions](https://docs.openclaw.ai/gateway/openai-http-api), opt-in endpoint | Typed task/decision/results без полного стороннего agent run на каждом тике |
| Async task lifecycle | [Programmatic integration](https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration): runs/status/events/stop/capabilities | Общая Gateway agent интеграция; robot-specific отмена/leases не подтверждены | Полный контроль deadlines/epochs |
| Tools и расширения | Terminal/web/skills/memory; tool execution на API-server host | Gateway tools/channels, agent policies | Малый registry, больше собственной работы |
| Изоляция | Зависит от выбранных terminal backends/toolsets | [Sandbox docs](https://docs.openclaw.ai/gateway/sandboxing): Docker и отдельные policies | Sandbox broker обязателен |
| Память/личность | Собственные memory/skills надо ограничить read-only projection | Собственные sessions/persona не равны canonical robot memory | Единая версия и происхождение |
| Главный риск | Full tool-equipped API, session coupling и изменения upstream | Endpoint token означает operator-level доступ; недопустимо отдавать сенсорам | Стоимость реализации, тесты, поддержка |

Рекомендация: собственный hub scheduler/reducer + model gateway и typed tool broker на ПК. Первым optional executor попробовать Hermes для сложных bounded research runs: documented run lifecycle ближе к task contract. Проверять `/v1/capabilities` и закреплять версию, а не считать маршруты неизменными. OpenClaw полезнее при необходимости множества каналов/интеграций пользователя. Ни одна платформа сейчас не доказана на этой установке.

Общий adapter: submit(task)->executor_run_id, status, result_stream, cancel(best effort), health и capability manifest. Hub journal/task table остаётся authority; `stop` внешнего агента может быть cooperative и не обеспечивает физическую остановку робота. Separate executor session per intent, не один persistent chat, куда на каждом тике дописывается snapshot. Агенту не передаётся управление mic, motor daemon или доступ к памяти на запись. Существующий brains.py не проверялся как production integration; его наличие не является подтверждением совместимости нового дизайна.

## Второй проход: конкретный артефакт, архитектура KV и runtime gates

Повторная ограниченная read-only проверка ПК и hub 2026-10-09 снова дала SSH connection timeout (по одной попытке). Других повторов, новых inference, load/unload и paid API не делалось. Поэтому таблица ниже разделяет публично проверенное и локально неизвестное.

| Проверка | Доказательство | Что ещё неизвестно |
|---|---|---|
| Published Q6 identity | [Страница Q6_K](https://huggingface.co/lmstudio-community/gemma-4-12B-it-GGUF/blob/main/gemma-4-12B-it-Q6_K.gguf): SHA256 `383372016e2f801719e4042aecc895c6731f54402f7ec5d88867970856df6161`, displayed commit `5c219ed` | Local SHA не прочитан; UI имя не доказательство совпадения |
| Published mmproj identity | [BF16 projector](https://huggingface.co/lmstudio-community/gemma-4-12B-it-GGUF/blob/main/mmproj-gemma-4-12B-it-BF16.gguf): SHA256 `7fd884a5f7d9ee60f6b88e5b51287151e547454b2b60a4a6270bb5434310ad0e`, displayed commit `65fe312` | Наличие/загрузка matching projector на ПК unknown |
| Unified implementation | [Merged PR #24077](https://github.com/ggml-org/llama.cpp/pull/24077), 2026-06-03; [vision projector implementation](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/mtmd/models/gemma4uv.cpp) найден | Нужен runtime commit, содержащий поддержку и последующие исправления; PR merge не SLA |
| Actual capability | Public docs/model config | Local text/schema/tool/vision/reasoning success по отдельности unknown |

[Google config](https://huggingface.co/google/gemma-4-12B-it/blob/main/config.json), displayed commit `5926caa`, задаёт 48 слоёв: 40 sliding и 8 full, sliding_window=1024, local KV heads=8/head_dim=256, global KV heads=1/global_head_dim=512; attention_k_eq_v=true. Это **HF config**, не прочитанный local GGUF. Поэтому прежний full-attention пример не использовать как оценку Gemma. Проверять mapping GGUF/global/local dims и runtime allocation.

Расчёт-приближение по этому config: при FP16, двух отдельно хранимых K/V и реально bounded sliding cache локальная часть `2*40*8*256*1024*2` ≈0,3125 GiB; global при 4K/8K/32K ≈0,0625/0,125/0,5 GiB. Сумма ≈0,375/0,4375/0,8125 GiB. Если sliding cache выделен full context, сумма соответственно ≈1,3125/2,625/10,5 GiB. Это **оценки layout**, без padding, copies, logits/image activations и compute buffers; sharing K/V при k_eq_v может уменьшить global часть, но не предполагается заранее. По [llama.cpp Gemma4 implementation](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/src/models/gemma4.cpp) важны отдельные sliding/global параметры и optional tensors; точное residency выясняется buffer report. Ускоренный/paged cache нельзя вывести из training context 256K.

Для fast Qwen3 [официальный config 0.6B](https://huggingface.co/Qwen/Qwen3-0.6B/raw/main/config.json) задаёт 28 слоёв, 8 KV heads, head_dim=128. Обычный FP16 KV при 2K ≈224 MiB, 4K ≈448 MiB; Q8 weights ~0,6–0,8 GiB плюс runtime overhead. Это RAM budget для CPU fast, не только 0,6B весов. Значение context в fast profile — 3K input +192 output и запас template, поэтому выделенный context candidate 4K. При лимите context 2K нельзя обещать cap 3K input.

[Qwen3.5-0.8B](https://huggingface.co/Qwen/Qwen3.5-0.8B) и [0.8B config](https://huggingface.co/Qwen/Qwen3.5-0.8B/blob/main/config.json) — альтернативный fast кандидат с vision и hybrid linear/full attention; [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) и [его config](https://huggingface.co/Qwen/Qwen3.5-9B/blob/main/config.json) — основная альтернатива с возможностью общей vision residency. Для гибридных моделей нельзя подставлять все слои в обычную KV формулу: есть recurrent state и ограничения rewind/cache. Fast baseline остаётся Qwen3-0.6B text-only до оценки 0.8B; vision в fast **не** включается даже если модель её умеет, чтобы large image encode не поглощал decision budget.

| Выбор | Runtime-кандидат | Ворота и причина |
|---|---|---|
| Fast CPU Qwen3-0.6B | Dedicated pinned llama-server process на ПК | Schema-constrained FastChoice, isolated slot/context, reuse metrics, supervised exit; не control loop на RPi |
| Main Gemma12B / Qwen9B | Сначала текущий LM Studio в test window; альтернативно pinned llama-server CUDA | Matching file/projector/build; choose по mixed load/cancel/visibility, а не интерфейсу |
| Separate small VLM | SmolVLM либо Qwen3.5-0.8B после tests | Только если scene quality лучше CPU change detector, не съедает fast CPU reserve |
| Native Transformers reference | Только отдельный исследовательский профиль ПК | Полезен для сравнения шаблона/model functionality, BF16 12B не planned fit 12GB; не основной always-resident deployment |

[LM Studio parallel requests](https://lmstudio.ai/docs/app/advanced/parallel-requests) описывает continuous batching и Max Concurrent Predictions, для GGUF указывает runtime llama.cpp v2.0.0; это имя runtime LM Studio, не upstream tag. Документированный default concurrency нельзя принять как нужную настройку робота: первоначальная main concurrency=1, иначе VRAM/KV и tail latency меняются. [Stateful chats](https://lmstudio.ai/docs/developer/rest/stateful-chats) описывает `/api/v1/chat` и `store:false`; fast следует stateless path, без бесконечной цепочки previous_response_id. [MLX cache blog](https://lmstudio.ai/blog/mlx-engine-agentic-workloads) относится к Apple silicon: результаты не переносятся на Windows CUDA.

[llama-server reference](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md) документирует continuous batching, cache_prompt, id_slot, KV types и slots cache save/restore/erase. `t_max_predict_ms` не полный end-to-end timeout; применять его как stop всех стадий нельзя. Gateway deadline и execution accounting остаются обязательны. Saved KV — temporary acceleration artifact, не роботовая memory. Parameters/version/API проверить у выбранного бинарника; response cache/no model execution запрещён для нового fast tick.

Runtime gate matrix: 100 FastChoice fixtures grammar/no reasoning; 20 text+image запросов на одном projector с scene corrections; 20 tool round trips (no tool/error/parallel proposal); verified separation reasoning vs spoken output; 10 cancellation/restart tests с busy-slot accounting; snapshot/model limits, reported KV/prefill/decode/cache metrics; mixed workload. Один JSON ответ подтверждает лишь один case. [Upstream function-calling](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md) и model template не гарантируют native parser в установленном LM Studio. Если инструментальный parser слабый, L1 выдаёт typed JSON proposal, broker исполняет разрешённое, следующий L1 получает result data; raw model tool_calls не обязательны для реализации user tool requirement.

## Исполнительные платформы: уточнение boundaries

[Hermes programmatic integration](https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration) описывает `/v1/runs`, lifecycle events и capabilities. Adapter предпочитает run API, отделяет durable submitted intent от terminal outcome и сверяет поддержанные функции. Existing text-only brains.py не предоставляет эту гарантию. [API server documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/) указывает идемпотентное создание run с ограниченным retention и cooperative stop: hub не должен повторно submit после неизвестного результата за пределами окна dedupe. Локальный intent ledger долговечнее executor idempotency cache.

[Hermes security](https://hermes-agent.nousresearch.com/docs/user-guide/security/) документирует terminal backends, hardening и env passthrough, включая skill-declared variables. Поэтому пустое forward_env само по себе не доказательство отсутствия secrets. Наш executor profile отключает сторонние auto skills, фиксирует toolset и проверяет фактический container env/mounts/egress; собственный broker сохраняет typed-command restrictions. «Sandbox» не означает произвольный shell безопасен.

[OpenClaw agent loop](https://docs.openclaw.ai/concepts/agent-loop) описывает serialized per-session runs; [Gateway protocol](https://docs.openclaw.ai/gateway/protocol) — отдельный RPC/auth boundary. Для adapter нужны run/session binding и confirmed result. [Abort operations](https://docs.openclaw.ai/tools/subagents/operations) различают exact-run и session-wide cancellation; ordinary chat.abort без runId не равен остановке всех descendant tasks. Поэтому registry задаёт cancel scope, а supervisor отслеживает children. Не переносить их операторские stop commands на robot mute: hub делает физическое прекращение самостоятельно.

Сторонний executor начинает с metadata-only evidence, без host shell/robot credentials/личных memory writes. Fairness и budgets upstream не отменяют admission робота. Наличие session memory/heartbeat/cron не реализует fresh FastChoice по sensor snapshot на каждом tick. Рекомендация собственного scheduler сохранена, optional Hermes выбирается только после run lifecycle/sandbox acceptance; OpenClaw при запросе каналов и отдельной compatibility matrix.

## Разделение чисел и пересмотр SLA

Measured live values второго прохода: **нет** GPU/CPU/model latency/VRAM samples; только network failure outcomes. Public constants — file hashes/sizes, model config и documented API. Estimates — KV arithmetic, queue budgets и token throughput examples. Targets — fast SLA/control/naturalness. Итоговый deployment period выбирает конечный benchmark, не одно опубликованное tok/s.

Реалистичная арифметика warm fast: `Tfast = network + prefill(new_suffix)/Rprefill + output/Rdecode + schema/guard`. Иллюстрация без замера: 300 новых tokens при 1500 tok/s, 48 output при 150 tok/s, прочее 100 ms →620 ms; period ≥620/0,7≈886 ms, 1 Hz feasible. При 500 tok/s и 70 decode tok/s тот же request ≈1,39 s; sustainable period ≥1,99 s, около 0,5 Hz. Cold static prefix и CPU contention добавляют время. 192 output cap может занять больше всего периода; common choice должно быть существенно короче. Отдельно считать `llm_calls/day`, context_tokens_processed и energy, не только accepted decisions.

Прежняя цель first speech ≤2,5 s была несогласована с ожиданием следующего L0 tick и L1. Теперь baseline E2E **target P95 ≤5 s после конца речи**, stretch ≤2,5 s только после измерения streaming pipeline. Worst-stage illustration: VAD tail 0,5 + STT 0,8 + tick wait до1,0 + L0 0,6 + main first segment1,5 + TTS/network0,4≈4,8 s. Это сумма иллюстративных задержек, не P95 из статистики. Предварительный взгляд/пауза обычно раньше речи; ack не обязателен. Ускорять можно partial stable-prefix speculation L1 в фоне, но новая речь/tools не commit до final evidence и current epoch.

Main caps и точное admission inequality определены в contracts «Полный бюджет main context» и design-config. 32K — отдельный measurement profile (text30720 + vision1024 + template256 + output512 + reserve256); он требует Q02/Q04 и не включается автоматически. Фактическая image/template стоимость зависит от локального runtime, превышение требует reprojection/recount или отказа до inference.
