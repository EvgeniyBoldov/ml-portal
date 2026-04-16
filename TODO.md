# TODO

Этот файл содержит только актуальный backlog.

## 1. Валидация загружаемых файлов

- Ввести явный allowlist по типам файлов для document upload и RAG upload.
- Валидировать расширение и MIME до запуска extraction pipeline.
- Синхронизировать правила для фронта, document collections и legacy RAG, чтобы не было разных входных контрактов.

## 2. Довести документный контур до одного канона

- Выровнять metadata contract между `collection_ingest`, `Source.meta` и UI.
- Зафиксировать публичные и внутренние retrieval-сурfaces для документов.
- Убрать остатки legacy RAG vocabulary из seed prompts и операторских подсказок.
- Явно зафиксировать, какие document fields являются обязательными, а какие автозаполняемыми.

## 3. Structured collection retrieval

- Сделать chunking для длинных text fields перед vectorization.
- Явно определить retrieval profiles по типу коллекции.
- Решить, где rerank обязателен, а где опционален.
- Добавить явный процесс revectorization всей таблицы для случаев смены модели или схемы.
- Оставить `semantic_search` только если он реально нужен как публичная операция, иначе увести внутрь backend.

## 4. Внешние интеграции через MCP

- Перенести оставшиеся внешние tool groups за MCP там, где это действительно упрощает ownership и креды.
- Довести discovery/config для provider domains до одного понятного контракта.
- Зафиксировать, что MCP rescan обновляет сырой каталог схем и tool descriptors, а runtime publication происходит отдельно через ToolProfile/OperationView.
- Проверить, что provider-specific credential scope и runtime publication описаны одинаково во всех слоях.

## 5. Operational maturity

- Улучшить логирование и recovery paths для collection provisioning и vectorization failures.
- Добавить health checks и cleanup story для Qdrant collections per collection/workspace.
- Сделать operator-facing ошибки по ingest/reindex более точными и действия-ориентированными.

## 6. Канонизация runtime vocabulary

- Убедиться, что seed prompts, runtime docs и builtin tools не возвращают старые названия операций.
- Свести domain filtering к узкому набору canonical operations.
- Убирать legacy naming только после того, как новый contract покрыт тестами и seed prompts.
- Продумать tenant/company glossary для нормализации пользовательских запросов по локальным аббревиатурам и терминам инфраструктуры перед routing/search; scope должен быть tenant/company-aware, а алиасы должны быть явными и контролируемыми, чтобы `форт1` и похожие формы не давали случайных ложных срабатываний.

## 7. Аудит entity pages

- `AgentPage`: сверить overview/current version data с backend contract и отдельно решить, нужен ли `allowed_instance_slugs` в version UI или это уже лишний слой.
- `AgentVersionPage`: проверить, что tabs содержат только version-level поля, а мета и доступ к данным не размазаны по нескольким блокам.
- `AgentRunsPage`: проверить состав payload/display полей и убрать legacy naming из статусов и метаданных.
- `ToolPage`: сверить общий слой тулза, current version meta и backend meta, отдельно проверить схемы и versions list.
- `ToolVersionPage`: оставить только version-level поля, без backend schema surface и без чужой меты в hints.
- `InstancesListPage` и detail pages: сверить domain/kind/placement/health/credentials/runtime summary; проверить, не остались ли `tool_group`/legacy compat поля в UI.
- `CollectionPage`: проверить source/type, status/status_details, vector readiness, qdrant name, permission gate и retrieval profile; убрать `structured` как UI-термин.
- `CollectionsListPage` и `CollectionDataPage`: убрать legacy `structured` naming и довести labels/styles до table/document модели.
- Legacy group pages/hooks: удалены, если снова всплывут только как compatibility-хвост, но не как продуктовый путь.
- Пройтись по shared field blocks и убрать дубли, где одни и те же данные рисуются разными компонентами.

## 8. Runtime maturity and debuggability

- Добавить `runtime evaluation harness` с эталонными сценариями для chat/RAG/SQL/tool paths, чтобы ловить деградации качества, а не только статусы.
- Сделать `deterministic replay / trace pack`: сохранять полный runtime snapshot, effective collections/tools/agents, prompts и tool I/O для воспроизводимого повторного прогона.
- Ввести budget policy по latency/cost/tool-call depth: лимиты по времени, токенам и числу вызовов должны быть явными и наблюдаемыми.
- Добавить reliability layer для operations: retry policy, circuit breaker, idempotency guard и понятные fallback-ветки для внешних интеграций.
- Довести planner/sandbox introspection UI до explainability уровня: показывать не только шаги, но и причины выбора агентa/tool, candidate set и assembled prompt surfaces.

## 9. Runtime contracts and control plane

- Подготовить настоящий checkpoint resume для runtime. Текущий continuation через новый turn рабочий, но длинные сценарии и дорогие step chains потребуют mid-run checkpointing.
- Довести UI consumption для structured answer contract (`answer_blocks.v1`): рендер text/table/file/citations/action без обязательной markdown-парсилки.
- Добавить режимы обязательных citations для критичных retrieval/analysis ответов (базовый `grounding score` уже сохраняется в `assistant.meta.grounding`).

## 10. Platform limits consolidation (P0)

- Привести `PlatformSettings` к правилу: в UI показываем только то, что реально применяется в runtime.
- Зафиксировать и оставить рабочий набор полей:
  - safety gates: `require_confirmation_for_write`, `require_confirmation_for_destructive`, `forbid_destructive`, `forbid_write_in_prod`
  - runtime caps: `abs_max_steps`, `abs_max_timeout_s`, `abs_max_plan_steps`, `abs_max_concurrency`
  - chat upload: `chat_upload_max_bytes`, `chat_upload_allowed_extensions`
- Для полей, которые остаются в контракте, но не применяются, сделать одно из двух (без промежуточного состояния):
  - либо добавить enforcement,
  - либо удалить из backend schema/model/service/router + frontend формы.
- Кандидаты на выпил в текущем состоянии (если не добавляем enforcement): `require_backup_before_write`, `abs_max_task_runtime_s`, `abs_max_retries`, `abs_max_tool_calls_per_step`.
- Исправить PATCH `/admin/settings` так, чтобы поддерживалась явная очистка nullable-полей (`null`) из UI.

## 11. Backend → Frontend field wiring (P0)

- `AgentPage`: прокинуть контейнерный `logging_level`.
- `AgentPage`: прокинуть контейнерные `tags`.
- `CollectionPage` (create/update): прокинуть `table_name`.
- `CollectionPage` (create/update): прокинуть `table_schema` (JSON).
- `CollectionPage` (SQL create): прокинуть `data_instance_id` (выбор instance).
- `CollectionPage`: определить судьбу `source_contract`:
  - либо сделать editable в UI,
  - либо убрать из публичного create/update контракта и оставить backend-managed.
- `ToolPage`: сделать `domains` редактируемым (сейчас readonly при наличии backend update поля).

## 12. Limits entity decision (P1)

- Принять решение по `Limit` entity: либо реально используем как отдельный контур и делаем admin UI, либо исключаем из продуктового контура и чистим legacy-остатки.
