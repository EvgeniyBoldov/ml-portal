# Chat Runtime Error Contract

## Scope

Contract defines how runtime failures are represented for:

- user chat stream,
- persisted assistant messages,
- admin/sandbox diagnostics.

## Event Contract (`SSE error`)

Execution failures inside graph planning may enter bounded partial-answer
finalization. `execution_interrupted` is an internal runtime event; it is not a
chat lifecycle status. The chat turn remains running until its persisted
terminal result is known. Technical plan failures remain in diagnostics. The
final answer reports supported findings and safe
limitations (time, execution budget, permissions or credentials); it does not
quote planner exceptions. Other interruptions are described as incomplete
processing, without inventing a time/budget cause. The finalization reserve is
one LLM call and `RUNTIME_FINALIZATION_TIMEOUT_SECONDS` (default 60 seconds).
If synthesis fails, runtime still sends a safe deterministic `final`. Cancellation
and explicit interaction pauses preserve their existing lifecycle.

- `type`: `"error"`
- `status`: `"failed"` lifecycle outcome
- `code`: stable machine code (`budget_exceeded`, `max_retries_exceeded`, `planner_failed`, `tool_unavailable`, `routing_failed`, etc.)
- `error`: user-safe message only (no traceback, no raw exception payload)

## Browser Stream Lifecycle

Initial sends and pause continuations use the same event consumer
(`domains/chat/chatStream.ts`) and UI update path (`hooks/useChatStreaming.ts`).
`delta` accumulates draft text; `final` supplies the authoritative message ID,
content, sources, attachments and lifecycle status, including responses without
any deltas. `state` is a lifecycle snapshot; `run_started` is sent only for a
new execution, while reattach starts with `state`. `done` only closes the SSE
transport. `stage` carries normalized execution stage plus action description
and optional activity outcome; it never changes the turn lifecycle.
`pause` retains the explicit interaction state, including a subsequent pause
during continuation. `cached` reloads persisted history. A rejected continuation
request keeps its existing pause available for retry.

EOF or `[DONE]` without `final`, `pause` or `cached` reports an interrupted
answer and preserves received draft text. A server `error` carries failed
lifecycle status; the client reloads persisted history instead of marking the
answer as a transport interruption. Cancellation may complete with
`[DONE]` alone. Stopping or switching chats invalidates the old stream's UI
updates; older history requests cannot overwrite a newly started answer.

The progress card shows the two most recent distinct descriptions, with the
previous description muted, and expands to at most ten events. Outcome icons
come only from `stage.activity.outcome`: `completed` is a green check; `failed`
or `error` is a red cross. This is the result of one runtime activity, not the
chat lifecycle. Missing or other outcomes have no icon. Neither event kind nor
transition to another stage implies success. Repeated adjacent activities
update their explicit outcome rather than discarding it with the duplicate
description.

## Persistence Contract (`assistant.meta`)

For failed/partial assistant messages:

- `runtime_status`: `failed | partial`
- `runtime_error_code`: normalized code
- `runtime_error_message`: user-safe message (for partial/failure UX)
- `runtime_run_id`: linked agent run id (when available)

## Diagnostics Contract (admin/sandbox)

Diagnostics may include operator-facing data:

- `code`
- `user_message`
- `operator_message`
- optional debug payload in trace/raw steps

These fields are shown in admin run page and sandbox inspector, not mixed into chat answer text.

## Safety Rules

- Runtime/internal exceptions never go into conversational prompt history.
- Raw exception strings are logged server-side only.
- Chat stream always emits sanitized user-facing errors.
