# Backend Architecture

## User Bearer authentication

`BearerAuthenticationService` authenticates both JWT access tokens and personal
API tokens. `get_current_user` also permits a web access-token cookie;
`get_bearer_user` requires the Authorization header for shadow and MCP.
Tenant middleware uses the same service and caches the principal for route
dependencies, so an opaque API token is never decoded as JWT.

Personal tokens have format `mlp_pat_<32-hex-id>.<43-character-secret>`.
The id is a public primary-key lookup; the secret contains 256 random bits.
Only SHA-256 of the complete token and a public prefix are stored. Comparison
uses constant-time digest comparison. Every request checks the active token,
expiry, active/non-deprecated owner and current active tenant memberships.
Tokens inherit the owner's current role/RBAC; there is no separate token-scope
permission system. Successful authentication updates `last_used_at` in a
dedicated transaction, without committing endpoint business changes.

Profile token CRUD uses services/repositories and the established `db_uow`
transaction dependency. Migration `0189` intentionally removes existing profile
tokens and the obsolete `api_keys` table. `X-API-Key`, the old key service and
`/api/v1/api-keys` routes are removed without fallback. Replacement tokens must
be created in the profile. Credential replacement is irreversible.

## System LLM Role Contracts

Response contracts for active runtime roles (Planner, Memory Preparer, Fact
Extractor, Fact Compactor and Synthesizer) are generated dynamically from
Pydantic models:

- **Source of truth**: Pydantic models (`PlannerStep` with nested `IterationProposal`,
  `_PreparationOutput`, `_LLMFactOutput`, `_CompactionOutput`) define the JSON
  schema for structured roles
- **Schema generation**: `build_response_contract()` in `app/services/system_llm_role_contracts.py` generates JSON Schema via `model_json_schema()`
- **Enrichment**: Schema is enriched with contract metadata (`x_when` for conditional fields, `oneOf` for discriminated unions)
- **Startup validation**: `validate_role_contracts()` runs on startup and blocks app launch if schema divergence detected
- **Format lock**: All built-in roles have `format_locked: true` — contracts are read-only in UI
- **Request assembly**: Shared structured calls send the compact generated schema
  once in `response_format.json_schema`; system prompts retain behavior rules and
  examples without a generated schema copy. On fallback to `json_object`, the
  same schema moves into the system prompt. Local Pydantic validation runs in
  either mode. File synthesis follows the same contract transport.

Root tool descriptors carry names/descriptions only: their argument models
already belong to the structured response schema. Role examples come only from
the configured database role; backend contracts add mechanics without another
set of demonstrations. Native agent tools carry operation schemas in `tools`;
plaintext agents carry them in one tools block, with collection cards listing
only operation names. Agents with tools keep the completion schema in their
prompt and validate it locally; LLM-only tasks use `response_format` with a
schema-free completion instruction. File synthesis replaces the text-output
section with its JSON delivery contract before compiling the prompt.

Prompt projections remove identical compatibility aliases (`description` versus
`answer`, `outputs` versus `structured_response`), preserving distinct legacy
values and the original persisted results. Planner receives goal once, brief
requirements once, selected run materials and one canonical `scope_context`.
Preflight retains conversation context but omits an echoed current message and
anchor text already represented in the dialogue. Inventories carry metadata;
tool instructions live in system/tool contracts. Schema correction keeps only
the latest failed answer and bounded validation feedback, without Pydantic's
copy of the rejected input (`LLM_SCHEMA_REPAIR_MAX_ERRORS`, default 12). Real
tool results and interaction history remain intact.

Migration `0197` compacts only the three audited verbose role profiles by exact
policy fingerprint. It preserves identity, examples, model and parameters,
backs up the previous policy in role extras, and skips customized profiles.
Downgrade restores only policies that have not subsequently been edited.

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

Документная LongMemory хранится в общем native HippoRAG корпусе и доступна
пользователям портала без фильтрации по user, tenant или ACL исходного
документа. Scope выбирает индекс общего корпуса и не является разрешением
доступа. Обычный RAG остаётся отдельным ACL-контуром. Текущий контракт,
индексация и поиск описаны в [архитектуре Memory](architecture/MEMORY.md).
Контекст чата и runtime trace также являются отдельными persistence surfaces.

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

### Document source metadata publication

RAG stages and LongMemory workers share `sources.meta` while publishing
independent artifacts and memory state. All mutations of an existing source's
metadata use the shared document-source metadata service. The publication
transaction locks rows in a fixed order: `RAGDocument`, then the current
`Source` row. It reads `Source` with `SELECT FOR UPDATE` and refreshes the ORM
identity-map value before merging, so a task cannot publish a stale metadata
snapshot after another worker commits. A mutation may update only its owned
metadata path and must preserve unrelated and legacy fields.

Perform S3, model, HTTP and other external work before acquiring publication
locks. Keep the locked section short and do not commit in the shared helper;
the calling workflow owns the transaction. For the RAG chunk stage, canonical
chunk rows, the chunk artifact pointer/count and successful stage status are
committed together. Verify the active ingest or LongMemory generation while
holding the document lock before publishing. Multi-document operations acquire
document locks in stable ID order. RAG status mutations use the same
`RAGDocument`-before-status-row order. Redis events and document collection
status projections are dispatched only after commit; the projection worker
locks collections and recomputes from committed documents. Failed projection
refreshes are retried by Celery up to three times. The after-commit broker
dispatch and individual Redis event deliveries are best effort; dispatch
failures are logged and do not roll back committed RAG state. Collection tenant
reassignment locks the collection first, then affected documents and sources in
stable ID order, before changing membership and tenant IDs. Collection API
responses compute a fresh status snapshot, so the persisted projection may lag
if its best-effort post-commit refresh cannot be dispatched. Collection API,
catalog and admin status reads compute a fresh snapshot. This prevents future
lost updates; it does not recreate artifact pointers already lost from
metadata. Such repair requires verifying a durable stage result and the
referenced object-storage artifact.

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
