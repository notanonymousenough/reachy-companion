# R38 — штатный обработанный вход найден, функциональная проверка не началась до deadline

17 октября 2026, МСК. Окно назначено 17:14:05–17:34:05. **CONFIGURED_HARDWARE_ROUTE_ELIGIBLE / FUNCTIONAL_UNTESTED / START_DEADLINE_ABORT.** Единственный physical owner `01a14a37-26ab-7103-abbb-c71a6c7b2138` освобождён после cleanup. Повторов нет.

Штатный аппаратный обработанный вход уже доступен на текущем USB-аудиоустройстве. Это положительный результат capability-инвентаризации; оснований объявлять AEC отсутствующим нет. Пригодность для автоматического прерывания речи этим результатом не доказана; U08/T05 остаются OPEN.

## Что проверено без открытия аудио

[Inventory](../../R38-live-evidence/inventory.json) установил SDK `reachy_mini 1.11.0` в factory `/venvs/mini_daemon` и `/venvs/apps_venv`. Factory daemon PID150625 сохранён. USB `38fb:1001`, `bcdDevice 2.12`, дескриптор echo-canceling speakerphone; один USB capture и один playback endpoint, оба stereo. Это USB-дескриптор, а не версия DSP-прошивки.

Текущие `plug:reachymini_audio_src` → `dsnoop` и `plug:reachymini_audio_sink` → `dmix` используют один `hw:0,0`, stereo16000. Ordinary Agent читает mono S16_LE16000 единственным `arecord284201`. В `.asoundrc` нет явной таблицы сведения stereo→mono; коэффициенты plug не измерялись. Оба DSP-канала имеют одинаковую маршрутизацию, поэтому нет основания считать один из них raw.

Экспортированы только публичные установленные SDK-исходники с SHA256: [manifest](../../R38-live-evidence/public-sdk-export.json), [control helper](../../R38-live-evidence/public-sdk/media/audio_control_utils.py). Helper SHA `f975055dde2bc72830f34e4c093b735a463fe9335807ca5a271bacef7787c729`. Его `ReSpeaker.__init__` только присваивает device; `read` использует vendor CTRL_IN. Полные ReachyMini/Media/GStreamer-конструкторы не создавались. GStreamer `webrtcdsp` и `webrtcechoprobe` 1.26.2 установлены, но текущий отдельный `aplay` не подаёт в их пару playback reference; установленный SDK в `.asoundrc`-ветке также использует hardware route напрямую. Наличие плагинов не даёт второго готового рабочего AEC-тракта.

