# Live baseline Reachy / Hub / PC — 17 октября 2026

Финальная проверка: **03:17:24 MSK (00:17:24 UTC), 2026-10-17**. Единственный владелец устройств в этом проходе — чат `01a14732-f696-7dd0-9003-c2868120dd62`. Один ограниченный голосовой прогон, без участия человека. Исходники, конфиги, архитектура, calibration и защиты не менялись; build, redeploy, очистка и загрузка моделей не выполнялись.

**Итог:** восстановлен работающий Docker Desktop и прежний worker; Hub, Agent и factory daemon работают. Получен кадр камеры, наблюдались реальные изменения положений антенн/головы, выполнено ALSA-воспроизведение короткого вопроса. **Ответный живой голосовой цикл не принят:** существующий контроллер отказал с `GuardDenied`, ответное воспроизведение не наблюдалось. Постоянно слушающий/смотрящий/двигающийся режим не достигнут. После штатной очистки службы оставлены включёнными, microphone/listening/capture и разрешение motion Agent — OFF.

## Исходный handoff и установленный runtime

Прочитаны свежие итоги чатов `01a12596-fe7e-7592-ae4d-27652600c257` («Reachy — запуск и проверки на устройствах») и `01a14364-fc76-77b3-b9dc-ff7c45f0477c` («Reachy — приёмка рабочего MVP»), `hardware-handoff-2026-10-10.md`, `live-demo.md`, `normal-companion-runtime.md`, эксплуатационные разделы README и установленный конфиг Hub.

Последний runner был прерван после остановки/запуска Docker: готовность worker не была подтверждена. Историческая операция CREATE имеет UNKNOWN; этот аудит её не повторял, не очищал operation slot и не объявляет её разрешённой. Ранее принятые с человеком vision/streaming-сценарии не засчитаны как сегодняшнее доказательство.

| Узел | Фактически установленное и наблюдавшееся |
| --- | --- |
| Hub `192.168.2.181` | `/home/deploy/reachy-companion`, `reachy-hub.service` active, процесс Hub PID 78887; voice router PID 24629. Существующая `.venv-router`; inference на Hub не запускался. |
| Reachy `192.168.2.158`, только через Hub | `/home/pollen/reachy-companion`; `reachy-voice-agent.service` active, PID 199098. Factory `reachy-mini-daemon.service` active, MainPID 150625; реальный daemon/SDK **1.11.0**, simulation/mockup false, backend ready, motors enabled на уровне factory. |
| PC `192.168.2.134` | Docker Desktop **4.88.0.237115**, Linux engine. Прежний контейнер `reachy-alice-two-ro-e589fef15c1d4f85baa7cf48244fdb5d`, ID `c46d9afc583eabd612cebae22ea6609b188769f54eac842010d65ec4ce443fc9`, image `sha256:0e42c38ae2b0b91873ba3cda454edf2cc3646ed4016a038a3dd12f3214120e3d`. Rootfs read-only; существующие read-only overlays `config.py`/`voice.py` в `/app/src` и `site-packages`, существующий writable `/config`. Это установленная сборка с overlays, не утверждение о совпадении с HEAD. |
| Модель PC | LM Studio `/v1/models` вернул `qwen3.5-9b-uncensored-hauhaucs-aggressive`. Новые load/unload или генерационные пробы не выполнялись. Текущий контекст/placement отдельно не переизмерялись. |
| Endpoint’ы | Hub `:8080`, voice router `:8081`, Agent `:8090`, PC worker `:8082`, LM Studio `:1234`. Токены использованы из существующих файлов, не раскрывались. |

Установленные SHA-256:

```text
Agent agent.py       4e2dcafdde29ba667ae40c240723954d48b8462f9641e50ffb32e56fe0ce575a
snapshot_vision.py   d43a70cc1e3b3846cb163f8b772c9af2b13a08aefac2c4279f6197b68b974c13
spoken_vision.py     486cfb8f23c9d9d5797910eab6ebf3143e64f1cfe4a686b4f50fe38db975a025
Hub client.py        adc324fc93ec4dfc1d88249deaa4a7925e8d44e92dc15946877cef574fac1c4f
Robot config         7f11d114873cc20de66e4789166ed5bbbd32109f708f82991aeb5ab3217d3b5e
Agent boot hash      db8325cf60023a16c92d00af1b7b6411c32260159d77221f48e15bb503f71bde
```

## Что запускалось

