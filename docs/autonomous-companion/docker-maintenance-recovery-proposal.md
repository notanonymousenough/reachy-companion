# Предложение восстановления после CREATE UNKNOWN

Дата: 2026-10-17. Статус: **для review, исполнение не разрешено этим документом**.
Единственный hardware runner выполняет операции; writer готовит публичный план.

Цель — вернуть проверенный baseline и затем повторить голосовую проверку. Старая
операция CREATE остаётся исторически UNKNOWN. Отсутствие кандидата и работающий
baseline не доказывают, что отложенное исполнение CREATE невозможно.

## Проверенные факты и влияние

Read-only inventory runner установил следующие агрегаты. Они описывают момент
проверки и должны быть подтверждены перед обслуживанием.

| Область | Факт | Влияние / ограничение |
|---|---|---|
| Docker | 17 контейнеров: 1 running, 16 stopped | Работает только Reachy worker; обслуживание прервёт его |
| Restart policies | 12 unless-stopped, 5 no; running worker — unless-stopped | Поведение 11 остановленных unless-stopped проверить после границы; не запускать их специально |
| Execution domain | Linux Engine в Docker Desktop, live-restore=false | Обычный restart daemon сам по себе не доказывает завершение старого execution domain |
| WSL | Две distro; Docker Desktop использует WSL | Остановка всех WSL не входит в предложение; влияние на другую distro не установлено |
| Нативная модель | Непрерывность LM Studio при обслуживании не проверена | До выбора конкретного метода нельзя обещать её доступность |
| Submitters | Известные старые submitters отсутствуют, diagnostic observer исключён | Отсутствие будущих retries/других actors пока не доказано |
| Baseline | Исходный worker running, профиль прежний; кандидат отсутствует | Повторить exact-spec/source/profile/port checks после границы |
| Оператор | Mic/capture/listening/motor/quiet/privacy false; owners отсутствуют | Не включать микрофон автоматически по старому разрешению или receipt |
| Canonical slot | CREATE mutation_pending UNKNOWN | Не clear/delete, не known-false, не повторять CREATE, не создавать новый namespace |

Других активных **контейнеров** не обнаружено. Это не инвентаризация всех нативных
служб PC. Продолжительность перерыва неизвестна; ETA не установлен.

## Предлагаемая граница обслуживания

Предлагается ограничить воздействие Docker Desktop и связанным execution domain.
Конкретный поддерживаемый способ остановки/старта и его witnesses ещё должны
принять архитектор и runner. В документе намеренно нет исполняемых команд:
доказательства завершения домена пока недостаточны.

Текущий конкретный кандидат runner: штатно остановить **только Docker Desktop**
и bounded RO проверкой подтвердить завершение соответствующей Desktop WSL
среды и старых Windows request/backend/proxy, недоступность прежнего API и
отсутствие автоматического возобновления; только после этого fresh start.
Если среда остаётся running или свидетельства неизвестны — abort/manual handoff,
**без start и без принудительного WSL terminate/shutdown**. Это кандидат для
review, **не maintenance GO**. Имена distro/процессов и endpoint остаются в
приватном inventory; угадывать их по типовой установке нельзя.

