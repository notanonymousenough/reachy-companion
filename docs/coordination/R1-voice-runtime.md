# R1: завершённый голосовой ход и штатное слушание

17 октября 2026, Europe/Moscow. Единственный оператор стенда — R1, текущий чат. Входы: `PROJECT.md`, `live-baseline-2026-10-17.md`, `R0-voice-failure.md`, задача №1 `DELIVERY-PLAN.md`. Другие чаты/подагенты не создавались.

**Получен один завершённый реальный ответный voice turn через внешнюю колонку без человека. После конечного cleanup включено штатное постоянное слушание существующего Agent. Исторический GuardDenied не воспроизвёлся; его конкретная runtime-причина остаётся неизвестной.** Нельзя объявлять исправленными freshness, STT или worker: адресная runtime-правка для них не потребовалась и не выполнялась. Автономный цикл, непрерывное зрение и совместные движения этим результатом не принимаются.

## Изменение и preflight

До аппаратного запуска сверены три исходных SHA-256 из R0 и patch `26000ae7dca9114915b492ec739f5dcd65b3489594b7f541c2799497954d27f9`. Сохранены byte-identical preimages, затем применён `deploy/patches/finite-alice-controller-failure.patch` к **существующему** `runner-20261015/Alice-factual-resume`, `--batch --fuzz=0 -p1`; dry-run прошёл. Итоговые hashes:

| Файл | SHA-256 после применения |
| --- | --- |
| controller.py | c5c521cb7f94a60dc95fa19be4a24043ff37130596ac53355f8f6561d1db97f4 |
| controller-driver.py | 126147bf7fe98928fafe2405c7b1a2d3f1e7e43e71a1cc1c0f0e4af3f5108cf6 |
| run.py | e4d0ff8e18f6cdbda7807c0a6b04c6338f467812b23f9fec20d5eea9cf839731 |

Это единственный source diff R1, уже подготовленный R0: structured failure receipt, controller.done при cleanup failure, конечное ожидание launcher. Repository launcher уже имел R0 hash `9571b76942ab81e7ea9e3335944926d467480b21b9239ee596ae5077c25dc69e`; повторно не менялся. Runtime/конфиги устройств, camera/perception/core и очищенные README/docs не редактировались. Guards не расширялись.

Свежий preflight 03:29 MSK подтвердил Agent PID199098, boot SHA `db8325cf60023a16c92d00af1b7b6411c32260159d77221f48e15bb503f71bde`, epochs210/114, OFF/paused, owners absent, ошибок нет. Factory PID150625 и Hub active; Hub free. Worker idle; Docker сохранил тот же container/image/StartedAt00:14:05Z, без рестарта. Agent/config/client hashes совпали с baseline. Source selfcheck исправленного runner прошёл без hardware; три изменённых файла дополнительно прошли compile/syntax и сверку SHA.

После установки повторены существующие `test_demo_launcher` и `test_finite_alice_failure`: **33 tests, OK, без skipped, 0.866s**. FINITE_ALICE_BASELINE указывал на временную офлайн-копию трёх сохранённых preimages и двух неизменённых posthoc-файлов, не на уже исправленный runner; тесты применили тот же repository patch. Новый harness/тесты не писались. `git diff --check` — OK. Лог `offline-tests.txt` сохранён рядом с evidence.

## Единственный диагностический повтор

```sh
python3 /Users/notanonenough/.codex/visualizations/2026/10/10/01a12596-fe7e-7592-ae4d-27652600c257/runner-20261015/Alice-factual-resume/run.py --execute --case sky --expected-mic 210 --expected-policy 114
```

Run ID `7c482724c64648beb3394f9681f4a13d`. Единственный новый scripted cue: **«Алиса, почему небо голубое?»**; ответ также начинается «Алиса, ...». Новых диагностических повторов, адресной правки runtime и подтверждающего voice-прогона не было: ошибка не повторилась. Последующий listening handoff не произносил новую тестовую фразу.

| Доказательство | Фактический результат |
| --- | --- |
| Cue /say | Собственный синхронный terminal, ok; worker idle с тем же fixed cue до resume |
| Реальный capture | Capture/listening наблюдались после cue; 388 role-qualified наблюдений capture-процесса, unknown/raced/empty=0 |
| Capture PCM | Agent journald в окне прогона: одна `phrase captured seconds=9.80`; 16kHz mono S16_LE, chunk100ms. Это около156800 mono frames по округлённой длительности, а не сохранённый точный счётчик samples |
| Энергия | Agent threshold_rms=588.1928011439704; существующий capture принимает только voiced chunks с RMS≥threshold и VAD. **Per-buffer RMS/peak не журналируются: отдельного численного измерения энергии этой фразы нет.** PCM не сохранялся и второй reader не запускался |
| Свежая STT → LLM | Agent turns1→2; worker_Agent_joined=true, actual_STT_nonempty=true; 19 слов, topic_match=true, cue overlap0.05263158; obvious_own_cue_echo=false; local_model_answer_route=true |
| Ответ | reply_nonempty/prefixed_Alice/complete_sentence=true; 13 слов; interruptions0→0, resumable_reply=false |
| Реальное воспроизведение | Дочерний `/usr/bin/aplay` с проверенными parent/cgroup/exe/argv0: 80 cue samples/span2.033202s; 158 reply samples/span5.372191s; reply_playback_end_observed=true |
| Terminal | completed=true, native_returncode0, phase_handshake_accepted=true, postnative_accepted=true; elapsed_watch32.551636s; controller23.290431s |

