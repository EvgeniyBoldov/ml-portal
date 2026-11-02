# Atlassian MCP Adapter

`atlassian-jira-mcp` and `atlassian-confluence-mcp` expose the upstream
[`sooperset/mcp-atlassian`](https://github.com/sooperset/mcp-atlassian) through
separate Portal-owned adapter containers using the
[shared HTTP MCP boundary](MCP_ADAPTER.md). Both use the package version pinned
in `mcp/atlassian_adapter/requirements.txt`; each container is configured for
exactly one product and one product URL.

Register two MCP provider instances in Portal, one for each service. Bind each
data connector to its matching MCP provider through `access_via_instance_id`.
Discovery and runtime tool sets are isolated by provider instance, so Jira
collections resolve Jira tools and Confluence collections resolve Confluence
tools without tool-level product metadata or additional resolver logic.
Credentials remain scoped to the corresponding data connector and contain the
fields required by their explicit auth_type. The data connector URL takes
precedence at call time.

## Adapter responsibilities

- Issue the Portal-required `mcp-session-id` on `initialize`. Upstream runs in
  stateless Streamable HTTP mode; the adapter owns the client session for one
  hour of inactivity.
- Accept credentials per `tools/call`: resolve `credential_access` with the
  shared secret broker when present, otherwise accept runtime-provided
  `instance_context.credentials` and `instance_context.auth_type` only in the
  explicitly enabled local compatibility mode. An explicit
  broker access context is authoritative: failed resolution never falls back
  to raw credentials. Credential material is never stored in the MCP session
  or process environment.
- Send request-resolved Atlassian PATs using upstream's per-request authentication
  headers. Runtime-only arguments (`credential_access`, `instance_context`, and
  collection targeting fields) are removed before forwarding the public tool args.
- Filter `tools/list` by `ATLASSIAN_MCP_ENABLED_TOOLS` and enforce the same
  allowlist at call time. An empty setting falls back to the small built-in
  read-only allowlist; it does not publish every upstream tool.
- Publish only the explicitly configured binary `inputSchema.x-runtime.risk_level`
  (`safe` or `risky`) for each enabled operation. The small built-in allowlist
  has an explicit safe classification per operation; enabling any additional
  operation requires adding its risk descriptor. Upstream risk, credential
  scope, side-effect, and confirmation metadata are not trusted or forwarded.
  Credential ownership is selected by runtime from the platform's effective
  operation risk.
- Emit operational request logs with a Portal correlation ID, MCP method/tool,
  processing stage, duration, exception class, upstream HTTP status, and JSON-RPC
  code. Arguments, credentials, response bodies, and exception text are omitted.

The upstream process receives placeholder PATs at startup only so it can
initialize toolsets and publish their schemas. `ALLOW_GLOBAL_CRED_FALLBACK=false`
is set. The placeholders are not valid service credentials. Tool calls require
request credentials in either supported form.

Portal sends `x-portal-request-id` on each MCP tool call, using the runtime tool
call ID. The adapter uses it to correlate its container log with the runtime
trace. Requests from other clients receive a generated local ID. MCP callers
continue to receive generic safe errors; operators use the correlated adapter
log to distinguish broker, upstream transport, timeout, and protocol failures.

## Configuration and onboarding

`ATLASSIAN_JIRA_URL` and `ATLASSIAN_CONFLUENCE_URL` configure the respective
provider URLs. The Jira container leaves `CONFLUENCE_URL` empty; the Confluence
container leaves `JIRA_URL` empty. `ATLASSIAN_JIRA_MCP_ENABLED_TOOLS` and
`ATLASSIAN_CONFLUENCE_MCP_ENABLED_TOOLS` are independent comma-separated
allowlists of exact upstream tool names. Defaults are
`jira_search,jira_get_issue,jira_get_project_issues` and
`confluence_search,confluence_get_page` respectively.
Set only tools supported by the configured Atlassian products and deployment.
For self-hosted Atlassian instances on private networks, set
`ATLASSIAN_ALLOWED_URL_DOMAINS` to their exact hostnames; upstream SSRF checks
otherwise reject private destinations.

Build and deploy the image as `mcp-atlassian`. Register its MCP endpoint as a
provider instance, then use the existing credential broker to deliver a
credential payload containing a Jira or Confluence PAT (and its URL when the
instance URL is not configured globally). Local compatibility requires both
runtime raw delivery permission and adapter
`MCP_ADAPTER_ALLOW_RAW_CREDENTIALS=true` with `ENV=local|dev|development`.
Authentication follows the broker-returned auth_type strictly; missing fields
never cause a switch to a different scheme. PAT aliases for auth_type=token
include `token`, `pat`, `personal_token`,
`personal_access_token`, the product-specific `jira_personal_token` or
`confluence_personal_token`, and `api_token`. Basic auth
accepts `username`/`email` with `password`/`api_token`; OAuth accepts
`access_token`. The data connector URL takes precedence over credential URLs.

## Operations

The local Compose services bind to `127.0.0.1:8017` (Jira) and
`127.0.0.1:8018` (Confluence), configurable with
`ATLASSIAN_JIRA_ADAPTER_PORT` and `ATLASSIAN_CONFLUENCE_ADAPTER_PORT`.
Production provider URLs should use the corresponding service names on the
internal Compose network. Health is available at `/healthz`. The older Portal
Jira shim remains available as `atlassian-jira-legacy-mcp`.

`MCP_ADAPTER_TOOL_DESCRIPTORS` can add per-tool descriptions, annotations and
x-runtime overrides using the shared adapter format. The same allowlist rejects
direct hidden-tool calls before credential resolution.
