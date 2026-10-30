# Reachy Companion — текущий технический статус

1. **Локальный режим ON, R30 operational retention 15:55:23–16:25:23 MSK.** S7 — единственный physical owner; read-only availability/natural turn metadata, без reseed/new inference/source experiments. Healthy functions остаются ON в конце; STOP только при actual fault. R29 finite movement + STOP PASS, player SHA `1e25036f…`; прежние Agent/Hub/factory/9B/Whisper/Piper. [Retention scope](../../TECH-evidence/R30-scope.json).
2. **Фактическая проверка:** 3 штатных Hub expression HTTP200, 224 encoder samples/11 active, движения головы и антенн; после STOP 22,8s без новых движений/аудиопроцессов/поздних команд, Hub known/free. 7 source + 5 independent boundary groups PASS. Actual typed409 не возникал; ветка отмены проверена офлайн. [Receipt](../../TECH-evidence/R29/actual-gate-review.json).
3. **Последний actual ON 15:54:05:** boot `46b5d19c…`, mic303/capture/listening ON/source2/gaps0/overflow0; motor141 ON, owners null, Hub free/unknown false/owned null/worker idle/errors absent. Camera: два меняющихся кадра/reader closed. +2dB, hardware100%, ordinary false/ACKfalse сохранены. Epochs — receipts, не replay payloads. [State](../../S7-evidence/R29/final-after.json).
4. **Голос частично принят:** R28 дал 2 полных связных русских ответа с playback/format errors0; третий не появился за120s при продолжающемся PCM и idle/listening. Причина отсутствия нового nonempty STT UNKNOWN; долгий непрерывный диалог/full companion ещё не принят. Новых seed/model/prompt/voice trials в R29 нет. [Voice](S7-R28-voice-isolation-live.md).
5. **Стоимость/границы:** source≈4m23s, review/install/actual gate/resume всего≈7min с начала R29, новых платных расходов0, rollback не потребовался; точный preimage/rollback сохранён. STOP/privacy/CAS/owners/UNKNOWN guards не ослаблены. Hosted/App packaging направления закрыты; дальнейший product scope выбирает ROOT. [История](TECH-HISTORY-before-R29-terminal.md).

| Владелец | Текущее состояние |
| --- | --- |
| S7 `01a148c3-97d7-73b3-99f7-afb841c17b53` | R29 terminal/release принят. Новый R30 sole physical owner: одно 30min read-only retention, до16:25:23; no new trials. |
| Source `01a148d4-bc4e-72e3-93aa-29847c0a836a` | Frozen player-only package завершён; 7 tests PASS, runtime calls0, parked. |
| TechLead | Контролирует R30 availability scope, готовит один ≤5-line next product outcome из реального восприятия. Source/hardware не пересекаются. |
| ROOT | PROJECT/OPERATING-MODE/product decisions; полный локальный companion остаётся открытым. |
