# Canonical Tool Flow

## Purpose
- Keep one source of truth for runtime tool semantics.
- Separate raw discovered capabilities from published runtime tools.
- Prevent collection-bound tools from leaking into global/system prompt space.

## Layers
1. `ToolRegistry` and MCP discovery expose raw handlers/tools.
2. `ToolDiscoveryService` stores raw snapshots in `discovered_tools`.
3. `app.agents.operation_publication` is the canonical semantics layer.
4. `CollectionToolResolver` selects raw tools for an instance/provider context.
5. `ToolResolver` maps a raw tool to a canonical published runtime tool.
6. `OperationBuilder` builds exact invoke identities for runtime execution.
7. Prompt builders and trace snapshots read published canonical summaries only.

## Rules
- `discovered_tools` is a raw availability snapshot, not a semantic source of truth.
- Scope classification (`system` vs `collection`) comes only from canonical publication.
- Collection-bound tools must declare supported `collection_types` in canonical semantics.
- Unpublished collection-like tools must not fall back to `system`.
- Runtime execution accepts only the exact invoke identity from `ResolvedOperation.operation_slug`.
- Prompts should expose human-facing capability structure and exact invoke names, but not internal raw handler aliases.

## Prompt Contract
- Capability card shows collections, purposes, and available actions.
- Callable tools appendix shows exact invoke name, concise description, collection binding, and input schema.
- Internal-only fields such as raw handler aliases stay out of LLM prompt and belong in operator tooling only if needed.

## Maintenance
- Adding a new runtime tool requires:
  - a canonical `OperationSpec`,
  - publication rules for raw aliases,
  - tests for discovery, collection compatibility, and exact invoke execution.
