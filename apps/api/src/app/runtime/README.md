# Runtime V3 Map

## Flow

`RuntimePipeline` coordinates one turn and emits canonical runtime events.

1. `pipeline.py` receives `PipelineRequest`.
2. `assembler.py` builds per-turn dependencies (`PipelineAssembler`).
3. Stages execute in order:
   - `stages/planning_stage.py` — single decision engine (absorbed direct_answer/clarify)
   - `stages/finalization_stage.py` — synthesizer for NEEDS_FINAL outcomes
4. State is persisted through ports (`ports.py`) and adapters (services/repos).
5. Output events are normalized in `events.py` and wrapped with envelope (`envelope.py`).

## Responsibility Split

- `pipeline.py`: orchestration only (stage order, terminal handling, replay/resume entry points).
- `assembler.py`: dependency wiring, cached services, stage factories.
- `platform_config.py`: load platform snapshot (`policy`, routable agents, config degradation).
- `turn_state.py`: canonical runtime state (`RuntimeTurnState`) — single source of truth for planner/agent/finalization.
- `synthesizer.py`: final answer synthesis and role prompt/model params loading.

## Ports and Adapters

Runtime code should depend on `ports.py` contracts, not concrete DB/HTTP classes.

- Ports: run store, memory repo, planner, synthesizer, config loader.
- Adapters: `app.services.*`, `app.repositories.*`, and external clients.

Rule of thumb:
- If logic is domain/runtime behavior -> keep in `app/runtime/*`.
- If logic is I/O, SQL, external API, or framework integration -> adapter layer.

## Prompt Ownership (Current)

| Concern | Current source | Where to change |
|---|---|---|
| Planner prompt | planner prompt builder | `app/runtime/planner/*` |
| Final synthesis prompt | DB role prompt with fallback | `app/runtime/synthesizer.py`, `app/services/system_llm_role_service.py` |
| Summary/Memory prompts | legacy-compatible services | `app/runtime/summarizer_turn.py`, `app/runtime/memory/*` |

Notes:
- Planner prompt is code-defined for fast iteration.
- Final synthesis resolves prompt/model params from DB role config with safe fallback.

## Tunable Points

- Policy limits: `platform_config.py` (`max_steps`, `max_wall_time_ms`).
- Stage behavior: `stages/*.py`.
- Event contract/envelope: `events.py`, `envelope.py`.
- Resume behavior: `resume.py`.
- Budget contract: `budget.py` (`RuntimeBudget`, `RuntimeBudgetTracker`).
- Redaction: `redactor.py` (`RuntimeRedactor`) for trace/prompt/tool/context surfaces.
- Replay: `replay.py` (trace-pack validation and deterministic replay checks).

Runtime-config keys currently used by orchestrator/agent flows:
- `required_operation_retry_instruction` — text injected on protocol retry when agent skipped required operation call.
- `operations_rules_text` — full override of "mandatory operation rules" block appended to operation prompt.
- `intent_messages` — map of runtime intent templates (`agent_start`, `final_answer`, `operation_call`).
- `runtime.synth_chunk_size` — default chunk size for synthesizer delta streaming in short-circuit/fallback paths.

## Collection Readiness

Runtime preflight exposes canonical collection readiness contract via
`CollectionRuntimeReadiness`:

- `status`: `ready|degraded_missing_credentials|degraded_provider_unhealthy|schema_stale|no_operations`
- `schema_freshness`, `provider_health`, `credential_status`
- `available_operations`, `missing_requirements`
- version/current schema metadata and `last_sync_at`

This payload is attached to `ResolvedDataInstance.readiness` and propagated into
capability cards/admin diagnostics.

## Trace-Pack v2 and Replay

- Trace pack version: `runtime.trace_pack.v2`.
- Includes: runtime config snapshot, budget policy/consumed, planner IO, policy decisions,
  memory bundle compact, typed tool errors, model config.
- Replay CLI:

```bash
python -m app.runtime.replay path/to/trace_pack.json
```

By default replay blocks destructive/write operations.

## Lifecycle Persistence Policy

- Canonical runtime event stream includes lifecycle events:
  `run_start/run_end`, `orchestrator_*`, `planner_iteration_*`,
  `agent_*`, `synthesis_*`.
- `agent_run_steps` (chat/agent runs) persist execution-relevant steps
  (`planner_decision`, `llm_turn`, `operation_*`, `budget_snapshot`, `final`, `error`)
  and do **not** require lifecycle duplication there.
- `sandbox_run_steps` persist the full event stream (including lifecycle events),
  which is used by sandbox inspector and deep replay/debug flows.
- Trace consumers must treat legacy step types (`llm_request/llm_response/llm_call`,
  `routing/triage/planner_action`) as historical fallback only.

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

## TODO

- Add `QueryRewriter` stage (behind a feature flag) before planner input assembly.
- Persist both `original_query` and `rewritten_query` in runtime trace.
