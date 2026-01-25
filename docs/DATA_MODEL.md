# Data Model

Описание ключевых сущностей системы и их взаимосвязей.

## Core Entities

### User (Пользователь)
```python
class Users:
    id: UUID
    login: str
    password_hash: str
    email: str | None
    role: str  # admin | tenant_admin | user
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

**Роли:**
- `admin` — системный администратор (доступ ко всему)
- `tenant_admin` — администратор департамента (управление своим тенантом)
- `user` — обычный пользователь (использование агентов)

### Tenant (Департамент)
```python
class Tenants:
    id: UUID
    name: str  # "Сетевой отдел", "Виртуализация"
    description: str | None
    is_active: bool
    embedding_model_alias: str | None
    ocr: bool
    layout: bool
    created_at: datetime
    updated_at: datetime
```

**Связь с пользователями:**
```python
class UserTenants:
    id: UUID
    user_id: UUID
    tenant_id: UUID
    is_default: bool  # дефолтный тенант для пользователя
```

Пользователь может быть в нескольких тенантах, но один из них дефолтный.

---

## AI Components

### Model (Модель)
```python
class Model:
    id: UUID
    alias: str  # "gpt-4o", "text-embedding-3-large"
    name: str
    type: str  # embedding | rerank | llm
    provider: str  # openai | local | anthropic
    status: str  # available | unavailable
    default_for_type: bool
    extra_config: dict  # {"vector_dim": 1536, "max_tokens": 8192}
    created_at: datetime
    updated_at: datetime
```

### Prompt (Промпт)
```python
class Prompt:
    id: UUID
    slug: str  # "chat.rag.system", "agent.netbox"
    name: str
    description: str | None
    template: str  # Jinja2 template
    input_variables: list[str]  # ["query", "context"]
    generation_config: dict  # {"temperature": 0.2}
    
    # Versioning
    version: int
    status: str  # draft | active | archived
    parent_version_id: UUID | None
    
    # Type
    type: str  # prompt | baseline
    
    created_at: datetime
    updated_at: datetime
```

**Типы промптов:**
- `prompt` — системный промпт с инструкциями для агента
- `baseline` — ограничения и запреты (что агент НЕ должен делать)

**Версионирование:**
- Только один `active` промпт на slug
- `draft` можно редактировать
- `archived` только для истории

### Tool (Инструмент)
```python
class Tool:
    id: UUID
    slug: str  # "rag.search", "jira.create", "netbox.get_device"
    name: str
    description: str | None
    type: str  # api | function | database
    input_schema: dict  # JSON Schema
    output_schema: dict | None
    config: dict  # execution config (НЕ креды!)
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

**Важно:** Tool — это определение инструмента в коде. Конкретные подключения хранятся в ToolInstance.

### Agent (Агент)
```python
class Agent:
    id: UUID
    slug: str  # "chat-rag", "netbox-assistant"
    name: str
    description: str | None
    
    # Prompts
    system_prompt_slug: str  # FK to Prompt (type=prompt)
    baseline_prompt_slug: str | None  # FK to Prompt (type=baseline)
    
    # Tools & Collections
    tools_config: list[dict]
    # [{"tool_slug": "rag.search", "required": true, "recommended": false}]
    
    collections_config: list[dict]
    # [{"collection_slug": "tickets", "required": false, "recommended": true}]
    
    # Policy
    policy: dict
    # {
    #   "execution": {"max_steps": 20, "max_tool_calls_total": 50},
    #   "retry": {"max_retries": 3},
    #   "output": {"citations_required": true}
    # }
    
    # Capabilities
    capabilities: list[str]  # ["knowledge_base_search", "ticket_management"]
    supports_partial_mode: bool
    
    generation_config: dict
    is_active: bool
    enable_logging: bool
    
    created_at: datetime
    updated_at: datetime
```

**Baseline merge:**
1. Загружаем default baseline (из общих настроек)
2. Если у агента есть `baseline_prompt_slug`, мержим с приоритетом агента
3. Результат используется в system prompt

---

## Integrations

### ToolInstance (Инстанс инструмента)
```python
class ToolInstance:
    id: UUID
    tool_id: UUID  # FK to Tool
    slug: str  # "jira-prod", "netbox-main"
    name: str
    
    # Scope (НЕ используется для инстансов, они глобальные)
    # Оставлено для обратной совместимости
    scope: str  # default | tenant | user
    tenant_id: UUID | None
    user_id: UUID | None
    
    connection_config: dict  # {"url": "https://jira.company.com", "project": "PROJ"}
    is_default: bool
    is_active: bool
    
    # Health check
    health_status: str  # healthy | unhealthy | unknown
    last_health_check_at: datetime
    
    created_at: datetime
    updated_at: datetime
```

**Важно:** Инстансы глобальные, scope не используется. Креды привязываются к инстансу на разных уровнях.

### CredentialSet (Креды)
```python
class CredentialSet:
    id: UUID
    tool_instance_id: UUID  # FK to ToolInstance
    
    # Scope
    scope: str  # default | tenant | user
    tenant_id: UUID | None
    user_id: UUID | None
    
    # Auth
    auth_type: str  # token | basic | oauth | api_key
    encrypted_payload: str  # зашифрованный JSON
    
    is_active: bool
    is_default: bool  # дефолтный для scope (если у юзера 2+ сета)
    
    created_at: datetime
    updated_at: datetime
```

