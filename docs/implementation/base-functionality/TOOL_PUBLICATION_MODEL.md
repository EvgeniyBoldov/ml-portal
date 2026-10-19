# Tool Publication and Resolution

## Current model

Provider discovery and runtime execution are separate surfaces:

- `DiscoveredTool` stores an active capability snapshot from a provider.
- `Tool` and `ToolRelease` provide optional curated catalog and execution
  metadata; their existence does not gate an active provider capability.
- `ResolvedOperation` is an internal execution contract for one resolved
  collection/provider target.
- The LLM-facing contract is a tool descriptor with name, description, and
  input schema.

## Resolution flow

1. A provider refreshes its discovered tool snapshot.
2. The collection resolver selects the provider bound to the requested
   collection and loads its active tools.
3. Platform collection defaults are added where applicable.
4. The runtime resolver applies collection compatibility, permissions,
   credentials, and readiness, then builds internal execution bindings.
5. Prompt assembly projects the available actions as callable tool schemas.
6. A tool call is mapped back to its resolved internal binding for execution.

Provider-specific URLs, credentials, persistence IDs, and execution bindings do
not enter the model-facing contract. Collection calls use `collection_slug` as
the public collection selector.

## Sandbox

Sandbox branches use the same provider-first resolution and tool projection as
normal runtime. Branch overrides may affect registered runtime-safe values, but
do not create a separate discovery or publication model.

See [Canonical Tool Flow](../../refactor/canonical-tool-flow.md) for the
collection/provider resolver boundaries.
