# P0 — existing Qwen3.5-0.8B CPU readiness

17 октября 2026, Europe/Moscow. **Existing fast backend поднят и оставлен готовым; 3/3 native contract-пробы прошли HTTP/JSON/schema/parser. Default N1 deadline 2 s не принят.** Последние snapshots: PC **04:46:58,607 MSK**, robot/Hub/worker **04:47:01,360 MSK**. **P0 завершён, аппаратное и инженерное владение явно освобождено. Normal listening ON.**

Входы: `PROJECT.md`, `runtime-baseline.md`, `pc-live.md`, готовый во время P0 `N1-native-adapter.md`. Read-only inventory нашёл остановленный fast, свободные 18097/8097, прежний CPU binary и exact 0.8B GGUF. Существующая установка сохранна; download/install/model research не потребовались. Использован прежний command shape `pc_probe.py`/`live_smoke.py`, выбранный CPU8/cache0/context4096/parallel1 profile. Никакой новый worker, recorder, gateway, camera producer или autonomous loop не запускался.

## Рабочий endpoint и pins

Все PC paths ниже относятся к **User@192.168.2.134**; HTTP — к loopback этого PC.

| Поле | Фактическое значение / evidence |
| --- | --- |
| Fast endpoint | `http://127.0.0.1:18097`; GET `/health` 200 `{"status":"ok"}`, POST `/tokenize`, POST `/completion` работают |
| Model alias | `reachy-shadow-fast-cpu`; фактический artifact **Qwen3.5-0.8B Q8_0**, не исторический Qwen3-0.6B |
| Weights | `C:\Users\User\reachy-shadow\Qwen3.5-0.8B-Q8_0.gguf`, **833592096 bytes** |
| Weights SHA256 | `37ae482d336108d23516fa35e8e0c4126688d81018b87178a18d752a1357814f`; свежий PC hash совпал с accepted artifact |
| Tokenizer | Native `/tokenize`, embedded в том же GGUF; provenance digest всего GGUF **тот же SHA256**, отдельный extracted tokenizer digest не заявляется. Два actual counts на каждую пробу |
| CPU backend | `C:\Users\User\.lmstudio\extensions\backends\llama.cpp-win-x86_64-avx2-2.20.1\llama-server.exe`; `--version`: **1 (94a220c), MSVC19.44.35227.0 x64** |
| Server SHA256 | `0bbac3a55d4a005772ce8a16c4c222163f683119bbbca13b42f6af788faaa4e6`; совпал с прежним pin и actual mapped exe |
| Actual implementation | Mapped `llama-server-impl.dll` SHA `5306c3bf6dd6d523afd33ed5496aac6f1ec48d89fdecf06904d9536fe592a377`; `llama.dll` `54a154c0c9744d63cb73377dbd61a499315e5171d1df9c3a5bfa7f011e513f06`; `ggml-cpu.dll` `7318ff9eea8afa23cb35030950b0adac9cf3213fc3fc33cd8307fe42c3c09712`. Полный observed module map+hashes в `final-pc.json` |
| Placement | **cpu_pc**, GPU layers0, `--no-op-offload`; actual startup log: compiled without GPU support, projected897MiB host memory. CUDA vendor PATH/offload не добавлялись |
| Resources | `--threads 8 --threads-batch 8 --threads-http 2 --ctx-size 4096 --parallel 1 --cache-ram 0`; model threads, не affinity. Actual `/props` n_ctx4096/total_slots1 и log slot0/context4096/cache disabled |
| Process | Один `llama-server.exe`, **PID7736**, start **01:44:58.7587746 UTC**, executable/command/start frozen в `fast-identity.json`; parent cmd21892. Listener `127.0.0.1:18097` принадлежит7736 |
| Native API configuration | `completion_backend=llama_native`, `completion_path=/completion`, `tokenize_path=/tokenize`, `tokenize_content_key=content`, `projection=full`, object format |
| Request limits | temperature0, output/n_predict192, input_cap2744, template_cap256, reserve256, context4096; actual token admission проверен до каждого inference |

Рабочий fast endpoint не требует HTTP bearer (`api_key_env=""`) и привязан только к PC loopback. Доступ извне — через существующий SSH account/проверенные host keys и отдельный operator-owned forward при следующем deployment; такого forward P0 не оставляет. Существующие gateway credentials находятся в PC `C:\Users\User\reachy-shadow\token.local`, считываются в env/file только владельцем следующей finite session; значения не выводились. **Authenticated autonomous gateway8097 сейчас не запущен**, его `/health.conversation_owner=native_agent` ещё должен проверить N2 после deployment N1. Raw18097 не подменяет этот gateway.

Effective message rendering для `/completion` берётся из существующего PC `profile.local.json` и совпадает с N1 example:

