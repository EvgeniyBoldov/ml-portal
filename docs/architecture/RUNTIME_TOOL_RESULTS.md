# Runtime tool results and Data Workspace

## Model input inventory

Runtime supplies a `datastore` projection directly in role inputs. Its `items`
list contains `kind=file` artifact passports and `kind=result` dataset metadata.
There is no `datastore.list` tool and no additional persistence surface. Files
remain in the chat artifact registry and object storage; datasets remain in the
Result Store. Files are read through `file.*`, datasets through `result.*`.

The shared projector is `runtime/datastore_context.py`. It includes identifiers,
file origin/description and representation state, or dataset producer task/call,
cardinality, revision, source completeness, SQL reference and bounded column
schema. It excludes file snippets, dataset samples, payloads, source continuation
arguments, memory and execution journals. The inventory is metadata, not proof
that a source was read or used. Source tools continue to validate every access.

Preflight receives its input-file passports. Each planner invocation refreshes
the authorized run dataset catalog and files referenced by task outcomes.
Agents receive input-file passports, explicit dependency/source files and
checkpoint artifacts; their dataset inventory includes their own task, explicit
dependencies/continuation and dataset IDs passed in task inputs or dependencies.
This is a prompt visibility rule, not a new access boundary: Result Workspace
still enforces run/user/tenant/TTL on reads. Synthesis receives input and selected
delivery/source files, plus datasets from its selected task reports or explicit
result references. Inventory membership does not select an attachment for delivery.
Deleted files are omitted. Dataset lists no longer silently show only the latest
ten entries; individual column schemas remain bounded and can be read further
with `result.describe`. New tool replies carry newly produced references during
an agent loop; after an interaction resume the initial inventory is refreshed,
replacing its saved copy. Catalog-load failures are marked `results_status=unavailable`
instead of being presented as an empty successful catalog.

Role-owned memory and task outcomes retain their existing prompt sections.
File indexing/search and agent notes are outside this inventory change.

Tool results are temporary run-scoped datasets, not long-term Memory or prompt
text. Successful results selected for Store delivery are redacted and persisted
in the dedicated `postgres-tool-results` database, including empty and
single-record responses. Datasets expire after `TOOL_RESULTS_RETENTION_DAYS`
(default 7, configurable from 1 to 30 days); an hourly cleanup task deletes
expired payloads. Runtime journal events use the same setting and have their
own hourly cleanup task.
An opaque UUID `result_id`, deterministically derived from the run and initial
tool call ID, identifies a dataset. Source pages append to that identity; SQL
output creates a new dataset. The original call ID remains explicit metadata.

`ToolResult.delivery` carries the provider/tool default (`stored` or `direct`),
but runtime resolves the effective policy from the active `DiscoveredTool`:
`result_delivery=direct|store`. New discoveries default to `direct`. Migration
0208 established the initial allowlist; migration 0209 refines it. Store remains
enabled for paginated NetBox object/device/site searches, Jira issue/project
lists, SQL row queries, collection table searches and grouped aggregates.
`jira_search`, `jira_get_project_issues`, `jira_search_issues` and the legacy
`jira_list_issues` alias normalize their issue arrays and continuation metadata.
`jira_get_issue` remains Store-enabled because its description field can be
large and the operation does not expose field selection. Singleton lookups
(`netbox_get_device`, `collection.get`) and schema-catalog searches use Direct;
Confluence text tools also default to Direct. Administrators can change any
discovered capability after reviewing its observed schema. Tool policy is
attached to the provider-scoped discovered capability, rather than inferred
from a generic result kind. Native `result.*` workspace tools keep their own
semantics. Virtual collection table search and aggregate operations without a
persisted discovery row retain their explicit Store fallback; singleton get is
Direct.

`memory.search`, `collection.doc_search` and `collection.list_documents` are
direct results as long as their discovered-tool policy is direct: runtime
redacts their payload and passes complete JSON to trace and SSE without Result
Store persistence, dataset descriptors or `result_id`. Agent `memory.search`
passages accumulate in the owning task's memory prompt section; its
conversation tool reply is a receipt, avoiding a second copy of the passages.
These tools bound their response through their own `limit` arguments; model
context limits still apply. Successful direct calls retain `evidence_call_id`
in the model message. The turn ledger preserves the delivery mode on reuse.

For a successful call to a discovered tool with no `observed_data_schema`,
runtime infers a structural JSON Schema from the raw `ToolResult.data` and
stores it once on that `DiscoveredTool`. The schema contains types and object
property names, but no observed values. The raw sample/result is not copied to
the primary database for admin review. An existing schema is not overwritten
by later calls. The provider's declared `output_schema` remains a separate
contract and is not replaced by the observed schema. Administrators can inspect
the observed schema and change `result_delivery` on the discovered-tool detail
page; subsequent calls use that policy. Discovery refresh does not reset these
operator fields.

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

