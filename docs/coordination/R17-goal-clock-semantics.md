# R17 — goal/clock semantics: отдельный candidate только operator goal text

17 октября 2026, Europe/Moscow. **SOURCE-ONLY. Подготовлен reviewable config-template candidate; runtime checkout не изменён, candidate не установлен и требует отдельной review. Модель/сеть/Hub/PC/robot не вызывались, arm/deploy/live не выполнялись. S5 остаётся единственным hardware owner.** Чаты и подагенты не создавались; PROJECT/baseline, Agent/ExpressionPlayer, worker/router/S4 не менялись.

## Причина и граница доказательств

Минимальный установленный semantic mismatch — между критерием демонстрации («получить один settle») и **условной operator goal**, которая сама разрешает безусловный `wait`. Это не доказанный отказ исполнения или потеря capability. Текст R14/R16 одинаков:

> Perform one initial small stock settle if appropriate: roll 1 degree then return to neutral, 0.5 seconds each. Waiting is permitted. No speech, tasks, or other effects.

Цель действительно просит движение, но оставляет модели оценку `if appropriate`; нейтральный `wait` ей не противоречит. В R16 все четыре actual outputs начинаются с `op.motion_allowed=true, but no audio or context…`, затем ссылаются на допустимость ожидания. R14 дал пять аналогичных actual wait, включая ссылку на отсутствие camera evidence. Это **явные brief why из FastChoice**, не доступ к внутренней причине выбора. Why ограничен 96 символами, окончания оборваны; продолжение не реконструируется.

R16: 4actual wait / 4accepted / 0stale / 0proposal / 0effect. R14: 5actual wait / 5stale / 0effect. Исправленный R15 coupling объясняет исчезновение stale, но не объясняет выбор `wait`. Accepted wait и latency не являются physical proof. Finite motion acceptance остаётся FAIL; proposal/effect/server CAS/physical settle path UNKNOWN / не exercised.

По frozen exact R16 source/config и actual construction regression:

| Вопрос | Локальное evidence / вывод |
| --- | --- |
| Доступна ли motor capability модели? | Native system явно описывает `optional motion=settle`, один fixed Hub stock profile при `op.motion_allowed=true`. Actual why всех 4 R16 outputs прямо упоминает этот true. `fast_schema` добавляет object `{a:explore,motion:settle,why:…}` при true; `wait` остаётся отдельной веткой. Нет признака отсутствующей capability. |
| Попадает ли goal/version/origin? | `GoalClockState.snapshot()` кладёт полный `native.goal`; `fast_projection(full)` сохраняет `goal`. Config R16: id `r16-single-settle-20261017`, version1, origin operator, evidence_ids[], **actual changed_at `2026-10-17T06:32:38.954375Z`**. Это фактическая подготовка, не более ранний timestamp шаблона. |
| Попадает ли clock basis? | Scene: finite initial stock settle from explicit operator goal and clock only; principles: only operator goal/clock may select fixed roll1°→neutral, .5s each. Sensor `native.clock` содержит elapsed_ms, goal_version и goal_remaining_ms. Wire field `basis` модель не выбирает: trusted adapter добавляет `operator_goal_clock` только к proposal. |
| Правдиво ли представлен sensor UNKNOWN? | Scene/principles указывают Sensors UNKNOWN; `native.audio=no_data`, age null, summary пуст. Dialogue/memory/prev/pending/ready/candidates/evidence_aliases пусты. PCM/audio/context/camera payload не передаётся. Это не continuous PCM. |
| Явно ли сказано, что отсутствие сенсоров не запрещает independent goal/clock settle? | **Нет прямого разъяснения.** Source допускает такой settle; prompt говорит goal/clock only и no audio/context evidence, но не формулирует отсутствие sensor trigger как ожидаемое условие этой задачи. Generic native system также не поясняет независимость mute/UNKNOWN для этого finite profile. |

Это доказательство наличия пути построения prompt, а не сохранённые actual wire bytes R16: passive witness записывал outputs/bindings/receipts, но **не incoming FastView/system/payload**. Полный исторический prompt и внутреннее понимание модели остаются UNKNOWN. В унаследованном FastView также остаётся `sim.origin=simulated`; связь этого поля с actual wait не доказана, его здесь не меняем. Дизайн v4 §1/inputs, §5/инициативность, §10/goal допускает clock и цель как inputs; он не требует сенсорного события для каждой разрешённой инициативы.

## Минимальный delta для отдельной review

Доказательств недостаточно для изменения gateway/system prompt, FastView, schema или guard. Достаточно для **уточнения самой легитимной operator task**: её независимый trigger теперь выражен в `operator_goal.text`. Это проверяемая следующая гипотеза, не установленное исправление model policy.

В отдельной копии public R16 `trial-template.json` изменено **ровно одно поле**, `native_agent.operator_goal.text`:

> Perform one initial fixed stock settle during this finite goal window: roll 1 degree then return to neutral, 0.5 seconds each. This operator goal and elapsed clock are the reason for the action; no audio, context or camera trigger is needed. Sensors remain UNKNOWN. Consider the settle only while op.motion_allowed=true; the goal grants no motor permission. Waiting remains permitted. No speech, tasks, or other effects.

Это task text, не новая policy/grant: `wait` остаётся свободным. Нет forced output, logit bias, запрета wait, mock response, ручного движения или другого action ради PASS. Cap прежний: один fixed settle roll1°→neutral/.5s+.5s, никаких новых skills/motions/framework. Generic/default observer prompt и observation-only service остаются byte-exact прежними. R11 не prerequisite.

