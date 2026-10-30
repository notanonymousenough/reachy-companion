# R39 — functional acceptance не получен; recorder exit 1, владелец освобождён

17 октября 2026, МСК. **INSUFFICIENT_CAPTURE_START_FAILED.** Выполнена одна разрешённая фактическая попытка helper; playback/ASR/обращения к Алисе не было. Это не `PROCESS NOT RUN`. U08/T05 остаются OPEN; положительный аппаратный AEC readback R38 сохраняется, функциональная пригодность UNKNOWN.

Первый немедленный запуск исходного wrapper завершился локальным `preflight / AssertionError / preflight_or_control_rejected`, до proof-start, SSH и controls. Срок подготовленного окна 17:29:20 уже прошёл. Затем поступил HOLD. Выполненная read-only проверка 17:30:17 подтвердила прежний ON327/source9, motor144OFF и сохранённые pins.

После этого поступила явная команда RUNNOW с обновлённым accepted gate: окно actual admission17:29:30, latest17:31:30 и hardfinal17:37:30. По ней wrapper был запущен, [proof-start](../../R39-live-evidence/proof-start.json) записан **17:31:03.710**. Затем пришёл промежуточный STOP с latest17:30:30/hardfinal17:35:20. К обработке STOP wrapper уже завершился естественно с reap и fresh ON; дополнительный сигнал остановки не потребовался. **Окончательным уточнением ROOT явно отменил промежуточный срок и подтвердил actual admission17:29:30/latest17:31:30/proof17:34:30/hardfinal17:37:30. Фактический запуск был разрешён и уложился в действительное окно.** Хронология сообщений сохранена; отрицательной оценки действий владельца по сроку нет. Нового gate, продления или повторной пробы этот владелец не создавал. Функциональная приёмка не получена из-за отказа recorder, а не из-за срока.

## Фактическое выполнение

Fresh OFF327→328, старый ordinary reader/source9 завершён. Два Piper PCM reference сформированы; единственный finite `arecord` завершился с **exit1** до `capture_ready`. [Неизменённый metadata receipt](../../R39-live-evidence/physical-metadata.json): `capture_start / RuntimeError / capture_exhausted`, elapsed0.912477s, CPU0.409006s, RSS delta7602176B, child exits `[1]`. Нижележащая причина ALSA/recorder неизвестна: stderr в протокол не экспортировался. Успешный capture и число записанных frames не доказаны.

`aplay`0, ASR0, Alice actuation0, LLM0. Отмеченный helper `resource_limits_met=false` относится к короткому неуспешному старту; это не измерение CPU устойчивой audio-нагрузки. Own-only rejection, real-Alice double-talk preservation, ERLE, physical onset, speaker identity и automatic interrupt остаются UNKNOWN. Данные VAD/ASR для этих выводов не получены.

Helper подтвердил `owned_children_reaped=true`, `guard_thread_ended=true`, `temporary_raw_remaining=false`. Wrapper выполнил отдельный fresh ON328→329. Raw PCM/transcript exports0; DSP reads/writes0; production/config/gain/firmware/model/install/restart changes0. Camera/motion/R35 arm не выполнялись. Повторов0.

## Конечное состояние и release

Свежие [health](../../R39-live-evidence/final-health.json), [Hub](../../R39-live-evidence/final-hub.json), [Robot pins](../../R39-live-evidence/final-robot.json), [PC installed pins](../../R39-live-evidence/final-pc-installed.json) и [cleanup](../../R39-live-evidence/cleanup.json) получены после OFF/ON, в **17:31:42–17:31:50**. Agent281630/boot084b…/mic329/source10, ordinary `arecord285798`; listening/capture/microphone ON. PCM1034240→1048576B за0.421s, gaps0/overflow0/output-suppressedfalse, ownersnull, motor144OFF, R35gen1done/UNARMED. Hub211637 free/knownunowned/actionfalse, workeridle; factory150625. Hardware volume100%/0dB/on. Все Robot/Hub/PC pins и конфиги совпали с R38; PC прежний container/image running/restarts0. Software gain сохранён по config pin; сокращённый selected-config helper вернул пустой словарь, поэтому отдельное новое чтение величины +2dB не заявляется.

В `/var/tmp` отсутствуют каталоги `reachy-R38-*`, которые использует неизменённый reviewed helper; есть только штатный ordinary recorder. Собственных audio children/observer/job нет. Владелец `01a14a44-8cad-7643-9774-9f2d92dcecec` **RELEASED**, дальнейших действий с устройствами нет. [Result](../../R39-live-evidence/result.json), [current baseline](../../R39-live-evidence/current-baseline.json), [explicit release](../../R39-live-evidence/owner-status.json). Epochs служат только квитанциями, не будущими CAS payloads.

Следующий узкий диагностический вопрос для отдельного допуска: почему existing finite recorder вернул exit1. Причина не установлена; повтор, смена gain/device, DSP routing или harness repair в R39 не выполнялись.
