# R8 — exact A1 legacy manual retire fix

17 октября 2026, Europe/Moscow. **Source-ready, OFFLINE PASS; установки и live PASS нет.** Закрыто конкретное окно R7 для legacy `/say` и `/ask`: clear listening и retire прежнего pump теперь выполняются через существующий `set_listening(False, {})` под microphone→policy locks. Reap остаётся вне locks. R5 permanent physical closure сохранён; native physical rearm не включён.

S3 остаётся единственным аппаратным владельцем и работает только с PC worker. R8 не использовал SSH/HTTP/deploy/model/devices, не создавал чаты/подагентов. HEAD Agent, frozen A0 builder/patches/bundle, pump, worker, native scheduler/session, camera и config не менялись. Входы: [R7](R7-stock-rearm.md), [A0](A0-continuous-capture.md), [baseline](runtime-baseline.md).

## Exact payload

| Артефакт | SHA256 |
| --- | --- |
| Agent A1 preimage | `de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b` |
| Agent R8 output | `001be4ec456141b41d0146b49d06e737ced5383dcba2201c288fa3ed35b667f6` |
| [Переносимый Agent patch](../../deploy/patches/reachy-agent-de362b-r8-manual-retire.patch) | `f42426d28c94b592ab6213b85d89450b03c810215b61c290e964d823932c8c0e` |
| A1 pump, неизменный | `5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6` |

[Builder](../../deploy/autonomous/prepare_manual_retire.py) восстанавливает exact A1 через неизменную историческую A0 цепочку, проверяет base/pump/patch/output hashes и compile, выдаёт **только Agent payload**, exact `agent-A1-preimage.py` для rollback и manifest. HEAD Agent `0cc3e643…` не является входом или результатом. Сборка в новый каталог:

```sh
python3 deploy/autonomous/prepare_manual_retire.py /private/tmp/reachy-R8-review-bundle
```

Из runtime меняется только `Agent.manual`. AST вне этого метода идентичен A1; `set_listening`, `set_microphone`, `set_motion_policy`, status/operator и весь pump сохранены. Нет новых epochs, protocol/grants, recorder или dependencies; opt-in A1 не переключается.

Есть одна необходимая дополнительная правка внутри того же метода: оба прежних restoration sites вызывают локальный `restore_listening()`. Он сохраняет `was_listening`, обычное восстановление после success/manual exception/failed audio lock и проверку microphone.enabled; проверяет также stop/quiet/privacy под mic→policy locks. Голый старый finally после privacy снова выставлял listening=true при enabled microphone — одной заменой retire-блока требование «privacy не восстанавливается» выполнить нельзя. Это узкое усиление restoration, без смены epochs или поведения bound manual (`was_listening=False`). Вызов `self.set_listening(True,{})` для finally не подходит: legacy resume проверяет только microphone.enabled, поэтому privacy/stop не удерживает. Явный legacy `/resume` API не менялся.

Отключение через существующий setter эквивалентно нужному A1 lifecycle: retired Event снимает authority сразу; pending packet очищается в critical section, accepted/mailbox/assembler очищаются при последующем close вне locks. Старый `_capture_retire` дополнительно чистит `_capture_control`, но exact A1 при continuous opt-in уже не создаёт pump barge consumer (A0 voice path); нового control consumer здесь нет. Failed close по-прежнему выходит до acquire/voice, оставляет listening=false и не скрывает unknown capture ownership.

## Source proof и regression

[R7 regression](../../tests/test_continuous_capture.py) теперь ожидает blocked/retired/source-change на exact R8. [Реализация barriers и проверки](../../tests/test_manual_retire_fix.py) исполняет полные reconstructed методы Agent, без AST extraction/rewrite application methods, и прежний deterministic subprocess PCM writer вместо ALSA.

Сохранена конкурентная фаза R7: `phase=processing`, capture_active=true, same boot/mic1/policy3/owners/expression1/source_generation1; reader остановлен на первом actual policy binding check после capture_active=true, вне pump condition. Manual остановлен сразу после actual Event.clear, **до** retire. Два других thread уже пытаются войти в actual resume и native operator/status read. Gate на входе mic-lock фиксирует попытки, а не предполагает их по sleep.

| Граница | Exact A1 / R7 preimage | Exact R8 candidate |
| --- | --- | --- |
| Manual после clear, до retire | Нет authority locks; resume/read проходят | Mic→policy удерживаются; resume и operator read blocked |
| Clear gate released, manual parked перед close/reap | Same-source receipt может восстановить FRESH | Retired Event уже установлен; resume завершается, но active/listening=true + processing receipt отвергается: `A1 actual PCM counters required` |
| Reader разрешён после завершённого resume, прежний реальный pipe получает PCM | 960B/480frames, retired=false в recovery receipt | Также 960B/480frames, но retired=true, chunks=0, pending=0; recovery=0 |
| Reap и replacement через actual `_capture_get` | Новая generation также terminal | Старый child завершён до нового, generation2; `Native source changed/counter regression`, recovery=0 |

В R8 сильнейший retired check выполняется отдельным actual native read **после завершённого resume**, пока reader ещё parked и capture_active=true, phase не меняется. Поэтому результат не подменён менее конкурентным paused/capture=false состоянием. Даже один уже начатый `permitted()` до retire может пропустить последующий `os.read`; immutable retired fence всё равно запрещает публикацию/receipt. Нет утверждения «ни одного позднего byte до reap».

Для порядков до/после critical section: resume до неё перекрывается последующим clear+retire; resume/status во время неё ждут mic-lock; resume после неё не снимает retired Event. Replacement всегда с новой generation и только после успешного close. Reader может успеть pre-check, но native статус видит retired, а `_publish` повторно проверяет permit. Это proof указанного окна; universal proof всех API/epoch interleavings и физическое rearm здесь не заявляются.