1. Read-only SSH/status/health на трёх узлах. Старый `/private/tmp/reachy-live-hub/password_ssh.py` отсутствует; использован существующий `scripts/factory_ssh.py`. Ключ робота взят из уже доверенного known_hosts Hub и сверён с fingerprint handoff `SHA256:GlOd19ZK0wlxeX+vk0jathiD6sF/2Zynfyvaf0VBKLg`. Новые ключи или credentials не создавались.
2. Один штатный `docker desktop start --timeout 30` на PC вернул 0 и поднял прежний контейнер. После завершения SSH процессы Desktop исчезли, порт 8082 стал недоступен: этот запуск оказался привязан к сеансу. Повторной остановки Docker не было.
3. Установленный `C:\Program Files\Docker\Docker\Docker Desktop.exe` запущен через штатный Windows `Win32_Process.Create` (`Invoke-CimMethod`) вне job SSH. ReturnValue 0, PID 7320. Новые задачи/службы не регистрировались. Прежний контейнер автоматически поднялся своей существующей политикой; StartedAt `2026-10-17T00:14:05.591565216Z`. В 00:17:24 UTC после нескольких завершённых SSH-соединений тот же контейнер оставался running, RestartCount 0, Desktop PID 7320 присутствовал. Worker дал HTTP 200/idle с Hub.
4. Один существующий конечный сценарий:

   ```text
   python3 <runner>/Alice-factual-resume/run.py --execute --case sky --expected-mic 208 --expected-policy 112
   ```

   `<runner>` — каталог квитанций, указанный ниже. Pins launcher/watch/client/controller совпали. Сценарий создал штатный независимый watch; первый ON был `listen=false`, затем bound `/say` с фразой **«Алиса, почему небо голубое?»**, затем guarded `/resume`. Это единственное новое обращение к Алисе в данном аудите.
5. После отказа контроллера отправлен SIGINT только собственному локальному runner PID 68415. Его штатный `finally`/device watch выполнил cleanup. Нового voice-прогона не было.
6. Отдельно один раз вызван существующий `snapshot_vision.capture_png()` в mount namespace действующего Agent через `nsenter -t 199098 -m`, с microphone/capture/listening OFF, без owners и без privacy. Камера закрыта, кадр остался в RAM робота; никакого image inference, экспорта изображения или записи pixel-файлов не было.

Основная Windows task `Reachy Companion` уже была Disabled после предыдущего обслуживания и осталась Disabled. Историческая `ReachyBaselinePostACL-…` не запускалась. Монитор/heartbeat не менялся. Robot/Hub службы не перезапускались.

## Доказательства отдельных каналов и сквозного цикла

| Канал | Свежий результат и граница доказательства |
| --- | --- |
| Микрофон | После cue контроллер наблюдал actual capture, 34 role-qualified наблюдения capture-процесса; отдельный `/status` показывал `phase=recording`, capture/listening/microphone true, epoch 209. Это подтверждает запуск живого capture-пути, но не измеренный ADC energy/число полученных PCM frames и не успешное распознавание ответа Алисы. |
| Камера | Один frame получен через установленный camera-only reader: выход 640×360 PNG, 533745 bytes в RAM, capture/encode/close **1.872 s**, camera_closed true, raw_files 0. Исходный SDK reader проверяет 1280×720 BGR. Время exposure/семантика сцены не подтверждены. Полное равенство operator до/после вернуло false; изменившееся поле helper не сохранил, поэтому неизменность всей authority при camera-пробе не заявляется. После неё OFF/owners absent и конечные epochs подтверждены отдельно. |
| Движение | В 15 read-only выборках существующего `/status` антенны изменились с `[-0.067495, 0.125786]` до `[-0.223961, 0.294524]` rad: примерно **8.96° / 9.67°**. Head yaw изменился с `0.003532` до `0.073429` rad, примерно **4.00°**. Наблюдались action_running и один owned stock UUID. Это actual factory robot telemetry, а не только команда движения; внешней визуальной верификации и нового stop-SLA нет. Runner terminal сам оставляет physical_motion_verified=false: отдельная телеметрия не переписывает его verdict. |
| Голос | Bound `/say` завершился успешно с точной собственной cue, producer/worker затем idle, собственный APLAY отсутствовал перед resume. 80 role-qualified playback samples, наблюдавшийся span **2.138112 s**. Это реальное ALSA output execution; span — нижняя граница по процессным выборкам, не измеренный DAC cursor или acoustic onset. Без независимого акустического свидетеля слышимость в комнате не объявляется полностью принятой. |
| End-to-end | **FAIL / не подтверждён.** `cue_sent=true`, `resumed=true`, actual_capture_observed_after_cue=true, но `APLAY_observed_after_resume=false`. Контроллер завершился `GuardDenied` на `observe_first_true_reply_playback`, elapsed **11.764555 s**, cleanup также получил GuardDenied. Сценарий имел исходно turns=1; после cleanup осталось turns=1. Последний worker turn — собственная фиксированная cue, не ответ Алисы и не новая STT→LLM реплика. Speaker identity unknown. |

