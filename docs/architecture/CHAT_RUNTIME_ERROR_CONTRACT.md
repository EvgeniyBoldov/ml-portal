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

Chat runtime error normalization preserves recognized machine codes and maps
unknown codes to `unknown_runtime_error`; timeout classification is not inferred
from incidental message text as a tool timeout unless the code identifies a
tool timeout. Local operation-handler exceptions use
`operation_execution_failed` and a generic model-facing failure result while
exception details stay in operator logs.

The runtime preserves recognized codes from its runtime and LLM error catalogs
in chat error payloads, with role-appropriate safe user messages. A resume
startup failure compensated before runner ownership uses
`CHAT_RUNTIME_START_FAILED` in RFC 7807 `code`, with `{run_id, status:
"failed"}` details and HTTP 503. The frontend preserves problem `code`,
`details`, and `traceId`; this specific terminal startup code clears the pause
and reloads persisted history, while other HTTP rejections keep the pause for
retry. If a runner already owns the run, its lifecycle remains that runner's
responsibility. Confirmed startup compensation also sends a bounded,
best-effort failed state/error/done notification to observers; see
[Chat Turn Lifecycle](CHAT_TURN_LIFECYCLE.md) for its execution correlation
and per-frame timeout.

An unexpected Redis run-control subscriber failure fails the active execution
with `chat_runtime_failed`; it is not interpreted as the user's Stop command.
The execution task is cancelled and awaited, and the persisted turn becomes
`failed`. Explicit Stop remains `cancelled`. If resume startup fails before a
runner task is created, the durable active turn is failed as
`chat_runtime_start_failed` and the resume endpoint returns HTTP 503; an
already-started owner retains responsibility for its lifecycle.

Stage snapshot lookup and service-event delivery are auxiliary to the persisted
turn lifecycle. A stage lookup failure omits the optional progress snapshot.
After a terminal outcome is durably committed, a Redis service-event delivery
or runner-tail failure does not change that outcome to failed/cancelled; the
failure is logged and the runner still performs cleanup.

LLM rejection events (`llm_response` and terminal `error`) also preserve optional
`status_code`, `provider_type`, `provider_code`, `provider_message` and
`provider_param`. These are operator diagnostics, propagated through agent
execution failures to shadow traces. The adapter extracts known error fields
from nested/flat JSON or plain text, removes credentials and known message/tool
content echoed by the provider, and bounds messages to 2,000 characters and
codes/parameter names to 200 characters. Raw response objects, HTML and SDK
exception chains are not used as the explanation. Missing evidence stays
absent; a generic rejection does not establish a schema or capability fault.

HTTP status takes precedence over incidental words such as `timeout` in a
validation message. Mentioning `json_schema` alone does not imply unsupported
structured output: invalid schemas retain `llm_invalid_request`. Explicit mode
rejections and `json_validate_failed` allow the existing bounded compatibility
fallback. Shadow HTTP failures retain status 502 and return the safe runtime
message plus `details.error_code` and `details.retryable`; provider diagnostics
remain in the operator trace.

## Safety Rules

- Runtime/internal exceptions never go into conversational prompt history.
- Raw exception strings are logged server-side only.
- Chat stream always emits sanitized user-facing errors.
