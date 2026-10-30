# Runtime Event Journal

## Purpose

`runtime_execution_events` is the sole persisted observability contract for
runtime. It records operator-meaningful facts from start to terminal state;
SSE transport and old trace/run tables are not alternate histories.

The journal is not an input to chat-context materialization. The separate
contract in [`CHAT_CONTEXT_MEMORY.md`](CHAT_CONTEXT_MEMORY.md) consumes a typed
runtime outcome projection and never scans, replays, copies, or summarizes raw
journal rows.

## Event identity and hierarchy

Every row has an event `id`, `run_id`, monotonic `sequence`, `event_type`,
`occurred_at` and a redacted JSON `payload`.

- `entity_type` / `entity_id` identify the entity the event describes.
- `parent_entity_type` / `parent_entity_id` describe containment.
- `caused_by_event_id` links a response, retry or rejection to its initiating
  event. It is not a substitute for the parent entity.

The canonical sandbox presentation hierarchy is:

```text
run → route_policy → turn_preflight → LLM call
                                  ├→ synthesis_run → final_answer_marker
                                  ├→ memory_recall → turn_preflight → LLM call
                                  ├→ interaction
                                  └→ planner orchestrator → planner_iteration → planner LLM call
                                                                ├→ task → attempt
                                                                ├→ step → agent_execution → LLM/tool/interaction/error/snapshot
                                                                └→ checkpoint
```

`route_policy` is a distinct pre-LLM recommendation entity. It records a
recommendation id, match status, rule/signals, an optional route/source hint and
a bounded explanation. Start metadata contains query/goal lengths and a query
hash rather than copying the dialogue. The policy entity always ends before
TurnPreflight starts for a new implicit turn; matched and unmatched outcomes
both proceed to TurnPreflight. A policy match is not a final route and never
creates a planner brief.

`iteration` is the operator-facing trace entity for one planner decision
and its execution wave. A planned `task` is the canonical executor node: it is
created in `waiting` state as soon as the proposal is applied, before an agent
starts. Attempts, steps and agent executions describe work performed for that
task and carry its linking IDs; they do not create a second task identity. A
`checkpoint` is the iteration's planned hand-off to planner or synthesis and
is also materialized before execution.

`planner_iteration_start` opens before the planner call. The matching
`planner_iteration_end` is emitted only after all schedulable tasks finish and
the checkpoint is decided (or when the iteration fails terminally). Thus the
iteration lifecycle covers the complete execution wave, not only generation
of the proposal.

The graph join contract is identifier-based. Consumers must not infer these
relations from sequence proximity, task titles, agent slugs or LLM payloads.

| Field | Meaning |
| --- | --- |
| `plan_id` | Persisted control-plane plan UUID. |
| `iteration_id` | Stable UUID of the planner iteration and task/checkpoint parent. |
| `task_id` | Human-readable planner-authored logical task key, unique within a plan. |
| `task_entity_id` | Stable opaque UUID of `(plan_id, task_id)`; canonical graph node ID. |
| `attempt_id` | Stable opaque UUID of `(task_entity_id, attempt number)`. |
| `step_id` | Stable opaque UUID of the concrete execution step. |
| `agent_execution_id` | Stable opaque UUID of the concrete agent run. |
| `checkpoint_id` | Stable opaque UUID of the terminal decision for one iteration. |

All task lifecycle events carry `plan_id`, `iteration_id`, `task_id` and
`task_entity_id`. Execution lifecycle events additionally carry every
applicable `attempt_id`, `step_id` and `agent_execution_id`. The same logical
entity always reuses the same opaque ID across its lifecycle.

`planner_iteration` identifies the iteration produced by one planner
invocation. It is not a revision or a second graph hierarchy. Iteration and
step ids are stable strings scoped by root run. Executor ids are UUIDs.
Parallel executor runs receive independent immutable logger scopes.

