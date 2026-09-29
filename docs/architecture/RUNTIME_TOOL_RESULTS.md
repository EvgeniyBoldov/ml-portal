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
checks tenant/user ownership. It provides bounded `overview`, `select`, and
`aggregate` modes. It does not accept SQL, arbitrary expressions, or access to
other runs. A selected page reports source completeness, matched/returned
counts, offset, selection identity, and whether another page exists.

For task outputs containing arrays derived from a result that was not fully
provided inline, the agent must declare coverage claims referencing the
stored source and all `result.analyze` select calls. The runtime checks that
pages are contiguous, use the same selection, reach the end, and cover the
declared array length. Incomplete upstream pages cannot be declared complete.

The store has its own Alembic configuration and migrations, Compose service,
credentials, and retention cleanup task. It is not a trace table and its
payload contents must never be copied into progress events.