Это связанный capture→непустая внешняя STT→LLM→реальный ALSA playback, а не HTTP/PCM-only проба. Биометрическая идентичность внешнего говорящего, акустический onset и измерение звука отдельным датчиком не установлены (`speaker_identity=unknown`, `acoustic_onset_verified=false`). Private transcript остаётся в существующем защищённом runner, в отчёт не включён.

Полный строгий критерий краткости старого harness **не пройден**: `short_sample_target_met=false` (13>11 слов и sampled span>5s). Поэтому сам `run.py` возвращает3 при `completed=true`; это не GuardDenied и не незавершённое воспроизведение. Sampled span — нижняя граница наблюдений процесса, не верхняя граница физической длительности. В shell log вывод последующего `cat` имеет exit0; результат runner определяется его documented return branch и terminal receipt, не кодом shell wrapper.

## Точная диагностика отказа

Исторический baseline: GuardDenied, stage `observe_first_true_reply_playback`, controller elapsed11.764555s, `failure_reason=OTHER`; operator elapsed/endpoint/changed keys тогда потеряны. R0 установил конкретную причину **потери диагностики и зависания launcher**, а не причину первоначального runtime-отказа.

В R1 исключения нет: terminal `controller_failure_code=null`, stage=null, controller_cleanup_status=null (failure cleanup не вызывался), controller_wait_expired=false, controller_reap_unknown=false. В успешном controller receipt `operator_GET_elapsed`, changed_operator_keys и last_endpoint отсутствуют; это **не** elapsed0/пустой успешный guard trace. Для старого отказа эти значения восстановить нельзя. Свежий успех при неизменных Agent/Hub/worker/config/pins опровергает необходимость немедленно ослаблять guard или менять stack; он не доказывает конкретную сетевую причину и не доказывает, что отказ никогда не повторится.

## Cleanup и listening handoff

Конечный тест завершил штатный cleanup: epochs212/116, OFF, owners absent, admission_retired/aplay_absent/factory_running_empty/volume_preserved=true, stock_unknown=false, volume100. Native watch-result подтверждён отдельным read-only чтением; audio processes отсутствовали, factory moves=[]; worker idle. У watch mic_OFF_POST/policy_OFF_POST=false: выключение уже сделал Hub client, watch подтвердил результат. Старое maintenance CREATE UNKNOWN не повторялось/не очищалось; Docker не останавливался.

Затем выполнен **один** guarded `/control/microphone` enabled=true/listen=true из свежего OFF boot/epoch212. Новый engineering owner не создавался: переключатель передан обычному production Agent, owner fields остались отсутствующими. Это существующий `Agent.set_microphone`, не новый harness и не увеличение конечного watch TTL. Поддержка подтверждена установленным source, prefix «Алиса, », wake/greet_on_start=false и отсутствием finite Alice gate.

03:34:03 MSK после завершения запускавшего SSH: тот же boot, Agent listening, microphone/capture/listening=true, epoch213; turns2, interruptions0, errors null, worker idle. Reachy `arecord` PID203670, aplay отсутствует; factory moves=[]; Hub free. Policy116 motor_enabled=false, quiet/privacy=false. Capture оставлен штатному Agent. Инженерное эксклюзивное владение **освобождено**; работающие службы и listening ON оставлены пользователю. Микрофон durable state сохраняет ON; STOP/physical mute/оператор OFF остаются действующими. Listening ON не означает непрерывный capture во время STT/LLM/playback: установленный finite capture путь по-прежнему имеет эти паузы.

## Артефакты и следующий шаг

Установленный manifest, команды эксплуатации и recovery — [runtime-baseline.md](runtime-baseline.md). Локальная папка доказательств и preimages:

```text
/Users/notanonenough/.codex/visualizations/2026/10/17/01a14742-6820-7201-b686-6f3b26348959/R1-evidence/
```

Там сохранены original-controller preimages, диагностический stdout, phase/terminal/posthoc, preflight PC/Hub/Reachy, native watch/controller metadata, listening-handoff и final readings. На Reachy оригинал `/run/reachy-companion-demo-7c482724c64648beb3394f9681f4a13d/`; private plan не копировался. `/run` недолговечен, существенные результаты продублированы здесь.

Следующий ограниченный scope — №3 DELIVERY-PLAN: убрать несовместимость слуха и камеры, измерив реальную непрерывность; затем normal joined session №4. Эта задача не блокирует кодовую подготовку. Поднимать новый autonomous Gateway, менять media adapter и принимать весь проект в R1 не требуется.

Именной список для последующей очистки: `Alice-factual-resume/run.py`, `controller.py`, `controller-driver.py`, `posthoc.py`, `posthoc-driver.py` — конечная диагностика вне оставленного service-listening пути. Сейчас их **сохранить** как единственный воспроизведённый smoke и rollback до замены проверенной normal session. `scripts/companion_demo.py`/`deploy/autonomous/demo_watch.py` ещё нужны этому smoke; доказанного безопасного кандидата на удаление в R1 нет.
