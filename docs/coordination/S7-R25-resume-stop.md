# S7 R25 approved resume — second essential dependency STOP

17 октября2026, final **15:05:32 MSK**. **Единственный ROOT-approved samepath correction/resume использован; второй essential dependency gate FAIL → STOP. Hardware явно освобождён TechLead `01a148d9-f558-7151-93c5-016d77b24489`.** Same official App1.1.1/SDK1.11/s2s619e/bridge/SSH architecture сохранена. Новый version/platform/environment strategy не выбирался. Runtime server/protocol milestone не достигнут; ожидание15:20/остатка15:50 не даёт разрешения продолжать после этого gate.

## Exact second blocker

PC same isolated stage `C:/Users/User/reachy-shadow/R25-local-20261017-1450`: resumed `pip install` завершил установку speech-to-speech1.0.0 и зависимостей в child venv; затем **обязательный полный `python -m pip check` вернул exit1 в15:04:59**. Owned root3652 естественно завершился, pid_exists=false. CLI/import/version gate после check **не выполнялся**; ready/serve PASS нет.

Actual check сообщает конфликты inherited/duplicate distribution closure:

- `open-webui0.11.0` pins aiohttp3.13.5/boto3 1.42.62/onnxruntime1.26.0/openai2.29.0; обнаружены3.14.3/1.43.78/1.27.0/2.54.0.
- inherited `reachy-mini1.9.0` требует starlette<1.0.0, обнаружен1.6.0.
- `speech-to-speech1.0.0` требует nltk3.10.3/openai2.28.0/transformers>=5.18,<6; check перечисляет3.9.4/2.54.0/5.5.4.
- qwen-tts-hf/faster-qwen3-tts требуют transformers>=5.15.1 и accelerate1.12.0; check перечисляет5.5.4/1.13.0.

Pip install log одновременно показывает child installation новых версий и отказ удалять base packages outside environment; check видит конфликтующие metadata. Точное runtime import precedence этой duplicate closure не исследовалось после failure. Конкретный blocker — **полный проверяемый dependency closure не прошёл**, а не доказанный model/HTTP/GPU fault. Не игнорировались старые warnings, не фильтровался `pip check`, не удалялись base distributions, не выбирались третий install или новый venv. [Exact PC log/state](../../S7-evidence/R25/s2s-resume-status.json).

## Robot correction outcome and stop

Public correction archive SHA `017c6b09b4447d6e60ea396e36eef3c17554ff5677bb78985686e430671e96c5`, все12artifacthashes проверены до execution. Child-only factory inheritance **фактически PASS**: samePython3.12.12/baseprefix/baseexe, PyGObject3.46.0/Gst1.26.2.0/SDK1.11.0 из существующего `/venvs/mini_daemon/lib/python3.12/site-packages`; новая `.pth` только child-site. Factory/base env/files не менялись. Исходный constraints SHA48cd619b… сохранён; **новый corrected file SHA5482d83c0e81a2a1da1eb9e648716a72699d9ab1af23bdef08662f2ef54295fa**, только Starlette1.7→0.52.1.

Robot approved resumed pip стартовал один раз после setup/hash checks. На PC check failure ещё выполнялся dependency resolver; exact owned detached process group **272055 SIGTERM→no remaining live group в15:05:27**. Stage и logs сохранены; Robot install/check/import completion не заявляется. Frozen source/runtime bridge не менялся. [Actual inheritance/pip progress](../../S7-evidence/R25/app-resume-status.json), [stop/hash/services](../../S7-evidence/R25/stop-robot-resume.json).

Два operator transfer helper failures до resumed Robot setup были исправлены без нового install attempt: неверное имя archive root, затем cross-device rename /tmp→workspace заменён exclusive copy. Они не изменяли constraints/source/base и не запускают новую runtime попытку.

## Preserved current ON and effects

**App0/s2sserve0/bridge0/warmups0/tunnels0/newinference0/controls0/service-restarts0/oldAgentstops0/HFallocations0/runtime private audio-JPEG cloud egress0.** Public package/source downloads и child-only files — единственные изменения. Silero/SmartTurn/ASR/TTS/LLM startup models не запускались. Оба exact stages, caches, original failure receipts/correction files и private rollback stages сохранены. Нет нового8765/18765listener.

Final **15:05:32** old localON: sameAgentboot a309d491/mic287/listeningcaptureON/source5/**PCM367015936B/gaps0/overflow0/retiredfalse**, turns173/volume100/errorsabsent; motor137ON/quietprivacyfalse/ownersnull/Hubfree/actionfalse/stockknownunowned/workeridle. Robot services **Agent247720/factory150625 active/NRestarts0**. FinalPC: samecontainer c46d/image0e42/StartedAt08:53:44.615893658Z/RestartCount0, same advertised9B; nativebase torch2.13.0/transformers5.5.4/faster-whisper1.2.1/onnxruntime1.27.0 unchanged. Useful fallback никогда не выключался; restore controls не требовались. Existingcamera/operatorcapability/+2dB не менялись; нового camera/motion/voice acceptance нет. Historical422/R23failure остаются открытыми.

[Result](../../S7-evidence/R25/resume-result.json), [local ON](../../S7-evidence/R25/resume-fallback-final.json), [PC base/container/listeners](../../S7-evidence/R25/resume-final-pc.json). **Следующее решение — TechLead/ROOT; дальнейший install/fix самостоятельно не выбран.** Original total budget used≈15мин40с; source/review/setup результат не подменяет отсутствующий работающий App. Epochs — receipts, не control payloads.