The planner's structured LLM call is a direct child of the
`planner_iteration` that it produces. For the sandbox execution graph, an `agent_start` payload creates the
`agent_execution` entity and also carries the
operator-facing executor identity: `executor_type`, `executor_name`,
`agent_slug`, and the task title/objective. `llm_request`/`llm_response` share
one `llm_call` entity; `tool_call`/`tool_result` share one `tool_call` entity.
Agent-owned call entities are direct children of the executor run that initiated them.
This is an explicit journal contract, not a frontend inference rule.

Root-role `memory.search` calls are direct children of the preflight orchestrator
or planner iteration. Their `tool_call` is admitted before execution and their
`tool_result` closes the same call on success, failure or cancellation, with
`duration_ms`. Server diagnostics emit `memory_search_started` and
`memory_search_finished` with the same call ID, actor and terminal status;
query text and search results are excluded from these logs.


Each user-visible LLM request has one stable `llm_call_id` from its initial
`llm_request` through the terminal response with an action or answer. Retries
reuse that ID and retain the same LLM parent; their `protocol_retry` payload
also carries the ID and the `logical_llm_call_id`. A later agent decision after
a tool result starts a new request and receives a new ID. Consumers must not
reconstruct retry chains from adjacent sequence numbers, timestamps, or a
shared executor parent. Historical rows that used a different ID per retry
remain compatible through their explicit shared `logical_llm_call_id`.

Each structured request records its attempt number and `input_tokens_estimate`
using the same serialization/token estimator as the outbound adapter, including
tool contracts and `response_format`. Streaming/agent requests use that
estimator too. Structured and streaming calls additionally emit
`status(stage=llm_context_allocated)` under their `llm_call`, with resolved model,
context window, estimated/reserved input, minimum output and available output.
When the adapter retries once with a corrected output limit after a provider
context rejection, it emits a second allocation snapshot with
`context_correction=true` and `status(stage=llm_transport_retry)` before that
transport attempt. It remains one logical LLM call; the correction is not a
second provider-billed usage row unless provider usage reports it.
This event precedes a local context rejection, so an emitted request does not
prove that the provider received it. Estimates for non-OpenAI tokenizers use
the documented fallback encoding and safety margin; they are not provider usage.
Usage accounting for chat, Sandbox, shadow and their worker continuations is a separate compact
projection from the diagnostic journal. LLM attempts retain provider token
counts when supplied; otherwise estimates are tagged `token_source=estimate`.
A terminal response without a token count is tagged `unknown`; request and
retry events do not overwrite a known source. Streaming synthesis uses
estimated tokens.
The platform currently stores no model price schedule, currency or monetary
amount, so token usage must not be presented as a money cost.

When native tool calling is unavailable, the failed native attempt still emits
a terminal `llm_response`; the plaintext-protocol fallback emits a correlated
`protocol_retry` and reuses the same call ID. A fallback must never leave its
`llm_request` in a running state.

Every started iteration, step and executor has a terminal event. Step start
contains goal/intent, inputs and risk; step end contains outcome, summary and
sufficiency. Executor end contains a safe result summary, `completion_kind`,
`sufficient_for_phase`, missing inputs/needs, attachments/artifacts, output
preview and retry/error classification.
On cancellation or an uncaught runtime failure, the journal closes open LLM,
tool and synthesis lifecycles with terminal failure/cancellation events before
closing the root run. The planner closes an interrupted task attempt, agent,
step, iteration and orchestrator as part of the same cancellation path.

The root `run_start` is written before platform configuration, RBAC, memory and
project-scope preparation. `status(stage=request_preparation_started)` and its
completion event bound that phase; completion carries duration and bounded
counts, not resolved private records. Failures in platform config, RBAC,
memory, scope or project preparation emit a safe error with the failed stage
and a terminal run status; cancellation closes the run as cancelled.

