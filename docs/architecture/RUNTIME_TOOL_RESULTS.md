# Runtime tool results and SQL analysis

Successful tool payloads are redacted and persisted to the dedicated
`postgres-tool-results` database. The original JSON payload remains available
in `runtime_tool_payloads`; `runtime_tool_result_rows` exposes it to SQL as
`ordinal` and `data JSONB` rows. Root arrays become one row per element. An
object or scalar, including an object that contains arrays, becomes one row.
Nested arrays and object structure are preserved in `data`.

Every result has an opaque UUID `result_id` and stable SQL name
`result_<uuid_without_hyphens>`. The runtime exposes this exact name and a
bounded observed schema and sample to agents. Schema metadata records observed
paths, types, nulls, and missing values. `schema_complete` and
`sample_complete` indicate when profile or sample limits were reached; a sample
does not promise that all rows have the same shape.

`result.analyze` version 2 accepts one PostgreSQL `SELECT` or `WITH ... SELECT`
query. Before execution, the runtime makes every unexpired result belonging to
the current run available as a CTE using its exact `sql_ref`, with `ordinal`
and `data` columns. The query runs in a read-only transaction with a 10 second
statement timeout. It may use PostgreSQL JSON functions to inspect nested data,
join results, filter, aggregate, and use CTEs. The SQL result is persisted as
another result with its own `result_id` and `sql_ref`, so later queries can use
it as a source.

The SQL tool returns result metadata and a bounded preview. The complete SQL
output is stored separately. Queries producing more than 10,000 rows or
exceeding `TOOL_RESULTS_MAX_PAYLOAD_BYTES` fail explicitly instead of returning
a successful partial result. Source completeness, query result completeness,
and preview size are separate properties. Query provenance includes the SQL
and IDs of the run results referenced by the query. Unused results in the
catalog do not affect `source_complete`. `query_complete` means the SQL query
finished and its full output was stored; `inline_complete` describes only the
returned preview, and `source_complete` describes the referenced upstream data.

All payloads, row projections, and metadata expire together according to the
runtime tool result retention period. Traces contain bounded metadata and
references, not full payloads.

## Terminal task contract

The runtime publishes `task_completion_json_schema(task)` and the normalization
rules with every task. The schema describes the canonical declaration after
normalization. The agent loop and final task reducer use the same validation;
one correction turn includes concrete field paths and reason codes before the
attempt ends. Repairs of JSON or evidence references do not require repeating
external actions. The final declaration and verified tool receipts remain
available for audit even if an output fails validation.
Receipt validation uses structured runtime metadata, independently of any
truncation applied to the displayed tool preview.

| Field | Requirement | Absence handling |
| --- | --- | --- |
| `completion` | `fulfilled`, `needs`, or `unfulfillable` | Missing/null/blank is invalid |
| `report` | Non-blank string | Missing/null/blank is invalid |
| `outputs` | Object keyed by the task's expected output keys | Omitted/null/blank becomes `{}` |
| `needs` | Non-empty only for `needs` | Omitted/null/blank becomes `[]` |
| `coverage` | Runtime-observed proof of access to stored data | Omitted/null/blank becomes `[]` |
| `limitation` | Object required only for `unfulfillable` | Omitted/null/blank becomes `null` |

A supplied output must be exactly a typed slot: `{kind: "value", value: ...}`,
`{kind: "evidence", refs: [...]}`, or `{kind: "artifact", refs: [...]}` as selected
by the output spec's `fulfillment`. An absent `value` member is an error;
`value: null` is a supplied value. Required outputs must be present and valid
for `fulfilled`. `needs` and `unfulfillable` may supply valid partial outputs.
Invalid supplied outputs are rejected for every completion status; missing
required outputs are permitted only for `needs` and `unfulfillable`.
Unknown fields, unknown output keys, duplicate need refs and duplicate
coverage `(output_key, output_path)` pairs are errors.

Within value slots, `null`, `""` and whitespace-only strings represent absence.
The runtime prefers `null` when the field schema permits it. Otherwise it
uses a schema-valid empty string, array or object. If an optional object
property permits no absent form it is omitted; a required property remains
invalid. An optional output supplied as a value slot with absence is similarly
omitted if its schema permits no absent form. Normalization is recursive and
idempotent, honors JSON Schema constraints and local `$ref`, and never converts
`0`, `false`, `[]`, `{}` or non-blank text into absence. Missing required data
is never invented. Blank reference-list entries are removed, references are
trimmed and deduplicated, and an empty required reference list is invalid.
Embedded output schemas retain their own `$ref` scope. Unresolved references
produce validation feedback rather than an uncaught task execution error.

`needs` entries require `ref`, `key`, and `description`; the defaults are
`kind="data"`, `schema={}`, `required=true`, and `context={}`. A limitation
requires `code` and `message`; omitted/null/blank `action` defaults to `none`.

Coverage claims require `output_key`, `result_id`, and non-empty
`query_call_ids`. Omitted/null/blank `output_path` means the whole value;
a dot-separated path can select a subtree, including nested arrays. If an
attempt has clipped tool results, non-empty output arrays require coverage.
SQL-derived values reference the saved SQL result ID and successful query
call ID. SQL may filter, aggregate or reshape rows; output length is not
compared to the SQL row count. Legacy claims referencing an upstream result
are accepted only when runtime-recorded SQL provenance links that result.
Copied `select` arrays still require all contiguous pages of the selection.

`TaskOutputSpec.require_complete_source` defaults to `false`: normal coverage
proves access to observed data and does not assert full upstream scope. Setting
it to `true` explicitly requires coverage and runtime-confirmed complete
sources. This policy is available only for `task_result` outputs and is
published to the agent with the other output requirements. Data correctness
and interpretation of the user's scope are separate from declaration shape
and verification of runtime references.
