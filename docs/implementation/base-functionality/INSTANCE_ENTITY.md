# Tool Instance

## Purpose

`ToolInstance` stores the runtime connection identity for data sources and
service providers. It carries placement, connection configuration, provider
links, health state, and references used for credential resolution. Collection
semantics and schema belong to `Collection`.

## Kinds and placement

- `data` instances represent remote data sources or persisted compatibility
  bindings for collections.
- `service` instances represent providers such as MCP gateways or model
  services.
- `local` or `remote` placement determines whether the platform executes a
  local handler or connects to an external service.

## Collection runtime resolution

Collection resolution starts from the active `Collection`. Local `table`,
`document`, and `template` collections select a shared local provider by
collection type. Remote `sql` and `api` collections use their configured data
instance and provider link. The runtime checks effective permissions and
readiness for each collection and resolves credentials using the platform's
scope precedence.

Instance IDs, provider URLs, connection configuration, and credentials remain
internal. Public collection calls identify their target with `collection_slug`;
the LLM receives tool descriptors and schemas, not instance records or
execution bindings.

## Domain metadata

`domain` remains available as descriptive/compatibility metadata. Collection
behavior and provider selection are driven by collection type, explicit data
bindings, provider capabilities, permissions, and readiness.