Docker документирует [Desktop stop](https://docs.docker.com/reference/cli/docker/desktop/stop/).
Это описание подтверждает назначение средства управления, но не отсутствие
durable replay или завершение конкретного запроса. Отдельные WSL lifecycle
команды и перезагрузка PC не входят в этот кандидат.

Дополнительный bounded RO capability check: установлен Desktop CLI 0.4.3;
version/status и help stop/start доступны, stop/start поддерживают timeout.
Самих stop/start не выполняли. Текущий pipe обслуживается Desktop backend;
в registry две distro, целевая Desktop distro уникальна и связана с локальным
Desktop storage. Однако выбранный WSL-engine setting недоступен: точная связь
endpoint → backend → завершаемая distro как достаточная execution boundary
**UNKNOWN**, исключение воздействия на соседнюю distro также **UNKNOWN**.
Эти capability checks не разрешают переход к обслуживанию.

Для submitters требуется проверяемый maintenance hold всех управляемых launcher,
scheduler и retry paths на время границы. Координатор уже поставил управляемые
чаты на HOLD PC mutations; это не доказывает hold всех внешних submitters.
Требуется установить фактический scope и контроль доступа к endpoint. Нельзя
выдавать отсутствие известных процессов за доказательство отсутствия всех
будущих пользователей или акторов.

RO результат по hold: координационный HOLD действует для трёх управляемых
классов ролей — runner/writer/reviewer; это не число процессов и не полный
аудит Windows retry/watchdog submitters. Canonical UNKNOWN блокирует новые
CREATE у клиентов, соблюдающих протокол. Общий проверенный enforcement для
всех управляемых будущих submitters пока отсутствует; gap ограничен этим
scope, а не требованием доказать отсутствие любых будущих внешних клиентов.
Известные прежние submitters отсутствуют. Новых мутаций и supersession нет.

### Последний RO topology / installed launch audit

Same fixed endpoint `/info`: Engine identity совпала с прежней, Linux/WSL2
kernel/Desktop OS подтверждены. Desktop APP/FileVersion 4.88.0.237115 отличается
от CLI 0.4.3. Известный settings-store.json существует и является JSON object,
но root key wslEngineEnabled отсутствует; explicit typed engine bool и
version-valid settings schema **не подтверждены**. Значение по умолчанию не
подставляется, широкий поиск других файлов не выполняется.

Точная приватная выборка Desktop target дала unique/version2/running/storage
association true; соседняя distro исключена из выбора. Всего registry records2
и running WSL targets2. Это уточняет выбранную цель, но не заменяет открытый
settings-schema proof или доказательство отсутствия воздействия на соседа.

Управляемый installed audit: одна enrolled startup task, XML enrollment и
project action/startup link совпали; enabled1/running0/restartCount3. Legacy
bypass/watchdog references в этой task отсутствуют. Owned services0, observed
project services0; owned-scope process metadata3, legacy bypass/watchdog refs0.
Эти три процесса не объявляются полным списком submitters. Известный прежний
CREATE submitter отсутствовал по предыдущей проверке.

**Конкретный незакрытый admission gap:** startup task включена и имеет retries.
Обслуживание должно включать её явный pause/disable и точное восстановление
исходной XML/enabled state по согласованному плану. Сейчас это не выполнено.
Известная project automation также ACTIVE: упоминание UNKNOWN в prompt не
является enforcement; требуется явный проверяемый HOLD её mutating dispatch
или согласованный pause с восстановлением. Координационный HOLD всех ролей
охватывает прямые legacy entries/private callers, но не подменяет эти действия.
Все проверки RO; runtime/task/service/slot/profile/Docker/WSL mutations0.

Конкретный предлагаемый HOLD после согласования обслуживания человеком:
приостановить **только heartbeat координатора** с сохранением его настроек;
отключить **только точно совпавшую enrolled startup task**, предварительно
сохранив XML, fingerprint и прежнее enabled state. Все managed roles и private
callers продолжают HOLD; старые actors должны отсутствовать, canonical UNKNOWN
сохраняется. После fresh inventory/spec/profile/port/operator reconciliation
восстановить исходное enabled state task и прежнее состояние heartbeat только
при безопасном текущем operator state. Если отключение/возврат имеет неизвестный
исход, не переходить к следующему шагу; выполнить RO сверку точной сущности.
Ничего из этого пока не выполнялось. Это конечный список managed admission
действий, а не требование аудита любого будущего клиента Windows.

Последующее решение архитектора rev21: SAME-pipe WSL2 runtime evidence вместе
с unique running linked target достаточно для runtime inference границы;
отсутствующий config boolean не является prerequisite и остаётся неизвестным.
Описанный конечный HOLD принят в managed scope; внешние клиенты исключаются
совместным обязательством не запускать команды на время обслуживания.
Это source decision, не свидетельство уже выполненного HOLD/обслуживания.

Подготовлен отдельный `deploy/autonomous/maintenance_supersession.py`:
существующий canonical provider удерживает **тот же** mutex весь переход,
проверяет exact namespace/approval/UNKNOWN bytes. Durable intent содержит
исходные bytes/hash до HOLD и disruption; затем approved boundary, recheck
перед fresh start, полный reconcile, durable supersession с outcome UNKNOWN
и ссылками SHA256 на приватные concrete witness bundles. Только после reread
обоих records и exact marker/approval — единственный existing `save(None)`.
Provider и effect adapter должны пройти отдельный composition review: модуль
не создаёт lock/namespace и не имеет CLI или Docker/FS реализации.

Ошибка **до** final save сохраняет canonical preimage, если его не изменил
другой actor; чужой marker никогда не перезаписывается. Ошибка **после** atomic
replace может означать уже заменённый marker: исходные bytes и UNKNOWN остаются
в durable journal/receipt, HOLD остаётся, task/heartbeat не восстанавливаются,
retry/новая мутация запрещены до RO reconciliation. Обещать неизменность
canonical bytes при неизвестном результате final write нельзя. Успешный save
проверяется как known-idle прежде чем adapter возвращает task/heartbeat.
Архитектор rev22 подтвердил: при UNKNOWN final write marker может быть прежним,
idle или недоступным; **даже pending=None не является authority**. Независимый
от slot HOLD сохраняется до RO manual reconciliation same plan/namespace/intent;
новые STOP/owner/privacy имеют приоритет. Нет второго clear или слепой записи
старого marker. Focused fixtures различают отказ до replace, после replace до
directory fsync и после fsync при verify; durable original/history и HOLD
сохраняются во всех трёх случаях.
Восемь синтетических тестов проверяют порядок и отказы, включая final-write
до/после rename, marker drift до fresh start и отказ restore. Runtime GO нет.

### Конечный source audit управляемых путей

Writer проверил публичные исходники перечисленных entry points. Это не
доказательство версии файлов, установленной на Windows, или отсутствия задач:
runner должен сопоставить только принадлежащие проекту task/service/process
metadata с этим списком. ROOT подтверждает полноту управляемого scope после
такого сопоставления; до этого HOLD coverage остаётся OPEN.

| Публичный путь | Guard / возможный обход | Кто удерживает |
|---|---|---|
| `scripts/start.ps1`, `scripts/start-worker.ps1`, `scripts/common.ps1`, `scripts/windows/verify_startup.py` | Обычный START вызывает read-only verifier; manual-stop проверяется до и после; bootstrap fallback запрещён | ROOT HOLD; runner проверяет installed source/task delegation |
| `scripts/install-startup.ps1` | Создаёт logon task с тремя restart attempts, делегирующий `start.ps1`; entry проверяет manual-stop; сам installer изменяет scheduler | ROOT запрещает installer; runner сверяет нашу фактическую task action/retry metadata |
| `scripts/bootstrap.ps1`, `scripts/bootstrap-worker.ps1` | Безусловный throw в начале; сохранённый ниже lifecycle recipe недостижим без изменения исходника | ROOT запрещает запуск/изменение; runner сверяет installed entry denial |
| `scripts/worker-docker`, `src/reachy_companion/worker_container.py` | Прямой Docker launcher **не проверяет** canonical slot/manual-stop; build/prepare/start/stop могут мутировать; command не запускает Docker, но до печати argv вызывает data_dir.mkdir, поэтому не является чистым RO | ROOT HOLD прямого CLI; runner проверяет отсутствие наших task/service/watchdog ссылок на этот entry |
| `scripts/apply-character.ps1` | Manual-stop guard есть, но profile write и Docker restart не проходят canonical slot | ROOT HOLD profile/restart пути; runner проверяет наши ссылки/акторы |
| `scripts/windows/enroll_worker.py`, `scripts/windows/stop_reachy.py` | Enrollment/owned stop — явные mutating инструменты, не разрешение обходить HOLD; dry-run отдельно | ROOT HOLD всех mutating вызовов, runner только разрешённая RO metadata |
| Frozen deployment caller runner | StrictSlot UNKNOWN блокирует protocol-compliant повтор; private installed source и launcher не входят в public source audit | Runner подтверждает отсутствие старых actors и retry/resume путей; ROOT HOLD новых вызовов |
| Управляемые chats/automation/watchdog | Координационный HOLD трёх role classes сам по себе не инвентаризация scheduler | ROOT объявляет конечный список наших launch/retry/resume путей, runner сопоставляет наши metadata |

Pure builders `deploy/autonomous/prepare_question_gate_container.py` и
`deploy/autonomous/docker_create_payload.py` не исполняют Docker operations.
Robot-native owner/runtime services не являются Windows CREATE submitters;
их сохранение и состояние проверяются отдельно. Наличие legacy bypass выше
запрещает объявлять canonical slot глобальной механической блокировкой.
Новый framework или патч guard в этом аудите не вводится. Условие будущего
обслуживания: пользователь и внешние клиенты не выполняют команды вне
согласованного managed scope во время границы.

1. Зафиксировать свежие operator state/STOP/epochs и RO inventory. Сохранить
   приватные exact baseline/spec/image/source/profile/FI receipts у runner.
   Проверить recoverability baseline и возможность вернуть штатные службы.
2. Установить полный перечень старых submitters, launcher/scheduler/watchdog и
   retry paths, способ их завершения и запрет последующего отложенного запуска.
   Известные отсутствующие процессы не заменяют это доказательство.
3. Завершить старый Docker execution domain выбранным reviewed способом вместе
   с submitters. Доказать отсутствие старого server/request execution и очередей,
   способных выполнить прежний CREATE после возврата. Не предполагать, что
   live-restore=false или новый PID daemon достаточны сами по себе.
   Проверить также durable state: новый domain не должен восстановить старую
   операцию из сохранённой очереди или restart/retry механизма.
4. Запустить новый разрешённый domain. Снять новую инвентаризацию: контейнеры и
   их состояния/restart policies, sole worker port, exact baseline sources/spec,
   профиль и FI, readiness модели и служб. Проверить отсутствие неожиданного
   кандидата и запуска ранее остановленных workloads. Если штатный worker не
   поднялся, восстановить только его reviewed baseline при свежем разрешении
   оператора; не выполнять прежний неизвестный CREATE.
5. После независимого review доказательств выполнить **ручной переход того же
   canonical slot** с записью `superseded-by-explicit-maintenance`. Запись связать
   с исходным UNKNOWN и maintenance witnesses; сохранить прежнюю историю и
   неопределённый исход CREATE. Это новая доказанная граница, а не доказательство
   отсутствия отправки старой операции. Не удалять pending history и не подменять
   её known-false; точный допустимый переход ещё требует review.
6. Сверить новые STOP/boot/ownership/epochs и штатные службы Reachy/PC/Hub.
   Только после этого отдельно разрешать следующий конечный тест. Сначала
   baseline readiness; gate deployment остаётся отдельной непрошедшей runtime
   приёмкой. Новый STOP или owner имеет приоритет над прежним состоянием.

## Критерии остановки и возврата

До обслуживания остановиться, если нельзя ограничить воздействие Docker Desktop,
исключить deferred execution или подтвердить recoverability baseline. После
обслуживания не продолжать тесты при неизвестном inventory/spec/profile/port,
неожиданном workload, старом submitter, недоступной модели или новом STOP.
Сохранить факты и UNKNOWN; не повторять мутацию вслепую. Штатные службы вернуть
в ON там, где это допускает текущий оператор; mic/motor state не восстанавливать
поверх нового OFF/STOP/owner. Если безопасный возврат не доказан, сообщить точную
неопределённость без обещания доступности.

## Что нужно до исполнения

- Source contract Docker-only boundary и managed HOLD принят архитектором rev21;
  runner должен получить предусмотренные фактические witnesses при исполнении,
  включая отсутствие server/request execution и deferred replay.
- Runner подтверждает влияние выбранного метода на другую WSL distro и
  нативную модель; неизвестное влияние явно включается в согласуемый scope.
- Reviewer принимает ручной переход **того же** slot с сохранением UNKNOWN.
- Для этого перехода нужен отдельный узкий reviewed способ записи: исходные
  slot identity/version и pending operation должны точно совпасть; все witnesses
  должны быть привязаны к одной maintenance boundary. Сохранение исходного
  pending/history и новой supersession должно быть атомарным либо иметь
  однозначное восстановление из journal. Ошибка/неизвестный исход записи
  оставляет слот заблокированным до RO reconciliation; автоматического retry,
  clear и разрешения следующей мутации нет. Отдельный admin core подготовлен;
  его concrete canonical provider/effects composition ещё требует review.
- Координатор предъявляет человеку готовый scope прерывания и получает
  конкретное разрешение на это обслуживание. Постоянное разрешение на передачу
  данных не используется как свидетельство завершения execution domain.

После возврата baseline микрофон объявляется готовым только по свежему
подтверждению capture/listening. Для живого запроса выделяется отдельное окно
не менее 90 секунд без тестовых реплик и переключений; результат речи и
слышимость проверяются отдельно от HTTP/readiness.

Независимый source review rev124: **SOURCE GO только для абстрактного admin
core** в рамках provider/effects contracts; восемь тестов PASS. SHA256 references
типизированы, но adapter должен доказать реальную durable-сохранность private
evidence. Composition, maintenance и execution GO не выданы. Следующий
reviewable результат — конкретный provider/effects adapter, затем финальный
scope обслуживания для человека.
