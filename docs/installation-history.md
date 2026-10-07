# История реальной установки и миграция

Дата оформления: 7 октября 2026. Реальные LAN IP и LM Studio model ID находятся в локальном config.local.json. Репозиторий оформляет ранее созданные рабочие программы в один пакет и конфиг; конфигурация интерфейсов, адресов, голоса и моделей больше не распределена по разным Python-файлам.

## Первоначальный hub

Рабочий каталог был `/home/deploy/reachy-hub`. Сначала был создан стандартный Python REST hub (`hub.py`, `config.json`, `scenarios/hello.json`, `data/events.log`), запускавшийся службой `reachy-hub.service`. Он опрашивал daemon и выполнял только ограниченные hello/wake/sleep. Затем добавлены `voice/voice_server.py`, `voice/voice_client.py`, `voice-config.json`, отдельный `voice-venv`, модели и `reachy-voice.service`.

Команды подготовки (выполнялись на хабе):

```sh
sudo apt-get update
sudo apt-get install -y python3-venv espeak-ng sox
mkdir -p /home/deploy/reachy-hub/{voice,models,data,scenarios}
python3 -m venv /home/deploy/reachy-hub/voice-venv
/home/deploy/reachy-hub/voice-venv/bin/pip install vosk piper-tts
# Версии фактического окружения сохранены в requirements/hub.lock.
# Модели скачивались по models.*.download_url, которые теперь в JSON.
sudo systemctl daemon-reload
sudo systemctl enable --now reachy-hub reachy-voice
```

eSpeak устанавливался как резервный вариант, текущий голос использует Piper. Прямая загрузка Vosk с alphacep зависала; рабочий ZIP взят из Hugging Face mirror, URL сохранён в конфиге. Предыдущий голос Irina сохранялся рядом с Ruslan. Мягкость сначала настраивалась параметрами Piper, затем выбран Ruslan и повышена высота SoX. Перед этими изменениями сохранялись резервные копии voice-config/source (суффиксы before-soft-voice и before-child-voice). Финальные настройки голоса — в `tts` общего конфига.

Первоначальные ExecStart:

```text
/usr/bin/python3 /home/deploy/reachy-hub/hub.py serve
/home/deploy/reachy-hub/voice-venv/bin/python /home/deploy/reachy-hub/voice/voice_server.py
```

Применялись User=deploy, Restart=on-failure, RestartSec=5, NoNewPrivileges, PrivateTmp, ProtectSystem=strict, ProtectHome=read-only, запись только data, UMask=0077 и OMP_NUM_THREADS=2 у voice.

## Первоначальный Reachy

Подключение выполнено к штатному SSH пользователя pollen, без изменения factory daemon. Создан `/home/pollen/reachy-hub-voice` с robot_agent.py/config.json/venv. Factory `.asoundrc` уже содержал dmix/dsnoop `reachymini_audio_sink/src`, карта 0, stereo 16 kHz, shared IPC; он не переписывался.

```sh
mkdir -p /home/pollen/reachy-hub-voice
python3 -m venv /home/pollen/reachy-hub-voice/venv
/home/pollen/reachy-hub-voice/venv/bin/pip install webrtcvad-wheels==2.0.14.post1
# alsa-utils уже присутствовал; в новой установке включён в apt_packages.
arecord -D plug:reachymini_audio_src -f S16_LE -r 16000 -c 1 -t raw
# Это ручная проверка захвата; завершить Ctrl-C.
aplay -D plug:reachymini_audio_sink /path/to/test.wav
sudo systemctl daemon-reload
sudo systemctl enable --now reachy-voice-agent
```

Первоначальный ExecStart:

```text
/home/pollen/reachy-hub-voice/venv/bin/python /home/pollen/reachy-hub-voice/robot_agent.py
```

Агент выполнялся User=pollen, в отдельном venv, с автоперезапуском и KillMode=control-group. Daemon-окружение `/venvs/mini_daemon` и приложения робота не изменялись. Настройка STT/TTS на ПК не выполнялась: ПК обслуживает только LLM.

