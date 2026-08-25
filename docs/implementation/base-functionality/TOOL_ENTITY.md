# Tool Entity

## Purpose

`Tool` is the publication container for one runtime capability family.

It exists between:
- raw capability discovery,
- semantic/runtime curation,
- instance-scoped operation publication.

`Tool` is not the raw source artifact and not the final runtime action.

## Core Model

The tool layer consists of three persisted entities:

1. `DiscoveredTool`
- active raw capability snapshot from one local or `mcp` provider,
- stores source linkage and call contract,
- becomes collection-available through the provider bound to that collection.

2. `Tool`
- optional product/catalog container,
- links a capability family to optional curated runtime releases,
- does not gate provider-tool availability.

3. `ToolRelease`
- optional semantic/runtime version of the tool,
- stores additional safety, execution and LLM-facing metadata,
- does not act as an allow-list for provider discovery.

## Resolver Contract

`ToolResolver` is the only place where tool data becomes agent-facing.

It must assemble the prompt/runtime view from the resolved provider snapshot,
the raw `DiscoveredTool` contract, optional catalog/release metadata and
sandbox overlays. Collection availability is resolved by the collection tool
resolver, not by publication rules.

If a field is already present in the raw contract or release semantics, do not duplicate it elsewhere unless the resolver needs to normalize or override it.

## Responsibilities

### `DiscoveredTool`

Responsible for:
- raw discovery identity,
- source/provider provenance,
- input/output schema snapshot,
- source lifecycle (`is_active`, `last_seen_at`),
- active/inactive source lifecycle (`is_active`, `last_seen_at`).

Not responsible for:
- optional curated metadata or product identity.

### `Tool`

Responsible for:
- stable business identity of the published capability,
- grouping releases under one catalog object,
- active release pointer (`current_version_id`),
- container-level metadata used in admin UX.

Not responsible for:
- storing raw provider contracts,
- per-instance execution targets,
- sandbox branch state.

### `ToolRelease`

Responsible for:
- semantic description used by runtime,
- safety metadata (`side_effects`, `risk_level`, `requires_confirmation`, `idempotent`),
- execution config (`timeout`, `retries`, `priority`, concurrency),
- routing/publication hints,
- LLM help (`description_for_llm`, `field_hints`, `examples`, `return_summary`).

Not responsible for:
- owning the raw backend contract,
- provider discovery lifecycle,
- direct instance binding.

## Relationship Between Entities

Canonical chain:

1. `DiscoveredTool` appears after provider discovery.
2. Collection resolver selects active snapshots from the collection's provider.
3. Runtime builds an operation from the raw contract and collection target.
4. `Tool`/`ToolRelease` may enrich or govern an already discovered capability,
   but their existence is not required for availability.

Important rule:
- every active provider capability is eligible for its bound collections,
- optional catalog/release data never replaces provider relationship resolution,
- sandbox overlays remain limited to registered runtime-safe values.

## Runtime Rule

Runtime must not assemble semantics from multiple competing persisted sources.

Target rule:
- raw contract comes from `DiscoveredTool`,
- optional metadata comes from effective catalog/release data,
- operation identity comes from the discovered provider tool name and collection
  target binding,
- prompt-facing tool view comes from the same resolver used by runtime/admin API.

## Sandbox Rule

Sandbox does not introduce a special tool domain model.

Sandbox overlays only explicitly registered runtime-safe values. The branch
snapshot uses the same provider-first tool resolution as runtime and does not
create a second publication or discovery model.

## Non-goals

- no direct agent dependency on provider URLs, credentials or storage rows,
- no semantic duplication across `DiscoveredTool` and `ToolRelease`,
- no second sandbox-only tool entity,
- no manual product-code publication rule for a new MCP capability.
