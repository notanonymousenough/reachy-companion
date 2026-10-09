# Optional VPS/n8n: выполненный этап

2026-10-09. На предоставленной VM фактически2vCPU/1966MiB RAM, Ubuntu24.04.4, Docker и существующий n8n2.32.0. Его пять контейнеров сохранили uptime4weeks; второй n8n не запускался. Создан отдельный companion workflow и отдельный broker-only compose проект. После запуска available RAM около863MiB; это текущий inventory, не обещание throughput. Вариант4GB/4vCPU остаётся допустимым будущим ресурсом.

`workflow.synthetic_echo` — единственная capability. Workflow: header-authenticated Webhook → Set (task_id/attempt_id/value) → response. Нет tools, robot controls, shell, моделей, S3 или paid API. Model выбирает только существующий candidate alias с kind=research; trusted adapter связывает его с этой capability. URLs, workflow selection и credentials не приходят из LLM. Feature по умолчанию disabled, отсутствие VPS не останавливает fast loop.

Broker хранит SQLite WAL в persistent volume, idempotency по task_id/attempt_id и digest всего envelope. Duplicate не dispatch повторно; conflicting body →409. Deadline до60s, value≤256chars, одна execution, bounded queue8, retention24h и cap1024 tombstones. При заполнении — admission refusal. Cancel отзывает acceptance; execution permit занят до фактического завершения. Неизвестное завершение/transport outage создаёт persistent quarantine, restart не снимает его и не повторяет jobs. Для восстановления нужен операторский аудит n8n execution; автоматического reset endpoint нет. Нельзя путать cancelled с физической остановкой n8n.

Broker опубликован только на127.0.0.1:15679; лимиты96MiB/0.25CPU, read-only root, no-new-privileges, cap_drop ALL, log rotation. Python image закреплён tag+digest, проверенным на VM. Existing editor listener0.0.0.0:5678 был до наших изменений; его bind/TLS не менялись. Для companion доступа используются loopback и SSH tunnel, публичный HTTP с credentials не используется. Existing editor hardening/TLS остаётся отдельным production gate.

Owner setup был пуст: создан owner с generated password; remote-only `admin.local.json`0600 хранит owner/session, `.env`0600 — отдельные webhook/broker tokens. Секреты не выводились и не включены в git. Workflow сохраняет neither success nor error payloads; два ранних собственных synthetic execution records удалены точечно. Остальные workflows/executions не изменялись.

## Воспроизведение и эксплуатация

Все instance/SSH параметры — ignored `config.workflows.local.json`, шаблон `config.workflows.example.json`. Выданный пользователем instance id хранится только в local config. Получить временный OS Login certificate штатным yc:

```sh
mkdir -m 700 -p /tmp/reachy-vps-ssh
yc compute ssh certificate export --directory /tmp/reachy-vps-ssh
```

Внести выведенный identity path, проверенные host/user/known_hosts/host_key_alias в local config. `ssh.py` использует обычные scp/SSH с StrictHostKeyChecking=yes; unknown host key проверяется штатным первым yc SSH подключением. Не переносить keys или secrets в git.

Для нового companion каталога на существующей n8n VM: создать каталог0700, скопировать reviewed deployment source files обычным scp. `setup_existing.py` проверен на установленной2.32.0; его REST routes version-specific. Он не сбрасывает existing owner, не перезапускает n8n и не делает bulk mutations. На VM:

```sh
python3 setup_existing.py --owner-email YOUR_OWNER_EMAIL
```

`--owner-email` нужен только при незавершённом owner setup; существующему owner требуется его авторизованная session. Session может истечь: восстановить её через editor/login, не reset owner. Generated credentials остаются в remote admin file. Идентификаторы созданных workflow/credential записываются там же.

Задать в remote `.env` фактический `N8N_NETWORK` и `N8N_WEBHOOK_URL` для существующего Docker network/container; копировать их из audited inventory. Затем из companion каталога:

```sh
sudo docker compose --progress plain -f broker-compose.yaml up -d
python3 smoke.py
sudo docker compose --progress plain -f broker-compose.yaml restart broker
python3 verify.py
```

После restart дождаться readiness `/health` (краткий connection reset во время startup допустим; проверять finite retry, не менять n8n). `smoke.py` создаёт только synthetic echo. Duplicate/auth проверяются на live broker; late/outage — в отдельных temporary stores с реальным n8n transport, не путём остановки existing services. `verify.py` повторяет уже существующий task и проверяет retention/dedupe/limits; нового execution не создаёт.

Локально, из repo:

```sh
python3 deploy/workflows/ssh.py copy deploy/workflows/broker.py deploy/workflows/broker-compose.yaml deploy/workflows/synthetic-echo.json deploy/workflows/setup_existing.py deploy/workflows/smoke.py deploy/workflows/verify.py
python3 deploy/workflows/ssh.py tunnel --duration 60
```

Tunnel bind толькоlocalhost, duration ограничена, exit/Ctrl-C гарантирует terminate/wait/kill. Для теста запускать отдельной bounded session и закрыть после проверки. Editor доступен черезlocalhost:15678, broker черезlocalhost:15679. Не менять VPN/routes этими командами.

Optional client config: `workflows.enabled=true`, `broker_url=http://127.0.0.1:15679`, отдельный token_env; token передаётся environment/private0600file. Для явного hybrid теста:

```sh
PYTHONPATH=src python3 deploy/workflows/shadow_smoke.py --config config.autonomous.vps.local.json --token-file /private/tmp/reachy-workflow-client.env
```

Hybrid означает fixture L0 + actual VPS workflow + simulated actors; это не real-model test. Обычный `replay` всегда остаётся без сети. Не переносить runtime logs/transcripts автоматически на VPS; synthetic capability не заменяет memory/privacy/export gates.

Restart только нового broker — команда выше. Rollback: disabled workflows в autonomous config; `docker compose -f broker-compose.yaml down` без `-v` сохраняет SQLite. Unpublish только созданный companion workflow через owner editor; не останавливать existing n8n. Для версии broker вернуть предыдущий source/compose и up -d после проверки idle/quarantine. Backup broker volume делать offline после остановки только broker; owner/webhook credentials хранить отдельно защищённо. Existing n8n data/encryption key/compose не удалять.

## Реально проверено

- Live authenticated n8n echo;10duplicates без повторного dispatch, conflict409; unauthenticated broker и webhook отказали.
- Actual n8n result, задержанный в isolated store, не принят после deadline; transport к closed localhost endpoint дал execution_unknown/quarantine. Existing n8n не останавливался.
- Через SSH tunnel: fixture fast → typed client → live broker/n8n → ready → fresh simulated commit.4fresh ticks,1task/ready/commit; inference/export/paid API/hardware=false.
- После broker recreate/restart SQLite сохранил прежний task: duplicate status expired, повторного execution нет. Active workflow, retention disabled, own saved executions0, memory96MiB, loopback-only подтверждены.
- Full local suite70tests passed, включая8workflow adversarial tests. Real L0/Main inference, CPU placement/tokenizer/VRAM и hardware stop/ownership ещё unknown. LAN недоступна из-за текущего VPN route; повторных LAN попыток не было.

Основание настройки: [официальная документация Webhook auth](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook.md), [security settings](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/security.md), [node restrictions](https://docs.n8n.io/deploy/host-n8n/configure-n8n/security/block-specific-nodes.md). Backend broker и ограничения — код этого репозитория, не встроенные гарантии n8n.
