# Runtime Event Journal

## Purpose

`runtime_execution_events` is the sole persisted observability contract for
runtime. It records operator-meaningful facts from start to terminal state;
SSE transport and old trace/run tables are not alternate histories.

## Event identity and hierarchy

Every row has an event `id`, `run_id`, monotonic `sequence`, `event_type`,
`occurred_at` and a redacted JSON `payload`.

- `entity_type` / `entity_id` identify the entity the event describes.
- `parent_entity_type` / `parent_entity_id` describe containment.
- `caused_by_event_id` links a response, retry or rejection to its initiating
  event. It is not a substitute for the parent entity.

The canonical sandbox presentation hierarchy is:

```text
run → orchestrator → plan_revision → step → agent_execution → LLM/tool/interaction/error/snapshot
```

`plan_revision` is the operator-facing trace entity for one planner decision
and its execution wave. `task` and `attempt` remain persisted runtime
control-plane entities: task lifecycle events retain their plan parent and
carry explicit task/attempt references to the executor run. They are not a
second competing containment hierarchy for the trace UI.

The current event/entity names `planner_iteration` and `iteration` are legacy
wire terminology for `plan_revision` until the planned breaking rename. The
trace projector may map those canonical rows to `plan_revision`, but new
emitters must not create a parallel hierarchy. Revision and step ids are stable
strings scoped by root run. Executor ids are UUIDs. Parallel executor runs
receive independent immutable logger scopes.

For the sandbox execution graph, an `agent_start` payload creates the
`agent_execution` entity and also carries the
operator-facing executor identity: `executor_type`, `executor_name`,
`agent_slug`, and the task title/objective. `llm_request`/`llm_response` share
one `llm_call` entity; `tool_call`/`tool_result` share one `tool_call` entity.
Both call entities are direct children of the executor run that initiated them.
This is an explicit journal contract, not a frontend inference rule.

Each user-visible LLM request has one stable `llm_call_id` from its initial
`llm_request` through the terminal response with an action or answer. Retries
reuse that ID and retain the same LLM parent; their `protocol_retry` payload
also carries the ID and the `logical_llm_call_id`. A later agent decision after
a tool result starts a new request and receives a new ID. Consumers must not
reconstruct retry chains from adjacent sequence numbers, timestamps, or a
shared executor parent. Historical rows that used a different ID per retry
remain compatible through their explicit shared `logical_llm_call_id`.

When native tool calling is unavailable, the failed native attempt still emits
a terminal `llm_response`; the plaintext-protocol fallback emits a correlated
`protocol_retry` and reuses the same call ID. A fallback must never leave its
`llm_request` in a running state.

Every started plan revision, step and executor has a terminal event. Step start
contains goal/intent, inputs and risk; step end contains outcome, summary and
sufficiency. Executor end contains a safe result summary, `completion_kind`,
`sufficient_for_phase`, missing inputs/needs, attachments/artifacts, output
preview and retry/error classification.

Plan creation and revision events are owned by the planner executor run that
produced them (and therefore are also contained by its plan revision). Their payload
includes `revision_before`, `revision_after`, mode/trigger and redacted plan patch.
`planner_decision` records the normalized semantic action; `protocol_retry`
records only retry number and safe error classification. Task lifecycle rows
keep their plan parent and include the task/attempt references used by the
corresponding executor run.

Preflight is represented by `preflight_started`, terminal
`preflight_completed`/`preflight_failed`, and a redacted capability/RBAC/limit
snapshot. An agent-triggered extraction has `extraction_started`, terminal
`extraction_completed`/`extraction_failed`, and is a child of its `tool_call`.
Standalone RAG ingest events are not runtime journal children.

The synthesizer owns a `synthesis_run`. Its final operator result is the
`final_answer_marker` whose parent is that synthesis run; the following
transport `final` frame is not a second journal result. This also applies to
verbatim and agent-result short-circuits. Frontend projection follows these
explicit parent links only and must not select nearby plan, extraction or final
events by sequence range.

## Levels

The level is resolved before payload construction.

| Level | Persisted events |
| --- | --- |
| `none` | nothing |
| `error` | `error` and rejected budget/limit/RBAC decisions |
| `brief` | lifecycle, planner decision summaries, task/attempt outcomes, RBAC/limit/budget snapshots, final status and errors |
| `full` | all allowed events, including LLM/tool request-response and retries |

`brief` stores metadata plus hashes/lengths for heavy values. `full` can store
request/response bodies, but always redacts secrets, credentials, DSNs and
hidden chain-of-thought.

## Chat and sandbox

- Sandbox forces `full`, persists the root run, and streams the same canonical
  events after persistence. The journal assigns `event_id` and `sequence` in
  the same DB append that creates the row; SSE and replay must use those exact
  values. Transport `delta` and `stop` are never journal records; debug stack
  traces remain application-log diagnostics.
- Chat never persists the root pipeline, planner, orchestrator or memory tail.
  A selected agent may create an independent executor journal only when its
  configured level is not `none`. Chat never streams diagnostic events or raw
  journal payloads.

## Safe progress transport

`RuntimeProgressStreamer` is attached to `RuntimeEventLogger`; it is not a
second event system or writer. From every admitted semantic event it may make a
small redacted progress projection with `run_id`, phase, kind, description and
status. The description uses a bounded planner/agent intent when present and a
mechanical fallback otherwise; prompts, reasoning, tool arguments and tool
results are forbidden.

`RuntimeLogContext` separates `stream_logs` from `stream_progress`:

- sandbox uses `full`, streams both raw tail events and safe progress;
- chat root uses `none`, persists no root row and streams only safe progress;
- agent scopes retain the configured level. `none` exposes no agent detail,
  `error` exposes errors, `brief` lifecycle/intents, and `full` also exposes
  LLM/tool progress.

The shared Redis runtime-tail channel carries `runtime_progress` messages.
`ChatStreamService` subscribes before a pipeline starts and maps only these
messages to typed `status/runtime_progress` SSE. It does not replay progress
after reconnect and does not expose raw tail messages to chat.

## Public API transport

There is no public `/runtime` plan, event, or timeline read surface. Persisted
plans remain runtime control-plane state; they are not a frontend contract.

Sandbox is the only full-journal reader. Its session-scoped run detail returns
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

Chat SSE is limited to `user_message`, `chat_title`, `status` (only
`runtime_progress`), `delta`, `pause`, `final`, `cached`, `error`, and `done`.
`pause` is the sole HITL transport frame and carries
`run_id`, `reason`, `action`, `context`, and `contract_version`.

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
- RBAC, budget, limit, plan and checkpoint state are snapshots owned by the
  entity making the decision.
- A persisted plan node may be `agent` or `planner`. A planner node is an
  explicit graph checkpoint: its lifecycle is visible as a task with
  `kind=planner`, followed by a planner iteration with `iteration_type=checkpoint`.
  It is not an agent execution, confirmation gate or user-input interaction.
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

## Prohibited

Do not add a second trace builder, compatibility mapper, or a second event
table. Do not persist SSE deltas/stop/done merely because they crossed
transport.

Do not create a per-pipeline sequence, envelope stamper, observation writer or
direct `RuntimeExecutionEvent` writer. Every semantic event goes through the
root `RuntimeEventLogger` or immutable scoped logger; only it may assign identity, sequence,
redaction and tail publication.
