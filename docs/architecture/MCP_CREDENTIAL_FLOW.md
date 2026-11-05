# MCP Credential Flow

## Purpose

This document describes how credentials move from platform ownership to MCP-backed execution.

## Core Rule

MCP servers should receive short-lived credentials, not permanent raw secrets.
An MCP adapter may resolve broker access for each tool call and attach the
resolved credential to the upstream request. It must not retain the credential
in a session, process environment, or shared client state. The Atlassian adapter
is documented in [Atlassian MCP Adapter](ATLASSIAN_MCP_ADAPTER.md).
The [shared HTTP MCP adapter](MCP_ADAPTER.md) owns broker resolution,
authentication profiles, tool filtering, and descriptor enrichment. Raw
credential delivery is an explicit local-only compatibility mode.

## Flow

1. Runtime resolves an operation.
2. Runtime selects credentials from the platform-owned operation risk: `risky`
   requires a credential owned by the requesting user; `safe` resolves in
   User → Tenant → Platform order. MCP `credential_scope` and side-effect
   metadata do not select credential ownership.
3. Runtime issues a short-lived signed retrieval token without decrypting the secret.
4. MCP adapter exchanges that token for the data instance's secret for this call.
5. The adapter authenticates to the upstream using the returned auth_type.
   The broker also returns `source_url` from the bound active data instance.
   The embedded Atlassian adapter requires this field for its per-call native
   client and does not accept a caller-selected source URL or broker endpoint.
   See [Atlassian MCP Adapter](ATLASSIAN_MCP_ADAPTER.md).

For NetBox, `auth_type=token` uses the legacy `Authorization: Token …` scheme;
`auth_type=bearer` uses `Authorization: Bearer …`. NetBox v2 API tokens require
the Bearer scheme. The credential payload for bearer may store the value as
`access_token` or `token`.

## Properties

- explicit expiry,
- short lifetime,
- revocation support,
- auditability.

## Security Boundary

Credential ownership stays in the platform.
Transport is just delivery.

Runtime resolves credentials only from the bound data instance. There is no
fallback to credentials on the MCP transport endpoint. The broker token signs
both data_instance_id and provider_instance_id. The stored credential must
belong to the signed data instance, remain active and satisfy the signed owner
and authentication-type claims. A different instance, including the MCP
provider, is rejected before decryption. User credentials stay bound to the
selected data connector and are never moved to the MCP service connector.

If the required credential is unavailable, runtime keeps the authorized
operation visible to the agent. Calling it returns a `credential_missing`
tool result naming the operation, data instance, and required owner scope;
runtime sends no upstream request.

Broker delivery is enforced in production, staging, and every non-local
environment. `MCP_CREDENTIAL_BROKER_ENABLED` only controls local/development
behavior; setting it false cannot disable broker delivery in a deployed
environment. Raw-credential fallback is also limited to local/development.
When `MCP_CREDENTIAL_BROKER_REQUIRED=true`, broker delivery is enabled even if
`MCP_CREDENTIAL_BROKER_ENABLED` is omitted in local/development configuration.
Runtime fails before sending an MCP request if it cannot issue
`instance_context.credential_access`. The adapter resolves that reference
against the internal broker for the call and uses the returned upstream
credential. Broker enablement does not configure the upstream service's own
Bearer authentication.

## Request tracing

Runtime uses the tool-call ID as `x-portal-request-id` and propagates it through
the MCP server, broker exchange, and upstream request. API and adapter logs use
the same ID. Logs include credential and instance IDs, `auth_type`, header
names, target origin, response status, duration, and sanitized transport error
details. They must not include JWTs, secret values, request or response bodies,
tool arguments, prompts, or model inputs.

### Diagnosing credential selection and delivery

API console logs expose resolution metadata in the message as well as structured
fields, so the default message-only formatter retains it. Search for:

- `runtime_credential_resolution_started/completed`: operation, selected data
  instance, user/tenant context, risk-derived strategy, broker mode, and selected
  credential ID, owner type and authentication type.
- `credential_scope_lookup_started` / `credential_scope_candidate`: allowed
  scope order and each attempted scope. Only active credentials on the selected
  data instance and matching owner qualify. `owner_context_missing` means there
  is no user/tenant identity to search; `no_active_credential_for_instance_and_owner`
  means no row passed those filters. Selection stops at the first match; lower
  priority scopes and unrelated owners are not enumerated.
- `operation_credential_binding_built`: data/provider binding, selected credential
  metadata and expected owner policy.
- `runtime_mcp_credential_delivery_policy`: environment and configured versus
  effective broker/fallback flags; only presence flags for broker URL settings.
- `runtime_mcp_credential_access_not_issued`: run/tool-call correlation, selected
  credential metadata and `broker_disabled` or `credential_id_missing`. A selected
  credential followed by `broker_disabled` is a delivery configuration failure;
  it does not indicate that the upstream service rejected its secret.

These are operator diagnostics, not user-facing progress or a credential dump.
They never include credential payloads, encrypted payloads, broker tokens or
configuration contents. In non-local environments the current runtime forces
broker delivery; a disabled effective broker warrants checking the running image
version and the configured environment.

## Why This Exists

This is the binding mechanism between tool execution and secure secret delivery.
