# Runtime V3 Map

## Flow

`RuntimePipeline` coordinates one turn and emits canonical runtime events.

1. `pipeline.py` receives `PipelineRequest`.
2. `assembler.py` builds per-turn dependencies (`PipelineAssembler`).
3. Stages execute in order:
   - `orchestrator.py` / `plan_store.py` — deterministic plan control and task lifecycle
   - `planner/*` — planner contract and immutable iteration generation
   - iteration terminal (`planner` or `synthesis`) — next decision or response
4. State is persisted through ports (`ports.py`) and adapters (services/repos).
5. Output events are normalized in `events.py` and wrapped with envelope (`envelope.py`).

## Responsibility Split

- `pipeline.py`: orchestration only (stage order, terminal handling and continuation entry points).
- `assembler.py`: dependency wiring, cached services, stage factories.
- `platform_config.py`: load platform snapshot (`policy`, routable agents, config degradation).
- `orchestrator_contracts.py`: planner/orchestrator/task/result contracts.
- `plan_store.py`: transactional iteration state, dependencies, terminal claims and attempts.
- `turn_state.py`: current-turn memory/context DTO; it is not the persisted plan.
- `synthesis_context.py`: redacted agent responses, statuses, diagnostics and runtime attachments; only explicitly excluded tasks are omitted.
- `synthesizer.py`: final answer synthesis at the terminal iteration.

Task lifecycle is runtime-owned. `ready` is derived from dependencies;
retryable failures remain `waiting_retry` until `next_retry_at`, failed
dependencies propagate to `blocked`, and an unsuccessful task always routes
the completed iteration back to planner. Synthesis runs only when the current
iteration completed successfully; it receives successful reports, explicitly
all non-excluded responses and current user-visible limitations. A synthesis
provider/context failure is a terminal plan failure after the synthesizer's
own retry policy is exhausted; it is not presented to the planner as a fake
task result or a mutable rewrite of the terminal iteration.

## Ports and Adapters

Runtime code should depend on `ports.py` contracts, not concrete DB/HTTP classes.

- Ports: run store, memory repo, planner, synthesizer, config loader.
- Adapters: `app.services.*`, `app.repositories.*`, and external clients.

## Memory ownership

`MemoryBuilder` is the turn-start assembly boundary. It uses
`MemoryService`/`FactStore` to create a bounded `MemorySnapshot` containing
confirmed active user and tenant facts, then combines it with bounded tool,
agent-result, attachment and collection sections. It does not load the
conversation summary into the active component registry.

Durable project memory is read on demand through ACL-aware `MemorySearchService`
and the canonical `memory.search` operation available to planner and agents.
TurnPreflight starts with mechanical identity lookup and may request a bounded
recall followed by a second routing decision. `MemoryPreparer`/`MemoryRecall`
remain separate legacy helpers; they are not the mandatory active root route.
Document memory is extracted during ingestion and published through review.

Each runtime reader records its own actual input as a canonical
`status(stage=memory_context_used)` snapshot. Sandbox inspectors combine that
snapshot with successful memory tool results owned by that reader; memory
writeback candidates remain a separate projection.

Terminal writeback is owned by `MemoryWriter` and normally runs in the Celery
`finalize_memory` task after the answer. The writer pipeline is
`FactExtractor -> FactCompactor -> FactReconciler`; only evidence-backed,
deduplicated and reconciled facts become active. The task uses a fresh worker
session and never passes a live session/logger through Celery.

Rule of thumb:
- If logic is domain/runtime behavior -> keep in `app/runtime/*`.
- If logic is I/O, SQL, external API, or framework integration -> adapter layer.

## Prompt Ownership (Current)

| Concern | Current source | Where to change |
|---|---|---|
| Planner prompt | active `system_llm_roles.planner` row in DB | `SystemLLMRoleService` |
| Final synthesis prompt | DB role prompt with fallback | `app/runtime/synthesizer.py`, `app/services/system_llm_role_service.py` |
| Memory preparation and fact prompts | DB-backed runtime roles | `app/runtime/memory/preparer.py`, `fact_extractor.py`, `fact_compactor.py` |

Notes:
- Planner prompt is compiled exclusively from the active planner role in DB.
  `ensure-defaults` never creates or backfills this role; a missing active
  planner is an explicit configuration error and must be created/activated by
  an administrator.
- Final synthesis resolves prompt/model params from DB role config with safe fallback.

## Tunable Points

- Policy limits: `platform_config.py` (`max_steps`, `max_wall_time_ms`).
- Stage behavior: `stages/*.py`.
- Event contract/envelope: `events.py`, `envelope.py`.
- Confirmation continuation behavior: `pipeline.py`, `orchestrator.py` and HITL protocol adapters.
- Budget contract: `budgets/schema.py`, `budgets/ledger.py` and
  `budgets/resolver.py`. Budget snapshots use the canonical runtime event stream;
  there is no second transactional budget journal.
