# Runtime tool results and Data Workspace

Tool results are temporary run-scoped datasets, not long-term Memory or prompt
text. Successful payloads are redacted and always persisted in the dedicated
`postgres-tool-results` database, including empty and single-record responses.
An opaque UUID `result_id`, deterministically derived from the run and initial
tool call ID, identifies a dataset. Source pages append to that identity; SQL
output creates a new dataset. The original call ID remains explicit metadata.

## Source protocol and normalization

External MCP/API responses pass through `ResultPage`, a Pydantic protocol:
`{"value": [...], "meta": {...}}`. Each value element is one record. Metadata
includes `source`, `total` (also accepts `count`), `has_next`, `complete`, and
internal `next_arguments`. Unknown values are nullable. Pagination parameters
are execution bindings, not instructions or URLs for the model to reconstruct.

Normalization belongs to a source adapter in MCP or runtime. Runtime currently
has explicit NetBox collection and multi-type search, Jira search and SQL MCP row adapters. Already normalized
responses pass through protocol validation without being wrapped twice. Other
responses use an identity adapter: root arrays are records; objects/scalars,
including null, are single records, with unknown pagination state. Runtime never
searches arbitrary JSON for a guessed collection or continuation. Additional
source formats need an explicit adapter or the published protocol.

NetBox uses returned offset/limit and retains original filters and object type.
Multi-type NetBox search extracts records from each per-type page; its envelope
(`results`, `errors`, `searched_types`) is not a record. Requested/successful types
and errors remain metadata. Missing/failed types prevent complete coverage, also
after continuation; an empty successful search stores zero records. Continuation
retains the original query/types and requires agreeing next offsets across endpoints.
Nonadvancing continuations are rejected. Missing pagination metadata remains
unknown, and a normalized page cannot claim complete coverage while declaring
another page or fewer records than its total.
Jira uses startAt/total/issues and retains JQL. Sources initially queried at a
nonzero offset do not claim complete coverage. Exhaustion and total coverage
are distinct; a short response inconsistent with its total is not complete.

## Persistence and lifecycle

Migration `tool_results_0003` adds dataset metadata, original operation arguments,
revision and `runtime_tool_result_pages`. Original source pages remain JSONB,
keyed idempotently by dataset and argument fingerprint. The dataset payload is
the accumulated record array. `runtime_tool_result_rows` stores one JSONB record
per ordinal, with a separate generated row ID (migration `tool_results_0004`).
Internal row IDs and ordinals are not virtual SQL columns. Appending locks the parent, validates the expected revision and
continuation, stores the page and records atomically, updates profiling and
increments the revision. Repeated page commits do not duplicate records.
Initial dataset metadata, record rows and original source-page provenance also
commit in one transaction; a page-storage failure leaves no partial dataset.
Execution/task IDs are normalized to strings for their VARCHAR storage columns,
including native workspace SQL calls whose context contains a UUID execution ID.

A dataset can contain zero or 50,000 records; cardinality does not change the
storage model. Byte limits remain explicit. All records/pages inherit parent
TTL through cascading deletion. Current workspace access requires matching run,
tenant and user and an unexpired parent; references do not grant access.

## Native workspace tools

Runtime adds Pydantic-derived `result.describe`, `result.read` and `result.load`
to agents with resolved operations. `result.sql` is exposed when SQL analysis
capability (`result.analyze`) was already resolved; the same gate applies
to `result.aggregate` and `result.find`; this does not silently grant
analysis capability to domain agents. Workspace read/query failures are returned
to the model for repair or a partial/needs declaration; they do not trigger the
generic two-unsuccessful-tool-steps abort. Global execution budgets still apply.
Existing result.analyze versions remain
compatible and use the same SQL storage engine.

* `result.describe(result_id, offset?, limit?, query?)` returns the actual SQL
  column map, revision, cardinality and source state, without internal continuation
  arguments. `sql_columns` maps exact top-level JSON keys to SQL types and JSON
  paths. Nested objects and arrays remain JSONB, without flattened aliases or
  added storage columns. All currently saved records contribute to schema
  discovery, including optional fields absent from the first record. Uniform
  scalar fields use text, numeric or boolean; mixed and all-null fields use JSONB.
  The same projection is inspected through PostgreSQL column descriptors and
  saved as `dataset_meta.table_schema` in the transaction storing the records.
  An empty dataset has an empty schema; scalar records expose `value`.
  Schema delivery is paginated with `next_schema_offset`, `schema_total_columns`,
  `schema_matched_columns` and `schema_page_complete`. `query` accepts comma-separated
  column-name search terms, without filtering records. The initial tool descriptor
  uses this same column map. Keys retain spelling and case; SQL quoting is needed
  for punctuation or reserved words. Invalid PostgreSQL identifiers (empty, NUL,
  longer than 63 UTF-8 bytes) fail explicitly rather than being silently renamed.
* `result.read(result_id, fields?, offset?, limit?, revision?)` reads a bounded
  portion of saved records. It returns `next_offset`, `read_complete` and
  `source_complete` separately. A record that cannot fit is explicitly marked
  `record_too_large`; the agent can select fewer fields or request SQL analysis.
  Read never issues a source API request. Revision checks prevent silently mixing
  pages read before and after dataset append.
  `fields` accepts exact top-level `sql_columns` names. `device_type` returns
  its complete object; nested paths use SQL JSON operators instead.
  Unknown field names fail explicitly instead of manufacturing null values;
  null and missing values in a known heterogeneous field remain null.
