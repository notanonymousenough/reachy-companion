# R23 — last single local-format capability pivot

17 октября2026, Europe/Moscow. ROOT11:43 разрешил≤25min, **hard end12:08MSK**. Source начат11:44:13; hardware owner S7, source owner R23 в прежнем R21 chat. Только `R23-evidence/*` и этот report; checkout/hardware/model/SSH/deploy0, новых чатов/подагентов/reviews0.

**Решение:** одна честная capability-проба `response_format` на **прежнем raw `/v1/completions`** с **точными actual legacy template/assistant_prefix/stop**, той же9B/temp/token cap и неизменными schema/decoder/validator R22. Поддержка raw structured field **UNVERIFIED**. При FAIL — всё local-format направление STOP, без вариантов/retry. При PASS — только один existing-bind voice candidate и фиксированная normal voice приёмка, не автоматический успех.

## Frozen ASAP:11:44:48MSK (<1min source)

- [Frozen gate](../../R23-evidence/FROZEN-GATE.json), [exact fixed messages](../../R23-evidence/protocol-messages.json), [request shape](../../R23-evidence/protocol-shape.json), [операторский protocol contract](../../R23-evidence/PROTOCOL-GATE.md).
- Candidate [voice.py](../../R23-evidence/candidate/voice.py) **`9e1e178b1b8281411233542a919511680c42ae4ce129fdaee7b93c06e4302d03`**, S6 preimage224ff166401f7842deeec96c59f08585232bee971306c33e02c9fe45c1059b71. **Один production file**, без новых module/mount/SDK/dependency/config/template/model.
- Actual unchanged brains **9c69d27979dce500148c06ee8d1dc58e90aabae3e5a2b1d3fc8edfb9e754642d**, источник S7 readiness; никаких отсутствующих repo helpers/reservation imports. Raw builder code **3fbd2f614d91d7868d7ffb8654bda30f304586bd80f546ffff44f6eb08d7948f**.
- Schema **34e43703d48e3645b4391c6fa38d44bdb84e3217d6a3691157402407796c7b15**, decoder **fa911c400147411de54a985701e69e7b9ba39b3ce10a638c50fd9d4c535f152c**, validator **552f83811f844eaf402ff1dab6191e250487e26dd876c7ec4801451d0701f448** — exact R22 freeze. Instruction `ALICE_GENERATION_CONTRACT` также не менялась. После actual gate source/contract variants запрещены.

## Что конкретно проверяется

`alice_generation_request(actual_config, fixed_messages)` исполняет **тот же** nested clean→`message_template.format(role,content)`→join→current assistant_prefix, что реальный installed legacy brains. URL — current base+current api_path, требуется exact `/v1/completions`; JSON serialization как legacy (`json.dumps` defaultASCII), model/prompt/temp/max_tokens/stream/stop сохранены, добавлено **ровно `response_format`**. Проба не должна использовать ручной другой prompt или R22 chat carrier. Actual request bytes/hash/current template binding фиксирует S7, private values не экспортирует.

Formal FINAL — **только `choices[0].text`** из matching same-model single-choice terminal stop. Не `message.content`, не reasoning, не tag stripping. Frozen strict decode `words[]+terminal` → declared exact join renderer → неизменный validator → прежние segments/Piper/history. Общие120 chars/normalized wake gate остаются host checks; malformed/long/wake/truncated не доходят до TTS, retry0. Schema lexical words не обещает semantic completeness. Existing Pipeline.lock/self.http и UNKNOWN latch как R22; default-human/false mode/explicit old constraints/control/STOP/privacy/STT/PCM не менялись.

Fresh restored known-ready baseline → guarded micOFF/drain/worker+same9B known idle → **одна actual gate ≤11:53**, metadata-only HTTP/model/index/finish/text type+length+SHA/strict decode/render/validator/current instance before/after. HTTP200 сам по себе не PASS. Unsupported/ignored field, empty/free-text/non-JSON FINAL, bad render/identity/UNKNOWN → **FAIL/NO INSTALL/entire direction STOP**, без raw grammar/endpoint/template/schema/model variants. R22 fail не объясняется выдуманным reasoning-routing диагнозом.

## Source proof и conditional deployment

