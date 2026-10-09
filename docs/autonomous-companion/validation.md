# Проверка проектных артефактов, ревизия1.1

2026-10-09. Второй проход завершён конечными локальными проверками. Запускается только проверка файлов; inference, службы, сеть и физические устройства она не использует.

```text
PASS: 2 schemas, 22 fixtures, 11 negative cases, 12 finite authority traces, 22 interruption traces, 18 context budget checks, 19 local links
No hardware/model execution. Cryptographic signatures, JCS and timing were not tested.
```

Проверено:

- Обе JSON Schema draft2020-12 проходят meta-schema validation; 22 fixtures проходят общий oneOf и ожидаемую конкретную definition.
- Формат времени проверяется strict UTC regex и календарным разбором; non-finite JSON отвергается. Интервалы, мягкий/жёсткий срок задач, stable-prefix и scene/interaction поля согласованы в примерах.
- Negative fixtures: fake activity, несуществующая календарная дата, grants в function, ready sensor при disabled, model-generated epoch, двойная speech+commit, VPS policy patch, excessive trait delta, raw shell template, path traversal и web limit.
- Межфайловая цепочка ready input → compact view/choice → trusted binding → canonical commit → MainProposal/MainSegment связана по ids, revisions, deadlines, evidence и task id.
- 12 конечных authority checks: base acceptance; отдельное изменение каждого hub/compute/robot boot, operator/microphone/interaction/speech epoch; stale attempt; suspected pause resume eligibility; отказ после confirmed turn/mute. Это проверки выбранных инвариантов контракта, а не тесты ещё не реализованных акторов или всех scheduler races.
- 22 interruption traces: граница2999/3000 ms, empty/self echo, задержка STT>3 s, pending/error/no_data/offline, mute/confirmed turn, stale authority, missing cursor/expired plan, сброс при внешней неразобранной речи и unknown hearing, новые3000 ms после восстановления, revoke при validated late final. Это конечная модель guards, не проверка реального VAD/STT/playback.
- 18 main budget checks: полные4K/8K/32K profiles проходят; превышение каждого input component, общего runtime context и unknown vision accounting отвергаются. Output512/reserve256 и selected profile/context согласованы; реальный tokenizer/image processor ещё не проверен.
- Все локальные Markdown ссылки и пары code fences проверены, `git diff --check` проходит. Прежние src/config/службы не менялись; новый каталог не содержит реальные LAN IP/Bearer values/локальные секретные пути.

Воспроизводимая команда в текущем исследовательском окружении:

```sh
/private/tmp/reachy-design-validate-venv/bin/python docs/autonomous-companion/validate_design.py
```

Для другого окружения нужен Python3 с `jsonschema`; зависимость устанавливать в отдельное проверочное окружение. Скрипт [validate_design.py](validate_design.py) read-only, не импортирует reachy_companion и не обращается к устройствам. Temp venv не является зависимостью рабочего проекта. Форма будущего JSON Schema validator должна включать format validation.

Не проверено этим проходом: фактический токенизированный размер prompt/model latency, kernel preemption, VRAM peak/paging, PCM cursor/AEC/stop timing, криптографические подписи/JCS, S3 provider semantics, personality drift на реальных эпизодах. Mermaid и псевдокод проверены чтением; отдельного Mermaid-rendering engine не запускалось. Все числовые latency/naturalness ограничения — цели, не результаты устройства.

Две ограниченные повторные SSH-проверки второго прохода (ПК и hub, по одной) завершились connection timeout. Повторов после них не было. GGUF/projector опубликованные hashes и HF model configurations проверены по первичным источникам, **локальная identity/runtime compatibility остаётся unknown**.

Результат: design contracts проверены на представленных примерах; проект имеет конкретные этапы/входы/выходы и P0 gates. Это design readiness для ограниченного shadow/replay slice, а не production/hardware readiness. Полный журнал решений и оставшиеся ворота: [review-and-decisions.md](review-and-decisions.md).
