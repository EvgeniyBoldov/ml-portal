# Atlassian MCP Adapter

`atlassian-jira-mcp` and `atlassian-confluence-mcp` expose the upstream
[`sooperset/mcp-atlassian`](https://github.com/sooperset/mcp-atlassian) through
separate Portal-owned adapter containers. Both use the package version pinned
in `mcp/atlassian_adapter/requirements.txt`; each container is configured for
exactly one product and one product URL.

Register two MCP provider instances in Portal, one for each service. Bind each
data connector to its matching MCP provider through `access_via_instance_id`.
Discovery and runtime tool sets are isolated by provider instance, so Jira
collections resolve Jira tools and Confluence collections resolve Confluence
tools without tool-level product metadata or additional resolver logic.
Credentials remain scoped to the corresponding data connector and must contain
the matching product PAT; the data connector URL takes precedence at call time.

## Adapter responsibilities

- Issue the Portal-required `mcp-session-id` on `initialize`. Upstream runs in
  stateless Streamable HTTP mode; the adapter owns the client session for one
  hour of inactivity.
- Resolve `credential_access` with the shared secret broker for every
  `tools/call`. Credential material is never stored in the MCP session or
  process environment.
- Send broker-resolved Atlassian PATs using upstream's per-request authentication
  headers. Runtime-only arguments (`credential_access`, `instance_context`, and
  injected endpoint aliases) are removed before forwarding the public tool args.
- Filter `tools/list` by `ATLASSIAN_MCP_ENABLED_TOOLS` and enforce the same
  allowlist at call time. An empty setting falls back to the small built-in
  read-only allowlist; it does not publish every upstream tool.
- Add missing `inputSchema.x-runtime` metadata. Upstream `readOnlyHint=true`
  maps to `safe`; mutating tools map to `write`; delete/remove/archive-like
  actions map to `destructive`; unknown tools default to `destructive`. These
  flags are also reflected in `side_effects`, `requires_confirmation`, and
  `credential_scope=user`. Explicit upstream risk metadata is preserved.

The upstream process receives placeholder PATs at startup only so it can
initialize toolsets and publish their schemas. `ALLOW_GLOBAL_CRED_FALLBACK=false`
is set. Tool calls require broker credentials; the placeholders are not valid
service credentials.

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
instance URL is not configured globally). The adapter supports the standard
`credential_access` field supplied by Portal runtime.

## Operations

The local Compose services bind to `127.0.0.1:8017` (Jira) and
`127.0.0.1:8018` (Confluence), configurable with
`ATLASSIAN_JIRA_ADAPTER_PORT` and `ATLASSIAN_CONFLUENCE_ADAPTER_PORT`.
Production provider URLs should use the corresponding service names on the
internal Compose network. Health is available at `/healthz`. The older Portal
Jira shim remains available as `atlassian-jira-legacy-mcp`.
