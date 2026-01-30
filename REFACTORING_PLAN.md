# План рефакторинга ML Portal

## 1. Backend — Разбиение больших сервисов

### 1.1 chat_stream_service.py (20KB → 3 файла)

**Текущее состояние:**
- 11 методов, хорошо структурирован, но смешаны разные ответственности

**План:**
```
services/
├── chat_stream_service.py (основной, 8KB)
│   ├── ChatStreamService
│   │   ├── send_message_stream()
│   │   ├── verify_chat_access()
│   │   ├── load_chat_context()
│   │   └── _map_runtime_event()
│   └── _run_with_router()
│
├── chat_title_generator.py (2KB)
│   └── ChatTitleGenerator
│       └── generate_chat_title()
│
└── chat_idempotency.py (2KB)
    └── ChatIdempotencyManager
        ├── check_idempotency()
        └── store_idempotency()
```

**Приоритет:** 🟡 Medium (не критично, но улучшит читаемость)

---

### 1.2 collection_service.py (24KB → 3 файла)

**Текущее состояние:**
- 15 методов + 4 helper, смешаны CRUD, SQL генерация, поиск

**План:**
```
services/
├── collection_service.py (CRUD, 8KB)
│   └── CollectionService
│       ├── create_collection()
│       ├── delete_collection()
│       ├── get_by_id()
│       ├── get_by_slug()
│       └── list_collections()
│
├── collection_table_builder.py (6KB)
│   └── CollectionTableBuilder
│       ├── _build_create_table_sql()
│       ├── _build_indexes_sql()
│       ├── _validate_slug()
│       ├── _validate_fields()
│       └── _generate_table_name()
│
└── collection_search_service.py (8KB)
    └── CollectionSearchService
        ├── search()
        ├── count()
        ├── insert_rows()
        └── delete_rows()
```

**Приоритет:** 🔴 High (смешанная ответственность)

---

### 1.3 rag_status_manager.py (23KB → 2 файла)

**Текущее состояние:**
- 11 методов, хорошо структурирован, но StatusGraph логика смешана

**План:**
```
services/
├── rag_status_manager.py (основной, 15KB)
│   └── RAGStatusManager
│       ├── initialize_document_statuses()
│       ├── transition_stage()
│       ├── start_ingest()
│       ├── retry_stage()
│       ├── archive_document()
│       └── _cascade_reset_downstream()
│
└── rag_status_graph.py (8KB)
    └── StatusGraph
        ├── get_document_status()
        ├── _update_aggregate_status()
        └── _get_target_models()
```

**Приоритет:** 🟡 Medium (хорошо структурирован, но можно улучшить)

---

### 1.4 rag_search_service.py (17KB → 2 файла)

**Текущее состояние:**
- 6 методов, но rerank логика смешана с поиском

**План:**
```
services/
├── rag_search_service.py (основной, 10KB)
│   └── RagSearchService
│       ├── search()
│       ├── _get_tenant_models()
│       └── _enrich_with_*()
│
└── rag_reranker.py (7KB)
    └── RagReranker
        ├── _rerank_results()
        ├── _normalize_scores()
        └── _rrf_merge()
```

**Приоритет:** 🟡 Medium (логика отделима, но работает)

---

## 2. Frontend — Shared компоненты

### 2.1 Дубликаты и конфликты

✅ **ВЫПОЛНЕНО:**
- Удалён `shared/components/PermissionsEditor` (дублировал RbacRulesEditor)
- Удалён `shared/components/CredentialSetsEditor` (не использовался)
- Удалена директория `shared/components/` (пусто)

**Статус:** ✅ Завершено

---

### 2.2 Типизация (146 `any` в 53 файлах)

**Топ проблемные файлы:**
- `shared/ui/DataTable/DataTable.tsx` — 12 `any`
- `domains/admin/pages/TenantEditorPage.tsx` — 7 `any`
- `domains/chat/contexts/ChatContext.tsx` — 7 `any`
- `domains/admin/pages/AgentEditorPage.tsx` — 6 `any`
- `shared/api/tools.ts` — 6 `any`

**План:**
```
Фаза 1: DataTable (критично)
├── Заменить Row = any на Row = Record<string, unknown>
├── Заменить Column = any на Column<T>
└── Добавить generics: DataTable<T>

Фаза 2: Admin pages (важно)
├── TenantEditorPage: заменить на TenantFormData
├── AgentEditorPage: заменить на AgentFormData
└── PromptEditorPage: заменить на PromptFormData

Фаза 3: API layer (важно)
├── tools.ts: добавить Tool, ToolResponse типы
├── prompts.ts: добавить Prompt, PromptVersion типы
└── admin.ts: добавить типы для каждого endpoint

Фаза 4: Contexts (medium)
└── ChatContext: заменить на ChatContextType
```

**Приоритет:** 🟡 Medium (техдолг, но не критично)

---

### 2.3 console.log и production код

**Найдено:**
- `shared/api/http.ts` — 1 console.log
- `shared/ui/DataTable/DataTable.tsx` — 1 console.log

