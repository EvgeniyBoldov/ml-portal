# Agent Permissions System

Система управления правами доступа к инструментам и коллекциям для агентов.

## Обзор

Система состоит из следующих компонентов:

1. **ToolInstance** - конкретное подключение к инструменту
2. **CredentialSet** - зашифрованные креды для ToolInstance
3. **PermissionSet** - права на tools/collections
4. **AgentRouter** - pre-runtime маршрутизатор
5. **Policy** - политики выполнения агента

## Иерархия прав

```
Default → Tenant → User
```

**Приоритет при резолве:** User > Tenant > Default

- Если на уровне User есть явное разрешение/запрет - используем его
- Иначе проверяем Tenant
- Иначе проверяем Default
- Если нигде не указано - запрещено по умолчанию

### Примеры

| Default | Tenant | User | Итог | Почему |
|---------|--------|------|------|--------|
| ❌ deny | ✅ allow | ❌ deny | ❌ deny | User запретил |
| ❌ deny | - | ✅ allow | ✅ allow | User разрешил |
| ✅ allow | ❌ deny | - | ❌ deny | Tenant запретил |
| ✅ allow | - | - | ✅ allow | Default разрешил |

## Модели данных

### ToolInstance

Конкретное подключение к инструменту (например, "Jira Production", "Jira Staging").

```python
class ToolInstance:
    id: UUID
    tool_id: UUID              # FK на tools
    slug: str                  # Уникальный slug (например "jira-prod")
    name: str
    scope: str                 # default | tenant | user
    tenant_id: UUID | None     # Для tenant/user scope
    user_id: UUID | None       # Для user scope
    connection_config: dict    # URL, параметры (НЕ креды!)
    is_default: bool           # Дефолтный instance на этом scope
    is_active: bool
    health_status: str         # healthy | unhealthy | unknown
    last_health_check_at: datetime
```

### CredentialSet

Зашифрованные креды для ToolInstance.

```python
class CredentialSet:
    id: UUID
    tool_instance_id: UUID     # FK на tool_instances
    scope: str                 # tenant | user
    tenant_id: UUID | None
    user_id: UUID | None
    auth_type: str             # token | basic | oauth | api_key
    encrypted_payload: str     # Зашифрованный JSON
    is_active: bool
```

**Типы авторизации:**
- `token` - Bearer token (payload: `{"token": "..."}`)
- `basic` - Basic auth (payload: `{"username": "...", "password": "..."}`)
- `api_key` - API key (payload: `{"api_key": "..."}`)
- `oauth` - OAuth (payload зависит от провайдера)

### PermissionSet

Набор разрешений для tools и collections.

```python
class PermissionSet:
    id: UUID
    scope: str                 # default | tenant | user
    tenant_id: UUID | None
    user_id: UUID | None
    allowed_tools: list[str]   # ["rag.search", "jira.create"]
    denied_tools: list[str]
    allowed_collections: list[str]
    denied_collections: list[str]
```

## Agent Configuration

### tools_config

Структурированная конфигурация инструментов:

```json
[
    {
        "tool_slug": "rag.search",
        "required": true,
        "recommended": false
    },
    {
        "tool_slug": "jira.create",
        "required": false,
        "recommended": true
    }
]
```

- `required: true` - агент не запустится без этого инструмента
- `recommended: true` - агент может работать без него, но лучше с ним

### collections_config

Аналогично tools_config:

```json
[
    {
        "collection_slug": "tickets",
        "required": false,
        "recommended": true
    }
]
```

### policy

Политики выполнения агента:

```json
{
    "execution": {
        "max_steps": 20,
        "max_tool_calls_total": 50,
        "max_wall_time_ms": 300000,
        "tool_timeout_ms": 30000,
        "streaming_enabled": true
    },
    "retry": {
        "max_retries": 3,
        "backoff_strategy": "exponential",
        "retry_on": ["timeout", "rate_limit", "server_error"]
    },
    "output": {
        "citations_required": true,
        "max_response_tokens": 4000
    },
    "tool_execution": {
        "allow_parallel_tool_calls": false,
        "batch_size": 10
    },
    "security": {
        "allowed_models": ["gpt-4o", "gpt-4o-mini"],
        "block_sensitive_args": ["password", "secret"]
    }
}
```

### capabilities

Список возможностей агента для Router matching:

```json
["knowledge_base_search", "ticket_management", "code_generation"]
```

## AgentRouter

Pre-runtime маршрутизатор. Выполняется ДО tool-call loop.

### Обязанности

1. **Загрузить агента** по slug
2. **Резолвить permissions** для user/tenant
3. **Резолвить tools** - проверить доступность, найти instances, проверить креды
4. **Резолвить collections** - проверить доступность
5. **Проверить prerequisites** - все required tools/collections доступны?
6. **Определить режим** - full | partial | unavailable
7. **Создать ExecutionRequest** для Runtime
8. **Логировать решение** в routing_logs

