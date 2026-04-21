# Модель данных

## Основные сущности

### Users & Tenants

`Tenant` здесь лучше читать как организационный контур, например отдел или подразделение, а не как жёсткую границу изоляции для общих инструментов и инстансов.

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
┌─────────────┐       ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Prompt    │◄──────│    Agent    │──────►│   Policy    │──────►│PolicyVersion│
├─────────────┤       ├─────────────┤       ├─────────────┤       ├─────────────┤
│ id          │       │ id          │       │ id          │       │ id          │
│ slug        │       │ slug        │       │ slug        │       │ policy_id   │
│ name        │       │ name        │       │ name        │       │ version     │
│ type        │       │ system_     │       │ description │       │ status      │
│ template    │       │ prompt_slug │       │ recommended_│       │ max_steps   │
│ version     │       │ baseline_   │       │ version_id  │       │ max_tool_   │
│ status      │       │ prompt_id   │       │ is_active   │       │ calls       │
└─────────────┘       │ policy_id   │       └─────────────┘       │ max_wall_   │
                      │ capabilities│                              │ time_ms     │
                      │ supports_   │                              │ budget_     │
                      │ partial_mode│                              │ tokens      │
                      └─────────────┘                              │ notes       │
                            │                                      │ parent_     │
                            ▼                                      │ version_id  │
                      ┌─────────────┐                              └─────────────┘
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

**Policy Versioning Pattern:**
- `Policy` (container) — метаданные: slug, name, description
- `PolicyVersion` — версионированные данные: лимиты, таймауты, бюджеты
- `recommended_version_id` — указывает на версию для использования по умолчанию
- Статусы версий: `draft` (черновик), `active` (активная), `inactive` (неактивная)

### Tools & Instances

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Tool      │       │  ToolDomain │       │ToolInstance │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ id          │       │ id          │       │ id          │
│ slug        │       │ slug        │       │ slug        │
│ name        │       │ name        │       │ name        │
│ domains[]   │       │ label       │       │ tool_id     │
└─────────────┘       │ description │       │ instance_   │
                      └─────────────┘       │ type        │
                                            │ config      │
                                            │ is_active   │
                                            │ health_     │
                                            │ status      │
                                            └─────────────┘
```

### Permissions & Credentials

PermissionSet and CredentialSet are still scope-aware, but scope is mainly used for control and rollout, not for forcing every tool/instance to be tenant-exclusive.

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
│ data_instance_id│
│ fields/schema   │
│ vector_config   │
│ status          │
└─────────────────┘
```

- `collections.data_instance_id` — обязательный FK на `tool_instances.id`.
- Binding через `config.bindings` удалён из runtime-контракта.
- Источник связи `Collection ↔ DataInstance` только реляционный FK.

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

### PolicyVersionStatus
- `draft` — черновик, можно редактировать
- `active` — активная версия (только одна на policy)
- `inactive` — деактивирована, нельзя использовать

### DocumentStatus
- `pending` — ожидает
- `processing` — обрабатывается
- `ready` — готов
- `failed` — ошибка
- `archived` — архив
