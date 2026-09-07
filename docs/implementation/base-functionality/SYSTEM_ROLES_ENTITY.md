# System Roles Entity

## Purpose

This document defines the active system LLM roles of the runtime and their
strict boundaries. They coordinate or support execution; none is a business
agent or an owner of domain tools.

The active role set is `planner`, `memory`, `fact_extractor`,
`fact_compactor` and `synthesizer`. Historical `triage`, `summary` and
`summary_compactor` roles are not part of the active runtime contract.

## Role responsibilities

### Planner

Planner produces one immutable `IterationProposal`. It receives the goal,
bounded memory, available agents/artifacts and the execution ledger. It returns
only agent tasks, bindings, resolutions for earlier incomplete work, and one
terminal: `planner` or `synthesis`.

Planner does not execute tools, mutate task state, create a confirmation gate,
or appear as a task node. When a prior task is incomplete, it must explicitly
continue it with new task ids, accept named partial outputs, exclude scope, or
report a limitation.

### Memory Preparer

Memory Preparer selects bounded indexes of confirmed facts, projects and
glossary entries for the planner. It neither writes facts nor decides routing,
task lifecycle or user-visible answers. A failure produces an empty optional
memory projection rather than failing the run.

### Fact Extractor and Fact Compactor

These post-turn roles prepare evidence-backed durable-memory candidates.
Extractor identifies supported candidate facts; Compactor deduplicates and
selects a compaction action. `FactReconciler`, not an LLM role, owns durable
persistence. Neither role changes the execution plan or acts as evidence for a
current task result.

### Synthesizer

Synthesizer receives a bounded synthesis context: synthesis brief, completed
reports, explicitly accepted partial outputs, verified references and current
user-visible limitations. It writes the final user answer only. It does not
plan, invoke tools, choose agents, hide limitations or add facts.

## Shared contract rules

- Structured roles use typed Pydantic DTOs and generated JSON schemas.
- Synthesizer uses a plain-text contract and accepts only the prepared context.
- Runtime owns task lifecycle, retries, dependency blocking, confirmations and
  verification of artifacts/evidence.
- Roles consume normalized bounded DTOs, never raw ORM rows, tool journals,
  credentials or provider diagnostics.

## Relation to agents and policy

Agents execute the immutable tasks assigned by planner. Policy and runtime
gates decide whether an operation may execute; a system role can neither
bypass nor approve a destructive operation. A confirmation is a task-local
runtime state, not a planner or synthesizer decision.
