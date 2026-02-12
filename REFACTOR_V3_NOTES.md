# Refactor V3 — Instance Types, RBAC Flatten, Tool Router, Assistant Mode

## Текущая архитектура (разведка)

### Таблицы (ключевые)
- **tool_groups** — группы: jira, rag, netbox, collection
- **tools** — конкретные операции: rag.search, collection.search, collection.get, collection.aggregate
- **tool_instances** — подключения к системам (jira-prod, netbox-main). Нет поля type (local/remote)
- **tool_releases** / **tool_backend_releases** — версионирование tool schemas
- **credentials** — owner-based (user/tenant/platform), привязаны к tool_instance
- **permission_sets** — RBAC для инстансов (scope: default/tenant/user) — JSONB с instance_permissions
- **rbac_policies** + **rbac_rules** — granular RBAC (policy → rules). Контейнер RbacPolicy лишний
- **agents** → **agent_versions** → **agent_bindings** (tool + instance + credential_strategy)
- **policies** → **policy_versions** — текстовые правила поведения
- **limits** → **limit_versions** — execution limits
- **collections** — динамические таблицы, уже имеют tool_instance_id (auto-create при создании)
- **ragdocuments** — RAG документы, scope: local/global

### Сервисы
- **CollectionService** — уже создаёт ToolInstance при создании коллекции, НО не удаляет при удалении
- **ToolInstanceService** — CRUD + health check, нет понятия local/remote
- **PermissionService** — resolve permissions (User > Tenant > Default)
- **RbacService** — CRUD для RbacPolicy + RbacRule, check_access
- **AgentRouter** — pre-runtime: load agent → resolve perms → resolve tools → check prerequisites
- **AgentRuntime** — tool-call loop engine
- **ToolSyncService** — sync tools from code registry to DB at startup
- **ChatStreamService** — use_router flag, delegates to AgentRuntime

### Builtins
- rag.search — поиск по RAG
- collection.search — поиск по коллекциям
- collection.get — получение записи
- collection.aggregate — агрегация

### Startup hooks (db.py lifespan)
1. _ensure_default_admin
2. _register_embedding_models
3. _sync_tools_from_registry
4. _ensure_default_permission_set

---

## План изменений

### Phase 1: ToolInstance — local vs remote
1. Добавить поле `instance_type` в ToolInstance: "local" | "remote"
2. Локальные: RAG (глобальный), коллекции (per-collection) — создаются/удаляются автоматически
3. Удалённые: jira, netbox, crm — создаются вручную через UI
4. Миграция: добавить колонку, пометить существующие

### Phase 2: Auto-lifecycle для локальных инстансов
1. При создании коллекции → auto-create instance (уже есть!)
2. При удалении коллекции → auto-delete instance (ДОБАВИТЬ)
3. RAG → создать глобальный инстанс при старте (scope=global)
4. Авторескан инстансов: кнопка + при старте бека

### Phase 3: RBAC flatten
1. Убрать RbacPolicy контейнер
2. RbacRule привязывать напрямую к user/tenant/platform
3. Миграция: flatten rules, drop rbac_policies table

### Phase 4: Cleanup seeds
1. Почистить policy, limits, tools, agents в БД
2. Сгенерировать правильные seeds с описаниями

### Phase 5: Tool Router как tool
1. Создать builtin tool "tool_router" который выбирает нужный tool
2. Написать агентов для поиска по коллекциям и RAG

### Phase 6: Chat mode — Chat vs Assistant
1. Убрать выбор агента из чата
2. Два режима: "chat" (простой LLM) и "assistant" (через tool router)

### Phase 7: Runtime RBAC
1. Получить список разрешений для пользователя
2. Подсветить через LLM что нет кредов/инстансов/запрещено
