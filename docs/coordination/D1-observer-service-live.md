# D1 — observation service: access dependency

17 октября 2026, **07:31:10 MSK**. **Deployment остановлен до source transfer: разрешённый постоянный Hub→PC SSH auth/host-pin path не подтверждён.** Один strict BatchMode probe завершился255: `No ED25519 host key is known for 192.168.2.134 and you have requested strict checking. Host key verification failed.` Host checking не ослаблялся. Новые keys/grants/trust/ACL/firewall/permissions не создавались и не менялись. Это одна transport/access dependency, не ошибка D0 runtime.

Входы: [D0](D0-observer-service.md), [Q3](Q3-native-loop.md), [baseline](runtime-baseline.md), [PROJECT](PROJECT.md). D1 — единственный назначенный аппаратный инженер; выполнено только чтение. STOP/ON, capture owner, arm, inference/session/model launch или restart не выполнялись. Других чатов/подагентов не создавалось. R11 candidate не устанавливался.

## Существующие access references

Local `config.local.json` и установленный Hub config подтверждают Hub `deploy@192.168.2.181`, PC `User@192.168.2.134`, Agent `192.168.2.158:8090`. Существующий Mac→Hub SSH с `BatchMode=yes`, `StrictHostKeyChecking=yes`, `ControlMaster=no`, `ControlPath=none`, `ForwardAgent=no` успешно вернул **reachy-hub/deploy**. Существующий Mac→PC с теми же ограничениями вернул **DESKTOP-OMHR8MT**. Local existing trust reference — `/Users/notanonenough/.ssh/known_hosts`; identity не переопределялась, auth references не добавлялись.

Hub `/home/deploy/.ssh`: только `authorized_keys` (0600,111 B) и `known_hosts` (0600,95 B). Содержимое credentials/authorized_keys не читалось и не экспортировалось. Hub-local `config` и стандартные private key files отсутствуют в этом каталоге; `SSH_AUTH_SOCK` отсутствует. `ssh -G User@192.168.2.134` выбирает user `User`, hostname `192.168.2.134`, port22, только стандартные отсутствующие identity paths; proxy/нестандартный IdentityFile/agent reference в effective resolution не обнаружены. User pin paths — `/home/deploy/.ssh/known_hosts` и `known_hosts2`; существующий `known_hosts` имеет **0 matches** для PC. Arbitrary private credential locations не сканировались; отсутствие любого возможного ключа на всём диске не заявляется.

После inventory выполнен ровно один Hub→PC read-only `hostname` probe с strict checking/BatchMode/no multiplex/no agent forwarding. Он остановлен на отсутствии host pin **до authentication**. Поэтому отдельный auth failure не доказан; подтверждённого Hub-local auth reference тоже нет. Рабочий Mac→PC доступ не переносится на Hub и не подменяет service transport. Временный Mac reverse tunnel не создавался.

## Установка и фактические метрики

Все три `reachy-observer-{session,gateway,forward}.service`: `LoadState=not-found`, `ActiveState=inactive`. `/home/deploy/reachy-shadow/observer-service` отсутствует; существующий `/home/deploy/reachy-shadow/.venv/bin/python` есть. **Installed stage/units:0; source transfer:0; systemd mutation/enable:0; fresh arm:0; observer sessions:0.**

`systemd-analyze verify`, staged effective imports/pins, actual fast7736 identity/slotidle и full service preflight не выполнялись: access prerequisite не пройдён. Они обязательны перед будущим запуском. **Soak duration/actual decisions/discards/gaps/recoveries/bounded observer memory: N/A**, не нулевые измерения работающей session. D0 offline tests и R6 decisions не засчитываются D1. Startup failure/retry не было.

## Финальное состояние и cleanup

Два authenticated GET-only snapshots с существующим Hub config, последний перед07:31:10 MSK:

- Agent boot `eea946cc-b050-40e5-b5c5-a91e578439aa`, mic249 **ON**, phase/listening/capture active; source_generation3, retired=false, PCM54390784→54433792 B (**+43008 B**), gaps0/overflow0, turns1, last_error=null.
- Owners absent; policy124 motor=false, quiet=false, privacy_all=false. Hub free, action_running=false, stock known/unowned. Worker `ok=true, phase=idle` в обоих snapshots.
- Hub MainPID78887, NRestarts0, active; Hub config SHA256 `7f11d114873cc20de66e4789166ed5bbbd32109f708f82991aeb5ab3217d3b5e` совпадает с baseline.

Exact R8 Agent001be4ec…/A1 pump/config/S2 worker opt-in TRUE — сохранённая R9/S3 база; D1 их не изменяла. Новая независимая сверка всех robot/PC source hashes не выполнялась, новый fast7736 health/slot receipt не заявляется. GET snapshots подтверждают текущую listening/worker доступность, не весь будущий service preflight. Epochs выше — receipts, не готовые CAS payload.

SSH процессы — короткие foreground команды, завершены. Удалённые файлы/listeners/forwards/units/tokens/arms D1 не создавала; rollback не требуется. Production listening оставлено **ON**. **D1 завершена с одной access dependency и явно освобождает инженерное/аппаратное владение Reachy/Hub/PC.**

## Минимальный план для отдельного human approval

1. Владелец указывает уже существующие разрешённые **Hub-local** config/identity/known_hosts paths и alias для `User@192.168.2.134:22`, либо отдельно утверждает provision такого доступа. Требуемые поля D0: `OBSERVER_PC_SSH_CONFIG`, `OBSERVER_PC_IDENTITY_FILE`, `OBSERVER_PC_KNOWN_HOSTS`, `OBSERVER_PC_SSH_ALIAS`. Нужны проверенная PC host identity и разрешение PC для указанной identity. В текущем scope grant/trust/key provisioning запрещён; новый ключ и команда изменения authorized_keys не придумываются без утверждённой identity.
2. После предоставления references выполнить read-only команду ниже, сверить effective target и hostname DESKTOP-OMHR8MT. Использовать уже проверенный fingerprint, не TOFU/accept-new.
3. После этого новый sole owner получает стенд и выполняет exact D0 manifest stage/three-unit verify/effective imports/pins/fast7736 idle/fresh authority, один single-use arm, ≥30min observation-only soak. Units без enable/Restart=no; main/context/speech/motion/stock/workflows OFF,3s/6s/ledger256/fresh goal.changed_at. Known revoke terminal, UNKNOWN slot не очищать. Успешную службу можно оставить ON по исходному заданию.

```sh
ssh -F <approved-config> -oBatchMode=yes -oStrictHostKeyChecking=yes \
  -oUserKnownHostsFile=<approved-pin-file> -oIdentityFile=<approved-identity> \
  -oControlMaster=no -S none -oForwardAgent=no <approved-alias> hostname
```

Source transfer не предъявлялся reviewer, transfer refusal здесь нет. Первоначальный sandbox network denial разрешён approved read-only escalation; unresolved auto-review rejection в D1 **нет**. Отдельное согласование auth provisioning следует из прямой границы задания.

Evidence: [access inventory](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1481f-6632-7f01-bdd0-5de16b475dbb/D1-evidence/access-inventory.json), [Hub final/probe](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1481f-6632-7f01-bdd0-5de16b475dbb/D1-evidence/hub-final-readonly.json), [PC hostname](/Users/notanonenough/.codex/visualizations/2026/10/17/01a1481f-6632-7f01-bdd0-5de16b475dbb/D1-evidence/pc-hostname-readonly.json). Inventory JSON — metadata projection tool receipt5deb71; final receipts записаны непосредственным read-only collector `/private/tmp/D1-access-inventory.py`. Secrets/raw media отсутствуют.
