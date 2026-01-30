# Модель данных

## Основные сущности

### Users & Tenants

```
┌─────────────┐       ┌─────────────┐
│   Tenant    │◄──────│    User     │
├─────────────┤       ├─────────────┤
│ id          │       │ id          │
│ name        │       │ login       │
│ description │       │ email       │
│ is_active   │       │ role        │
│ ocr         │       │ tenant_id   │
│ layout      │       │ is_active   │
└─────────────┘       └─────────────┘
```

### Agents & Prompts

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Prompt    │◄──────│    Agent    │──────►│   Policy    │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ id          │       │ id          │       │ id          │
│ slug        │       │ slug        │       │ name        │
│ name        │       │ name        │       │ max_steps   │
│ type        │       │ system_     │       │ max_tokens  │
│ template    │       │ prompt_slug │       │ timeout_ms  │
│ version     │       │ baseline_   │       │ is_active   │
│ status      │       │ prompt_id   │       └─────────────┘
└─────────────┘       │ policy_id   │
                      │ capabilities│
                      │ supports_   │
                      │ partial_mode│
                      └─────────────┘
                            │
                            ▼
                      ┌─────────────┐
                      │AgentBinding │
                      ├─────────────┤
                      │ agent_id    │
                      │ tool_id     │
                      │ tool_       │
                      │ instance_id │
                      │ credential_ │
                      │ strategy    │
                      │ required    │
                      └─────────────┘
```

### Tools & Instances

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│  ToolGroup  │◄──────│    Tool     │◄──────│ToolInstance │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ id          │       │ id          │       │ id          │
│ slug        │       │ slug        │       │ slug        │
│ name        │       │ name        │       │ name        │
│ description │       │ description │       │ tool_id     │
└─────────────┘       │ tool_group_ │       │ instance_   │
                      │ id          │       │ type        │
                      │ handler_    │       │ config      │
                      │ class       │       │ is_active   │
                      │ parameters  │       │ health_     │
                      └─────────────┘       │ status      │
                                            └─────────────┘
```

### Permissions & Credentials

```
┌─────────────────┐       ┌─────────────────┐
│  PermissionSet  │       │  CredentialSet  │
├─────────────────┤       ├─────────────────┤
│ id              │       │ id              │
│ scope           │       │ scope           │
│ tenant_id       │       │ tenant_id       │
│ user_id         │       │ user_id         │
│ instance_       │       │ tool_instance_  │
│ permissions     │       │ id              │
│ agent_          │       │ encrypted_      │
│ permissions     │       │ payload         │
└─────────────────┘       │ is_default      │
                          └─────────────────┘
```

### Collections

```
┌─────────────────┐       ┌─────────────────┐
│   Collection    │──────►│  ToolInstance   │
├─────────────────┤       └─────────────────┘
│ id              │
│ slug            │
│ name            │
│ tenant_id       │
│ tool_instance_  │
│ id              │
│ schema          │
│ embedding_      │
│ config          │
│ status          │
└─────────────────┘
```

### RAG Documents

```
┌─────────────────┐       ┌─────────────────┐
│   RagDocument   │──────►│   RagIngest     │
├─────────────────┤       ├─────────────────┤
│ id              │       │ id              │
│ tenant_id       │       │ document_id     │
│ filename        │       │ stage           │
│ file_key        │       │ status          │
│ content_hash    │       │ started_at      │
│ status          │       │ finished_at     │
│ tags            │       │ error           │
│ scope           │       │ metadata        │
└─────────────────┘       └─────────────────┘
```

### Chats

```
┌─────────────────┐       ┌─────────────────┐
│      Chat       │◄──────│    Message      │
├─────────────────┤       ├─────────────────┤
│ id              │       │ id              │
│ user_id         │       │ chat_id         │
│ agent_slug      │       │ role            │
│ title           │       │ content         │
│ created_at      │       │ tool_calls      │
└─────────────────┘       │ created_at      │
                          └─────────────────┘
```

## Scope-based сущности

Сущности с иерархией Default → Tenant → User:

| Сущность | Default | Tenant | User |
|----------|---------|--------|------|
| PermissionSet | ✅ | ✅ | ✅ |
| CredentialSet | ✅ | ✅ | ✅ |

## Enum значения

### PermissionScope
- `default` — глобальные настройки
- `tenant` — настройки департамента
- `user` — индивидуальные настройки

### PermissionValue
- `allowed` — разрешено
- `denied` — запрещено
- `undefined` — наследуется

### InstanceType
- `local` — локальный (коллекции)
- `http` — HTTP API
- `custom` — кастомный

### PromptType
- `system` — системный промпт
- `baseline` — baseline ограничения
- `user` — пользовательский

### PromptStatus
- `draft` — черновик
- `active` — активная версия
- `archived` — архив

### DocumentStatus
- `pending` — ожидает
- `processing` — обрабатывается
- `ready` — готов
- `failed` — ошибка
- `archived` — архив