* `result.load(result_id, mode=next|remaining, max_pages?)` calls the same resolved
  read-only source operation with persisted continuation arguments. It rechecks
  availability, argument validation and credential resolution through the normal
  facade. It does not follow arbitrary next URLs. Time/page/storage budgets stop
  loading with saved pages intact and an explicit limitation. Each source page
  has its own call ID in page provenance. Remaining loading is bounded, resumable,
  and does not require an LLM turn per source page.
* `result.sql(sql)` executes one read-only PostgreSQL SELECT or WITH query. Each
  referenced dataset is a virtual CTE named `result_<uuid_without_hyphens>` with
  exactly the top-level fields of the saved records. `SELECT name, status FROM
  result_<id>` reads those columns; `status->>'label'` accesses a nested value.
  Source keys named `data` or `ordinal` remain source columns, without renaming.
  Describe and execution share one projection generator. SQL may join accessible
  datasets, filter, sort and aggregate. An SQL parser rejects multiple statements,
  writes, physical/schema-qualified tables, inaccessible result references and
  functions outside the supported read-only function set. A repeatable-read
  transaction pins the catalog, input revisions and queried rows to one snapshot.
  Query output is saved with SQL, parameters, source IDs and input revisions as lineage.
* `result.aggregate(result_id, columns, offset?, limit?)` groups saved records by
  the specified top-level columns and returns a count per combination. JSONB
  grouping compares the complete nested value. Use SQL for grouping by nested fields.
* `result.find(result_id, q, columns?, offset?, limit?)` searches saved records,
  including nested JSONB, for literal case-insensitive text. The search term is a
  bound parameter, so SQL syntax and wildcard characters remain literal text.
  Both wrappers use the SQL engine, persist their output as a new result and
  report upstream completeness separately. Neither implicitly loads source pages.

SQL has a configured statement timeout, row limit (default 100,000), and byte
limit. Oversized SQL output fails explicitly; full successful output is stored.
`query_complete` describes execution, not upstream coverage. Analyzer delegation
continues through agent needs and planner decisions, not automatic runtime task
creation.

## Model presentation

Every stored result has a descriptor and `delivery=inline|stored`. Complete small
payloads may accompany the descriptor. Large payloads expose bounded observed
fields/SQL columns and valid JSON samples. Samples are examples, never coverage
proofs. Oversized sample records are omitted rather than sliced into invalid JSON.
Descriptions explain how to read, analyze, or fetch source pages next. Internal
pagination arguments are not shown to the model. The column schema has priority
over samples and SQL lineage in the context budget. Inline data is not duplicated
as a sample. Catalog and tool descriptors both expose the same column contract,
and nested fields can be inspected with result.read before using JSON operators.

Presentation uses `TOOL_RESULTS_CONTEXT_TOKENS` with a conservative byte-based
estimate (three UTF-8 bytes per estimated token), plus existing character caps;
it is not an exact provider tokenizer. Reads have their own bounded presentation.
Empty arrays, null, false and zero are preserved. Local execution retains runtime
metadata rather than losing it in an MCP transport round trip. Duplicate-call
reuse retains the stored dataset reference and refreshes its descriptor instead
of treating the descriptor as another source payload.

Traces/SSE previews and model messages are separate projections. Traces contain
metadata, revisions and references. The complete payload remains in the store.

## Agent response protocol v2

`task_completion_json_schema(task)` describes only the universal Pydantic
protocol: required `completion`, optional string `answer`, arbitrary JSON
`structured_response`, and discovered `needs`. `needs` completion requires a
nonempty list with unique refs; other completion modes require no unresolved
needs. Invalid JSON, unknown envelope fields and inconsistent statuses receive
bounded protocol correction. Data schemas never cause correction.

The agent assesses task success and completeness. Planner `response_spec.schema`,
legacy output specs and registered data contracts guide the LLM. Runtime records
schema deviations (or an invalid advisory schema) as warning diagnostics and
retains the original data, including null, blank strings, false, zero and empty
collections. Coverage metadata and retrieval receipts remain observations for
auditing, not acceptance conditions. `result.analyze` is a way to read stored
results, not a mandatory proof that the answer satisfies a guessed schema.

Only a mandatory file (`response_spec.mode=artifact`, or a legacy required
artifact spec) has an acceptance check: at least one undeleted attachment
created by runtime operations in this task. Runtime supplies attachments and
sources automatically. Missing files return `required_artifact_missing` while
preserving answer/data; `needs` is never erased by missing data or files.

Bindings pass actual result values unchanged, using legacy keys or JSON Pointers
(e.g. `/structured_response/rows`). Missing paths block the consumer and return
to planning; advisory schema differences do not. A prior completed result may
be bound without recreating the producer. Large task inputs/dependency context
are stored with accessible `result_id`/`sql_ref` metadata rather than string
truncation. These context datasets also remain available through the workspace read and SQL interfaces.

Legacy declarations are adapted: `report` becomes `answer`, value slots become
`structured_response`; runtime-issued files/sources come from the observed
ledger. New responses do not need slots, coverage claims or evidence identifiers.
