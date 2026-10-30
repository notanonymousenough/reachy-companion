# S4 — typed Alice rejection taxonomy, exact deployed S2, source-ready

17 октября 2026, Europe/Moscow. **SOURCE-READY / offline PASS; production не менялась.** Подготовлен минимальный worker-only candidate поверх exact deployed S2 `voice.py` SHA256 `cfd55a2e930869a6d82b77325fab913d18dae2f42a888ca1e670775edf532681`. Ожидаемый `AlicePhraseRejected` до headers теперь отличим от backend/unavailable: **HTTP 422**, bounded JSON `{"ok": false, "error": "alice_phrase_rejected", "reason": "sentence_shape"}` (reason здесь только пример enum, не вывод о D5). Unexpected stream failure сохраняет прежний generic HTTP 503/body. **Taxonomy не устраняет все rejections, не чинит неизвестный predicate D5 и не закрывает failed ≥30min soak.** Actual model/live/physical acceptance остаются UNKNOWN.

Прочитаны окончательные [D5](D5-503-producer-records.md), [D4](D4-terminal-503-diagnosis.md), [S3](S3-alice-format-live.md) и [S2](S2-alice-format.md). D5 доказала worker `/stream/text` `AlicePhraseRejected` у составного `validate_alice_phrase:66`, до HTTP 200 и TTS этого ответа; **конкретный нарушенный predicate и exact cross-host request correlation UNKNOWN**. S4 не называет причиной длину/пунктуацию/prompt и не исправляет формат предположением. Исторический exact source взят из D4 `sources/S2-voice.py`; независимое воспроизведение frozen S2 builder в тестах совпало побайтово. Checkout/HEAD как preimage не использовался.

## Изменение и контракт

[Candidate voice.py](/Users/notanonenough/reachy-companion/S4-evidence/candidate/voice.py) меняет только enum/типизированное исключение, разложение составного validator, typed raise существующего style guard и отдельный catch в unary/stream POST handlers. Prompt, model arguments/call count, parser/expression behavior, prefixes, TTS/audio/PCM limits и history/lock lifecycle сохранены. Существующий валидатор не ослаблен: те же regex/Unicode-normalization/type check/границы, та же последовательность short-circuit, тот же accepted body. Сохраняются одно полное предложение, ≤120 символов с canonical `Алиса, `, ≤10 слов body/≤11 вместе с обращением, wake/duplicate-address запреты и повторная проверка на TTS boundary. Новых rewrite/truncate/retry/rearm/model calls нет.

`AliceRejectionReason(str, Enum)` хранит стабильные content-free значения. Возвращается **только первая нарушенная проверка**; это не полный набор нарушений и не характеристика исторического D5 ответа.

| Reason enum | Прежнее условие S2, в прежнем порядке |
| --- | --- |
| `text_type` | `type(text) is not str` |
| `edge_whitespace` | `body != body.strip()` после прежней нормализации одного leading prefix |
| `character_limit` | `len('Алиса, ' + body) > 120` |
| `forbidden_symbol` | прежний regex control/markup symbols |
| `sentence_shape` | прежний fullmatch одного законченного предложения |
| `word_count` | прежние 1…10 regex words в body |
| `wake_name` | прежние NFKD/casefold/combining/mixed-alphabet wake-name проверки |
| `style_word_boundary` | уже существующее S2 несоответствие words до/после expression parsing в `prepare` |

Exception принимает только enum, его `args`/message содержат фиксированный code и enum. В обработчиках ожидаемый rejection логируется одним `LOG.warning('alice_phrase_rejected reason=%s headers_sent=%s', …)` **без `exc_info`/traceback/exception chain**. JSON содержит только `ok=false`, фиксированный `error`, enum `reason`; фразы, user input, session/token/PCM, длины и arbitrary exception message не добавляются. В тестах JSON/error-event ≤128 bytes и warning message ≤96 chars для всех восьми причин; это bound application payload/message, не formatter timestamps/HTTP headers. Prefix/answer не включаются в rejection metadata.

До первого iterator event stream получает 422 вместо 200/503, без NDJSON reply/audio и TTS. Unary `/text`, `/turn`, `/say` получают ту же typed 422. Если typed rejection неожиданно возникнет **после** отправки 200, handler не пытается изменить HTTP status: пишет bounded `type=error` event с теми же code/reason и закрывает iterator. Это defensive branch, не обещание retract уже принятого output. Первоначальный generic stream `except Exception`/503/error-event и unary unexpected/upstream branches побайтово/AST сохранены; body generic stream остаётся `{"error":"Worker stream failed"}`. Existing unary generic exception body по S2 не перепроектирован.

**Worker-only attempt ID не добавлен.** Reason и `headers_sent` достаточно для различения локального ожидаемого отказа и unavailable. Новый worker ID без изменений Hub/Agent не связывал бы три host records и неоправданно расширял бы scope; cross-host correlation сохраняется UNKNOWN. Статус 422 остаётся HTTP error для существующих клиентов; Agent/Hub/native/status/recovery не менялись. Known `phase=error` остаётся terminal по D0; taxonomy не предоставляет recovery, retry или authority.

## Exact bundle и перенос

