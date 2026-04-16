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
- raw capability snapshot from `local` registry or `mcp` provider,
- stores source linkage and call contract,
- may exist without any published runtime tool.

2. `Tool`
- stable product container,
- links a chosen capability family to curated runtime releases,
- owns human-readable catalog metadata and current active release pointer.

3. `ToolRelease`
- semantic/runtime version of the tool,
- stores safety, execution, routing, and LLM-facing metadata,
- is the only semantic version entity that runtime should treat as curated source of truth.

## Resolver Contract

`ToolResolver` is the only place where tool data becomes agent-facing.

It must assemble the prompt/runtime view from:
- `DiscoveredTool` raw contract,
- effective `ToolRelease` semantics,
- sandbox overlays,
- canonical publication rules.

If a field is already present in the raw contract or release semantics, do not duplicate it elsewhere unless the resolver needs to normalize or override it.

## Responsibilities

### `DiscoveredTool`

Responsible for:
- raw discovery identity,
- source/provider provenance,
- input/output schema snapshot,
- source lifecycle (`is_active`, `last_seen_at`),
- draft candidate state before publication.

Not responsible for:
- final runtime semantics,
- planner-facing naming,
- policy-ready metadata,
- stable publication identity.

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

1. `DiscoveredTool` appears after discovery.
2. Admin may leave it unpublished.
3. When the capability should become a product/runtime tool, platform creates or links a `Tool`.
4. `ToolRelease` provides curated semantic/runtime versions for that `Tool`.
5. Runtime resolves instance-scoped operations from:
   `DiscoveredTool` contract + `ToolRelease` semantics + instance binding + publication rules.

Important rule:
- not every `DiscoveredTool` must become a `Tool`,
- unpublished discovered capabilities remain valid draft candidates,
- sandbox may temporarily publish such draft candidates through resolver overlays.

## Runtime Rule

Runtime must not assemble semantics from multiple competing persisted sources.

Target rule:
- raw contract comes from `DiscoveredTool`,
- curated semantics come from effective `ToolRelease`,
- operation identity comes from publication rules and canonical operation specs,
- prompt-facing tool view comes only from `ToolResolver`.

## Sandbox Rule

Sandbox does not introduce a special tool domain model.

Sandbox overlays only the effective semantic version:
- existing `ToolRelease` may be overridden through resolver,
- unpublished `DiscoveredTool` may be treated as draft candidate and temporarily exposed through resolver,
- branch snapshot materializes the effective publication state without mutating global admin state.

## Non-goals

- no direct agent dependency on raw discovered tool slugs,
- no semantic duplication across `DiscoveredTool` and `ToolRelease`,
- no second sandbox-only tool entity,
- no forced publication of every discovered capability.
