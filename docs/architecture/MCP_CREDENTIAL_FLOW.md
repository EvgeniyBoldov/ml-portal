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
2. Runtime determines the required credential scope.
3. Runtime issues a short-lived signed retrieval token without decrypting the secret.
4. MCP adapter exchanges that token for the data instance's secret for this call.
5. The adapter authenticates to the upstream using the returned auth_type.

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

Enable this delivery path with `MCP_CREDENTIAL_BROKER_ENABLED=true`.
`MCP_CREDENTIAL_BROKER_REQUIRED=true` and
`MCP_ALLOW_RAW_CREDENTIAL_FALLBACK=false` prevent raw-secret fallback when a
credential is present but a broker access context cannot be issued. The adapter
receives `instance_context.credential_access`, resolves it against the internal
broker for that call, and uses the resolved upstream credential. Token enablement
does not configure the upstream service's own Bearer authentication.

## Why This Exists

This is the binding mechanism between tool execution and secure secret delivery.
