# Backend Architecture

## System LLM Role Contracts

Response contracts for active runtime roles (Planner, Memory Preparer, Fact
Extractor, Fact Compactor and Synthesizer) are generated dynamically from
Pydantic models:

- **Source of truth**: Pydantic models (`IterationProposal`,
  `_PreparationOutput`, `_LLMFactOutput`, `_CompactionOutput`) define the JSON
  schema for structured roles
- **Schema generation**: `build_response_contract()` in `app/services/system_llm_role_contracts.py` generates JSON Schema via `model_json_schema()`
- **Enrichment**: Schema is enriched with contract metadata (`x_when` for conditional fields, `oneOf` for discriminated unions)
- **Startup validation**: `validate_role_contracts()` runs on startup and blocks app launch if schema divergence detected
- **Format lock**: All built-in roles have `format_locked: true` — contracts are read-only in UI

### Contract Types

- **JSON contracts**: Used by Planner, Memory Preparer, Fact Extractor and
  Fact Compactor — render as structured form fields
- **Plain text contracts**: Used by Synthesizer — render as criteria/forbidden lists
- **Markdown contracts**: Reserved for future roles

## Runtime

Runtime использует MCP-compatible tool descriptor как контракт capabilities/discovery.

### Runtime Memory

Контекст одного runtime turn собирается bounded-секциями через
`MemoryBuilder`; он включает подтверждённые user/tenant facts и данные текущего
turn. После ответа диалоговые кандидаты проходят асинхронные
`FactExtractor -> FactCompactor -> FactReconciler`.

Документная Semantic Memory хранится отдельно в source-backed
`MemoryItem`/`MemoryClaim` и читается через ACL-aware `memory.search`. Её
извлечение, публикация, виртуальные коллекции и границы доступа описаны в
[архитектуре Memory](architecture/MEMORY.md). Контекст чата и runtime trace
также являются отдельными persistence surfaces.

### MCP runtime flags

Дополнительные runtime-флаги операций задаются через расширение JSON Schema `x-runtime`.

Подробный контракт и правила валидации: [MCP_RUNTIME_FLAGS.md](./MCP_RUNTIME_FLAGS.md).

### Collection/DataInstance Binding

- Runtime `DataInstanceResolver` использует только `collections.data_instance_id` (FK).
- Legacy binding через `tool_instances.config.bindings` больше не является источником истины.

### Collection Runtime Readiness Contract

Runtime и admin diagnostics используют единый readiness DTO (`CollectionRuntimeReadiness`):

- `status`: `ready|degraded_missing_credentials|degraded_provider_unhealthy|schema_stale|no_operations`
- `schema_status` + `schema_freshness`
- `provider_health` + `credential_status`
- `available_operations` + `missing_requirements`
- `current_version*` + `last_sync_at`

Для planner/runtime card это устраняет "guessing" по коллекциям: в prompt идут только
каноничные readiness/operations/table preview данные.

### Runtime Eval

- Eval harness (`tests/eval`) оценивает runtime по dimension scores:
  `tool_choice`, `memory_selection`, `grounding`, `terminal_behavior`, `safety`.

### Admin Diagnostics Endpoints

Дополнительно к capability-graph/HITL/trace-pack:

- `GET /admin/collections/{collection_id}/runtime-readiness`
- `GET /admin/agent-runs/{run_id}/diagnostics-summary`

Эти endpoints предназначены для объяснения "почему не сработало" без чтения container logs.

### Tenant Semantics

Tenant в локальном корпоративном инстансе означает отдел/рабочую область.
Это не hard security boundary как во внешнем SaaS. Sharing между отделами
разрешается policy/RBAC и должен быть видим в trace/admin diagnostics.