```text
message_template = "<|im_start|>{role}\n{content}<|im_end|>\n"
assistant_prefix = "<|im_start|>assistant\n<think>\n\n</think>\n\n"
stop = ["<|im_end|>", "<|im_start|>"]
```

SHA256 UTF-8 `json.dumps([message_template,assistant_prefix,stop],ensure_ascii=False)` = **`da8586387961d27cf1f580f825cde64cae3eeacf407c27362d19a5390a60cc23`**. Это effective handwritten template native completion, GGUF/server chat template не используется вместо него. PC private `profile.local.json`/`context-profile.local.json` прочитаны только в части model metadata; не изменялись. Исторические `verified=true` сами по себе доказательством не считались: файлы хешированы заново, runtime process/log/props и реальные запросы проверены отдельно.

## Ровно три реальные пробы

**04:46:07,193–04:46:14,527 MSK**, native N1 object decision contract. Payloads построены текущими `NativeState.snapshot` и `ModelBackend.generate_loaded` на **явно synthetic snapshots**: listening idle, processing/voice busy, camera.pixel_quality unknown с age upper=null. Во всех normal Agent — единственный conversational owner, candidates/ready/dialogue пусты, motor permission=false; никаких simulated utterance/main/commit и физических effect. Snapshot metadata fixtures не объявляются live observations во время inference.

| Case | HTTP | Input / text / template tokens | Output tokens | Completion s | Два tokenize s | Сумма HTTP s | Choice / finish / validation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| native_idle | 200 | 450 /433 /17 | 36 | 1,984020 | 0,003478 | **1,987498** | wait /eos /PASS |
| native_voice_busy | 200 | 482 /465 /17 | 36 | 2,064229 | 0,039380 | **2,103608** | wait /eos /PASS |
| native_camera_unknown | 200 | 487 /470 /17 | 36 | 2,098124 | 0,026614 | **2,124738** | wait /eos /PASS |

Latency — PC `perf_counter`, полностью прочитанный native HTTP response; сумма включает оба exact-tokenize HTTP, но не SSH/session/reducer overhead. Запросы последовательные, parallel1; три actual completion, не бесконечный benchmark. Full snapshots не сокращались до task_only. Никаких дополнительных generation на fast/main не было.

Сохранены HTTP status/headers/raw UTF-8/full JSON, actual tokenizer IDs, stop_type/tokens_predicted/timings. Все ответы содержат один JSON `{"a":"wait","why":...}`; why≤96, eos, никаких start/commit/say/motion. Strict duplicate/nonfinite JSON decoder, admitted generation schema и `FastChoice` validator прошли. Сохранённые реальные responses повторно пропущены через **тот же current `ModelBackend.generate_loaded` parser**, с exact payload/count input equality, а не через отдельно придуманную parser-логику.

Reasoning: prefix заранее закрывает `<think>`; actual completion content не содержал think tags, отдельных reasoning fields в трёх responses нет. Runtime slot params после проб: reasoning_format=deepseek/reasoning_in_content=false; это metadata, не доказательство скрытого reasoning. Применён существующий parser `re.sub(r'<think>.*?</think>', '', ..., flags=re.S)` → strict decode; оборванная генерация не принималась. `why` — обычное поле decision, не отдельный chain-of-thought канал.

**Backend readiness PASS; 2 s deadline/cadence acceptance отсутствует.** Две генерации и две суммы HTTP уже >2 s, первая сумма почти без запаса. Example N1 `fast_deadline_s=2,period_s=2` нельзя объявить рабочим по этим данным. Не измерены runtime ticks, ≥10 decisions, busy gaps, sustained/P95 или mixed main inference; моторы/камера/Алиса не тестировались. Минимальный следующий шаг — N2 deployment/один finite native loop с этим уже готовым backend и явно reviewed временными period/deadline с запасом (например3 s как **непроверенная настройка**, не обещание cadence), без смены модели или нового ресерча. Сохранение именно2 s требует отдельной адресной latency-работы.

## Сохранность baseline и финал

Перед start **04:44:23–04:44:27 MSK**: Agent normal listening/capture ON, boot `f2a66c3b-dc89-4a2f-961d-ab738696b950`, mic221/generation3, PID205817; factory150625; оба active/running/NRestarts0. Hub free, worker idle, motor=false, owners absent. Read-only inventory не нашёл fast process или listener18097/8097.

Основной LM Studio PID24060/endpoint1234 сохранился. SDK1.5.0 использовал только list_loaded/get_info/get_load_config, без load/unload/model()/prediction/tokenize. Before/after трёх проб совпали полностью: **instance `Xnc6eP1JA8Q5KjfFgFU9CVal`**, model_key/id `qwen3.5-9b-uncensored-hauhaucs-aggressive`, context32768, GPU ratio1.0/flashAttention=true и весь load config. Это свежая identity, исторический instance из pc-live не переносился. GPU before/after: UUID `GPU-a8c946c0-898f-1363-1d79-326250aceec0`, total12227/used9975/free1969MiB; два samples, не headroom monitor/soak.

