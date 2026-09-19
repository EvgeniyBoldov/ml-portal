# Runtime Memory Architecture

## Purpose

Runtime memory is a bounded, provenance-aware context projection. It is not
runtime state, RAG knowledge, an artifact registry, or an execution trace.

Per-chat working context is a separate surface defined in
[`CHAT_CONTEXT_MEMORY.md`](CHAT_CONTEXT_MEMORY.md). It may refer to durable
facts, plans, and artifacts, but it never copies their authoritative data and
never reads the runtime event journal.

```text
facts table -> MemoryService/FactStore -> immutable MemorySnapshot
  -> bounded mechanical lookup or scoped runtime recall
  -> TurnPreflight, planner or agent context
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
- `AgentMemoryContext`: the bounded run-selected projection supplied to a
  task; task instructions and tool retrieval further narrow its use, but the
  runtime does not claim a second per-task selector;
- `ProjectMemoryContext`: a bounded, query-relevant project projection when
  project candidates are available.

No caller receives raw ORM rows or an unrestricted memory dump.

## Turn routing and recall

Memory preparation is not an unconditional LLM step before planning.
`TurnPreflight` first receives only a cheap, ACL-safe mechanical lookup of
confirmed glossary aliases, project names and entity mappings. It can request
bounded context with a `MemoryRequest`, but does not read memory storage or run
a memory tool loop itself.

For a simple memory-grounded answer, runtime resolves the requested scoped
context and invokes TurnPreflight once more to produce a `SynthesisBrief`.
For execution work, TurnPreflight sends a `TaskBrief` to planner without a
preselected project-memory dump. Planner then calls canonical memory operations
and decides which returned rules, processes and facts belong in the plan.

## Prompt profiles

Planner and agents have different memory needs.

| Consumer | Injected automatically | Retrieved on demand |
| --- | --- | --- |
| TurnPreflight | Mechanical glossary/project/entity candidates only | Requests a bounded recall; it does not read memory itself |
| Planner | No automatic project-memory dump | Glossary/project resolution and exact project memory through canonical system operations |
| Agent | Task-filtered user/tenant context | Project memory, files and RAG through canonical tools |
| Synthesizer | No durable memory by default; bounded completed reports, verified artifacts, allowed evidence and task limitations | None |

Planner never receives an unrestricted memory dump or raw ORM rows. Its
`TaskBrief` carries task/project direction, while canonical memory operations
return only bounded scoped projections that planner selected for the plan.

The runtime passes the bounded context already selected for the current run to
the agent prompt. Task intent, instructions and dependency outputs delimit how
it is used; further project-specific information must be obtained through the
canonical tools. The runtime does not promise a separate per-task semantic
selector.

## Project-memory tools

Project context follows progressive disclosure. The sole canonical system
operation is `memory.search(query, project_keys?, entity_ids?, kinds?,
direction?, limit?)`. It is available without collection binding to Planner
and agents, validates project keys fail-closed, and returns a bounded typed
`memory_context`: resolved projects/terms, relevant knowledge, rules,
procedures, constraints, durable user/tenant facts, uncertainty, provenance
and whether source verification is required. It never returns raw ORM rows or
storage keys.

TurnPreflight uses a separate mechanical lookup and `MemoryRequest`; it never
calls the operation itself. Unknown or ambiguous project identity is a
clarification condition before planning. No role receives arbitrary database
access or unrestricted file content.

## Planner and task lifecycle

`GraphPlanner` is the only producer of `IterationProposal`. Its planning call
may perform a bounded read-only contextual tool loop before emitting the
proposal. Tool requests/results are typed, budgeted, redacted and journalled
through the existing runtime logger.

An iteration contains agent tasks and one terminal property. `terminal=planner`
returns the full structural execution ledger to the planner after its tasks are
terminal. `terminal=synthesis` produces the answer only when every task in the
iteration completed; any failed, blocked, unfulfillable or missing-dependency
task deterministically returns control to planner instead.

Planner receives every persisted task outcome across the run. It makes an
explicit resolution for incomplete work: continue via named new tasks, accept
named partial outputs, exclude part of the requested scope, or report the
remaining limitation. Runtime never infers this decision from result text.

Dependency outputs must be injected into a dependent agent's task context as
bounded summaries, extracted facts, evidence and opaque artifact references.
They must not carry unbounded file bodies.

## Context-reader agent

File and document inspection belongs to a standard context/document agent,
not to planner execution. It is a normal configured agent with safe system
operations such as `file.read`, `memory.lookup`, `memory.read`, RAG search and
project-memory tools.

For a simple file summary the planner creates one context-reader task and an
iteration with `terminal=synthesis`. For a file analysis that changes the next
action, it creates an iteration with `terminal=planner`.

## Writeback and administration

After terminal synthesis, `MemoryWriter` receives the bounded turn material
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

For Sandbox observability, every accepted, rejected, skipped, conflicting or
published conversational candidate is collected as a bounded decision and
emitted through the canonical runtime journal after writeback succeeds. Its
evidence is represented by references/counts only; raw prompts, source text
and LLM reasoning are never journalled as memory decisions.

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
