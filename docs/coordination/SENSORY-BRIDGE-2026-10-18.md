# Sensory bridge: source-only контракт

Файлы: `src/reachy_companion/r42/sensory_loop.py`, `tests/test_sensory_loop.py`. Agent/initiative/voice/manifest не менялись; устройства/модели/старый autonomous profile не запускались. Это интегрируемый модуль, не доставленная живая способность.

`SensoryLoop(decision, execute)` стартует без разрешения outputs. Trusted owner вызывает `set_authority(binding, enabled=..., privacy=...)`; binding содержит актуальные boot/MIC/policy/mode epochs, без ключей. Только фактические controls определяют enabled/privacy. Новая authority, OFF и STOP отменяют выходы; смена authority и OFF очищают старые observations, поэтому ON не переигрывает их. `invalidate()` отменяет текущие/pending outputs, сохраняя ограниченный сенсорный state; например, новый пользовательский foreground turn вытесняет инициативу. После invalidate следующая новая публикация либо явный `request_decision()` запускает новое решение.

Существующий owner публикует данные без ожидания inference/playback:

```python
observation_id = loop.publish({
    'kind': 'vision.semantic',       # либо sound.event / audio.activity
    'source': 'existing-snapshot-vlm',
    'source_event_id': checked_frame_or_capture_id,
    'observed_monotonic': trusted_local_observation_time,
    'summary': checked_short_observation,
    'ttl_s': 2,
})
loop.advance()                      # далее регулярно, например раз в 50–100 мс
```

`observed_monotonic` — время реального события в monotonic domain этого процесса. Для удалённого сенсора adapter обязан установить консервативную верхнюю границу возраста и преобразовать в локальное время; receipt «только что пришёл VLM ответ» не доказывает свежесть pixels. При неизвестной свежести семантику не публиковать как fresh evidence. Не использовать `LatestVideo` pixel metrics как описание человека/предмета. Модуль не открывает дополнительный capture и не подтверждает speaker identity.

`decision(snapshot, cancel_event)` выполняется в одном daemon callback. Snapshot содержит fresh/expired observations, authority/state revision, busy/pending, предыдущие действия. Ответ: `{'action': 'wait', 'why': 'нет свежего события', 'evidence': []}` либо bounded `{action, why, evidence: [observation_id], payload?: dict}`. Non-wait требует актуальных fresh evidence из переданного snapshot. Pending decision один, новые данные его заменяют; при запуске snapshot пересобирается с актуальными ages/busy. Частые `advance()` без новой публикации не делают бесконечные model calls; ограниченный idle trigger — явный `request_decision()`.

`execute(proposal, permit)` — независимый один callback; очередь ожидающего исполнения тоже ровно одна, последнее допустимое предложение заменяет предыдущее. Proposal содержит action/payload, evidence/provenance, decided/expiry time, полный authority binding и revisions. Executor обязан:

- allowlist action/payload; модель не выдаёт permissions и не выбирает произвольный endpoint;
- проверить `permit()` непосредственно перед каждым выходом и после дорогого ожидания; следить за `permit.cancelled` во время работы;
- в существующем Agent/guarded actuator **атомарно** проверить реальные MIC/policy/boot/mode epochs из proposal перед физическим выходом. `permit()` сам не делает атомарной транзакцию с отдельным устройством;
- использовать существующие единичные voice/motion slots и STOP, не создавать второй playback/capture owner; возвращать `True` только после фактического нормального завершения, иначе `False`/exception.

STOP/OFF/privacy, expiry или superseded evidence делают permit недействительным и сигналят cancellation. Python не может насильно остановить произвольный callback: занятый decision/execution lane удерживается до реального возврата callback, включая timeout/close. `close()` отзывает admission и немедленно возвращает управление; это не подтверждение физического stop или backend cancellation. Для штатной аппаратной отмены callback использует существующий stop path; сетевой timeout не считается terminal backend outcome. Sensory publication продолжается, пока callback занят. При privacy observations/history очищены, публикации отклоняются; реальное прекращение capture/remote work остаётся обязанностью текущего control owner.

Локальная проверка: `PYTHONPATH=src python3 -m unittest discover -s tests -p test_sensory_loop.py -v`. Покрыты bounded latest pending при 100 обновлениях, независимость execution/decision/sensors, TTL/expired/fabricated evidence, STOP/OFF/invalidate/новая authority, privacy и callback failures. Тесты синтетические и не заменяют живую приёмку сцены/звука/речи. Модуль пока не добавлен в R42 manifest: TL делает это только вместе с согласованными integration hooks и свежим release.

## R53: подключён узкий source путь

`sensory_bridge.py`, Agent hooks и SoundMonitor реализуют **sound→local model→finite guarded attention**. Opt-in `conversation.sensory_loop.enabled` по умолчанию false. Дополнительные bounded параметры: `model_timeout_s` 6 (1–10), `event_ttl_s` 10 (2–15), `event_cooldown_s` 6 (3–60). TL отдельно решает сохранённую настройку включения; этот source не включает MIC/initiative/motors и не меняет их intent. Модель не вызывается при motor OFF, quiet/privacy, неизвестной/просроченной evidence и foreground speaking/processing. Смена boot/MIC/policy/intent/mode, OFF/STOP и новый foreground PCM отменяют старые proposals.

