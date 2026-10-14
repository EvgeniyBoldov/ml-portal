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

## Embedding model and vector-index contract

`Model.embedding_dimensions`, `max_input_tokens`, `model_version` and
`vector_normalized` are canonical characteristics. Provider discovery uses the
same metadata service in the admin UI and embedding registration; missing
characteristics require discovery or explicit manual configuration. Vector
creation never substitutes a guessed dimension such as 384.

`VectorIndexService` resolves one encoder configuration and adapter for each
operation. Provisioning, document indexing, table vectorization and collection
search use that resolver. The physical Qdrant name is
`vi_<collection-namespace-hash>_<embedding-fingerprint>`.
`Collection.qdrant_collection_name` is the stable namespace, not necessarily a
physical Qdrant collection. Each fingerprint includes model identity, weights
version/revision, dimension, input limit, normalization and input policy. Health,
latency and default-model ordering do not change the vector-space identity.

Different encoders, including encoders of equal dimension, have separate
indexes. Changing encoder characteristics creates a new generation and retains
previous indexes. Document embedding artifacts, Redis idempotency and index
status carry the same fingerprint; incompatible artifacts must be regenerated
from canonical chunks. Table vectorization checks identities before choosing
pending rows and performs full revectorization when the selected spaces change.

Long document chunks and queries use conservative UTF-8 byte-bounded segments
within the selected encoder's input limit, reserving special tokens through
`EMB_INPUT_TOKEN_RESERVE`. Segment vectors are averaged and normalized to one
vector per original chunk/query. This preserves the original payload text and
avoids silently cutting its suffix. Input-policy changes invalidate embedding
artifacts. Provider batches are checked for count, dimension and finite values
before indexing. Table field extraction retains its existing character-length
limit and chunk configuration.

Search embeds each query once per selected space. Results across encoders use
reciprocal rank fusion (`MULTI_EMBEDDING_RRF_K`) before reranking, because raw
similarity scales cannot be compared between encoders. Existing ACL and payload
filters remain in the search path. Legacy indexes are read only when a pinned
encoder configuration, point alias/version and physical dimension match;
unknown provenance requires reindexing. New generations become searchable as
points are written; a full reindex is needed for complete coverage.

The batch reindex endpoint detects missing/changed fingerprints, including
legacy indexes and failed index stages. It also backfills a newly selected
encoder when canonical chunks are ready but its index stage is absent/pending. Running stages and archived documents
are excluded. Without an explicit model alias it processes currently selected
global/tenant encoders; unknown dimensions must be verified first. Dry-run
reports candidates without dispatching workers. Audit and deletion recognize
all physical generations owned by a collection namespace.

HippoRAG owns its SQLite corpus and native vector/graph indexes on its volume;
it does not use these Qdrant generations. Its encoder selection remains
`use_for_long_memory`, independently of the RAG global/tenant defaults. Native
encoder configuration changes use the existing durable rebuild workflow.
