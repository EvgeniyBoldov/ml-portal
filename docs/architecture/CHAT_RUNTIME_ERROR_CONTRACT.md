# Chat Runtime Error Contract

## Scope

Contract defines how runtime failures are represented for:

- user chat stream,
- persisted assistant messages,
- admin/sandbox diagnostics.

## Event Contract (`SSE error`)

- `type`: `"error"`
- `code`: stable machine code (`budget_exceeded`, `max_retries_exceeded`, `planner_failed`, `tool_unavailable`, `routing_failed`, etc.)
- `error`: user-safe message only (no traceback, no raw exception payload)

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