Собственный [manifest.json](/Users/notanonenough/reachy-companion/S4-evidence/manifest.json), SHA256 **`04bf899a997e3a1dc1d0c02c65cb81a2c09f0114b34294189f69c185c195620d`**, фиксирует 10 payload/test/receipt files, семь origin references и required config pin. Config output отсутствует; transfer allowlist содержит только candidate `voice.py`.

| Artifact | SHA256 |
| --- | --- |
| [S2 preimage](/Users/notanonenough/reachy-companion/S4-evidence/preimage/voice.py) | `cfd55a2e930869a6d82b77325fab913d18dae2f42a888ca1e670775edf532681` |
| [S4 candidate](/Users/notanonenough/reachy-companion/S4-evidence/candidate/voice.py) | `4ec7cfe56f7ee5a4b37ac9906a2c467b70983a6437a7840c25416695a5dfd4fd` |
| [Exact forward/reverse patch](/Users/notanonenough/reachy-companion/S4-evidence/patches/voice.py.patch) | `99e4c82dfe432a7e4435f5807c74dbcf64d274cf57dc7f041708d683de8800f6` |
| Existing required config module, unchanged | `9773283044a22b2abefdebb885f1711592e6a22facd22988c4847ee815b1c703` |

[Apply/rollback recipe](/Users/notanonenough/reachy-companion/S4-evidence/source-recipe.md) и executable local [verify_bundle.py](/Users/notanonenough/reachy-companion/S4-evidence/verify_bundle.py) проверяют exact input hash до `patch --batch --fuzz=0 -p1`, output hash после forward/reverse и отказ на foreign source без изменения bytes. Проверка применяет patch только в disposable temp staging, не production. Future deployment owner обязан получить fresh authority/boot/generation/owners/imports и сохранить свой exact backup/ACL; effective import должен быть `/usr/local/lib/python3.13/site-packages/reachy_companion/voice.py`, не `/app/src`. При другом source/config-module/generation требуется остановка и отдельный review, не подстановка HEAD. Rollback только от своего проверенного S4 output к exact S2 backup/preimage; private config/Agent state не откатываются, config delta отсутствует. Исторические S3/D5 generations не являются fresh authority/CAS payload.

## Offline validation и пределы

Адресные [tests/test_alice_rejection_taxonomy.py](/Users/notanonenough/reachy-companion/tests/test_alice_rejection_taxonomy.py): **20 PASS**. Вместе с frozen S0/S2: **44 PASS, 0 failures/errors/skips**, Python 3.13.0. Команда `python3 -B S4-evidence/run_offline.py`; [runner](/Users/notanonenough/reachy-companion/S4-evidence/run_offline.py) запрещает socket creation, фиксирует [offline-results.json](/Users/notanonenough/reachy-companion/S4-evidence/offline-results.json) и [test-output.txt](/Users/notanonenough/reachy-companion/S4-evidence/test-output.txt). Ни actual model/Piper/STT, ни TCP/SSH/HTTP/робот/Hub/PC/bridge/deploy/arm не вызывались. HTTP POST handlers исполнены настоящим candidate-кодом с BytesIO и fake server constructor, без сокета.

- Direct S2↔S4 validator equivalence на **4091 входе: 36 accepted / 4055 rejected**; accepted body совпадает. Корпус включает 120/121 spoken-character boundary, 0/1/10/11 body words, типы, punctuation/Unicode wake names, controls/markup, prefix/whitespace и комбинации нескольких нарушений, плюс deterministic random seed503.
- Все enum/first-failure priorities, bounded exception args, in-word style boundary; safe metadata для каждого enum даже при secret exception chain. Rejected text/input/session/PCM не попадают в body/log; typed catch не логирует traceback.
- Actual POST `/text`, `/turn`, `/say` и `/stream/{text,turn,say}`: ровно HTTP422 до 200, TTS0, rejected reply/audio events0, history commit0, lock released/idle, model fixture calls1 (say0), без retry. Размер Content-Length соответствует JSON.
- Defensive post-header typed event: один HTTP200, safe terminal error event, iterator closed. Unexpected backend pre-header503/body/log messages совпадают с exact S2; generic branches AST-identical.
- Все прежние S2 behavioral tests на S4 candidate: canonical prefix/full aggregate, 11/12-word boundary, style splits/8-segment tail, default/absent/false flag и human override parity, prompts/config scope, one TTS dispatch, history/cancel/STOP/ack и TTS-boundary refusal.
- AST equality вне narrow taxonomy/handler delta, guarded portable patch forward/reverse exact и foreign-source rejection. [verification.json](/Users/notanonenough/reachy-companion/S4-evidence/verification.json): 10 files +7 origins verified, compile PASS, protected source/docs hashes unchanged.

Записаны только собственные `S4-evidence/`, адресный test и этот report. Checkout `src/reachy_companion/voice.py` отличается от deployed pin и **не менялся**; config/Agent/router/native и PROJECT/runtime/live baseline сохранены по own before/after hashes. Q5/R15 expression pair, hardware/runtime/controls/recovery не затронуты; чаты/подагенты не создавались. Production текущим read-only snapshot не проверялась: S4 не использовала сеть и не заявляет свежую runtime attestation.

**S4 завершена как source-ready taxonomy.** Конкретный D5 predicate, exact cross-host attempt и actual model acceptance остаются UNKNOWN. Ни успешный долгий диалог, ни ≥30min soak, ни PCM≤5s этим offline result не доказаны.