**11 focused offline checks PASS**, failures/errors/skips0: [log](../../R23-evidence/offline-tests.txt), [receipt](../../R23-evidence/offline-results.json). Особый wire test исполняет **actual brains9c69 request construction** с fakeHTTP: удаление только response_format из candidate даёт те же parsed fields и **те же legacy JSON bytes/URL/headers** для тех же messages. Полный candidate Pipeline stream→raw request→strict envelope→choice.text→renderer→unchanged validator→synthetic Piper/history проверен; invalid/long/duplicate wake/UNKNOWN не TTS/retry. Frozen hash equality и exact forward/reverse patch PASS. Это не actual backend/voice evidence.

После **PASS actual raw gate**, один [install/rollback recipe](../../R23-evidence/INSTALL-ROLLBACK.md): fresh OFF/known idle, same existing container stop/write only existing effective voice bind/start, actual imports/hash/unchanged config+ACL+mounts; normalON. Config/Piper output+2dB/camera publisher/normal movement сохраняются. Новая container generation не считается cancellation старой inference.

Одна fixed **480s/30normal completions/noerror/45sstall** live приёмка, start≤11:59, total deadline12:08; first failure→reconcile/rollback, никакого второгоseed/source tuning. Production install/live/seed пока **0/UNTESTED** source scope. S7 actual receipt отдельно решит PASS/FAIL; source checks не принимают устойчивую Alice voice/PCM/acoustic duration.

Если rawFAIL: useful current localON/operator camera/Piper/+2dB сохраняются. **Одна следующая foundation alternative только ROOT:** официальный ConversationApp hostedHF из [готового recipe](../../R21-evidence/launch-recipe.md), отдельный bounded20–30min setup/acceptance scope с stop при dependency/allocator blocker, без предположения фактического срока установки. Меняются front door/model/voice/STOP semantics, audio и запрошенные camera frames идут во внешний HF; existing local stack сохраняется для поэтапного возврата, один physical owner обязателен. Это reviewable альтернатива, не запуск и не completion полного memory/persona/goals/S3/VPS target.

Source handoff/полные pins и transfer allowlist фиксируются в manifest после упаковки. Никаких дальнейших local-format исследований/variants без нового ROOT foundation decision.

**Явный SOURCE HANDOFF:** [bundle](../../R23-evidence/R23-source.tar.gz), SHA256 `65a4ab3fc4e201578f68214cbd1e295ef8a9ee5d6d0c11c14b1b0a8f5dc19e0b`; [manifest](../../R23-evidence/transfer-manifest.json), elapsed 153.336s. Source-владение освобождено TechLead; next checkpoint только S7 single frozen raw gate. Candidate/schema/decoder/validator после freeze не менялись.

## Actual terminal outcome — protocol PASS / voice FAIL / direction STOP

[Actual S7 raw protocol](../../S7-evidence/R23/probe-result.json): oneHTTP200/stop, strict decode/render/unchanged validator **PASS**,2.133619s. [Installed voice](../../S7-evidence/R23/install.json) matched frozen9e1e178b… in same container/image, config/private config and ACL preserved. This is **not voice acceptance**.

[One actual live window](../../S7-evidence/R23/live/live-report.json),11:49:59.552→11:50:11.146MSK: **FAIL first503 at11.235274s, normal completed replies0, voice_trials1**. One operator seed completed at5.834736s; it is not a normal reply or success for the declared480s/30completion gate. Existing STOP followed. Source does not infer the internal503 exception from this receipt; S7 collects only the existing first exception/known terminal, restores exact S6 and normal-ready fallback. Rollback completion is pending its actual receipt, not presumed here.

**ROOT local-format direction STOP:** no new helper/source fix/endpoint/schema/template/prompt variation, reprobe/reseed or retryfallback. Frozen R23 source/bundle remain unchanged. [Terminal metadata](../../R23-evidence/actual-terminal-result.json). **Source explicitly released/parked.** One concrete prepared foundation alternative is [R24 official ConversationApp+HF scene](R24-ready-baseline-alternative.md), conditional15–25min with product/privacy/STOP/rollback impact; HFlaunch0 until ROOT chooses. Useful current localON/operator camera/+2dB/movement must be preserved by sole operator handoff; strict normal Alice remains unaccepted.
