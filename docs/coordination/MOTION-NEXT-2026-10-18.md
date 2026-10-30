# Оставленное движение и внимание: выбранный путь

18 октября 2026. Source/read-only анализ для TL; hardware owner только TL. Remote0, hardware0, product source changes0. Основание: повторное требование пользователя оставить живого компаньона с движением, U04/T01/T06; [handoff](HANDOFF-2026-10-18.md), [реестр](REQUIREMENTS.md). Старые диагностические окна R34/R46 не запускались.

**Выбор: сохранить установленный stock factory transport, включить durable motor policy через существующий CAS API и принять существующий ExpressionPlayer вместе с новым guarded sensory attention.** Native actor/новый writer/прямая отправка SDK-команд не нужны. Source-исправление expression_player/motion_proxy/speech_motion по прочитанному коду сейчас не обосновано.

## Почему сейчас нет движения

- Handoff оставил factory в `enabled` hold, но durable `motion_policy.motor_enabled=false`. `Agent.motor_permitted()` требует одновременно guarded_motion enabled, motor permission true и quiet/privacy false. ExpressionPlayer не ставит движения в очередь без этой проверки. Это конкретный программный запрет; source не доказывает физическую неисправность и не устанавливает неизвестную причину прежнего R34 сбоя.
- При `transport=stock` `motion_actor.ready=false / stock_factory_api_not_native_actor` штатно описывает отсутствие native actor. Это не запрет stock expressions и не причина ставить native service.
- Панель mode/MIC/initiative не включает motor. Смена normal/alice_test тоже не включает его.
- Capture-pump путь ставит `neutral` при возвращении к слушанию. Один этот pose не означает постоянное семантическое внимание. Существующий sound reaction и новый sensory bridge могут вызывать конечное внимание по реальному событию; speech timeline уже даёт движения во время речи. Бесконечный случайный idle sweep не предлагается.

## Уже существующий guarded путь

`worker /expression/plan` либо motion events из voice stream → `ExpressionPlayer.set/timeline` → `/actions/expression` Hub → одна serialized stock lane → `/api/move/goto` factory. На Agent один expression thread; поздние speech cues сливаются до текущей цели, бесконечного backlog нет. На Hub сохраняются boot/MIC/policy/expression_version CAS, factory free/ready, отсутствие чужого UUID, проверка control_mode и остановка только собственного UUID при отзыве. Unknown completion/stop остаётся latched, без автоматического обхода.

`motion_limits.validate_steps` разрешает только ориентацию головы и две антенны: xyz=0, minjerk, 0.5–1.5с на шаг, configured angle/step/total limits. `speech_motion.pose_step` ограничивает углы перед выдачей cue. Реальные runtime значения TL читает из установленного Agent/Hub/PC; локальный config.local и example не являются runtime evidence. Для первого включения не расширять уже принятые пределы.

TL уже предоставил actual whitelist readouts: [Robot](../../R52-mode/baseline/robot-motion-config.json), [Hub](../../R52-mode/baseline/hub-motion-config.json), [PC](../../R52-mode/baseline/pc-motion-config.json). Robot/Hub guarded stock enabled; на всех трёх expressions enabled, duration 0.55с, max total 3с, антенны ≤30°, speech_sync enabled с min interval 0.75с/160 cues/amplitude2°, library repeat_processing true. PC guarded native disabled закономерен для producer без hardware writer. `max_head_degrees` присутствует среди effective keys; whitelist не включил его значение, поэтому число здесь не выдумывается. Нет основания менять конфигурацию ради первого retained включения.

Первый speech cue исполняется через `wait_timeline` перед запуском aplay; последующие cues идут по SpeechClock. Это оценка синхронизации от записанных PCM и wall time, не измеренный акустический clock. `last_expression`/HTTP success не доказывает физическое перемещение; `completed` означает завершение обработки, даже при ошибке. Проверять также `last_error`, discarded/unknown и реальные положения.

## Минимальное включение и сохранение

