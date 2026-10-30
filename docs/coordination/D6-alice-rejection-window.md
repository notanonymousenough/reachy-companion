# D6 — actual S4 rejection: sentence_shape / headers_sent=false

17 октября 2026, final hardware receipt **10:01:15 MSK**. **Diagnostic PASS: реальный normal voice получил `reason=sentence_shape`, `headers_sent=false`, HTTP422.** Единственное окно **10:00:10.383289–10:00:40.100258 MSK / 29.722514s** до первого наблюдённого отказа. Один seed, **два полных normal replies**, третий `/stream/text` отклонён. В 10:00:40.320320 подтверждён guarded STOP; сбор завершающего safe status окончен 10:00:40.469191. Последующие read-only reconciliation и отдельный normal-listening ON не являются продолжением теста.

**Явный hardware handoff root: D6 завершён, эксклюзивное владение Reachy/Hub/PC освобождено. Normal listening/capture ON, motorOFF, observerOFF, owners absent, Hubfree/stockknown-unowned/workeridle/PCfastidle.** PROJECT пишет root. Новых чатов/подагентов нет. Изменены только собственные D6 evidence/report и factual update runtime-baseline.

## Preflight и границы

Прочитаны PROJECT, явный S5 handoff, S4, D5, runtime-baseline. Fresh existing-auth-only SSH: Hub deploy@192.168.2.181, robot pollen@192.168.2.158 через Hub/существующий factory helper и pinned known-hosts, PC User@192.168.2.134. Initial sandbox SSH был заблокирован `Operation not permitted`; тот же read-only preflight прошёл sanctioned escalation. Auto-review denial/unresolved approval отсутствует.

Fresh before/final совпали: effective site-packages voice **4ec7cfe56f7ee5a4b37ac9906a2c467b70983a6437a7840c25416695a5dfd4fd**, config module97732830…/recognition6211a01e…/PID1 configb864d375…/short flag=true; containerc46d…/image0e42…/StartedAt**2026-10-17T06:46:23.968192569Z**/RestartCount0/rootfsRO. R15 Agent1f4e52a6…/expression4b2ea103…/A1pump5fe20c69…/robot configa6171f68…/Hub config7f11d114… сохранены. Agent**240868**, boot**1e697e8a-271c-4764-bb44-bc8b617d0d58**, factory150625/Hub78887/NRestarts0 и PCfast**7736** creation/exe/command/weights/idle slots совпали. Existing LM Studio process identities unchanged. Main9B/Whisper/Piper/model/prompt/config/source/deploy/restart/auth/trust/ACL/firewall/bridge не менялись; независимый новый hash всех 9B/STT/TTS weights не заявляется.

До запуска mic259/source4/turns3/listening/captureON, motorpolicy129OFF/quietfalse/privacyfalse, ownersnull, Hubfree/no action/known-unowned stock, workeridle, observerunitsnot-found/nativeprocesses[]/observerports absent. Предустановлены пределы **595s (внутри 10min)/30 полных normal replies/первая ошибка**; дополнительная остановка при45s без следующего завершения, без повторного seed. Только metadata, без сохранения/вывода текста/transcripts/media/exception body.

## Реальный normal Agent → Hub → PC → robot → соседняя Алиса

