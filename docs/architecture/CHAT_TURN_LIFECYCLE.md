# Chat Turn Lifecycle and Runtime Stages

## Persisted lifecycle

`chat_turns.status` is the authoritative lifecycle for one logical user turn.
Revision `0206` normalizes persisted values to:

| Status | Meaning | Terminal |
| --- | --- | --- |
| `running` | The turn is executing, including a resumed continuation | No |
| `waiting_input` | The turn is paused for a user answer | No |
| `waiting_confirmation` | The turn is paused for an explicit confirmation | No |
| `completed` | The assistant answer was persisted successfully | Yes |
| `failed` | Execution or final persistence failed | Yes |
| `cancelled` | An explicit Stop or paused-run cancel ended the turn | Yes |

Before migration, stored `started` and `resumed` are read as `running`; stored
`paused` is read as `waiting_input` or `waiting_confirmation` from
`pause_status`. New writes use canonical values. The migration backfills those
aliases and adds `heartbeat_at`, initialized from `started_at`. Downgrade maps
`running` back to `started`, and both waiting states back to `paused`.

The API projects lifecycle status independently of runtime stage. `GET
/chats/{chat_id}/active-run` returns the active run identity, canonical status,
and the latest safe stage activity when available. `GET
/chats/{chat_id}/paused-run` returns an explicit waiting checkpoint. Plan and task
statuses remain separate control-plane state and are not rewritten by this
contract.

The runner updates `heartbeat_at` every 30 seconds while the turn is active.
The 15-minute lease detects a crashed API process or a dead runner; it no longer
expires a live, long-running turn merely because `started_at` is old. Execution
ownership is still process-local, so heartbeat does not recover work after a
process crash. The lease is stale detection, not durable job recovery.

## Stage and activity

Lifecycle status answers “what state is the turn in?” Stage answers “what part
of execution is active?” Chat stages are stable and separate from planner/task
statuses:

- `preparing`
- `planning`
- `executing`
- `synthesizing`
- `finalizing`

The named SSE `stage` event contains `run_id`, normalized stage, action kind,
bounded user-safe description, and optional activity outcome. The activity
outcome describes that runtime action only; it is not the ChatTurn lifecycle.
Descriptions use static, bounded text and never include prompts, tool arguments,
tool results, planner task text, or agent summaries.

The shared internal Redis runtime-tail envelope remains `runtime_progress` for
sandbox compatibility. It carries additional `chat_stage`, `action`, and
`outcome` projection fields consumed by chat. Runtime Plan, Iteration, Task, and
Attempt status vocabularies are unchanged.

## SSE lifecycle and reconnect

- `run_started` marks a newly opened execution, including a deliberate resume.
- Reattaching an observer starts with a `state` snapshot; it does not emit a
  second `run_started`.
- `state` carries a canonical lifecycle status and optional stage snapshot.
- `pause`, `final`, `error`, and `cancelled` describe lifecycle outcomes and
  carry the corresponding canonical status where applicable.
- `done` means only that this SSE response ended. It is not a turn status.
- `delta` is an answer-rendering optimization. `final` is authoritative answer
  content and includes `completed` or `failed` status.

Ordinary SSE detach/navigation only removes the observer. Stop sends the
explicit cancel command to the execution owner. Redis chat events remain
pub/sub without replay: reattachment restores the persisted lifecycle and latest
stage snapshot, but does not reconstruct already-published deltas or earlier
activity history. The UI reloads persisted messages on terminal errors and
cancellation.

## Global chat status stream

`GET /api/v1/chats/status-events` is an authenticated application-level SSE
connection. It returns one `snapshot` event on connection and sends a new full
snapshot when the database projection changes. Each snapshot contains the
latest turn for each chat owned by the authenticated user, with only
`chat_id`, `run_id`, lifecycle `status`, optional canonical `stage`, and
`updated_at` plus optional `stage_updated_at`. Lifecycle time comes from the
persisted turn; stage time is present only when a Redis stage snapshot exists.
It never carries message content, prompts, errors, or stage descriptions.

The stream polls the database every two seconds instead of publishing from
individual lifecycle writers. That keeps the database as the source of truth
and avoids a transaction/Redis publication race. Every reconnect starts with a
fresh database snapshot, so missed updates do not leave the client stale. The
stage is an optional allowlisted projection from the runner's existing Redis
stage snapshot; missing Redis data only removes that optional field.

The frontend opens the stream after authentication, aborts it on logout or
unmount, retries with bounded backoff, and stores the latest snapshot in a
user-scoped query cache. A transition to `completed` produces an in-app toast.
Opening a chat still uses the regular active-run and message-history endpoints;
the global channel is not an answer transport. The database polling interval
sets the expected upper bound for status update latency while connected.

`ChatTurnState` is an in-memory execution-phase tracker only. `RuntimeTurnState`
has a lifecycle projection with the same canonical vocabulary. Neither replaces
the persisted `ChatTurn` lifecycle.
