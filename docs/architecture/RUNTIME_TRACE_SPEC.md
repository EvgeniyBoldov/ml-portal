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

Sandbox hierarchy is:

```text
run → orchestrator → iteration → step → agent_execution → LLM/tool/interaction/error/snapshot
```

Iteration and step ids are stable strings scoped by root run. Executor ids are UUIDs.
Parallel executor runs receive independent immutable logger scopes.

For the sandbox execution graph, an `agent_start` payload creates the
`agent_execution` entity and also carries the
operator-facing executor identity: `executor_type`, `executor_name`,
`agent_slug`, and the task title/objective. `llm_request`/`llm_response` share
one `llm_call` entity; `tool_call`/`tool_result` share one `tool_call` entity.
Both call entities are direct children of the executor run that initiated them.
This is an explicit journal contract, not a frontend inference rule.

Every started iteration, step and executor has a terminal event. Step start
contains goal/intent, inputs and risk; step end contains outcome, summary and
sufficiency. Executor end contains a safe result summary, needs, attachments,
output preview and retry/error classification.

Plan creation and revision events are owned by the planner executor run that
produced them (and therefore are also contained by its iteration). Their payload
includes the revision, mode/trigger and redacted plan patch. Task lifecycle rows
keep their plan parent and include the task/attempt references used by the
corresponding executor run.

Preflight is represented by `preflight_started`, terminal
`preflight_completed`/`preflight_failed`, and a redacted capability/RBAC/limit
snapshot. An agent-triggered extraction has `extraction_started`, terminal
`extraction_completed`/`extraction_failed`, and is a child of its `tool_call`.
Standalone RAG ingest events are not runtime journal children.

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

Chat SSE is limited to `user_message`, `chat_title`, `status` (only
`runtime_progress`), `delta`, `pause`, `final`, `cached`, `error`, and `done`.
`pause` is the sole HITL transport frame and carries
`run_id`, `reason`, `action`, `context`, and `contract_version`.

## Calls, snapshots and workers

- LLM/tool calls are a request event and a response/result event. The latter
  contains duration and `caused_by_event_id` of the request.
- RBAC, budget, limit, plan and checkpoint state are snapshots owned by the
  entity making the decision.
- Worker boundaries transport JSON `RuntimeLogContext`, never a live logger or
  database session. The worker reconstructs a logger with a session factory,
  retains `run_id`, and uses task attempt/idempotency keys for retries.

## Prohibited

Do not add a second trace builder, compatibility mapper, or a second event
table. Do not persist SSE deltas/stop/done merely because they crossed
transport.

Do not create a per-pipeline sequence, envelope stamper, observation writer or
direct `RuntimeExecutionEvent` writer. Every semantic event goes through the
root `RuntimeEventLogger` or immutable scoped logger; only it may assign identity, sequence,
redaction and tail publication.