Один штатный guarded `/robot/say` seed **«Алиса, сколько будет два плюс два?»**, затем обычное внешнее capture/STT/main/Piper/playback без человека. Synthetic/raw HTTP model dialogue/injected transcript/forcing/rewrite/truncate/retry/autorearm отсутствуют. Accepted spoken seed и два ответа имеют один canonical `Алиса, `, один segment; wordcounts6/**11/10** вместе с обращением. Первая normal completion Agentturns3→4 в07:00:23.748113UTC, вторая4→5 в07:00:33.443616UTC: listening/workeridle после production playback return. Completion evidence — Agent successful turns/status, отдельного process/PCM playback meter в D6 нет. **Acoustic/PCM≤5s UNKNOWN**, wordcount этого не доказывает.

| Worker UTC | Safe event |
| --- | --- |
| 07:00:11.841 | `/stream/say`200 |
| 07:00:18.541 →19.198 | `/transcribe`200 → `/stream/text`200; normal reply1 |
| 07:00:28.962 →29.554 | `/transcribe`200 → `/stream/text`200; normal reply2 |
| 07:00:39.149 | `/transcribe`200 следующего normal хода |
| **07:00:40.053** | **`alice_phrase_rejected reason=sentence_shape headers_sent=False`** |
| **07:00:40.054** | **`/stream/text`422** |

Agent first observed phaseerror/last_error HTTP422 в **07:00:40.100244UTC**, turns5. Немедленный guarded MicOFF259→260 подтверждён **07:00:40.320320UTC**; после STOP capturefalse/retiredtrue, незавершённый ответ не завершён/не посчитан. Не было дополнительного пробного ответа или повторного seed. Known Agent error/D0terminal/STOP/validator contracts сохранены. D6 не использовал native observer и не проверял D0 live recovery.

Exact S4 source связывает enum с провалом прежнего fullmatch `[^.!?…？؟！。．]+[.!?]` после нормализации одного leading prefix. Это **первая нарушенная проверка**: type/edge-whitespace/character-limit/forbidden-symbol до неё прошли; word-count/wake-name после неё этим record не доказаны. Конкретный вариант (отсутствующий конечный знак, второй знак/предложение, многоточие или иное несовпадение) **UNKNOWN**, отвергнутый текст не читался для диагностики/не экспортировался. Поэтому «слишком длинный ответ» и конкретный prompt fix не установлены. `headers_sent=false` здесь реально записано S4; source-derived inference: отказ до первого reply event/HTTP200/TTS данного rejected ответа. Historical D5 predicate этим новым окном не переименовывается.

[Worker records](/Users/notanonenough/reachy-companion/D6-evidence/worker-records.json): **8records /2417B**, omitted0/sizecapfalse, hard cap16records/16KiB. Collector на PC отбирал existing compute.log/.1 строго в07:00:10.383289–40.469191UTC до вывода; только timestamps/fixed event/source/route/status/reason/headers_sent и safe log coverage. Никаких traceback/arbitrary message/body/token/content. Ровно один typed rejection и соседний422 в одном worker log/generation, generic503/stream_failed0. Safe local attempt attribution убедительно поддерживается этими соседними same-worker records, но **worker requestID отсутствует; формальная exact attempt linkage и cross-host correlation без requestID/clock history UNKNOWN**. Agent/worker UTC разность не является измеренной сетевой latency. `last_turn` после отказа содержит прежний успешный ответ и не выдаётся за rejected text/result.

Manual seed штатно retired source4; normal portion шёл source5 с растущими counters, gaps0/overflow0; при STOP802816B/retiredtrue. Continuity через manual seed/STOP не заявляется. Нового continuous30min испытания не было, прежний D3≥30minFAIL остаётся. Единственный factory reader/physical acoustic identity не измерялись.

## Cleanup и handoff

Fresh **07:01:01.547441UTC**: Agentpaused/micOFF/capturefalse, Hubfree/knownunowned/workeridle/ownersnull, last_error_present=true как сохранённый результат отказа. UNKNOWNjob отсутствует по доступным idle/paused status; destructive job cleanup не выполнялся. После этой проверки один отдельный guarded normal MicON260→261; это требуемое возвращение production listening, без seed/diagnostic rearm.

Final **07:01:15.832503UTC /10:01:15MSK**: mic**261ON/listening/capture/source6**, PCM**403456B**, gaps0/overflow0/retiredfalse, turns**5**, interruptions0/last_error absent; один Agent arecord**242448→240868**, APLAY absent. Policy**129 motorfalse/quietfalse/privacyfalse**, ownersnull, Hubfree/actionfalse/stockknown-unowned, workeridle/PCfastidle. Same processes/import/config/container-generation before/final, observerOFF/unitsnot-found/no nativeprocess/no observerports/camera listener. Собственных remote stage/service/token/bridge/listener/grant/masters не создавалось; короткие SSH завершились. Production continuous voice оставлен ON.

[Analysis](/Users/notanonenough/reachy-companion/D6-evidence/analysis.json)/[evidence](/Users/notanonenough/reachy-companion/D6-evidence/): preflight/final safe receipts, reproducible collectors, bounded live metadata, source scripts и SHA256. Automatic analysis проверила limits/one seed/two completions/typed enum+422/all8records/unchanged pins+processes+generation/idle+normal cleanup. **D6 закончен, hardware явно освобождён root.** Следующий source-only форматный анализ может опираться на `sentence_shape`; live fix/restart/новое окно этим отчётом не назначаются.