[Официальные Pollen controls](https://huggingface.co/docs/reachy_mini/platforms/reachy_mini/media_advanced_controls) описывают аппаратный AEC по умолчанию и стереовыход. Это описание сопоставлено с фактическим [readback](../../R38-live-evidence/dsp-readback.json), а не принято за состояние устройства.

| Прочитанный параметр | Фактическое значение |
| --- | --- |
| VERSION / BLD_REPO_HASH | `2.1.2` / `eaea4d41f0ead1e0e18ea55130765f1d579224da` |
| AUDIO_MGR_OP_L / OP_R | оба `[8,0]`: postprocessed auto-selected beam по [таблице XMOS](https://www.xmos.com/documentation/XM-014888-PC/html/modules/fwk_xvf/doc/user_guide/03_using_the_host_application.html) |
| OP_PACKED / OP_UPSAMPLE | оба `[0,0]` |
| SHF_BYPASS | `0` |
| AEC_NUM_MICS / NUM_FARENDS | `4` / `1` |
| AEC_AECCONVERGED / AEC_ASROUTONOFF | `1` / `1` |
| AUDIO_MGR_REF_GAIN / PP_ECHOONOFF | `8.0` / `1` |

Все13 разрешённых чтений завершились за0.4443s без ошибок. [Исполненный helper](../../R38-live-evidence/read-dsp.py) загрузил только проверенный файл через importlib; VID/PID фиксированы, USB transfer обёрнут точным CTRL_IN/request0/selector allowlist, host timeout250ms. DSP writes/set-configuration/claim/reset/save/reboot0; own USB handle освобождён. Никаких параметров, defaults или gain не применялось.

## Критерий функциональной проверки и готовая альтернатива

**Tech уточнил: отсутствие raw comparator не блокирует функциональную проверку.** L и R уже processed `[8,0]`; current mono не смешивает processed с raw. Raw был бы нужен для отдельного ERLE/сравнения до-после; такие метрики остаются UNKNOWN, DSP routing менять не требуется. Первоначальный вывод «оба processed => нет допуска» отозван до любого audio action.

Функциональный proof требует реального внешнего Alice overlap с собственным playback. Source завершил пересмотренный [протокол](../../R38-evidence/proposed-finite-proof.md) до17:20:05: neutral own-only → один canonical query → externally started responsive speech → replay того же neutral PCM. Внешняя реплика должна начаться до replay и продолжиться в overlap; actual-capture ASR/topic checks — только дополнительное свидетельство, не speaker identity. Raw comparator/станционный API не обязательны; физическое начало/ERLE не измеряются.

К17:23:13 заморожены [functional helper](../../R38-live-evidence/functional-probe.py), [wrapper](../../R38-live-evidence/run-functional.py), [точные hashes](../../R38-live-evidence/candidate-pins.json) после трёх правок Tech. Syntax PASS; единственный operator HTTP503 secret-canary [fault check](../../R38-live-evidence/fault-check.json) PASS, receipt AST неизменён после runtime-правок. Tech отдельно проверил formatter в [receipt](../../TECH-evidence/R38/fault-verification.json); это не повтор физической попытки. Read-only preflight подтвердил существующие VAD/Assembler и threshold2304.96953; worker rules/fasterWhisper остаются по config pins. Протокол предусматривал локальный authority monitor300ms, fresh OFF/reap/один finite recorder, guard/reap/отдельный fresh ON. Все runtime helpers находятся только в evidence, production не менялась.

## Единственная попытка и конкретный blocker

Tech явно одобрил exact probe `68cf94…` и wrapper `4528…` в сообщении17:24:32; объявленный файл gate ещё отсутствовал при первой локальной проверке. Она завершилась до SSH, proof-start, controls и аудио: [local-only receipt](../../R38-live-evidence/local-dispatch-preflight-only.json). Затем точные одобренные hashes из сообщения записаны в [accepted gate](../../R38-live-evidence/accepted-tech-gate.json); появившийся позднее [Tech artifact](../../TECH-evidence/R38/functional-gate.json) содержит те же hashes и ограничения. Допуск не менялся.

Один [proof dispatch](../../R38-live-evidence/proof-start.json) начался **17:24:56.180**. Fresh Hub был idle/free; MIC OFF325→326, ordinary source8 retired и reader reaped. Но Robot helper вошёл уже после жёсткого старта17:25:00: первая проверка времени в `main()` завершилась `AssertionError` до локального operator запроса, monitor, TTS, recorder или playback. [Raw result](../../R38-live-evidence/physical-metadata.json): stage=`preflight`, class=`AssertionError`, reason=`unclassified`, elapsed0.0003496s, child exits`[]`, все owned children reaped, thread ended, temp raw отсутствует. Причина hard-start получена из точного первого source assertion и хода dispatch; исходный reason не переписан. Диагностика expiry требует отдельного исправления harness, скрывать этот недостаток receipt нельзя. CPU-limit flag вычислен на0.35ms preflight; он не доказывает устойчивое превышение CPU.

**Один blocker:** функциональные измерения отсутствуют, потому что до входа в finite helper истёк согласованный start deadline. Tech подтвердил процедурную задержку handoff/gate, включая исправление формата metadata AST hash. Это не отрицательный результат AEC и не отсутствие готового processed input. Capture/TTS/playback/ASR/Alice actuation0. После abort выполнен отдельный свежий ON326→327; повтор, новый запрос или продление окна не выполнялись. ERLE, own-only rejection, real-Alice double-talk preservation, физическое начало и автоматический interrupt остаются UNKNOWN. U08/T05 OPEN.

[Классифицированный receipt](../../R38-live-evidence/classified-failure.json) фиксирует `preflight / start_deadline_expired / AssertionError` отдельно от исходного `unclassified`. Runtime CPU/RSS verification — NOTRUN: submillisecond preflight ratio не является измерением ресурсоёмкости audio helper. Один конкретный следующий repair в harness — проверять оставшийся бюджет remote-start и классифицировать expiry **до MIC OFF**. Здесь этот repair не выполнялся, нового окна не назначалось.

**Одна готовая альтернатива:** существующий явный MIC OFF/STOP → отдельный fresh MIC ON после reap и проверки owner/privacy. Production changes0, реализация0min; отдельная конечная операционная приёмка при выборе ROOT — оценка≤5min. В R38 она не запускалась. Это ручное прекращение и отдельный возврат слушания; U08 не закрывает. Срок автоматического barge-in честно не оценён до пригодного доказанного сигнала.

## Сохранённое состояние и release

Свежий Hub17:25:28: Hub211637/boot`a642…`/SHA`9c00…`, knownfree/unowned/actionfalse/workeridle; ошибок Agent и expression нет. Robot17:25:30: Agent281630/boot`084b…`/mic327/source9, все pins Agent`3a5e…`, initiative`8215…`, snapshot`04e…`, player`1e25…`, capture`5fe…`, config`a617…` совпали. Factory150625/Agent NRestarts0.

Health17:25:31: listening/capture/microphone ON, PCM800768→817152B за0.430s, source9/gaps0/overflow0/outputfalse/retiredfalse; один ordinary `arecord285376`, ownersnull, quiet/privacyfalse, motor144OFF, R35gen1done/UNARMED. Hardware volume100%/0dB/on. Конфигурации не менялись, software+2dB/ordinaryfalse/ACKfalse сохранены по тем же config pins. Camera path не трогался, нового semantic camera proof нет.

PC17:17:35: прежний container`c46d…`, image`0e42…`, running/restarts0; фактический import-origin `/usr/local/lib/python3.13/site-packages/reachy_companion/voice.py`, SHA`224ff166…`, config`2e0a…` прежние. Первая сокращённая проверка `/app/src` прочитала другую неиспользуемую копию `92cf…`; [уточнение import-origin](../../R38-live-evidence/final-pc-installed.json) сняло расхождение, установки/отката не было.

Cleanup17:25:34: R38 temp directories0, только ordinary `arecord285376`; собственного recorder/aplay/observer/job нет. Raw PCM/transcript/private audio exports0, временного raw вообще не создавалось. Fresh restore подтверждён health. Предварительный release17:18:16 был отозван после уточнения Tech; окончательный release записан после этой попытки и cleanup. [Result](../../R38-live-evidence/result.json) и [owner status](../../R38-live-evidence/owner-status.json) содержат окончательное состояние. Все epochs только receipts, не будущие CAS payloads.
