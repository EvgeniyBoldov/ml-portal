# Canonical Tool Flow

## Purpose
- Keep one source of truth for runtime tool semantics.
- Separate provider discovery snapshots from runtime execution descriptors.
- Prevent collection-bound tools from leaking into global/system prompt space.

## Layers
1. `ToolRegistry` and MCP discovery expose raw handlers/tools.
2. `ToolDiscoveryService` stores raw provider snapshots in `discovered_tools`.
3. `CollectionToolResolver` resolves `collection -> data instance -> provider`
   and returns that provider's active tools plus platform collection defaults.
4. `ToolResolver` projects a resolved raw tool into a runtime descriptor; it
   does not infer collection availability from domains or provider names.
5. `OperationBuilder` builds exact collection-bound execution identities.
6. Prompt builders, runtime and admin capability API consume the same resolved
   operation set.

## Rules
- `discovered_tools` is a raw availability snapshot belonging to one provider.
- A collection-bound tool is available because its resolved provider discovered
  it, not because a domain/name allow-list recognizes it.
- `collection.info` is a platform collection default. System tools remain a
  separate global surface.
- MCP tool names are the public operation names and must be unique for
  incompatible schemas in one runtime snapshot.
- Runtime execution accepts only the exact invoke identity from `ResolvedOperation.operation_slug`.
- Prompts expose resolved provider tool names, human descriptions and exact
  invoke schemas; provider URLs and execution bindings remain internal.

## Prompt Contract
- Capability card shows collections, purposes, and available actions.
- Callable tools appendix shows exact invoke name, concise description, collection binding, and input schema.
- Internal provider URLs, credentials and execution bindings stay out of the
  LLM prompt and belong in runtime/operator surfaces only if needed.

## Maintenance
- Adding a remote MCP tool requires discovery plus an active provider binding;
  no product-code publication rule is added. Tests cover discovery, collection
  resolution and exact invoke execution.