Iteration creation is owned by the planner invocation that produced it. Its
`plan_iteration_applied` payload includes trigger, terminal and a redacted
iteration proposal. Planner invocation lifecycle records the call itself;
there is no patch/revision decision event. Immediately after it, one
`task_planned` event is emitted per proposal task and one `checkpoint_planned`
event is emitted for the proposal terminal. `protocol_retry` records only
retry number and safe error classification.

`checkpoint_planned` carries `declared_next=planner|synthesis` and
`status=waiting`. When the scheduler actually crosses that checkpoint it emits
`checkpoint_decided` with the same `checkpoint_id`, `declared_next`,
`effective_next` and a machine-readable `reason`. A failed task can therefore
change a declared synthesis hand-off to `effective_next=planner`; the frontend
must update that checkpoint only from this event, not directly from an agent
error. Independent tasks may still run between the error and the decision.

`turn_preflight` is the final root routing entity for new implicit turns,
regardless of the root policy match. Its LLM input includes the typed
recommendation and the same bounded, provenance-bearing dialogue used for
reference resolution. Its terminal event carries only the safe route and
bounded brief/request metadata; `recall` is a separate child and the second
TurnPreflight invocation has the same root parent. A `clarify` decision owns a
root interaction and never creates a plan, task or agent.
`preflight_route_decision` records proposed and effective routes, the linked
policy recommendation id, policy disposition (`accepted`, `modified`,
`rejected`, or `not_applicable`) and a reason code on the TurnPreflight
orchestrator. Root recommendations are recorded on their own `route_policy`
entity. The legacy `memory_scope_selected.route` remains the effective route
only. Older journal rows with `route_policy_decision.route` remain legacy
records; absence of a TurnPreflight node in such a run is not repaired by the
frontend. Sandbox agent execution also emits `sandbox_override_snapshot`;
its configured publication/semantic overrides and effective resolved
operations are separate, while `suppressed_publication` explains configured
false values that correctly produced no operation.

Agent execution preflight is represented by `preflight_started`, terminal
`preflight_completed`/`preflight_failed`, and a redacted capability/RBAC/limit
snapshot. An agent-triggered extraction has `extraction_started`, terminal
`extraction_completed`/`extraction_failed`, and is a child of its `tool_call`.
Standalone RAG ingest events are not runtime journal children.

The synthesizer owns a `synthesis_run`. Its final operator result is one
`final_answer_marker` event with `entity_type=run`, `entity_id=<run_id>`, and
`parent_entity_type=synthesis_run`, `parent_entity_id=<synthesis_id>`. Its safe
payload contains `status=completed`, `producer`, `content`, `sources`, and
`attachments`. The following transport `final` frame is not persisted as a
second journal result. This also applies to direct preflight synthesis and
file delivery. Nested agent `final` frames remain transport-only and are not
run results. Frontend projection follows these explicit parent links only and
must not select nearby plan, extraction or final events by sequence range.

## Levels

The level is resolved before payload construction.

| Level | Persisted events |
| --- | --- |
| `none` | nothing |
| `error` | `error` and rejected budget/limit/RBAC decisions |
| `brief` | lifecycle, planner decision summaries, task/attempt outcomes, RBAC/limit/budget snapshots, final status and errors |
| `full` | all allowed events, including LLM/tool request-response and retries |

`brief` stores metadata plus hashes/lengths for heavy values. `full` can store
request/response bodies and applies `RuntimeRedactor` to secrets, credentials,
DSNs and dedicated hidden-reasoning fields. The trace records explicit model
outputs and runtime decisions, not a model's private reasoning process.

## Chat and sandbox

- Sandbox forces `full`, persists the root run, and streams the same canonical
  events after persistence. The journal assigns `event_id` and `sequence` in
  the same DB append that creates the row; SSE and replay must use those exact
  values. Transport `delta` and `stop` are never journal records; debug stack
  traces remain application-log diagnostics.
