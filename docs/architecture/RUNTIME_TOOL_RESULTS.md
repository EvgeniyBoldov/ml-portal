# Runtime tool result store

`runtime_execution_events` remains the only runtime journal. Complete external
tool payloads are separately persisted to the dedicated `postgres-tool-results`
database in `runtime_tool_payloads`, keyed by opaque result UUID and linked to
the root runtime run and tool call. Payloads are redacted before storage and
expire after the configured retention window.

Successful operations must persist before their result is exposed. A storage
failure is returned as an explicit operation failure and must not trigger an
automatic retry of the external operation. Trace events contain only bounded
shape/count metadata and the opaque result reference. Small complete results
may be projected into agent context; larger results are represented by a
pointer and must be read through `result.analyze`.

`result.analyze` accepts only an opaque result ID from the current run and
checks tenant/user ownership. It provides bounded `overview`, `project`,
`select`, `text`, and `aggregate` modes. `project` reads up to 20 named paths from a
JSON object, including nested paths such as `fields.status.name`; arrays must
be read with paginated `select`. A missing path is reported separately from a
JSON null. A projection exceeding the response budget fails without silently
truncating a value. Use paginated `text` with `text_path`, `text_offset`, and
`text_limit` for a long string. It does not accept SQL, arbitrary expressions, or access to
other runs. A selected page reports source completeness, matched/returned
counts, offset, selection identity, and whether another page exists.

For a stored Jira issue, request scalar paths such as `key`,
`fields.summary`, and `fields.status.name` with `project`. Read a long
`fields.description` with `text`. Read
`fields.subtasks` and `fields.comment.comments` with `select` and its
`array_path` argument; `fields` in `select` applies to each array item.

Source completeness checks known pagination metadata recursively, including
Jira comment pages nested inside an issue. It is a source-level flag; it does
not establish that an external API omitted no fields or related resources.

For task outputs containing arrays derived from a result that was not fully
provided inline, the agent must declare coverage claims referencing the
stored source and all `result.analyze` select calls. The runtime checks that
pages are contiguous, use the same selection, reach the end, and cover the
declared array length. Incomplete upstream pages cannot be declared complete.

The store has its own Alembic configuration and migrations, Compose service,
credentials, and retention cleanup task. It is not a trace table and its
payload contents must never be copied into progress events.
