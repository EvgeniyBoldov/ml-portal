# Shared HTTP MCP adapter

New external HTTP MCP servers are connected through a Portal-owned adapter.
Portal registers the adapter URL as its MCP connector; the data connector keeps
the destination service URL and credentials. The MCP connector has no upstream
service credentials.

`mcp/adapter/server.py` is the standalone gateway; `mcp/helpers/mcp_adapter.py`
owns the shared HTTP boundary. The Atlassian adapter uses this boundary around
its embedded upstream ASGI app. The legacy Jira and ML facade shims reuse the
shared credential resolver and authentication profiles for their REST calls.

## Credential flow

1. Runtime resolves a credential reference from the selected data connector,
   using the operation's existing credential scope policy. In broker mode it
   does not decrypt or carry the secret payload. There is no provider fallback.
2. Runtime signs a short-lived `credential_access` JWT and places it inside
   `arguments.instance_context`. The request to the adapter has no HTTP
   Authorization header; its MCP session ID is separate from credentials.
3. The adapter exchanges the JWT at the API broker on each tool call. The
   broker validates expiry, issuer/audience, data-instance ownership, credential
   activation, owner scope, and authentication type before returning the secret.
4. The adapter builds upstream authentication from the returned `auth_type` and
   the configured profile. Caller-supplied auth_type cannot override it. Missing
   fields and unsupported schemes fail rather than choosing another scheme.
5. The gateway removes `instance_context`, `credential_access`, legacy
   `credentials`, `collection_slug`, and `collection_id` from public tool args.
   Tool fields such as `url` are preserved. Runtime does not inject endpoint
   aliases or credential hints into public arguments.

Sessions hold only an opaque ID and expiry. Each upstream exchange has a fresh
client/session and the current call's authentication, including initialize. The
adapter sends `notifications/initialized`, handles JSON or bounded SSE replies,
and never replays tools/call. It supports HTTP POST MCP tools, not stdio,
legacy SSE transports, resources/prompts/subscriptions, or env-only credentials.

Discovery uses no data credentials. The upstream must expose its schema surface
without service credentials. Embedded Atlassian uses its existing non-secret
placeholder for discovery. An upstream requiring credentials even for discovery
needs an additional discovery integration; do not store a permanent discovery
secret in adapter env.

## Profiles

| Credential auth_type | Standard | Atlassian |
| --- | --- | --- |
| token | Configured header/scheme; default Authorization: Bearer | Product-specific X-Atlassian-…-Personal-Token |
| basic | Basic from username/email and password/api_token | Basic plus product URL header |
| oauth / bearer | Bearer from access_token/token | Bearer plus product URL header |
| api_key | Configured header; default X-API-Key | Same explicit API-key header; upstream must support it |

Aliases choose the value within the declared scheme, never another scheme. A
Basic credential containing only a token fails. For Token-style upstreams set
`MCP_ADAPTER_TOKEN_SCHEME=Token`. The Atlassian product is selected by the tool
name (confluence_… or Jira); the data connector URL takes precedence. Generic
upstreams can receive that URL via `MCP_ADAPTER_TARGET_URL_HEADER`. Profiles
cannot make an unmodified upstream understand arbitrary credential arguments.

Broker delivery is mandatory by default. Explicit local compatibility requires
both `MCP_ADAPTER_ALLOW_RAW_CREDENTIALS=true` and `ENV=local|dev|development`;
it accepts instance_context.credentials with an explicit auth_type. A supplied
broker context always wins, including when resolution fails. Production rejects
raw fallback.

## Tool policy

`MCP_ADAPTER_ENABLED_TOOLS` is an exact comma-separated allowlist. Empty exposes
no tools; `*` explicitly permits all. It filters tools/list and rejects direct
calls to hidden tools before secret resolution. Upstream cursors are preserved,
including on empty filtered pages.

`MCP_ADAPTER_TOOL_DESCRIPTORS` is a JSON object keyed by upstream tool name. It
can override title, description, annotations, and input-schema x-runtime. It
does not rename tools or change input/output contracts. Example:

```json
{"model_info":{"description":"Inspect deployed model contracts","x-runtime":{"risk_level":"safe","credential_scope":"auto"}}}
```

Missing risk metadata is inferred conservatively: destructive hint/name first,
then read-only/write hints; unknown operations are destructive. Explicit
metadata is retained unless configured overrides replace it. Metadata is a
capability description, not RBAC.

## Deployment

Build with `MCP_SERVER_DIR=adapter` using the existing MCP Dockerfile. Configure
upstream, profile and allowlist before starting the optional local gateway:

```bash
docker compose --profile mcp-adapter up -d --build mcp-adapter
```

The default local port is 8019. Run one configured gateway per upstream provider.
Register `http://mcp-adapter:8080/` as the MCP connector, link the data connector
through access_via_instance_id, save credentials on that data connector, onboard
discovery, and bind the collection to the agent.

Settings: `MCP_ADAPTER_UPSTREAM_URL`, `MCP_ADAPTER_AUTH_PROFILE` (standard or
atlassian), `MCP_ADAPTER_TOKEN_HEADER`, `MCP_ADAPTER_TOKEN_SCHEME`,
`MCP_ADAPTER_API_KEY_HEADER`, `MCP_ADAPTER_TARGET_URL_HEADER`,
`MCP_ADAPTER_TIMEOUT_SECONDS` (120), `MCP_SECRET_BROKER_TIMEOUT_SECONDS` (10),
`MCP_ADAPTER_SESSION_TTL_SECONDS` (3600), `MCP_ADAPTER_MAX_REQUEST_BYTES` (262144),
`MCP_ADAPTER_MAX_RESPONSE_BYTES` (1048576), `VERIFY_SSL`, and
`MCP_ADAPTER_CA_BUNDLE`. No redirects are followed with credentials.

Every runtime MCP call uses its runtime tool-call ID as `x-portal-request-id`.
Runtime forwards it through initialize and tools/call; adapters send the same ID
to the credential broker and upstream MCP server. Search API and MCP container
logs by that value to follow one call across the boundary:

```bash
docker compose logs --since=15m api ml-inference-mcp atlassian-jira-mcp atlassian-confluence-mcp \
  | rg 'request_id=<tool-call-id>'
```

Logs record dispatch, HTTP attempts and statuses, broker resolution, selected
`auth_type`, names of authentication headers (never their values), upstream
target origin, response size, JSON-RPC code, duration, and safe transport error
details such as connection errno. They never record request/response bodies,
tool arguments, credentials, broker JWTs, prompts, model inputs, or upstream
error text. User-facing MCP errors stay generic to prevent upstreams from
echoing secrets. Health is available at /healthz.

Run `make test-mcp-adapter` for the focused contract suite in the API image with
the MCP sources mounted read-only. Tests live in `mcp/adapter/tests/test_adapter.py`,
`mcp/atlassian_adapter/tests/test_credentials.py`, and the backend focused broker,
runtime credential resolver, operation builder/executor, Jira and ML shim suites.
