# Runtime Memory Architecture

## Purpose

Runtime memory is a bounded, provenance-aware context projection. It is not
runtime state, RAG knowledge, an artifact registry, or an execution trace.

```text
facts table -> MemoryService/FactStore -> immutable MemorySnapshot
  -> prompt-profile adapter -> planner or agent context
```

`RuntimeTurnState`, persisted plans/tasks/attempts, and tool outputs remain
runtime working state. RAG keeps source documents and retrieval evidence.
Artifacts remain opaque references whose access is resolved at use time.
The runtime memory implementation is currently backed by the `facts` table and
the `MemoryService`/`FactStore` facade; the older `WorkingMemory` API is not a
public source of truth.

The terminology catalogue is a separate persistence surface. It stores
canonical terms and aliases rather than propositions, so it is not a `Fact`
row. Automatically extracted user and tenant terms begin as evidence-backed
candidates in `glossary_entries`; terminology grounded in a successful document
or table search becomes a global candidate. A term becomes `confirmed` only
after three distinct stable source references. Pending and unconfirmed terms
are hidden. Confirmed entries are supplied to the memory selector as a
separate bounded glossary input and are also available to `memory.lookup` for
alias expansion. Glossary entries do not need to declare an entity type: the
expanded forms are matched against the project catalogue and project-memory
keys in the read service.

## Durable scopes

The implemented durable scopes are:

- **user** — role, responsibilities, working systems, preferences and other
  stable personal context;
- **tenant** — terminology, shared conventions, default process rules and
  organization-wide operational context;
- **project** — project-specific process rules, constraints, decisions,
  terminology and source references. Project facts are associated with the
  tenant-owned `Project` catalogue entity.

Chat conversation summaries remain persisted for compatibility, but the
conversation-summary component is currently disabled in the active
`MemoryBuilder` registry. The active runtime memory path is facts plus
in-turn/tool/agent/attachment sections; chat history is supplied separately by
the turn request.

Projects are tenant-owned catalog entities. A run is not permanently bound to
a project: one chat can discuss multiple projects. A project is resolved only
when the request or a clarification identifies it.

## Canonical data contract

The current durable contract is a `Fact` row owned by exactly one scope subject
or project. Its logical fields include:

```text
id, scope, owner_type, owner_id, project_id, kind, subject, value,
entry_metadata, confidence, source, source_ref, support_count, status,
superseded_by, observed_at, created_at, updated_at
```

`kind` and `scope` carry the semantic category. `source_ref` and
`FactObservation` rows are evidence only; an artifact reference never grants
access and is re-authorized when a tool reads it. A fact is active for runtime
selection only when `superseded_by IS NULL` and `status=confirmed`.

`DialogueSummary` remains compatibility storage, not an active runtime memory
component. `WorkingMemory` and the historical `ExecutionMemoryService` are
legacy compatibility surfaces and must not be introduced in new runtime code.

## Read service and snapshots

`MemoryService` is the runtime durable-fact read/write facade. It resolves
effective access, selects active entries, bounds output, and returns DTOs;
prompt builders and tools do not query memory tables directly. Administrative
manual edits use the separate authenticated admin fact service, which applies
the same owner/scope and supersede rules.

It exposes these immutable projections:

- `MemorySnapshot`: user and tenant context for one runtime run;
- `PlannerMemoryContext`: the planner-specific projection of that snapshot;
- `AgentMemoryContext`: a task-filtered projection of that snapshot;
- `ProjectMemoryContext`: a bounded, query-relevant project projection when
  project candidates are available.

No caller receives raw ORM rows or an unrestricted memory dump.

## Prompt profiles

Planner and agents have different memory needs.

| Consumer | Injected automatically | Retrieved on demand |
| --- | --- | --- |
| Planner | Selected user/tenant context | Glossary/project resolution and exact project memory through canonical system operations |
| Agent | Task-filtered user/tenant context | Project memory, files and RAG through canonical tools |
| Synthesizer | No durable memory by default; only bounded runtime-owned projections of final task results, verified artifacts and allowed evidence | None |

The planner receives structured `memory_context` in its planning payload, not
a prose dump. It contains only bounded user role/responsibility/preferences
and tenant terminology/conventions/default process rules selected for this
request. It never receives all project rules.

The agent adapter selects only entries relevant to task intent, instructions,
dependency outputs and the current query. Its output is rendered into the
agent prompt through the existing prompt assembler; unrelated profile data is
not injected.

## Project-memory tools

Project context follows progressive disclosure. The runtime exposes the
canonical system operations `memory.lookup`, `memory.read` and `memory.mark`:

