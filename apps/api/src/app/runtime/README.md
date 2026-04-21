# Runtime V3 Map

## Flow

`RuntimePipeline` coordinates one turn and emits canonical runtime events.

1. `pipeline.py` receives `PipelineRequest`.
2. `assembler.py` builds per-turn dependencies (`PipelineAssembler`).
3. Stages execute in order:
   - `stages/triage_stage.py`
   - `stages/planning_stage.py`
   - `stages/finalization_stage.py`
4. State is persisted through ports (`ports.py`) and adapters (services/repos).
5. Output events are normalized in `events.py` and wrapped with envelope (`envelope.py`).

## Responsibility Split

- `pipeline.py`: orchestration only (stage order, terminal handling, replay/resume entry points).
- `assembler.py`: dependency wiring, cached services, stage factories.
- `platform_config.py`: load platform snapshot (`policy`, routable agents, config degradation).
- `resume.py`: paused-run continuation and replay safety.
- `memory/working_memory.py`: turn memory model and loop guards.
- `synthesizer.py`: final answer synthesis and role prompt/model params loading.

## Ports and Adapters

Runtime code should depend on `ports.py` contracts, not concrete DB/HTTP classes.

- Ports: run store, memory repo, planner, triage, synthesizer, config loader.
- Adapters: `app.services.*`, `app.repositories.*`, and external clients.

Rule of thumb:
- If logic is domain/runtime behavior -> keep in `app/runtime/*`.
- If logic is I/O, SQL, external API, or framework integration -> adapter layer.

## Prompt Ownership (Current)

| Concern | Current source | Where to change |
|---|---|---|
| Triage prompt | runtime triage builder | `app/runtime/triage/*` |
| Planner prompt | planner prompt builder | `app/runtime/planner/*` |
| Final synthesis prompt | DB role prompt with fallback | `app/runtime/synthesizer.py`, `app/services/system_llm_role_service.py` |
| Summary/Memory prompts | legacy-compatible services | `app/runtime/summarizer_turn.py`, `app/runtime/memory/*` |

Notes:
- Triage/Planner prompts are still code-defined for fast iteration.
- Final synthesis already resolves prompt/model params from DB role config with safe fallback.

## Tunable Points

- Policy limits: `platform_config.py` (`max_steps`, `max_wall_time_ms`).
- Stage behavior: `stages/*.py`.
- Event contract/envelope: `events.py`, `envelope.py`.
- Resume behavior: `resume.py`.

## Tests

Core unit seams:
- `tests/unit/test_runtime_v3_pipeline.py`
- `tests/unit/test_runtime_v3_stages.py`
- `tests/unit/test_pipeline_assembler.py`
- `tests/unit/test_platform_config_loader.py`
- `tests/unit/test_synthesizer_loads_db_prompt.py`

CI gates:
- `pytest tests/unit -q --tb=short`
- `--cov=app.runtime --cov-fail-under=70`