### Режимы выполнения

- `full` - все required tools/collections доступны
- `partial` - часть недоступна, но агент поддерживает partial mode
- `unavailable` - критичные prerequisites отсутствуют

### Использование

```python
router = AgentRouter(session)

try:
    exec_request = await router.route(
        agent_slug="chat-rag",
        user_id=user_id,
        tenant_id=tenant_id,
        request_text="Найди документацию по API",
    )
    
    # Передаем в AgentRuntime
    async for event in runtime.run_with_request(exec_request, messages, ctx):
        handle_event(event)
        
except AgentUnavailableError as e:
    print(f"Cannot run agent: {e.missing.to_message()}")
```

## API Endpoints

### Tool Instances

```
GET    /api/v1/admin/tool-instances
POST   /api/v1/admin/tool-instances
GET    /api/v1/admin/tool-instances/{id}
PUT    /api/v1/admin/tool-instances/{id}
DELETE /api/v1/admin/tool-instances/{id}
POST   /api/v1/admin/tool-instances/{id}/health-check
```

### Credentials

```
GET    /api/v1/admin/credentials
POST   /api/v1/admin/credentials
GET    /api/v1/admin/credentials/{id}
PUT    /api/v1/admin/credentials/{id}
DELETE /api/v1/admin/credentials/{id}
```

### Permissions

```
GET    /api/v1/admin/permissions
POST   /api/v1/admin/permissions
GET    /api/v1/admin/permissions/effective?user_id=...&tenant_id=...
GET    /api/v1/admin/permissions/{id}
PUT    /api/v1/admin/permissions/{id}
DELETE /api/v1/admin/permissions/{id}
```

### Routing Logs

```
GET    /api/v1/admin/routing-logs
GET    /api/v1/admin/routing-logs/stats
GET    /api/v1/admin/routing-logs/{id}
GET    /api/v1/admin/routing-logs/run/{run_id}
```

## Конфигурация

### Environment Variables

```bash
# Мастер-ключ для шифрования credentials (обязателен в production)
CREDENTIALS_MASTER_KEY=your-secure-key-here

# Включить AgentRouter (по умолчанию выключен)
AGENT_ROUTER_ENABLED=true
```

## Миграция

Миграция `0041_agent_permissions_system.py` создает:

- Таблицу `tool_instances`
- Таблицу `credential_sets`
- Таблицу `permission_sets`
- Таблицу `routing_logs`
- Новые колонки в `agents`: `tools_config`, `collections_config`, `policy`, `capabilities`, `supports_partial_mode`

## Startup Hooks

При старте приложения:

1. `sync_tools_from_registry()` - синхронизирует ToolHandler из кода в таблицу `tools`
2. `_ensure_default_permission_set()` - создает default PermissionSet если его нет

## Безопасность

### Шифрование credentials

- Используется Fernet (AES-128-CBC)
- Мастер-ключ из `CREDENTIALS_MASTER_KEY`
- Если ключ не задан - используется fallback (НЕБЕЗОПАСНО для production!)

### Ротация ключей

```python
crypto = CryptoService()
new_encrypted = crypto.rotate_key(old_encrypted, new_master_key)
```

## Примеры

### Создание ToolInstance

```bash
curl -X POST /api/v1/admin/tool-instances \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "tool_slug": "jira.create",
    "slug": "jira-prod",
    "name": "Jira Production",
    "scope": "tenant",
    "tenant_id": "...",
    "connection_config": {
      "url": "https://jira.company.com",
      "project": "PROJ"
    },
    "is_default": true
  }'
```

### Создание Credentials

```bash
curl -X POST /api/v1/admin/credentials \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "tool_instance_id": "...",
    "auth_type": "token",
    "payload": {"token": "jira-api-token"},
    "scope": "tenant",
    "tenant_id": "..."
  }'
```

### Настройка Permissions

```bash
curl -X POST /api/v1/admin/permissions \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "scope": "tenant",
    "tenant_id": "...",
    "allowed_tools": ["rag.search", "jira.create"],
    "denied_tools": [],
    "allowed_collections": ["tickets"],
    "denied_collections": []
  }'
```

### Проверка Effective Permissions

```bash
curl "/api/v1/admin/permissions/effective?user_id=...&tenant_id=..." \
  -H "Authorization: Bearer $TOKEN"
```

Ответ:
```json
{
  "allowed_tools": ["rag.search", "jira.create"],
  "denied_tools": ["admin.delete"],
  "allowed_collections": ["tickets", "docs"],
  "denied_collections": []
}
```
