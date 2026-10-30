# S7 R25 — first dependency gate STOP, old local ON preserved

17 октября2026, финал **14:58:39 MSK**. **R25 joined local App outcome НЕ достигнут: STOP на первом essential dependency failure, без альтернативного resolver/version/backend trial. Hardware явно освобождён TechLead `01a148d9-f558-7151-93c5-016d77b24489`.** ROOT scope14:50–15:50, использовано≈8мин40с, включая checkpoint/cleanup. Это ранний STOP вместо ожидания15:05/15:20; без автоматического расходования оставшегося времени.

## One exact blocker

Robot pinned official App1.1.1 commit `0a3ef5c07c4c9ba58ceaf788244393033acd88c7`, isolated SDK1.11 candidate, **ровно R21 uv.lock-derived constraints**. Первый `pip install` завершился exit1/`ResolutionImpossible` в **14:57:21**:

- R21 generated constraint требует **starlette==1.7.0**.
- Official **reachy-mini1.11.0 требует starlette<1.0.0**.
- mcp2.2.0 требует starlette>=0.27 наPython<3.14.

Таким образом точный frozen recipe несовместим с собственным SDK1.11 override. Это install dependency conflict до App/runtime, не failure speech/model/protocol. Constraints/source/SDK/daemon/baseenv не изменялись для обхода. Отдельный TechLead/ROOT recipe decision требуется до любой новой install attempt; narrowed version или новый resolver trial самостоятельно не выбирался. [Actual App error](../../S7-evidence/R25/app-status.json).

## Что реально staged и сохранено

Новые exact stages предварительно отсутствовали:

- Robot `/home/pollen/reachy-companion/.r25-local-20261017-1450`: pinned official archive/source, verified pyproject/README hashes, original uv.lock, constraints, isolated --system-site-packages venv, preparation script/state/log. Agent оставалсяON. App pip resolver failed before installation; preparator PID270677 завершён.
- PC `C:/Users/User/reachy-shadow/R25-local-20261017-1450`: official s2s1.0.0 commit `619e3fe4f71d1c6f35c15870d588a3638de34722`, archive SHA `f3263a3f54502cb476cd3218a6043b5b109a063f3f85d2142cc93ae3dec691a1`, pyprojectSHA `87ace2c683f2625f998b2852ae25ccceead5e55ed73fafd5d731d88662e450ff`, nativePython3.12.9 isolated --system-site-packages venv. Torch constrained to inherited2.13.0 to preserve existing package. Public deps downloaded; wheel speech_to_speech1.0.0 built. Installation was still running when Robot blocker observed; **exact owned preparation tree23284 stopped at14:58:20**, all descendants reaped/no remaining stage processes. Venv is partial/unvalidated; no pip-check/import/ready PASS. Preserve state rather than treating stale phase=running file as a live process.

PC public library downloads included **lingua-language-detector170.1MB**, llvmlite41.9MB, gradio31.4MB, transformers12.8MB and smaller packages. No separate ASR/TTS/LLM checkpoint download/load occurred. Native base torch2.13.0/transformers5.5.4/faster-whisper1.2.1/onnxruntime1.27.0 verified unchanged after stop; installer logs explicitly declined uninstalling inherited base distributions.

Only tiny secret-free `R25-source.tar.gz` + manifest transferred to PC, archiveSHA `408322c4f73cb2421c74ffdc89ad45d558f3e2e520112600c989403911bd3622`; every frozen file hash matched, including bridge5754b8c1… and run_s2s97adfa55…. These were **not executed**. Existing cached R21/R24 source/evidence/private rollback stages retained. No secret/config/private speech/pixels transferred. [Transfer proof](../../S7-evidence/R25/transfer.json), [owned installer stop](../../S7-evidence/R25/stop-preparation.json).

Read-only PC contracts: existing authenticated worker `http://127.0.0.1:8082` responds status/idle, token existence/minimum length checked privately; raw selected worker config classifier=`rules`, streaming sample rate16000. Effective profile loader and all maxrequest/intent-admission gates were not fully executed before STOP. Official startup source identifies Silero VAD torch-hub and SmartTurn v3.2 CPU ONNX + NLTK resources; none started/fetched as runtime assets. No remaining startup/import/API compatibility claim.