Контроллер сохраняет только `failure_reason=OTHER`, теряя конкретный `GuardDenied.code`, endpoint и elapsed. Поэтому причина не сведена к «Алиса не ответила», STT, worker или конкретному freshness timeout. Код watch содержит, в частности, 300 ms operator freshness и authority guards; какой именно отказ сработал, **неизвестно**. В этом аудите guards не ослаблялись и код не исправлялся.

Native run ID: `34ee6532d85e483398284a8630696056`. После SIGINT `companion-demo-terminal`: child_returncode 130, **cleanup_verified=true**. Watch elapsed **73.956656 s**; это длительность ограниченного запуска до завершения, не voice latency. Natural terminal completed=false. Сквозная задержка от конца ответа Алисы до речи Reachy не измерена. Синтетический HTTP/PCM тест вместо диалога не выполнялся.

## Финальное состояние

В 00:17:01–00:17:24 UTC:

- Agent paused; microphone=false, capture=false, listening=false, epoch **210**; motion motor_enabled=false, quiet=false, privacy_all=false, epoch **114**; owners absent; volume **100**, ошибок Agent/microphone-state нет.
- Watch: final_OFF, admission_retired, aplay_absent, factory_running_empty, volume_preserved — true; stock_unknown=false. Дополнительное factory API чтение: running moves **0**. Два последовательных operator чтения не различались.
- Hub/factory active, ownership free, action_running=false, backend ready; media available=true/released=false/no_media=false.
- Worker idle, error отсутствует. Desktop и прежний контейнер running после отключения запускавшего SSH.

Таким образом, восстановлена вычислительная часть и сохранены включённые службы. **Это не готовый постоянный companion:** штатный конечный тест завершил microphone/motion permission в OFF; камера проверена одним кадром, непрерывное зрение не запускалось. Не выполнен дополнительный неограниченный handoff в listening после сорвавшейся проверки.

## Логи и квитанции

Существующий runner-каталог:

```text
/Users/notanonenough/.codex/visualizations/2026/10/10/01a12596-fe7e-7592-ae4d-27652600c257/runner-20261015/
```

Свежие файлы в нём:

- `actual-natural-Alice-phase-sky-controller.json` — cue/capture/GuardDenied, без raw transcript.
- `actual-natural-Alice-34ee6532d85e483398284a8630696056-terminal.json` — конечный FAIL и успешный cleanup.

Свежие локальные metadata receipts, временное хранение:

```text
/private/tmp/reachy-live-baseline-20261017/camera-metadata.json
/private/tmp/reachy-live-baseline-20261017/final-readonly.json
/private/tmp/reachy-live-baseline-20261017/robot-final-readonly.json
/private/tmp/reachy-live-baseline-20261017/pc-final-readonly.json
```

Robot-native receipts (root-only, не раскрывать `plan.private.json`/owner):

```text
/run/reachy-companion-demo-34ee6532d85e483398284a8630696056/natural-Alice-phase.public.json
/run/reachy-companion-demo-34ee6532d85e483398284a8630696056/watch-result.json
```

Robot journald: `reachy-voice-agent.service`, `reachy-mini-daemon.service`, `reachy-companion-demo-34ee6532d85e483398284a8630696056.service`. Hub journald: `reachy-hub.service`. Read-only motion samples и команды восстановления также сохранены в tool transcript этого чата; отдельного raw-motion файла не создавалось. `/run` и `/private/tmp` могут быть очищены системой; ключевые результаты продублированы здесь. Секреты, PCM и camera pixels в отчёт не включены.

## Точная следующая задача

**Исправить диагностический finite Alice controller, сохранив все существующие guards:** при первичном `GuardDenied` и отказе cleanup записывать `.code`, `.elapsed`, список изменившихся имён полей и `IO.last_endpoint_by_thread`, без nonce/текста/токена; гарантировать штатный finish после отказа controller, не оставляя launcher ждать до ручного SIGINT. Проверить этот путь офлайн на отказах operator freshness/HTTP/authority. Здесь исходники не менялись.

Затем единственному владельцу стенда сделать свежий read-only preflight текущих boot/epochs/worker и **один** короткий повтор с Алисой, сохранив actual capture energy/frames, STT→worker join и ответный playback. Только его результат позволит определить runtime-блокер и подготовить штатный постоянный listening handoff. Восстановление прежнего PC maintenance bookkeeping/disabled startup task и исторического CREATE UNKNOWN остаётся отдельной незавершённой задачей; включение автозапуска не вытекает из успешного Desktop start.
