# Архитектурный разбор трассировки Sandbox

**Статус:** архитектурный план согласован и реализован в локальной рабочей копии; затронутые проверки пройдены.

## Задача

Проверить полный путь наблюдаемости runtime: точки логирования → персистентный журнал → API/SSE → модель трассы на frontend → дерево исполнений → типизированные инспекторы. Цель интерфейса — показывать структуру и последовательность работы в дереве, а в инспекторе выбранной сущности — только значимые для её типа данные с едиными названиями, статусами и форматами.

## Архитектурная основа

Каноническое хранилище событий — `runtime_execution_events`. События получают `event_id` и монотонный `sequence`; API читает журнал в этом порядке, SSE передаёт те же записи, а frontend дедуплицирует их по ID. После завершения sandbox-run пропущенный realtime хвост восстанавливается чтением журнала из БД. Поэтому итоговый trace надёжнее realtime-картинки во время выполнения.

Связи имеют разный смысл:

- `entity_type/id` — сущность, которую описывает событие;
- `parent_entity_type/id` — сущность-владелец в графе выполнения;
- `caused_by_event_id` — событие, которое вызвало ответ, повтор или отказ.

Нельзя восстанавливать отношения по соседству sequence, заголовкам задач или slug исполнителя. Контракт графа и его ID описаны в [RUNTIME_TRACE_SPEC.md](RUNTIME_TRACE_SPEC.md); презентационный контракт инспектора — в [SANDBOX_RUNTIME.md](SANDBOX_RUNTIME.md).

## Карта «сущность → основные события → UI»

| Сущность | Основные события | Представление |
| --- | --- | --- |
| `run` | `run_start/end`, финальное состояние, бюджет, ошибка | Статус запуска, ответ, вложения и итоговые ограничения |
| `orchestrator` / TurnPreflight | lifecycle, решение маршрутизации и LLM calls | Корневой этап маршрутизации; типизированный маршрут и вызовы |
| `planner_iteration` | начало/конец волны, применённый план, checkpoint и planner call | Этап решения: план, его задачи и передача управления |
| `task` | `task_planned`, lifecycle, причина исхода и зависимости | Один логический узел задачи со статусом и результатом |
| `attempt` | начало/успех/ошибка попытки, retry | Последовательность попыток внутри одной задачи; сейчас не отдельный самостоятельный узел дерева |
| `step` | `step_start/end`, task/attempt IDs | Конкретный шаг исполнения; не должен дублировать логическую задачу |
| `agent_execution` | `agent_start/end`, task snapshot, prompt/access/limits snapshots | Инфо, задача и доступные терминальные данные исполнителя |
| `llm_call` | `llm_request/response`, `protocol_retry`, usage/context allocation | Запрос, ответ или ошибка, статус, длительность и повторы |
| `tool_call` | `tool_call/result`, извлечение документа и memory payload | Запрос и безопасный типизированный результат операции |
| `checkpoint` | planned/decided с declared/effective next | Контрольная точка и фактическое решение планировщика |
| `synthesis_run` | start/end, финальная метка ответа | Синтез и единственный канонический итог ответа |

## Реализованные изменения

### Канонический результат запуска

Runtime создаёт `final_answer_marker`, принадлежащий `run` и ссылающийся на `synthesis_run`. В нём фиксируются статус, текст, источники и вложения. Транспортные `final`/`delta` остаются SSE-событиями и не записываются как второй итог журнала. Run inspector и история получают ответ из канонической метки.

### Задачи, попытки и терминальные состояния

Проектор группирует шаги по логической задаче, а попытки — по явному `attempt_id`; retry не создаёт дублирующую задачу. `terminal=false` не завершает вызов и не увеличивает успешные счётчики. Lifecycle исполнителя фиксирует `completed`, `failed`, `paused` либо `cancelled`; при отмене запись единственного `agent_end` ожидается до проброса `CancelledError`.

### Маршрутизация, overrides и снимки

`preflight_route_decision` фиксирует предложенный и эффективный маршрут с причиной выбора/перенаправления. `sandbox_override_snapshot` связывает заданные overrides с эффективными операциями и причинами подавления; разрешение по-прежнему ограничено обнаруженными возможностями, canonical publication и RBAC. Неселектируемые release и небезопасные изменения scope представлены как недоступные для редактирования.

### Инспекторы и представление

