# Chat Context Memory

## Status

Implemented architecture contract. `chat_memory_items` is the typed,
revisioned persistence surface for chat-local working context.

## Scope contract since migration 0191

The active focus uses flat `scope_keys` and `scope_mode=inherit|replace`.
Inheritance unions tenant and user preferences; empty profiles select `company`.
An explicit empty chat override searches no documents, while `scope_keys=null` on
`PUT /chats/{id}/memory-scopes` restores inheritance. UI updates use a revision
fence and survive delayed runtime writeback. `memory.search` returns one independent
result group per selected scope. The request and persistence contract uses
`scope_keys`; legacy `team_keys` and `project_keys` are accepted only in the
chat-context reducer as compatibility input. The current memory search contract
is described in [Memory](MEMORY.md#scope-чата).

## 1. Purpose

Chat context memory preserves the bounded working context of one chat so that
the runtime can understand follow-up requests such as:

- «продолжай»;
- «сделай это для второго проекта»;
- «используй тот файл»;
- «что осталось?»;
- «попробуй ещё раз после исправления доступа».

It is deliberately narrower than complete message history, durable user
memory, project knowledge, runtime control state, and observability.

The runtime preserves bounded conversational references without copying the full
transcript or execution journal into chat memory.

The current flow is:

```text
persisted chat messages + current ChatContextSnapshot
  -> bounded turn input
  -> TurnPreflight
  -> direct synthesis OR planner -> agents -> synthesis
  -> typed RuntimeOutcomeProjection
  -> deterministic ChatContextReducer
  -> optional bounded ChatContextCompactor
  -> ChatContextReconciler
  -> next ChatContextSnapshot
```

The runtime journal is not part of this flow.

> **Текущий контракт LongMemory:** документная память является единым общим корпусом
> для пользователей портала. Scope из настроек пользователя/tenant и чата выбирают
> тематические индексы общего корпуса; они не задают ACL и не создают изолированные
> копии памяти. Обычные RAG-коллекции используют собственные проверки доступа.

## 2. Related contracts

This document extends, but does not replace:

- [`AGENT_RUNTIME.md`](AGENT_RUNTIME.md) — canonical execution pipeline;
- [`ADR_TURN_PREFLIGHT_ROUTING.md`](ADR_TURN_PREFLIGHT_ROUTING.md) — root
  routing and clarification;
- [`RUNTIME_MEMORY.md`](RUNTIME_MEMORY.md) — durable user, tenant, and project
  memory;
- [`RUNTIME_TRACE_SPEC.md`](RUNTIME_TRACE_SPEC.md) — operator journal and
  progress projections;
- [`CHAT_FILE_ATTACHMENTS.md`](CHAT_FILE_ATTACHMENTS.md) — artifact identity,
  ownership, and delivery;
- [`CHAT_RUNTIME_ERROR_CONTRACT.md`](CHAT_RUNTIME_ERROR_CONTRACT.md) — safe
  errors in chat transport and persistence;
- [`SANDBOX_RUNTIME.md`](SANDBOX_RUNTIME.md) — branch isolation and immutable
  sandbox snapshots.

If these contracts appear to overlap, ownership is resolved by the boundaries
defined below.

## 3. Goals

The architecture must:

1. Preserve the active subject of the chat: project, topic, entities, current
   objective, and unresolved question.
2. Maintain a chat-scoped registry of files mentioned, uploaded, discovered,
   or generated during a run.
3. Preserve only bounded user-relevant run outcomes needed by a later turn.
4. Carry exact provenance to the source chat turn, message, run, plan task, or
   artifact reference.
5. Apply deterministic precedence and ask for clarification when a reference
   remains ambiguous.
6. Make the next turn safe even if optional LLM compaction is delayed or
   unavailable.
7. Remain isolated by chat and, for sandbox-backed chats, by branch.
8. Keep every prompt projection bounded, typed, redacted, and purpose-specific.

## 4. Non-goals

Chat context memory is not:

- a copy or replay of `runtime_execution_events`;
- an unrestricted transcript;
- a second runtime plan store;
- a cache of raw tool arguments or results;
- durable user or tenant memory;
- source-backed project knowledge;
- an artifact ownership or authorization mechanism;
- a substitute for a fresh read from an external system;
- a place for credentials, prompts, hidden reasoning, stack traces, provider
  responses, or raw exceptions.

The current implementation does not provide parallel goal trees, semantic
search over the whole conversation, arbitrary historical task replay, or a
general knowledge graph.

## 5. Canonical state surfaces

The system has several related but non-interchangeable surfaces.

| Surface | Canonical responsibility | May enter chat context |
| --- | --- | --- |
| `chatmessages` | User-visible transcript and message metadata | Bounded recent tail and message references |
| `chat_turns` | Chat turn lifecycle, idempotency, pause/resume binding | Turn identity, terminal state, safe pause context |
| `chat_memory_items` | Materialized chat-local working context | Yes; it is the persistence surface defined here |
| `chat_artifact_references` | Chat-scoped artifact registry, resolvable target identity, and content-free normalized passport | `artifact_id` plus an authorized passport projection; file text only after explicit `file.read` |
| `runtime_plans`, tasks, attempts | Execution control plane | Only typed outcome references and bounded user-relevant status |
| `RuntimeTurnState` | In-memory state of the current run | Source for terminal outcome projection |
| `runtime_run_contexts` | Plan-independent run manifest and stored working-context snapshot | Only typed outcome references |
| `chat_artifact_representations` | Versioned extracted file content | Representation ID, completeness and bounded description |
| `facts` | Confirmed durable user/tenant facts | Read separately through `MemoryService`; never copied into chat memory |
| Document LongMemory | Shared source-derived knowledge searched by scope | Retrieved separately; never copied into chat memory |
| `runtime_execution_events` | Operator observability journal | Never read, copied, replayed, or summarized into chat memory |

The same fact may be referenced by more than one surface, but it has one
authoritative owner. Chat memory stores references and conversational meaning;
it does not duplicate source data.

## 6. Journal isolation

### 6.1 Binding rule

`runtime_execution_events` is categorically excluded as an input to chat
memory extraction.

No chat-memory component may:

- query journal rows to reconstruct a run;
- scan event sequence ranges for artifacts, plans, answers, or errors;
- parse raw event payloads;
- depend on runtime logging level;
- require a journal row to exist before context can be updated;
- copy a journal payload into `chat_memory_items`.

This rule is required for correctness as well as safety. Chat root runs may use
logging level `none`, agent logging is independently configurable, payloads
vary by redaction level, and the journal is allowed to evolve for operator
presentation without changing business semantics.

### 6.2 Allowed relationship

A chat-memory item may contain `source_run_id` or an opaque canonical entity
reference for provenance. This is a link, not a read dependency. The target
journal may not exist.

The runtime and journal may observe the same semantic occurrence through
different projections:

```text
successful artifact-producing tool call
  -> RuntimeEventLogger emits an operator event when logging allows it
  -> RuntimeTurnState/verified ledger records the canonical artifact
  -> RuntimeOutcomeProjector emits an ArtifactOutcome
  -> chat artifact registry registers or confirms the artifact reference
```

The two consumers share the typed runtime occurrence; chat memory does not
consume the journal consumer's output.

## 7. Ownership and components

### 7.1 `ChatContextService`

Application service responsible for:

- loading the active chat-local context;
- applying per-kind limits and expiry rules;
- resolving active/superseded/closed items;
- producing a typed `ChatContextSnapshot`;
- coordinating reducer, compactor, and reconciler writes;
- enforcing chat/branch identity and idempotency.

It does not resolve artifact bytes, query the runtime journal, or call external
systems.

`ChatContextService` owns chat-context reads and writes. The separate
`MemoryService` handles durable user and tenant facts.

### 7.2 `RuntimeOutcomeProjector`

Pure runtime-domain component that builds a bounded, serializable
`RuntimeOutcomeProjection` from canonical terminal state already available to
the pipeline:

- `RuntimeTurnState`;
- terminal preflight decision;
- final persisted plan snapshot, when a plan exists;
- runtime-owned task results and limitations;
- verified artifact ledger;
- pause or clarification outcome;
- normalized terminal reason;
- final synthesis receipt.

It never receives ORM journal rows and never performs database writes.

### 7.3 `ChatContextReducer`

Deterministic component that turns exact runtime outcomes into context
operations. It handles information that does not require semantic inference:

- explicit project selection;
- exact glossary matches;
- artifact registration and mention updates;
- clarification/open-loop lifecycle;
- exact task completion/blocking state;
- terminal outcome references;
- explicit artifact deletion;
- explicit user corrections and scope switches.

Its result is a list of typed `ChatContextOperation` values. It does not mutate
ORM rows directly.

### 7.4 `ChatContextCompactor`

Optional bounded LLM component for information that requires language
understanding:

- active conversational goal;
- current topic;
- explicit user decision or constraint;
- resolved referents useful for the next turn;
- compact recent-turn anchor.

It receives only:

- the prior typed snapshot;
- a bounded recent dialogue tail;
- current user and assistant messages;
- the typed runtime outcome projection;
- a list of valid source identifiers.

It returns proposed operations referencing those source identifiers. It cannot
write storage, invent source IDs, create durable facts, or report hidden
reasoning. Failure produces no inferred operations and does not fail the turn.

### 7.5 `ChatContextReconciler`

Deterministic persistence owner. It:

- validates item kind and payload schema;
- validates provenance references;
- checks turn ordering and expected revision;
- applies add/update/supersede/close/expire operations;
- prevents an older turn from overwriting a newer context item;
- preserves one active value for singleton keys;
- deduplicates collection-like keys;
- records safe diagnostics.

It performs `flush()` but does not independently commit outside an explicitly
owned worker transaction.

### 7.6 `ChatArtifactReferenceService`

Remains the sole chat artifact registry and access boundary. It owns:

- stable chat-scoped `artifact_id`;
- target kind and target identity;
- chat/user ownership;
- collection binding where applicable;
- safe metadata snapshot;
- re-authorization and target resolution.

Chat context may say why an artifact matters, but only the artifact service
may say whether the artifact is currently accessible.

### 7.7 `ChatTurnOrchestrator`

Owns orchestration between message persistence, runtime execution, and chat
context finalization. It supplies stable `chat_turn_id`, user/assistant message
IDs, and transaction context.

It does not interpret plans, raw tool outputs, or journal payloads. The runtime
supplies a typed outcome projection.

### 7.8 `ChatContextOutcomePort`

The runtime-to-chat handoff is an internal typed port, not an SSE frame and not
a journal reader.

Conceptually:

```python
class ChatContextOutcomePort(Protocol):
    async def apply(
        self,
        *,
        projection: RuntimeOutcomeProjection,
        expected_context_revision: int,
    ) -> ChatContextApplyReceipt: ...
```

`PipelineAssembler` supplies the adapter for a chat run. Sandbox supplies a
branch-scoped adapter or an explicit no-op when no persistent chat exists. The
pipeline invokes the port once per terminal or paused turn after its canonical
state is known. The adapter owns artifact registration, deterministic
reduction, and reconciliation under the caller's transaction.

`PipelineRequest` therefore needs a stable `chat_turn_id` and the context
revision read at turn start. It must not carry a live service, session, or
callback across a worker boundary. Concrete adapters are wired by the
assembler; serializable request data carries only identity and revision.

The receipt contains counts, the resulting revision, and safe degradation
codes. It contains no memory payload and is not exposed as chat transport.

## 8. Core contracts

The following are the current bounded runtime and persistence contracts.

### 8.0 Persistence layout

Persistence uses a small revision head plus typed item rows:

```text
chat_context_heads
  id
  chat_id
  sandbox_branch_id?
  revision
  updated_through_turn_id?
  updated_through_turn_order
  created_at
  updated_at

chat_memory_items
  typed item envelope defined below
```

`chat_context_heads` is the compare-and-swap boundary. There is exactly one
ordinary-chat head for `chat_id` with no branch and one head per
`(chat_id, sandbox_branch_id)` for sandbox branches. PostgreSQL uniqueness must
handle the nullable ordinary-chat branch explicitly through separate partial
unique indexes or an equivalent normalized scope key.

The head is locked or conditionally updated during reconciliation. Item rows
are never used to infer a global revision from timestamps.

Singleton kinds have at most one active row per context scope and stable
`item_key`. Collection kinds have at most one active row per
`(context scope, kind, item_key)`. These invariants are enforced by database
indexes as well as service validation.

### 8.1 `ChatContextSnapshot`

```json
{
  "chat_id": "uuid",
  "sandbox_branch_id": null,
  "revision": 17,
  "updated_through_turn_id": "uuid",
  "focus": {
    "scope_keys": ["ml-portal"],
    "scope_mode": "inherit",
    "topic": "chat context memory",
    "entity_refs": [],
    "source": "explicit"
  },
  "active_goal": {
    "text": "Design chat-local context memory",
    "status": "active",
    "source_turn_id": "uuid"
  },
  "term_bindings": [],
  "artifacts": [],
  "open_loops": [],
  "decisions": [],
  "recent_anchor": {
    "last_user_intent": "Approve an architecture before implementation",
    "last_assistant_outcome": "Architecture document prepared"
  },
  "uncertainties": []
}
```

The snapshot is a read model, not necessarily one database row. It must be
immutable for the duration of a run.

### 8.2 Context item kinds

The current context item kinds are:

| Kind | Cardinality | Purpose |
| --- | --- | --- |
| `scope` | one active item | Current document-memory scope focus and conversational topic |
| `goal` | one active item initially | Current user objective |
| `term_binding` | bounded set | Terms and abbreviations actually used in this chat |
| `artifact_ref` | bounded set | Conversational meaning around a registry artifact |
| `open_loop` | bounded set | Clarification, confirmation, blocked work, or promised follow-up |
| `decision` | bounded set | Explicit user choice or constraint relevant to later work |
| `recent_anchor` | one active item | Compact bridge beyond the raw dialogue tail |
| `task_result_ref` | bounded set | Reference to a user-relevant runtime outcome, not its raw payload |

The canonical names are `open_loop`, `decision`, and `recent_anchor`; the
runtime contract does not use `open_question`, `chat_fact`, or `summary` item
kinds.

### 8.3 Common item envelope

Every persisted item requires:

```text
id
chat_id
sandbox_branch_id?
kind
item_key
payload
status = active | superseded | closed | expired
confidence
source_turn_id?
source_message_id?
source_run_id?
source_ref?
source_turn_order
created_at
updated_at
expires_at?
```

`source_turn_order` or an equivalent monotonic chat revision is required to
prevent a delayed older worker from replacing newer state.

Singleton items use stable keys such as `current_scope`, `active_goal`, and
`recent_anchor`. Collection items use canonical keys such as published glossary term ID,
artifact ID, plan task entity ID, or a deterministic content fingerprint.

### 8.4 `RuntimeOutcomeProjection`

```json
{
  "schema_version": 1,
  "run_id": "uuid",
  "chat_id": "uuid",
  "chat_turn_id": "uuid",
  "terminal_state": "completed|waiting_input|waiting_confirmation|failed",
  "effective_goal": "...",
  "project_context": {
    "scope_keys": [],
    "scope_mode": "inherit"
  },
  "clarification": null,
  "plan": {
    "plan_id": "uuid",
    "revision": 3,
    "outcome": "completed",
    "user_relevant_items": []
  },
  "artifacts": [],
  "limitations": [],
  "safe_error": null,
  "assistant_outcome": {
    "message_id": null,
    "summary": "bounded safe outcome"
  }
}
```

The projection is not a trace. It excludes event sequence, prompts, LLM calls,
tool arguments, raw tool results, retries, credentials, token accounting, and
operator debug fields.

`assistant_outcome.message_id` is optional because synthesis completes before
`ChatTurnOrchestrator` persists the assistant message. The turn ID and run ID
are sufficient for initial reconciliation; the orchestrator may attach the
message reference later in the same transaction without changing semantic
context.

### 8.5 `ChatContextOperation`

```json
{
  "action": "add|update|supersede|close|expire|touch",
  "kind": "artifact_ref",
  "item_key": "artifact-id",
  "payload": {},
  "source_ids": ["runtime-artifact:artifact-id"],
  "expected_revision": 16
}
```

Unknown actions, kinds, keys, payload fields, or source references fail closed.

### 8.6 Trust classes

Every projected field has one trust class:

| Trust class | Examples | Allowed use |
| --- | --- | --- |
| `application_verified` | Current message attachment, registered artifact, exact project catalog match, persisted task status | Deterministic context and artifact registry |
| `runtime_normalized` | Accepted `TaskBrief.goal`, final limitation, synthesis receipt summary | Conversational intent/outcome only; never proof of external state |
| `user_explicit` | User-stated goal, choice, constraint, or term in a referenced message | Context candidate with message provenance |
| `model_inferred` | Topic, implicit goal, referent proposed by compactor | Bounded low-authority context; revision guarded and never used to bypass clarification |

An LLM-emitted artifact ID or claimed completed action has no trust class until
verified by the runtime. Technical journal data is not assigned a chat-context
trust class at all.

Payload schemas carry `trust_class` where a consumer needs to distinguish
exact and inferred values. A composite scope additionally carries independent
trust classes for `project_keys`, `entity_refs`, and `topic`: an inferred topic
must never downgrade or relabel verified project/entity identity. Explicit
current input always overrides an inferred item regardless of confidence
score.

## 9. Read lifecycle

At the start of a normal chat turn:

1. Router resolves chat access and current user.
2. `ChatStreamService` loads a bounded recent message tail.
3. `ChatContextService` loads the active snapshot for `(chat_id, branch_id)`.
4. Artifact IDs in the selected snapshot are batch-resolved through
   `ChatArtifactReferenceService` using current user, tenant, and chat access.
5. Missing or denied artifacts are omitted from runtime context. Reads are
   side-effect free; a registry deletion or an explicit lifecycle writer may
   retire the stale conversational reference later. Cached metadata never
   grants access.
6. Durable user/tenant facts are independently loaded through
   `MemoryService`.
7. Project/company knowledge remains on-demand through canonical memory/RAG
   operations.
8. Runtime freezes the resulting bounded turn context.

The read path must not wait for optional compaction. If a previous compactor
is delayed, deterministic items and recent messages still provide usable
context.

### 9.1 Prompt precedence

When resolving a reference, every consumer follows:

```text
explicit current user message
  > explicit recent dialogue
  > active chat context
  > durable user default
  > clarification
```

External current state is never resolved from memory. If the user asks for a
current ticket status, balance, deployment state, or similar value, runtime
must use an allowed current-state operation or state the limitation.

### 9.2 Ambiguity

Memory is a candidate resolver, not permission to guess. Runtime asks one
focused clarification when:

- more than one project remains equally plausible;
- «тот файл» matches multiple active artifacts without a recent unique use;
- a goal was superseded but the user refers to the old and new goal
  ambiguously;
- one alias matches several published terms;
- an artifact reference exists but is no longer authorized or available.

## 10. Write lifecycle

### 10.1 Completed turn

```text
RuntimePipeline reaches a terminal answer
  -> RuntimeOutcomeProjector builds typed projection
  -> ChatContextOutcomePort receives projection + expected revision
  -> deterministic ChatContextReducer builds operations
  -> artifact registry registration/resolution completes
  -> ChatContextReconciler applies deterministic operations
  -> ChatTurnOrchestrator persists assistant message and attaches its reference
  -> transaction commits
  -> final chat frame is emitted/closed according to transport contract
  -> optional ChatContextCompactor runs with revision guard
```

The exact final-frame/commit order must preserve the existing streaming
transaction contract, but the next accepted user turn must not observe a state
older than the immediately preceding committed turn.

### 10.2 Paused turn

For `waiting_input` or `waiting_confirmation`:

- `chat_turns` remains the lifecycle source of truth;
- chat context receives an `open_loop` pointing to the turn/run and containing
  only the safe user-facing question or confirmation summary;
- no goal is marked completed;
- verified artifacts already produced may be registered;
- resume closes or updates the same open loop instead of creating an unrelated
  one.

### 10.3 Failed turn

Failure alone is not memory.

The reducer stores an error-derived item only when it changes what the next
user turn must know. Examples:

- keep an active goal and mark its work item `blocked` because authorization is
  missing;
- preserve a safe limitation stating that a requested source was unavailable;
- keep a retryable open loop when the user can provide required input.

Provider failures, stack traces, retry history, model errors, raw operation
errors, and internal error strings remain outside chat memory.

### 10.4 Cancelled or superseded work

An explicit user cancellation closes the corresponding open loop and active
goal when applicable. A new explicit goal supersedes the previous singleton
goal but preserves provenance. Physical deletion is not required for normal
lifecycle transitions.

## 11. Artifact architecture

### 11.1 Registry versus memory

Two records have different responsibilities:

```text
chat_artifact_references
  artifact_id -> authorized target identity and safe file metadata

chat_memory_items(kind=artifact_ref)
  artifact_id -> conversational role, aliases, recency, source turn/run
```

The registry is authoritative. Chat memory must not duplicate bucket, storage
key, presigned URL, file bytes, full extracted content, or access policy.

### 11.2 Trusted artifact sources

Only runtime-verified or application-owned references may be registered from a
run:

- attachments validated for the current user message;
- generated files returned by `ArtifactWriter`;
- verified artifacts in runtime task results;
- collection/template/export targets resolved through the canonical artifact
  service;
- artifacts already present in the chat registry and re-used by a successful
  operation.

An artifact ID mentioned only in LLM text, agent narrative, planner output, or
an unverified task output is rejected.

### 11.3 Artifact outcome projection

Each artifact outcome contains at most:

```text
artifact_id or verified target descriptor
file_name
content_type
size_bytes
role = input | generated | referenced | transformed
producer task/entity reference?
source_turn_id
source_run_id
derived_from_artifact_ids[]
safe label?
```

`snippet` may be held only in the current turn's bounded attachment context.
Long-lived chat memory should not retain file content. A later turn calls
`file.read` or another canonical operation after re-authorization.

### 11.4 Registration flow

1. Projector selects only verified artifact outcomes.
2. Reducer normalizes nested and flat runtime artifact shapes into one DTO.
3. `ChatArtifactReferenceService` confirms an existing chat reference or
   registers a target through a supported provenance adapter.
4. Reconciler creates or touches the conversational `artifact_ref` item.
5. At next read, registry resolution revalidates ownership, RBAC, and storage
   availability.

### 11.5 Deletion and unavailability

If `file.delete` removes an artifact, the artifact registry applies its
canonical deletion semantics and chat context closes the corresponding
`artifact_ref`. If an external target disappears or access is revoked, the
reference is omitted from runtime context and marked unavailable/closed. The
old metadata snapshot must never make it usable.

## 12. Plan and task outcomes

### 12.1 Plan ownership

`runtime_plans`, `runtime_plan_tasks`, and `runtime_task_attempts` remain the
only execution-control state. Chat memory never stores an executable plan and
never resumes work by replaying a stored memory payload.

### 12.2 Allowed projection

When useful for a later turn, chat context may retain:

- opaque `plan_id` and final revision;
- active user objective;
- bounded user-visible work items;
- completed/blocked/cancelled status;
- safe outcome summary already accepted by runtime;
- explicit remaining limitation;
- references to verified artifacts;
- an open clarification or confirmation.

It must not retain:

- planner prompt or reasoning;
- arbitrary planner instructions;
- tool arguments;
- dependency payload bodies;
- raw task result JSON;
- retry/attempt history;
- unpublished partial outputs;
- IDs invented by a model.

### 12.3 `task_result_ref`

A task-result reference is appropriate only if the result remains relevant to
future dialogue. It has the shape:

```text
plan_id
task_entity_id
outcome
safe_summary
artifact_ids[]
completed_at
source_run_id
```

The safe summary comes from a runtime-owned bounded result or final synthesis
receipt. It is not copied from raw journal data.

Task-result references are persisted as bounded, provenance-backed context
items. Their configured default limit is 20 and their default TTL is 30 days.

## 13. Error and limitation projection

Errors have three separate surfaces:

| Surface | Content |
| --- | --- |
| Runtime journal/application logs | Operator diagnostics according to logging/redaction policy |
| Chat message/SSE | Stable error code and user-safe message |
| Chat context | Only a continuation-relevant limitation or blocked state |

Chat context may store:

```json
{
  "kind": "open_loop",
  "status": "blocked",
  "reason_code": "missing_authorization",
  "user_message": "Для продолжения нужен доступ к проекту ABC",
  "retryable_by_user": true
}
```

It may not store `operator_message`, exception class, traceback, raw provider
body, tool arguments, credentials, or journal error payload.

Technical transient failures should normally not survive the turn. A later
request may retry through normal runtime planning.

## 14. Message history and conversational continuity

Persisted messages remain the authoritative transcript. They are not copied
wholesale into chat memory.

At turn start, runtime receives:

1. the current user message;
2. a bounded recent dialogue tail;
3. the typed chat context snapshot;
4. independently resolved durable facts and document LongMemory as needed.

The recent tail preserves exact wording. The snapshot preserves the stable
working state after older messages leave the tail.

`recent_anchor` is a bounded structured bridge beyond the recent dialogue tail:

```text
last_user_intent
last_assistant_outcome
current_referents[]
source user/assistant message ids
```

No broader conversation summary is part of the active chat-context contract.

## 15. Consumer-specific projections

No LLM role receives the entire persistence payload.

### 15.1 TurnPreflight

Receives:

- current user request;
- recent dialogue tail;
- focus/project context;
- active goal;
- term bindings;
- safe artifact candidates;
- open loops and uncertainties;
- confirmed durable facts through their existing bounded projection.

Its prompt contract must explicitly authorize these inputs and define the
precedence rule. It must clarify unresolved ambiguity rather than guess.
TurnPreflight is the only role that automatically receives the dialogue tail
and chat snapshot. Neither snapshot is copied into `facts_context` or planner
memory. It compiles a self-contained `TaskBrief`, preserving names, conditions
and constraints, resolving conversational references through
`resolved_references` (`expression`, `meaning`, `source_message_ids`) and
retaining unresolved questions in `uncertainties`.

### 15.2 Planner

Receives:

- normalized `TaskBrief`;
- the current task's goal and effective scope;
- authorized artifact metadata;
- constraints and uncertainties selected by preflight;
- normal durable memory context.

The exact current request remains in `run_context.original_request`. Preflight
selects source material through `TaskBrief.evidence_refs` and historical messages
through `TaskBrief.message_refs`. Selected messages appear as data in
`run_context.conversation_materials`; history reads never become source evidence
merely because the read succeeded. Unknown selected references are reported in
`unavailable_material_refs`. The planner can explicitly read more history when
its brief is insufficient.

It does not receive the automatic raw transcript. It never treats a previous plan reference
as an instruction to execute without producing a new valid iteration.

### 15.3 Agent

Receives only task-relevant context selected mechanically from the snapshot:

- effective project;
- active objective relevant to its task;
- selected artifact references;
- applicable term bindings and explicit constraints;
- dependency outputs owned by the current plan.

Agents receive task-relevant inputs and dependencies from the planner, plus the
current request and constraints. The planner selects applicable resolved references
and passes them in task inputs/instructions. No previous chat messages
are injected as assistant/user messages. A task's own working transcript still
survives its pause/resume checkpoint. If historical text is needed for an agent's
task, the planner passes the selected material explicitly in task inputs.

### 15.4 Synthesizer

Direct synthesis receives `SynthesisBrief`, `direct_answer_draft` and explicitly
selected evidence/messages. It does not receive the complete chat snapshot.

Planned synthesis remains grounded in completed reports, accepted partial
outputs, verified artifacts, limitations, and the final synthesis brief. It
does not independently reinterpret historical context.
The final `SynthesisBrief.evidence_refs` and `message_refs` select additional
source/dialogue material. Historical messages can support rewriting or comparison,
but do not prove current external state or successful execution. The stored
`RunContext` retains the original snapshot and dialogue for continuity; its LLM
projection uses an allowlist and excludes prior answers, delivery cache and
unselected material. The full preflight brief is checkpointed with the run and
reused for planner/agent continuations instead of a generic continuation brief.

## 16. Bounds, retention, and staleness

All limits come from configuration, not embedded prompt assumptions.

Configured default bounds and lifecycle:

| Kind | Active limit | Default lifecycle |
| --- | ---: | --- |
| `scope` | 1 | Until explicit switch or chat deletion |
| `goal` | 1 | Until completed, cancelled, or superseded |
| `term_binding` | 20 | TTL 90 days; touch on reuse |
| `artifact_ref` | 50 | Until deletion/unavailability; bounded prompt selection |
| `open_loop` | 5 | Blocked items expire after 30 days |
| `decision` | 10 | Until superseded or chat retention cleanup |
| `recent_anchor` | 1 | Replaced each completed/paused turn |
| `task_result_ref` | 20 | TTL/LRU; default TTL 30 days |

Database reads must apply per-kind limits. A single global `ORDER BY updated_at
LIMIT N` is invalid because many recent artifacts could evict the current
scope or goal from the snapshot.

`expires_at <= now()` is treated as expired even if a cleanup job has not yet
changed the stored status.

## 17. Idempotency, ordering, and concurrency

### 17.1 Idempotency

Applying the same `(chat_turn_id, projection schema version)` more than once
must produce the same active state. Artifact registration relies on canonical
target uniqueness; context operations use stable item keys and source refs.

### 17.2 Ordering

Every write is guarded by chat revision or monotonic turn order. An async
compactor for turn 10 may not overwrite a deterministic or compacted item from
turn 11.

Allowed outcomes of a stale compactor are:

- merge a collection item if its source remains valid and it does not replace
  newer state;
- skip with a stale-revision diagnostic;
- rebase explicitly against the newest snapshot and revalidate.

Silent last-write-wins is forbidden for singleton context.

### 17.3 Concurrent turns

If the product permits concurrent turns in one chat, reconciliation serializes
snapshot revisions with a row lock or compare-and-swap update. Each turn keeps
its own runtime execution; only validated operations enter the next revision.

### 17.4 Transaction boundaries

- Message, turn, deterministic context, and registry mutations should commit
  under one application-owned transaction where practical.
- Repositories and reconcilers flush but do not commit.
- Optional compaction uses an isolated worker transaction and revision guard.
- Artifact storage and database mutation retain the retry/idempotency rules of
  the canonical artifact services.
- A failed optional compactor never rolls back an already delivered answer.

## 18. Security and privacy

1. Chat access is resolved before reading context.
2. Sandbox branch identity is part of the context scope.
3. Artifact references are re-authorized on every use.
4. Tenant ID alone is not treated as a complete access policy; effective RBAC
   and sharing rules apply.
5. Prompts, reasoning, credentials, secrets, raw tool I/O, and tracebacks are
   prohibited.
6. Context payloads pass the runtime redactor before persistence when they
   contain model-produced text.
7. Artifact content is not persisted in chat memory.
8. Source references do not grant access to their targets.
9. User-visible context must not expose opaque internal IDs unless a product
   surface explicitly needs them.
10. Chat deletion cascades chat-local context and artifact references according
    to the existing ownership rules; it does not delete external collection
    sources.

## 19. Sandbox behavior

Sandbox and chat use the same context contracts but different persistence
scope.

- A sandbox-backed chat includes `sandbox_branch_id` in every lookup and key.
- Branch A never reads or mutates Branch B context.
- A run freezes the effective branch context before execution.
- Sandbox may inspect the resulting context delta as a typed semantic model,
  not by parsing journal events.
- Sandbox raw journal remains a separate operator surface.
- Branch context never publishes durable user/tenant facts.

Promotion of sandbox chat context into a normal chat or durable memory is not
part of the first implementation and requires an explicit product contract.

## 20. Observability

Chat-context processing has its own safe diagnostics but no second event
journal.

Recommended structured metrics/logs:

```text
chat_context_snapshot_load_total{status}
chat_context_reconcile_total{action,kind,status}
chat_context_compaction_total{status}
chat_context_stale_write_total{kind}
chat_artifact_registry_projection_total{status,target_kind}
chat_context_snapshot_items{kind}
```

Application logs include chat/turn/run IDs, revision, item counts, status, and
duration. They exclude payload bodies and secrets.

When sandbox/full observability is enabled, runtime may emit a bounded status
event such as `chat_context_reconciled` containing counts and revision only.
That event observes the completed business operation; it is not the input to
the operation.

## 21. Failure and degradation policy

| Failure | Required behavior |
| --- | --- |
| Context read fails | Continue with recent dialogue and empty chat snapshot; emit safe diagnostic |
| Artifact re-authorization fails | Omit artifact without writing during the read; an explicit lifecycle writer may close it later; do not fail unrelated answer |
| Deterministic reconciliation fails before commit | Fail/rollback the owning persistence transaction according to chat finalization contract |
| Optional compactor fails | Keep deterministic context; answer remains successful |
| Compactor output invalid | Reject all invalid operations; no partial raw write |
| Stale revision | Skip or explicit rebase; never overwrite newer singleton state |
| Registry registration fails | Artifact is not advertised as available in future context; preserve the already validated delivery result according to artifact contract |
| Runtime fails before outcome | Preserve existing snapshot; add only a safe continuation-relevant limitation if available |

Context quality degradation is preferable to invented context. Empty context is
safer than a guessed project, file, or completed action.

## 22. Current implementation modules

- `app/runtime/context_outcome.py` projects safe outcomes from runtime state.
- `app/services/chat_context_contracts.py` defines typed context contracts.
- `app/services/chat_context_service.py` reads and writes chat context.
- `app/services/chat_context_reducer.py` creates deterministic context changes.
- `app/services/chat_context_compactor.py` proposes bounded topic updates.
- `app/services/chat_context_reconciler.py` validates and persists updates.
- `app/repositories/chat_context_repository.py` owns typed database access.
- `app/services/chat_artifact_reference_service.py` registers and authorizes
  chat artifact references.

## 23. Current implementation

The following contract requirements are implemented and covered by focused
service/runtime tests:

- deterministic writers for scope, goal, open loops, safe limitations,
  recent anchor, verified artifacts, term bindings, and bounded task-result
  references;
- prompt-authorized chat context and recent dialogue for TurnPreflight, direct
  synthesis, planner, and mechanically selected task-agent inputs;
- normalized runtime-verified artifact DTOs and fresh registry
  re-authorization; unavailable references are omitted by a read-only
  snapshot and may be retired only by an explicit lifecycle writer;
- per-kind bounded snapshot reads (singleton scope/goal/anchor cannot be
  evicted by recent artifacts), TTL handling on both read and write paths, and
  scheduled expiry cleanup;
- source turn/message/run/artifact/glossary/task provenance resolved against
  the owning chat/turn, canonical vocabulary, partial active-row uniqueness,
  revision/CAS guards, and stale compactor rejection;
- branch-scoped sandbox snapshots and outcome handoff through a hidden
  sandbox chat turn whose paused, completed, failed, and cancelled lifecycle
  is synchronized with the sandbox run;
- user-safe inspection/reset controls and context metrics; and
- removal of the legacy summary path from chat-context consumers, leaving one
  active source of conversational working state.

The document's non-goals remain intentional exclusions, not deferred gaps.

## 24. Current invariants

The current contract preserves these invariants:

1. Raw runtime journal data never enters chat memory.
2. Chat memory is chat-local and separate from durable facts and project
   knowledge.
3. Artifact registry identity/access and conversational artifact meaning are
   separate responsibilities.
4. Only runtime-verified artifacts may be registered from a run.
5. Plans remain control-plane state; chat memory stores at most bounded outcome
   references.
6. Only safe, continuation-relevant limitations survive a turn; technical
   diagnostics do not.
7. Deterministic context updates cannot depend on an asynchronous LLM worker.
8. Every inferred update is source-linked, validated, bounded, and revision
   guarded.
9. Every artifact is re-authorized when used.
10. Ambiguity produces clarification, not guessing.

## Turn file/context implementation since 0195

The same original request and explicit constraints reach all runtime stages. Root roles
can explicitly page older messages through `chat.history.read` with a `before_message_id`
cursor; this is a bounded transcript read, not journal replay or semantic search.
Sandbox uses frozen branch history rather than reading a shared hidden-chat transcript.

Run context is checkpointed independently of planning. Evidence carries a stable ID,
owner, operation arguments and original source material; memory groups retain their scope.
Planner chooses `evidence_refs` for final synthesis rather than implicitly forwarding its
whole search history. File descriptions in chat context are marked `model_inferred`.

Deterministic outcome reconciliation runs on the owning request session before chat
finalization commits. It is no longer part of the detached post-final task. Only fact
writeback and optional semantic compaction remain asynchronous. Failure of mandatory
reconciliation prevents a successful final response; the transport rolls back pending
writes. The next turn accepted after `final` observes the committed answer and context.