Отрицательное evidence не удалено: original R7 report/receipts остались на месте; [копия negative receipts](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147f5-e8e3-75e1-a852-9d55a9c5de05/R8-evidence/R7-negative-receipts.json), [exact test preimage](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147f5-e8e3-75e1-a852-9d55a9c5de05/R8-evidence/preimages/test_continuous_capture.py) SHA `1a5a92de66699738eecd38d62c274a65386e38543c58765c1997c15efc4f95f8`. Старый test повторно исполнен без изменения: обе ветки снова дали recovery=1, same generation1, bytes0→960; физический fence R5 удержан. [Replay receipts](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147f5-e8e3-75e1-a852-9d55a9c5de05/R8-evidence/R7-replayed-receipts.json).

**130/130 offline tests PASS, failures/errors/skips=0**, плюс отдельный старый negative replay (2 subcases). [Log](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147f5-e8e3-75e1-a852-9d55a9c5de05/R8-evidence/offline-tests.txt), [candidate receipts](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147f5-e8e3-75e1-a852-9d55a9c5de05/R8-evidence/offline-receipts.json), [source manifest](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147f5-e8e3-75e1-a852-9d55a9c5de05/R8-evidence/source-manifest.json). Existing venv, установки dependencies не было.

```sh
PYTHONPATH=src:tests /private/tmp/reachy-head-validate-20261015/bin/python -B -m unittest \
  test_manual_retire_fix test_continuous_capture test_native_agent_session \
  test_capture_pump test_bound_listening test_agent_stream_timing -v
```

Новые candidate проверки: 12 combinations `/say|/ask` × initial listening on/off × success/error/busy; 24 combinations `/say|/ask` × success/error/busy × STOP/privacy/quiet/shutdown; 2 unknown-reap/no-second-child subcases; 13 bound listening/manual guards на R8. Проверяются прежние routes `/say`/`/text`, session, allow_barge_in, filtering audio_base64, released audio lock, restoration под locks, reap вне locks, bound owner/epoch/deadline/phase rechecks. STOP/privacy не восстанавливаются ни из finally, ни из failed-acquire branch. A0/S1 tests сохраняют bounded burst/mailbox/TTL/output-tail, continuous pipe progression, OFF persistence-failure и late-STT cancellation; byte-identical pump и AST equivalence вне manual связывают эти проверки с R8. Native R5 tests сохраняют deadline300ms, single-use/no replay, terminal authority/source fences и permanent physical closure.

Standard patch dry-run/apply/reverse на отдельной exact копии прошли, output/base hashes совпали. [Patch check](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147f5-e8e3-75e1-a852-9d55a9c5de05/R8-evidence/patch-check.json). [Exact bundle](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147f5-e8e3-75e1-a852-9d55a9c5de05/R8-evidence/exact-R8/manifest.json), [reproducible runner](/Users/notanonenough/.codex/visualizations/2026/10/17/01a147f5-e8e3-75e1-a852-9d55a9c5de05/R8-evidence/run_offline.py).

## Следующий конечный install / rollback

**Сейчас не выполнять:** source-ready R8 не передаёт аппаратное владение от S3 и не разрешает ему менять Reachy. После отдельной передачи Reachy-владения: fresh preflight всех effective import/dependency pins из A0, сохранённый protected rollback Agent/config, guarded OFF с актуальными boot/epochs, подтверждённый reap Agent child и controlled stop `reachy-voice-agent.service`. Не восстанавливать persisted ON backup. Pump/config/worker/factory/camera не менять; native R5 fallback оставить. Review patch доставляется заранее как `/var/tmp/reachy-R8-reviewed/reachy-agent-de362b-r8-manual-retire.patch`.

Одна конечная команда **на Reachy**, после этих условий. Для rollback поменять только первый аргумент `install` на `rollback`; проверяются обратные pins и применяется `-R`. В R8 команда не исполнялась:

```sh
sh -s install <<'SH'
set -eu
mode=$1
base=de362b7f8d1011230009cc747989a194ab7853b815f086febf0ad42a5721897b
output=001be4ec456141b41d0146b49d06e737ced5383dcba2201c288fa3ed35b667f6
review_patch=/var/tmp/reachy-R8-reviewed/reachy-agent-de362b-r8-manual-retire.patch
case "$mode" in
  install) before=$base; after=$output ;;
  rollback) before=$output; after=$base ;;
  *) exit 2 ;;
esac
test "$(systemctl is-active reachy-voice-agent.service || true)" = inactive
cd /home/pollen/reachy-companion
printf '%s  %s\n' "$before" src/reachy_companion/agent.py \
  f42426d28c94b592ab6213b85d89450b03c810215b61c290e964d823932c8c0e "$review_patch" \
  5fe20c69d7becc63571e76e0c9ea05094d86f562d4762feec5b5a942ec0ff7c6 src/reachy_companion/capture_pump.py | sha256sum -c -
set -- --batch --fuzz=0 -p1 -i "$review_patch"
if test "$mode" = rollback; then set -- -R "$@"; fi
patch "$@"
printf '%s  %s\n' "$after" src/reachy_companion/agent.py | sha256sum -c -
python3 -c 'from pathlib import Path; p=Path("src/reachy_companion/agent.py"); compile(p.read_bytes(),str(p),"exec")'
sudo systemctl start reachy-voice-agent.service
SH
```

После команды проверить новый boot, OFF/no capture/no APLAY и unchanged sources/config. Возврат normal ON — отдельное явное guarded действие со свежими authority values. При mismatch/failed reap/start — остановка и сохранение UNKNOWN, без retry/второго reader. Эта будущая finite установка не является live acceptance; hardware pause/manual recheck остаётся следующему владельцу.
