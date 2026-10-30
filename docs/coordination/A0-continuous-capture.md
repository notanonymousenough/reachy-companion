# A0 — непрерывный PCM capture, source-ready

17 октября 2026, Europe/Moscow. **Офлайн-кандидат готов; hardware/live acceptance отсутствует.** SSH, HTTP, deploy, перезапусков, открытия ALSA/камеры и изменения private config не было. M1 сохраняет эксклюзивное владение стендом. Другие чаты/подагенты не создавались.

Входы: [runtime-baseline](runtime-baseline.md), [Q1](Q1-voice-baseline.md), [PROJECT](PROJECT.md), [S1](../../deploy/patches/capture-pump-S1.md) и его exact overlays. Область результата — audio lifecycle Agent и существующий `capture_pump`; worker/model, camera/snapshot/spoken_vision, scheduler/session и README не изменены.

## Переносимый кандидат к установленному baseline

Установленный Agent **`4e2dcafd…`**, а не HEAD `0cc3e643…`. Локальный exact builder восстанавливает `4e2d` по прежней цепочке Git → timing → S1 `cf50` → bound-listening. S1 уже присутствует в этой версии, но сохранённый baseline работает с `capture_pump_enabled=false`. A0 не переносит HEAD Agent и не вводит новый audio framework.

Изменяются **два runtime-файла**. Исторический `src/reachy_companion/capture_pump.py` и старые S1 builders оставлены без изменения, поэтому прежний rollback и воспроизводимость baseline сохраняются. Новый helper доставляется exact patch поверх старого.

| Файл | Exact preimage SHA-256 | A0 output SHA-256 |
| --- | --- | --- |
| `agent.py` | `4e2dcafdde29ba667ae40c240723954d48b8462f9641e50ffb32e56fe0ce575a` | `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b` |
| `capture_pump.py` | `b7b1ffa551d8b3ad4346cc2920f0e17d04e37c2300d8583abf336ea90fb9e5b0` | `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6` |

| Переносимый patch | SHA-256 |
| --- | --- |
| [reachy-agent-4e2d-a0-continuous.patch](../../deploy/patches/reachy-agent-4e2d-a0-continuous.patch) | `52913ef59ff3719459c8eba94008c89123917c199db223dd524964993a317d2b` |
| [reachy-capture-b7b1-a0-continuous.patch](../../deploy/patches/reachy-capture-b7b1-a0-continuous.patch) | `f5f41c4b8a3435de137b1224202a1ded2dcb7c17ec157116d68f4b2d83b9bc08` |

Сборка в **новый** каталог; команда только офлайн:

```sh
python3 deploy/autonomous/prepare_continuous_capture.py /private/tmp/reachy-A0-review-bundle
```

[Builder](../../deploy/autonomous/prepare_continuous_capture.py) проверяет hashes preimages/patches/outputs, применяет без fuzz и компилирует оба результата. Не импортирует Agent, SDK или модель. `manifest.json` содержит полные pins неизменяемых barge_in, microphone, motion_policy, Config, SoundMonitor, spoken_vision. Эти dependency/helper pins происходят из исторической S1 установки; R1/Q1 не перемеряли их все. **Будущий оператор обязан свежим чтением сверить effective imports и каждый pin. Несовпадение — остановка применения, без подмены на HEAD.**

Opt-in остаётся прежним `conversation.capture_pump_enabled`, отсутствующий/false сохраняет finite capture. Строгая boolean-проверка и исходные prerequisites streaming=true, barge_in.enabled=true, confirm_with_stt=true, mono 16 kHz сохранены. В A0 эти barge settings — prerequisites старого S1, но pump barge consumer отключён: при opt-in не запускается дополнительное STT-подтверждение. Default/private config не менялись; отдельная активация потребует ровно прежнего opt-in и свежего Agent boot.

## Исправления и границы поведения