- Chat persists the root pipeline, planner, orchestrator and memory tail at
  `full`, using the same redacted canonical journal as Sandbox. Chat still
  streams only the safe progress projection; raw journal events are available
  only through admin runtime-trace read endpoints. The root journal includes
  selected agent subgraphs, so agent execution events are not written a second
  time as a separate chat trace.

## Safe progress transport

`RuntimeProgressStreamer` is attached to `RuntimeEventLogger`; it is not a
second event system or writer. From every admitted semantic event it may make a
small redacted progress projection. Chat adds a stable `chat_stage`, action
kind, safe bounded description and optional activity outcome to the existing
shared runtime-tail envelope. The chat description uses fixed safe text;
prompts, planner text, reasoning, tool arguments and tool results are forbidden.

`RuntimeLogContext` separates `stream_logs` from `stream_progress`:

- sandbox uses `full`, streams both raw tail events and safe progress;
- chat root uses `full`, persists diagnostics and streams only safe progress;
- Sandbox uses `full` and streams both journal and safe progress;
- agent scopes in chat are part of the root journal. Their configured
  observation level still controls user-facing progress, not journal admission.

The shared Redis runtime-tail channel keeps its `runtime_progress` envelope for
sandbox compatibility. `ChatStreamService` subscribes before a pipeline starts
and maps only safe activity to typed `stage` SSE. Chat stage keys are `preparing`,
`planning`, `executing`, `synthesizing`, and `finalizing`; an activity outcome
is not the chat lifecycle status. Chat does not replay progress after reconnect
and does not expose raw tail messages to chat.

## Public API transport

There is no public `/runtime` plan, event, or timeline read surface. Persisted
plans remain runtime control-plane state; they are not a frontend contract.
Administrators can list persisted chat traces at `/api/v1/admin/runtime-runs`
and page through `/api/v1/admin/runtime-runs/{run_id}?after_sequence=0&limit=500`.

Sandbox run detail returns
the ordered canonical journal rows, and its start/resume SSE stream emits named
frames: `run_started`, `progress`, `journal`, `delta`, `pause`, `final`,
`error`, and `done`. `progress` is the same bounded safe projection used by
chat and never participates in journal replay. A `journal` frame has exactly
the persisted row schema; no flattened payload or synthetic step format is
permitted.

`final` and `done` end the user-facing sandbox stream. Post-turn memory
writeback is dispatched after finalization and continues independently in the
same journal; its later facts/summary events are obtained by refreshing the
run detail, not by holding the answer stream open for `tail_finished`.

Chat SSE separates lifecycle (`state`, `run_started`, `pause`, `final`,
`cancelled`, `error`) from stage activity (`stage`) and answer rendering
(`user_message`, `delta`, `cached`). `done` closes the transport and is not a
lifecycle status. A reattached observer receives `state`, not a second
`run_started`.
`pause` is the sole HITL transport frame and carries
`run_id`, `reason`, `action`, `context`, and `contract_version`.

Chat execution is owned by an in-process `ChatRuntimeRunner` with a fresh DB
session; the POST/resume SSE response only observes the run through a per-run
Redis tail channel. Closing the SSE subscriber, including during chat
navigation, does not cancel the `ChatTurn`. Explicit Stop calls
`POST /chats/{chat_id}/runs/{run_id}/cancel`, which publishes a run-control
signal; the runner cancels the execution generator and the turn lifecycle writes
`cancelled`. Canonical persisted `ChatTurn.status` values are `running`,
`waiting_input`, `waiting_confirmation`, `completed`, `failed`, and `cancelled`;
legacy aliases are normalized by migration `0206` and remain readable by the
new service during rollout. See [Chat Turn Lifecycle](CHAT_TURN_LIFECYCLE.md).

`GET /chats/{chat_id}/active-run` provides the persisted active run identity,
canonical lifecycle status and latest safe stage snapshot,
and `GET /chats/{chat_id}/runs/{run_id}/events` attaches a new SSE observer.
The Redis tail is pub/sub and does not replay deltas emitted before attachment;
the final frame remains authoritative for complete answer content. The current
runner is process-local, not a durable worker: API process loss can interrupt
execution. Celery ownership and durable event replay remain future work.