Реальный существующий classifier отдаёт только class index и категорию sound; bridge не угадывает причину/собеседника. Timestamp консервативно `PCM read_end - window_duration`, источник явно `existing-pcm-classifier-read-receipt`. Нет утверждения о верифицированном времени физического capture. Один event на cooldown предотвращает самоподавление решения частыми окнами. Публикация не ждёт модель; существующая playback suppression и отсутствие sound feed в reply mode сохранены. Значит, это пока **не постоянное восприятие всех звуков во время речи**.

Model callback использует существующий приватный `network.llm_base_url`, `/api/v1/models` и ровно один загруженный instance текущего `llm.model`; затем native `/api/v1/chat`, `store=false`, без integrations и Robot bearer token. Новая модель не загружается. Ответ ограничен wait/attend + evidence ids. Неизвестный terminal outcome после отправки лачит `model_execution_unknown`; следующие events не повторяют inference. Обычный HTTP timeout не освобождает backend admission. Статус `Agent.status()['sensory']` показывает scope/unknown/busy/counters и source state. Наличие процесса/статуса не является аппаратным proof.

Attention использует существующие expression state/version и worker/Hub guarded path, только safe idle и свободный expression slot. Atomic enqueue проверяет реальные controls; scoped permit/expiry дополнительно проверяются через существующий `motor_permitted`. Callback ждёт terminal `completed` текущего ExpressionPlayer, а не считает enqueue успехом; при отмене отзываются будущие выходы, уже начатая конечная операция учитывается до возврата worker. Затем только свой finite state убирается, поэтому expired guard не блокирует следующую обычную речь. Не добавлены voice/camera outputs или новый motor transport. Camera helper сейчас прямо возвращает `source_capture_time_verified=False`; его не представили fresh visual observation.

R53 проверки: `test_r53_sensory_bridge.py` — mocked native model, настоящие Agent authority/admission hooks, busy publication, mode/OFF cancellation, unknown-backend latch, final control recheck, SoundMonitor publication до busy-phase discard. Дополнительно прошли существующие conversation mode и sound regressions. Schedule regressions проходят кроме package-manifest closure: canonical Agent изменён для R53, manifest по поручению оставлен TL; R52 frozen wheel этим не меняется. Живой приёмки R53 пока нет.

## R54 correction: actual thinking-budget failure

Следующая реальная приёмка TL подтвердила речь/движение и реальные sound observations, но model attention не доставился. [Одна native diagnostic отправка](../../R53-loop/diagnostics/native-once-result.txt) вернула полный HTTP200: только `reasoning`, output192/reasoning191, final message отсутствует. Inventory не рекламирует `reasoning.allowed_options`, поэтому native default thinking не был отключён. Это конкретное новое основание сменить короткий decision path, а не повторять native probe или сбрасывать unknown latch. Предыдущий source также ошибочно объявлял parser rejection unknown execution: теперь complete HTTP errors/invalid decision имеют отдельный `model_failure_latched`; timeout/неполный body сохраняют unknown. Ни один latch не перезапускает запросы автоматически.

Выбранный candidate использует **ту же загруженную модель** и уже успешно принятый ordinary voice raw completion protocol: `/v1/completions`, actual config `llm.message_template`, закрытый `<think>…</think>` в `assistant_prefix`, actual stop tokens. Новый profile-local `raw_decision_payload` побайтно совпадает с root `brains.raw_prompt` для тех же SYSTEM/DATA messages; persona/history не добавляются. Native inventory остаётся только preflight для единственного already-loaded instance выбранного config model. Запрос ограничен max_tokens192 и socket timeout≤6с, не меняет модели, не вызывает load и не выбирает произвольный endpoint.

Полный ответ принимается только при exact model identity, одном choices[0], index0, finish_reason=`stop`, bounded text и валидном wait/attend JSON. `length`/config/parser failures лачатся без повторения; полный HTTP200 не выдаётся за uncertain transport. Content-free status: model_protocol/failure_class/http_status/body_bytes/response_complete/model_failure_latched/model_execution_unknown; raw response/inputs не журналируются.

[raw_once.py](../../R53-loop/diagnostics/raw_once.py) вызывает **тот же candidate payload helper** с синтетическим non-actionable DATA, без Agent/voice/actuator calls. Default — inventory/config only; `--submit-once` делает ровно один raw request после штатного known-idle admission TL. До install можно передать `--candidate-source PATH_TO_CANDIDATE_sensory_bridge.py`; код загружается только для точного formatter. Script не сбрасывает latches, не делает retry и не печатает prompt/response text. Candidate проверен 12 R53 source tests, включая точное совпадение с принятым voice formatter и uncertainty labels. Actual raw-protocol result и одна integrated live reaction ещё требуются; при отсутствии полезной реакции fallback — observation-only с сохранёнными speech/movement, без новой цепочки probes.

Для решения добавлена маленькая map14 YAMNet classes из [официального TensorFlow CSV](https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv): в том числе реально наблюдавшиеся67 Animal и504 Outside/rural/natural, clapping/knock/keyboard/fan/noise. Summary всегда помечает classifier label и `cause/speaker unconfirmed`; unknown index остаётся unknown, «Animal» не объявляет реального животного. SYSTEM велит wait для повторяющегося фона/шума и вероятного собственного недавнего движения. Это интерпретация классификатора, не новое распознавание личности или физическое доказательство причины.
