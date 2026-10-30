# R11 — retirement меняет существующую microphone authority

17 октября 2026, Europe/Moscow. **Source-ready, OFFLINE PASS; не установлен, live acceptance отсутствует.** Отдельный Agent-only candidate поверх установленного по [R9](R9-manual-retire-live.md) exact R8 закрывает составной receipt ABA из [R10](R10-stock-rearm.md): первый retirement активного pump при pause/legacy manual повышает существующий microphone epoch и сохраняет microphone state под mic→policy locks. Финальный operator после resume отличается от binding до retire. R5 physical closure остаётся обязательным; новое rearm — отдельная задача после применения и проверки candidate.

SSH/HTTP/deploy/model/hardware не использовались; новые чаты/подагенты не создавались. Frozen R8/A0 builders/patches и HEAD Agent не переписывались. Native runtime/session, stock, pump, camera, worker и config не изменялись этой задачей. Исходные R7/R10 reports и negative tests/receipts сохранены.

## Exact payload и сборка

| Артефакт | SHA256 |
| --- | --- |
| Exact R8 Agent base | `001be4ec456141b41d0146b49d06e737ced5383dcba2201c288fa3ed35b667f6` |
| R11 Agent output | `ec3a1ad998ec9e9d05d835deda19934f6930b52aba03f374e790bae4128531b9` |
| [Portable runtime patch](../../deploy/patches/reachy-agent-001be4-r11-retirement-authority.patch) | `f6068ac993207055ed2a1a8cac96e8cd4f800de73b645f5ebd5f18789aeea17d` |
| [Новый builder](../../deploy/autonomous/prepare_retirement_authority.py) | `af4f6770cf75efc5df4f3d47c1bcd96435394913bfd86ef245d58c98a0e8d522` |
| [Новые exact-method tests](../../tests/test_retirement_authority.py) | `166db5128f2bbd98b9d8460af646bb962a1a4304a88d96bf400dbf26238e9753` |
| A1 pump, unchanged | `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6` |
| Installed microphone dependency, exact historical class исполняется в tests | `d35ef6d3e0cc289e8043a0da68480ecd110ef3fff98afb81da0afad25e416129` |
| MotionPolicy dependency, unchanged | `d224385e999a0c6056db42e1fc3a3c90afaa2009336eaf1ef364037dc98a8466` |

```sh
python3 -B deploy/autonomous/prepare_retirement_authority.py /private/tmp/reachy-R11-review-bundle
```

Новый каталог обязателен. Builder восстанавливает exact R8 через неизменную historical цепочку, проверяет base/pump/patch/output hashes и compile. Выдаёт только runtime payload `agent.py`, `agent-R8-preimage.py` и manifest; A0 `required_unchanged` pins сохраняются. HEAD Agent `0cc3e643…` и HEAD microphone `ecb3f480…` не подставляются вместо установленного source.

AST вне `set_microphone`, `set_listening`, `manual` и нового private helper `_set_listening` идентичен exact R8. `voice`, `run`, status/operator, `_capture_get`, `_capture_retire` и source generation неизменны. Нет нового persisted field, grant, wire shape, recorder или dependency. HTTP setter по-прежнему возвращает ровно `ok/listening`; его private helper дополнительно возвращает локальный receipt текущей mutation только legacy manual.

## Semantics и callers

`set_listening(False, …)` сначала выполняет прежний binding CAS под mic→policy locks. Затем clear listening и retired Event остаются в той же critical section; при первом retire ещё не retired pump выполняются `microphone_epoch += 1` и существующий `MicrophoneState.save(current_enabled)`. Owner не переназначается, enabled при успешном save сохраняется. Actual M повышает persisted epoch, выполняет file fsync→replace→directory fsync до enabled publish. Operator reader не может попасть между retire и version change. Child close/reap выполняется в `finally` после освобождения обоих locks, включая persistence failure.

| Caller / граница | Поведение R11 |
| --- | --- |
| Active bound pause | Проверяется прежний binding, retirement сохраняет новую authority; для последующего bound resume/say нужен новый `/operator` binding. Старый CAS отвергается. |
| Already retired pause | Повторного increment/save нет. |
| Bound manual, уже paused/capture=false/listening=false | Прежние два admission checks и guarded setter сохранены; increment/save нет даже у inactive source object с ещё не выставленным retired Event. Иначе setter сам сделал бы binding устаревшим перед voice. Это единственное явное исключение, защищённое прежним `require_paused` guard под locks. |
| `set_microphone` / spoken STOP/OFF | Existing mutator уже повышает authority и retires pump; следующий pause не повышает её второй раз. Mic owner CAS и durable OFF сохранены. |
| Legacy `/say` и `/ask` | `_set_listening` возвращает was_listening и boot/mic epoch/mic owner/policy epoch/policy owner, снятые в той же mutation после save, **до close/reap**. Success/error/failed-acquire restoration проверяет этот receipt под paired locks, enabled/error/stop/quiet/privacy. OFF→ON и owner/privacy round-trip больше не могут восстановить listening из старого manual. |
| Legacy manual output | Передаёт в неизменный `voice` captured mic/policy epochs через уже существующие параметры. Поздний result после withdrawal отменяется штатным `cancelled()`, включая revoke во время close или ожидания audio lock; capture/output не запускаются со свежей authority от чужого перехода. |
| Source generation / continuous pump | Retired Event никогда не очищается. Старый child reap до replacement; `_capture_get` по-прежнему создаёт generation+1, которая не выдаётся за прежний source. Обычная continuous capture через processing/speaking не затрагивается. |

