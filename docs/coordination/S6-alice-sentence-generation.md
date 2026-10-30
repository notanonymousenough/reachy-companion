# S6 — exact S4 sentence-generation prompt, source-ready

17 октября 2026, Europe/Moscow. **SOURCE-READY; 67 offline checks PASS, не установлен.** Кандидат поверх установленного по S5/D6 exact S4 `voice.py` меняет только две строки Alice opt-in prompt. Реальное улучшение генерации **UNKNOWN**: ни model calls, ни TTS, ни сеть/робот/Hub/PC/bridge/arm/deploy в S6 не использовались. R18 остаётся единственным hardware owner.

## Почему этот узкий delta обоснован

Прочитаны PROJECT, D6, S5, S4, S2/S3 и дизайн v4 §17 (ранний живой цикл/normal Alice exchange). D6: один seed → два полных normal replies → `sentence_shape`, `headers_sent=false`, HTTP422. Exact subtype **UNKNOWN**, rejected text не экспортирован. Утверждать «слишком длинный ответ», несколько предложений, отсутствие финального знака, многоточие или конкретную дробь причиной D6 нельзя. Первая проверка character-limit уже прошла, word-count после sentence-shape этим событием не установлен. Historical D5 predicate остаётся UNKNOWN.

S4 уже однозначно просит одно короткое законченное предложение, конечный знак, без обрыва/хвоста/многоточий/сокращений с точками. Поэтому ещё одно общее «отвечай короче» не добавлено. Но его **естественно-языковое** «одно предложение» слабее точного лексического контракта `[^.!?…？؟！。．]+[.!?]`: одно законченное предложение может содержать десятичную точку или `?!`; одно предложение может завершаться Unicode знаком. S4 не явно перечисляет все запрещённые внутренние/Unicode знаки. Это наблюдаемый source contract gap, а не реконструкция D6 текста.

В `ALICE_SHORT_FORMAT` перед прежним правилом о начальных метках добавлены ровно:

> В предложении используй ровно один знак из трёх: «.», «?» или «!», только в самом конце. Внутри предложения не используй «.?!…？؟！。．»; дробные числа пиши словами.

Никаких few-shot ответов, заданного содержания/арифметического продолжения, нового system framework или замены persona. Модель по-прежнему сама выбирает содержание и законченно формулирует мысль в прежних ≤10 body words/≤120 spoken chars с одним canonical `Алиса, `. Обе старые границы и все другие проверки сохранены. «Числа словами» относится к генерации; никакого runtime преобразования числа/ответа нет. Возможное уменьшение rejection — **гипотеза**, ещё не измеренная на actual model.

## Exact construction и границы доказательства

Preimage скопирован из [S4 candidate](/Users/notanonenough/reachy-companion/S4-evidence/candidate/voice.py) с проверкой S4 manifest и S5 transfer pin; не из checkout/HEAD. В exact S4 `prepare` только при `alice_short_replies=true` и effective prefix `Алиса, ` вызывает `answer(..., alice_short=True)`. Тот добавляет одну текущую `ALICE_SHORT_FORMAT` к первому system message перед history/interruption/user и единственным `brains.answer`; ACK в этом режиме выключен прежним кодом. История хранит spoken body без обращения, текущий format добавляется заново один раз. Кандидат **не меняет ни одной из этих функций**.

Для офлайн проверки фактической сборки raw generation payload отдельно заморожен `brains.py` из exact S0-base commit `2865db30e92fcb069c241c34bae4419ad65ed594`, SHA `732a8bae6c85eef4ae2b32bb4e24ebc869cd9040f12a6f19bf1eb3a4d4b328f6`. Reference исполняется с fixture config и локальным synthetic choice вместо HTTP. Проверены `Pipeline.answer → brains.answer → raw_prompt → Request` и отсутствие изменений model/temperature/max_tokens/stop/stream/URL/headers кроме prompt literal. Это **historical source contract**, не fresh deployed brains hash/actual wire/tokenizer/model proof. S4 manifest/D6 не содержат actual brains pin или exported private generation prompt. Никакой test reference не устанавливается. D6 `temperature=0/max_tokens=192` из fast CPU slot **не является настройкой main voice 9B**; публичные example settings тоже не выдаются за private production settings. Их изменение не предложено.

## Reviewable bundle / apply / rollback

| Artifact | SHA256 |
| --- | --- |
| [S4 preimage](/Users/notanonenough/reachy-companion/S6-evidence/preimage/voice.py) | `4ec7cfe56f7ee5a4b37ac9906a2c467b70983a6437a7840c25416695a5dfd4fd` |
| [S6 candidate](/Users/notanonenough/reachy-companion/S6-evidence/candidate/voice.py) | `224ff166401f7842deeec96c59f08585232bee971306c33e02c9fe45c1059b71` |
| [Exact forward/reverse patch](/Users/notanonenough/reachy-companion/S6-evidence/patches/voice.py.patch) | `912d31c7011cbd019922b3e43cab71a4ff74f3c867d7b9c55818b0e059ea5e10` |
| Required unchanged config module | `9773283044a22b2abefdebb885f1711592e6a22facd22988c4847ee815b1c703` |