**Credential resolution:**
1. Ищем креды user scope для инстанса
2. Если нет → tenant scope
3. Если нет → default scope
4. Если нет → ошибка "credentials not found"

**Multiple credentials:**
Если у пользователя 2+ credential set для одного инстанса, используется `is_default=true`.

### Collection (Коллекция)
```python
class Collection:
    id: UUID
    tenant_id: UUID  # FK to Tenant
    slug: str  # "tickets", "devices", "docs"
    name: str
    description: str | None
    
    # Schema
    fields: list[dict]
    # [
    #   {"name": "title", "type": "text", "required": true, "search_modes": ["exact", "like"]},
    #   {"name": "description", "type": "text", "search_modes": ["like", "vector"]}
    # ]
    
    table_name: str  # динамическая таблица в БД
    row_count: int
    
    # Vector search
    vector_config: dict | None
    qdrant_collection_name: str | None
    total_rows: int
    vectorized_rows: int
    total_chunks: int
    failed_rows: int
    
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

**Доступ к коллекциям:**
Определяется через PermissionSet. Коллекция привязана к tenant, но может быть доступна другим тенантам через политики.

---

## Permissions

### PermissionSet (Политики доступа)
```python
class PermissionSet:
    id: UUID
    
    # Scope
    scope: str  # default | tenant | user
    tenant_id: UUID | None
    user_id: UUID | None
    
    # Permissions
    allowed_tools: list[str]  # ["rag.search", "jira.create"]
    denied_tools: list[str]
    allowed_collections: list[str]  # ["tickets", "devices"]
    denied_collections: list[str]
    
    created_at: datetime
    updated_at: datetime
```

**Permission resolution:**
1. Загружаем user permissions
2. Мержим с tenant permissions
3. Мержим с default permissions
4. Приоритет: User > Tenant > Default

**Логика merge:**
- Если на уровне User есть явное `allowed` или `denied` → используем его
- Иначе проверяем Tenant
- Иначе проверяем Default
- Если нигде не указано → `denied` по умолчанию

**Автоматическое добавление:**
При создании нового Tool или Collection автоматически создается запись в default PermissionSet со статусом `denied`.

---

## Logging

### AgentRun (Запуск агента)
```python
class AgentRun:
    id: UUID
    agent_id: UUID
    user_id: UUID
    tenant_id: UUID
    chat_id: UUID | None
    
    status: str  # running | completed | failed | cancelled
    
    # Input/Output
    input_text: str
    output_text: str | None
    
    # Metrics
    total_steps: int
    total_tool_calls: int
    duration_ms: int
    tokens_used: int
    
    # Error
    error_message: str | None
    
    created_at: datetime
    updated_at: datetime
```

### AgentRunStep (Шаг агента)
```python
class AgentRunStep:
    id: UUID
    agent_run_id: UUID
    step_number: int
    
    step_type: str  # llm_call | tool_call | final_answer
    
    # Tool call
    tool_slug: str | None
    tool_input: dict | None
    tool_output: dict | None
    
    # LLM call
    llm_input: str | None
    llm_output: str | None
    
    status: str  # running | completed | failed
    duration_ms: int
    
    created_at: datetime
```

### AuditLog (Аудит)
```python
class AuditLog:
    id: UUID
    
    # Request
    endpoint: str  # "/api/v1/admin/agents"
    method: str  # POST | PUT | DELETE
    user_id: UUID | None
    tenant_id: UUID | None
    
    # Payload
    request_data: dict
    response_data: dict | None
    
    # Metrics
    status_code: int
    duration_ms: int
    
    # Error
    error_message: str | None
    
    created_at: datetime
```

**Retention:**
- `agent_runs` — 30 дней
- `audit_logs` — 90 дней

---

## Relationships

```
User ──< UserTenants >── Tenant
User ──< CredentialSet (scope=user)
Tenant ──< CredentialSet (scope=tenant)
Tenant ──< Collection

Agent ──> Prompt (system_prompt_slug)
Agent ──> Prompt (baseline_prompt_slug)

Tool ──< ToolInstance
ToolInstance ──< CredentialSet

PermissionSet (scope=default/tenant/user)
  ├─ allowed_tools: [Tool.slug]
  └─ allowed_collections: [Collection.slug]

AgentRun ──> Agent
AgentRun ──> User
AgentRun ──> Tenant
AgentRun ──< AgentRunStep
```

---

## Scope Hierarchy

```
┌─────────────────────────────────────┐
│         DEFAULT (Global)            │
│  - Default permissions              │
│  - Default baseline                 │
│  - Default credentials              │
└─────────────────────────────────────┘
              ▼
┌─────────────────────────────────────┐
│         TENANT (Department)         │
│  - Tenant permissions               │
│  - Tenant credentials               │
│  - Tenant collections               │
└─────────────────────────────────────┘
              ▼
┌─────────────────────────────────────┐
│         USER (Individual)           │
│  - User permissions                 │
│  - User credentials                 │
└─────────────────────────────────────┘
```

**Priority:** User > Tenant > Default
