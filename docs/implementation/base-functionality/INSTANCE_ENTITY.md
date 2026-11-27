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
  services and connections to external integrations.
- `local` or `remote` placement determines whether the platform executes a
  local handler or connects to an external service.

## Integration connectors

Create a connector of type `integration` in the admin connector registry.
Set its URL to the full HTTP(S) destination endpoint, including the path.
Keep authorization in the connector's existing Credentials tab. The platform
stores these credentials encrypted and links them by instance ID, as it
does for model connectors. Use a platform-level Bearer credential for a
service-to-service callback that uses the `Authorization: Bearer` header.
Integration endpoints have no automatic or manual network health probe.

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

## Admin integrations

In **Platform settings → Integrations**, create an integration with a unique
incoming identity such as `clouds:express`. This is the value of
`X-Assignment-Connector` and must match the source in the assignment envelope.
Select an integration connector for the reply endpoint and its outbound
credentials.

Issue Bearer tokens in the integration's **Authorization tokens** tab. The
secret appears once at issuance. Admins can set an expiry, see the last successful
use, revoke individual tokens, or disable the whole integration. A managed
identity uses its issued tokens as soon as it is created. Legacy environment
tokens continue to apply to identities without a managed integration.
