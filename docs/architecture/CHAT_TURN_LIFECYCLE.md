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

The chat and sandbox runners update `heartbeat_at` every 30 seconds while they
own an active turn. The 15-minute lease detects a crashed API process or a dead
runner; it no longer expires a live, long-running turn merely because
`started_at` is old. Execution ownership is still process-local, so heartbeat
does not recover work after a process crash. The lease is stale detection, not
durable job recovery. Sandbox reconciliation also compares an active or waiting
companion turn with its linked `SandboxRun` and closes it when that run is
already terminal; a live run or a real waiting checkpoint remains active.

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

Browser restoration is guarded by a generation token: a late active-run lookup
cannot attach over a newer chat selection or send/resume operation. History
reload merges canonical server rows by message ID (server data wins for
duplicates), retains older pages, and preserves messages received while the
request was in flight plus placeholders belonging to the current active run.
A live assistant placeholder is retained across repeated pause/resume history
reloads when the server page does not yet contain that assistant row.

Run-control subscriber transport errors observed while execution is active are
execution failures, not explicit Stop: the runner cancels and awaits the
execution, then persists a failed turn with `chat_runtime_failed`. If execution
has already completed, a later control-channel failure is logged without
rewriting the completed turn or its terminal SSE event. Resume startup failures
before runner creation compensate the durable running claim by persisting a
failed turn and return HTTP 503 with RFC 7807 code
`CHAT_RUNTIME_START_FAILED` and details containing `run_id` and
`status: "failed"`; the client clears the terminal pause and reloads history
for this code. A transient resume HTTP rejection keeps the pause available for
retry. Once that compensation is confirmed persisted, the resume endpoint also
best-effort publishes `state(status=failed)`, `error(code=chat_runtime_start_failed)`,
and `done` to attached Redis observers, tagged with the failed execution's
`execution_id`. Each frame publish is bounded by
`CHAT_RUNTIME_START_FAILURE_NOTIFY_TIMEOUT_SECONDS` (default 1 second, range
0.1–10 seconds); failure or timeout for one frame does not suppress attempts
for the remaining frames. No terminal notification is fabricated when
compensation is not confirmed or a live runner still owns the run. Subscriber
resources are cleaned up on failed attach/start paths as well as normal stream
completion. For a same-run resume while the previous
process owner is finishing a pause, the runner waits for that owner, shielded
from caller cancellation and outside the global runner lock, then rechecks
ownership before creating the resumed task. Previous-owner cleanup cannot
delete the resumed owner's Redis marker.

Each runner execution has an internal `execution_id`, distinct from the stable
root `run_id`. The runner tags its Redis service events and `done` marker with
that ID. A resume observer accepts only its exact execution ID, so a queued
`done` from the prior continuation cannot close the new stream. The initial
duplicate-send observer remains unfiltered because a start request can reuse an
already-running task created by another command. A generic attach treats a
tagged `done` as a prompt to check current persisted chat/user/run status in a
fresh short-lived session; it ignores the marker if the run is still active
and closes only after the persisted run is terminal. The ID is internal to
event transport; public lifecycle frames keep the root `run_id`.

Stage snapshots are optional progress state: a Redis read failure is logged and
the corresponding state/attach frame simply has no stage snapshot. Once a
durable terminal outcome has been produced, a failure publishing a later
service event or finishing the runner tail is logged and cleaned up without
rewriting the persisted terminal status as failed or cancelled.

Optional context compaction dispatch happens after the terminal `final` or
`stop` event has been yielded. A detached task captures a bounded plain DTO,
loads the committed snapshot through a fresh database session, and publishes
through a worker thread. The request's live database session is not passed to
it; asynchronous snapshot loading remains on the event loop, while only the
synchronous broker publish is sent to a worker thread. Broker latency does not
block delivery of the terminal event. Dispatch is best-effort and bounded by
`CHAT_CONTEXT_COMPACTION_DISPATCH_LIMIT` (default 32, minimum 1); saturation
skips dispatch.

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
user-scoped query cache. The first snapshot seeds the client and does not
produce historical notifications. After that baseline, a newly observed chat
already in `completed` state is also treated as a completion, covering turns
that start and finish between polls. Completion notifications are deduplicated
per chat and run; when `run_id` is absent, lifecycle `updated_at` is the
fallback deduplication key. Completion of
the currently active chat is suppressed; completion in another chat produces
a toast and marks that chat as unread. The toast uses the chat name from the
existing chat-list cache when available, with a generic message otherwise.
Active chat and unread markers are session-local presentation state; entering
a chat clears its unread marker. Logout or listener teardown clears this
state. The latest status snapshot is kept separately in the user-scoped query
cache and remains the source for status presentation. In the chat list, active
execution uses a spinner and an unread completion uses a separate dot; these
indicators may coexist. The row layout remains fixed while they appear, and
the spinner respects the reduced-motion preference. Opening a chat still uses
the regular active-run and message-history endpoints;
the global channel is not an answer transport. The database polling interval
sets the expected upper bound for status update latency while connected.

`ChatTurnState` is an in-memory execution-phase tracker only. `RuntimeTurnState`
has a lifecycle projection with the same canonical vocabulary. Neither replaces
the persisted `ChatTurn` lifecycle.
