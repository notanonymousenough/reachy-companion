# S7 local pivot — bounded operational receipt and PC facts

17 октября 2026, final operational **14:51:25 MSK**, PC metadata14:50:58–14:51:25. **Hardware явно освобождён TechLead `01a148d9-f558-7151-93c5-016d77b24489`; ожидается один конкретный local PC план.** Реализация local route, package setup, model inference/download и trial не начинались.

## Operational outcome

Один read-only интервал14:50:43–14:51:25: same Agent boot `a309d491-d0f5-43ac-a250-61c55101a7a3`, mic287/listening/captureON, PCM source5 **338,558,976→339,910,656B (+1,351,680)**, gaps0/overflow0/retiredfalse. Motor policy137 ON, quiet/privacyfalse, ownersnull, volume100. Первый snapshot поймал existing ordinary processing/workerthinking/actionrunning/known stock ownership; новых stimulus/model requests оператор не подавал. Финал phase listening/workeridle/Hubfree/actionfalse/stockknownunowned, last_error/expression_error отсутствуют, turns162. Это не новая controlled voice acceptance; historical422/R23failure не закрыты.

Существующий pinned snapshot helper прочитал **два разных camera frames (481162/480456B)**, pixels только RAM/readerclosed/audioinitfalse/semanticinferencefalse/newproducerfalse. Passive encoder telemetry **150samples/0errors**, running moves0; наблюдаемая голова/антенны практически неподвижны. Camera availability подтверждена; новая демонстрация движения и постоянное semantic vision не заявляются. Process check: Agent247720/factory150625 active/NRestarts0; один arecord250221→247720/noAPLAY. Controls/restarts0.

## PC capacity and runtime, actual metadata only

| Факт | Измерено |
| --- | --- |
| GPU | NVIDIA GeForce RTX5070, driver591.86 |
| VRAM MiB из nvidia-smi | **total12227 / used9977 / free1967**; текущий loaded environment, не unloaded budget |
| Process VRAM | WDDM query возвращает N/A по процессам; распределение по9B/ASR/desktop этим receipt не доказано |
| Windows | Windows11Pro10.0.26200/64bit, RAM32614388KiB total/17112108KiB free |
| Native Python | **3.12.9**, `C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe`; `py` и `uv` доступны |
| Existing shadow venv | Python3.12.9, `C:\Users\User\reachy-shadow\.venv\Scripts\python.exe`; targeted speech/s2s package metadata пусты |
| WSL | DefaultUbuntu **Running/WSL2**, docker-desktop **Running/WSL2**; Ubuntu `/usr/bin/python3` **3.14.4**, targeted speech/s2s metadata пусты |
| Docker | Desktop4.88.0(237115), Engine29.7.2/linuxamd64, kernel6.18.33.2-microsoft-standard-WSL2;16CPU/16292409344B RAM;1runningcontainer |
| Existing worker | same c46d9afc…/image0e42c38…/read-onlyrootfs, StartedAt08:53:44.615893658Z/RestartCount0 |
| Worker Python | `/usr/local/bin/python` **3.13.16** |

Native Windows metadata: **faster-whisper1.2.1, ctranslate2 4.8.1, torch2.13.0, transformers5.5.4, accelerate1.13.0, onnxruntime1.27.0, huggingface_hub1.27.0, reachy_mini1.9.0**, soundfile0.13.1, tokenizers0.22.2, sentencepiece0.2.1, safetensors0.8.0. Existing worker: **faster-whisper1.2.1, Piper1.8.0, vosk0.3.45, onnxruntime1.30.0, onnx1.23.2, huggingface_hub1.33.0, reachy-companion0.2.0**, tokenizers0.23.2. In these enumerated environments no package name matching s2s/fastrtc/gradio was found; other private/unlisted environments were not searched. Metadata only: no heavy model imports, GPU allocation or audio calls.

Existing reusable worker `/config/models`: Whisper-small `model.bin` **483546902B** plus tokenizer/config/vocab; Piper `ru_RU-ruslan-medium.onnx` **63201294B** plus4882B model JSON; Vosk-small-ru0.22 and YAMNet16093355B present. Windows source models mirror the same named files. No model contents/config contents exported. Windows HF cache has named directories for faster-whisper-large-v3, F5-TTS, OmniVoice, vocos and other historical models; **directory presence does not prove complete or runnable weights**. Ubuntu HF cache has Qwen3-0.6B-GGUF directory. Worker standard HF cache roots inspected are absent. Current LMStudio9B stays loaded; no unload/load or endpoint inference was issued.

Measured free1967MiB gives no basis to stack an additional roughly8GB speech runtime on top of the current environment. Preferred source-owner direction remains officialApp+s2s with a protocol adapter reusing existing9B/Whisper/Piper; **no implementation, dependency-resolution or API compatibility PASS is claimed**. Native SDK1.9.0 is a concrete compatibility fact for that plan; factorySDK1.11.0 was not replaced.

## Hosted retirement and preserved stage

R24 hosted was canceled before effects: **App install/launch0, HF allocation0, HF audio/JPEG egress0, remote downloads/venv installs0, oldAgentstops0**. Fresh process/stage check again shows proposed `/home/pollen/reachy-companion/.r24-20261017-144238` absent and App processes empty. Cached R21 public source/frozen recipe, R24 local receipts, existing private rollback/staging remain preserved. Nothing required restore; useful local ON remains running. No alternate local route was implemented.

One metadata-helper dispatch initially returned no JSON (no inference or runtime change); corrected only the read-only PowerShell invocation, then successful metadata receipt. The operational observation was not repeated.

[Summary](../../S7-evidence/local-pivot/summary.json), [before](../../S7-evidence/local-pivot/before.json), [after](../../S7-evidence/local-pivot/after.json), [PC inventory](../../S7-evidence/local-pivot/pc-inventory.json), [native/WSL Python packages](../../S7-evidence/local-pivot/extra-runtimes.json), [camera](../../S7-evidence/local-pivot/camera.json), [encoder receipts](../../S7-evidence/local-pivot/poses.json), [process/stage](../../S7-evidence/local-pivot/processes.json). No private speech/pixels/config/secrets exported. Epochs are receipt values, never reusable control payloads.

## Subsequent scope authorization

После завершения maintenance receipt TechLead передал новый ROOT-approved local officialApp+official realtime scope: actual start14:50:00MSK, hard deadline15:50:00MSK, checkpoint15:05 frozen path/contracts/deps/VRAM и15:20 actual local server/protocol response либо STOP+one blocker. **S7 вновь принимает sole hardware ownership для этого отдельного scope**, ожидая frozen source package/Tech review/concrete dispatch; прежнее release выше относится к завершённому maintenance receipt. До frozen dispatch ничего не устанавливается/не запускается; current local ON сохранён. Runtime cloud/private egress0, no duplicate weights/model/template/endpoint loops, минимум5мин rollback reserve; отсутствие working result к30мин не даёт автоматического продолжения.
