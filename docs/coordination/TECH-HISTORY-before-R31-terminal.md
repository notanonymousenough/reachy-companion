# Reachy Companion — текущий технический статус

1. **R31 ACTIVE 15:58:56–16:33:56 MSK:** один opt-in once-per-arm самостоятельный русский вопрос по настоящему свежему кадру; source≤16:13:56/install+oneproof≤16:28:56/rollback≥5min. ROOT разрешил независимо от motorOFF после R30 known-ready voice/camera terminal. Source R21, physical S7. [Scope](../../TECH-evidence/R31-scope.json).
2. **Фактическая проверка:** 3 штатных Hub expression HTTP200, 224 encoder samples/11 active, движения головы и антенн; после STOP 22,8s без новых движений/аудиопроцессов/поздних команд, Hub known/free. 7 source + 5 independent boundary groups PASS. Actual typed409 не возникал; ветка отмены проверена офлайн. [Receipt](../../TECH-evidence/R29/actual-gate-review.json).
3. **Fallback actual 15:57:41:** boot `46b5d19c…`, mic303/capture/listening ON/source3/PCM827392B/gaps0/overflow0; motor142 OFF, owners null, Hub free/unknown false/owned null/worker idle/errors absent. Camera меняет кадры/reader closed. +2dB, hardware100%, ordinary false/ACKfalse сохранены. Epochs — receipts, не replay payloads. [State](../../S7-evidence/R30/final.json).
4. **Голос частично принят:** R28 дал 2 полных связных русских ответа с playback/format errors0; третий не появился за120s при продолжающемся PCM и idle/listening. Причина отсутствия нового nonempty STT UNKNOWN; долгий непрерывный диалог/full companion ещё не принят. Новых seed/model/prompt/voice trials в R29 нет. [Voice](S7-R28-voice-isolation-live.md).
5. **R30 retention FAIL закрыт:** natural expression409 `Fresh stock operator required`, nondict/elapsed>.3/delay subcause UNKNOWN; correct guard оставлен, motion repair PARKED. Один guarded motorOFF, source/inference/reseed/restarts0/paid0. R31 не даёт motion/always-autonomy/full-companion PASS и не блокируется независимым motor fault. [R30 terminal](S7-R30-retention.md), [packet](R30-next-product-decision.md), [история](TECH-HISTORY-before-R30-terminal.md).

| Владелец | Текущее состояние |
| --- | --- |
| S7 `01a148c3-97d7-73b3-99f7-afb841c17b53` | R30 terminal/release принят. R31 sole physical owner: public exact preimages export, stage/rollback, no install until Tech gate. |
| Source `01a148d4-bc4e-72e3-93aa-29847c0a836a` | R31 minimal once-per-arm admission/helper, exact deployed preimages/manifest/tests; no hardware/model calls, deadline source16:13:56. |
| TechLead | R30 motion fault PARKED; независимый review R31 fresh image/content/admission/STOP/capture return. Total35min cap. |
| ROOT | PROJECT/OPERATING-MODE/product decisions; полный локальный companion остаётся открытым. |
