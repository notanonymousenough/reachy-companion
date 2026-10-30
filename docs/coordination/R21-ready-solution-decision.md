# R21 — решение: локальный spoken snapshot на работающем S7 baseline

17 октября 2026, Europe/Moscow. Уточнение для TechLead; SOURCE-ONLY, hardware/model/SSH/deploy/runtime changes **0**. Scope: только этот report и `R21-evidence/local-slice/*`.

**Одно решение: сохранить S7 operational baseline и поставить один helper fix для normal unowned camera question → текущая PC9B → существующий Piper.** Hosted ConversationApp остаётся готовой reviewable альтернативой ROOT, самостоятельно не запускается.

## Что реально получено

**Source-ready artifact**, не новая установленная функция: [R21-local-snapshot.tar.gz](../../R21-evidence/local-slice/R21-local-snapshot.tar.gz), [точный manifest](../../R21-evidence/local-slice/transfer-manifest.json), [операторский рецепт](../../R21-evidence/local-slice/README.md). Один production candidate `spoken_vision.py`, меняется только admission-функция `check_operator`; зависимости/камеру/Agent/worker не переписываем.

Свежий [S7 report](S7-sentence-prompt-live.md), receipt **10:51:47 MSK**: listening+A1 capture **ON**, factory camera publisher **ON**, bounded normal expressions/motor **ON**, физическое движение измерено, owners **None/None**, Hub free. Ранее в R21 camera/movement считались OFF — это старое состояние, теперь superseded. Factory publisher не объявляется semantic vision. S7 report фиксирует release; назначение hardware owner остаётся явным решением TechLead по текущему root handoff.

## Единственный binding blocker и минимальное исправление

Installed `Agent1f4e52a6…` захватывает `spoken_vision.binding(operator_status())` с `owner_id=None` перед свежим normal STT. При exact camera question существующий `_capture_visual()` закрывает A1 pump и вызывает dispatch под прежним audio lock. Installed `spoken_vision486cfb8f…` требует **строковый** owner ID и отвергает штатную пару None/None до child. Это воспроизведено offline; камера здесь ещё не вызывалась.

Candidate **`2d7f29e20ee98b8f3607b060be39afb2170fdb2646b550bd772545eb84d4cb1c`**, **9149B**: разрешает ожидаемый owner `None` либо прежнюю bounded string. Exact boot/mic epoch/policy epoch/owner equality, matching second owner, processing/listening/mic/motor, capture inactive, error/privacy/quiet/deadline guards сохранены. Другие AST nodes byte-equivalent по структуре. Не создаёт owner и не выдаёт чужой grant за normal.

Маршрут уже существует: real STT exact **«Ричи, что ты видишь?»** / **«Что перед тобой?»** → existing camera-only `snapshot_vision.py` → configured private LM Studio native `/api/v1/chat`, same loaded vision-capable model instance → bounded FINAL → Agent `voice('/say')` → existing PC Piper. Vision capability/instance/no-model-load проверяются существующим helper; если actual inventory не подходит, отказ — точный blocker, без нового model/account/dependency.

**Lifecycle limitation сохраняется:** `_capture_visual` временно retire/close microphone pump на snapshot+PC inference; перед Piper существующий `voice()` запускает новый pump. Это один полезный запрос со слышимым ответом, **не** непрерывная semantic camera и не исправление simultaneous listening during inference. Physical exposure age/semantic accuracy не подтверждены. S7 capture/publisher/expressions остаются рабочим fallback.

## Следующее действие sole hardware owner

**TechLead: назначить один ≤10min install/start/utterance scope** по [README](../../R21-evidence/local-slice/README.md); не новый review-чат/обзор.
1. Fresh S7 pins/boot/free/unowned/privacy/known idle, guarded MicOFF/drain, остановить только `reachy-voice-agent`. Сохранить exact helper preimage/mode/uid/gid. Factory/Hub/PC/S6/R20 не менять.
2. Проверить helper486cfb8f/Agent1f4e52a6/snapshotd43a70cc/pump5fe20c69/expression4b2ea103 и текущие config/worker. Атомарно заменить **только helper**, сохранить attributes/compile, controlled start Agent (parent module cached, restart нужен). Несовпадение pins/UNKNOWN — STOP, не fuzzy apply.
3. Fresh normal ON с сохранённой operational motor policy. Один настоящий человеческий вопрос в normal non-interruption режиме; service сам вызывает helper, отдельный child вручную не запускать. Проверить actual route→PC FINAL→один Piper playback→normal listening/PCM и no-owner восстановлены. На first failure — typed phase/class, без retry/reseed.
4. **STOP:** существующий guarded mic OFF; полный operational STOP — prepared `S7-evidence/stop-operational.py` через approved route (fresh mic OFF затем motor OFF, no POST retry). Late FINAL не озвучивается; in-flight compute не объявлять мгновенно остановленным, дождаться known idle/reap.
5. **Rollback:** guarded OFF/drain/idle, остановить только Agent, при exact candidate restore сохранённый helper486cfb8f с attributes/compile, start. Fresh reconcile, отдельный normal ON; motor ON вернуть только если STOP его менял. Старые epochs/grants не восстанавливать. Полезный baseline по окончании оставить ON.

## Проверки, затраты, граница решения

**8 meaningful new checks + 11 existing helper regressions PASS; failures/errors/skipped0.** Проверены прежний normal blocker, None/claimed owners, все control/STOP/privacy fences, late response discard до Piper, actual installed `_capture_visual` restart/suppression, child operator checks, exact AST scope и no-fuzz forward/reverse patch. Старый test, ожидающий отказ именно None-owner, намеренно исключён; его changed-policy/stopped случаи сохранены новыми checks. [Evidence](../../R21-evidence/local-slice/validation.json).

Работа начата **10:54:11 MSK**, завершение/elapsed в validation; timebox10min соблюдён. Потери operating baseline **0**, runtime changes **0**, installed/live result **UNTESTED**. Никаких новых account, HF calls, model/device/SSH/deploy, чатов или подагентов. До hardware назначения действия не выполняются.

Сохранены полный дизайн memory/persona/goals/S3/VPS и постоянные LLM/perception target; этот запрос их не подменяет. Первоначальный hosted вариант и точный SDK1.11 recipe сохранены в [R21 launch recipe](../../R21-evidence/launch-recipe.md): official App1.1.1 допускает SDK>=1.11.0, его frozen lock выбирает1.12.0, поэтому бездумный frozen install не предложен. Это альтернатива ROOT, а ближайший **локальный outcome — один spoken camera answer на уже работающем baseline**.

**Source release TechLead:** camera candidate2d7f29 принят для bounded install; bundle/manifest/recipe закончены, дальнейших source edits не требуется. Sole hardware owner S7; ROOT сохранил LOCAL и лимит11:04MSK, hosted HF не запускать. Последующий idle source scope отменён/parked до разработки: сохранён только exact R15 preimage4b2ea103 в `R21-evidence/idle-slice`, candidate/config/tests/deploy0. R21 source-владение явно освобождено; новых работ не начинает.
