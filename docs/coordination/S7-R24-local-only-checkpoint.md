# S7 R24 — hosted attempt canceled before runtime changes

17 октября 2026, итоговый read-only receipt **14:44:36 MSK**. Прямое пользовательское указание «давай локально сделаем» отменило прежнее разрешение hosted R24. **Hosted установка и запуск не начались. S7 явно освобождает аппаратное владение TechLead `01a148d9-f558-7151-93c5-016d77b24489`.** Новый локальный setup или trial не начинался; следующий план выбирает TechLead.

## Фактический объём

Выполнены чтение frozen R24/R21 recipe и уже сохранённого публичного source, свежие read-only Robot/PC preflight и финальное чтение состояния. Созданы только локальные receipt/scripts в `S7-evidence/R24`. Existing cached R21 source и recipe сохранены.

**Downloads 0; dependency/venv installs 0; App installs/launches 0; HF allocations 0; HF audio/JPEG egress 0; control requests 0; service restarts 0; old Agent stops 0.** Предложенный remote stage `/home/pollen/reachy-companion/.r24-20261017-144238` фактически отсутствует; App processes отсутствуют. Удаление remote stage или восстановление runtime не требовались. SDK1.11.0 и official App1.1.1 commit `0a3ef5c07c4c9ba58ceaf788244393033acd88c7` остались лишь frozen предложением, новой установки нет.

## Итоговый local ON receipt

С 14:43:58 до 14:44:36 MSK прежний Agent boot `a309d491-d0f5-43ac-a250-61c55101a7a3` и PCM source5 сохранились; PCM **325,588,992 → 326,813,696 B (+1,224,704)**, gap0/overflow0/retired=false. Mic287 enabled/listening/capture=true, phase listening; motor policy137 ON, quiet/privacy=false, microphone/motion owners=null. Последние last_error/expression_error отсутствуют, turns155, volume100. Hub free/action=false, stock selected/known/unowned; worker idle.

Read-only process receipt: Agent PID247720 active/NRestarts0; factory daemon PID150625 active/NRestarts0; ровно один `arecord` PID250221/PPID247720; APLAY отсутствует. Существующий factory camera publisher не останавливался и не заменялся; нового camera consumer не было. Новые pixels/encoder samples в R24 не запрашивались. Свежий PC preflight до отмены сохранил прежний S6 worker224ff166, контейнер c46d/image0e42/generation08:53:44.615893658Z/RestartCount0, 9B instance и +2dB profile. После него изменений на PC не выполнялось.

Этот receipt подтверждает сохранение полезного local ON режима; **stable normal voice и постоянное semantic vision не приняты**. Исторические S6 format422 и R23 renderer_normalization_rejected/503 остаются открытыми. Весь прежний local-format tuning остановлен; новая LOCAL ONLY цель ожидает отдельного выбранного TechLead плана.

[Checkpoint](../../S7-evidence/R24/checkpoint.json), [before](../../S7-evidence/R24/fresh-before.json), [final](../../S7-evidence/R24/local-only-final.json), [processes/stage](../../S7-evidence/R24/no-app-state.json), [PC preflight](../../S7-evidence/R24-pc-before.json), [Robot preflight](../../S7-evidence/visual-local/R24-robot-before.json). Epoch values — только historical receipts, не готовые control payload.
