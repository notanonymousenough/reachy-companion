# Проверки второго этапа

- [x] Router импортируется без установленных piper/vosk/onnxruntime.
- [x] Первый NDJSON event доходит клиенту раньше завершения worker (реальные loopback HTTP servers).
- [x] Неверный токен отклоняется; недоступный worker даёт 503 без inference fallback.
- [x] Формирование Qwen no-thinking prompt и параметры читаются из JSON.
- [x] OpenClaw: user ID и отправка последнего сообщения; Hermes: полный transcript и session header (mock API).
- [x] PCM попадает в один процесс проигрывания; поток без done обнаруживается (тестовый player вместо ALSA).
- [x] При прекращении чтения stream worker снимает lock без записи незавершённого ответа в локальную историю.
- [x] Локальная сборка Docker/arm64, загрузка реальных моделей и полный STT→LM Studio→stream TTS.
- [x] Запуск PowerShell и Docker/x86_64 на Windows ПК.
- [x] Health compute с hub и проверка реальных STT/TTS на ПК.
- [x] Переключение voice.mode=remote, streaming.enabled=true на live hub/robot.
- [x] Захват фраз микрофоном и успешное реальное ALSA-воспроизведение через agent → hub → Windows worker.
- [x] Замер первого PCM chunk настоящего Windows STT→LLM→TTS через хаб: 1,099 s.
- [ ] Живой разговор рядом с роботом, субъективная оценка тембра/громкости и offline/reconnect ПК.
- [ ] Подключение настоящего OpenClaw/Hermes (в этом этапе только задел).

Автозапуск служб включён; полная перезагрузка не проверялась. Адаптеры OpenClaw/Hermes проверены mock API, настоящие агентные runtimes не развёрнуты.

- [x] Коммиты/push GitHub main и настоящий checkout Windows/hub/Reachy.
- [x] Версионируемый профиль обновляется без перезаписи локальной сети/токена.
- [x] Повторный pull/restart Linux без изменения firewall.
- [x] Единый Windows start.ps1: загрузка LLM, worker, повторный запуск.
- [x] Task Scheduler LastTaskResult=0, LLM/worker переживают закрытие SSH.
- [ ] Полная перезагрузка Windows и проверка запуска при следующем login.
