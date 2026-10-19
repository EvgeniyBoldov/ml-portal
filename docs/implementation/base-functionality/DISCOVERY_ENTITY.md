# Discovery Entity

## Purpose

Discovery refreshes the active capability snapshot for local handlers and
remote MCP providers. A `DiscoveredTool` records the provider identity, name,
description, input/output schemas, source metadata, and active/last-seen state.

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

## Sandbox

Sandbox resolution uses the same provider discovery and collection binding
rules. Explicit sandbox overrides may change supported runtime-safe metadata;
they do not mutate global discovery snapshots.
