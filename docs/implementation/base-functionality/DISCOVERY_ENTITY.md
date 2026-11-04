# Discovery Entity

## Purpose

Discovery refreshes the active capability snapshot for local handlers and
remote MCP providers. A `DiscoveredTool` records the provider identity, name,
description, input/output schemas, source metadata, and active/last-seen state.
It also owns the result delivery policy (`direct` or `store`) and, after its
first successful execution, an optional observed data schema inferred from
the raw result. The observed schema contains structure only; raw result values
are not retained for admin review. The provider-declared output schema and
observed data schema are separate fields. New capabilities default to direct
delivery; migration 0208 assigns Store delivery to the established
dataset-backed operations and migration 0209 narrows that policy to list and
row-producing operations, leaving singleton lookups and schema-catalog tools
in Direct by default.

## Runtime use

The collection resolver selects the provider for a requested collection. The
tool resolver loads that provider's active discovered capabilities, adds
platform collection defaults where applicable, applies collection
compatibility, and returns the runtime tool set. Runtime then applies effective
permissions, readiness, credentials, and safety policy before exposing tool
schemas to the model.

A persisted `Tool` or `ToolRelease` may enrich a capability with curated
metadata, but provider discovery and collection binding determine its
availability. Discovery snapshots alone do not grant access: runtime access
checks remain authoritative.

Administrators can inspect the observed schema and change the result delivery
policy on the discovered-tool detail page. The policy is keyed by the persisted
provider-scoped discovery record. Refreshes update provider metadata and
last-seen state while preserving this operator setting and the first observed
schema. The detailed storage, context-budget and reader behavior is owned by
[Runtime Tool Results](../../architecture/RUNTIME_TOOL_RESULTS.md).

## Sandbox

Sandbox resolution uses the same provider discovery and collection binding
rules. Explicit sandbox overrides may change supported runtime-safe metadata;
they do not mutate global discovery snapshots.