Первоначальный адаптивный порог RMS ограничивался сверху значением 1200. При фоне примерно 1300 он постоянно срабатывал. Верхнее ограничение снято: порог зависит от шума с множителем 1.8 и floor=500. Зафиксирован рабочий порог примерно 1996.5. Стереоканалы микрофона при проверке оказались одинаковыми. Включён VAD mode=2; один VAD без RMS в этой обстановке шум не отсекал.

## Перенос в пакет

Новые root/venv задаются только в `deployment.*` конфига. При миграции копируются исходники, конфиг и существующий общий токен; имена основных systemd-служб сохраняются, меняется ExecStart. Старые каталоги оставлены для отката. Для использования уже скачанных моделей их можно копировать (либо временно ссылаться на старый models). Установка в чистый каталог скачивает модели автоматически.

Последовательность миграции с Mac:

```sh
HUB_ROOT=$(./scripts/companion config value deployment.hub.root)
ROBOT_ROOT=$(./scripts/companion config value deployment.robot.root)
./scripts/companion ssh hub -- sudo cp -a /etc/systemd/system/reachy-hub.service /etc/systemd/system/reachy-hub.service.before-companion
./scripts/companion ssh hub -- sudo cp -a /etc/systemd/system/reachy-voice.service /etc/systemd/system/reachy-voice.service.before-companion
./scripts/companion ssh robot -- sudo cp -a /etc/systemd/system/reachy-voice-agent.service /etc/systemd/system/reachy-voice-agent.service.before-companion
./scripts/companion deploy hub
./scripts/companion deploy robot
./scripts/companion voice status
# После проверки нового SSH через хаб и работы daemon:
./scripts/companion ssh robot -- sudo "$ROBOT_ROOT/scripts/companion" firewall confirm
```

Firewall установлен отдельно от factory system nftables ruleset. Пакет nftables добавлен на Reachy; собственная persistent-служба использует JSON allow-list. Отложенный rollback подготовлен до включения. Проверяются новый SSH через hub, REST daemon с hub, новый voice status и невозможность прямых новых подключений с Mac.

Для отката runtime к старым службам (данные старых каталогов должны сохраниться):

```sh
./scripts/companion ssh hub -- sudo cp /etc/systemd/system/reachy-hub.service.before-companion /etc/systemd/system/reachy-hub.service
./scripts/companion ssh hub -- sudo cp /etc/systemd/system/reachy-voice.service.before-companion /etc/systemd/system/reachy-voice.service
./scripts/companion ssh robot -- sudo cp /etc/systemd/system/reachy-voice-agent.service.before-companion /etc/systemd/system/reachy-voice-agent.service
./scripts/companion ssh hub -- sudo systemctl daemon-reload
./scripts/companion ssh robot -- sudo systemctl daemon-reload
./scripts/companion ssh hub -- sudo systemctl restart reachy-hub reachy-voice
./scripts/companion ssh robot -- sudo systemctl restart reachy-voice-agent
```

Runtime-откат не снимает firewall. Для снятия: `ssh robot -- sudo systemctl disable --now reachy-companion-firewall.service`. При полностью потерянном SSH и уже подтверждённом firewall нужен локальный доступ к роботу или возврат хабу разрешённого адреса. После первого применения automatic rollback предназначен именно для предотвращения такой ситуации.

## Подтверждённое состояние после переноса

Runtime действительно переключён на `/home/deploy/reachy-companion` и `/home/pollen/reachy-companion`. Чтобы не скачивать веса и не дублировать рабочие зависимости, при этой миграции использованы ссылки:

```sh
# На хабе:
ln -s /home/deploy/reachy-hub/models /home/deploy/reachy-companion/models
ln -s /home/deploy/reachy-hub/voice-venv /home/deploy/reachy-companion/.venv
cd /home/deploy/reachy-companion
sudo ./scripts/companion install hub --skip-model-download
# На роботе:
ln -s /home/pollen/reachy-hub-voice/venv /home/pollen/reachy-companion/.venv
cd /home/pollen/reachy-companion
sudo ./scripts/companion install robot
```

**Старые каталоги сейчас нужны не только для отката:** ссылки models/.venv зависят от них. Не удалять их до замены ссылок полноценными каталогами (создать новые venv установщиком, перенести/скачать модели и проверить службы). При чистой установке без таких ссылок установщик создаёт обычные новые каталоги.

