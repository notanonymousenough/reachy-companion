# Reachy Companion — журнал архитектурного review

17 октября 2026, Europe/Moscow. Результат: [полный дизайн v4](/Users/notanonenough/reachy-companion/docs/coordination/design-2026-10-17.md). Только документация: исходники, устройства, сервисы и файлы других специалистов не менялись.

## Решение

Рекомендую завершить существующий `reachy_companion.autonomous`: Robot media/actuator owners → Hub Scheduler/State → PC Qwen3.5-0.8B Q8 CPU/2 s + существующая 9B/Whisper/Piper. Один запасной путь — официальная Conversation App + локальный speech-to-speech с адаптером автономии и Piper. Переключаться только по конкретному отказу voice/media integration и конечному fit check. Более низкая стоимость разработки текущего пути — инженерная оценка по наличию кода, без обещаний сроков.

Первый результат: один живой цикл с продолжающимися микрофоном, кадрами, разрешённым движением и LLM-решениями в тишине; два коротких обращения к рядом стоящей Алисе через speaker/mic робота. Затем тот же путь работает как постоянная служба. Semantic scene/music, полный stock motion set, model/TTS overlap, память/цели/persona evolution и S3/VPS сохраняются отдельными обязательными этапами.

## Обоснованные изменения относительно v3

| Изменение | Основание и следствие |
|---|---|
| Обязательная миграция на App снята с первого запуска | В workspace уже есть Scheduler/State/gateway, SQLite memory, video cache и normal-session interfaces. Переписывание до live добавляет работу. [Runtime](/Users/notanonenough/reachy-companion/src/reachy_companion/autonomous/runtime.py), [session](/Users/notanonenough/reachy-companion/src/reachy_companion/autonomous/companion_session.py) |
| App сохранена как конкретный запасной путь | Официальный [local guide](https://huggingface.co/blog/local-reachy-mini-conversation) подтверждает App на Robot и voice engine на PC. В [handler](https://github.com/pollen-robotics/reachy_mini_conversation_app/blob/main/src/reachy_mini_conversation_app/conversation_handler.py) idle tool не отправляет turn модели, а say не гарантирует дословный текст: необходимы timer/admission adapter и literal TTS для Алисы |
| Fast конкретизирована: 0.8B CPU/2 s вместо абстрактных 0.6B и 1–2 Hz | [Проектные пробы и audit corrections](/Users/notanonenough/reachy-companion/docs/autonomous-companion/pc-live.md) фиксируют semantic failures Qwen3-0.6B и историю Qwen3.5-0.8B. Старые результаты не являются текущей независимой приёмкой. [Официальная карточка 0.8B](https://huggingface.co/Qwen/Qwen3.5-0.8B) подтверждает модель, но не наш latency |
| Разведены Robot и отдельный Pi Hub | Текущая топология и runtime interfaces размещают orchestration на Hub, physical control на Robot, inference на PC. Перенос всего в embedded Pi больше не подразумевается. [README](/Users/notanonenough/reachy-companion/README.md) |
| Persistent memory признана частично реализованной | [SQLite MemoryStore](/Users/notanonenough/reachy-companion/src/reachy_companion/autonomous/memory.py) уже существует. Upstream [memory.py](https://github.com/pollen-robotics/reachy_mini_conversation_app/blob/main/src/reachy_mini_conversation_app/memory.py) — ограниченный fact store; два независимых writers не нужны. Episodes/goals/evolution ещё требуют работы |
| Одновременные слух и камера стали явным первым gap | Старый [camera admission](/Users/notanonenough/reachy-companion/docs/autonomous-companion/context-live.md) требует mic=false. [Media stack](https://huggingface.co/blog/pollen-robotics/reachy-mini-media-stack) даёт готовую основу, однако наша совместная работа не доказана. Freshness unknown не превращена в свежую scene summary |
| Alice smoke отделён от combined acceptance | [finite_alice_trial.py](/Users/notanonenough/reachy-companion/src/reachy_companion/finite_alice_trial.py) разрешает один exact arithmetic cue, audio-only и motors disabled. В v4 задан normal-session тест двух раундов без человека, с коротким префиксом «Алиса, ...» и actual playback/capture evidence |
| Уточнена совместимость запасного TTS | [S2S external TTS contract](https://github.com/huggingface/speech-to-speech/blob/main/docs/openai-compatible-tts.md) принимает PCM/WAV через audio/speech; наш NDJSON stream/say требует адаптера. Cancellation consumer не равен terminal backend. Piper сохраняет русский голос без дополнительной GPU модели |
| Community-кандидат актуализирован и исключён из пути запуска | Physical AI OS переименован в [lampOS](https://github.com/autonomous-ai/lampOS); README указывает Reachy port и ONNX conflict optional Pipecat. Проверенной эквивалентности нашим local/continuous требованиям нет |

## Tradeoffs и границы исследования

Текущий путь сохраняет собственную интеграцию и её поддержку. Запасной даёт готовые voice/tools/profiles, но требует hooks, единого authority и protocol adapter; он не доказанно быстрее. CPU fast уменьшает давление на VRAM, но конкурирует за CPU с STT/TTS; hybrid оставлен измеряемой оптимизацией. SQLite/journal достаточны для начального объёма, без обязательного нового брокера и vector DB.

Платные API и новое железо для первого пути не требуются. Суммы за электричество, S3/VPS и end-to-end p95 неизвестны; в дизайне приведены границы метрик и формулы расходов без выдуманных цен. Заявленный русский язык [Qwen3-TTS](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice) не доказывает голос/latency/VRAM нашего стенда; менять Piper до первого цикла не требуется.

Проверены официальные README, handler/tools/memory interfaces, media guide и dependency declarations. Просмотренные main-файлы объявляют [App 1.1.0, SDK ≥1.11.0](https://github.com/pollen-robotics/reachy_mini_conversation_app/blob/main/pyproject.toml) и [speech-to-speech 1.0.0](https://github.com/huggingface/speech-to-speech/blob/main/pyproject.toml); это не deployment pins. GitHub commit API недоступен исследовательскому инструменту, поэтому exact upstream SHA не утверждается. Исполнитель фиксирует SHA/locks до установки; исследование на этом завершено, без нового обзора frameworks.

Исходный дизайн сохранён: SHA256 `050d88b00ac401ab464be0ff048ea02a741236413cbfb50524d4c0613667cda2`. Все 19 смысловых разделов перенесены в полную версию. STOP/privacy, bounded queues/context, UNKNOWN, provenance, изменяемые цели, overload barrier и versioned S3/VPS bundles сохранены. Текущую readiness и конкретного аппаратного owner определяют параллельные аудит и baseline.