Worker container `c46d9afc583eabd612cebae22ea6609b188769f54eac842010d65ec4ce443fc9`, image `sha256:0e42c38ae2b0b91873ba3cda454edf2cc3646ed4016a038a3dd12f3214120e3d`, StartedAt `2026-10-17T00:14:05.591565216Z`, restart_count0, readonly rootfs, running. PC config SHA `ae0535ca2b23bc7b0544f45c1d7979f6000df082b9c8cc44de17bffa02fe6b4e` совпал с baseline; Whisper/Piper/config не менялись, новый STT/TTS test не выполнялся.

Финал **04:47:01 MSK**: тот же Agent205817/factory150625/NRestarts0/boot/mic221/generation3, microphone_enabled/listening/capture_active=true, phase=listening, last_error/state_error=null, turns3. Один прежний arecord208199→Agent205817; read_bytes **38496256→43431936**, gaps/overflow0, retired=false. Это два snapshots, не доказательство каждого промежуточного PCM sample. Volume100, policy116 motor=false/quiet=false/privacy=false, owners=null. Hub free/action_running=false/stock unknown=false; worker idle/ok=true. Один initial final-check GET завершился HTTP503; повторный конечный read-only snapshot прошёл, restart/control не применялись. Transient503 сохраняется как ограничение status transport для следующего preflight.

Последний fast `/health` ok, `/slots` один/is_processing=false; fast оставлен запущенным для следующего владельца. Штатные службы/listening сохранены, hardware control POST, моторных команд, Алиса диалогов, новых reader/worker, рестартов Docker/factory/Agent, правок autonomous/audio/camera/voice source или большого private runtime config не было. Чаты/подагенты не создавались. **P0 больше не удерживает аппаратную сессию; фоновых P0 probes/SSH/observers нет.**

## Launch, rollback и receipts

PC отдельный directory **`C:\Users\User\reachy-shadow\P0-fast-readiness\`**: `start-fast.ps1`, `launch-receipt.json`, `fast-identity.json`, `stop-fast.ps1`, `server.log`, `probe-inputs.json`, `probe-results.json`, `final-pc.json`. Единственная подготовленная launch config не изменяет production files. Start проверяет отсутствие любого llama-server/занятости18097, exact server/weight hashes и существующего log; затем Win32_Process.Create запускает существующий binary вне SSH job, CPU8/context4096/parallel1/cache0. Create return0/parent21892, фактический child7736/endpoint проверены после завершения SSH.

**Не исполнять start повторно поверх работающего7736.** Startup persistence/reboot recovery/task/service не добавлялись. При необходимости остановки следующий sole operator сначала исключает новых fast clients, затем запускает PC `powershell -NoProfile -File C:\Users\User\reachy-shadow\P0-fast-readiness\stop-fast.ps1`. Скрипт сравнивает frozen PID/exe/command/creation time, требует actual idle slot, останавливает только этот PID и проверяет отсутствие процесса/listener. Busy/unknown/identity mismatch — отказ, без kill чужого replacement. Rollback подготовлен и проверен чтением; **не выполнялся**, чтобы оставить fast ready. Для последующего start после доказанного stop сначала вручную сохранить прежние logs/receipts и обновить frozen identity нового процесса; blind retry запрещён самим start script. Main9B/worker/Agent rollback не затрагиваются.

Локальный evidence directory:
`/Users/notanonenough/.codex/visualizations/2026/10/17/01a14786-f0b0-7f52-bdb9-f8116fa83137/P0-evidence/`.

`probe-inputs.json` — synthetic requests/profile; `probe-results.json` — raw actual PC receipts; `parsed-results.json` — current parser/schema/token admission results и main identity; `final-pc.json` — observed module map+hashes/container/listeners; `baseline-before.json`/`baseline-after.json` — sanitized robot/Hub/worker receipts; `sha256.json` — file manifest. Ключевые SHA256:

- `probe-results.json`: `46029a4b8a3fea1432db79f7691405c2580fc3218e4a404320ca30472756f51e`.
- `parsed-results.json`: `876bb206090d6824c361f9c8f04eca3d433129b67f073d8a9e0f66056ae10728`.
- `final-pc.json`: `67aab4a72efb0b92b9ee8fa2fcdde9253c7effffc97d0f61308342979cfc88b0`.
- `baseline-after.json`: `28f90d5673190397234fb598a2a9a6f5a931779c31429e55a966b5ab6452ccd9`.

Это evidence ограниченной P0 readiness, не frozen независимый `live_smoke.py` audit/lease, не attestation большого runtime и не integrated autonomy acceptance. P0 не создавал audit namespace и не переносил исторические flags/TTL для запуска старого harness. Следующий владелец обязан сделать свежий preflight; ownership передано свободным явно, epoch221 из этого отчёта не готовый control payload.
