# S1 — exact S0 installed; first normal reply rejected

17 октября 2026, Europe/Moscow. **Short live acceptance FAIL / exact blocker:** первый ответ normal STT→LLM содержал несколько expression segments и получил `AlicePhraseRejected: Exactly one complete Alice segment required` **до TTS**. Seed завершён, следующих полных replies **0 из 2**. Rejection не считается успешным диалогом. Один seed, одна normal попытка; повторного обмена и model retry не было.

**Финал 06:07:05,324 MSK:** S0 source оставлен в существующих effective binds, **opt-in OFF**; private worker config восстановлен byte-for-byte. Normal listening/capture **ON mic239/generation14**, bytes2564096→2643968, last_error=null, interruptions0; один Agent arecord211737→205817, APLAY отсутствует. A1 source/config, Agent205817/boot `f2a66c3b-dc89-4a2f-961d-ab738696b950`, factory150625/NRestarts0 сохранены. Policy124 motor=false/quiet=false/privacy=false/owners absent; Hub free/stock known/unowned, worker idle/ok. **S1 завершён и явно освобождает исключительное аппаратное/инженерное владение Reachy/Hub/PC.**

## Установка и effective pins

Входы: [S0](S0-alice-short-replies.md), [baseline](runtime-baseline.md), [A1](A1-continuous-live.md), [PROJECT](PROJECT.md). Новые чаты/подагенты не создавались; autonomous source/config/session не менялись. Свежий preflight подтвердил исторический N4 финал mic235/generation11, но CAS использовал новые GET, не исторические payload. Hub192.168.2.181 и PC192.168.2.134 подтверждены установленным local deployment config/hostname и ранее зафиксированной прямой пользовательской авторизацией.

Exact builder `deploy/autonomous/prepare_alice_short_replies.py` воспроизвёл два S0 output; **10/10 offline tests PASS**. Переносились только generated `voice.py`33088B и `config.py`14589B из явного `transfer-manifest.json`. README/factory credential, private config, tokens, logs, raw PCM/media не передавались. Первоначальный большой inline SSH exec отвергнут транспортом до исполнения; staged SCP заменил только способ передачи. Windows ACL использует well-known SID вместо локализованного имени Administrators. Нерешённого auto-review отказа и обхода нет.

| Effective item | Pin / фактическое состояние |
| --- | --- |
| Existing container | `reachy-alice-two-ro-e589fef15c1d4f85baa7cf48244fdb5d`, ID `c46d9afc583eabd612cebae22ea6609b188769f54eac842010d65ec4ce443fc9` |
| Image | `sha256:0e42c38ae2b0b91873ba3cda454edf2cc3646ed4016a038a3dd12f3214120e3d` |
| Effective imports | `/usr/local/lib/python3.13/site-packages/reachy_companion/{voice,config}.py` |
| voice preimage → installed | `92cf69096fd6f08551a13a9c44d85fbbfc0470ca2f17315616691044018ab865` → `b4afda9d2ead77e405612badfea12f5fc8674f4c4e7fc480404f0334d774ddc7` |
| config module preimage → installed | `c0b0e7a8470401a20b684ada3132784e0805333f9ab56c18b1f8d585d7eb3436` → `9773283044a22b2abefdebb885f1711592e6a22facd22988c4847ee815b1c703` |
| Recognition module, unchanged | `6211a01e8d4ecf515636d4407856fddcf6e5deec4ddbd5639ae977770111f15f` |
| PID1 effective config | `--config /config/config.worker.local.json worker serve`; его hash до/после rollback `7aca57ff6fc0f93ffa821ff8d2686555c86aca6caaade7f9a8de37ffb06b274c` |
| Config while enabled | `b864d375b128c49dfa6aacc9caa52ef34c0dd7d5f2a4a32f2d7bcdd4193676e7`; единственный semantic diff `conversation.alice_short_replies`: absent→true |
| Other PC config, unchanged | `/config/config.local.json` `ae0535ca2b23bc7b0544f45c1d7979f6000df082b9c8cc44de17bffa02fe6b4e`; **этот файл PID1 не использует** |
| Prefix / model selectors | Worker default prefix=""; штатный Agent передаёт request prefix=`Алиса, `. `lm_studio`, прежний streaming=true, faster_whisper, Piper `models/ru_RU-ruslan-medium.onnx` |
| Final container generation | StartedAt `2026-10-17T03:05:06.916878049Z`, running, rootfs/read-only code binds сохранены |

