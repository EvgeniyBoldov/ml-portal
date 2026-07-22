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
run → orchestrator → iteration → executor_run → LLM/tool/snapshot
```

Iteration ids are stable strings scoped by root run. Executor ids are UUIDs.
Parallel executor runs receive independent immutable logger scopes.

For the sandbox execution graph, an `agent_start` payload also carries the
operator-facing executor identity: `executor_type`, `executor_name`,
`agent_slug`, and the task title/objective. `llm_request`/`llm_response` share
one `llm_call` entity; `tool_call`/`tool_result` share one `tool_call` entity.
Both call entities are direct children of the executor run that initiated them.
This is an explicit journal contract, not a frontend inference rule.

Plan creation and revision events are owned by the planner executor run that
produced them (and therefore are also contained by its iteration). Their payload
includes the revision, mode/trigger and redacted plan patch. Task lifecycle rows
keep their plan parent and include the task/attempt references used by the
corresponding executor run.

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
  events after persistence.
- Chat never persists the root pipeline, planner, orchestrator or memory tail.
  A selected agent may create an independent executor journal only when its
  configured level is not `none`. Chat never streams diagnostic events; admin
  reads those executor journals later.

## Calls, snapshots and workers

- LLM/tool calls are a request event and a response/result event. The latter
  contains duration and `caused_by_event_id` of the request.
- RBAC, budget, limit, plan and checkpoint state are snapshots owned by the
  entity making the decision.
- Worker boundaries transport JSON `RuntimeLogContext`, never a live logger or
  database session. The worker reconstructs a logger with a session factory,
  retains `run_id`, and uses task attempt/idempotency keys for retries.

## Prohibited

Do not add `AgentRun`, `AgentRunStep`, system LLM trace, trace-pack, runtime
trace builder, compatibility mapper, or a second event table. Do not persist
SSE deltas/stop/done merely because they crossed transport.