- Один прежний `arecord -q -D <existing device> -f S16_LE -r 16000 -c 1 -t raw`, один reader-thread и один assembler. Blocking STT/LLM/APLAY находятся вне reader. Второго arecord, второй ASR, AEC и новых зависимостей нет.
- S1 завершал источник при двух накопившихся chunks. A0 читает bounded burst до восьми chunks; выше порога четырёх оставляет последний целый chunk с partial tail, сбрасывает незавершённую фразу и pending revision, считает точные discarded bytes/frames. Источник продолжает drain. Raw staging строго меньше девяти chunks, assembler/pre-roll ограничены прежними audio limits, pending event один, admitted turn один. Потери не скрываются.
- В `/status.capture_pcm` доступны реальные `read_bytes`, `read_frames=read_bytes//2`, `read_calls`, `chunks`, `last_read_monotonic`, `max_read_gap_seconds`, `gap_events`, `overflow_events/bytes/frames`, `superseded_events`, `suppressed_frames`, размеры и `source_generation`. Byte/frame counters монотонны **внутри generation**; между boot/generation значения не вычитать. `raw_capacity_bytes` учитывает transient staging; отдельный `raw_overflow_threshold_bytes` задаёт порог discard. PCM/transcripts в метриках отсутствуют.
- Software receipt gap >max(250 ms, четыре chunk periods) закрывает источник с gap receipt. `os.read` receipt не является hardware capture timestamp; наличие bytes в pipe не доказывает акустическую свежесть. Kernel/ALSA buffers этим diff не измеряются.
- Pending audio по-прежнему имеет исходный TTL 2 s и latest-only admission. S1 применял этот TTL также после blocking STT, отбрасывая ответ уже принятой фразы, если STT занял >2 s. A0 отделяет admission от результата: принятый packet сохраняет идентичность и boot/mic/policy/source authority на время существующего HTTP request timeout. OFF/privacy/pause, смена epoch/boot/source или source failure всё равно лишают поздний результат права на model dispatch. TTL очереди не продлевается. Более новая фраза во время STT может занять latest slot, но не отменяет уже принятый запрос.
- Перед APLAY включается явная маска own output; assembler/mailbox очищаются с invalidation старой revision. Reader продолжает считать PCM, но эти frames не идут ни в STT, ни в SoundMonitor. После reap playback маска держится `max(0.3, min(2.0, existing echo_tail_seconds))` секунд. Это программное подавление, **не AEC и не полноценный barge-in**; внешняя речь в этом интервале тоже теряется. Акустическое эхо за пределами tail не исключено офлайн.
- Сохраняются S1 OFF/quiet/privacy withdrawal и reap вне microphone lock, включая failure сохранения mic state. Pause дополнительно retire-ит source даже без смены epochs; resume создаёт новую generation. Reap после pause выполняется вне microphone/policy locks, чтобы не образовать инверсию с reader. Manual primed/listen=false не открывает reader. Завершение Agent.run закрывает pump. Неизвестный reap сохраняет ownership/capture_active и блокирует replacement, а не создаёт второго child. Late cancelled output не коммитит новый turn после отзыва authority.

**Оставшийся gap:** неизменённый `_capture_visual` S1 закрывает pump перед synchronous spoken-camera child и может открыть новый source после его возврата. A0 не обеспечивает непрерывность через этот child и не исправляет camera ownership. Следующая совместная проверка должна использовать выбранный M1 producer и честно отличать его coexistence от этого legacy gap. Также Q1 видел factory audio fds: A0 гарантирует один capture child **Agent**, а не единственный физический reader всей системы. Аппаратное владение factory остаётся предметом A1/M1 наблюдения, без запуска ещё одного recorder.

## Офлайн-проверки и evidence

[Тесты A0](../../tests/test_continuous_capture.py): **29 PASS** (16 адресных и 13 прежних bound-listening checks, повторно исполненных на A0 Agent). Прежние S1/bound-listening/timing: **60 PASS**. Итого **89 tests, failures/errors/skips=0**. Оба standard `patch -p1 --dry-run` против exact preimages прошли; builder дополнительно проверил outputs/compile.

```sh
PYTHONPATH=src:tests python3 -m unittest test_continuous_capture test_capture_pump test_bound_listening test_agent_stream_timing -q
```

Проверки используют настоящий локальный Python subprocess и его stdout pipe вместо ALSA. Медленный/блокирующий consumer не заменён одним `capture_active=true`: real `os.read` counters продвинулись listening **11520 B / 5760 frames** → processing **23040 B / 11520 frames** → masked speaking **34560 B / 17280 frames**, generation=1, один child, gaps=0; при speaking подавлено 5760 frames. Это ускоренный синтетический producer, не измерение частоты физического микрофона.

Exact burst 7680 B: прочитано 3840 frames, overflow=1, discarded=6720 B / 3360 frames, assembled=один chunk, child не перезапускался. Отдельный actual Agent.run fixture блокирует `/transcribe`, проверяет дальнейшее продвижение pipe bytes, вызывает **настоящий** Agent.set_microphone(False), проверяет закрытый stdout/reaped child, затем освобождает STT: model calls=0, turns=0. Другой actual run принимает STT >2 s при прежней authority и завершает ровно один model turn.

Покрыты latest-only/TTL, own output+tail, source gap, boot/mic/policy withdrawal, persistence failure, privacy, pause/resume с теми же epochs/new generation, failed reap/no replacement, отсутствие pump-barge STT, default-false voice parity, primed no-reader, metadata-only status. Все HTTP/model/APLAY ответы в этих tests — fixtures; **никакого live PASS**.

Локальный frozen bundle и receipts:

```text
/Users/notanonenough/.codex/visualizations/2026/10/17/01a1475d-f91e-7bf3-a237-93adb450e3a4/A0-source-ready/
  agent.py, capture_pump.py, manifest.json
  reachy-agent-4e2d-a0-continuous.patch, reachy-capture-b7b1-a0-continuous.patch
  offline-tests.txt, offline-receipts.json, SHA256.json
```

