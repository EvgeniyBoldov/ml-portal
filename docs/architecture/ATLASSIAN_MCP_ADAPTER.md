# Atlassian MCP Adapter

`atlassian-jira-mcp` and `atlassian-confluence-mcp` expose native tools from the
pinned `mcp-atlassian==0.23.1` package through Portal's shared HTTP MCP boundary.
Each provider has its own operation allowlist. Data connectors retain their
URLs and credentials and link to the provider through `access_via_instance_id`.

## Broker-bound source configuration

For each `tools/call`, the adapter exchanges the short-lived credential reference
at the configured Portal broker. The broker validates the signed data-instance
binding, credential activation, owner and authentication type, and the continued
availability of the data instance. Its additive `source_url` response field comes
from that instance's persisted `url`, alongside the credential payload.

The Atlassian adapter requires this broker-confirmed URL. URLs in public tool
arguments, `instance_context`, credential payloads and container environment do
not override it. A mismatched data-instance ID or a missing broker source URL
fails before creating a client. An older broker must be upgraded before deploying
the new adapter. Generic MCP adapters and the legacy Jira shim retain their
existing contracts.

The adapter accepts references only to the configured Portal broker endpoint,
using the API's existing `MCP_CREDENTIAL_BROKER_BASE_URL` and
`MCP_CREDENTIAL_BROKER_RESOLVE_PATH` settings. A caller cannot supply a different
resolve endpoint to manufacture a trusted source. These are control-plane
settings, not Jira/Confluence endpoints. Atlassian runtime requires the broker;
raw credentials are not an alternative path.

## Native tool integration

`source_runtime.py` creates a native Jira/Confluence config and fetcher for the
current call and supplies it through the upstream's request-scoped fetcher
boundary. Both PAT and Basic use the same broker-confirmed source, including its
context path. Jira `/rest/api/2`, `/rest/api/3`, and `/rest/api` suffixes are
normalized to a service root; Confluence REST suffixes are normalized similarly.

The embedded server mounts native Jira/Confluence tools with their existing
read-only/toolset filters. Portal's broker authentication replaces the native
public HTTP header/environment authentication middleware. In particular, Basic
no longer clones an environment-configured client, and private registered
sources are not rejected merely because their DNS points to a private address.
Discovery publishes schemas without any source URL, placeholder PAT or global
service configuration. The adapter's explicit operation allowlist still filters
`tools/list` and rejects hidden direct calls before credential resolution.

Each fetcher has its own SDK HTTP session. `SourceBoundAdapter` permits outbound
requests only to that source's origin and context path. Redirects are rejected
before another request is made; tool-supplied URLs cannot move credentials to
another host, port, scheme or context path. HTTP(S) source URLs may not contain
userinfo, query parameters or fragments. TLS verification remains enabled by
default. No `.netrc`, process proxy settings, global credential client or mutable
URL allowlist can replace the selected source or authentication.

A context variable associates the client with the current in-process upstream
exchange. Parallel calls do not share clients. After completion, failure or
cancellation the context is reset and the SDK session is closed. MCP session
state contains only an opaque ID and expiry, never a fetcher or credential.

Authentication follows the broker-returned `auth_type`:

| Type | Jira/Confluence HTTP authentication |
| --- | --- |
| `token` | Native PAT client; `Authorization: Bearer …` |
| `basic` | Native Basic client using username/email and password/api_token |
| `oauth` / `bearer` | Broker-supplied bearer header on the bound client; no global OAuth fallback |
| `api_key` | Explicit `X-API-Key` header on the bound client |

Token aliases are `jira_personal_token` / `confluence_personal_token`, `token`,
`pat`, `personal_token`, `personal_access_token`, and `api_token`. An invalid
credential never causes a switch to another authentication scheme.

## Configuration and deployment

Register the provider endpoints at their internal service addresses. The local
ports remain `ATLASSIAN_JIRA_ADAPTER_PORT` (8017) and
`ATLASSIAN_CONFLUENCE_ADAPTER_PORT` (8018); health is available at `/healthz`.

`ATLASSIAN_JIRA_MCP_ENABLED_TOOLS` and `ATLASSIAN_CONFLUENCE_MCP_ENABLED_TOOLS`
are comma-separated allowlists. Defaults are
`jira_search,jira_get_issue,jira_get_project_issues` and
`confluence_search,confluence_get_page`. Every enabled operation needs an
explicit safe/risky descriptor; the built-in defaults have safe descriptors.
`MCP_ADAPTER_TOOL_DESCRIPTORS` can provide further descriptions and risk metadata.

Source endpoint variables `ATLASSIAN_JIRA_URL`, `ATLASSIAN_CONFLUENCE_URL` and
`ATLASSIAN_ALLOWED_URL_DOMAINS` are no longer part of the Portal adapter
configuration. Set URLs on data connectors instead. No endpoint or credential
placeholders are needed to initialize the embedded tool server.

Deploy the API with the new broker response first, then rebuild/deploy the
`mcp-atlassian` image. Existing broker consumers ignore the additive field.

## Diagnostics and validation

`mcp_authentication_request` records the declared scheme, credential ID, Basic
username, known credential-field presence and masked transport header metadata.
`atlassian_source_client_bound` records the actual source origin/product chosen
for the native SDK. `auth_middleware` records the in-process source binding and
response status. Passwords, PATs, API tokens, encoded Basic values, broker JWTs,
request/response bodies and arbitrary tool arguments are not logged.

The source-runtime suite runs the real pinned server, its native tools and SDKs,
with only broker/Jira HTTP mocked. It covers discovery without service ENV,
parallel PAT/Basic source isolation, declared external schemes, normalization,
private sources, rejected caller endpoints, broker endpoint trust, redirects,
transport bounds and cancellation cleanup. Run it with the shared adapter tests:

```bash
pip install -r mcp/atlassian_adapter/requirements-test.txt
python -m pytest --noconftest -o addopts= -q \
  mcp/adapter/tests/test_adapter.py mcp/atlassian_adapter/tests/
```

The dedicated CI job installs the pinned upstream, checks adapter startup and
runs this suite on Python 3.11, matching the MCP image.