[Manifest](/Users/notanonenough/reachy-companion/S6-evidence/manifest.json), [transfer manifest](/Users/notanonenough/reachy-companion/S6-evidence/transfer-manifest.json), [recipe](/Users/notanonenough/reachy-companion/S6-evidence/source-recipe.md), [verifier](/Users/notanonenough/reachy-companion/S6-evidence/verify_bundle.py). Transfer allowlist — только candidate voice + secret-free manifest. Verifier выполняет forward/reverse в disposable staging при whole-file preimage/patch/output hashes и `--fuzz=0`, foreign source отклоняет без изменения. Production target при будущем назначенном install — effective site-packages import, не `/app/src`. Recipe требует свежие owner/boot/generation/idle/ACL/backup и прежний config pin; rollback только от exact S6 к fresh exact S4 backup. Старые D6 generations не являются authority. В S6 выполнена только локальная проверка.

## Offline evidence

`python3 -B S6-evidence/run_offline.py`: **67 PASS / failures0 / errors0 / skips0**, Python3.13.0; 44 исходных S0/S2/S4 regression checks +23 проверок поведения/контракта кандидата. [Results](/Users/notanonenough/reachy-companion/S6-evidence/offline-results.json), [output](/Users/notanonenough/reachy-companion/S6-evidence/test-output.txt), [S6 tests](/Users/notanonenough/reachy-companion/S6-evidence/test_sentence_generation.py).

- AST equality всего модуля кроме одного `ALICE_SHORT_FORMAT` literal; старый literal восстанавливается удалением только двух новых строк. Валидатор, prefix, word/char limits, style parser/guard, handlers, все generation call arguments и ordering history/TTS идентичны S4.
- Actual prompt assembly на unary/stream `/text` и `/turn`, один model fixture call; request opt-in/human override/false/missing flag parity; неизменная config, body history и один текущий format при следующем construction. Дополнительно exact historical `brains` строит raw Request с текущим правилом, user/history/interruption сохранены; локальный choice fixture не обращается к модели.
- S4↔S6 validator equivalence **4091 inputs:36 accepted/4055 rejected**, включая приоритет typed first failure. Synthetic witnesses `Это 3.14.`, `Правда?!`, `Верно。`, несколько предложений и отсутствие финального знака по-прежнему отклоняются `sentence_shape`; это fixtures, не D6 текст/actual model evidence.
- Настоящие candidate POST handlers, через BytesIO/fake constructor без сокета: pre-header422 на всех unary/stream text/turn/say, safe enums, TTS0/rejected reply-events0/history commit0/lock released/idle; say modelcalls0, generation fixturecalls1, retry0. Safe post-header terminal event, no second status; generic backend503 parity с S4. Direct TTS boundary/cancel/STOP/ACK/whole aggregate/8-segment tail checks сохранены.
- Socket creation запрещена runner. Synthetic fixture responses/audio не считаются actual моделью/голосом/playback. Не использованы grammar/stop-on-punctuation, truncation/rewrite/fallback/automatic retry/rearm, новая metadata или более слабые ограничения.

Записи только `S6-evidence/` и этот report. Protected snapshot/verification показывают неизменные checkout voice/brains/config/Agent/ExpressionPlayer/router/native, PROJECT/design/baseline, S4/S5/D6 frozen references; конфигурационные secrets не копировались. Known error/D0 terminal, STOP,300ms/no-POST-retry не переписаны. Runtime state S6 не опрашивала; hardware state берётся только как historical receipt D6, не новая attestation.

## Один bounded actual acceptance, после отдельного назначения owner

После source review и fresh owner admission — только **одно** normal Agent→Hub→PC→Piper→robot→соседняя Алиса окно: один штатный seed «Алиса, сколько будет два плюс два?», затем actual external capture/STT/main replies без человека, injected transcript, forced answer/reseed или retry. Same model/config/sampling, motorOFF, observerOFF; только этот prompt delta.

Предустановленный cap **595s/30 полных normal replies/первая ошибка**, дополнительный stop после45s без следующего полного normal completion. **PASS гипотезы:30 normal completions подряд, 0 format rejections/other errors/stalls**; лимит времени без30 — INCONCLUSIVE. До третьего хода улучшение не заявлять: D6 провалился на третьем. Любая ошибка прекращает окно, без повторного пробного ответа; known422/error остаётся terminal. Safe existing S4 reasons/headers/status и completion/capture counters; error collector читает только от последнего полного completion до STOP (при stall — последние45s), ≤16records/16KiB, без rejected text/media/exception body; полные completion counts берутся из обычного bounded status collector, truncation любого evidence явно отмечается. Успешный HTTP/reply-event не равен полному playback. Cleanup — verified idle/free/owners absent, затем отдельное штатное normal-listening восстановление по existing policy, не продолжение теста.

Даже PASS30 — ограниченная acceptance этого prompt, не статистическое доказательство надёжности/≥30min/PCM≤5s/combined autonomy. Если повторится `sentence_shape`, гипотеза не принята: **не начинать серию prompt tuning**. Следующий единственный адресный probe, если отдельно назначен, — только на первом таком отказе bounded structural counts после той же prefix normalization/aggregate: ASCII-terminal count≤2, forbidden Unicode count≤2, final-class enum (`ascii_terminal`/`unicode_terminal`/`other`/`empty`), internal-reserved count≤2; после emit немедленный штатный отказ/STOP. Ни text/substring/hash, ни content-derived arbitrary keys, ни новая framework/request-ID схема; checker/422/TTS/history порядок сохраняется. Сам probe в S6 не реализован/не назначен. Дальнейший fix только по измеренному классу либо честное UNKNOWN при исчерпании окна.

**S6 закончена как source-ready prompt-only candidate с измеримым одним acceptance gate. Actual generation improvement/D6 exact subtype/physical/soak остаются UNKNOWN.**