Шесть локальных тестов прошли. Новый пакет на хабе загрузил реальные модели, получил ответ LM Studio и синтезировал WAV. После миграции успешно выполнены hub status, voice status, SSH через хаб, pause → ask → проигрывание → resume. Генерация проверочной короткой реплики заняла 4,77 s (без времени проигрывания). Прямой REST через IPv4 и IPv6 с Mac завершился таймаутом; прямой SSH закрыт. Firewall подтверждён после проверок; повторный запуск его службы проверяет повторное создание правил. Автозапуск включён; полная перезагрузка устройств ради проверки не выполнялась.


## Второй этап: перенос вычислений на Windows ПК

После первого этапа пользователь запустил `scripts/start-worker.ps1` на Windows 11 с Docker Desktop (Linux engine). Для первоначального скачивания весов понадобился VPN. Worker сообщил `Worker ready`; затем с hub проверены health и запрос с общим токеном. LM Studio продолжает запускаться вручную; её CLI-автозапуск отложен.

Перед переносом сохранены резервные копии. Команды выполнялись на соответствующем устройстве (к Reachy подключение только через jump host):

```sh
# Hub, до deploy:
cd /home/deploy/reachy-companion
cp -an config.local.json config.before-router.local.json
cp -an src src.before-router
sudo cp -an /etc/systemd/system/reachy-hub.service /etc/systemd/system/reachy-hub.service.before-router
sudo cp -an /etc/systemd/system/reachy-voice.service /etc/systemd/system/reachy-voice.service.before-router
# Reachy, до копирования:
cd /home/pollen/reachy-companion
cp -an config.local.json config.before-router.local.json
cp -an src src.before-router
sudo cp -an /etc/systemd/system/reachy-voice-agent.service /etc/systemd/system/reachy-voice-agent.service.before-router
```

В основном config.local.json установлены voice.mode=remote, streaming.enabled=true и deployment.hub.venv_dir=.venv-router. Hub обновлён `./scripts/companion deploy hub`: apt проверил Python venv, создано новое чистое окружение, установлен пакет 0.2.0 с пустым hub.lock, перезапущены reachy-hub/reachy-voice. В новом окружении нет vosk, piper и onnxruntime. Старые веса и .venv-ссылка сохранены для явного отката; текущие службы хаба их не используют.

Код/конфиг/токен робота скопированы через scp -J hub, затем выполнено `sudo ./scripts/companion install robot`. Это тот же порядок, что `deploy robot`; пароль factory SSH введён интерактивно. Установщик проверил python3-venv, alsa-utils, nftables, установил robot.lock и пакет 0.2.0, обновил systemd и заново применил firewall с таймером отката. После нового SSH через hub проверены обе службы и выполнено `sudo ./scripts/companion firewall confirm`.

Проверки: pause → ask → успешный поток PCM в ALSA → resume; полный синтетический STT→LLM→TTS через реальный Windows worker; agent снова listening, last_error=null; прямые Mac-подключения к Reachy на 22/8000/8090 закрыты. Время первого chunk полного turn — 1,099 s, поток завершён за 1,285 s (запись/проигрывание не входят). STT/TTS пока используют CPU ПК, LM Studio — RTX 5070. Hub выполняет только маршрутизацию, авторизацию и контроль допустимых команд. OpenClaw/Hermes — задел с адаптерами, без развёртывания.

При откате вернуть voice.mode=local, streaming.enabled=false и deployment.hub.venv_dir=.venv, затем deploy hub/robot. Существующая .venv-ссылка хаба зависит от старого каталога; robot .venv тоже остаётся ссылкой, поэтому старые каталоги пока не удалять.


## Новый характер и голос

По запросу пользователя детский характер заменён на язвительного молодого приятеля. Профиль вынесен в profiles/friend.json; llm.system_prompt, tts и служебные conversation-фразы обновлены в example и основном локальном конфиге. Pitch +300 cents вместо +650, length_scale=1.0; остальные параметры мягкости и громкости сохранены. Для Windows подготовлен apply-character.ps1 с резервным копированием и перезапуском worker. У Windows нет настроенного SSH или API изменения конфигурации, поэтому постоянное применение на ПК требует запуска этого скрипта пользователем; до этого worker сохраняет прежний профиль.