- Redaction: `redactor.py` (`RuntimeRedactor`) for trace/prompt/tool/context surfaces.

Runtime-config keys currently used by orchestrator/agent flows:
- `required_operation_retry_instruction` — text injected on protocol retry when agent skipped required tool call.
- `operations_rules_text` — full override of "mandatory operation rules" block appended to tool prompt.
- `intent_messages` — map of runtime intent templates (`agent_start`, `final_answer`, `tool_call`).
- The final-plan report has a runtime-owned hard size limit (currently
  `120_000` characters); exceeding it fails explicitly instead of truncating
  or silently dropping evidence.

## Collection Readiness

Runtime preflight exposes canonical collection readiness contract via
`CollectionRuntimeReadiness`:

- `status`: `ready|degraded_missing_credentials|degraded_provider_unhealthy|schema_stale|no_operations`
- `schema_freshness`, `provider_health`, `credential_status`
- `available_operations`, `missing_requirements`
- version/current schema metadata and `last_sync_at`

This payload is attached to `ResolvedDataInstance.readiness` and propagated into
capability cards/admin diagnostics.

## Agent Prompt Surface

LLM-facing agent prompts use a collection-centered structure:

- base agent prompt
- `Доступные коллекции`
- for each collection:
  - slug/name/type/purpose/data and usage rules from current version
  - business fields and available operation names
  - the model may call `collection.info` when a result is empty or the schema is unclear
- `Системные операции`
- machine-oriented `tool_call` JSON contract for:
  - system operations
  - all preflight-authorized collection operations

Rules:
- Diagnostic/runtime readiness data must not be rendered into the LLM prompt.
- Collections without bound operations must not appear in the LLM prompt.
- System operations must be rendered separately from collection-bound operations.
- Detailed operation argument contracts come from the initial native tools payload or plaintext tools appendix.

## Lifecycle Persistence Policy

- Canonical runtime event stream includes lifecycle events:
  `run_start/run_end`, `orchestrator_*`, `planner_iteration_*`,
  `agent_*`, `synthesis_*`.
- `runtime_execution_events` is the only persisted runtime journal. Chat root
  runs use level `none`; scoped agent executions persist according to the
  configured agent level. `RuntimeProgressStreamer` projects safe progress
  from the same logger admission point without creating a second trace.
- LLM trace uses `llm_request` and `llm_response` for one stable `llm_call_id`.

## Tests

Core unit seams:
- `tests/unit/test_runtime_v3_pipeline.py`
- `tests/unit/test_runtime_v3_stages.py`
- `tests/unit/test_pipeline_assembler.py`
- `tests/unit/test_platform_config_loader.py`
- `tests/unit/test_synthesizer_loads_db_prompt.py`

CI gates:
- `pytest tests/unit -q --tb=short`
- `pytest tests/eval -q`
- `--cov=app.runtime --cov=app.agents.contracts --cov=app.agents.credential_resolver --cov=app.agents.execution_preflight --cov=app.agents.operation_router --cov=app.agents.runtime_rbac_resolver --cov-fail-under=70`

## Completed (was TODO)

- ✅ Remove bidirectional state bridge `WorkingMemory ↔ RuntimeTurnState` — fully migrated to `RuntimeTurnState` as single source of truth.
- ✅ Remove `WorkingMemory` from public runtime package exports (`app.runtime`, `app.runtime.memory`).

## TODO

- Remove legacy operation transport from agent-facing LLM flow:
  stop exposing operation-shaped contracts to models, keep tool-first prompting/protocol,
  and keep operation resolution as an internal runtime concern only.
- Add `QueryRewriter` stage (behind a feature flag) before planner input assembly.
- Persist both `original_query` and `rewritten_query` in runtime trace.
- Implement remote `collection.info` runtime enrichment for `sql` / `api` collections:
  return provider-aware field/value profiling, remote freshness signals, and safe distinct/top-value hints without relying on local table profiling.

### Agent response protocol v2

`response_spec` requests presentation (`any`, `text`, `structured`, `artifact`)
with an advisory schema. Agent completion and actual JSON data are preserved;
only envelope/needs invariants and required runtime-created files are enforced.
Data schema deviations are warnings, including registered data contracts.
Bindings accept actual result JSON Pointers and prior completed producers;
missing paths replan only the consumer. See `docs/architecture/AGENT_RUNTIME.md`
and `RUNTIME_TOOL_RESULTS.md` for compatibility and persistence behavior.
