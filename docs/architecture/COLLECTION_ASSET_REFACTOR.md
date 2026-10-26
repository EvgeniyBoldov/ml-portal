# Collection and Runtime Binding

## Current model

`Collection` is the semantic data asset. It owns the collection slug, type,
schema, published semantic profile, and usage metadata. `ToolInstance` describes
runtime access and provider connections. Credentials are resolved through the
existing credential scope rules.

Supported collection types are `table`, `document`, `template`, `sql`, and
`api`. Local collection types select a shared local provider by collection type.
Remote SQL and API collections resolve their data instance and configured MCP
provider chain.

The user catalogue lists persisted collections only. The glossary is a separate
read-only catalogue; legacy Project Memory and Global Memory views are removed.
HippoRAG document operations and the shared memory scope catalogue remain active.

Public metadata, data, upload, export, document lifecycle, template and SSE routes
apply the same effective collection permissions. An explicit collection deny
returns 404 before reading or mutating its contents. Membership checks use active
database memberships rather than cached token ordering; membership alone never
overrides the effective collection policy.

Document uploads additionally require a platform administrator, tenant
administrator, or tenant data editor. The API enforces the configured upload
size before sending the original to object storage, validates declared metadata
types, and rejects inactive collections. Failed uploads clean up the original
artifact when the database transaction has not been committed.

The ingest run and each stage command are durable outbox records. Workers persist
stage results and the next commands in one database transaction; duplicate
deliveries return the saved result. Dispatch keeps commands recoverable across
broker failures, and stop increments the document generation so in-flight work
cannot complete as the current ingest. Vector indexing accepts an embeddings
artifact only when it has exactly one valid vector for every canonical chunk.
Reindex writes generation-scoped points, then removes older points after the new
index is complete, preserving the previous index when an upload or upsert fails.

## Runtime resolution

The runtime resolves a public `collection_slug` to an active collection, checks
its effective permissions and readiness, then resolves the source/provider and
its available tools. `CollectionRuntimeResolver` owns collection-to-source and
provider resolution. `CollectionToolResolver` loads active discovered tools for
that provider and adds platform collection defaults. The resulting execution
bindings remain internal; agent-facing prompts expose tool names, descriptions,
and schemas.

Provider discovery does not require a product-code publication rule for each
new capability. Active provider tools are eligible for the collections bound to
that provider, subject to collection compatibility, permissions, and readiness.

## Important boundaries

- `collection_slug` is the public collection selector; persistence IDs and
  execution bindings remain internal.
- Provider identity does not replace collection identity. A shared local provider
  may serve multiple collections, and each call retains its explicit collection
  target.
- `instance.domain` may supply compatibility/fallback metadata, but collection
  type and relational bindings drive collection behavior.
- Collection schema and semantic metadata describe data. Provider configuration
  and credentials describe access.
- Resolved operations are internal execution contracts; the LLM protocol uses
  tool calls.

See [Canonical Tool Flow](../../refactor/canonical-tool-flow.md) for the
provider discovery and tool-resolution contract.
