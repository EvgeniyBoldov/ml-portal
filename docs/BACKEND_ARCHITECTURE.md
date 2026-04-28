# Backend Architecture

## Runtime

Runtime использует MCP-compatible operation descriptor как контракт capabilities/discovery.

### Runtime Memory

Runtime memory собирается компонентами под конкретный запрос. Компонент не
должен отдавать весь свой storage в prompt: он возвращает bounded section с
selected items, budget, priority, selection reason и diagnostics.

Базовые секции:

- `conversation` — структурированная summary/open questions/entities/raw tail.
- `facts` — query-ranked user / department / company facts.
- `tool_ledger` / `agent_results` — in-turn runtime context.

Текущий `TurnMemory.summary` и `TurnMemory.retrieved_facts` остаются
backward-compatible projection до полного удаления legacy `WorkingMemory`.

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

### Trace-Pack v2 / Replay / Eval

- Trace-pack экспортируется в версии `runtime.trace_pack.v2`.
- Payload включает redacted prompt/tool/memory/policy/model/budget surfaces.
- Replay: `python -m app.runtime.replay path/to/trace_pack.json` (без side-effects по умолчанию).
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