Frozen `manifest.json` SHA-256: `c75e964a6f58352421005ec1c513aa053eca653034add1a178e774df8cebe303`; `offline-receipts.json`: `70f1d9b8759c1525843799462c4bb07dbc89f92bfa00e1c054ebd8dac86d0673`; `offline-tests.txt`: `d1f302fe7f4c8115c228183c27871c287ebb756589fb8b102944c7fa6a37b8de`. `SHA256.json` проверяет все семь payload files bundle, включая оба patches.

## Конечная аппаратная проверка A1 — пока не выполнялась

После явной передачи стенда от M1 — один оператор, существующие Agent/Hub/worker/factory. Не запускать другой Agent/recorder. Общий наблюдаемый opt-in window ограничить **90 s**, один обычный ответный voice turn; при недоступной/слишком короткой фазе критерий UNKNOWN, без бесконечного повтора.

1. Свежий preflight: effective source/import/config hashes, boot/epochs/owners, quiet/privacy, mic switch, Hub free, worker idle, известные voice jobs, factory instance и PCM roles. Сохранить original bytes/mode/ownership двух файлов и exact config в защищённый rollback bundle; persisted mic state отдельно наблюдать, не переписывать. При любом pin mismatch остановиться. Применение только после штатного guarded OFF и подтверждённого ухода Agent capture child; factory не останавливать.
2. Поставить два candidate files сначала при прежнем false, compile/hash, один controlled restart Agent. Новый boot, default-false normal capture и штатный OFF должны воспроизвести baseline. После fresh OFF включить только прежний opt-in=true через сохранённый private config механизм и controlled restart Agent. Сохранить unchanged sources/config diff; старые boot/epoch payloads не переиспользовать.
3. Один normal microphone ON по свежему guarded CAS. Poll protected Agent status с интервалом ~100 ms; сохранять только allowlist metadata: boot, epochs, phase, capture counters/generation, own-output mask, process identities. Никаких PCM/secrets/transcripts в evidence. Наблюдать существующий worker phase (`recognizing`, `thinking`) и role-qualified APLAY. Для каждого наблюдаемого STT/main/APLAY интервала ≥300 ms зафиксировать **положительный delta read_bytes/read_frames** и тот же Agent arecord PID/source generation. Уровни RMS/VAD, статус ON или PID сами по себе этого не доказывают. За длительный непрерывный интервал сравнить delta frames с ожидаемыми 16000/s с учётом границ опроса; отдельную разницу отметить, не подменять capture_active.
4. Во время own playback `output_suppressed=true`, `suppressed_frames` растёт; own speech не создаёт новый STT/turn. Один свежий внешний вопрос после tail должен завершить STT→main→полный APLAY. Вход во время output не обязан прерывать ответ. Параллельно выбранный M1 camera producer продолжает новые frame IDs; synchronous spoken snapshot здесь не запускать. Требовать gaps=0/overflow=0 в штатном окне; иначе сохранить exact counters/interval и считать continuity FAIL, не расширять buffers молча.
5. Пока capture активен, штатный OFF по **свежему** boot/epoch CAS: один owned child reaped, capture_active=false, counters после возврата OFF стабильны, pending/admitted не dispatch-ятся. Если в этот момент STT занят, дождаться его known completion в существующем timeout и доказать отсутствие позднего APLAY/turn. Затем отдельный явный ON даёт новую source_generation, новый child и свежий input; старые packets не воскресают. Если подходящий STT race не наблюдался, live late-result criterion UNKNOWN, offline check отдельно PASS.
6. Конечное состояние window: guarded OFF, Agent reader/APLAY отсутствуют, Hub free/worker idle, claims освобождены; factory/M1 producer в переданном состоянии, motor/volume/privacy не менять. Постоянный normal listening возвращать только отдельным явно разрешённым handoff с новым preflight. Hardware result, install hashes и дальнейший owner фиксируются отдельным A1 отчётом; A0 их не предполагает.

## Rollback для оператора

При source/reap/authority error — guarded OFF, дождаться ухода только Agent-owned processes; неизвестный reap не обходить вторым reader. Остановить соответствующую Agent service в контролируемом порядке перед заменой файлов, восстановить **оба exact preimages** из сохранённого rollback bundle и прежний opt-in/config только при совпадении ожидаемого candidate config (чужие новые изменения не затирать). Проверить hashes/compile, один controlled Agent restart, новый boot/preflight. Worker, factory daemon, camera bindings, модели и volume не перезапускать/не менять.

Persisted microphone-state не восстанавливать из старого ON backup: текущий OFF/STOP должен сохраниться. Проверить OFF/no Agent capture/no APLAY, затем отдельное разрешённое normal ON через свежий CAS. Возврат к default false достаточен для временного выключения pump, но полный rollback возвращает оба источника; HEAD не является rollback. Ничего из этого плана в A0 не применялось.
