# System LLM Roles

## Active turn roles

- **TurnPreflight** routes a user turn to direct synthesis, planner, memory
  search, or clarification. It may propose durable user/tenant fact candidates
  but does not write them.
- **Planner** proposes persisted agent tasks and the next terminal decision.
  Runtime owns task state, retries, dependencies, and execution.
- **Synthesizer** prepares the user-facing answer from the bounded synthesis
  context. It does not execute tools or change the plan.

## Post-turn fact roles

- **FactExtractor** proposes facts supported by the completed turn and its
  evidence.
- **FactCompactor** deduplicates and selects a bounded reconciliation action.
- **FactReconciler** validates and persists eligible user/tenant facts. The
  LLM roles do not write directly to durable storage.

Document LongMemory indexing uses the HippoRAG worker's configured model calls.
Semantic Memory extraction/evaluation roles remain available for legacy review
operations; they are not part of the active root-turn `memory.search` flow.

## Shared boundaries

Structured roles derive JSON schemas from Pydantic contracts. Roles receive
bounded normalized DTOs, not raw ORM rows, credentials, or provider diagnostics.
Runtime owns access checks, tool execution, task lifecycle, and persistence.