The terminal `final` frame may carry deduplicated generated-file `attachments`.
Each attachment contains `artifact_id`, `file_name`, `download_url`,
`content_type`, and `size_bytes`. `download_url` is a relative API delivery
route that is authorized when opened; clients render these as attachment UI
below the answer and do not require the synthesizer to emit markdown links.

## Calls, snapshots and workers

- LLM/tool calls are a request event and a response/result event. The latter
  contains duration and `caused_by_event_id` of the request.
- Call payloads expose the operator lifecycle status: `running` while waiting
  for the provider/operation, `waiting_retry` during a scheduled retry,
  `failed` for a terminal error, and `completed` for a terminal result.
- A retry keeps the same `llm_call_id` or `tool_call` id. Its attempt metadata
  (`attempt`, `max_attempts`, `terminal`, `retryable`, `retry_after_ms` and
  `duration_ms`) is attached to the request/result and the corresponding
  `protocol_retry` event. Intermediate retryable errors are historical
  failures, not the final call status.
- Terminal LLM responses may include `result_kind`: `plan`, `tool_calls`,
  `answer`, `clarification`, `empty` or `error`. A `tool_calls` result means
  the LLM call completed; each linked tool call has its own lifecycle.
- Every LLM provider failure still closes its `llm_call` with an
  `llm_response` containing a safe `error_code`, `retryable` and provider
  status where available, followed by the canonical runtime `error`. Raw
  provider bodies and tracebacks remain application-log diagnostics.
- RBAC, budget, limit, plan and terminal-invocation state are snapshots owned by the
  entity making the decision.
- Planner agent filtering is recorded as `rbac_snapshot` on each
  `planner_iteration`, including iterations whose LLM call later fails. The
  planner orchestrator also retains the audit in its start context snapshot.
- Persisted plan tasks are always `agent` tasks and are trace graph nodes.
  Planner and synthesis are terminal checkpoint outcomes rather than tasks or
  agent executions.
- Worker boundaries transport JSON `RuntimeLogContext`, never a live logger or
  database session. The worker reconstructs a logger with a session factory,
  retains `run_id`, and uses task attempt/idempotency keys for retries.

### Post-turn memory components

`fact_extractor` and `fact_compactor` are `agent_execution` children of the
post-turn memory orchestrator. Whenever either component makes an LLM request,
its `llm_request` and `llm_response` are direct children of that component
execution and use the normal call lifecycle contract.

Each component emits one `status` event with
`stage=memory_component_result`. In addition to bounded counts and safe error
fields, its `facts` field is a typed operator projection. The extractor lists
only extracted candidates. The compactor lists only persisted changes; each
item has the fact's scope/kind/subject/value, `change_type`, status before and
after, confirmation support before/after and delta, and its compaction action.
Unchanged facts are omitted. This projection never contains raw evidence,
credentials or LLM reasoning. The inspector renders it through the canonical
trace projection; RAW remains the only generic journal-payload view.

Each candidate decision is additionally a canonical `status` event with
`stage=memory_candidate_decision`, owned by the corresponding component
`agent_execution`. It carries the component, phase, outcome, stable safe
reason code, run-local candidate IDs, bounded candidate/evidence projection,
optional compaction action and optional lifecycle transition. The worker emits
these records after the writeback checkpoint commits. Document semantic
extraction remains a RAG/admin diagnostic and is never a Sandbox writeback
child.

### Agent task inspection and duration

The shared Sandbox/admin trace projection reads task metadata from the plan and
`agent_start`. Missing task fields are also resolved from the latest owned
`status(stage=agent_context_snapshot).context_snapshot.inputs`: `inputs` contains
the actual task data, alongside `task_id`, `intent`, `instructions`, and `goal`.
Both the executor task tab and its containing step show the saved input object,
including an explicitly empty object. Standalone shadow runs need no persisted
plan or extra journal event to display their input. The journal remains unchanged.