1. TL получает свежий короткий срез: Agent operator/panel state, Hub status, factory move/running и control_mode; runtime Agent/Hub guarded_motion=`enabled:true,transport:stock`, expressions enabled; PC expressions/speech_sync enabled. Требуются owners NULL, privacy/quiet false, Hub stock unknown false/owned_uuid NULL, factory ready/free, фактический enabled и idle listening без речи/queued output. Если сейчас есть новый пользовательский OFF/privacy/чужой owner, не включать его поверх. Существующий factory enabled hold не требует wake/re-enable.
2. Через authenticated Hub `POST /control/motion-policy` отправить только актуальный разрешённый переход: `{motor_enabled:true,quiet:false,privacy_all:false,expected_boot_id:<fresh Agent boot>,expected_epoch:<fresh policy epoch>}`. Значения quiet/privacy берутся из свежего разрешающего состояния; чужие OFF не очищать. Не присваивать временного policy owner штатной эксплуатации и не менять конфигурацию/модели/transport ради этого шага.
3. **Побочный эффект, который нельзя потерять:** текущий `Agent.set_motion_policy` при любом write вызывает `initiative.cancel()` и retire capture. Motor ON не меняет durable listening/automatic intent, но отменяет активное schedule. Recovery допускает только `audio_loop_error`, поэтому на `cancelled` автоматически полагаться нельзя. Дождаться свежего capture progress. Если до перехода и после него durable automatic_requested остаётся true при той же intent generation, MIC/listening true и пользователь не дал OFF, выполнить одну явную `automatic_on` панели со свежим binding. При новом OFF не восстанавливать старый snapshot. Это отдельная контрольная команда, а не seed/restore файлов.
4. Speech использует уже существующий поток. Новый sensory bridge вызывает тот же ExpressionPlayer только по свежему разрешению и idle attention; при speaking/processing он ждёт. Не открывать вторую motion lane и не конкурировать с speech timeline. Новый bridge ещё нужно установить/включить/принять отдельно; его source сама по себе не является работающей сенсорикой.
5. Оставить durable motor ON после успешной приёмки; не делать автоматический motor OFF в finally успешного proof. Один штатный Agent restart подтверждает чтение policy true и возвращение durable MIC/schedule без перезаписи intent. Это проверка persistence, не soak/полное обесточивание.

## Ограниченная живая приёмка TL

Одно продуктовое окно до 5 минут после безопасного включения, без нового diagnostic harness:

- Обычный настоящий voice exchange: слышимая речь и минимум два изменившихся положения головы/антенн внутри речевого интервала; сопоставить фабричные actual positions/видео с временем playback. Успешные JSON/PCM/cues одни не считаются физическим результатом. После конца — возвращение к реальному capture и свободная stock lane без постоянного expression_error.
- Одно реальное неголосовое sound event в idle → bridge observation/model decision/attend → физическая реакция через ту же lane; следующая sensory итерация не ждёт речи. Не требовать поворота к конкретному направлению: текущий источник не даёт направления звука и не распознаёт собеседника. Камерная семантика отдельно OPEN.
- Один STOP во время собственного движения: текущий owned UUID прекращён/отсутствует, новые движения не появляются, policy motor false и MIC/initiative OFF. Это отзыв разрешения и прекращение команд, не доказательство снятия torque/питания. Затем TL может дать **новые явные** MIC/motor/automatic ON в рамках пользовательского поручения только по свежему состоянию, если нового пользовательского OFF/privacy не появилось; старые intent файлы не восстанавливать.
- После явного возобновления — ещё одна обычная реплика с движением и короткое наблюдение, что lane снова idle, capture растёт, motor policy осталась true. Успешное окно заканчивается работающим разрешённым состоянием. Если restart включён в это окно, повторить один exchange после restart. В отчёте честно разделить bounded retention и ещё не проверенный длительный soak.

При первой конкретной ошибке завершить этот proof и сохранить один срез/причину; не крутить старое диагностическое окно. Принятие функции требует совместного результата speech+movement+attention, а не только успешного motor ON.

## Fallback

При неизвестном completion/stop — явный motor policy OFF с текущим CAS, existing hold/owned stop; никакого чужого stop UUID, return-pose/sleep или direct REST/native обхода. Не сбрасывать `stock_unknown`/`_stock_cancel_unknown` через restart ради нового движения. Для известного owned UUID существует штатная bounded reconciliation при motor denied; использовать только её точный контракт и сохранять исход неизвестным при неполном наблюдении. Оставить доставленные voice/panel/MIC privacy способности, не откатывать пользовательский intent. Причина R34 остаётся OPEN до конкретного нового evidence.

## Выполненная локальная проверка

27 existing motion-policy/expression unit tests PASS. Дополнительно реальные r42 pure planners: 140 phase/emotion plans и 392 emotion/gesture speech timelines прошли текущий validate_steps на example+friend settings. Это подтверждает source bounds, не runtime config и не физическую приёмку. Source/Hub/Agent/config/manifest не изменялись этим scope.