Табы строятся по наличию значимых данных. «Проверка» заменена на «Валидация» и появляется только для собственно validation checks; доступ и лимиты остаются отдельными темами. Добавлено типизированное представление tool overrides. Для run-бюджета используются только события с владельцем `run`; промежуточные и дочерние события не подменяют агрегаты запуска.

Изменения отражены в [RUNTIME_TRACE_SPEC.md](RUNTIME_TRACE_SPEC.md) и [SANDBOX_RUNTIME.md](SANDBOX_RUNTIME.md). Остальные незавершённые изменения рабочей копии относятся к параллельным задачам и не включены в описанную проверку.

## Рекомендуемая целевая модель

1. Backend emits typed lifecycle, terminal result, error, retry, usage, budget/access snapshot and correlation IDs at every runtime boundary.
2. Persisted journal remains canonical. API and SSE preserve the same event identity, parent links and sequence; replay is deterministic.
3. One frontend projector converts journal records to typed presentation entities and typed run result. View components do not search/reinterpret raw journal payloads.
4. Trace tree shows only execution structure and order: stage → logical task/checkpoint → attempts/steps → executor → calls. Event spam remains inside RAW or is aggregated.
5. Inspector tab policy derives from entity kind and available data. Every field has one human label, normalized value, source and absence policy. Remove duplicate or semantically unclear tabs.

## Приёмка и ограничения

- Runtime события для run result, route decision и tool override имеют типизированные owner/parent IDs; terminal отменённого исполнителя сохраняется до возврата отмены.
- Регрессионные тесты покрывают канонический итог, группировку попыток, nonterminal calls, overrides и отмену.
- Проекции используют корреляционные связи и owner-scoped данные для маршрута, результата и бюджета; вкладки скрываются при отсутствии исходных значений.

Проверка live/replay паритета выполнена на уровне unit-проекций и событийного контракта, но отдельный сквозной запуск браузера на живом sandbox run не проводился. Полный frontend build и полный backend suite также не входили в этот локальный набор проверок.

## Локальная среда и проверки

Проверки выполняются в Docker Compose на исходниках этой рабочей копии. На момент записи все compose-сервисы были запущены; отдельный build/recreate не выполнялся.

- `docker compose exec -T frontend npm run type-check` — прошёл.
- `docker compose exec -T frontend npm run test:unit -- src/domains/sandbox` — 78 тестов прошли.
- `docker compose exec -T api python -m pytest ...` — 106 выбранных runtime, sandbox, overrides, operation resolution и preflight тестов прошли; pytest выдал 3 существующих Pydantic warnings о поле `schema`.
- `docker compose exec -T frontend npm run type-check` — прошёл.
- `git diff --check` — прошёл.

## Follow-up по run `dcb7485a-756f-4247-9403-1071b6aa09e3` (2026-10-25)

Разбор реальных записей журнала подтвердил несколько дефектов, пропущенных предыдущей проверкой:

- Preflight сделал `memory.search`, ошибочно принял описания типов коммутаторов за ответ об инвентаре и изменил scope. Runtime затем перенаправил запрос в planner. Для явных запросов текущего инвентаря добавлена ранняя политика planner-маршрута с объяснением причины в route inspector.
- Агент завершился до проверки NetBox: `ExecutionPreflight.prepare()` не передавал sandbox overrides дальше в `OperationRouter`, хотя вызывающая сторона уже передавала этот параметр. Добавлена передача и regression на wiring.
- Перепланирование отдало `report_unresolved` для retry-задачи, но план оставил незакрытой её исходную задачу с `continue_with_tasks`. Проверка плана теперь считает исходную задачу закрытой, если все замены получили терминальный disposition.
- Для неудачного checkpoint в журнале был только `planner_checkpoint_failed`; UI показывал статус без понятного кода. Инспектор теперь показывает локализованную причину и точный error code, если отдельного безопасного сообщения нет.
- Ответ синтезатора был сохранён как `final_answer_marker`, но RunChat скрывал его из-за общего failed статуса запуска. Частичный итог теперь виден отдельно от статуса и ошибки запуска.
- Токены разделены на вход/выход/всего; checkpoint получил отдельную вкладку «Решение» с declared/effective переходом, причиной и итерацией.

Проверки follow-up: 58 API тестов и 83 sandbox frontend теста прошли; frontend type-check прошёл. Набор тронутых компонентов проверен unit-тестами; browser smoke на авторизованной сессии не завершён.