Локальный manual receipt не является новой authority: он сравнивает существующие server CAS fields, чья microphone version сохраняется через exact M. Policy и owner изменения по [R4](R4-authority-epoch-contract.md) также увеличивают существующие epochs. Для нормального legacy manual `motor_enabled=False` допустим, как в R9; новый bound motor guard к legacy не добавлен.

Обе microphone increment sites ограничены максимумом `2**63-1`. Переход max−1→max сохраняется; дальнейшая попытка retirement/микрофонного switch отключает microphone, оставляет listening=false, retires/reaps child, stops speaker и сообщает exhaustion. Epoch не wrap и не rollback. Уже retired no-op при max разрешён. Существующий `set_microphone` раньше мог публиковать RAM epoch `2**63`; эта узкая правка устраняет это и в OFF caller.

File/directory fsync failure оставляет повышенные RAM epochs, disabled/error M, очищенные pending/resume, stopped output и retired/reaped source; manual не входит в voice. До replace старый durable ON может остаться на диске, после directory-fsync failure durability UNKNOWN. Успешная durable OFF при ошибке не заявляется. Restore старого persisted ON и epoch rollback запрещены. Нового power-loss/external-writer/file-rollback proof нет.

Legacy explicit `/resume {}` сохраняет прежний API. Он не снимает retired Event, не отменяет epoch mismatch и не восстанавливает terminal native binding. Изменение semantics его policy admission не входит в R11.

## Exact-method evidence

**172/172 offline tests PASS, failures/errors/skips=0, 11,171s** в текущем workspace. Дополнительно **28/28 PASS** с hash-checked frozen R10 `NativeAgent c8fb477f…`, загруженным под исходным module name в отдельном interpreter без изменения native файлов. Это R11 27 tests плюс неизменный R10 negative test. Tests исполняют полные reconstructed Agent methods и actual A1 pump, а не AST-extracted application methods. Ранее существующие HTTP handler tests остаются в suite. Только fixture subprocess PCM writer, temp durable files, mocked HTTP streams/playback dependencies; ни ALSA, ни model call.

| Проверка | Результат |
| --- | --- |
| R10 operator→status→pause/say/ask→resume→final Hub operator | Все 3 scheduling cases отвергнуты `Native authority/listening withdrawn; no reconnect`, mic1→2; status PCM generation1 до retire, final PCM generation1 retired=true, recoveries0, stock POST0. Read BEGIN после gap, deadlines не расширены. |
| Старый R10 negative на frozen R8 | Все 3 cases по-прежнему recovery1 со старым binding; original receipts скопированы, negative replay сохранён отдельно. |
| R7 clear→retire boundary | Resume/operator пытаются взять mic-lock и blocked до release; после retire+save имеют mic2, прежний binding terminal. Reader может выйти ещё до следующего os.read; нулевые аппаратные late bytes не заявляются. |
| CAS/no-op/owner | Сохранение enabled/owner None и owned; свежий bound manual/resume проходят, старые CAS не мутируют; already-paused bound inactive source и retired source без лишнего increment. OFF затем pause — один переход. |
| Durability/errors/exhaustion | Actual exact M: два fsync под locks; отдельно file и directory failure; cleanup/no temp; max−1→max и повторный exhausted attempt без wrap в pause и microphone caller. |
| Legacy normal/error/busy | `/say|/ask` × listening on/off × success/error/busy сохраняют routes/session/filter/restoration; actual reply/done stream также успешно завершается. Generated acoustic playback в этом positive fixture отсутствует. |
| Late voice / busy restore | Actual streaming voice после STOP, STOP→ON, mic/policy owner round-trip, privacy→clear, quiet, shutdown возвращает cancelled; Popen playback запрещён и не вызывается. Revoke во время close не rebases receipt. Busy restore после authority round-trip остаётся false. |
| Child ownership | Unknown reap оставляет owned source и запрещает replacement/voice; real-pipe fixture не создаёт следующий child до завершения предыдущего. Reap под locks запрещён assertions. |

Current native observer/session в workspace уже имели отдельные изменения относительно R10 pins до этой проверки. R11 их не редактировал: before/after hashes совпали; полный current suite проверен как compatibility evidence. Frozen R10 native использован дополнительно именно для exact counterexample proof. Frozen session сохранён как reference, в дополнительном 28-test run session не исполняется. Ни current native source, ни source fixtures не являются live evidence.