## Effects and fallback

**App starts0, s2s serve0, bridge starts0, warmups0, SSH tunnels0, new inference0, HF allocations0, runtime audio/JPEG cloud egress0, controls0, service restarts0, old Agent stops0.** Latest PC confirms no new8765/18765 listeners, previous same container c46d/image0e42/StartedAt08:53:44.615893658Z/RestartCount0 running, same advertised9B model ID; no model unload/reload. No physical front-door handoff took place, so rollback controls were unnecessary.

Final **14:58:39**: same boot a309d491, mic287 enabled/listening/captureON/source5/PCM353798144B/gap0/overflow0/retiredfalse, phase listening, turns167, volume100; motorpolicy137ON/quietprivacyfalse/ownersnull. Hub free/actionfalse/stockknownunowned, workeridle, current last_error/expression_error absent. Earlier postfailure14:58:08 PCM352796672→353798144B (+1001472), same source. Existing factory camera and operator capability/+2dB unchanged by this dependency-only attempt; no new camera/encoder check. Historical S6 format422/R23failure remain open; no stablevoice/semanticvision/App acceptance PASS.

[Result](../../S7-evidence/R25/result.json), [fallback receipt](../../S7-evidence/R25/fallback-final.json), [final PC](../../S7-evidence/R25/final-pc.json), [PC contracts](../../S7-evidence/R25/pc-contracts.json), [PC staging log snapshot](../../S7-evidence/R25/s2s-status.json). Source-gate/architecture approval did not prove this dependency closure. Epochs — receipts only, not control payloads.

## Authorized narrow read-only GI follow-up — 15:01:25 MSK

ROOT разрешил одну deterministic correction/resume того же пути, pending coherent source/Tech gate; **pip не возобновлён**. S7 снова sole hardware owner для этой узкой readiness/ожидания gate. [Actual GI readiness](../../S7-evidence/R25/gi-readiness.json):

- Stage Python3.12.12, baseprefix `/home/pollen/.local/share/uv/python/cpython-3.12.12-linux-aarch64-gnu`; **import gi FAIL: ModuleNotFoundError gi**. Stage sys.path содержит собственный site-packages + basepython site-packages, без factory venv site-packages; PyGObject/pycairo distributions отсутствуют.
- Existing `/venvs/mini_daemon/bin/python` — тот же underlying Python3.12.12/baseprefix; **gi3.46.0 import PASS**, module `/venvs/mini_daemon/lib/python3.12/site-packages/gi/__init__.py`; **Gst1.26.2.0**, namespace1.0. Distribution PyGObject3.46.0 и pycairo1.29.0 находятся в `/venvs/mini_daemon/lib/python3.12/site-packages`.
- Это доказывает границу --system-site-packages: новый venv не наследует parent factory-venv site-packages. Read-only inheritance path теперь известен точно; `.pth`/PYTHONPATH/package changes не применялись. No Gst.init/SDKClient/media initialization, installs/downloads/controls0 в этом follow-up. Baseenv/daemon не менялись. Await one coherent constraints + GI inheritance Tech gate; original15:20/15:50 limits remain.

## ONE authorized samepath correction/resume checkpoint — 15:05 MSK

ROOT/Tech gate `R25-evidence/TECH-correction-gate.json` разрешил ровно одно продолжение same App1.1.1/SDK1.11/s2s619e/bridge/SSH route. Original failed constraints/log/partial PC venv сохранены. Source correction hashes verified: only Starlette1.7→0.52.1 and intended child-only exact factory-site `.pth`, no base/daemon modifications. PC resumed installer rootPID3652 (same stage/source/cache), Robot correction transferred and hash-checked before dispatch. A transfer helper initially used wrong archive-root name; corrected to actual `R25-constraints-correction` before Robot resumed installation, no resolver attempt during that helper failure. Stage/deps still IN PROGRESS, not ready. Old Agent remainsON; no serve/warmup/App/tunnel/control/inference started. S7 sole owner for approved resume, 15:20 actualserver/protocol orSTOP and15:50 harddeadline unchanged; second essential setup/install failure STOP.
