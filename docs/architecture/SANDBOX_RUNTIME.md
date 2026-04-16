# Sandbox Runtime

## Purpose

Sandbox is an admin-only overlay over the real runtime.

It exists to let operators change runtime values without introducing a second execution model.

## Core Rule

Sandbox may override values, but it must not redefine runtime behavior.

Sandbox is not a generic editor for database rows. It is a structured browser for runtime-relevant entities and their overrideable fields.

The resolver is the source of truth for what can be edited in sandbox.

## Resolver Contract

`SandboxOverrideResolver` is the canonical boundary between stored values and sandbox values.

It should expose only entities and attributes that:
- participate in runtime resolution,
- can be safely overridden without breaking contracts,
- are already consumed by runtime or sandbox flow.

It should not expose:
- RBAC rules as editable sandbox state,
- raw data rows,
- credentials,
- generic admin-only metadata that does not influence runtime behavior.

The resolver may still surface read-only summaries for related entities, but overrides must stay on the runtime side.

Allowed overrides:
- prompt fragments,
- tool semantic release fields,
- versioned semantic fields,
- model aliases,
- retry and timeout values,
- execution flags already known to runtime,
- other runtime-safe fields that are explicitly registered by the resolver.

Tool-specific rule:
- tool input/output schemas are read-only in sandbox,
- they come from `DiscoveredTool` or backend release data,
- only semantic/runtime fields of effective `ToolRelease` may be overridden in branch state,
- unpublished `DiscoveredTool` may be temporarily exposed as draft publication candidate in branch state.

## Resolver Tree Model

Sandbox should work with the same resolver object model that runtime uses.

Conceptually the resolver has three layers:

1. `Base state`
- the canonical values stored in DB
- this is the original runtime tree

2. `Branch overlay`
- sandbox branch overrides stored in branch-scoped tables
- this is the editable layer

3. `Effective state`
- `base + overlay`
- this is what sandbox preview and runtime execution consume

The resolver must be able to expose, for every relevant field:
- `base_value`
- `override_value`
- `effective_value`

This makes reset/diff/preview behavior deterministic and keeps the UI and runtime aligned.

The sandbox may store overrides in branch-scoped persistence, but it should interact with the resolver as a structured tree, not as a flat form over database rows.

For tools, the resolver should treat `published` as an overrideable runtime-safe flag within the sandbox branch overlay:
- `published=false` means capability stays only in discovery inventory for that branch
- `published=true` means capability is visible to runtime for that sandbox branch snapshot

This does not change global publication state in the registry or admin area.

Disallowed changes:
- routing logic,
- policy logic,
- RBAC logic,
- discovery logic,
- publication logic,
- tool execution algorithms,
- planner behavior.

## UI Shape

The sandbox UI should render a structured tree, not a flat list.

Recommended layout:
- left panel: runtime entities grouped by domain and layer,
- right panel: selected entity fields and current effective values,
- overlay editor: supported overrides for the selected field set,
- live preview: compiled effective config used by the runtime.

The left panel should show discovered tools grouped by runtime context.
Each tool item should indicate publication state:
- published
- draft/unpublished

The right panel should show the selected effective tool release or draft candidate, including the publish toggle and semantic/runtime-safe fields.

Run inspector contract:
- right panel for selected step is tabbed by data direction:
  - `Summary`
  - `Input`
  - `Output`
  - `Context`
  - `Raw`
- each tab renders parameters as accordions (parameter-level drill-down),
- field rendering is typed (`datetime`, `duration`, `label`, `labels`, `json`, `string`, `bigstring`, `number`, `boolean`),
- UUID-only payloads are considered low-quality observability; backend step payloads should include human-readable refs where possible.

Good group boundaries:
- agent version,
- tool release/version,
- orchestration,
- platform settings,
- system roles,
- instance runtime view,
- collection runtime view.

Bad group boundaries:
- tool groups,
- raw admin-only CRUD containers,
- policy or RBAC documents as editable sandbox state.

## Runtime Flow

1. Start from production runtime context.
2. Resolve sandbox overrides through the same resolver used by runtime.
3. Apply a value-level overlay only to supported runtime fields.
4. Build the effective resolver tree and freeze it into a snapshot for the branch/run.
5. Resolve the same routing, policy, and execution layers.
6. Emit the same trace primitives as production, with higher visibility.

Snapshot rule:
- the run must use the immutable snapshot produced from the branch resolver state,
- the snapshot must include both resolver shape fingerprint and branch override payload,
- the runtime must never read mutable branch state after the snapshot is created.

## Why This Exists

This is the linking mechanism between operator debugging and the authoritative runtime path.
