# Runtime Memory Architecture

## Purpose

Runtime memory is a bounded, provenance-aware context projection. It is not
runtime state, RAG knowledge, an artifact registry, or an execution trace.

```text
database records -> RuntimeMemoryService -> immutable MemorySnapshot
  -> prompt-profile adapter -> planner or agent context
```

`RuntimeTurnState`, persisted plans/tasks/attempts, and tool outputs remain
runtime working state. RAG keeps source documents and retrieval evidence.
Artifacts remain opaque references whose access is resolved at use time.

## Durable scopes

The target durable scopes are:

- **user** — role, responsibilities, working systems, preferences and other
  stable personal context;
- **tenant** — terminology, shared conventions, default process rules and
  organization-wide operational context;
- **project** — project-specific process rules, constraints, decisions,
  terminology and source references.

Chat memory is deliberately outside the first increment. Current chat history
and `RuntimeTurnState` remain the context for a chat until a separately
designed chat-memory contract exists.

Projects are tenant-owned catalog entities. A run is not permanently bound to
a project: one chat can discuss multiple projects. A project is resolved only
when the request or a clarification identifies it.

## Canonical data contract

The future persistence contract is an atomic `MemoryEntry` owned by exactly
one scope subject. Its logical fields are:

```text
id, scope, owner_id, kind, key, content, metadata,
priority, source_ref, revision, active, created_at, updated_at
```

`kind` is one of: `profile`, `preference`, `responsibility`, `system`,
`terminology`, `process_rule`, `constraint`, or `decision`. `source_ref` is
evidence only; an artifact reference never grants access and is re-authorized
when a tool reads it.

The legacy `Fact` and `DialogueSummary` models are not the new public memory
contract. They remain compatibility state until an explicit migration plan.

## Read service and snapshots

`RuntimeMemoryService` is the sole memory read facade. It resolves effective
access, selects active entries, bounds output, and returns DTOs; prompt
builders and tools do not query memory tables directly.

It exposes these immutable projections:

- `MemorySnapshot`: user and tenant context for one runtime run;
- `PlannerMemoryContext`: the planner-specific projection of that snapshot;
- `AgentMemoryContext`: a task-filtered projection of that snapshot;
- `ProjectMemoryContext`: a bounded, query-relevant project projection.

No caller receives raw ORM rows or an unrestricted memory dump.

## Prompt profiles

Planner and agents have different memory needs.

| Consumer | Injected automatically | Retrieved on demand |
| --- | --- | --- |
| Planner | User profile and tenant context | Project resolution and project memory |
| Agent | Task-filtered user/tenant context | Project memory, files and RAG through canonical tools |
| Synthesizer | No durable memory by default; only final task results and allowed evidence | None |

The planner receives structured `memory_context` in its planning payload, not
a prose dump. It contains only bounded user role/responsibility/preferences
and tenant terminology/conventions/default process rules. It never receives
all project rules.

The agent adapter selects only entries relevant to task intent, instructions,
dependency outputs and the current query. Its output is rendered into the
agent prompt through the existing prompt assembler; unrelated profile data is
not injected.

## Project-memory tools

Project context follows progressive disclosure. Both planner and agents use
the same versioned, read-only system tools:

- `project.resolve(query)` returns at most five authorized project candidates
  with stable id, name and short description;
- `project.memory.read(project_id, query)` returns bounded relevant process
  rules, constraints, decisions and source references.

Planner access is deliberately limited to these contextual tools. It does not
receive arbitrary database access or unrestricted file content. Files and RAG
are read by a normal context/document agent through existing canonical tools.

An ambiguous or missing project result causes the planner to use its existing
`ask_user` decision and resume after the user supplies the project.

## Planner and task lifecycle

`GraphPlanner` remains the only producer of `PlanPatch`, but its planning call
may perform a bounded read-only contextual tool loop before emitting that
patch. Tool requests/results are typed, budgeted, redacted and journalled
through the existing runtime logger.

Successful task completion is not equivalent to terminal run completion. A
planned task declares:

```text
on_success = continue | replan
```

- `continue` runs already-declared dependent tasks; a plan naturally completes
  when all its tasks are terminal;
- `replan` sends the task's bounded outputs to the planner as
  `completed_outputs`, which creates the next plan revision.

The planner needs an explicit `complete` decision for a replan whose context
task already made the answer sufficient. An empty `apply_graph` is never a
completion signal.

Dependency outputs must be injected into a dependent agent's task context as
bounded summaries, extracted facts, evidence and opaque artifact references.
They must not carry unbounded file bodies.

## Context-reader agent

File and document inspection belongs to a standard context/document agent,
not to planner execution. It is a normal configured agent with safe system
operations such as `file.read`, RAG search and project-memory tools.

For a simple file summary the planner creates one context-reader task with
`on_success=continue`; once that task completes, normal finalization produces
the answer. For a file analysis that changes the next action, the reader task
uses `on_success=replan` and returns a bounded structured context result.

## Explicitly deferred

This document does not authorize implementation of automatic extraction,
memory writing, background jobs, cleanup/retention, conflict resolution,
review UI, or authoring APIs. Those require a separate lifecycle and mutation
contract.