**План:**
```
Шаг 1: Удалить console.log
├── http.ts
└── DataTable.tsx

Шаг 2: Добавить ESLint rule
└── "no-console": ["error", { allow: ["warn", "error"] }]

Шаг 3: Pre-commit hook
└── Запретить console.log в коммитах
```

**Приоритет:** 🔴 High (production code)

---

## 3. Backend — Transaction Management (flush в RAG)

### 3.1 Обновить документацию

**Проблема:** В RAG pipeline используется flush() вместо commit() из-за откатов.

**План:**
```
Файл: docs/backend/MIGRATIONS.md

Добавить раздел "Celery Tasks и flush/commit":

### Celery Tasks и flush/commit

В Celery воркерах используется flush() для промежуточных операций:

✅ Правильно:
async with worker_transaction(session, "task_name"):
    await update_status(...)
    await session.flush()  # Для SSE событий
    result = await process(...)
    # commit() автоматически при выходе

❌ Неправильно:
await session.commit()  # Может привести к откатам при ошибке

Причина: если задача упадёт после commit(), откат невозможен.
```

**Приоритет:** 🟡 Medium (документация)

---

## 4. Repository Pattern — commit() в репозиториях

### 4.1 Исправить нарушения

**Найдено:**
- `agent_repository.py:15,32,38` — commit() в create/update/delete
- `tool_repository.py:15,32,38` — commit() в create/update/delete

**План:**
```
Шаг 1: Заменить commit() на flush()
├── agent_repository.py
└── tool_repository.py

Шаг 2: Проверить все роутеры
├── Убедиться, что они делают commit() после сервиса
└── Добавить await session.commit() где нужно

Шаг 3: Добавить в docs/backend/RULES.md
└── Раздел "Repository Pattern" с примерами
```

**Приоритет:** 🔴 High (нарушение паттерна)

---

## 5. Baseline — отдельная сущность

### 5.1 Архитектура

**План:**
```
Модели:
├── Baseline (новая)
│   ├── id, slug, template
│   ├── version (draft/active/archived)
│   ├── scope (default/tenant/user)
│   ├── tenant_id (опционально)
│   ├── user_id (опционально)
│   └── created_at, updated_at
│
└── Prompt (изменить)
    ├── baseline_id (FK, опционально)
    └── custom_baseline (override, опционально)

Сервис:
├── BaselineService
│   ├── create_baseline()
│   ├── get_baseline()
│   ├── list_baselines()
│   ├── activate_version()
│   └── merge_baselines() — static method
│
└── PromptService (изменить)
    └── get_effective_baseline() — использует merge_baselines()

API:
├── POST /admin/baselines
├── GET /admin/baselines
├── GET /admin/baselines/{slug}
├── PATCH /admin/baselines/{slug}
└── DELETE /admin/baselines/{slug}

Frontend:
├── /admin/baselines — список
├── /admin/baselines/new — создание
├── /admin/baselines/{slug} — редактирование
└── Prompt Editor — выбор baseline через Select
```

**Приоритет:** 🟡 Medium (улучшение архитектуры)

---

## 6. IDE + Plugin + Proxy

### 6.1 Новые компоненты

**План:**
```
Backend:
├── models/api_key.py (новая)
│   └── APIKey (user_id, key_hash, scopes, rate_limit)
│
├── services/ide_auth_service.py (новая)
│   └── IDEAuthService
│       ├── create_api_key()
│       ├── validate_api_key()
│       └── revoke_api_key()
│
├── services/policy_enforcer.py (новая)
│   └── PolicyEnforcer
│       ├── check_model_allowed()
│       ├── check_rate_limit()
│       └── inject_system_prompt()
│
└── api/v1/ide/ (новая)
    ├── router.py
    ├── auth.py — API key endpoints
    └── chat.py — /ide/chat/completions

Frontend (IDE Plugin):
├── src/api/client.ts — HTTP client с API key
├── src/hooks/useChat.ts — hook для чата
└── src/components/ChatPanel.tsx — UI
```

**Приоритет:** 🟢 Low (новая функциональность, не срочно)

---

## Итоговый приоритет

### 🔴 High (срочно)
1. `collection_service.py` — разбить на 3 файла
2. Удалить `console.log` из production кода
3. Исправить `commit()` в репозиториях (agent, tool)
4. Консолидировать shared компоненты (PermissionsEditor, CredentialSetsEditor)

### 🟡 Medium (важно, но не срочно)
1. `chat_stream_service.py` — разбить на 3 файла
2. `rag_status_manager.py` — вынести StatusGraph
3. `rag_search_service.py` — вынести Reranker
4. Типизация (заменить `any` на конкретные типы)
5. Baseline — отдельная сущность

### 🟢 Low (nice-to-have)
1. IDE + Plugin + Proxy архитектура
2. Дополнить UI компоненты (Stepper, Tooltip, Combobox)
3. Storybook для shared/ui

---

## Метрики успеха

- [ ] Все файлы < 20KB (кроме моделей и миграций)
- [ ] Нет `any` в критичных файлах (DataTable, API, Admin pages)
- [ ] Нет `console.log` в production коде
- [ ] Все репозитории используют только `flush()`
- [ ] Нет дубликатов компонентов
- [ ] Baseline — отдельная сущность с версионированием