Вторая пара overlays `/app/src/reachy_companion/{voice,config}.py` осталась прежней92cf/c0b0; её source directory отличается от effective site-packages. Установка проверялась реальными imports после controlled start, не checkout. На PC в закрытом для User/SYSTEM/Administrators `C:\Users\User\reachy-shadow\S1-short-01a147cc\` сохранены source preimages, private `config.worker.preimage.json` и исходные SDDL. ACL обоих source файлов и worker config после всех изменений **совпадают** с backup.

Последовательность: guarded OFF235→236, paused/no capture/free/idle → backup → stop существующего container → in-place запись ровно двух его host bind sources → start при default false → readiness/output hashes → только opt-in → restart того же container → active imports/flag/readiness. После failure — STOP237→238 → paused/free/idle и exact own output/config hash guard → byte-identical private config rollback → restart того же container → flag=false/readiness → новый guarded ON238→239. Всего три controlled stop/start transitions; Docker `RestartCount=0` отражает отсутствие automatic restart, **не отсутствие этих explicit transitions**. CREATE/replacement/второй worker и restart Docker Desktop не выполнялись.9B/STT/Piper voice/weights/settings, Hub/Agent/factory/audio pump не менялись; обычный worker startup не называется отсутствием model initialization.

## Единственное live окно 06:04:09,719–06:04:21,946 MSK

Normal Agent, прежние маршруты и session; observer только читал status и пытался читать `/proc`. Нового voice controller/ASR/recorder/harness не было. Manual seed вызван один раз после normal ON236→237 и capture readiness.

| Событие | Реальный receipt |
| --- | --- |
| Seed, elapsed3,666s | **«Алиса, сколько будет два плюс два?»** — ровно один canonical prefix, одно завершённое предложение, **6 слов** вместе с обращением по `[^\W_]+` |
| Seed completion, elapsed7,424s | `/stream/say` HTTP200; штатный manual endpoint `ok=true`, canonical `spoken_text`, один segment. Один TTS dispatch следует из exact S0 control path; отдельного live dispatch counter нет. Call span3,758s включает HTTP/TTS/воспроизведение/tail, это **не PCM duration** |
| Normal input | Ровно один `/transcribe` HTTP200 в03:04:20,442UTC; Agent processing, worker thinking наблюдались. Raw transcript не сохранялся. Идентичность внешнего speaker акустически UNKNOWN |
| Normal reply |03:04:21,265UTC `stream_failed` / `AlicePhraseRejected: Exactly one complete Alice segment required`; затем единственный `/stream/text` HTTP503 в03:04:21,269UTC |
| Termination | failed turn обнаружен11,755s; guarded STOP237→238 завершён12,080s. Agent.turns4→4; следующего seed/retry/второго normal turn нет |

Validator отклонил **несколько segments**, а не доказанно превышенный word count. Текст/число слов отвергнутого ответа недоступны; нельзя называть его коротким или длинным. Exact exception boundary расположен до reply/audio yield и первого TTS вызова; поэтому для этого normal turn dispatch0 и replacement speech0 следуют из выполненного code path. Одна inference/model retries0 — свойство exact worker пути, отдельного live model call counter нет. Worker `/status.last_turn` остался **seed**, не отвергнутый ответ; его lengths не переиспользованы как ответный turn. Agent last_transcript также остался прежним после error.

Ошибка observer: ожидаемый `/home/deploy/reachy-companion/scripts/factory_ssh.py` на Hub отсутствовал. Ни одного live process observation не получено; **role-qualified full APLAY completion UNKNOWN**, несмотря на seed endpoint `ok=true`. Это ошибка измерения, не доказанный playback defect. Отдельный final read-only `/proc` check выполнен локальным существующим helper через Hub с public host pin из Hub known_hosts; он подтверждает финальный arecord/no APLAY, но не дополняет прошедшее окно задним числом.

В raw observer event ошибочно hardcoded `words=7`; воспроизводимый `analysis.json` пересчитывает исходный exact spoken string и фиксирует **6**. Raw receipt/source сохранены с явной поправкой, а не заменены. Полного PCM frame meter в installed stream telemetry нет: фактическая PCM duration и акустические≤5s **UNKNOWN**. Word count не является акустической гарантией.

## Сохранение A1 и отдельные verdicts

ON создаёт generation12; manual `/say` retires её и после seed начинается generation13. Непрерывность через manual seed **не заявляется**. Generation13 observations7,719…11,754s:6144→135168B (**+129024B**), processing10,397…11,490s:+34816B, одна generation. Короткий sampled thinking представлен одной строкой, отдельного300ms main interval нет. STOP финализировал145408B, gap_events=overflow_events=superseded_events0, suppressed_frames6400, retired=true. Own-output suppression и counters сохранены; это не новая приёмка AEC/успешного reply playback. Исторический ограниченный A1 PASS не переоценивается.

| Критерий | Verdict |
| --- | --- |
| Exact S0 install / flag activation | **PASS**, реальные output imports и active config подтверждены |
| Seed prefix / sentence / ≤11 words | **PASS**, один prefix,6 слов, один segment; dispatch1 code-derived |
| Два consecutive external STT→LLM→full replies | **FAIL**, первый input/STT дошёл до LLM, reply rejected, completed replies0/2 |
| Failed-turn fallback до TTS | **PASS для наблюдённого multi-segment rejection**, HTTP503, без replacement speech; не dialogue success |
| Normal replies prefix/count/≤5s | **UNKNOWN / не достигнуты**, accepted reply отсутствует |
| Seed фактическая PCM≤5s / role-qualified APLAY completion | **UNKNOWN**, meter отсутствует / process observer не стартовал |
| A1 installed invariants / short PCM progression | **PASS** source/config identity и измеренные byte deltas; новый full STT/main/APLAY continuous PASS не заявляется |
| Rollback / normal listening handoff | **PASS**, flag absent/default false, exact private config восстановлен, healthy idle worker, mic239/generation14 ON |

## Cleanup и следующий scope

Собственные SSH команды завершились; persistent forwards, processes, stage на Hub/Reachy, grants/listeners/tokens не создавались. Две staged `.candidate` копии на PC удалены; private rollback directory/preimages/ACL сохранены. Hub config7f11d114…/service78887/NRestarts0 и A1 Agent/capture/config de362b7f…/5fe20c69…/a6171f68… совпали. Agent и factory active с прежними PID/NRestarts0. Финальные два status reads подтвердили generation14 PCM progression, worker idle/ok, Hub free/known/unowned и owners absent. Last_error=null; сломанный silent opt-in runtime не оставлен.

Конкретный следующий scope: **форма normal LLM output несовместима с требованием S0 одного expression segment**. Отдельно подготовить адресную source/prompt правку для этого exact worker и лишь затем новую ограниченную приёмку с исправленным read-only observer. В S1 validator не ослаблялся, ответы не обрезались, HEAD/модели не подменялись.

Evidence: `/Users/notanonenough/.codex/visualizations/2026/10/17/01a147cc-0ea8-7b42-94fb-4ba9e08cb5e7/S1-evidence/`.30 payload files, `SHA256.json` SHA-256 `a65390f983c8620bbdc4f64c177a6163c44294d3deea25bec300b1227602ff17`. Основные receipts: `live-report.json`, `filtered-live-http-errors.json`, `analysis.json`/`analyze.py`, effective imports до/default-false/active/final, `pc-container-{before,final}.json`, `rollback-optin.json`, `robot-final.json`, `final-http.json`, `pc-cleanup.json`. Evidence не содержит private config bytes, tokens, env credentials, raw transcript/PCM/media.