Воспроизведение current suite:

```sh
PYTHONPATH=src:tests /private/tmp/reachy-head-validate-20261015/bin/python -B -m unittest \
  test_retirement_authority test_native_stock_rearm_gap test_manual_retire_fix \
  test_continuous_capture test_native_agent_session test_capture_pump \
  test_bound_listening test_agent_stream_timing test_microphone test_motion_policy -v
```

[Evidence](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-4bbb-7133-9d57-157adcec74c4/R11-evidence/): [full log](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-4bbb-7133-9d57-157adcec74c4/R11-evidence/offline-tests.txt), [source hashes](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-4bbb-7133-9d57-157adcec74c4/R11-evidence/source-manifest.json), [exact R10 log](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-4bbb-7133-9d57-157adcec74c4/R11-evidence/exact-R10-tests.txt), [candidate receipts](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-4bbb-7133-9d57-157adcec74c4/R11-evidence/exact-R10-candidate-receipts.json), [unchanged negative replay](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-4bbb-7133-9d57-157adcec74c4/R11-evidence/exact-R10-replayed-negative-receipts.json), [runner](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-4bbb-7133-9d57-157adcec74c4/R11-evidence/run_offline.py), [frozen reader runner](/Users/notanonenough/.codex/visualizations/2026/10/17/01a14811-4bbb-7133-9d57-157adcec74c4/R11-evidence/run_exact_r10.py). Manifest/bundle содержат exact R8 rollback preimage. Standard patch dry-run/apply/reverse без fuzz проверены на отдельных копиях.

## Install / protected rollback prerequisite — не выполнялось

До любой установки нужна отдельная передача hardware-владения по R9, fresh effective-import/dependency preflight всех A0 pins, protected root0700 rollback directory с exact текущим R8 Agent root0600 и original uid/gid/mode в manifest; private config preimage отдельно root0600, не в review artifacts. **Persisted microphone ON state не копировать/не восстанавливать; epochs не откатывать.** Старый R9 backup содержит A1 preimage, поэтому он не заменяет новый независимый R8 rollback preimage.

Сначала guarded OFF с актуальными boot/epoch/owner CAS; подтвердить paused/no capture/no APLAY, worker idle и reap Agent child; controlled stop только Agent service. Pump/worker/factory/Hub/camera/config сохраняются. Доставить hash-checked patch и review manifest заранее. При failed reap, unknown state, dependency mismatch — stop, без второго reader и retry. R5 physical closure оставить.

Конечная **будущая** команда на Reachy после prerequisites; не исполнялась в R11. `rollback` вместо `install` применяет exact reverse patch R11→R8, сохраняя текущие persisted epochs и OFF. Перед rollback нужны те же fresh OFF/reap/controlled-stop checks и protected preimage/hash verification.

```sh
sh -s install <<'SH'
set -eu
mode=$1
base=001be4ec456141b41d0146b49d06e737ced5383dcba2201c288fa3ed35b667f6
output=ec3a1ad998ec9e9d05d835deda19934f6930b52aba03f374e790bae4128531b9
review_patch=/var/tmp/reachy-R11-reviewed/reachy-agent-001be4-r11-retirement-authority.patch
case "$mode" in
  install) before=$base; after=$output ;;
  rollback) before=$output; after=$base ;;
  *) exit 2 ;;
esac
test "$(systemctl is-active reachy-voice-agent.service || true)" = inactive
cd /home/pollen/reachy-companion/src/reachy_companion
printf '%s  %s\n' "$before" agent.py \
  f6068ac993207055ed2a1a8cac96e8cd4f800de73b645f5ebd5f18789aeea17d "$review_patch" \
  5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6 capture_pump.py \
  d35ef6d3e0cc289e8043a0da68480ecd110ef3fff98afb81da0afad25e416129 microphone.py \
  d224385e999a0c6056db42e1fc3a3c90afaa2009336eaf1ef364037dc98a8466 motion_policy.py | sha256sum -c -
set -- --batch --fuzz=0 -p1 -i "$review_patch"
if test "$mode" = rollback; then set -- -R "$@"; fi
patch "$@" --dry-run
patch "$@"
printf '%s  %s\n' "$after" agent.py | sha256sum -c -
python3 -c 'from pathlib import Path; p=Path("agent.py"); compile(p.read_bytes(),str(p),"exec")'
sudo systemctl start reachy-voice-agent.service
SH
```

После start проверить новый boot и OFF/no capture/no APLAY, source hashes/metadata и неизменные dependencies/config. Fresh guarded ON и finite normal/manual acceptance выполняет следующий hardware owner. Ровно этот candidate ещё не установлен; установленные R8/R9 продолжают иметь R10 gap. Universal proof аппаратуры и разрешение stock rearm отсутствуют.