- `memory.lookup` accepts a batch of suspicious terms. It first returns
  confirmed glossary matches and expands each query with its canonical term
  and aliases. It then searches project `key`, `name` and aliases and returns
  only bounded dynamic memory keys for each resolved project; fact values are
  never returned by this operation;
- `memory.read` accepts one or more exact `{project_key, keys}` groups and
  returns bounded confirmed values only for those keys. Agents should use keys
  returned by `memory.lookup`, not invent subject keys;
- `memory.mark` records bounded evidence-backed candidates in the
  current turn only and never writes durable memory directly. Its evidence IDs
  must be the `evidence_call_id` exposed on a successful tool result; artifact
  IDs and native provider call IDs are not valid evidence.

All three operations are published as `scope_kind=system` operations and are
available without collection binding. Planner and agent access is deliberately
limited to these contextual tools. They do not receive arbitrary database
access or unrestricted file content. Files and RAG are read by a normal
context/document agent through existing canonical tools.

The older `project_memory.read` operation remains a compatibility surface for
existing callers during migration; new prompts and plans must use
`memory.lookup` followed by `memory.read`.

If one term resolves to multiple projects, `memory.lookup` returns
`ambiguous_projects` and does not read any of them. If several distinct
projects are identified in one request, it returns all of them as separate
groups. An ambiguous or missing project result causes the planner to use its
existing `ask_user` decision and resume after the user supplies the project.

## Planner and task lifecycle

`GraphPlanner` remains the only producer of `PlanPatch`, but its planning call
may perform a bounded read-only contextual tool loop before emitting that
patch. Tool requests/results are typed, budgeted, redacted and journalled
through the existing runtime logger.

Successful task completion is not equivalent to terminal run completion. An
agent node may declare:

```text
on_success = continue | replan
```

- `continue` runs already-declared dependent tasks; a plan naturally completes
  when all its tasks are terminal;
- `replan` sends the task's bounded outputs to the planner as
  `completed_outputs`, which creates the next plan revision.

For a multi-task discovery phase, planner creates a separate `kind=planner`
checkpoint node with dependencies on the discovery tasks. When it becomes
ready, the runtime returns the full persisted plan graph (task results and
artifact references, never file bodies) to planner and applies the next graph
revision before completing the checkpoint.

The planner needs an explicit `complete` decision for a replan whose context
task already made the answer sufficient. An empty `apply_graph` is never a
completion signal.

Dependency outputs must be injected into a dependent agent's task context as
bounded summaries, extracted facts, evidence and opaque artifact references.
They must not carry unbounded file bodies.

## Context-reader agent

File and document inspection belongs to a standard context/document agent,
not to planner execution. It is a normal configured agent with safe system
operations such as `file.read`, `memory.lookup`, `memory.read`, RAG search and
project-memory tools.

For a simple file summary the planner creates one context-reader task with
`on_success=continue`; once that task completes, normal finalization produces
the answer. For a file analysis that changes the next action, the reader can
feed a planner checkpoint that determines the following graph segment.

## Writeback and administration

After terminal finalization, `MemoryWriter` receives the bounded turn material
and runs the write pipeline:

```text
successful evidence -> FactExtractor -> FactCompactor -> FactReconciler
                    -> Fact + FactObservation rows

terminology evidence -> FactExtractor -> FactCompactor -> GlossaryReconciler
                     -> glossary_entries + GlossaryObservation rows
```

`FactExtractor` validates that a candidate is stable, scoped and supported by
evidence. `FactCompactor` removes duplicates and chooses a deterministic
compaction action. `FactReconciler` owns persistence, support counts,
confirmation thresholds, project resolution, conflict markers and
supersede/tombstone semantics. None of these components may write raw LLM
output directly to active memory.

`GlossaryReconciler` owns the analogous candidate lifecycle for `kind=glossary`.
It deduplicates source references, merges aliases case-insensitively and does
not expose a pending or unconfirmed term to users or runtime consumers.

Chat dispatches this writeback to the Celery `memory` queue by default after
the final answer. Sandbox does not mutate durable facts; its `set`/`deleted`
overlays are resolved into the immutable run snapshot. An inline writeback mode
exists for explicit runtime/configuration use and follows the same writer
pipeline.

Administrative fact CRUD is a separate, authenticated service for user and
tenant owners. Manual admin facts are confirmed and source-marked as manual;
updates create a replacement and supersede the previous row, while delete is a
self-tombstone. Credentials are never part of memory data or memory prompts.

The remaining lifecycle work is limited to retention/cleanup policy,
conflict-review UX and broader project authoring/RAG extraction policy; these
must extend this contract rather than create another memory store.
