# M0 — camera/audio coexistence, source-ready

17 октября 2026. **SOURCE READY / hardware acceptance OPEN.** Только офлайн: SSH, HTTP к стенду, устройства, службы и установленный runtime не использовались и не менялись. Q1 сохраняет эксклюзивный аппаратный доступ. №3 DELIVERY-PLAN целиком этим результатом не закрыта.

## Причина и выбранный путь

В `deploy/autonomous/video_server.py` старый `Producer.operator()` разрешал камеру исключительно при `microphone_enabled=false && capture_active=false`. Это policy самого producer, а не техническое требование reader: он уже использует `GStreamerCamera` из штатного daemon IPC и не создаёт audio backend или аппаратный camera source. Поэтому выбран адресный патч **этого существующего camera producer**, с тем же transport, `/policy`, `/latest` и PC decoder. `camera_relay`, новый transport, semantic VLM и audio core не нужны для этого отдельного среза.

Проверен официальный [SDK v1.11.0 camera reader](https://github.com/pollen-robotics/reachy_mini/blob/v1.11.0/src/reachy_mini/media/camera_gstreamer.py): `unixfdsrc`, appsink с `max-buffers=1/drop=true`, `close()` переводит собственный reader pipeline в NULL. Это подтверждает устройство API, **не** аппаратную совместимость с нашим `arecord`.

Установленный R1 — другой entrypoint: `snapshot_vision.py` (локально `deploy/autonomous/demo_vision.py`) и `spoken_vision.py`. Их bytes совпали с manifest R1. Snapshot reader сам не выключает микрофон; spoken admission требует ON/listening, но также `capture_active=false`, `phase=processing` и связанного owner. Синхронный Agent caller держит audio lock до возврата child. Ослабление только `spoken_vision.check_operator()` не создаст параллельный PCM capture. Эти guards и caller оставлены без изменений.

**Граница поставки:** runtime-baseline не фиксирует установленный `video_server.py` и не утверждает, что он запущен. M0 готовит уже существующий независимый producer к следующей конечной проверке; это не патч, который можно применить вместо установленного `snapshot_vision.py`. Подключение producer в нужном mount namespace, выбор единственного reader и наблюдение штатного audio owner относятся к следующему аппаратному scope. Полный непрерывный PCM во время STT/main/TTS может потребовать отдельного изменения audio core; M0 его не подменяет camera patch.

## Diff и pins

HEAD при подготовке: `59bc59a6433dee432371319ba48ad0aeab0985f4`. Переносимый [patch](../../deploy/patches/m0-video-producer-e5e8-coexist.patch), один production-файл: `deploy/autonomous/video_server.py`, **72 добавленные / 15 удалённых строк**. Дополнительно: шесть целевых offline tests в `tests/test_camera_coexist.py`; по одной строке в двух существующих тестах для изоляции remote policy от нового local operator gate.

| Артефакт | SHA-256 |
| --- | --- |
| Producer preimage, HEAD, не установленный manifest | `e5e8c1703fa1b65f10be4fce5b8598f45679fca894d7699837a95911a92f9228` |
| Producer candidate | `6182a6516d93d4ab065c1ba5ba0c3c6fe8ebfb57e28f08d7dea8f83a8139ae56` |
| Portable patch | `2fd8059bb0c61ec4b3f1461268a2cfe6613dcddeb88e8bddc59ba905f75976f3` |
| R1 snapshot, неизменённый | `d43a70cc1e3b3846cb163f8b772c9af2b13a08aefac2c4279f6197b68b974c13` |
| R1 spoken, неизменённый | `486cfb8f23c9d9d5797910eab6ebf3143e64f1cfe4a686b4f50fe38db975a025` |
| R1 Agent, только reference из baseline | `4e2dcafdde29ba667ae40c240723954d48b8462f9641e50ffb32e56fe0ce575a` |

Изменение:

- ON/OFF микрофона больше не является предварительным запретом камеры. Только read-only `/operator`, bounded response ≤16000 bytes и свежесть чтения ≤300 ms. Ни одного audio/control POST.
- Первый local snapshot привязывает admission к Agent boot, microphone epoch, policy epoch, совпадающей паре owner IDs и положению mic switch. Обычная unowned пара `None/None` допустима; моторное разрешение для видео не требуется. `capture_active/listening/phase` могут естественно меняться при обработке речи.
- Ошибка/просрочка operator read, local authority change и local privacy/quiet отзывают admission. Вернувшийся старый snapshot не возобновляет его. Remote privacy тоже требует нового `admission_id`; прежние owner/epoch/seq/retired-admission fences сохранены. После замеченного opt-out или истечения lease capture закрывается и тоже требует нового admission.
- Проверка operator повторяется после sample и до publish. Старые generation/scope frames не публикуются; `/latest` закрыт при просроченной local authority. Один replaceable RAM slot, прежняя remote lease 1.5 s и frame receipt TTL 2 s. Интервал capture loop снижен с 500 до 100 ms, чтобы обслуживать local authority TTL; это верхняя частота около 10 samples/s, её реальная стоимость требует hardware измерения.
- Не более одного `capture()` в одном producer. Единственным hardware camera source остаётся factory daemon: reader использует его IPC, не `libcamerasrc`/V4L2 и не relay. Межпроцессный выбор ровно одного consumer не доказывается этим lock: оператор обязан не запускать второй producer/legacy snapshot child; существующий bind одного loopback port также исключает второй экземпляр на том же endpoint.
- Каждый путь закрывает SDK reader; NULL подтверждается `get_state(1s)`. Неизвестный shutdown терминален, отражается `reader_shutdown_unknown=true` и exit 2, без повторного открытия.
- PTS, segment running time, consumer clock/base, reader/producer boot, frame seq/ID, lineage и SHA сохранены. Physical exposure timestamp отсутствует: `source_capture_time_verified=false`, upper age unknown. Новый receipt/ID не делает старый кадр свежим. PC `video_adapter.py`/`perception.py` не изменялись.

## Офлайн-проверки

```sh
PYTHONPATH=src:tests:/private/tmp/reachy-head-validate-20261015/lib/python3.13/site-packages python3 -m unittest test_camera_coexist test_video_adapter test_perception test_demo_vision test_spoken_vision
```

**44 tests, OK, skipped=0, 0.925 s.** Первое выполнение системным Python обнаружило отсутствующий `jsonschema` в двух прежних tests; окончательный прогон использует уже имеющийся local dependency directory, без установки пакетов и подмены validation.

Шесть новых тестов исполняют настоящий producer loop с offline SDK/sample fixtures: mic ON/capture ON остаются неизменными при трёх последовательных кадрах; повторный reader отвергнут; local privacy, remote revoke, mic STOP/epoch, camera opt-out и lease expiry закрывают reader и отбрасывают in-flight sample; authority ABA и медленный read не возобновляют admission; remote privacy false без нового admission не возобновляет capture; latest slot вытесняет предыдущий и истекает; PTS/unknown exposure provenance проходит настоящий PC packet decoder; неизвестный NULL shutdown терминален. Два прежних source-policy tests сохраняют отдельную проверку generation/epoch/retired-owner fencing.

Patch dry-run/application и reverse dry-run/application выполнены **только во временной локальной копии**, `--batch --fuzz=0 -p1`; candidate/preimage bytes совпали с hashes. `git diff --check` для изменённых исходников/тестов — OK.

Локальные evidence и manifest: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a14750-1d74-7971-9923-8aa8a943a333/M0-evidence/`. Это проверки source behavior, без live PCM, camera exposure или акустической приёмки.

## Следующий конечный hardware acceptance — только после передачи от Q1

Один finite window, максимум 60 s, без второго Agent, camera relay, SDK audio owner или перезапуска factory daemon.

1. Зафиксировать свежие boot/epochs/owners, privacy, working Agent/audio owner и factory camera PID. Проверить фактический `/operator` и SDK 1.11.0. Сохранить preimage выбранного producer; применять patch только к точному `e5e8…` либо stage уже проверенный `6182…`. Несовпадение source, UNKNOWN jobs или namespace/socket недоступность — закончить окно без bare retry. Не копировать camera patch на `snapshot_vision.py`.
2. В существующем видимом factory IPC namespace запустить **один** этот finite producer на существующем свободном loopback endpoint, duration **45 s**, с отдельным video token и явной local camera policy. Использовать его прежний CLI (`--production-root`, `--policy-file`, `--token-file`, `--output`, `--port`, `--duration 45`), без новых installation settings в M0. Existing PC context consumer обновляет тот же `/policy` с новым admission каждые ≤0.5 s и читает `/latest`; не обходить auth/lease. Визуальную STT-команду legacy helper в этом окне не давать.
3. Первые **30 s** штатный mic остаётся ON. Зафиксировать минимум 10 разных decoded `(producer_boot_id, seq, frame_id)` с PTS/unknown capture-age, max raw slot=1. Через разрешённое наблюдение **существующего** audio owner зафиксировать продвижение фактических PCM sample counters/байтов при camera reads и один обычный STT→main→TTS turn с продолжающимися кадрами. Одни `microphone_enabled/capture_active=true` и frame IDs не являются доказательством непрерывного PCM/физической свежести. Не менять mic switch ради кадра. Если baseline не даёт PCM progression receipts или capture действительно прекращается при STT/TTS, это измеренный audio-core gap, не PASS M0 и не повод писать второй recorder.
4. На **30-й секунде** существующим control путём выполнить один STOP/mic OFF: прежний admission должен перестать выдавать кадры, reader закрыться. Далее отдельным **новым** явным camera admission проверить remote privacy=true/false: privacy убирает `/latest`, false со старым admission не возобновляет его. Выход допускается только после нового admission и явного разрешения оператора. Измерить detection/reader-close latency, отсутствие поздней публикации и NULL; не объявлять жёсткую realtime гарантию. Poll/read/open/close имеют конечные ожидания, включая SDK open до ~2 s, HTTP read до 1 s и NULL check до 1 s.
5. К **45 s** finite producer завершён, HTTP listener и reader отсутствуют, `capture_thread_reaped=true`, `reader_shutdown_unknown=false`. В пределах общего **60 s** окна подтвердить cleanup, unchanged factory owner и итоговое control состояние. Возврат штатного слушания после тестового STOP — отдельный свежий guarded ON штатного оператора, не автоматический camera resume. Записать реальные counters/latency/hashes и вердикт; source tests не засчитывать в эти числа.

## Rollback и следующий scope

После отзыва только собственного video admission дождаться NULL/reap конечного producer, убрать только его listener и временную local camera grant. Не останавливать daemon/Agent/Hub/PC и не менять mic автоматически. Восстановить сохранённый producer preimage либо применить обратный patch с `--fuzz=0` только при hash `6182…`; проверить `e5e8…`. Если выбранный producer отсутствовал в R1, достаточно убрать stage/собственный finite process после известного cleanup. Неизвестный close оставляет HOLD и evidence, без второго reader.

Следующий scope: finite совместная аппаратная проверка выбранного producer с фактическим штатным audio owner и mount visibility. После неё — отдельное подключение в normal session. Если для непрерывного PCM нужен lifecycle/capture_pump/Agent audio-loop change, вернуть координатору конкретный interval/counters и разрешить именно этот следующий scope. Существующий synchronous spoken snapshot не объявляется исправленным данным patch.
