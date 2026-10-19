# Collection Entity

## Purpose

`Collection` is the user-facing data asset: it defines the dataset's identity,
schema, semantics, and usage context. `ToolInstance` and its provider chain
represent runtime access, connection settings, and credentials. A collection is
not itself a provider or an access boundary; effective permissions are resolved
by the runtime.

## Supported collection types

- `table` — locally stored structured records.
- `document` — locally stored and indexed documents.
- `template` — locally stored template records.
- `sql` — a remote SQL data asset accessed through its configured data source
  and MCP provider.
- `api` — a remote API data asset accessed through its configured data source
  and MCP provider.

Local collection-specific storage and vector fields may be null for remote
collections. Remote schema and freshness metadata are stored on the collection.
The schema contract is versioned through `CollectionSchema` and
`CollectionVersion` as applicable to the collection type.

## Runtime resolution

Collection resolution is collection-first:

1. Load active collections and their schema, current version, and data binding.
2. For `table`, `document`, and `template`, select the local provider by
   `collection_type`.
3. For `sql` and `api`, resolve the collection's data instance and its provider
   through the configured access chain.
4. Load active discovered tools from the resolved provider and add platform
   collection defaults.
5. Apply permissions and readiness checks for each collection, then create
   internal execution bindings.

`CollectionRuntimeResolver` owns source/provider selection.
`CollectionToolResolver` owns the discovered-tool set for a resolved collection.
Runtime execution uses resolved internal operation bindings. Agent prompts and
LLM requests expose callable tools with their schemas; provider URLs, credentials,
and execution bindings remain internal.

## Schema and semantic metadata

Collection schema describes fields, data types, descriptions, and capabilities
such as filtering, sorting, retrieval, and prompt context. Collection versions
hold published semantic descriptions and usage guidance. Local table schema is
aligned with local storage; remote SQL/API schema records discovered or
configured source structure. Instance configuration remains the connection and
authentication surface.

`collection_id` and provider bindings are runtime/persistence details. Public
collection operations address the asset through `collection_slug`.

## Source of truth

- Collection identity, schema, type, and semantic version: `Collection`,
  `CollectionSchema`, and `CollectionVersion`.
- Remote access and credentials: the collection's data instance and its
  configured provider chain.
- Provider capabilities: active `DiscoveredTool` records for the resolved
  provider plus platform collection defaults.
- Runtime action and target: resolved internal operation binding, projected to
  the model as a tool contract.

See [Canonical Tool Flow](../../refactor/canonical-tool-flow.md) for provider
resolution and prompt publication details.