Dataset metadata lives in `runtime_tool_payloads` in the dedicated results
database. The similarly named `runtime_tool_results` model in the main database
retains per-attempt operation receipts/payload references; it is a separate
runtime audit surface, not the dataset catalog.

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
  column-name search terms, without filtering records. Keys retain spelling and case; SQL quoting is needed
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

## MCP failure observations

MCP failure diagnostics use the shared `portal_mcp_contract.MCPFailure` model
described in [MCP Adapter](MCP_ADAPTER.md). A failed `ToolResult` keeps its safe
public message in `error` and the normalized source diagnostic in
`metadata.mcp_failure`. Model tool observations receive a structured failed
result containing that diagnostic, including the source's parser/validation
details. They do not collapse it to `Error: <generic message>`.

The same bounded, secret-redacted diagnostic accompanies the failed tool call
in the runtime trace. It is separate from successful tool-result datasets:
failures are not persisted as successful Result Store records. Existing
providers returning legacy JSON-RPC errors or `isError` content are normalized
at the consumer boundary. Successful content and pagination keep their existing
semantics.

This observation contract does not decide which failures an agent may repair,
whether a repeat is safe, or what internal details may be explained to the
user. Those policies remain runtime/prompt responsibilities. The safe public
message remains available independently of diagnostic content.

## Model presentation

Model-facing dataset replies use a compact typed receipt: `status` (`ready` or
`already_completed`), `result_id`, `revision`, and `source_coverage` (source
completion, known source total and number of saved records). A reply contains
complete `records` when they fit the allocated context budget, or a concrete
`next_action` with the available workspace tool and arguments. Source completion
refers to this selection, not completion of the agent's task. An empty records
array is a real empty result. Unknown source coverage is not false.

Ordinary receipts omit SQL schema pages, generic SQL examples, samples and
redundant delivery/completeness flags. `result.describe` provides schema on demand.
`result.read` reads saved records; it does not repeat the source operation. Its
continuation must preserve the selected fields and dataset revision. Oversized
records require a narrower projection; no partial record is presented as complete.
The model presentation uses the actual allocated budget rather than the store's
preliminary inline eligibility. Persistence limits remain independent.

The complete journal/checkpoint transcript is retained. Model requests use a
separate projection that preserves native assistant/tool call pairing and direct
or otherwise unrecoverable evidence. Older recoverable dataset responses may be
represented by compact receipts. The authorized, task-selected result inventory
is refreshed before decisions, so new results and revisions are visible.

Before executing a batch of tool calls, runtime estimates the input room for
the next model request with `inspect_context`, including current history, the
assistant tool-call message, placeholder tool replies, tool schemas,
`tool_choice` and `response_format`, while preserving the configured output
reserve. It uses the selected model's registry context window when available;
otherwise it falls back to the default context window. The remaining input
budget is divided evenly among calls in that batch. This is conservative: an
unused share is not redistributed. Result serialization is checked against
that per-call budget with the selected model's token estimator. Direct results
are delivered whole when they fit; if they do not, the model receives an
explicit `context_budget_exceeded` limitation and guidance to retry with a
narrower request. Runtime does not silently clip direct JSON or move an
oversized direct result into Result Store.

The same budget is passed to `result.describe`, `result.read`, and
`result.analyze` projections. These readers return bounded pages and preserve
continuation offsets. `result.analyze` text mode advances by the actual
returned chunk length. Store-side byte limits and transport/payload limits
remain in force; the dynamic context allocation replaces fixed prompt-output
caps, not persistence limits. Non-runtime callers retain compatibility
fallback bounds. Empty arrays, null, false and zero are preserved. Local execution retains runtime
metadata rather than losing it in an MCP transport round trip. Duplicate-call
reuse retains the stored dataset reference and refreshes its descriptor instead
of treating the descriptor as another source payload.

For stored datasets, traces/SSE previews and model messages are separate projections. Traces contain
metadata, revisions and references. The complete payload remains in the store.
The trace inspector displays a complete tool reply when it can match it by call
ID and owner in a later recorded LLM request. Otherwise it previews data in the
tool-result event. In sandbox, a stored descriptor can be opened through the
metadata endpoint and paginated dataset API. Interpret
`result_inline_complete` as completeness of model delivery only. Source coverage
(`result_source_complete`), query execution (`query_complete`), event truncation
and the counts `result_row_count`/`result_source_total` remain separate facts;
missing flags are unknown rather than false. The sandbox result browsing API
provides separately authorized, paginated access to retained dataset rows.

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