Planner executor inspectors expose a `Вход` tab from the owning planner
orchestrator's `context_snapshot.inputs` (`goal` and the normalized `task_brief`).
The exact serialized planner LLM request, including execution ledger and the
RBAC-filtered available-agent catalog, remains available on that call's request
view. The `route_policy` inspector shows the advisory recommendation before
TurnPreflight; TurnPreflight's decision inspector shows the final route and
whether it accepted, modified or rejected the recommendation.

The result projection reads the owned `final` event when `agent_end` contains
only lifecycle metadata. A protocol-v2 completion is displayed through its
`structured_response` (or text `answer`), preserving empty objects/lists, false,
zero and null. Raw intermediate `llm_response` events are not final results.
Lifecycle errors remain authoritative even if the model claimed success.
This applies to both Sandbox and admin executor/step result tabs.

Run duration ends at `run_end`. Admin agent-run endpoints return only the closed
agent subgraph, excluding root run events; for such journals with no `run_start`,
duration ends at the last `agent_end` when all observed agent executions have
ended. An ongoing Sandbox run retains its live clock even after an agent ends.

## Prohibited

Do not add a second trace builder, compatibility mapper, or a second event
table. Do not persist SSE deltas/stop/done merely because they crossed
transport.

Do not create a per-pipeline sequence, envelope stamper, observation writer or
direct `RuntimeExecutionEvent` writer. Every semantic event goes through the
root `RuntimeEventLogger` or immutable scoped logger; only it may assign identity, sequence,
redaction and tail publication.

### Memory read snapshots

Runtime readers emit canonical `status` events with `stage=memory_context_used`:
TurnPreflight owns its orchestrator snapshot, the planner owns its
`planner_iteration` snapshot, the agent owns its `agent_execution` snapshot,
and synthesis owns its `synthesis_run` snapshot. `memory_context` is the actual
input passed to that reader, including task scope projection or synthesis
context bounding already applied by runtime. These events use the existing
journal/logger, admission levels, redaction, sequence and replay contracts.
Full logging retains the redacted payload; lower levels never expose its body.

Planner/task snapshots carry `memory_owner=planner|task`, `memory_owner_id` and
`reason=iteration_started|attempt_started|search_completed`. They record both
the restored memory at entry and the accumulated memory after each search.
Complete search responses remain separately attached to their original tools.
Sandbox executor inspectors use the latest recorded owner snapshot; they do not
add tool response passages to it again. Historical traces without owner snapshots
retain their existing projection from input and owned calls. They never inherit
an unrestricted run snapshot or another executor's read results. The Memory tab
separates user facts, tenant facts, glossary and long-term document knowledge;
projects and runtime facts have separate context sections. Facts and terms use compact shared tables with one record per row.
Document knowledge shows subject, content and kind in a table; its detail
viewer retains the complete JSON with provenance. Document knowledge is grouped
by scope, including empty groups and failures; zero summary counters are hidden.
Long values are bounded in rows and can be opened in the
shared read-only viewer. Memory tool response and Memory tabs reuse the same viewer.
An empty recorded snapshot is distinguished from an absent historical snapshot.
This is context made available to an executor, not proof that every item caused
a claim in its final answer. Candidate writeback remains separate.

Successful planner envelope recovery is recorded as a status on the same LLM call:
`stage=llm_response_normalized`, `attempt`, and `normalizations=[{path,operation}]`.
Operations are `infer_proposal_kind`, `move_proposal_kind_to_root`,
`unwrap_proposal_envelope`, and `wrap_legacy_proposal`. The record contains no
copied task data. The original model text stays in `llm_response`; the accepted
canonical iteration is persisted by orchestration. A normalization record is
not evidence that task execution has succeeded.