**Файлы — отдельно от checkout:** [evidence root](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/).

| Артефакт | SHA256 |
| --- | --- |
| [Preimage template](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/preimage/trial-template.json) | `0a3e8aee3935afd524c242a59fdc44094d8e61f242a67abe582fb3b730bd8c97` |
| [Candidate template](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/candidate/trial-template.json) | `a39c1ddc3e0ded6edb2b4fc81d23884b706bb932b009d049096f151f46107020` |
| [Patch](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/goal-text.patch) | `a6f1950fd1b4bedd07ee074e40940d8af1f65e6ef17ece768de5abfc8dc058d2` |
| [Allowlisted semantic evidence](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/semantic-evidence.json) | `c237895211fcb2e931258a42b28a015189a49a669822a7c8c6c235f4457990e6` |

Template намеренно сохраняет исторические id/changed_at для одно-полевого review diff. **Он не готовый launch config и не новая authority.** Следующий владелец после review создаёт fresh goal id/version/changed_at в момент подготовки с прежним operator origin/evidence_ids[]/TTL15; исторические values/arm/epochs не используются повторно. Metadata обновления фиксируются отдельно от этого text-only patch.

## Validation и ограничения

**5/5 offline construction regressions PASS.** [Tests](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/test_prompt_semantics.py), [лог](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/offline-tests.txt), [reconstructed requests](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/reconstructed-construction.json).

Actual frozen `GoalClockState.snapshot`→`fast_projection(full)`→`ModelBackend.generate/generate_loaded` формируют prompt и request schema. Deterministic fixture задаёт только admitted/withdrawn bit, micOFF и clock; это не motor receipt. Transport sink сохраняет построенный request и сразу **бросает exception до сети**, model response не возвращается. Count заменён plumbing surrogate; **реальный tokenizer/token budget/inference/choice не проверены**. Audit hook запрещает connect/bind/DNS/subprocess. Проверены:

- Configs равны за исключением goal.text; actual prompt различается только тем же текстом, остальные payload fields/schema равны.
- Полный goal/clock и UNKNOWN проходят actual projection; audio/content/history не появились.
- Actual schema принимает `wait` при true и false, допускает только прежний settle при true и отвергает его при false; `attentive` запрещён.
- Все импортированные runtime bytes взяты из manifest-verified R16 archive. Шесть checkout runtime files read-only сверены с exact R16; изменений нет.

Patch dry-run/apply/reverse dry-run/reverse на отдельных temporary копиях PASS, `-F 0`, без fuzz/offset; bytes обоих направлений совпали. [Verification](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/patch-verification.json). [Manifest](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/candidate-manifest.json), [SHA index](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1489a-59ba-7730-ad22-52a9b5e70444/R17-evidence/SHA256.json). Входы: PROJECT/design v4, R13/R14/R16 docs, public archive template/manifest, allowlisted goal/model metadata и bounded actual output records. Private configs/raw media/credentials не читались и не копировались.

Single-field template diff не меняет original model/goal expiry, <300ms BEGIN/effect deadline, server CAS обоих targets, STOP/boot/epoch/owner/quiet/privacy, real expression-change fence, single-use/UNKNOWN/no POST retry/replay. Их новое live прохождение **не доказано**. Более длинный goal увеличит prompt/timing; budget проверяет прежний actual tokenizer admission, без расширения caps/deadlines. Даже после уточнения модель вправе снова выбрать wait.

## Scope следующего live — только S5 после отдельной review

Здесь запуска нет. После review candidate и явного окна/handoff S5 может провести **один fresh finite15s trial** exact R16/R15 stack с единственным text delta выше и fresh goal metadata. No service, camera/context, new models, другое движение, ручное действие, response retry или повторный arm. Preflight/drain/единственный owner и прежние guards обязательны; known failure/UNKNOWN означает HOLD/cleanup, не расширение deadline.

Минимальное дополнительное evidence — bounded passive capture **actual gateway request construction до transport**: system text, allowlisted FastView goal/op/clock/UNKNOWN и пустые content groups, actual json_schema и actual tokenizer counts; до16KiB/до4requests, без token/env/endpoints/private config/rawmedia. Сохранить точные bytes/SHA и original actual FastChoice/request IDs/reducer outcomes. Не менять prompt/output/schema в recorder. Если source/config/import hashes или allowlisted structure не совпадают — trial не интерпретировать как проверку этого candidate.

При wait зафиксировать честные accepted wait и завершить окно без forced action/rearm. Если модель сама выбрала settle — separately проверить proposal basis/version/original min-deadline, fresh BEGIN-age<300ms, attempted POST count≤1, оба server guards, independent pose telemetry roll1°→neutral и cleanup. Report acceptance/HTTP/latency не заменяют physical evidence. Unknown send outcome не повторять; старый slot не освобождать для нового эффекта. Финал: guarded durable motorOFF, verified idle/owners absent и normal listening/captureON по прежнему lifecycle.

Если actual wire уже содержит всё перечисленное и снова даёт wait, можно установить лишь «модель не выбрала settle при явной задаче и UNKNOWN», а не выдумывать скрытую причину. Следующее решение тогда отдельное; этот report не разрешает дальнейшее prompt tuning, guard edits или blind повтор.
